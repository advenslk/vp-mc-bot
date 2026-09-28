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


## Provider support

### VPS / LXC
- QEMU VPS plans use a prepared Proxmox VM template.
- LXC plans use a prepared Proxmox CT template by setting the plan provider to `lxc`.
- Owner command: `.admin-plan-provider <plan> <qemu|lxc>`.
- Configure `PROXMOX_TEMPLATE_VMID` for QEMU and `PROXMOX_TEMPLATE_CTID` for LXC.
- Automatic expiry stops the resource and marks it expired.

### Minecraft
Minecraft plans default to the Pterodactyl provider. Configure:

```env
PTERODACTYL_URL=https://panel.example.com
PTERODACTYL_API_KEY=...
PTERODACTYL_NEST_ID=...
PTERODACTYL_EGG_ID=...
PTERODACTYL_LOCATION_ID=...
PTERODACTYL_DOCKER_IMAGE=ghcr.io/pterodactyl/yolks:java_21
PTERODACTYL_STARTUP=java -Xms128M -Xmx{{SERVER_MEMORY}}M -jar {{SERVER_JARFILE}} nogui
```

The bot creates/reuses a non-admin Pterodactyl user, creates the server with the plan's RAM/CPU/disk limits, records the provider resource, and suspends it automatically after expiry.

### Administration
- `.admin-plan-cost <plan> <hzl>`
- `.admin-plan-toggle <plan> <0|1>`
- `.admin-plan-provider <plan> <qemu|lxc|pterodactyl>`
- `.admin-node-add <name> <node> <location> <api_url>`
- `.admin-node-toggle <name> <0|1>`
- `.admin-nodes`

### User hosting
- `.mc-plans`
- `.vps-plans`
- `.redeem <plan>`
- `.my-redemptions`
- `.myvps`
- `.vps-info <id>`
- `.vps-start <id>`
- `.vps-stop <id>`
- `.vps-shutdown <id>`
- `.vps-restart <id>`
- `.vps-delete <id> CONFIRM`

Destructive deletion requires the explicit `CONFIRM` argument and verifies ownership before deleting the provider resource.


## Optional Web API

Run the API separately with:

```bash
uvicorn web.api:app --host 0.0.0.0 --port 8000
```

Endpoints include account registration/verification/login/logout, authenticated plan listing, server listing and HZL redemption. Configure SMTP before enabling account verification in production.
