from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wallets (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    balance INTEGER NOT NULL DEFAULT 0 CHECK(balance >= 0),
    lifetime_earned INTEGER NOT NULL DEFAULT 0 CHECK(lifetime_earned >= 0),
    lifetime_spent INTEGER NOT NULL DEFAULT 0 CHECK(lifetime_spent >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    amount INTEGER NOT NULL,
    balance_before INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    transaction_type TEXT NOT NULL,
    source TEXT NOT NULL,
    reference_id TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_created ON transactions(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS daily_claims (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    last_claimed_at TEXT
);

CREATE TABLE IF NOT EXISTS reward_cooldowns (
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    reward_key TEXT NOT NULL,
    last_rewarded_at TEXT NOT NULL,
    PRIMARY KEY(user_id, reward_key)
);

CREATE TABLE IF NOT EXISTS invites (
    guild_id INTEGER NOT NULL,
    inviter_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    invitee_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    code TEXT,
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified INTEGER NOT NULL DEFAULT 0,
    rewarded INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(guild_id, invitee_id)
);

CREATE INDEX IF NOT EXISTS idx_invites_inviter ON invites(guild_id, inviter_id);

CREATE TABLE IF NOT EXISTS invite_milestones (
    milestone INTEGER PRIMARY KEY,
    reward INTEGER NOT NULL CHECK(reward >= 0),
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS reward_rules (
    reward_key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK(amount >= 0),
    cooldown_seconds INTEGER NOT NULL DEFAULT 0,
    daily_limit INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS quests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quest_key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    target INTEGER NOT NULL CHECK(target > 0),
    reward INTEGER NOT NULL CHECK(reward >= 0),
    period TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS quest_progress (
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    quest_id INTEGER NOT NULL REFERENCES quests(id) ON DELETE CASCADE,
    period_key TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    rewarded INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(user_id, quest_id, period_key)
);

CREATE TABLE IF NOT EXISTS achievements (
    achievement_key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    reward INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_achievements (
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    achievement_key TEXT NOT NULL REFERENCES achievements(achievement_key) ON DELETE CASCADE,
    unlocked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id, achievement_key)
);

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK(kind IN ('minecraft', 'vps')),
    plan_key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    ram_mb INTEGER NOT NULL,
    cpu_units INTEGER NOT NULL,
    storage_gb INTEGER NOT NULL,
    price_usd REAL NOT NULL DEFAULT 0,
    hzl_cost INTEGER NOT NULL DEFAULT 0,
    location TEXT NOT NULL,
    duration_days INTEGER NOT NULL DEFAULT 30,
    enabled INTEGER NOT NULL DEFAULT 1,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_plans_kind_enabled ON plans(kind, enabled);

CREATE TABLE IF NOT EXISTS redemptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    plan_id INTEGER NOT NULL REFERENCES plans(id),
    cost INTEGER NOT NULL,
    status TEXT NOT NULL,
    provider_resource_id TEXT,
    failure_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    action TEXT NOT NULL,
    target_id TEXT,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS proxmox_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    api_url TEXT NOT NULL,
    node_name TEXT NOT NULL,
    location TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    verify_ssl INTEGER NOT NULL DEFAULT 0,
    token_id TEXT,
    token_secret TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vps_servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    plan_id INTEGER NOT NULL REFERENCES plans(id),
    node_id INTEGER REFERENCES proxmox_nodes(id),
    vmid INTEGER,
    hostname TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'vps' CHECK(kind IN ('vps','minecraft')),
    status TEXT NOT NULL DEFAULT 'provisioning',
    ipv4 TEXT,
    ipv6 TEXT,
    username TEXT,
    os TEXT,
    expires_at TEXT,
    provider_id TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vps_user_status ON vps_servers(user_id, status);
CREATE INDEX IF NOT EXISTS idx_vps_node ON vps_servers(node_id);

CREATE TABLE IF NOT EXISTS provisioning_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    redemption_id INTEGER NOT NULL REFERENCES redemptions(id) ON DELETE CASCADE,
    server_id INTEGER REFERENCES vps_servers(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    attempts INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT UNIQUE NOT NULL,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_provisioning_status ON provisioning_jobs(status);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 0,
    locked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS account_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    token_hash TEXT UNIQUE NOT NULL,
    token_type TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_account_tokens_hash ON account_tokens(token_hash);

CREATE TABLE IF NOT EXISTS reward_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    reward_key TEXT NOT NULL,
    amount INTEGER NOT NULL,
    reference_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_reward_claims_user_key_date ON reward_claims(user_id,reward_key,created_at);

CREATE TABLE IF NOT EXISTS node_health (
    node_id INTEGER PRIMARY KEY REFERENCES proxmox_nodes(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'unknown',
    free_memory_mb INTEGER,
    total_memory_mb INTEGER,
    cpu_load REAL,
    last_checked_at TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS server_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL REFERENCES vps_servers(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_server_events_server ON server_events(server_id,created_at DESC);

CREATE TABLE IF NOT EXISTS discord_links (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    linked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, path: str):
        self.path = Path(path)
        self._write_lock = asyncio.Lock()

    async def connect(self) -> aiosqlite.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        return db

    async def initialize(self) -> None:
        async with self.connect() as db:
            await db.executescript(SCHEMA)
            await db.commit()

    @asynccontextmanager
    async def transaction(self):
        async with self._write_lock:
            db = await self.connect()
            try:
                await db.execute("BEGIN IMMEDIATE")
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise
            finally:
                await db.close()

    async def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        async with self._write_lock:
            async with self.connect() as db:
                await db.execute(query, params)
                await db.commit()

    async def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        async with self.connect() as db:
            cursor = await db.execute(query, params)
            return await cursor.fetchone()

    async def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        async with self.connect() as db:
            cursor = await db.execute(query, params)
            return await cursor.fetchall()
