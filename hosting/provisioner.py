from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone

from proxmox.client import ProxmoxClient, ProxmoxConfig, ProxmoxError, ProxmoxConfigurationError
from minecraft.client import PterodactylClient, PterodactylConfig, PterodactylError
from core.components import provisioning_view


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

    def client(self, cluster_name=None) -> ProxmoxClient | None:
        from proxmox.client import client_from_settings
        return client_from_settings(self.settings, cluster_name)

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

    async def recover_interrupted_jobs(self) -> None:
        # If the process/container restarted after a transient infrastructure error,
        # never leave a customer redemption permanently stuck in a failed job state.
        await self.db.execute(
            "UPDATE provisioning_jobs SET status='queued',finished_at=NULL "
            "WHERE status='failed' AND redemption_id IN "
            "(SELECT id FROM redemptions WHERE status='provisioning')"
        )

    async def progress(self, job_id: int, plan_key: str, stage: str, percent: int, detail: str, status: str = "provisioning") -> None:
        await self.db.execute(
            "UPDATE provisioning_jobs SET progress_stage=?,progress_percent=?,progress_detail=? WHERE id=?",
            (stage, max(0, min(100, int(percent))), detail[:1000], job_id),
        )
        row = await self.db.fetchone("SELECT channel_id,message_id FROM provisioning_jobs WHERE id=?", (job_id,))
        if not row or not row["channel_id"] or not row["message_id"]:
            return
        try:
            channel = self.bot.get_channel(int(row["channel_id"]))
            if channel is None:
                channel = await self.bot.fetch_channel(int(row["channel_id"]))
            message = await channel.fetch_message(int(row["message_id"]))
            await message.edit(view=provisioning_view(plan_key, stage, percent, detail, status))
        except Exception:
            self.logger.debug("Could not update provisioning progress for job %s", job_id, exc_info=True)
    async def run_once(self) -> None:
        await self.recover_interrupted_jobs()
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
        provider = str(plan_metadata.get("provider", "lxc")).lower()
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
        await self.db.execute("UPDATE redemptions SET status='provisioning' WHERE id=? AND status IN ('pending','provisioning')", (int(row["redemption_id"]),))
        await self.progress(job_id, str(row["plan_key"]), "Preparing", 10, "Provisioning worker started. Validating the selected provider and target.")
        try:
            await self.provision(client, row)
        except ProxmoxConfigurationError as exc:
            self.logger.warning("Provisioning job %s waiting for Proxmox configuration: %s", job_id, exc)
            await self.db.execute(
                "UPDATE provisioning_jobs SET status='queued',last_error=?,finished_at=NULL WHERE id=?",
                (str(exc)[:1000], job_id),
            )
            await self.progress(
                job_id, str(row["plan_key"]), "Waiting for Proxmox", 35,
                str(exc)[:900], "provisioning",
            )
            return
        except Exception as exc:
            self.logger.exception("Provisioning job %s failed", job_id)
            await self.db.execute(
                "UPDATE provisioning_jobs SET status='failed',last_error=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (str(exc)[:1000], job_id),
            )
            await self.progress(job_id, str(row["plan_key"]), "Failed", 100, "Provisioning stopped: %s" % str(exc)[:700], "failed")
            attempts = int(row["attempts"]) + 1
            if attempts >= 3:
                await self.bot.hosting.fail_and_refund(int(row["redemption_id"]), str(exc)[:500])
            else:
                await self.db.execute("UPDATE provisioning_jobs SET status='queued' WHERE id=?", (job_id,))

    async def provision(self, client: ProxmoxClient, row) -> None:
        settings = self.settings
        job_id = int(row["id"])
        plan_key = str(row["plan_key"])
        await self.progress(job_id, plan_key, "Selecting node", 20, "Selecting a Proxmox node with the required resources.")
        try:
            plan_metadata = json.loads(row["metadata"] or "{}")
        except (TypeError, ValueError):
            plan_metadata = {}
        cluster_name = str(plan_metadata.get("cluster") or settings.proxmox_default_node or "") or None
        client = self.client(cluster_name)
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

        hostname = "hx-%s-%s" % (str(row["plan_key"]).lower(), secrets.token_hex(3))
        try:
            metadata = json.loads(row["metadata"] or "{}")
        except (TypeError, ValueError):
            metadata = {}
        provider = str(metadata.get("provider", "lxc")).lower()

        if provider == "pterodactyl":
            await self.progress(job_id, plan_key, "Creating Minecraft", 50, "Creating the Minecraft server in Pterodactyl.")
            await self.provision_minecraft(row, hostname)
            return

        await self.progress(job_id, plan_key, "Allocating resource", 35, "Node selected. Allocating the next available VMID.")
        vmid = await client.next_vmid()

        vps_username = "root"
        vps_password = secrets.token_urlsafe(15)

        if provider == "lxc":
            await self.progress(job_id, plan_key, "Creating LXC", 50, "Cloning the prepared LXC template into VMID `%s`." % vmid)
            if not settings.proxmox_template_ctid:
                raise ProxmoxError("PROXMOX_TEMPLATE_CTID is required for LXC plans.")
            await client.clone_container_and_wait(
                node_name,
                int(settings.proxmox_template_ctid),
                vmid,
                hostname,
                settings.proxmox_storage,
                full=True,
            )
            target_storage_gb = int(row["storage_gb"] or 0)
            if target_storage_gb > 0:
                rootfs = await client.container_config(node_name, vmid)
                rootfs_value = str((rootfs or {}).get("rootfs") or "")
                current_gb = None
                for part in rootfs_value.split(","):
                    part = part.strip()
                    if part.startswith("size="):
                        raw = part.split("=", 1)[1].strip().upper()
                        try:
                            if raw.endswith("T"):
                                current_gb = float(raw[:-1]) * 1024
                            elif raw.endswith("G"):
                                current_gb = float(raw[:-1])
                            elif raw.endswith("M"):
                                current_gb = float(raw[:-1]) / 1024
                        except ValueError:
                            current_gb = None
                        break
                if current_gb is not None and current_gb > target_storage_gb:
                    raise ProxmoxError(
                        "LXC template rootfs is %.1f GB but plan %s requires %s GB. "
                        "Proxmox cannot shrink an LXC rootfs during provisioning."
                        % (current_gb, plan_key, target_storage_gb)
                    )
                if current_gb is None or current_gb < target_storage_gb:
                    await client.resize_container(
                        node_name, vmid, "rootfs", "%sG" % target_storage_gb
                    )
            config = {
                "memory": int(row["ram_mb"]),
                "swap": max(256, int(row["ram_mb"]) // 2),
                "hostname": hostname,
                "onboot": 1,
                "cores": int(row["cpu_units"]),
                "password": vps_password,
            }
            if settings.proxmox_bridge:
                config["net0"] = "name=eth0,bridge=%s,ip=dhcp" % settings.proxmox_bridge
            await client.set_container_config(node_name, vmid, config)
            await self.progress(job_id, plan_key, "Applying resources", 70, "Applying RAM, CPU, hostname, network and VPS credentials.")
            kind = "vps"
        else:
            await self.progress(job_id, plan_key, "Creating VPS", 50, "Cloning the prepared VM template into VMID `%s`." % vmid)
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
            await self.progress(job_id, plan_key, "Applying resources", 70, "Applying RAM, CPU, hostname and network configuration.")
            kind = "vps"

        node_id = await self.db.fetchone(
            "SELECT id FROM proxmox_nodes WHERE node_name=? LIMIT 1", (node_name,)
        )
        async with self.db.transaction() as db:
            cur = await db.execute(
                """INSERT INTO vps_servers
                   (user_id,plan_id,node_id,vmid,hostname,kind,status,os,expires_at,provider_id,username,metadata)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    int(row["user_id"]), await self.plan_id(db, str(row["plan_key"])),
                    int(node_id["id"]) if node_id else None, vmid, hostname, kind,
                    "active", "template", (datetime.now(timezone.utc)+timedelta(days=int(row["duration_days"]))).isoformat(),
                    str(vmid), vps_username,
                    json.dumps({"node": node_name, "cluster": cluster_name, "provider": provider}, separators=(",", ":")),
                ),
            )
            server_id = cur.lastrowid
        await self.progress(job_id, plan_key, "Starting VPS", 85, "Resource created successfully. Starting the VPS and waiting for finalization.")
        if settings.proxmox_start:
            if provider == "lxc":
                await client.container_action(node_name, vmid, "start")
            else:
                await client.vm_action(node_name, vmid, "start")

        await self.db.execute(
            "UPDATE provisioning_jobs SET status='completed',server_id=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",
            (server_id, int(row["id"])),
        )
        await self.db.execute(
            "UPDATE redemptions SET status='completed',provider_resource_id=?,completed_at=CURRENT_TIMESTAMP WHERE id=? AND status IN ('pending','provisioning')",
            (str(vmid), int(row["redemption_id"])),
        )
        await self.progress(job_id, plan_key, "Finalizing", 95, "VPS is ready. Preparing the access details and final Discord notification.")
        user = self.bot.get_user(int(row["user_id"]))
        if user is None:
            try:
                user = await self.bot.fetch_user(int(row["user_id"]))
            except Exception:
                user = None
        if user:
            try:
                await user.send(
                    "## HelzerX Cloud — VPS Ready\n"
                    "Your **%s** VPS has been provisioned successfully.\n\n"
                    "### Proxmox Access\n"
                    "• Panel: **%s**\n• Node: **%s**\n• VMID: **%s**\n\n"
                    "### VPS Login\n"
                    "• Username: `%s`\n• Password: `%s`\n• Hostname: `%s`\n\n"
                    "### Resources\n"
                    "• Plan: **%s**\n• RAM: **%s MB**\n• CPU: **%s cores**\n• Storage: **%s GB**\n\n"
                    "Keep this message private and change the password after your first login."
                    % (hostname, settings.proxmox_public_url or "Proxmox panel URL is not configured",
                       node_name, vmid, vps_username, vps_password, hostname, row["plan_key"],
                       row["ram_mb"], row["cpu_units"], row["storage_gb"])
                )
            except Exception:
                self.logger.warning("Could not DM provisioning result to user %s", row["user_id"])
                await self.progress(
                    job_id, plan_key, "Completed", 100,
                    "VPS is ready, but Discord could not deliver the private DM. Run .vps-password %s to securely generate a new VPS password." % server_id,
                    "completed",
                )
                return

        await self.progress(
            job_id, plan_key, "Completed", 100,
            "VPS provisioning is complete. Access details were sent to your Discord DM.",
            "completed",
        )

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
                "UPDATE redemptions SET status='completed',provider_resource_id=?,completed_at=CURRENT_TIMESTAMP WHERE id=? AND status IN ('pending','provisioning')",
                (provider_id, int(row["redemption_id"])),
            )
        user_obj = self.bot.get_user(int(row["user_id"]))
        await self.progress(
            int(row["id"]),
            str(row["plan_key"]),
            "Finalizing", 95,
            "Minecraft server is ready. Preparing the final notification.",
        )
        await self.progress(
            int(row["id"]),
            str(row["plan_key"]),
            "Completed", 100,
            "Minecraft server provisioning is complete.",
            "completed",
        )
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
