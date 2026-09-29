from __future__ import annotations

import asyncio
import shlex
from pathlib import Path

import paramiko


class ProxmoxHostExecutionError(RuntimeError):
    pass


class ProxmoxHostExecutor:
    """Execute narrowly-scoped LXC password operations on a Proxmox node."""

    def __init__(self, settings):
        self.settings = settings

    def _connect_and_set_password(self, vmid: int, password: str) -> None:
        host = self.settings.proxmox_ssh_host
        if not host:
            raise ProxmoxHostExecutionError(
                "PROXMOX_SSH_HOST is required to set an LXC password. "
                "Proxmox has no REST endpoint for changing an existing LXC password."
            )

        client = paramiko.SSHClient()
        try:
            known_hosts = self.settings.proxmox_ssh_known_hosts
            if known_hosts:
                client.load_host_keys(str(Path(known_hosts).expanduser()))
            elif self.settings.proxmox_ssh_strict_host_key:
                client.load_system_host_keys()

            if self.settings.proxmox_ssh_strict_host_key:
                client.set_missing_host_key_policy(paramiko.RejectPolicy())
            else:
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                "hostname": host,
                "port": self.settings.proxmox_ssh_port,
                "username": self.settings.proxmox_ssh_user,
                "timeout": 15,
                "banner_timeout": 15,
                "auth_timeout": 15,
                "look_for_keys": not bool(self.settings.proxmox_ssh_key_file),
                "allow_agent": not bool(self.settings.proxmox_ssh_key_file),
            }
            if self.settings.proxmox_ssh_key_file:
                connect_kwargs["key_filename"] = str(Path(self.settings.proxmox_ssh_key_file).expanduser())
            elif self.settings.proxmox_ssh_password:
                connect_kwargs["password"] = self.settings.proxmox_ssh_password

            client.connect(**connect_kwargs)

            # chpasswd reads the secret from stdin, so the password is never
            # placed in the remote command line or shell history.
            command = "pct exec %d -- chpasswd" % int(vmid)
            stdin, stdout, stderr = client.exec_command(command, timeout=30)
            stdin.write("root:%s\n" % password)
            stdin.flush()
            stdin.channel.shutdown_write()

            exit_code = stdout.channel.recv_exit_status()
            err = stderr.read().decode("utf-8", "replace").strip()
            if exit_code != 0:
                raise ProxmoxHostExecutionError(
                    "pct exec failed for LXC %s (exit %s): %s" % (vmid, exit_code, err[:500])
                )
        except ProxmoxHostExecutionError:
            raise
        except Exception as exc:
            raise ProxmoxHostExecutionError(
                "Could not execute pct on Proxmox host %s: %s" % (host, exc)
            ) from exc
        finally:
            client.close()

    def _run(self, command: str, timeout: int = 30) -> str:
        host = self.settings.proxmox_ssh_host
        if not host:
            raise ProxmoxHostExecutionError("PROXMOX_SSH_HOST is required for Proxmox host operations.")
        client = paramiko.SSHClient()
        try:
            known_hosts = self.settings.proxmox_ssh_known_hosts
            if known_hosts:
                client.load_host_keys(str(Path(known_hosts).expanduser()))
            elif self.settings.proxmox_ssh_strict_host_key:
                client.load_system_host_keys()
            client.set_missing_host_key_policy(
                paramiko.RejectPolicy() if self.settings.proxmox_ssh_strict_host_key else paramiko.AutoAddPolicy()
            )
            connect_kwargs = {
                "hostname": host,
                "port": self.settings.proxmox_ssh_port,
                "username": self.settings.proxmox_ssh_user,
                "timeout": 15,
                "banner_timeout": 15,
                "auth_timeout": 15,
                "look_for_keys": not bool(self.settings.proxmox_ssh_key_file),
                "allow_agent": not bool(self.settings.proxmox_ssh_key_file),
            }
            if self.settings.proxmox_ssh_key_file:
                connect_kwargs["key_filename"] = str(Path(self.settings.proxmox_ssh_key_file).expanduser())
            elif self.settings.proxmox_ssh_password:
                connect_kwargs["password"] = self.settings.proxmox_ssh_password
            client.connect(**connect_kwargs)
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            err = stderr.read().decode("utf-8", "replace").strip()
            out = stdout.read().decode("utf-8", "replace").strip()
            if exit_code != 0:
                raise ProxmoxHostExecutionError("Proxmox host command failed (exit %s): %s" % (exit_code, err[:500]))
            return out
        except ProxmoxHostExecutionError:
            raise
        except Exception as exc:
            raise ProxmoxHostExecutionError("Could not execute Proxmox host command on %s: %s" % (host, exc)) from exc
        finally:
            client.close()

    def _create_panel_user(self, vmid: int, username: str, password: str) -> None:
        userid = "%s@pve" % username
        quoted_user = shlex.quote(userid)
        quoted_password = shlex.quote(password)
        # The username is deterministic per VMID. Remove a stale account first so
        # a reused VMID can never inherit credentials or ACLs from an old VPS.
        command = (
            "pveum user delete {user} >/dev/null 2>&1 || true; "
            "pveum user add {user} --password {password} --comment {comment}; "
            "pveum acl modify /vms/{vmid} -user {user} -role PVEVMAdmin"
        ).format(
            user=quoted_user,
            password=quoted_password,
            comment=shlex.quote("HelzerX Cloud VPS %s" % int(vmid)),
            vmid=int(vmid),
        )
        self._run(command)

    def _delete_panel_user(self, username: str) -> None:
        userid = username if "@" in username else "%s@pve" % username
        self._run("pveum user delete %s" % shlex.quote(userid))

    async def create_panel_user(self, vmid: int, username: str, password: str) -> None:
        await asyncio.to_thread(self._create_panel_user, int(vmid), username, password)

    async def delete_panel_user(self, username: str) -> None:
        await asyncio.to_thread(self._delete_panel_user, username)

    async def set_container_password(self, vmid: int, password: str) -> None:
        await asyncio.to_thread(self._connect_and_set_password, int(vmid), password)
