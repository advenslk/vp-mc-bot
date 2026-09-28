from __future__ import annotations

import discord
from discord.ext import commands

from core.components import simple_view


class CommunityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="help", aliases=("commands",))
    async def help(self, ctx: commands.Context) -> None:
        p = self.bot.settings.prefix
        body = (
            "### Economy\n"
            "%sprofile · %sbalance · %sdaily · %sinvites\n"
            "%stransactions · %sleaderboard · %srewards · %squests · %sachievements\n\n"
            "### Hosting\n"
            "%smc-plans · %svps-plans · %sredeem <plan> · %smy-redemptions\n"
            "%smyvps · %svps-info <id> · %svps-start <id> · %svps-stop <id> · %svps-restart <id>\n"
            "%svps-delete <id> CONFIRM\n\n"
            "### Admin\n"
            "%sadmin-add · %sadmin-remove · %sadmin-plan-cost <plan> <hzl> · %sadmin-plan-toggle <plan> <0|1>\n"
            "%sadmin-plan-provider <plan> <qemu|lxc|pterodactyl> · %sadmin-node-add · %sadmin-node-toggle · %sadmin-nodes\n\n"
            "All reward accounting is recorded in the HZL transaction ledger."
        ) % (
            p,p,p,p,p,p,p,p,p,p,p,p,p,p,p,p,p,p,p,p,p,p,p,p,p,p,p
        )
        await ctx.send(view=simple_view("# HelzerX Cloud Command Center", body))

    @commands.command(name="quests")
    async def quests(self, ctx: commands.Context) -> None:
        rows = await self.bot.db.fetchall(
            "SELECT name,description,target,reward,period FROM quests WHERE enabled=1 ORDER BY id ASC"
        )
        if not rows:
            body = "No active quests are configured yet."
        else:
            body = "\n".join(
                "• **%s** — %s | %d target | +%d HZL | %s"
                % (r["name"], r["description"], r["target"], r["reward"], r["period"])
                for r in rows
            )
        await ctx.send(view=simple_view("# HZL Quests", body))

    @commands.command(name="achievements", aliases=("achievements-list",))
    async def achievements(self, ctx: commands.Context) -> None:
        rows = await self.bot.db.fetchall(
            "SELECT name,description,reward FROM achievements ORDER BY achievement_key"
        )
        body = "\n".join(
            "• **%s** — %s | +%d HZL" % (r["name"], r["description"], r["reward"])
            for r in rows
        ) or "No achievements configured."
        await ctx.send(view=simple_view("# HZL Achievements", body))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommunityCog(bot))
