from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone

from proxmox.client import ProxmoxClient, ProxmoxConfig, ProxmoxError
from minecraft.client import PterodactylClient, PterodactylConfig, PterodactylError


class ProvisioningService:
    """Idempotent redemption -> Proxmox VM worker.

    It intentionally requires a prebuilt cloud-init/template VM. The template
    supplies the OS, network defaults and disk layout; this service only clones
    it and applies the plan's CPU/RAM/name settings.
    """

    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.settings = bot.settings
        self.logger = logging.getLogger("helzerx.provisioning")

    def client(self) -> ProxmoxClient | None:
        s = self.settings
        if not all((s.proxmox_api_url, s.proxmox_token_id, s.proxmox_token_secret)):

            return None
        return ProxmoxClient(ProxmoxConfig(
            base_url=s.proxmox_api_url,
            token_id=s.proxmox_token_id,
            token_secret=s.proxmox_token_secret,
            verify_ssl=s.proxmox_verify_ssl,
        ))

    async def enqueue_pending(self) -> None:
        rows = await self.db.fetchall(
            "SELECT r.id FROM redemptions r LEFT JOIN provisioning_jobs j ON j.redemption_id=r.id "
            "WHERE r.status='pending' AND j.id IS NULL ORDER BY r.id LIMIT 25"
        )
        for row in rows:
            await self.db.execute(
                "INSERT OR IGNORE INTO provisioning_jobs(redemption_id,status,idempotency_key) VALUES(?,?,?)",
                (int(row["id"]), "queued", "redemption:%s" % row["id"]),
            )

    async def run_once(self) -> None:
        await self.enqueue_pending()
        row = await self.db.fetchone(
            "SELECT j.*,r.user_id,r.cost,p.plan_key,p.name,p.ram_mb,p.cpu_units,p.storage_gb,p.duration_days,p.metadata "
            "FROM provisioning_jobs j JOIN redemptions r ON r.id=j.redemption_id "
            "JOIN plans p ON p.id=r.plan_id WHERE j.status='queued' ORDER BY j.id LIMIT 1"
        )
        if not row:
            return
        try:
            plan_metadata = json.loads(row["metadata"] or "{}")
        except (TypeError, ValueError):
            plan_metadata = {}
        provider = str(plan_metadata.get("provider", "qemu")).lower()
        cluster_name = str(plan_metadata.get("cluster") or self.settings.proxmox_default_node or "") or None
        client = self.client(cluster_name)
        if provider == "pterodactyl":
            if not all((self.settings.pterodactyl_url, self.settings.pterodactyl_api_key)):
                return
        elif client is None:
            return

        job_id = int(row["id"])
        await self.db.execute(
            "UPDATE provisioning_jobs SET status='running',attempts=attempts+1,started_at=CURRENT_TIMESTAMP WHERE id=? AND status='queued'",
            (job_id,),
        )
        try:
            await self.provision(client, row)
        except Exception as exc:
            self.logger.exception("Provisioning job %s failed", job_id)
            await self.db.execute(
                "UPDATE provisioning_jobs SET status='failed',last_error=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (str(exc)[:1000], job_id),
            )
            attempts = int(row["attempts"]) + 1
            if attempts >= 3:
                await self.bot.hosting.fail_and_refund(int(row["redemption_id"]), str(exc)[:500])
            else:
                await self.db.execute("UPDATE provisioning_jobs SET status='queued' WHERE id=?", (job_id,))

    async def provision(self, client: ProxmoxClient, row) -> None:
        settings = self.settings
        try:
            plan_metadata = json.loads(row["metadata"] or "{}")
        except (TypeError, ValueError):
            plan_metadata = {}
        cluster_name = str(plan_metadata.get("cluster") or settings.proxmox_default_node or "") or None
        client = self.client(cluster_name) if client is not None else self.client(cluster_name)
        node_name = plan_metadata.get("node") or settings.proxmox_default_node
        if not node_name:
            nodes = await client.nodes()
            ram_need = int(row["ram_mb"]) * 1024 * 1024
            cpu_need = float(row["cpu_units"])
            available = []
            for n in nodes:
                if n.get("status") != "online":
                    continue
                free_mem = int(n.get("maxmem", 0)) - int(n.get("mem", 0))
                max_cpu = float(n.get("maxcpu", 0))
                used_ratio = float(n.get("cpu", 0))
                free_cpu = max_cpu * max(0.0, 1.0 - used_ratio)
                if free_mem >= ram_need and free_cpu >= cpu_need:
                    available.append((free_mem, free_cpu, n["node"]))
            if not available:
                raise ProxmoxError("No online Proxmox node has enough reported capacity for this plan.")
            available.sort(reverse=True)
            node_name = available[0][2]

        vmid = await client.next_vmid()
        hostname = "hx-%s-%s" % (str(row["plan_key"]).lower(), secrets.token_hex(3))
        try:
            metadata = json.loads(row["metadata"] or "{}")
        except (TypeError, ValueError):
            metadata = {}
        provider = str(metadata.get("provider", "qemu")).lower()

        if provider == "pterodactyl":
            await self.provision_minecraft(row, hostname)
            return

        if provider == "lxc":
            if not settings.proxmox_template_ctid:
                raise ProxmoxError("PROXMOX_TEMPLATE_CTID is required for LXC plans.")
            await client.clone_container(
                node_name, int(settings.proxmox_template_ctid), vmid, hostname, settings.proxmox_storage
            )
            config = {
                "memory": int(row["ram_mb"]),
                "swap": max(256, int(row["ram_mb"]) // 2),
                "hostname": hostname,
                "onboot": 1,
                "cores": int(row["cpu_units"]),
            }
            if settings.proxmox_bridge:
                config["net0"] = "name=eth0,bridge=%s,ip=dhcp" % settings.proxmox_bridge
            await client.set_container_config(node_name, vmid, config)
            kind = "vps"
        else:
            if not settings.proxmox_template_vmid:
                raise ProxmoxError("PROXMOX_TEMPLATE_VMID is required for QEMU plans.")
            await client.clone_vm(
                node_name, int(settings.proxmox_template_vmid), vmid, hostname, True, settings.proxmox_storage
            )
            config = {
                "memory": int(row["ram_mb"]),
                "cores": int(row["cpu_units"]),
                "name": hostname,
                "onboot": 1,
                "agent": 1,
            }
            if settings.proxmox_bridge:
                config["net0"] = "virtio,bridge=%s" % settings.proxmox_bridge
            await client.set_vm_config(node_name, vmid, config)
            kind = "vps"

        node_id = await self.db.fetchone(
            "SELECT id FROM proxmox_nodes WHERE node_name=? LIMIT 1", (node_name,)
        )
        async with self.db.transaction() as db:
            cur = await db.execute(
                """INSERT INTO vps_servers
                   (user_id,plan_id,node_id,vmid,hostname,kind,status,os,expires_at,provider_id,metadata)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    int(row["user_id"]), await self.plan_id(db, str(row["plan_key"])),
                    int(node_id["id"]) if node_id else None, vmid, hostname, kind,
                    "active", "template", (datetime.now(timezone.utc)+timedelta(days=int(row["duration_days"]))).isoformat(),
                    str(vmid), json.dumps({"node": node_name, "provider": provider}, separators=(",", ":")),
                ),
            )
            server_id = cur.lastrowid
            await db.execute(
                "UPDATE provisioning_jobs SET status='completed',server_id=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (server_id, int(row["id"])),
            )
            await db.execute(
                "UPDATE redemptions SET status='completed',provider_resource_id=?,completed_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",
                (str(vmid), int(row["redemption_id"])),
            )

        if settings.proxmox_start:
            if provider == "lxc":
                await client.container_action(node_name, vmid, "start")
            else:
                await client.vm_action(node_name, vmid, "start")

        user = self.bot.get_user(int(row["user_id"]))
        if user:
            try:
                await user.send(
                    "## HelzerX Cloud — VPS Provisioned\n"
                    "Your VPS **%s** has been created.\n\n"
                    "• Plan: **%s**\n• VMID: **%s**\n• Node: **%s**\n"
                    "• RAM: **%s MB**\n• CPU: **%s cores**\n• Storage: **%s GB**\n\n"
                    "Network credentials depend on your configured cloud-init template."
                    % (hostname, row["plan_key"], vmid, node_name, row["ram_mb"], row["cpu_units"], row["storage_gb"])
                )
            except Exception:
                self.logger.warning("Could not DM provisioning result to user %s", row["user_id"])

    async def provision_minecraft(self, row, hostname: str) -> None:
        s = self.settings
        if not all((s.pterodactyl_url, s.pterodactyl_api_key, s.pterodactyl_nest_id,
                    s.pterodactyl_egg_id, s.pterodactyl_location_id)):
            raise PterodactylError("Pterodactyl provisioning is not fully configured.")
        client = PterodactylClient(PterodactylConfig(
            base_url=s.pterodactyl_url,
            api_key=s.pterodactyl_api_key,
            verify_ssl=s.proxmox_verify_ssl,
        ))
        account = await self.db.fetchone("SELECT email FROM accounts WHERE user_id=? AND email_verified=1", (row["user_id"],))
        email = account["email"] if account else "discord-%s@helzerx.local" % row["user_id"]
        user = await client.find_user(email)
        if not user:
            user = await client.create_user(
                "hx%s" % row["user_id"],
                email,
                "HelzerX",
                "User",
            )
        attrs_user = user.get("attributes", user)
        ptero_user_id = int(attrs_user["id"])
        result = await client.create_server(
            hostname,
            ptero_user_id,
            int(s.pterodactyl_nest_id),
            int(s.pterodactyl_egg_id),
            s.pterodactyl_docker_image,
            s.pterodactyl_startup,
            int(row["ram_mb"]),
            int(row["storage_gb"]) * 1024,
            int(row["cpu_units"]),
            int(s.pterodactyl_location_id),
            {"SERVER_JARFILE": "server.jar"},
        )
        attrs = result.get("attributes", result)
        provider_id = str(attrs.get("id") or attrs.get("identifier") or "")
        async with self.db.transaction() as db:
            plan_id = await self.plan_id(db, str(row["plan_key"]))
            cur = await db.execute(
                """INSERT INTO vps_servers
                   (user_id,plan_id,vmid,hostname,kind,status,os,expires_at,provider_id,metadata)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    int(row["user_id"]), plan_id, None, hostname, "minecraft", "active",
                    "pterodactyl",
                    (datetime.now(timezone.utc)+timedelta(days=int(row["duration_days"]))).isoformat(),
                    provider_id,
                    json.dumps({"provider":"pterodactyl","panel_url":s.pterodactyl_url}, separators=(",", ":")),
                ),
            )
            await db.execute(
                "UPDATE provisioning_jobs SET status='completed',server_id=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (cur.lastrowid, int(row["id"])),
            )
            await db.execute(
                "UPDATE redemptions SET status='completed',provider_resource_id=?,completed_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",
                (provider_id, int(row["redemption_id"])),
            )
        user_obj = self.bot.get_user(int(row["user_id"]))
        if user_obj:
            try:
                await user_obj.send(
                    "## HelzerX Cloud — Minecraft Server Provisioned\\n"
                    "Your **%s** server has been created.\\n\\n"
                    "• Plan: **%s**\\n• Memory: **%s MB**\\n• Storage: **%s GB**\\n"
                    "• CPU: **%s%%**\\n• Server ID: **%s**"
                    % (hostname,row["plan_key"],row["ram_mb"],row["storage_gb"],row["cpu_units"],provider_id)
                )
            except Exception:
                self.logger.warning("Could not DM Minecraft provisioning result to user %s", row["user_id"])


    async def plan_id(self, db, plan_key: str) -> int:
        row = await (await db.execute("SELECT id FROM plans WHERE plan_key=?", (plan_key,))).fetchone()
        if not row:
            raise RuntimeError("Plan disappeared during provisioning.")
        return int(row["id"])
