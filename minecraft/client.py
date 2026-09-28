from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class PterodactylError(RuntimeError):
    pass


@dataclass(frozen=True)
class PterodactylConfig:
    base_url: str
    api_key: str
    verify_ssl: bool = True


class PterodactylClient:
    def __init__(self, config: PterodactylConfig):
        self.config = config
        self.headers = {
            "Authorization": "Bearer " + config.api_key,
            "Accept": "Application/vnd.pterodactyl.v1+json",
            "Content-Type": "application/json",
        }

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        async with httpx.AsyncClient(verify=self.config.verify_ssl, timeout=30) as client:
            response = await client.request(
                method,
                self.config.base_url.rstrip("/") + "/api/application/" + path.lstrip("/"),
                headers=self.headers,
                **kwargs,
            )
        if response.status_code >= 400:
            raise PterodactylError("Pterodactyl HTTP %s: %s" % (response.status_code, response.text[:500]))
        return response.json()

    async def create_server(
        self,
        name: str,
        user_id: int,
        nest_id: int,
        egg_id: int,
        docker_image: str,
        startup: str,
        memory: int,
        disk: int,
        cpu: int,
        location_id: int,
        environment: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "name": name,
            "user": user_id,
            "nest": nest_id,
            "egg": egg_id,
            "docker_image": docker_image,
            "startup": startup,
            "environment": environment or {},
            "limits": {"memory": memory, "swap": 0, "disk": disk, "io": 500, "cpu": cpu},
            "feature_limits": {"databases": 1, "allocations": 1, "backups": 2},
            "deploy": {"locations": [location_id], "port_range": [], "dedicated_ip": False},
            "start_on_completion": True,
        }
        return await self.request("POST", "servers", json=payload)

    async def suspend(self, server_id: str) -> Any:
        return await self.request("POST", "servers/%s/suspend" % server_id)

    async def unsuspend(self, server_id: str) -> Any:
        return await self.request("POST", "servers/%s/unsuspend" % server_id)

    async def delete(self, server_id: str, force: bool = False) -> Any:
        return await self.request("DELETE", "servers/%s%s" % (server_id, "?force=true" if force else ""))

    async def details(self, server_id: str) -> Any:
        return await self.request("GET", "servers/%s" % server_id)
