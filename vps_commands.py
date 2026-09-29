from __future__ import annotations

import json
import secrets

import discord
from discord.ext import commands

from config.emoji import e
from core.components import simple_view
from proxmox.client import ProxmoxConfig, ProxmoxClient, ProxmoxError
from proxmox.host_exec import ProxmoxHostExecutionError, ProxmoxHostExecutor

VPS_PANEL_URL = "https://cvp.helzerx.cyou"


async def reset_lxc_password(settings, vmid: int, password: str) -> None:
    await ProxmoxHostExecutor(settings).set_container_password(int(vmid), password)


async def reset_panel_password(settings, vmid: int, username: str, password: str) -> None:
    await ProxmoxHostExecutor(settings).reset_panel_user(int(vmid), username, password)


class VPSCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def client(self, cluster_name=None):
        from proxmox.client import client_from_settings
        return client_from_settings(self.bot.settings, cluster_name)

    async def own_server(self, ctx, server_id: int):
        row = await self.bot.db.fetchone(
            "SELECT s.*,p.plan_key,p.name AS plan_name FROM vps_servers s JOIN plans p ON p.id=s.plan_id WHERE s.id=? AND s.user_id=?",
            (server_id, ctx.author.id),
        )
        if not row:
            await ctx.send(view=simple_view("# VPS Not Found", "That VPS does not exist or does not belong to you.", discord.Colour.orange()))
        return row

    @commands.command(name="myvps", aliases=("vps", "servers"))
    @commands.guild_only()
    async def myvps(self, ctx):
        rows = await self.bot.db.fetchall(
            "SELECT id,hostname,plan_id,vmid,status,ipv4,expires_at FROM vps_servers WHERE user_id=? ORDER BY id DESC",
            (ctx.author.id,),
        )
        if not rows:
            body = "You do not have any VPS resources yet."
        else:
            body = "\n".join(
                "• #%s %s — VMID %s — %s%s"
                % (r["id"], r["hostname"], r["vmid"] or "-", r["status"],
                   (" — %s" % r["ipv4"]) if r["ipv4"] else "")
                for r in rows
            )
        await ctx.send(view=simple_view("# Your HelzerX VPS", body))

    @commands.command(name="vps-info")
    @commands.guild_only()
    async def info(self, ctx, server_id: int):
        row = await self.own_server(ctx, server_id)
        if not row:
            return
        body = (
            "**Hostname:** %s\n**Plan:** %s\n**VMID:** %s\n"
            "**Status:** %s\n**IPv4:** %s\n**Expires:** %s"
            % (row["hostname"], row["plan_key"], row["vmid"] or "-", row["status"],
               row["ipv4"] or "Pending/DHCP", row["expires_at"] or "-")
        )
        node = self.bot.settings.proxmox_default_node
        try:
            metadata = json.loads(row["metadata"] or "{}")
        except (TypeError, ValueError):
            metadata = {}
        node = metadata.get("node") or node
        client = self.client(metadata.get("cluster") or node)
        if client and row["vmid"] and node:
            try:
                if metadata.get("provider") == "lxc":
                    status = await client.container_status(node, int(row["vmid"]))
                else:
                    status = await client.vm_status(node, int(row["vmid"]))
                body += "\n**Provider status:** %s" % status.get("status", "unknown")
            except Exception:
                pass
        await ctx.send(view=simple_view("# VPS #%s" % server_id, body))

    async def action(self, ctx, server_id: int, action: str):
        row = await self.own_server(ctx, server_id)
        if not row:
            return
        if not row["vmid"] and not row["provider_id"]:
            await ctx.send(view=simple_view("# VPS Not Ready", "This resource is still provisioning.", discord.Colour.orange()))
            return

        try:
            metadata = json.loads(row["metadata"] or "{}")
        except (TypeError, ValueError):
            metadata = {}

        try:
            if metadata.get("provider") == "pterodactyl":
                ptero = self.bot.lifecycle.pterodactyl()
                if not ptero:
                    await ctx.send(view=simple_view("# VPS Control Unavailable", "Pterodactyl control is not configured.", discord.Colour.orange()))
                    return
                mapping = {"start": "start", "stop": "stop", "shutdown": "stop", "reboot": "restart"}
                if action not in mapping:
                    await ctx.send(view=simple_view("# Unsupported Action", "That action is not available for Minecraft resources.", discord.Colour.orange()))
                    return
                await ptero.power(str(row["provider_id"]), mapping[action])
                state = "running" if action in {"start", "reboot"} else "stopped"
                await self.bot.db.execute(
                    "UPDATE vps_servers SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (state, server_id),
                )
                await self.bot.db.execute(
                    "INSERT INTO server_events(server_id,event_type,details) VALUES(?,?,?)",
                    (server_id, "power", json.dumps({"signal": mapping[action]})),
                )
                await ctx.send(view=simple_view("# VPS Action Complete", "%s was requested for %s." % (action, row["hostname"])))
                return

            client = self.client(metadata.get("cluster"))
            node = metadata.get("node") or self.bot.settings.proxmox_default_node
            if not client or not node:
                await ctx.send(view=simple_view("# VPS Control Unavailable", "Proxmox control is not configured.", discord.Colour.orange()))
                return

            if metadata.get("provider") == "lxc":
                await client.container_action(node, int(row["vmid"]), action)
            else:
                await client.vm_action(node, int(row["vmid"]), action)

            state = "running" if action == "start" else (
                "stopped" if action in {"stop", "shutdown"} else action
            )
            await self.bot.db.execute(
                "UPDATE vps_servers SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (state, server_id),
            )
            await self.bot.db.execute(
                "INSERT INTO server_events(server_id,event_type,details) VALUES(?,?,?)",
                (server_id, "power", json.dumps({"action": action})),
            )
            await ctx.send(view=simple_view("# VPS Action Complete", "%s was requested for %s." % (action, row["hostname"])))
        except ProxmoxError as exc:
            await ctx.send(view=simple_view("# VPS Action Failed", str(exc), discord.Colour.red()))

    @commands.command(name="vps-start")
    async def start(self, ctx, server_id: int):
        await self.action(ctx, server_id, "start")

    @commands.command(name="vps-stop")
    async def stop(self, ctx, server_id: int):
        await self.action(ctx, server_id, "stop")

    @commands.command(name="vps-shutdown")
    async def shutdown(self, ctx, server_id: int):
        await self.action(ctx, server_id, "shutdown")

    @commands.command(name="vps-restart")
    async def restart(self, ctx, server_id: int):
        await self.action(ctx, server_id, "reboot")

    @commands.command(name="vps-delete")
    @commands.guild_only()
    async def delete(self, ctx, server_id: int, confirmation: str = ""):
        if confirmation.upper() != "CONFIRM":
            await ctx.send(view=simple_view(
                "# Permanent VPS Deletion",
                "This permanently deletes the provider resource. Use `%svps-delete %s CONFIRM` to continue."
                % (self.bot.settings.prefix, server_id), discord.Colour.orange()
            ))
            return
        row = await self.own_server(ctx, server_id)
        if not row:
            return
        try:
            ok = await self.bot.lifecycle.delete_server(server_id, ctx.author.id)
        except ProxmoxError as exc:
            await ctx.send(view=simple_view("# Deletion Failed", str(exc), discord.Colour.red()))
            return
        if ok:
            await ctx.send(view=simple_view("# VPS Deleted", "VPS #%s has been permanently deleted." % server_id))
        else:
            await ctx.send(view=simple_view("# VPS Not Found", "That VPS no longer exists.", discord.Colour.orange()))


    @commands.command(name="vps-password", aliases=("vps-credentials", "vps-login"))
    @commands.guild_only()
    async def password(self, ctx, server_id: int):
        row = await self.own_server(ctx, server_id)
        if not row:
            return
        try:
            metadata = json.loads(row["metadata"] or "{}")
        except (TypeError, ValueError):
            metadata = {}
        if metadata.get("provider") != "lxc":
            await ctx.send(view=simple_view("# Password Reset Unavailable", "Password reset is currently supported for LXC VPS resources."))
            return
        if not row["vmid"]:
            await ctx.send(view=simple_view("# VPS Not Ready", "This VPS is still provisioning."))
            return

        view = discord.ui.LayoutView(timeout=300)
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay("# VPS Credentials"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            "For security, the VPS password is generated only when you request it.\n"
            "Click **Generate New Password** to receive the credentials privately."
        ))
        action_row = discord.ui.ActionRow()
        button = discord.ui.Button(label="Generate New Password", style=discord.ButtonStyle.secondary, custom_id="vps:generate-password")

        async def generate(interaction: discord.Interaction) -> None:
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("These credentials belong to another member.", ephemeral=True)
                return
            node = metadata.get("node") or self.bot.settings.proxmox_default_node
            if not node:
                await interaction.response.send_message("Proxmox node is not configured for this VPS.", ephemeral=True)
                return
            new_password = secrets.token_urlsafe(15)
            panel_username = str(metadata.get("panel_username") or ("hxvps%s@pve" % int(row["vmid"])))
            panel_password = secrets.token_urlsafe(18)
            try:
                await reset_lxc_password(self.bot.settings, int(row["vmid"]), new_password)
                await reset_panel_password(self.bot.settings, int(row["vmid"]), panel_username, panel_password)
                await self.bot.db.execute(
                    "UPDATE vps_servers SET username=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    ("root", server_id),
                )
            except ProxmoxHostExecutionError as exc:
                await interaction.response.send_message("Password reset failed: %s" % str(exc), ephemeral=True)
                return
            panel = VPS_PANEL_URL
            credential_view = discord.ui.LayoutView(timeout=600)
            credential_container = discord.ui.Container()
            credential_container.add_item(discord.ui.TextDisplay(
                "# %s HelzerX Cloud — VPS Credentials" % e("brand", "◆")
            ))
            credential_container.add_item(discord.ui.Separator())
            credential_container.add_item(discord.ui.TextDisplay(
                "### %s VPS Ready\n"
                "Your VPS has been provisioned successfully. Keep these credentials private."
                % e("node", "▣")
            ))
            credential_container.add_item(discord.ui.Separator())
            credential_container.add_item(discord.ui.TextDisplay(
                "### %s Connection Details\n"
                "> **Hostname:** `%s`\n"
                "> **VMID:** `%s`\n"
                "> **Node:** `%s`"
                % (e("code", "▣"), row["hostname"], row["vmid"], node)
            ))
            credential_container.add_item(discord.ui.Separator())
            credential_container.add_item(discord.ui.TextDisplay(
                "### %s VPS Login Credentials\n"
                "> **Username:** `root`\n"
                "> **Password:** `%s`"
                % (e("star", "★"), new_password)
            ))
            credential_container.add_item(discord.ui.Separator())
            credential_container.add_item(discord.ui.TextDisplay(
                "### %s Proxmox Panel Login\n"
                "> **Username:** `%s`\n"
                "> **Password:** `%s`\n\n"
                "%s"
                % (e("support", "↗"), panel_username, panel_password, panel)
            ))
            credential_container.add_item(discord.ui.Separator())
            credential_container.add_item(discord.ui.TextDisplay(
                "%s **Security Notice**\n"
                "These credentials are shown only to you. Do not share them publicly. "
                "The Proxmox account is restricted to this VPS only."
                % e("warning", "⚠")
            ))
            credential_view.add_item(credential_container)

            try:
                await interaction.user.send(view=credential_view)
            except discord.Forbidden:
                await interaction.response.send_message(view=credential_view, ephemeral=True)
                return
            await interaction.response.send_message(
                "%s Your VPS credentials were sent to your DMs."
                % e("brand", "◆"),
                ephemeral=True,
            )

        button.callback = generate
        action_row.add_item(button)
        container.add_item(action_row)
        view.add_item(container)
        await ctx.send(view=view)

async def setup(bot) -> None:
    await bot.add_cog(VPSCog(bot))
