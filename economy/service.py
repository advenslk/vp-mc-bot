from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from core.database import Database


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EconomyError(Exception):
    pass


class EconomyService:
    def __init__(self, db: Database):
        self.db = db

    async def ensure_user(self, user_id: int, username: str, display_name: str) -> None:
        async with self.db.transaction() as conn:
            await conn.execute(
                """INSERT INTO users(user_id, username, display_name)
                   VALUES(?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
                   display_name=excluded.display_name, updated_at=CURRENT_TIMESTAMP""",
                (user_id, username, display_name),
            )
            await conn.execute(
                "INSERT INTO wallets(user_id) VALUES(?) ON CONFLICT(user_id) DO NOTHING",
                (user_id,),
            )

    async def balance(self, user_id: int) -> int:
        row = await self.db.fetchone("SELECT balance FROM wallets WHERE user_id=?", (user_id,))
        return int(row["balance"]) if row else 0

    async def change_balance(
        self, user_id: int, amount: int, transaction_type: str, source: str,
        reference_id: str | None = None, metadata: dict[str, Any] | None = None
    ) -> tuple[int, int]:
        if amount == 0:
            value = await self.balance(user_id)
            return value, value
        async with self.db.transaction() as conn:
            row = await (await conn.execute(
                "SELECT balance FROM wallets WHERE user_id=?", (user_id,)
            )).fetchone()
            if row is None:
                raise EconomyError("Wallet does not exist.")
            before = int(row["balance"])
            after = before + amount
            if after < 0:
                raise EconomyError("Insufficient HZL balance.")
            await conn.execute(
                """UPDATE wallets SET balance=?,
                   lifetime_earned=lifetime_earned+CASE WHEN ? > 0 THEN ? ELSE 0 END,
                   lifetime_spent=lifetime_spent+CASE WHEN ? < 0 THEN ? ELSE 0 END,
                   updated_at=CURRENT_TIMESTAMP WHERE user_id=?""",
                (after, amount, amount, amount, abs(amount), user_id),
            )
            await conn.execute(
                """INSERT INTO transactions
                   (user_id,amount,balance_before,balance_after,transaction_type,source,reference_id,metadata)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (user_id, amount, before, after, transaction_type, source,
                 reference_id, json.dumps(metadata or {}, separators=(",", ":"))),
            )
            return before, after

    async def claim_daily(self, user_id: int, amount: int) -> tuple[bool, int]:
        now = utcnow()
        async with self.db.transaction() as conn:
            row = await (await conn.execute(
                "SELECT last_claimed_at FROM daily_claims WHERE user_id=?", (user_id,)
            )).fetchone()
            if row and row["last_claimed_at"]:
                last = datetime.fromisoformat(row["last_claimed_at"])
                remaining = int((last + timedelta(hours=24) - now).total_seconds())
                if remaining > 0:
                    return False, remaining
            wallet = await (await conn.execute(
                "SELECT balance FROM wallets WHERE user_id=?", (user_id,)
            )).fetchone()
            before = int(wallet["balance"])
            after = before + amount
            await conn.execute(
                """UPDATE wallets SET balance=?, lifetime_earned=lifetime_earned+?,
                   updated_at=CURRENT_TIMESTAMP WHERE user_id=?""",
                (after, amount, user_id),
            )
            await conn.execute(
                """INSERT INTO daily_claims(user_id,last_claimed_at) VALUES(?,?)
                   ON CONFLICT(user_id) DO UPDATE SET last_claimed_at=excluded.last_claimed_at""",
                (user_id, now.isoformat()),
            )
            await conn.execute(
                """INSERT INTO transactions(user_id,amount,balance_before,balance_after,transaction_type,source)
                   VALUES(?,?,?,?,?,?)""",
                (user_id, amount, before, after, "credit", "daily"),
            )
            return True, amount

    async def claim_cooldown_reward(
        self, user_id: int, reward_key: str, amount: int, cooldown_seconds: int, source: str
    ) -> tuple[bool, int]:
        now = utcnow()
        async with self.db.transaction() as conn:
            row = await (await conn.execute(
                "SELECT last_rewarded_at FROM reward_cooldowns WHERE user_id=? AND reward_key=?",
                (user_id, reward_key),
            )).fetchone()
            if row:
                last = datetime.fromisoformat(row["last_rewarded_at"])
                remaining = cooldown_seconds - int((now - last).total_seconds())
                if remaining > 0:
                    return False, remaining
            wallet = await (await conn.execute(
                "SELECT balance FROM wallets WHERE user_id=?", (user_id,)
            )).fetchone()
            before = int(wallet["balance"])
            after = before + amount
            await conn.execute(
                "UPDATE wallets SET balance=?, lifetime_earned=lifetime_earned+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                (after, amount, user_id),
            )
            await conn.execute(
                """INSERT INTO reward_cooldowns(user_id,reward_key,last_rewarded_at) VALUES(?,?,?)
                   ON CONFLICT(user_id,reward_key) DO UPDATE SET last_rewarded_at=excluded.last_rewarded_at""",
                (user_id, reward_key, now.isoformat()),
            )
            await conn.execute(
                """INSERT INTO transactions(user_id,amount,balance_before,balance_after,transaction_type,source)
                   VALUES(?,?,?,?,?,?)""",
                (user_id, amount, before, after, "credit", source),
            )
            return True, amount

    async def leaderboard(self, limit: int = 10) -> list[Any]:
        return await self.db.fetchall(
            """SELECT u.user_id,u.display_name,w.balance,w.lifetime_earned
               FROM wallets w JOIN users u ON u.user_id=w.user_id
               ORDER BY w.balance DESC LIMIT ?""",
            (max(1, min(limit, 50)),),
        )

    async def transactions(self, user_id: int, limit: int = 10) -> list[Any]:
        return await self.db.fetchall(
            """SELECT amount,balance_before,balance_after,transaction_type,source,created_at
               FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT ?""",
            (user_id, max(1, min(limit, 50))),
        )

    async def invite_count(self, guild_id: int, user_id: int) -> int:
        row = await self.db.fetchone(
            "SELECT COUNT(*) AS count FROM invites WHERE guild_id=? AND inviter_id=? AND verified=1",
            (guild_id, user_id),
        )
        return int(row["count"]) if row else 0

    async def record_invite(self, guild_id: int, inviter_id: int, invitee_id: int, code: str | None) -> bool:
        if inviter_id == invitee_id:
            return False
        async with self.db.transaction() as conn:
            cur = await conn.execute(
                """INSERT OR IGNORE INTO invites(guild_id,inviter_id,invitee_id,code,verified)
                   VALUES(?,?,?,?,1)""",
                (guild_id, inviter_id, invitee_id, code),
            )
            return cur.rowcount > 0

    async def recent_summary(self, user_id: int) -> str:
        rows = await self.transactions(user_id, 5)
        if not rows:
            return "No transactions yet."
        return "\n".join(
            f"{'+' if row['amount'] >= 0 else ''}{row['amount']} HZL • {row['source']}"
            for row in rows
        )
