from __future__ import annotations

import discord
from discord.ext import commands


class HelpView(discord.ui.LayoutView):
    def __init__(self, prefix: str):
        super().__init__(timeout=600)
        self.prefix = prefix
        self._render("home")

    def _categories(self) -> list[discord.SelectOption]:
        return [
            discord.SelectOption(label="Overview", value="home", description="HelzerX Cloud command center", emoji="⌂"),
            discord.SelectOption(label="Economy", value="economy", description="HZL balance, rewards and activity", emoji="◈"),
            discord.SelectOption(label="Hosting", value="hosting", description="Minecraft, VPS plans and redemptions", emoji="◆"),
            discord.SelectOption(label="VPS Management", value="vps", description="View and control your VPS resources", emoji="▣"),
            discord.SelectOption(label="Account", value="account", description="Link and check your HelzerX account", emoji="◎"),
            discord.SelectOption(label="Admin", value="admin", description="Owner-only administration commands", emoji="⚙"),
        ]

    def _command(self, name: str, description: str) -> str:
        return "**%s%s** — %s" % (self.prefix, name, description)

    def _content(self, category: str) -> tuple[str, str]:
        p = self.prefix

        if category == "economy":
            return ("# HZL Economy", "\n".join([
                "Manage your HelzerX reward wallet and community progress.", "",
                self._command("profile", "View your wallet, HZL balance, verified invites and recent activity."),
                self._command("balance", "Check your current HZL balance."),
                self._command("daily", "Claim the configured daily HZL reward."),
                self._command("invites", "View your verified Discord invite count."),
                self._command("transactions", "View your recent HZL transaction history."),
                self._command("leaderboard", "View the current HZL leaderboard."),
                self._command("rewards", "See the available ways to earn HZL."),
                self._command("quests", "Track active quests and their rewards."),
                self._command("achievements", "View unlocked and locked achievements."),
            ]))

        if category == "hosting":
            return ("# HelzerX Hosting", "\n".join([
                "Browse hosting plans and manage your HZL redemptions.", "",
                self._command("mc-plans", "View available Minecraft hosting plans."),
                self._command("vps-plans", "View available VPS plans."),
                self._command("redeem <plan>", "Reserve a configured hosting plan using HZL."),
                self._command("my-redemptions", "View your hosting redemption history."), "",
                "Example: `%sredeem HXC-S04`" % p,
            ]))

        if category == "vps":
            return ("# VPS Management", "\n".join([
                "View and control VPS resources provisioned through HelzerX.", "",
                self._command("myvps", "List your VPS resources."),
                self._command("vps-info <id>", "Show VPS plan, VMID, status, IP and expiry details."),
                self._command("vps-start <id>", "Start your VPS."),
                self._command("vps-stop <id>", "Stop your VPS."),
                self._command("vps-shutdown <id>", "Request a graceful shutdown."),
                self._command("vps-restart <id>", "Restart your VPS."),
                self._command("vps-delete <id> CONFIRM", "Permanently delete your VPS resource."),
            ]))

        if category == "account":
            return ("# HelzerX Account", "\n".join([
                "Connect your Discord identity with the HelzerX Cloud web account.", "",
                self._command("account-link", "Generate a one-time Discord account linking code."),
                self._command("account-status", "Check your linked account and verification status."), "",
                "Link codes are one-time credentials and expire after a short period.",
            ]))

        if category == "admin":
            return ("# Administration", "\n".join([
                "Owner-only commands for economy, plans and infrastructure configuration.", "",
                self._command("admin-add <member> <amount>", "Credit HZL to a member."),
                self._command("admin-remove <member> <amount>", "Debit HZL from a member."),
                self._command("admin-plan-cost <plan> <hzl>", "Set a plan's HZL redemption cost."),
                self._command("admin-plan-set <plan> <price> <hzl> <days>", "Update plan price, HZL cost and duration."),
                self._command("admin-plan-target <plan> <cluster> [node]", "Set a plan's provisioning target."),
                self._command("admin-plan-toggle <plan> <0|1>", "Enable or disable a plan."),
                self._command("admin-plan-provider <plan> <qemu|lxc|pterodactyl>", "Set the provisioning provider."),
                self._command("admin-node-add <name> <node> <location> <api>", "Register a Proxmox node."),
                self._command("admin-node-toggle <name> <0|1>", "Enable or disable a node."),
                self._command("admin-node-health", "Check configured Proxmox node health."),
                self._command("admin-nodes", "List configured Proxmox nodes."),
            ]))

        return ("# HelzerX Cloud Help", "\n".join([
            "**Infrastructure Built For Everyone**",
            "Your command center for HZL rewards, hosting plans, VPS resources and your HelzerX account.", "",
            "**Getting started**",
            "1. Check your wallet with `%sprofile`." % p,
            "2. Browse `%smc-plans` or `%svps-plans`." % (p, p),
            "3. Use `%sredeem <plan>` when you have enough HZL." % p, "",
            "**Command categories**",
            "Use the menu below to open a focused help section. Each section includes the command, what it does and the expected arguments.", "",
            "Prefix: `%s`" % p,
        ]))

    async def _select_callback(self, interaction: discord.Interaction) -> None:
        category = interaction.data.get("values", ["home"])[0]
        self._render(category)
        await interaction.response.edit_message(view=self)

    def _render(self, category: str) -> None:
        self.clear_items()
        title, body = self._content(category)
        self.add_item(discord.ui.TextDisplay(title))
        self.add_item(discord.ui.Separator())
        self.add_item(discord.ui.TextDisplay(body))
        self.add_item(discord.ui.Separator())

        row = discord.ui.ActionRow()
        select = discord.ui.Select(
            placeholder="Select a help category…",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=option.label, value=option.value, description=option.description,
                    emoji=option.emoji, default=(option.value == category),
                )
                for option in self._categories()
            ],
        )
        select.callback = self._select_callback
        row.add_item(select)
        self.add_item(row)


class CommunityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="help", aliases=("commands",))
    async def help(self, ctx: commands.Context) -> None:
        await ctx.send(view=HelpView(self.bot.settings.prefix))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommunityCog(bot))
