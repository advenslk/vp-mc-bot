from __future__ import annotations

import discord
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

        view = discord.ui.LayoutView(timeout=600)
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay("# HelzerX Cloud Account Link"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            "Your one-time account link code is ready.\n"
            "Click **Show Link Code** to reveal it privately.\n\n"
            "The code expires in **10 minutes**."
        ))
        row = discord.ui.ActionRow()
        button = discord.ui.Button(
            label="Show Link Code",
            style=discord.ButtonStyle.secondary,
            custom_id="account-link:show-code",
        )

        async def show_code(interaction: discord.Interaction) -> None:
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message(
                    "This link code belongs to another member.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                "## HelzerX Cloud Account Link Code\n"
                "Use this one-time code on the HelzerX Cloud website:\n\n"
                "**%s**\n\n"
                "It expires in 10 minutes." % code,
                ephemeral=True,
            )

        button.callback = show_code
        row.add_item(button)
        container.add_item(row)
        view.add_item(container)

        await ctx.send(view=view)

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