from __future__ import annotations

import discord
from config.emoji import e


def wallet_view(
    display_name: str,
    balance: int,
    invites: int,
    recent: str,
    transactions_text: str = "",
    rewards_text: str = "",
) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=300)
    container = discord.ui.Container()
    container.add_item(discord.ui.TextDisplay("# %s HelzerX Wallet" % e("currency", "◈")))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(
        "### %s\n"
        "> **Balance:** `%s HZL`\n"
        "> **Verified Invites:** `%s`"
        % (display_name, format(balance, ","), invites)
    ))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay("### Recent Activity\n" + (recent or "No recent activity.")))

    row = discord.ui.ActionRow()
    transactions_button = discord.ui.Button(label="Transactions", custom_id="wallet:transactions", style=discord.ButtonStyle.secondary, emoji=e("money", "◈"))
    rewards_button = discord.ui.Button(label="Rewards", custom_id="wallet:rewards", style=discord.ButtonStyle.secondary, emoji=e("gift", "◆"))

    async def show_transactions(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "### HZL Transaction History\n" + (transactions_text or "No transactions yet."),
            ephemeral=True,
        )

    async def show_rewards(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "### HelzerX Rewards\n" + (
                rewards_text
                or "Earn HZL through daily rewards, eligible activity, verified invites, quests and achievements."
            ),
            ephemeral=True,
        )

    transactions_button.callback = show_transactions
    rewards_button.callback = show_rewards
    row.add_item(transactions_button)
    row.add_item(rewards_button)
    container.add_item(row)
    view.add_item(container)
    return view


def simple_view(title: str, body: str, colour: discord.Colour = discord.Colour.blurple()) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=300)
    container = discord.ui.Container()
    container.add_item(discord.ui.TextDisplay(title))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(body))
    view.add_item(container)
    return view


def plans_view(kind: str, plans: list) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=300)
    container = discord.ui.Container()
    icon = e("minecraft") if kind == "minecraft" else e("node")
    container.add_item(discord.ui.TextDisplay("# %s HelzerX %s Plans" % (icon, kind.title())))
    container.add_item(discord.ui.TextDisplay(
        "Choose a plan that matches your resource needs. "
        "Use `.redeem <plan>` when you are ready to redeem a configured HZL plan."
    ))
    container.add_item(discord.ui.Separator())

    if not plans:
        container.add_item(discord.ui.TextDisplay("No plans are currently available."))
    else:
        for index, p in enumerate(plans):
            body = (
                "### %s · `%s`\n"
                "%s `%s GB`  %s `%s`  %s `%s GB`\n"
                "%s **%s HZL** · **$%.2f/month** · `%s`"
            ) % (
                p["name"], p["plan_key"], e("ram", "RAM"), p["ram_mb"] // 1024,
                e("cpu", "CPU"), p["cpu_units"], e("disk", "Disk"), p["storage_gb"],
                e("currency", "◈"), p["hzl_cost"], p["price_usd"], p["location"],
            )
            container.add_item(discord.ui.TextDisplay(body))
            if index != len(plans) - 1:
                container.add_item(discord.ui.Separator())
    view.add_item(container)
    return view


def provisioning_view(plan_key: str, stage: str, percent: int, detail: str, status: str = "provisioning") -> discord.ui.LayoutView:
    percent = max(0, min(100, int(percent)))
    filled = int(round(percent / 10))
    bar = "█" * filled + "░" * (10 - filled)
    view = discord.ui.LayoutView(timeout=300)
    container = discord.ui.Container()
    container.add_item(discord.ui.TextDisplay("# HelzerX Cloud — VPS Provisioning"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(
        "### `%s`\n`%s` **%s%%**\n\n**Stage:** %s\n%s\n\n**Status:** `%s`"
        % (plan_key, bar, percent, stage, detail, status)
    ))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay("This message updates automatically while the VPS is being prepared."))
    view.add_item(container)
    return view
