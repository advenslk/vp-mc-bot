from __future__ import annotations

import secrets
from dataclasses import dataclass

from core.database import Database
from economy.service import EconomyError, EconomyService


@dataclass(frozen=True)
class RedemptionResult:
    redemption_id: int
    status: str
    message: str


class HostingService:
    def __init__(self, db: Database, economy: EconomyService):
        self.db = db
        self.economy = economy

    async def get_plans(self, kind: str):
        return await self.db.fetchall(
            """SELECT * FROM plans WHERE kind=? AND enabled=1 ORDER BY ram_mb ASC""",
            (kind,),
        )

    async def redeem(self, user_id: int, plan_key: str) -> RedemptionResult:
        async with self.db.transaction() as db:
            plan = await (await db.execute(
                "SELECT * FROM plans WHERE plan_key=? AND enabled=1", (plan_key.upper(),)
            )).fetchone()
            if not plan:
                raise ValueError("Plan not found or disabled.")
            cost = int(plan["hzl_cost"])
            if cost <= 0:
                raise ValueError("This plan is not configured for HZL redemption yet.")

            wallet = await (await db.execute(
                "SELECT balance FROM wallets WHERE user_id=?", (user_id,)
            )).fetchone()
            if not wallet or int(wallet["balance"]) < cost:
                raise EconomyError("Insufficient HZL balance.")

            # Reserve the redemption and debit atomically. The provisioning worker
            # can refund it if the provider fails.
            before = int(wallet["balance"])
            after = before - cost
            await db.execute(
                "UPDATE wallets SET balance=?, lifetime_spent=lifetime_spent+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                (after, cost, user_id),
            )
            cur = await db.execute(
                """INSERT INTO redemptions(user_id,plan_id,cost,status)
                   VALUES(?,?,?,?)""",
                (user_id, plan["id"], cost, "pending"),
            )
            redemption_id = cur.lastrowid
            await db.execute(
                """INSERT INTO transactions
                   (user_id,amount,balance_before,balance_after,transaction_type,source,reference_id,metadata)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (user_id, -cost, before, after, "debit", "hosting_redemption",
                 str(redemption_id), '{"status":"pending"}'),
            )
            return RedemptionResult(
                redemption_id=redemption_id or 0,
                status="pending",
                message="Redemption reserved. Provisioning can now be started safely.",
            )

    async def fail_and_refund(self, redemption_id: int, reason: str) -> None:
        async with self.db.transaction() as db:
            row = await (await db.execute(
                "SELECT user_id,cost,status FROM redemptions WHERE id=?", (redemption_id,)
            )).fetchone()
            if not row or row["status"] not in {"pending", "provisioning"}:
                return
            user_id, cost = int(row["user_id"]), int(row["cost"])
            wallet = await (await db.execute(
                "SELECT balance FROM wallets WHERE user_id=?", (user_id,)
            )).fetchone()
            before = int(wallet["balance"])
            after = before + cost
            await db.execute(
                "UPDATE wallets SET balance=?, lifetime_spent=MAX(0, lifetime_spent-?), updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                (after, cost, user_id),
            )
            await db.execute(
                "UPDATE redemptions SET status='refunded',failure_reason=?,completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (reason[:500], redemption_id),
            )
            await db.execute(
                """INSERT INTO transactions
                   (user_id,amount,balance_before,balance_after,transaction_type,source,reference_id,metadata)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (user_id, cost, before, after, "refund", "hosting_redemption",
                 str(redemption_id), '{"status":"refunded"}'),
            )

    async def complete(self, redemption_id: int, provider_resource_id: str) -> None:
        await self.db.execute(
            """UPDATE redemptions SET status='completed',provider_resource_id=?,
               completed_at=CURRENT_TIMESTAMP WHERE id=? AND status IN ('pending','provisioning')""",
            (provider_resource_id, redemption_id),
        )
