import asyncio

from proxmox.client import ProxmoxClient, ProxmoxConfig, ProxmoxConfigurationError


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
    assert 'host.docker.internal:host-gateway' in compose


def test_database_initializes_and_writes(tmp_path):
    from core.database import Database

    async def run():
        db = Database(str(tmp_path / "helzerx.db"))
        await db.initialize()
        await db.execute(
            "CREATE TABLE IF NOT EXISTS _write_test (id INTEGER PRIMARY KEY, value TEXT)"
        )
        await db.execute("INSERT INTO _write_test(value) VALUES(?)", ("ok",))
        row = await db.fetchone("SELECT value FROM _write_test WHERE id=1")
        assert row["value"] == "ok"

    asyncio.run(run())


def test_lxc_clone_acl_failure_is_configuration_error():
    client = ProxmoxClient(
        ProxmoxConfig(
            base_url="https://pve.example:8006",
            token_id="user@pam!bot",
            token_secret="secret",
        )
    )

    async def fake_request(*args, **kwargs):
        raise ProxmoxConfigurationError(
            "Proxmox API permission denied: Permission check failed (/vms/9000, VM.Clone)"
        )

    client.request = fake_request

    async def run():
        try:
            await client.clone_container("pve01", 9000, 101, "hx-test")
        except ProxmoxConfigurationError as exc:
            assert "VM.Clone" in str(exc)
            assert "/vms/9000" in str(exc)
        else:
            raise AssertionError("Expected ProxmoxConfigurationError")

    asyncio.run(run())


def test_lxc_clone_full_clone_sends_storage():
    client = ProxmoxClient(
        ProxmoxConfig(
            base_url="https://pve.example:8006",
            token_id="user@pam!bot",
            token_secret="secret",
        )
    )
    calls = []

    async def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"data": "UPID:test"}

    client.request = fake_request

    async def run():
        result = await client.clone_container("pve01", 9000, 101, "hx-test", "local-lvm")
        assert result["data"] == "UPID:test"
        assert calls[0][2]["full"] == 1
        assert calls[0][2]["storage"] == "local-lvm"

    asyncio.run(run())


def test_next_vmid_skips_reserved_provisioning_ids():
    client = ProxmoxClient(
        ProxmoxConfig(
            base_url="https://pve.example:8006",
            token_id="user@pam!bot",
            token_secret="secret",
        )
    )

    async def fake_resources():
        return [
            {"type": "lxc", "vmid": 100},
            {"type": "lxc", "vmid": 101},
        ]

    client.cluster_resources = fake_resources
    assert asyncio.run(client.next_vmid({102, 103})) == 104


def test_wait_for_task_accepts_proxmox_warning(monkeypatch):
    client = ProxmoxClient(
        ProxmoxConfig(
            base_url="https://pve.example:8006",
            token_id="user@pam!bot",
            token_secret="secret",
        )
    )

    async def fake_request(method, path, **kwargs):
        return {"status": "stopped", "exitstatus": "WARNINGS: 1"}

    monkeypatch.setattr(client, "request", fake_request)
    result = asyncio.run(client.wait_for_task("node1", "UPID:test"))
    assert result["exitstatus"] == "WARNINGS: 1"


def test_lxc_clone_password_is_sent_to_clone_endpoint():
    client = ProxmoxClient(
        ProxmoxConfig(
            base_url="https://pve.example:8006",
            token_id="user@pam!bot",
            token_secret="secret",
        )
    )
    calls = []

    async def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"data": "UPID:test"}

    client.request = fake_request

    async def run():
        await client.clone_container(
            "pve01", 9000, 101, "hx-test", "local", True, "Generated-Password-123!"
        )
        assert calls[0][2]["password"] == "Generated-Password-123!"

    asyncio.run(run())


def test_qemu_clone_and_wait_waits_for_task(monkeypatch):
    client = ProxmoxClient(
        ProxmoxConfig(
            base_url="https://pve.example:8006",
            token_id="user@pam!bot",
            token_secret="secret",
        )
    )

    async def fake_clone(*args, **kwargs):
        return {"data": "UPID:test"}

    waited = []

    async def fake_wait(node, upid, *args, **kwargs):
        waited.append((node, upid))
        return {"status": "stopped", "exitstatus": "OK"}

    monkeypatch.setattr(client, "clone_vm", fake_clone)
    monkeypatch.setattr(client, "wait_for_task", fake_wait)

    result = asyncio.run(
        client.clone_vm_and_wait("pve01", 9000, 101, "hx-test", True, "local")
    )

    assert result["data"] == "UPID:test"
    assert waited == [("pve01", "UPID:test")]
