import asyncio

import vps_commands


def test_reset_lxc_password_uses_host_executor(monkeypatch):
    calls = []

    class FakeExecutor:
        def __init__(self, settings):
            calls.append(("init", settings))

        async def set_container_password(self, vmid, password):
            calls.append(("set", vmid, password))

    settings = object()
    monkeypatch.setattr(vps_commands, "ProxmoxHostExecutor", FakeExecutor)

    asyncio.run(vps_commands.reset_lxc_password(settings, 9022, "Secret-123!"))

    assert calls == [
        ("init", settings),
        ("set", 9022, "Secret-123!"),
    ]
