from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import asyncio
from urllib.parse import quote

import httpx


class ProxmoxError(RuntimeError):
    pass


class ProxmoxConfigurationError(ProxmoxError):
    """A provider-side configuration/permission problem that needs operator action."""
    pass


@dataclass(frozen=True)
class ProxmoxConfig:
    base_url: str
    token_id: str
    token_secret: str
    verify_ssl: bool = False


class ProxmoxClient:
    """Small, async Proxmox API client.

    The bot should use a dedicated API token with only the permissions needed
    for provisioning. Never store a root password in the bot.
    """

    def __init__(self, config: ProxmoxConfig):
        self.config = config
        self.headers = {"Authorization": "PVEAPIToken=%s=%s" % (config.token_id, config.token_secret)}

    def _url(self, path: str) -> str:
        base = self.config.base_url.rstrip('/')
        # Accept host URLs and URLs already ending in /api2/json.
        if base.endswith('/api2/json'):
            base = base[:-len('/api2/json')]
        return base + '/api2/json/' + path.lstrip('/')

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        timeout = kwargs.pop("timeout", httpx.Timeout(30.0, connect=10.0))
        url = self._url(path)
        try:
            request_kwargs = {}
            if method.upper() in {"GET", "DELETE"}:
                request_kwargs["params"] = kwargs
            else:
                request_kwargs["data"] = kwargs
            async with httpx.AsyncClient(verify=self.config.verify_ssl, timeout=timeout) as client:
                response = await client.request(method, url, headers=self.headers, **request_kwargs)
        except httpx.ConnectTimeout as exc:
            raise ProxmoxError(
                "Could not connect to Proxmox API within 10 seconds: %s. "
                "Check PROXMOX_API_URL/PROXMOX_CLUSTERS_JSON, DNS, firewall and TCP port 8006."
                % self.config.base_url
            ) from exc
        except httpx.ConnectError as exc:
            raise ProxmoxError(
                "Could not connect to Proxmox API: %s. "
                "Check DNS, routing and TCP port 8006 from the bot container."
                % self.config.base_url
            ) from exc
        except httpx.HTTPError as exc:
            raise ProxmoxError("Proxmox HTTP client error: %s" % exc) from exc
        if response.status_code >= 400:
            body = response.text[:1000]
            if response.status_code == 403 and "Permission check failed" in body:
                message = (
                    "Proxmox API permission denied: %s. "
                    "Fix the token ACL on the indicated Proxmox path; the provisioning job will remain queued and retry automatically."
                    % body
                )
                if "SDN.Use" in body:
                    token_id = self.config.token_id
                    user_id = token_id.split("!", 1)[0]
                    message += (
                        " This Proxmox version requires SDN.Use for the bridge/VNet used by the LXC template. "
                        "On the Proxmox host, grant the backing user and the privilege-separated token access with: "
                        "pveum acl modify /sdn/zones/localnetwork -user '%s' -role PVESDNUser && "
                        "pveum acl modify /sdn/zones/localnetwork -token '%s' -role PVESDNUser"
                        % (user_id, token_id)
                    )
                raise ProxmoxConfigurationError(message)
            raise ProxmoxError("Proxmox returned HTTP %s: %s" % (response.status_code, body[:500]))
        payload = response.json()
        if isinstance(payload, dict) and payload.get("errors"):
            raise ProxmoxError(str(payload["errors"]))
        return payload.get("data", payload)

    async def cluster_resources(self) -> Any:
        return await self.request("GET", "cluster/resources")

    async def nodes(self) -> Any:
        return await self.request("GET", "nodes")

    async def node_status(self, node: str) -> Any:
        return await self.request("GET", "nodes/%s/status" % node)

    async def create_vm(self, node: str, vmid: int, config: dict[str, Any]) -> Any:
        return await self.request("POST", "nodes/%s/qemu" % node, vmid=vmid, **config)

    async def create_container(self, node: str, vmid: int, config: dict[str, Any]) -> Any:
        return await self.request("POST", "nodes/%s/lxc" % node, vmid=vmid, **config)

    async def clone_vm(self, node: str, template_vmid: int, newid: int, name: str, full: bool = True, storage: str | None = None) -> Any:
        params = {"newid": newid, "name": name, "full": 1 if full else 0}
        if storage:
            params["storage"] = storage
        return await self.request("POST", "nodes/%s/qemu/%s/clone" % (node, template_vmid), **params)

    async def clone_container(
        self,
        node: str,
        template_vmid: int,
        newid: int,
        hostname: str,
        storage: str | None = None,
        full: bool = True,
        password: str | None = None,
    ) -> Any:
        """Clone an LXC template as an independent full clone.

        Proxmox rejects the storage parameter for linked LXC clones.
        Hosted VPSes need independent root filesystems because the worker
        resizes them to the purchased plan size, so full clones are used.
        """
        params = {
            "newid": newid,
            "hostname": hostname,
            "full": 1 if full else 0,
        }
        if full and storage:
            params["storage"] = storage
        if password:
            params["password"] = password
        return await self.request(
            "POST", "nodes/%s/lxc/%s/clone" % (node, template_vmid), **params
        )

    async def wait_for_task(self, node: str, upid: str, timeout_seconds: int = 180, poll_seconds: float = 2.0) -> Any:
        """Wait for a Proxmox task (such as an LXC clone) to finish."""
        encoded = quote(str(upid), safe="")
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while True:
            result = await self.request("GET", "nodes/%s/tasks/%s/status" % (node, encoded))
            status = str((result or {}).get("status", "")).lower()
            if status == "stopped":
                exitstatus = str((result or {}).get("exitstatus", "")).lower()
                # Proxmox may finish successfully with non-fatal warnings,
                # e.g. "WARNINGS: 1". Only explicit failure statuses are errors.
                normalized = exitstatus.strip()
                if normalized and normalized not in {"ok", "null"} and not normalized.startswith("warnings:"):
                    raise ProxmoxError("Proxmox task failed: %s" % str(result)[:1000])
                return result
            if asyncio.get_running_loop().time() >= deadline:
                raise ProxmoxError("Proxmox task did not finish within %s seconds: %s" % (timeout_seconds, upid))
            await asyncio.sleep(poll_seconds)

    async def clone_container_and_wait(
        self,
        node: str,
        template_vmid: int,
        newid: int,
        hostname: str,
        storage: str | None = None,
        full: bool = True,
        password: str | None = None,
    ) -> Any:
        """Start an LXC clone and wait until the clone task has finished."""
        result = await self.clone_container(
            node, template_vmid, newid, hostname, storage, full, password
        )
        upid = result.get("data") if isinstance(result, dict) else result
        if upid:
            await self.wait_for_task(node, str(upid))
        return result

    async def clone_vm_and_wait(
        self,
        node: str,
        template_vmid: int,
        newid: int,
        name: str,
        full: bool = True,
        storage: str | None = None,
    ) -> Any:
        """Start a QEMU clone and wait until the clone task has finished."""
        result = await self.clone_vm(node, template_vmid, newid, name, full, storage)
        upid = result.get("data") if isinstance(result, dict) else result
        if upid:
            await self.wait_for_task(node, str(upid))
        return result
    async def set_container_config(self, node: str, vmid: int, config: dict[str, Any]) -> Any:
        return await self.request("PUT", "nodes/%s/lxc/%s/config" % (node, vmid), **config)

    async def container_config(self, node: str, vmid: int) -> Any:
        return await self.request("GET", "nodes/%s/lxc/%s/config" % (node, vmid))

    async def resize_container(self, node: str, vmid: int, disk: str, size: str) -> Any:
        return await self.request(
            "PUT", "nodes/%s/lxc/%s/resize" % (node, vmid), disk=disk, size=size
        )

    async def container_status(self, node: str, vmid: int) -> Any:
        return await self.request("GET", "nodes/%s/lxc/%s/status/current" % (node, vmid))

    async def delete_container(self, node: str, vmid: int, purge: bool = True) -> Any:
        return await self.request(
            "DELETE", "nodes/%s/lxc/%s" % (node, vmid), purge=1 if purge else 0
        )

    async def set_vm_config(self, node: str, vmid: int, config: dict[str, Any]) -> Any:
        return await self.request("PUT", "nodes/%s/qemu/%s/config" % (node, vmid), **config)

    async def vm_status(self, node: str, vmid: int) -> Any:
        return await self.request("GET", "nodes/%s/qemu/%s/status/current" % (node, vmid))

    async def delete_vm(self, node: str, vmid: int, purge: bool = True) -> Any:
        return await self.request(
            "DELETE", "nodes/%s/qemu/%s" % (node, vmid), purge=1 if purge else 0
        )

    async def next_vmid(self, excluded: set[int] | None = None) -> int:
        """Return a free VMID, excluding IDs reserved by provisioning jobs."""
        resources = await self.cluster_resources()

        used: set[int] = set(excluded or set())
        for item in resources if isinstance(resources, list) else []:
            if not isinstance(item, dict) or item.get("type") not in {"qemu", "lxc"}:
                continue
            try:
                used.add(int(item["vmid"]))
            except (KeyError, TypeError, ValueError):
                continue

        candidate = max(100, max(used, default=99) + 1)
        while candidate in used:
            candidate += 1

        if candidate > 999_999_999:
            raise ProxmoxError("No free VMID is available in the Proxmox VMID range.")
        return candidate

    async def vm_action(self, node: str, vmid: int, action: str) -> Any:
        if action not in {"start", "stop", "shutdown", "reboot", "reset"}:
            raise ValueError("Unsupported VM action")
        return await self.request("POST", "nodes/%s/qemu/%s/status/%s" % (node, vmid, action))

    async def container_action(self, node: str, vmid: int, action: str) -> Any:
        if action not in {"start", "stop", "shutdown", "reboot"}:
            raise ValueError("Unsupported container action")
        return await self.request("POST", "nodes/%s/lxc/%s/status/%s" % (node, vmid, action))


def client_from_settings(settings, cluster_name: str | None = None) -> ProxmoxClient | None:
    """Build a client from a named JSON cluster, falling back to legacy env settings."""
    cluster = None
    name = cluster_name or settings.proxmox_default_node
    clusters = getattr(settings, "proxmox_clusters", {}) or {}
    if name:
        cluster = clusters.get(name)
    if cluster:
        if not all(cluster.get(k) for k in ("api_url", "token_id", "token_secret")):
            return None
        return ProxmoxClient(ProxmoxConfig(
            base_url=str(cluster["api_url"]),
            token_id=str(cluster["token_id"]),
            token_secret=str(cluster["token_secret"]),
            verify_ssl=bool(cluster.get("verify_ssl", settings.proxmox_verify_ssl)),
        ))
    if not all((settings.proxmox_api_url, settings.proxmox_token_id, settings.proxmox_token_secret)):
        return None
    return ProxmoxClient(ProxmoxConfig(
        base_url=settings.proxmox_api_url,
        token_id=settings.proxmox_token_id,
        token_secret=settings.proxmox_token_secret,
        verify_ssl=settings.proxmox_verify_ssl,
    ))
