from hosting.os_options import available_os_options, resolve_os_template


def test_debian_is_available_by_default():
    options = available_os_options({"PROXMOX_TEMPLATE_CTID": "9000"})
    assert options == [("debian12", "Debian 12", 9000)]


def test_configured_os_options_are_returned_in_stable_order():
    env = {
        "PROXMOX_TEMPLATE_CTID": "9000",
        "PROXMOX_UBUNTU_2204_TEMPLATE_CTID": "9001",
        "PROXMOX_UBUNTU_2404_TEMPLATE_CTID": "9002",
        "PROXMOX_ALMALINUX_9_TEMPLATE_CTID": "9003",
    }
    assert available_os_options(env) == [
        ("debian12", "Debian 12", 9000),
        ("ubuntu2204", "Ubuntu 22.04", 9001),
        ("ubuntu2404", "Ubuntu 24.04", 9002),
        ("almalinux9", "AlmaLinux 9", 9003),
    ]


def test_resolve_os_template_rejects_unconfigured_os():
    try:
        resolve_os_template("ubuntu2404", {"PROXMOX_TEMPLATE_CTID": "9000"})
    except ValueError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("Expected unconfigured OS to be rejected")
