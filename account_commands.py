from __future__ import annotations

from discord.ext import commands

from core.components import simple_view


class AccountCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="account-link")
    @commands.guild_only()
    async def account_link(self, ctx):
        await self.bot.economy.ensure_user(ctx.author.id, str(ctx.author), ctx.author.display_name)
        code = await self.bot.accounts.create_link_code(ctx.author.id)
        await ctx.author.send(
            "## HelzerX Cloud Account Link Code\\n"
            "Use this one-time code on the HelzerX Cloud website to link your Discord account:\\n\\n"
            "**%s**\\n\\n"
            "It expires in 10 minutes." % code
        )
        await ctx.send(view=simple_view("# Account Link Code", "I sent a one-time link code to your Discord DMs. It expires in 10 minutes."))

    @commands.command(name="account-status")
    @commands.guild_only()
    async def account_status(self, ctx):
        row = await self.bot.db.fetchone(
            "SELECT email,email_verified,created_at FROM accounts WHERE user_id=?",
            (ctx.author.id,),
        )
        if not row:
            body = "No HelzerX web account is linked."
        else:
            body = "Email: **%s**\\nVerification: **%s**\\nCreated: `%s`" % (
                row["email"], "verified" if row["email_verified"] else "pending", row["created_at"]
            )
        await ctx.send(view=simple_view("# HelzerX Account", body))


async def setup(bot) -> None:
    await bot.add_cog(AccountCog(bot))