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
    proxmox_public_url: str | None
    proxmox_token_id: str | None
    proxmox_token_secret: str | None
    proxmox_template_vmid: int | None
    proxmox_template_ctid: int | None
    proxmox_storage: str | None
    proxmox_bridge: str
    proxmox_start: bool
    proxmox_ssh_host: str | None
    proxmox_ssh_port: int
    proxmox_ssh_user: str
    proxmox_ssh_key_file: str | None
    proxmox_ssh_password: str | None
    proxmox_ssh_known_hosts: str | None
    proxmox_ssh_strict_host_key: bool
    proxmox_clusters: dict[str, dict[str, object]]
    provisioning_interval: int
    pterodactyl_url: str | None
    pterodactyl_api_key: str | None
    pterodactyl_nest_id: int | None
    pterodactyl_egg_id: int | None
    pterodactyl_location_id: int | None
    pterodactyl_docker_image: str
    pterodactyl_startup: str


def _optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value.isdigit() else None


def load_settings() -> Settings:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is missing. Copy .env.example to .env and configure it.")

    import json
    clusters = {}
    raw_clusters = os.getenv("PROXMOX_CLUSTERS_JSON", "").strip()
    if raw_clusters:
        try:
            parsed = json.loads(raw_clusters)
            if isinstance(parsed, dict):
                clusters = {str(k): v for k, v in parsed.items() if isinstance(v, dict)}
        except json.JSONDecodeError as exc:
            raise RuntimeError("PROXMOX_CLUSTERS_JSON is not valid JSON.") from exc

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
        proxmox_public_url=os.getenv("PROXMOX_PUBLIC_URL") or None,
        proxmox_token_id=os.getenv("PROXMOX_TOKEN_ID") or None,
        proxmox_token_secret=os.getenv("PROXMOX_TOKEN_SECRET") or None,
        proxmox_template_vmid=_optional_int("PROXMOX_TEMPLATE_VMID"),
        proxmox_template_ctid=_optional_int("PROXMOX_TEMPLATE_CTID"),\n        proxmox_ubuntu_2204_template_ctid=_optional_int("PROXMOX_UBUNTU_2204_TEMPLATE_CTID"),\n        proxmox_ubuntu_2404_template_ctid=_optional_int("PROXMOX_UBUNTU_2404_TEMPLATE_CTID"),\n        proxmox_almalinux_9_template_ctid=_optional_int("PROXMOX_ALMALINUX_9_TEMPLATE_CTID"),
        proxmox_storage=os.getenv("PROXMOX_STORAGE") or None,
        proxmox_bridge=os.getenv("PROXMOX_BRIDGE", "vmbr0"),
        proxmox_start=os.getenv("PROXMOX_START", "true").lower() in {"1", "true", "yes"},
        proxmox_ssh_host=os.getenv("PROXMOX_SSH_HOST") or None,
        proxmox_ssh_port=max(1, int(os.getenv("PROXMOX_SSH_PORT", "22"))),
        proxmox_ssh_user=os.getenv("PROXMOX_SSH_USER", "root"),
        proxmox_ssh_key_file=os.getenv("PROXMOX_SSH_KEY_FILE") or None,
        proxmox_ssh_password=os.getenv("PROXMOX_SSH_PASSWORD") or None,
        proxmox_ssh_known_hosts=os.getenv("PROXMOX_SSH_KNOWN_HOSTS") or None,
        proxmox_ssh_strict_host_key=os.getenv("PROXMOX_SSH_STRICT_HOST_KEY", "true").lower() in {"1", "true", "yes"},
        proxmox_clusters=clusters,
        provisioning_interval=max(10, int(os.getenv("PROVISIONING_INTERVAL", "20"))),
        pterodactyl_url=os.getenv("PTERODACTYL_URL") or None,
        pterodactyl_api_key=os.getenv("PTERODACTYL_API_KEY") or None,
        pterodactyl_nest_id=_optional_int("PTERODACTYL_NEST_ID"),
        pterodactyl_egg_id=_optional_int("PTERODACTYL_EGG_ID"),
        pterodactyl_location_id=_optional_int("PTERODACTYL_LOCATION_ID"),
        pterodactyl_docker_image=os.getenv("PTERODACTYL_DOCKER_IMAGE", "ghcr.io/pterodactyl/yolks:java_21"),
        pterodactyl_startup=os.getenv("PTERODACTYL_STARTUP", "java -Xms128M -Xmx{{SERVER_MEMORY}}M -jar {{SERVER_JARFILE}} nogui"),
    )
