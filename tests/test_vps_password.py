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



def test_create_panel_user_scopes_acl_to_vmid(monkeypatch):
    from proxmox.host_exec import ProxmoxHostExecutor

    executor = object.__new__(ProxmoxHostExecutor)
    commands = []
    monkeypatch.setattr(executor, "_run", lambda command: commands.append(command))

    executor._create_panel_user(9023, "hxvps9023", "Panel-Secret-123!")

    assert commands
    command = commands[0]
    assert "hxvps9023@pve" in command
    assert "/vms/9023" in command
    assert "PVEVMAdmin" in command


def test_reset_panel_password_recreates_scoped_user(monkeypatch):
    calls = []

    class FakeExecutor:
        def __init__(self, settings):
            calls.append(("init", settings))

        async def reset_panel_user(self, vmid, username, password):
            calls.append(("reset", vmid, username, password))

    settings = object()
    monkeypatch.setattr(vps_commands, "ProxmoxHostExecutor", FakeExecutor)

    asyncio.run(
        vps_commands.reset_panel_password(
            settings,
            9023,
            "hxvps9023@pve",
            "Panel-Secret-123!",
        )
    )

    assert calls == [
        ("init", settings),
        ("reset", 9023, "hxvps9023@pve", "Panel-Secret-123!"),
    ]
