from __future__ import annotations

import discord
from config.emoji import e


def wallet_view(display_name: str, balance: int, invites: int, recent: str) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=180)
    box = discord.ui.Container(accent_colour=discord.Colour.blurple())
    box.add_item(discord.ui.TextDisplay("# %s HelzerX Wallet" % e("currency", "◈")))
    box.add_item(discord.ui.Separator())
    box.add_item(discord.ui.TextDisplay(
        "### %s\\n> **Balance:** \`%s HZL\`\\n> **Verified Invites:** \`%s\`"
        % (display_name, format(balance, ","), invites)
    ))
    box.add_item(discord.ui.Separator())
    box.add_item(discord.ui.TextDisplay("**Recent Activity**\\n" + recent))
    row = discord.ui.ActionRow()
    row.add_item(discord.ui.Button(label="Transactions", custom_id="wallet:transactions",
                                   style=discord.ButtonStyle.secondary, emoji=e("money", "◈")))
    row.add_item(discord.ui.Button(label="Rewards", custom_id="wallet:rewards",
                                   style=discord.ButtonStyle.primary, emoji=e("gift", "◆")))
    box.add_item(row)
    view.add_item(box)
    return view


def simple_view(title: str, body: str, colour: discord.Colour = discord.Colour.blurple()) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=180)
    box = discord.ui.Container(accent_colour=colour)
    box.add_item(discord.ui.TextDisplay(title))
    box.add_item(discord.ui.Separator())
    box.add_item(discord.ui.TextDisplay(body))
    view.add_item(box)
    return view


def plans_view(kind: str, plans: list) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=180)
    box = discord.ui.Container(accent_colour=discord.Colour.blurple())
    icon = e("minecraft") if kind == "minecraft" else e("node")
    box.add_item(discord.ui.TextDisplay("# %s HelzerX %s Plans" % (icon, kind.title())))
    box.add_item(discord.ui.Separator())
    if not plans:
        box.add_item(discord.ui.TextDisplay("No plans are currently available."))
    else:
        for p in plans:
            body = (
                "### %s · \`%s\`\\n"
                "%s \`%s GB\`  %s \`%s\`  %s \`%s GB\`\\n"
                "%s **%s HZL** · $%.2f/month · \`%s\`"
            ) % (
                p["name"], p["plan_key"], e("ram", "RAM"), p["ram_mb"] // 1024,
                e("cpu", "CPU"), p["cpu_units"], e("disk", "Disk"), p["storage_gb"],
                e("currency", "◈"), p["hzl_cost"], p["price_usd"], p["location"]
            )
            box.add_item(discord.ui.TextDisplay(body))
            box.add_item(discord.ui.Separator())
    view.add_item(box)
    return view
