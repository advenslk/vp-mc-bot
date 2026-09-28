from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _int_set(value: str | None) -> set[int]:
    if not value:
        return set()
    result: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if item.isdigit():
            result.add(int(item))
    return result


@dataclass(frozen=True)
class Settings:
    token: str
    database_path: str
    prefix: str
    bot_name: str
    log_level: str
    owner_ids: set[int]
    guild_id: int | None
    reward_channel_id: int | None
    log_channel_id: int | None
    daily_reward: int
    message_reward: int
    message_reward_cooldown: int
    voice_reward_per_10_min: int
    voice_min_members: int
    proxmox_verify_ssl: bool
    proxmox_default_node: str | None
    proxmox_api_url: str | None
    proxmox_token_id: str | None
    proxmox_token_secret: str | None
    proxmox_template_vmid: int | None
    proxmox_storage: str | None
    proxmox_bridge: str
    proxmox_start: bool
    provisioning_interval: int


def _optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value.isdigit() else None


def load_settings() -> Settings:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is missing. Copy .env.example to .env and configure it.")

    return Settings(
        token=token,
        database_path=os.getenv("DATABASE_PATH", "data/helzerx.db"),
        prefix=os.getenv("PREFIX", "."),
        bot_name=os.getenv("BOT_NAME", "HelzerX Cloud"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        owner_ids=_int_set(os.getenv("OWNER_IDS")),
        guild_id=_optional_int("GUILD_ID"),
        reward_channel_id=_optional_int("REWARD_CHANNEL_ID"),
        log_channel_id=_optional_int("LOG_CHANNEL_ID"),
        daily_reward=max(0, int(os.getenv("DAILY_REWARD", "100"))),
        message_reward=max(0, int(os.getenv("MESSAGE_REWARD", "2"))),
        message_reward_cooldown=max(1, int(os.getenv("MESSAGE_REWARD_COOLDOWN", "60"))),
        voice_reward_per_10_min=max(0, int(os.getenv("VOICE_REWARD_PER_10_MIN", "10"))),
        voice_min_members=max(1, int(os.getenv("VOICE_MIN_MEMBERS", "2"))),
        proxmox_verify_ssl=os.getenv("PROXMOX_VERIFY_SSL", "false").lower() in {"1", "true", "yes"},
        proxmox_default_node=os.getenv("PROXMOX_DEFAULT_NODE") or None,
        proxmox_api_url=os.getenv("PROXMOX_API_URL") or None,
        proxmox_token_id=os.getenv("PROXMOX_TOKEN_ID") or None,
        proxmox_token_secret=os.getenv("PROXMOX_TOKEN_SECRET") or None,
        proxmox_template_vmid=_optional_int("PROXMOX_TEMPLATE_VMID"),
        proxmox_storage=os.getenv("PROXMOX_STORAGE") or None,
        proxmox_bridge=os.getenv("PROXMOX_BRIDGE", "vmbr0"),
        proxmox_start=os.getenv("PROXMOX_START", "true").lower() in {"1", "true", "yes"},
        provisioning_interval=max(10, int(os.getenv("PROVISIONING_INTERVAL", "20"))),
    )
