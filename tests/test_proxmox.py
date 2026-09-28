import asyncio

from proxmox.client import ProxmoxClient, ProxmoxConfig


def test_proxmox_url_normalization():
    client = ProxmoxClient(
        ProxmoxConfig(
            base_url="https://pve.example:8006/api2/json/",
            token_id="user@pam!bot",
            token_secret="secret",
        )
    )
    assert client._url("cluster/resources") == "https://pve.example:8006/api2/json/cluster/resources"


def test_next_vmid_uses_cluster_resources():
    client = ProxmoxClient(
        ProxmoxConfig(
            base_url="https://pve.example:8006",
            token_id="user@pam!bot",
            token_secret="secret",
        )
    )

    async def fake_resources():
        return [
            {"type": "node", "node": "pve01"},
            {"type": "lxc", "vmid": 100},
            {"type": "qemu", "vmid": 101},
            {"type": "lxc", "vmid": 103},
        ]

    client.cluster_resources = fake_resources
    assert asyncio.run(client.next_vmid()) == 104


def test_docker_compose_runtime_configuration():
    compose = open("docker-compose.yml", encoding="utf-8").read()
    assert "apparmor=unconfined" in compose
    assert "security_opt:" in compose
    assert "user: root" in compose
