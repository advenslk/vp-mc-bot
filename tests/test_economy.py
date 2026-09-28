import asyncio
from pathlib import Path

from core.database import Database
from economy.service import EconomyService


def test_wallet_transaction(tmp_path: Path):
    async def run():
        db = Database(str(tmp_path / "test.db"))
        await db.initialize()
        economy = EconomyService(db)
        await economy.ensure_user(1, "tester", "Tester")
        before, after = await economy.change_balance(1, 100, "credit", "test")
        assert before == 0
        assert after == 100
        assert await economy.balance(1) == 100
        before, after = await economy.change_balance(1, -40, "debit", "test")
        assert before == 100
        assert after == 60

    asyncio.run(run())
