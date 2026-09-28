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
