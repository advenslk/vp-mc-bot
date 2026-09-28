from __future__ import annotations

import discord
from discord.ext import commands

from config.emoji import e
from core.components import plans_view, simple_view, wallet_view
from economy.service import EconomyError, EconomyService


class EconomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economy: EconomyService = bot.economy

    async def _ensure(self, ctx: commands.Context) -> None:
        user = ctx.author
        await self.economy.ensure_user(user.id, str(user), user.display_name)

    @commands.command(name="profile", aliases=("wallet", "me"))
    @commands.guild_only()
    async def profile(self, ctx: commands.Context) -> None:
        await self._ensure(ctx)
        balance = await self.economy.balance(ctx.author.id)
        invites = await self.economy.invite_count(ctx.guild.id, ctx.author.id)
        recent = await self.economy.recent_summary(ctx.author.id)
        transactions = await self.economy.transactions(ctx.author.id, 8)
        transaction_text = "\n".join(
            "%s%s HZL · %s · %s" % (
                "+" if row["amount"] >= 0 else "",
                row["amount"],
                row["source"],
                row["transaction_type"],
            )
            for row in transactions
        ) or "No transactions yet."
        rewards_text = (
            "• Daily check-in — configurable reward\n"
            "• Eligible community activity — cooldown protected\n"
            "• Verified Discord invites — anti-abuse checks\n"
            "• Quests and achievements — database driven\n\n"
            "HZL is an internal HelzerX reward currency with no cash value."
        )
        await self.economy.unlock_achievement(ctx.author.id, "first_profile")
        await ctx.send(view=wallet_view(
            ctx.author.display_name,
            balance,
            invites,
            recent,
            transaction_text,
            rewards_text,
        ))

    @commands.command(name="balance", aliases=("bal", "hzl"))
    async def balance(self, ctx: commands.Context) -> None:
        await self._ensure(ctx)
        value = await self.economy.balance(ctx.author.id)
        await ctx.send(view=simple_view(
            "# %s HZL Balance" % e("currency", "◈"),
            "Your current balance is **%s HZL**." % format(value, ",")
        ))

    @commands.command(name="daily")
    @commands.guild_only()
    async def daily(self, ctx: commands.Context) -> None:
        await self._ensure(ctx)
        ok, value = await self.economy.claim_daily(ctx.author.id, self.bot.settings.daily_reward)
        if not ok:
            hours, rem = divmod(value, 3600)
            minutes, _ = divmod(rem, 60)
            await ctx.send(view=simple_view(
                "# Daily Reward",
                "You have already claimed your daily reward. Try again in **%dh %dm**." % (hours, minutes),
                discord.Colour.orange()
            ))
            return
        await self.economy.unlock_achievement(ctx.author.id, "first_daily")
        await ctx.send(view=simple_view(
            "# %s Daily Reward Claimed" % e("gift", "◆"),
            "You received **+%s HZL**. Your balance is now **%s HZL**."
            % (format(value, ","), format(await self.economy.balance(ctx.author.id), ","))
        ))

    @commands.command(name="invites")
    @commands.guild_only()
    async def invites(self, ctx: commands.Context) -> None:
        await self._ensure(ctx)
        count = await self.economy.invite_count(ctx.guild.id, ctx.author.id)
        await ctx.send(view=simple_view(
            "# %s Verified Invites" % e("invites", "◆"),
            "You have **%d verified invites**.\n\nInvite rewards are issued only for valid, non-self, non-bot members."
            % count
        ))

    @commands.command(name="transactions", aliases=("tx", "history"))
    async def transactions(self, ctx: commands.Context) -> None:
        await self._ensure(ctx)
        rows = await self.economy.transactions(ctx.author.id, 15)
        if not rows:
            body = "No transactions yet."
        else:
            body = "\n".join(
                "%s%s HZL · %s · %s" % (
                    "+" if row["amount"] >= 0 else "",
                    row["amount"], row["source"], row["transaction_type"]
                )
                for row in rows
            )
        await ctx.send(view=simple_view("# HZL Transaction History", body))

    @commands.command(name="leaderboard", aliases=("lb", "top"))
    async def leaderboard(self, ctx: commands.Context) -> None:
        rows = await self.economy.leaderboard(10)
        body = "No economy data yet." if not rows else "\n".join(
            "%d. **%s** — %s HZL" % (i, row["display_name"], format(row["balance"], ","))
            for i, row in enumerate(rows, 1)
        )
        await ctx.send(view=simple_view("# HZL Leaderboard", body))


    @commands.command(name="quests", aliases=("quest",))
    @commands.guild_only()
    async def quests(self, ctx: commands.Context) -> None:
        await self._ensure(ctx)
        rows = await self.economy.quests(ctx.author.id)
        body = "\n".join(
            "• **%s** — %s/%s%s\n  %s · +%s HZL"
            % (r["name"], r["progress"], r["target"], " ✓" if r["completed"] else "",
               r["description"], format(r["reward"], ","))
            for r in rows
        ) or "No active quests."
        await ctx.send(view=simple_view("# HZL Quests", body))

    @commands.command(name="achievements", aliases=("achievements-list",))
    async def achievements(self, ctx: commands.Context) -> None:
        await self._ensure(ctx)
        rows = await self.economy.achievements(ctx.author.id)
        body = "\n".join(
            "• **%s** — %s%s"
            % (r["name"], "Unlocked" if r["unlocked_at"] else "Locked",
               (" · +%s HZL" % format(r["reward"], ",")) if r["reward"] else "")
            for r in rows
        ) or "No achievements configured."
        await ctx.send(view=simple_view("# HZL Achievements", body))

class HostingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _plans(self, ctx: commands.Context, kind: str) -> None:
        rows = await self.bot.db.fetchall(
            """SELECT id,plan_key,name,ram_mb,cpu_units,storage_gb,price_usd,hzl_cost,location
               FROM plans WHERE kind=? AND enabled=1 ORDER BY ram_mb ASC""",
            (kind,),
        )
        await ctx.send(view=plans_view(kind, rows))

    @commands.command(name="mc-plans", aliases=("minecraft-plans", "mcplans"))
    async def minecraft_plans(self, ctx: commands.Context) -> None:
        await self._plans(ctx, "minecraft")

    @commands.command(name="vps-plans", aliases=("vpsplans",))
    async def vps_plans(self, ctx: commands.Context) -> None:
        await self._plans(ctx, "vps")

    @commands.command(name="rewards", aliases=("reward",))
    async def rewards(self, ctx: commands.Context) -> None:
        body = (
            "### HZL Earning\n"
            "• Daily check-in — configurable reward\n"
            "• Eligible community activity — cooldown protected\n"
            "• Verified Discord invites — anti-abuse checks\n"
            "• Quests and achievements — database driven\n\n"
            "HZL is an internal HelzerX reward currency. It has no cash value and cannot be withdrawn."
        )
        await ctx.send(view=simple_view("# %s HelzerX Rewards" % e("gift", "◆"), body))


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _owner(self, ctx: commands.Context) -> bool:
        return ctx.author.id in self.bot.settings.owner_ids or await self.bot.is_owner(ctx.author)

    @commands.command(name="admin-add")
    async def admin_add(self, ctx: commands.Context, member: discord.Member, amount: int, *, reason: str = "manual adjustment") -> None:
        if not await self._owner(ctx):
            await ctx.send(view=simple_view("# Permission Denied", "This command is restricted to bot owners.", discord.Colour.red()))
            return
        if amount <= 0:
            await ctx.send(view=simple_view("# Invalid Amount", "Amount must be greater than zero.", discord.Colour.orange()))
            return
        await self.bot.economy.ensure_user(member.id, str(member), member.display_name)
        before, after = await self.bot.economy.change_balance(member.id, amount, "admin_credit", "admin", str(ctx.author.id), {"reason": reason})
        await self.bot.db.execute("INSERT INTO audit_logs(actor_id,action,target_id,details) VALUES(?,?,?,?)",
                                   (ctx.author.id, "economy.credit", str(member.id), reason))
        await ctx.send(view=simple_view(
            "# HZL Adjustment",
            "**%s** received **+%s HZL**.\nBalance: %s → %s HZL\nReason: %s"
            % (member.display_name, format(amount, ","), format(before, ","), format(after, ","), reason)
        ))

    @commands.command(name="admin-remove")
    async def admin_remove(self, ctx: commands.Context, member: discord.Member, amount: int, *, reason: str = "manual adjustment") -> None:
        if not await self._owner(ctx):
            await ctx.send(view=simple_view("# Permission Denied", "This command is restricted to bot owners.", discord.Colour.red()))
            return
        if amount <= 0:
            await ctx.send(view=simple_view("# Invalid Amount", "Amount must be greater than zero.", discord.Colour.orange()))
            return
        await self.bot.economy.ensure_user(member.id, str(member), member.display_name)
        try:
            before, after = await self.bot.economy.change_balance(member.id, -amount, "admin_debit", "admin", str(ctx.author.id), {"reason": reason})
        except EconomyError:
            await ctx.send(view=simple_view("# Insufficient Balance", "The member does not have enough HZL.", discord.Colour.red()))
            return
        await self.bot.db.execute("INSERT INTO audit_logs(actor_id,action,target_id,details) VALUES(?,?,?,?)",
                                   (ctx.author.id, "economy.debit", str(member.id), reason))
        await ctx.send(view=simple_view(
            "# HZL Adjustment",
            "**%s** lost **%s HZL**.\nBalance: %s → %s HZL\nReason: %s"
            % (member.display_name, format(amount, ","), format(before, ","), format(after, ","), reason)
        ))


    @commands.command(name="admin-plan-cost")
    async def admin_plan_cost(self, ctx: commands.Context, plan_key: str, hzl_cost: int) -> None:
        if not await self._owner(ctx):
            await ctx.send(view=simple_view("# Permission Denied", "This command is restricted to bot owners.", discord.Colour.red()))
            return
        if hzl_cost < 0:
            await ctx.send(view=simple_view("# Invalid Cost", "HZL cost cannot be negative.", discord.Colour.orange()))
            return
        row = await self.bot.db.fetchone("SELECT plan_key FROM plans WHERE plan_key=?", (plan_key.upper(),))
        if not row:
            await ctx.send(view=simple_view("# Plan Not Found", "Unknown plan key.", discord.Colour.orange()))
            return
        await self.bot.db.execute("UPDATE plans SET hzl_cost=?,updated_at=CURRENT_TIMESTAMP WHERE plan_key=?",
                                  (hzl_cost, plan_key.upper()))
        await self.bot.db.execute("INSERT INTO audit_logs(actor_id,action,target_id,details) VALUES(?,?,?,?)",
                                  (ctx.author.id, "plan.cost.update", plan_key.upper(), str(hzl_cost)))
        await ctx.send(view=simple_view("# Plan Updated", "%s now costs **%s HZL** for redemption." %
                                         (plan_key.upper(), format(hzl_cost, ","))))

    @commands.command(name="admin-plan-set")
    async def admin_plan_set(self, ctx: commands.Context, plan_key: str, price_usd: float, hzl_cost: int, duration_days: int) -> None:
        if not await self._owner(ctx):
            await ctx.send(view=simple_view("# Permission Denied", "This command is restricted to bot owners.", discord.Colour.red()))
            return
        key = plan_key.upper()
        if price_usd < 0 or hzl_cost < 0 or duration_days < 1:
            await ctx.send(view=simple_view("# Invalid Values", "Price/cost must be non-negative and duration must be at least 1 day.", discord.Colour.orange()))
            return
        row = await self.bot.db.fetchone("SELECT id FROM plans WHERE plan_key=?", (key,))
        if not row:
            await ctx.send(view=simple_view("# Plan Not Found", "Unknown plan key.", discord.Colour.orange()))
            return
        await self.bot.db.execute(
            "UPDATE plans SET price_usd=?,hzl_cost=?,duration_days=?,updated_at=CURRENT_TIMESTAMP WHERE plan_key=?",
            (price_usd, hzl_cost, duration_days, key),
        )
        await self.bot.db.execute(
            "INSERT INTO audit_logs(actor_id,action,target_id,details) VALUES(?,?,?,?)",
            (ctx.author.id, "plan.update", key, "price_usd=%s,hzl_cost=%s,duration_days=%s" % (price_usd, hzl_cost, duration_days)),
        )
        await ctx.send(view=simple_view("# Plan Updated", "%s · $%.2f · %s HZL · %s days" % (key, price_usd, hzl_cost, duration_days)))

    @commands.command(name="admin-plan-target")
    async def admin_plan_target(self, ctx: commands.Context, plan_key: str, cluster: str, node: str = "") -> None:
        if not await self._owner(ctx):
            await ctx.send(view=simple_view("# Permission Denied", "This command is restricted to bot owners.", discord.Colour.red()))
            return
        key = plan_key.upper()
        row = await self.bot.db.fetchone("SELECT metadata FROM plans WHERE plan_key=?", (key,))
        if not row:
            await ctx.send(view=simple_view("# Plan Not Found", "Unknown plan key.", discord.Colour.orange()))
            return
        import json
        try:
            metadata = json.loads(row["metadata"] or "{}")
        except (TypeError, ValueError):
            metadata = {}
        metadata["cluster"] = cluster
        if node:
            metadata["node"] = node
        else:
            metadata.pop("node", None)
        await self.bot.db.execute(
            "UPDATE plans SET metadata=?,updated_at=CURRENT_TIMESTAMP WHERE plan_key=?",
            (json.dumps(metadata, separators=(",", ":")), key),
        )
        await self.bot.db.execute(
            "INSERT INTO audit_logs(actor_id,action,target_id,details) VALUES(?,?,?,?)",
            (ctx.author.id, "plan.target.update", key, "cluster=%s,node=%s" % (cluster, node or "auto")),
        )
        await ctx.send(view=simple_view("# Plan Target Updated", "%s → cluster **%s** · node **%s**" % (key, cluster, node or "automatic")))

    @commands.command(name="admin-plan-toggle")
    async def admin_plan_toggle(self, ctx: commands.Context, plan_key: str, enabled: int) -> None:
        if not await self._owner(ctx):
            await ctx.send(view=simple_view("# Permission Denied", "This command is restricted to bot owners.", discord.Colour.red()))
            return
        if enabled not in (0, 1):
            await ctx.send(view=simple_view("# Invalid Value", "Use 1 to enable or 0 to disable.", discord.Colour.orange()))
            return
        await self.bot.db.execute("UPDATE plans SET enabled=?,updated_at=CURRENT_TIMESTAMP WHERE plan_key=?",
                                  (enabled, plan_key.upper()))
        await ctx.send(view=simple_view("# Plan Status Updated", "%s is now %s." %
                                         (plan_key.upper(), "enabled" if enabled else "disabled")))

    @commands.command(name="admin-plan-provider")
    async def admin_plan_provider(self, ctx: commands.Context, plan_key: str, provider: str) -> None:
        if not await self._owner(ctx):
            await ctx.send(view=simple_view("# Permission Denied", "This command is restricted to bot owners.", discord.Colour.red()))
            return
        provider = provider.lower()
        if provider not in {"qemu", "lxc", "pterodactyl"}:
            await ctx.send(view=simple_view("# Invalid Provider", "Use qemu or lxc.", discord.Colour.orange()))
            return
        row = await self.bot.db.fetchone("SELECT metadata FROM plans WHERE plan_key=?", (plan_key.upper(),))
        if not row:
            await ctx.send(view=simple_view("# Plan Not Found", "Unknown plan key.", discord.Colour.orange()))
            return
        import json
        try:
            metadata = json.loads(row["metadata"] or "{}")
        except (TypeError, ValueError):
            metadata = {}
        metadata["provider"] = provider
        await self.bot.db.execute(
            "UPDATE plans SET metadata=?,updated_at=CURRENT_TIMESTAMP WHERE plan_key=?",
            (json.dumps(metadata, separators=(",", ":")), plan_key.upper()),
        )
        await ctx.send(view=simple_view("# Provider Updated", "%s now provisions using %s." % (plan_key.upper(), provider)))

    @commands.command(name="admin-node-add")
    async def admin_node_add(self, ctx: commands.Context, name: str, node_name: str, location: str, api_url: str) -> None:
        if not await self._owner(ctx):
            await ctx.send(view=simple_view("# Permission Denied", "This command is restricted to bot owners.", discord.Colour.red()))
            return
        await self.bot.db.execute(
            """INSERT INTO proxmox_nodes(name,node_name,location,api_url)
               VALUES(?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET node_name=excluded.node_name,
               location=excluded.location,api_url=excluded.api_url,updated_at=CURRENT_TIMESTAMP""",
            (name, node_name, location, api_url),
        )
        await ctx.send(view=simple_view("# Proxmox Node Saved", "%s · %s · %s" % (name, node_name, location)))

    @commands.command(name="admin-node-toggle")
    async def admin_node_toggle(self, ctx: commands.Context, name: str, enabled: int) -> None:
        if not await self._owner(ctx):
            await ctx.send(view=simple_view("# Permission Denied", "This command is restricted to bot owners.", discord.Colour.red()))
            return
        if enabled not in (0, 1):
            await ctx.send(view=simple_view("# Invalid Value", "Use 1 to enable or 0 to disable.", discord.Colour.orange()))
            return
        await self.bot.db.execute("UPDATE proxmox_nodes SET enabled=? WHERE name=?", (enabled, name))
        await ctx.send(view=simple_view("# Node Status", "%s is now %s." % (name, "enabled" if enabled else "disabled")))

    @commands.command(name="admin-node-health")
    async def admin_node_health(self, ctx: commands.Context) -> None:
        if not await self._owner(ctx):
            await ctx.send(view=simple_view("# Permission Denied", "This command is restricted to bot owners.", discord.Colour.red()))
            return

        from proxmox.client import ProxmoxClient, ProxmoxConfig, client_from_settings

        targets = []
        rows = await self.bot.db.fetchall(
            "SELECT name,node_name,location,enabled,api_url,verify_ssl,token_id,token_secret FROM proxmox_nodes WHERE enabled=1 ORDER BY location,name"
        )
        clusters = getattr(self.bot.settings, "proxmox_clusters", {}) or {}
        for row in rows:
            cluster_name = str(row["name"])
            client = None
            if cluster_name in clusters:
                client = client_from_settings(self.bot.settings, cluster_name)
            else:
                matched = next(
                    (
                        cfg for cfg in clusters.values()
                        if str(cfg.get("api_url") or "").rstrip("/") == str(row["api_url"] or "").rstrip("/")
                        or str(cfg.get("node_name") or cfg.get("node") or "") == str(row["node_name"] or "")
                    ),
                    None,
                )
                if matched and all(matched.get(k) for k in ("api_url", "token_id", "token_secret")):
                    client = ProxmoxClient(ProxmoxConfig(
                        base_url=str(matched["api_url"]),
                        token_id=str(matched["token_id"]),
                        token_secret=str(matched["token_secret"]),
                        verify_ssl=bool(matched.get("verify_ssl", self.bot.settings.proxmox_verify_ssl)),
                    ))
            if client is None and row["token_id"] and row["token_secret"]:
                client = ProxmoxClient(ProxmoxConfig(
                    base_url=row["api_url"],
                    token_id=row["token_id"],
                    token_secret=row["token_secret"],
                    verify_ssl=bool(row["verify_ssl"]),
                ))
            elif row["api_url"] and self.bot.settings.proxmox_token_id and self.bot.settings.proxmox_token_secret:
                client = ProxmoxClient(ProxmoxConfig(
                    base_url=row["api_url"],
                    token_id=self.bot.settings.proxmox_token_id,
                    token_secret=self.bot.settings.proxmox_token_secret,
                    verify_ssl=bool(row["verify_ssl"]) if row["verify_ssl"] is not None else self.bot.settings.proxmox_verify_ssl,
                ))
            else:
                client = client_from_settings(self.bot.settings, cluster_name)

            targets.append({
                "name": cluster_name,
                "node": row["node_name"],
                "location": row["location"],
                "client": client,
            })

        if not targets:
            for name, cfg in clusters.items():
                targets.append({
                    "name": str(name),
                    "node": cfg.get("node_name") or cfg.get("node") or self.bot.settings.proxmox_default_node,
                    "location": str(cfg.get("location") or "configured cluster"),
                    "client": client_from_settings(self.bot.settings, str(name)),
                })
            if not targets and self.bot.settings.proxmox_api_url:
                targets.append({
                    "name": "default",
                    "node": self.bot.settings.proxmox_default_node,
                    "location": "default cluster",
                    "client": client_from_settings(self.bot.settings),
                })

        if not targets:
            await ctx.send(view=simple_view(
                "# Proxmox Node Health",
                "No Proxmox connection is configured. Configure `PROXMOX_API_URL` + token credentials or `PROXMOX_CLUSTERS_JSON` first.",
                discord.Colour.orange(),
            ))
            return

        lines = []
        for target in targets:
            client = target["client"]
            if not client:
                lines.append("• **%s** — client credentials not configured" % target["name"])
                continue
            try:
                node_name = target["node"]
                if not node_name:
                    nodes = await client.nodes()
                    online = [n for n in nodes if n.get("status") == "online"]
                    if not online:
                        lines.append("• **%s** — no online node detected" % target["name"])
                        continue
                    node_name = online[0]["node"]
                status = await client.node_status(str(node_name))
                memory = status.get("memory", {}) or {}
                total = float(memory.get("total", 0))
                used = float(memory.get("used", 0))
                free_mb = int(max(0, total - used) / 1048576)
                total_mb = int(total / 1048576)
                cpu_pct = float(status.get("cpu", 0)) * 100
                lines.append("• **%s** · `%s` · **ONLINE**\n  Location: `%s` · CPU: `%.1f%%` · RAM: `%s / %s MB free/total`" % (target["name"], node_name, target["location"], cpu_pct, free_mb, total_mb))
                db_node = await self.bot.db.fetchone("SELECT id FROM proxmox_nodes WHERE name=? LIMIT 1", (target["name"],))
                if db_node:
                    await self.bot.db.execute(
                        "INSERT INTO node_health(node_id,status,free_memory_mb,total_memory_mb,cpu_load,last_checked_at,error) VALUES(?,?,?,?,?,CURRENT_TIMESTAMP,NULL) ON CONFLICT(node_id) DO UPDATE SET status='online',free_memory_mb=excluded.free_memory_mb,total_memory_mb=excluded.total_memory_mb,cpu_load=excluded.cpu_load,last_checked_at=CURRENT_TIMESTAMP,error=NULL",
                        (int(db_node["id"]), free_mb, total_mb, float(status.get("cpu", 0))),
                    )
            except Exception as exc:
                lines.append("• **%s** — **ERROR**: `%s`" % (target["name"], str(exc)[:180]))

        await ctx.send(view=simple_view("# Proxmox Node Health", "\n".join(lines)))

    @commands.command(name="admin-nodes")
    async def admin_nodes(self, ctx: commands.Context) -> None:
        if not await self._owner(ctx):
            await ctx.send(view=simple_view("# Permission Denied", "This command is restricted to bot owners.", discord.Colour.red()))
            return
        rows = await self.bot.db.fetchall("SELECT name,node_name,location,api_url,enabled FROM proxmox_nodes ORDER BY location,name")
        body = "\n".join("• **%s** · %s · %s · %s" % (r["name"],r["node_name"],r["location"],"enabled" if r["enabled"] else "disabled") for r in rows) or "No nodes configured."
        await ctx.send(view=simple_view("# Proxmox Nodes", body))



async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EconomyCog(bot))
    await bot.add_cog(HostingCog(bot))
    await bot.add_cog(AdminCog(bot))
