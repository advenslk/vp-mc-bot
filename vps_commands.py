from __future__ import annotations

import json

import discord
from discord.ext import commands

from core.components import simple_view
from proxmox.client import ProxmoxConfig, ProxmoxClient, ProxmoxError


class VPSCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def client(self):
        s = self.bot.settings
        if not all((s.proxmox_api_url, s.proxmox_token_id, s.proxmox_token_secret)):
            return None
        return ProxmoxClient(ProxmoxConfig(
            base_url=s.proxmox_api_url,
            token_id=s.proxmox_token_id,
            token_secret=s.proxmox_token_secret,
            verify_ssl=s.proxmox_verify_ssl,
        ))

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
        client = self.client()
        node = self.bot.settings.proxmox_default_node
        try:
            node = json.loads(row["metadata"] or "{}").get("node") or node
        except (TypeError, ValueError):
            pass
        if client and row["vmid"] and node:
            try:
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
            state = "running" if action in {"start","reboot"} else "stopped"
            await self.bot.db.execute(
                "UPDATE vps_servers SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (state, server_id),
            )
            await self.bot.db.execute(
                "INSERT INTO server_events(server_id,event_type,details) VALUES(?,?,?)",
                (server_id, "power", json.dumps({"signal": mapping[action]})),
            )
        else:
            client = self.client()
            node = self.bot.settings.proxmox_default_node
            try:
                node = metadata.get("node") or node
            except (TypeError, ValueError):
                pass
            if not client or not node:
                await ctx.send(view=simple_view("# VPS Control Unavailable", "Proxmox control is not configured.", discord.Colour.orange()))
                return
            if metadata.get("provider") == "lxc":
                await client.container_action(node, int(row["vmid"]), action)
            else:
                await client.vm_action(node, int(row["vmid"]), action)
            state = "running" if action == "start" else ("stopped" if action in {"stop", "shutdown"} else action)
            await self.bot.db.execute(
                "UPDATE vps_servers SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (state, server_id),
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



async def setup(bot) -> None:
    await bot.add_cog(VPSCog(bot))
