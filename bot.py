from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from config.settings import load_settings
from core.database import Database
from account.service import AccountService
from economy.service import EconomyService
from hosting.service import HostingService
from hosting.provisioner import ProvisioningService
from hosting.lifecycle import LifecycleService


class HelzerXBot(commands.Bot):
    def __init__(self):
        self.settings = load_settings()
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True
        intents.voice_states = True
        super().__init__(
            command_prefix=self.settings.prefix,
            intents=intents,
            help_command=None,
            case_insensitive=True,
            strip_after_prefix=True,
        )
        self.db = Database(self.settings.database_path)
        self.economy = EconomyService(self.db)
        self.hosting = HostingService(self.db, self.economy)
        self.accounts = AccountService(self.db)
        self.provisioner = ProvisioningService(self)
        self.lifecycle = LifecycleService(self)
        self.invite_cache: dict[int, dict[str, int]] = {}
        self.voice_started: dict[int, datetime] = {}
        self.logger = logging.getLogger("helzerx")
        self.activity_reward_lock = asyncio.Lock()

    async def setup_hook(self) -> None:
        await self.db.initialize()
        await self.seed_defaults()
        await self.load_extension("commands")
        await self.load_extension("hosting_commands")
        await self.load_extension("community_commands")
        await self.load_extension("vps_commands")
        await self.load_extension("account_commands")
        self.voice_rewards.start()
        self.provisioning_loop.change_interval(seconds=self.settings.provisioning_interval)
        self.provisioning_loop.start()
        self.lifecycle_loop.start()

    async def seed_defaults(self) -> None:
        plans = [
            ("minecraft", "HXC-S02", "HXC-S02", 2048, 100, 20, 0.69, 0, "Singapore"),
            ("minecraft", "HXC-S04", "HXC-S04", 4096, 200, 40, 1.19, 0, "Singapore"),
            ("minecraft", "HXC-S06", "HXC-S06", 6144, 200, 50, 1.59, 0, "Singapore"),
            ("minecraft", "HXC-S08", "HXC-S08", 8192, 300, 80, 2.19, 0, "Singapore"),
            ("minecraft", "HXC-S12", "HXC-S12", 12288, 400, 120, 3.19, 0, "Singapore"),
            ("minecraft", "HXC-S16", "HXC-S16", 16384, 500, 160, 4.19, 0, "Singapore"),
            ("minecraft", "HXC-S24", "HXC-S24", 24576, 600, 240, 5.99, 0, "Singapore"),
            ("minecraft", "HXC-S32", "HXC-S32", 32768, 800, 320, 7.99, 0, "Singapore"),
            ("minecraft", "HXC-S48", "HXC-S48", 49152, 1000, 480, 11.99, 0, "Singapore"),
            ("minecraft", "HXC-S64", "HXC-S64", 65536, 1200, 640, 14.99, 0, "Singapore"),
            ("vps", "HXC-V02", "HXC-V02", 2048, 2, 30, 2.29, 0, "Singapore"),
            ("vps", "HXC-V04", "HXC-V04", 4096, 2, 60, 3.49, 0, "Singapore"),
            ("vps", "HXC-V06", "HXC-V06", 6144, 3, 90, 4.69, 0, "Singapore"),
            ("vps", "HXC-V08", "HXC-V08", 8192, 4, 120, 5.69, 0, "Singapore"),
            ("vps", "HXC-V12", "HXC-V12", 12288, 4, 160, 7.99, 0, "Singapore"),
            ("vps", "HXC-V16", "HXC-V16", 16384, 6, 220, 9.99, 0, "Singapore"),
            ("vps", "HXC-V24", "HXC-V24", 24576, 8, 320, 13.49, 0, "Singapore"),
            ("vps", "HXC-V32", "HXC-V32", 32768, 10, 400, 15.49, 0, "Singapore"),
            ("vps", "HXC-V48", "HXC-V48", 49152, 12, 600, 17.99, 0, "Singapore"),
            ("vps", "HXC-V64", "HXC-V64", 65536, 16, 800, 21.99, 0, "Singapore"),
        ]
        async with self.db.transaction() as db:
            for p in plans:
                await db.execute(
                    """INSERT INTO plans(kind,plan_key,name,ram_mb,cpu_units,storage_gb,price_usd,hzl_cost,location)
                       VALUES(?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(plan_key) DO UPDATE SET name=excluded.name,
                       ram_mb=excluded.ram_mb,cpu_units=excluded.cpu_units,storage_gb=excluded.storage_gb,
                       price_usd=excluded.price_usd,location=excluded.location,updated_at=CURRENT_TIMESTAMP""",
                    p,
                )
            await db.execute(
                "UPDATE plans SET metadata=? WHERE kind='minecraft' AND (metadata='{}' OR metadata IS NULL)",
                ('{"provider":"pterodactyl"}',),
            )
            achievements = [
                ("first_profile", "First Profile", "Open your HelzerX profile.", 25),
                ("first_daily", "Daily Start", "Claim your first daily reward.", 25),
                ("first_invite", "Community Builder", "Bring your first verified member.", 100),
                ("first_1000", "HZL Collector", "Reach 1,000 lifetime earned HZL.", 100),
            ]
            for a in achievements:
                await db.execute(
                    "INSERT OR IGNORE INTO achievements(achievement_key,name,description,reward) VALUES(?,?,?,?)",
                    a,
                )
            milestones = [
                (2, 200), (4, 600), (8, 900), (12, 1300), (16, 1700),
                (24, 2400), (28, 2900), (34, 3400), (38, 4000), (42, 4500),
            ]
            for milestone, reward in milestones:
                await db.execute(
                    "INSERT INTO invite_milestones(milestone,reward) VALUES(?,?) "
                    "ON CONFLICT(milestone) DO UPDATE SET reward=excluded.reward",
                    (milestone, reward),
                )

            reward_rules = [
                ("message", "Message Activity", 2, 60, 100),
                ("voice_10m", "Voice Activity", 10, 600, 120),
                ("daily", "Daily Check-in", 100, 86400, 1),
            ]
            for key, name, amount, cooldown, daily_limit in reward_rules:
                await db.execute(
                    """INSERT INTO reward_rules(reward_key,name,amount,cooldown_seconds,daily_limit,description)
                       VALUES(?,?,?,?,?,?)
                       ON CONFLICT(reward_key) DO UPDATE SET name=excluded.name,
                       amount=excluded.amount,cooldown_seconds=excluded.cooldown_seconds,
                       daily_limit=excluded.daily_limit,description=excluded.description""",
                    (key, name, amount, cooldown, daily_limit, "Configurable HelzerX community reward."),
                )
            quests = [
                ("daily_messages", "Daily Messages", "Send 10 eligible community messages.", 10, 50, "daily"),
                ("daily_voice", "Daily Voice", "Participate in eligible voice activity 6 times.", 6, 75, "daily"),
                ("weekly_invites", "Weekly Builder", "Earn 3 verified invites.", 3, 250, "weekly"),
            ]
            for q in quests:
                await db.execute(
                    """INSERT INTO quests(quest_key,name,description,target,reward,period)
                       VALUES(?,?,?,?,?,?)
                       ON CONFLICT(quest_key) DO UPDATE SET name=excluded.name,
                       description=excluded.description,target=excluded.target,reward=excluded.reward,
                       period=excluded.period""",
                    q,
                )

    async def on_ready(self) -> None:
        assert self.user is not None
        self.logger.info("Logged in as %s (%s)", self.user, self.user.id)
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Game(name="HelzerX Cloud • Infrastructure Built For Everyone"),
        )
        for guild in self.guilds:
            await self.refresh_invites(guild)

    async def refresh_invites(self, guild: discord.Guild) -> None:
        try:
            invites = await guild.invites()
            self.invite_cache[guild.id] = {invite.code: invite.uses or 0 for invite in invites}
        except (discord.Forbidden, discord.HTTPException):
            self.logger.warning("Cannot read invites in %s; Manage Server permission may be missing.", guild.id)

    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        await self.economy.ensure_user(member.id, str(member), member.display_name)
        before = self.invite_cache.get(member.guild.id, {})
        try:
            invites = await member.guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            return
        used = next((i for i in invites if (i.uses or 0) > before.get(i.code, 0)), None)
        self.invite_cache[member.guild.id] = {i.code: i.uses or 0 for i in invites}
        if not used or not used.inviter:
            return
        inviter = used.inviter
        if inviter.bot or inviter.id == member.id:
            return
        await self.economy.ensure_user(inviter.id, str(inviter), getattr(inviter, "display_name", str(inviter)))
        created = await self.economy.record_invite(member.guild.id, inviter.id, member.id, used.code)
        if not created:
            return
        count = await self.economy.invite_count(member.guild.id, inviter.id)
        milestone = await self.db.fetchone(
            "SELECT milestone,reward FROM invite_milestones WHERE milestone=? AND enabled=1",
            (count,),
        )
        await self.economy.update_quest(inviter.id, "weekly_invites", 1)
        await self.economy.unlock_achievement(inviter.id, "first_invite")
        if milestone:
            await self.economy.change_balance(
                inviter.id, int(milestone["reward"]), "invite_reward", "verified_invite",
                str(member.id), {"invitee": member.id, "code": used.code, "milestone": count},
            )

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        await self.economy.ensure_user(message.author.id, str(message.author), message.author.display_name)
        if len(message.content.strip()) >= 4:
            rewarded, _ = await self.economy.claim_cooldown_reward(
                message.author.id, "message", self.settings.message_reward,
                self.settings.message_reward_cooldown, "message_activity",
            )
            await self.economy.update_quest(message.author.id, "daily_messages", 1)
            if await self.economy.balance(message.author.id) >= 1000:
                await self.economy.unlock_achievement(message.author.id, "first_1000")
        await self.process_commands(message)

    @tasks.loop(minutes=1)
    async def lifecycle_loop(self) -> None:
        try:
            await self.lifecycle.expire_due()
        except Exception:
            self.logger.exception("Lifecycle loop error")

    @lifecycle_loop.before_loop
    async def before_lifecycle_loop(self) -> None:
        await self.wait_until_ready()

    @tasks.loop(seconds=20)
    async def provisioning_loop(self) -> None:
        try:
            await self.provisioner.run_once()
        except Exception:
            self.logger.exception("Provisioning loop error")

    @provisioning_loop.before_loop
    async def before_provisioning_loop(self) -> None:
        await self.wait_until_ready()

    @tasks.loop(minutes=10)
    async def voice_rewards(self) -> None:
        for guild in self.guilds:
            for channel in guild.voice_channels:
                if guild.afk_channel and channel.id == guild.afk_channel.id:
                    continue
                members = [m for m in channel.members if not m.bot]
                if len(members) < self.settings.voice_min_members:
                    continue
                for member in members:
                    await self.economy.ensure_user(member.id, str(member), member.display_name)
                    rewarded, _ = await self.economy.claim_cooldown_reward(
                        member.id, "voice_10m", self.settings.voice_reward_per_10_min,
                        600, "voice_activity",
                    )
                    if rewarded:
                        await self.economy.update_quest(member.id, "daily_voice", 1)

    @voice_rewards.before_loop
    async def before_voice_rewards(self) -> None:
        await self.wait_until_ready()

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Missing argument. Use %shelp for command usage." % self.settings.prefix)
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send("Invalid argument. Please check the command format.")
            return
        self.logger.exception("Command error", exc_info=error)
        await ctx.send("Something went wrong while processing that command.")


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, load_settings().log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    bot = HelzerXBot()
    bot.run(bot.settings.token, log_handler=None)


if __name__ == "__main__":
    main()
