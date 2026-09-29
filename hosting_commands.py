from __future__ import annotations

import discord
from discord.ext import commands

from core.components import provisioning_view, simple_view
from economy.service import EconomyError
from hosting.os_options import available_os_options
from hosting.service import HostingService


class VPSOSSelectionView(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, author_id: int, redemption_id: int, plan_key: str):
        super().__init__(timeout=300)
        self.bot = bot
        self.author_id = author_id
        self.redemption_id = redemption_id
        self.plan_key = plan_key

        env = {
            "PROXMOX_TEMPLATE_CTID": str(bot.settings.proxmox_template_ctid or ""),
            "PROXMOX_UBUNTU_2204_TEMPLATE_CTID": str(bot.settings.proxmox_ubuntu_2204_template_ctid or ""),
            "PROXMOX_UBUNTU_2404_TEMPLATE_CTID": str(bot.settings.proxmox_ubuntu_2404_template_ctid or ""),
            "PROXMOX_ALMALINUX_9_TEMPLATE_CTID": str(bot.settings.proxmox_almalinux_9_template_ctid or ""),
        }
        options = available_os_options(env)
        self._templates = {key: (label, ctid) for key, label, ctid in options}

        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay("# HelzerX Cloud — Select VPS OS"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            "Choose the operating system for your VPS. Provisioning starts only after you select one."
        ))

        if options:
            select = discord.ui.Select(
                placeholder="Select an operating system...",
                min_values=1,
                max_values=1,
                options=[
                    discord.SelectOption(
                        label=label,
                        value=key,
                        description="Use %s for this VPS." % label,
                    )
                    for key, label, _ctid in options
                ],
            )

            async def select_os(interaction: discord.Interaction) -> None:
                if interaction.user.id != self.author_id:
                    await interaction.response.send_message(
                        "This OS selector belongs to the user who redeemed the VPS.",
                        ephemeral=True,
                    )
                    return

                key = select.values[0]
                label, template_ctid = self._templates[key]
                redemption = await self.bot.db.fetchone(
                    "SELECT status FROM redemptions WHERE id=? AND user_id=?",
                    (self.redemption_id, self.author_id),
                )
                if not redemption or redemption["status"] != "pending":
                    await interaction.response.send_message(
                        "This VPS redemption is no longer waiting for OS selection.",
                        ephemeral=True,
                    )
                    return

                await interaction.response.defer()
                await self.bot.db.execute(
                    "UPDATE redemptions SET os_key=?,template_ctid=? "
                    "WHERE id=? AND user_id=? AND status='pending'",
                    (key, template_ctid, self.redemption_id, self.author_id),
                )
                await self.bot.provisioner.enqueue_pending()

                job = await self.bot.db.fetchone(
                    "SELECT id FROM provisioning_jobs WHERE redemption_id=? ORDER BY id DESC LIMIT 1",
                    (self.redemption_id,),
                )
                detail = "OS selected: **%s**. Your VPS is now queued for provisioning." % label
                if job:
                    await self.bot.db.execute(
                        "UPDATE provisioning_jobs SET channel_id=?,message_id=?,"
                        "progress_stage=?,progress_percent=?,progress_detail=? WHERE id=?",
                        (
                            interaction.channel_id,
                            interaction.message.id,
                            "Queued",
                            5,
                            detail,
                            int(job["id"]),
                        ),
                    )

                await interaction.message.edit(
                    content=None,
                    view=provisioning_view(self.plan_key, "Queued", 5, detail),
                )
                self.stop()

            select.callback = select_os
            row = discord.ui.ActionRow(select)
            container.add_item(row)
        else:
            container.add_item(
                discord.ui.TextDisplay(
                    "No VPS operating system templates are configured by the administrator."
                )
            )

        self.add_item(container)


class HostingRedemptionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hosting = bot.hosting

    @commands.command(name="redeem")
    @commands.guild_only()
    async def redeem(self, ctx: commands.Context, plan_key: str) -> None:
        await self.bot.economy.ensure_user(ctx.author.id, str(ctx.author), ctx.author.display_name)
        try:
            result = await self.hosting.redeem(ctx.author.id, plan_key)
        except (ValueError, EconomyError) as exc:
            await ctx.send(view=simple_view("# Redemption Unavailable", str(exc), discord.Colour.orange()))
            return
        plan = await self.bot.db.fetchone("SELECT kind FROM plans WHERE plan_key=?", (plan_key.upper(),))
        if plan and plan["kind"] == "vps":
            options = available_os_options({
                "PROXMOX_TEMPLATE_CTID": str(self.bot.settings.proxmox_template_ctid or ""),
                "PROXMOX_UBUNTU_2204_TEMPLATE_CTID": str(self.bot.settings.proxmox_ubuntu_2204_template_ctid or ""),
                "PROXMOX_UBUNTU_2404_TEMPLATE_CTID": str(self.bot.settings.proxmox_ubuntu_2404_template_ctid or ""),
                "PROXMOX_ALMALINUX_9_TEMPLATE_CTID": str(self.bot.settings.proxmox_almalinux_9_template_ctid or ""),
            })
            if not options:
                await self.bot.hosting.fail_and_refund(result.redemption_id, "No VPS operating system templates are configured.")
                await ctx.send(view=simple_view("# Redemption Unavailable", "No VPS operating system templates are configured.", discord.Colour.orange()))
                return
            await ctx.send(view=VPSOSSelectionView(self.bot, ctx.author.id, result.redemption_id, plan_key.upper()))
            return
        await self.bot.provisioner.enqueue_pending()
        job = await self.bot.db.fetchone(
            "SELECT id FROM provisioning_jobs WHERE redemption_id=? ORDER BY id DESC LIMIT 1",
            (result.redemption_id,),
        )
        progress = await ctx.send(view=provisioning_view(
            plan_key.upper(),
            "Queued",
            5,
            "Your redemption has been accepted and is waiting for the provisioning worker.",
        ))
        if job:
            await self.bot.db.execute(
                "UPDATE provisioning_jobs SET channel_id=?,message_id=?,progress_stage=?,progress_percent=?,progress_detail=? WHERE id=?",
                (ctx.channel.id, progress.id, "Queued", 5,
                 "Your redemption has been accepted and is waiting for the provisioning worker.",
                 int(job["id"])),
            )

    @commands.command(name="my-redemptions", aliases=("redemptions",))
    async def my_redemptions(self, ctx: commands.Context) -> None:
        rows = await self.bot.db.fetchall(
            """SELECT r.id,p.plan_key,p.name,r.cost,r.status,r.provider_resource_id,r.created_at
               FROM redemptions r JOIN plans p ON p.id=r.plan_id
               WHERE r.user_id=? ORDER BY r.id DESC LIMIT 20""",
            (ctx.author.id,),
        )
        if not rows:
            body = "You have no hosting redemptions."
        else:
            body = "\n".join(
                "%s · %s · %s HZL · %s" % (
                    row["plan_key"], row["status"], format(row["cost"], ","), row["created_at"][:16]
                )
                for row in rows
            )
        await ctx.send(view=simple_view("# My Hosting Redemptions", body))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HostingRedemptionCog(bot))
