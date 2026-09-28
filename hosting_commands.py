from __future__ import annotations

import discord
from discord.ext import commands

from core.components import simple_view
from economy.service import EconomyError
from hosting.service import HostingService


class HostingRedemptionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hosting = HostingService(bot.db, bot.economy)

    @commands.command(name="redeem")
    @commands.guild_only()
    async def redeem(self, ctx: commands.Context, plan_key: str) -> None:
        await self.bot.economy.ensure_user(ctx.author.id, str(ctx.author), ctx.author.display_name)
        try:
            result = await self.hosting.redeem(ctx.author.id, plan_key)
        except (ValueError, EconomyError) as exc:
            await ctx.send(view=simple_view("# Redemption Unavailable", str(exc), discord.Colour.orange()))
            return
        await ctx.send(view=simple_view(
            "# Redemption Reserved",
            "Your request for **%s** has been reserved.\n"
            "Redemption ID: **%s**\n"
            "Status: **%s**\n\n"
            "A provisioning worker can now safely create the resource. If provisioning fails, the reservation is automatically refundable."
            % (plan_key.upper(), result.redemption_id, result.status)
        ))

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
