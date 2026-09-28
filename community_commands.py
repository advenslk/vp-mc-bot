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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommunityCog(bot))
