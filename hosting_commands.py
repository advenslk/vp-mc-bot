from __future__ import annotations

import discord
from discord.ext import commands

from core.components import provisioning_view, simple_view
from economy.service import EconomyError
from hosting.service import HostingService


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
