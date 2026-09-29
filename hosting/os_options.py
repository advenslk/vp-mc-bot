from __future__ import annotations


OS_ENV_KEYS = (
    ("debian12", "Debian 12", "PROXMOX_TEMPLATE_CTID"),
    ("ubuntu2204", "Ubuntu 22.04", "PROXMOX_UBUNTU_2204_TEMPLATE_CTID"),
    ("ubuntu2404", "Ubuntu 24.04", "PROXMOX_UBUNTU_2404_TEMPLATE_CTID"),
    ("almalinux9", "AlmaLinux 9", "PROXMOX_ALMALINUX_9_TEMPLATE_CTID"),
)


def _template_id(env: dict[str, str], key: str) -> int | None:
    value = str(env.get(key, "")).strip()
    return int(value) if value.isdigit() and int(value) > 0 else None


def available_os_options(env: dict[str, str]) -> list[tuple[str, str, int]]:
    return [
        (os_key, label, template_ctid)
        for os_key, label, env_key in OS_ENV_KEYS
        if (template_ctid := _template_id(env, env_key)) is not None
    ]


def resolve_os_template(os_key: str, env: dict[str, str]) -> int:
    normalized = os_key.strip().lower()
    for key, _label, env_key in OS_ENV_KEYS:
        if key == normalized:
            template_ctid = _template_id(env, env_key)
            if template_ctid is None:
                raise ValueError("OS %s is not configured." % normalized)
            return template_ctid
    raise ValueError("Unknown operating system: %s" % os_key)
