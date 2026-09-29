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


def test_lxc_clone_and_wait_does_not_pass_password_to_clone(monkeypatch):
    client = ProxmoxClient(
        ProxmoxConfig(
            base_url="https://pve.example:8006",
            token_id="user@pam!bot",
            token_secret="secret",
        )
    )
    calls = []

    async def fake_clone(*args, **kwargs):
        calls.append((args, kwargs))
        return {"data": "UPID:test"}

    async def fake_wait(node, upid, *args, **kwargs):
        return {"status": "stopped", "exitstatus": "OK"}

    monkeypatch.setattr(client, "clone_container", fake_clone)
    monkeypatch.setattr(client, "wait_for_task", fake_wait)

    result = asyncio.run(
        client.clone_container_and_wait("pve01", 9000, 101, "hx-test", "local-lvm", True)
    )

    assert result["data"] == "UPID:test"
    assert calls == [
        (("pve01", 9000, 101, "hx-test", "local-lvm", True), {})
    ]




def test_proxmox_host_executor_writes_password_to_stdin(monkeypatch):
    from types import SimpleNamespace
    from proxmox.host_exec import ProxmoxHostExecutor

    class FakeChannel:
        def shutdown_write(self):
            pass

        def recv_exit_status(self):
            return 0

    class FakeStream:
        def __init__(self):
            self.channel = FakeChannel()

        def read(self):
            return b""

    class FakeStdin:
        def __init__(self):
            self.writes = []
            self.channel = FakeChannel()

        def write(self, value):
            self.writes.append(value)

        def flush(self):
            pass

    class FakeClient:
        instance = None

        def __init__(self):
            FakeClient.instance = self
            self.stdin = FakeStdin()

        def load_system_host_keys(self):
            pass

        def set_missing_host_key_policy(self, policy):
            pass

        def connect(self, **kwargs):
            self.connect_kwargs = kwargs

        def exec_command(self, command, timeout=None):
            self.command = command
            return self.stdin, FakeStream(), FakeStream()

        def close(self):
            pass

    monkeypatch.setattr("paramiko.SSHClient", FakeClient)
    settings = SimpleNamespace(
        proxmox_ssh_host="host.docker.internal",
        proxmox_ssh_port=22,
        proxmox_ssh_user="root",
        proxmox_ssh_key_file="/run/secrets/key",
        proxmox_ssh_password=None,
        proxmox_ssh_known_hosts=None,
        proxmox_ssh_strict_host_key=False,
    )

    asyncio.run(ProxmoxHostExecutor(settings).set_container_password(9016, "Secret-123!"))

    assert FakeClient.instance.command == "pct exec 9016 -- chpasswd"
    assert FakeClient.instance.stdin.writes == ["root:Secret-123!\n"]


def test_set_container_config_retries_transient_lock():
    client = ProxmoxClient(
        ProxmoxConfig(
            base_url="https://pve.example:8006",
            token_id="user@pam!bot",
            token_secret="secret",
        )
    )
    calls = []

    async def fake_request(method, path, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise ProxmoxError("Proxmox returned HTTP 500: can't lock file '/run/lock/lxc/pve-config-9019.lock' - got timeout")
        return {"data": None}

    client._request_once = fake_request
    result = asyncio.run(
        client.set_container_config("pve01", 9019, {"memory": 512})
    )

    assert result == {"data": None}
    assert len(calls) == 3


def test_provisioning_does_not_start_lxc_twice():
    source = open("hosting/provisioner.py", encoding="utf-8").read()
    assert "if settings.proxmox_start and not resource_started:" in source
