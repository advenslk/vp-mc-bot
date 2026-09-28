from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from proxmox.client import ProxmoxClient, ProxmoxConfig, ProxmoxError


class LifecycleService:
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("helzerx.lifecycle")

    def client(self) -> ProxmoxClient | None:
        s = self.bot.settings
        if not all((s.proxmox_api_url, s.proxmox_token_id, s.proxmox_token_secret)):
            return None
        return ProxmoxClient(ProxmoxConfig(
            base_url=s.proxmox_api_url,
            token_id=s.proxmox_token_id,
            token_secret=s.proxmox_token_secret,
            verify_ssl=s.proxmox_verify_ssl,
        ))

    async def expire_due(self) -> int:
        rows = await self.bot.db.fetchall(
            "SELECT id,vmid,kind,metadata FROM vps_servers "
            "WHERE status='active' AND expires_at IS NOT NULL AND expires_at<=CURRENT_TIMESTAMP"
        )
        client = self.client()
        count = 0
        for row in rows:
            try:
                meta = json.loads(row["metadata"] or "{}")
                node = meta.get("node") or self.bot.settings.proxmox_default_node
                if client and node and row["vmid"]:
                    if row["kind"] == "minecraft":
                        await client.container_action(node, int(row["vmid"]), "stop")
                    elif meta.get("provider") == "lxc":
                        await client.container_action(node, int(row["vmid"]), "stop")
                    else:
                        await client.vm_action(node, int(row["vmid"]), "shutdown")
                await self.bot.db.execute(
                    "UPDATE vps_servers SET status='expired',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='active'",
                    (int(row["id"]),),
                )
                await self.bot.db.execute(
                    "INSERT INTO server_events(server_id,event_type,details) VALUES(?,?,?)",
                    (int(row["id"]), "expired", '{"automatic":true}'),
                )
                count += 1
            except Exception:
                self.logger.exception("Failed to expire server %s", row["id"])
        return count

    async def delete_server(self, server_id: int, user_id: int | None = None) -> bool:
        clauses = ["id=?"]
        params: list[object] = [server_id]
        if user_id is not None:
            clauses.append("user_id=?")
            params.append(user_id)
        row = await self.bot.db.fetchone(
            "SELECT * FROM vps_servers WHERE " + " AND ".join(clauses),
            tuple(params),
        )
        if not row:
            return False
        client = self.client()
        meta = json.loads(row["metadata"] or "{}")
        node = meta.get("node") or self.bot.settings.proxmox_default_node
        if client and node and row["vmid"]:
            if meta.get("provider") == "lxc":
                await client.delete_container(node, int(row["vmid"]))
            else:
                await client.delete_vm(node, int(row["vmid"]))
        await self.bot.db.execute("DELETE FROM vps_servers WHERE id=?", (server_id,))
        return True
