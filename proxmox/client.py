from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class ProxmoxError(RuntimeError):
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
        return self.config.base_url.rstrip("/") + "/api2/json/" + path.lstrip("/")

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        timeout = kwargs.pop("timeout", 30.0)
        async with httpx.AsyncClient(verify=self.config.verify_ssl, timeout=timeout) as client:
            response = await client.request(method, self._url(path), headers=self.headers, **kwargs)
        if response.status_code >= 400:
            raise ProxmoxError("Proxmox returned HTTP %s: %s" % (response.status_code, response.text[:500]))
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

    async def clone_vm(self, node: str, template_vmid: int, newid: int, name: str, full: bool = True) -> Any:
        return await self.request(
            "POST", "nodes/%s/qemu/%s/clone" % (node, template_vmid),
            newid=newid, name=name, full=1 if full else 0,
        )

    async def set_vm_config(self, node: str, vmid: int, config: dict[str, Any]) -> Any:
        return await self.request("PUT", "nodes/%s/qemu/%s/config" % (node, vmid), **config)

    async def vm_status(self, node: str, vmid: int) -> Any:
        return await self.request("GET", "nodes/%s/qemu/%s/status/current" % (node, vmid))

    async def delete_vm(self, node: str, vmid: int, purge: bool = True) -> Any:
        return await self.request(
            "DELETE", "nodes/%s/qemu/%s" % (node, vmid), purge=1 if purge else 0
        )

    async def next_vmid(self) -> int:
        value = await self.request("GET", "cluster/nextid")
        return int(value)

    async def vm_action(self, node: str, vmid: int, action: str) -> Any:
        if action not in {"start", "stop", "shutdown", "reboot", "reset"}:
            raise ValueError("Unsupported VM action")
        return await self.request("POST", "nodes/%s/qemu/%s/status/%s" % (node, vmid, action))

    async def container_action(self, node: str, vmid: int, action: str) -> Any:
        if action not in {"start", "stop", "shutdown", "reboot"}:
            raise ValueError("Unsupported container action")
        return await self.request("POST", "nodes/%s/lxc/%s/status/%s" % (node, vmid, action))
