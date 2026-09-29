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


def test_deliver_private_credentials_falls_back_to_ephemeral(monkeypatch):
    class FakeForbidden(Exception):
        pass

    class FakeUser:
        async def send(self, view):
            raise FakeForbidden()

    class FakeResponse:
        def __init__(self):
            self.calls = []

        async def send_message(self, view, ephemeral):
            self.calls.append((view, ephemeral))

    class FakeInteraction:
        def __init__(self):
            self.user = FakeUser()
            self.response = FakeResponse()

    monkeypatch.setattr(vps_commands.discord, "Forbidden", FakeForbidden)

    interaction = FakeInteraction()
    view = object()
    result = asyncio.run(vps_commands.deliver_private_credentials(interaction, view))

    assert result == "ephemeral"
    assert interaction.response.calls == [(view, True)]



def test_create_panel_user_uses_vm_scoped_acl(monkeypatch):
    calls = []

    class FakeExecutor:
        def __init__(self, settings):
            pass

        def _create_panel_user(self, vmid, username, password):
            calls.append((vmid, username, password))

    import proxmox.host_exec as host_exec
    executor = object.__new__(FakeExecutor)
    executor._create_panel_user(9023, "hxvps9023", "Panel-Secret-123!")

    assert calls == [(9023, "hxvps9023", "Panel-Secret-123!")]
