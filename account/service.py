from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from core.database import Database


class AccountError(Exception):
    pass


class AccountService:
    """Secure account primitives. Email delivery is intentionally external."""

    def __init__(self, db: Database):
        self.db = db
        self.hasher = PasswordHasher()

    def hash_password(self, password: str) -> str:
        if len(password) < 10:
            raise AccountError("Password must contain at least 10 characters.")
        return self.hasher.hash(password)

    def verify_password(self, password_hash: str, password: str) -> bool:
        try:
            return self.hasher.verify(password_hash, password)
        except VerifyMismatchError:
            return False

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def register(self, user_id: int, email: str, password: str) -> str:
        email = email.strip().lower()
        if "@" not in email or len(email) > 254:
            raise AccountError("Invalid email address.")
        password_hash = self.hash_password(password)
        raw_token = secrets.token_urlsafe(32)
        token_hash = self.token_hash(raw_token)
        expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        async with self.db.transaction() as db:
            if await (await db.execute("SELECT id FROM accounts WHERE user_id=?", (user_id,))).fetchone():
                raise AccountError("A HelzerX account is already registered for this Discord user.")
            if await (await db.execute("SELECT id FROM accounts WHERE email=?", (email,))).fetchone():
                raise AccountError("That email address is already registered.")
            cur = await db.execute(
                "INSERT INTO accounts(user_id,email,password_hash) VALUES(?,?,?)",
                (user_id, email, password_hash),
            )
            await db.execute(
                "INSERT INTO account_tokens(account_id,token_hash,token_type,expires_at) VALUES(?,?,?,?)",
                (int(cur.lastrowid), token_hash, "email_verification", expires),
            )
        return raw_token

    async def verify_email(self, raw_token: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as db:
            row = await (await db.execute(
                "SELECT id,account_id FROM account_tokens WHERE token_hash=? AND token_type='email_verification' "
                "AND used_at IS NULL AND expires_at>?",
                (self.token_hash(raw_token), now),
            )).fetchone()
            if not row:
                return False
            await db.execute("UPDATE accounts SET email_verified=1,updated_at=CURRENT_TIMESTAMP WHERE id=?", (row["account_id"],))
            await db.execute("UPDATE account_tokens SET used_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))
            return True

    async def authenticate(self, email: str, password: str) -> int:
        row = await self.db.fetchone(
            "SELECT id,user_id,password_hash,email_verified,locked FROM accounts WHERE email=?",
            (email.strip().lower(),),
        )
        if not row or int(row["locked"]) or not int(row["email_verified"]):
            raise AccountError("Invalid credentials or account not verified.")
        if not self.verify_password(row["password_hash"], password):
            raise AccountError("Invalid credentials.")
        return int(row["user_id"])
