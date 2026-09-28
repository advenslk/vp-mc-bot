# HelzerX Cloud — VPS / Minecraft Discord Bot

Production-oriented Python Discord bot foundation for the HelzerX Cloud community economy and hosting platform.

## Core

- Discord Components V2 UI
- Central custom emoji registry in config/emoji.py
- SQLite WAL database with transactional writes
- HZL internal reward currency
- Daily rewards
- Cooldown-protected message rewards
- Voice activity rewards with minimum-member protection
- Verified invite tracking
- Invite milestone database
- Transaction ledger
- HZL leaderboard
- Hosting plans for Minecraft and VPS
- Atomic HZL hosting redemption
- Automatic refund path for failed provisioning
- Audit log foundation
- Async Proxmox API client
- Owner-protected economy administration
- Environment-based secrets

## Setup

1. Install Python 3.11+.
2. Create a virtual environment.
3. Install dependencies:

    python -m pip install -r requirements.txt

4. Copy .env.example to .env and set DISCORD_TOKEN.
5. Enable the Discord Developer Portal intents required by the bot:
   - Server Members Intent
   - Message Content Intent
   - Presence Intent if presence features are used
6. Start:

    python bot.py

## Important

Never commit .env, Discord tokens, Proxmox API secrets, database files, or user credentials.

The Proxmox integration is deliberately isolated. Use a dedicated PVE API token with the smallest possible permissions instead of a root password.

## Commands

.profile
.balance
.daily
.invites
.transactions
.leaderboard
.rewards
.mc-plans
.vps-plans
.redeem <plan>
.my-redemptions

Owner-only:
.admin-add <member> <amount> [reason]
.admin-remove <member> <amount> [reason]

## Architecture

The bot is separated into configuration, database, economy, hosting, Proxmox, command, and UI layers. This keeps economy accounting independent from infrastructure provisioning so a failed provider operation can be rolled back without creating negative HZL balances.

## Roadmap

The repository is designed to grow into:

- Full HZL quest and achievement engine
- Configurable reward campaigns and multipliers
- Full account registration and email verification
- Discord account linking
- VPS/Minecraft lifecycle management
- Proxmox node selection and capacity checks
- Automatic VM provisioning
- Resource monitoring
- Password reset and secure credential delivery
- Admin dashboard
- Web API
- Notifications and expiry automation
- Backups, metrics, health checks and operational audit tooling


## Current production foundation

The bot now includes:

- HZL wallet, atomic ledger, daily rewards, message/voice reward cooldowns and daily activity caps.
- Verified invite tracking with database-driven milestones.
- Database-driven quests and achievements.
- Minecraft and VPS plan catalog with owner-controlled HZL redemption costs.
- Atomic redemption reservations with automatic refund on provisioning failure.
- Proxmox API integration using API tokens.
- Capacity-aware automatic node selection when no default node is configured.
- Template-based automatic VPS cloning, resource assignment and startup.
- VPS ownership checks plus start/stop/shutdown/reboot/status/list commands.
- Provisioning jobs with idempotency keys and retry-safe state transitions.
- Argon2id password hashing, email verification token primitives and Discord/account link schema.
- Discord Components V2 UI, Docker deployment and GitHub CI.

### Automatic VPS provisioning

Configure a prepared Proxmox cloud-init/template VM and the following variables:

```env
PROXMOX_API_URL=https://your-proxmox:8006
PROXMOX_TOKEN_ID=...
PROXMOX_TOKEN_SECRET=...
PROXMOX_TEMPLATE_VMID=9000
PROXMOX_STORAGE=local-lvm
PROXMOX_BRIDGE=vmbr0
PROXMOX_START=true
```

The template should already have a supported OS, cloud-init/network configuration and a working disk layout. The bot does not create arbitrary operating-system images or expose Proxmox root credentials.

### Security model

Never place Proxmox secrets, passwords or recovery tokens in Discord messages, source code or Git history. Use a dedicated Proxmox API token with only the permissions required for provisioning and lifecycle actions. Email verification/account delivery still requires an SMTP or transactional-email provider before it can be exposed through a public web UI.

### Important deployment note

The repository is a production-oriented foundation, not a claim that every external provider is configured automatically. Proxmox templates, network/IP allocation, Pterodactyl panel credentials, email delivery, DNS and payment gateways are environment/provider-specific and must be configured before those integrations can be activated.
