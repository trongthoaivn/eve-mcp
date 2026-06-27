"""
remote_service.py
-----------------
Service layer that uses Netmiko to SSH into network devices and execute
show / configuration commands.

Design decisions
----------------
- Each call opens a fresh SSH connection, runs commands, then closes.
  This avoids persistent-connection management and works reliably with
  devices that limit concurrent sessions.
- Three public entry points cover 99% of automation needs:
    run_command()        – single show/exec command
    run_commands()       – list of show/exec commands, results keyed by command
    run_config_commands() – push config-mode commands (optionally save)
- All exceptions are surfaced to the caller (the controller's wrap_errors
  will convert them to {"error": "..."} for the MCP client).

Supported device_type values (Netmiko names):
    cisco_ios, cisco_nxos, cisco_xr, cisco_asa,
    arista_eos, juniper_junos, linux, paloalto_panos,
    huawei, mikrotik_routeros, ... (see Netmiko docs for full list)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from netmiko import ConnectHandler
from netmiko.exceptions import (
    NetmikoAuthenticationException,
    NetmikoTimeoutException,
)

_logger = logging.getLogger("eve_mcp")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_device_params(
    host: str,
    username: str,
    password: str,
    device_type: str,
    port: int,
    secret: str,
    timeout: int,
    conn_timeout: int,
    ssh_strict: bool,
) -> Dict[str, Any]:
    """Assemble the Netmiko device dictionary."""
    params: Dict[str, Any] = {
        "device_type": device_type,
        "host": host,
        "username": username,
        "password": password,
        "port": port,
        "timeout": timeout,
        "conn_timeout": conn_timeout,
        "ssh_strict": ssh_strict,
    }
    if secret:
        params["secret"] = secret
    return params


def _prepare_cisco_session(conn: Any, device_type: str) -> None:
    """Prepares Cisco sessions by clearing buffer and disabling console logging

    so that syslog messages or startup output does not corrupt prompt detection.
    """
    dev_type_lower = device_type.lower()
    if "cisco" not in dev_type_lower:
        return

    _logger.debug("Preparing Cisco session to bypass EULA and disable console logging.")
    try:
        # Load commands from services/command/cisco_init_commands.txt
        current_dir = os.path.dirname(os.path.abspath(__file__))
        commands_file = os.path.join(current_dir, "command", "cisco_init_commands.txt")
        init_cmds = []
        try:
            if os.path.exists(commands_file):
                with open(commands_file, "r", encoding="utf-8") as f:
                    init_cmds = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        except Exception as read_err:
            _logger.warning("Could not read Cisco init commands file: %s", read_err)

        if not init_cmds:
            init_cmds = ["no logging console", "line con 0", "logging synchronous"]

        # Clear buffer and send carriage returns to clear any pending syslog output
        conn.clear_buffer()
        for _ in range(3):
            conn.write_channel("\n")
            time.sleep(0.2)
        conn.clear_buffer()

        # Try to execute config commands to disable console logging.
        # This prevents incoming syslog messages from breaking prompts.
        try:
            conn.config_mode()
            conn.send_config_set(init_cmds)
            conn.exit_config_mode()
        except Exception as e:
            _logger.warning("Standard config_mode failed: %s. Trying manual/timing fallback.", e)
            conn.clear_buffer()
            conn.send_command_timing("configure terminal")
            for cmd in init_cmds:
                conn.send_command_timing(cmd)
            conn.send_command_timing("end")
            conn.clear_buffer()
    except Exception as exc:
        _logger.warning("Failed to prepare Cisco session: %s. Proceeding anyway.", exc)


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

def run_command(
    host: str,
    username: str,
    password: str,
    command: str,
    device_type: str = "cisco_ios",
    port: int = 22,
    secret: str = "",
    timeout: int = 30,
    conn_timeout: int = 10,
    ssh_strict: bool = False,
    expect_string: Optional[str] = None,
    use_textfsm: bool = False,
) -> Dict:
    """SSH into a device and execute a single show / exec-mode command.

    :param host:         Device IP address or hostname
    :param username:     SSH username
    :param password:     SSH password
    :param command:      Command to run (e.g. 'show ip interface brief')
    :param device_type:  Netmiko device type (default: 'cisco_ios')
    :param port:         SSH port (default: 22)
    :param secret:       Enable secret for privilege escalation (Cisco)
    :param timeout:      Command timeout in seconds (default: 30)
    :param conn_timeout: Connection timeout in seconds (default: 10)
    :param ssh_strict:   Enforce strict SSH host-key checking (default: False)
    :param expect_string: Optional regex to wait for after sending command
    :param use_textfsm:  Parse output with TextFSM/NTC templates if True
    :returns: Dict with 'host', 'command', and 'output' keys.
    """
    params = _build_device_params(
        host, username, password, device_type,
        port, secret, timeout, conn_timeout, ssh_strict,
    )

    _logger.info("SSH run_command: %s@%s:%s -> %r", username, host, port, command)
    try:
        with ConnectHandler(**params) as conn:
            if secret:
                conn.enable()
            _prepare_cisco_session(conn, device_type)
            kwargs: Dict[str, Any] = {"command_string": command}
            if expect_string is not None:
                kwargs["expect_string"] = expect_string
            if use_textfsm:
                kwargs["use_textfsm"] = True
            output = conn.send_command(**kwargs)
    except NetmikoAuthenticationException as exc:
        _logger.error("SSH auth failed for %s@%s: %s", username, host, exc)
        raise
    except NetmikoTimeoutException as exc:
        _logger.error("SSH timeout connecting to %s: %s", host, exc)
        raise

    _logger.debug("SSH run_command done: %s@%s", username, host)
    return {
        "host": host,
        "device_type": device_type,
        "command": command,
        "output": output,
    }


def run_commands(
    host: str,
    username: str,
    password: str,
    commands: List[str],
    device_type: str = "cisco_ios",
    port: int = 22,
    secret: str = "",
    timeout: int = 30,
    conn_timeout: int = 10,
    ssh_strict: bool = False,
) -> Dict:
    """SSH into a device and execute multiple show / exec-mode commands.

    Opens a single SSH connection and runs all commands sequentially,
    then closes the connection.

    :param host:         Device IP address or hostname
    :param username:     SSH username
    :param password:     SSH password
    :param commands:     List of commands to run
    :param device_type:  Netmiko device type (default: 'cisco_ios')
    :param port:         SSH port (default: 22)
    :param secret:       Enable secret for privilege escalation (Cisco)
    :param timeout:      Command timeout in seconds (default: 30)
    :param conn_timeout: Connection timeout in seconds (default: 10)
    :param ssh_strict:   Enforce strict SSH host-key checking (default: False)
    :returns: Dict with 'host', 'results' (list of {command, output}) keys.
    """
    params = _build_device_params(
        host, username, password, device_type,
        port, secret, timeout, conn_timeout, ssh_strict,
    )

    _logger.info(
        "SSH run_commands: %s@%s:%s -> %d commands",
        username, host, port, len(commands),
    )
    results = []
    try:
        with ConnectHandler(**params) as conn:
            if secret:
                conn.enable()
            _prepare_cisco_session(conn, device_type)
            for cmd in commands:
                _logger.debug("SSH send: %r", cmd)
                output = conn.send_command(command_string=cmd)
                results.append({"command": cmd, "output": output})
    except NetmikoAuthenticationException as exc:
        _logger.error("SSH auth failed for %s@%s: %s", username, host, exc)
        raise
    except NetmikoTimeoutException as exc:
        _logger.error("SSH timeout connecting to %s: %s", host, exc)
        raise

    _logger.debug("SSH run_commands done: %s@%s", username, host)
    return {
        "host": host,
        "device_type": device_type,
        "results": results,
    }


def run_config_commands(
    host: str,
    username: str,
    password: str,
    commands: List[str],
    device_type: str = "cisco_ios",
    port: int = 22,
    secret: str = "",
    timeout: int = 60,
    conn_timeout: int = 10,
    ssh_strict: bool = False,
    save_config: bool = False,
) -> Dict:
    """SSH into a device and push configuration-mode commands.

    Enters config mode, sends all commands, exits config mode, and
    optionally saves the running config to startup.

    :param host:         Device IP address or hostname
    :param username:     SSH username
    :param password:     SSH password
    :param commands:     List of configuration commands (no 'conf t' needed)
    :param device_type:  Netmiko device type (default: 'cisco_ios')
    :param port:         SSH port (default: 22)
    :param secret:       Enable secret for privilege escalation (Cisco)
    :param timeout:      Command timeout in seconds (default: 60)
    :param conn_timeout: Connection timeout in seconds (default: 10)
    :param ssh_strict:   Enforce strict SSH host-key checking (default: False)
    :param save_config:  Write running-config to startup after changes (default: False)
    :returns: Dict with 'host', 'commands', 'config_output', and 'saved' keys.
    """
    params = _build_device_params(
        host, username, password, device_type,
        port, secret, timeout, conn_timeout, ssh_strict,
    )

    _logger.info(
        "SSH run_config_commands: %s@%s:%s -> %d config commands (save=%s)",
        username, host, port, len(commands), save_config,
    )
    try:
        with ConnectHandler(**params) as conn:
            if secret:
                conn.enable()
            _prepare_cisco_session(conn, device_type)
            config_output = conn.send_config_set(commands)
            saved = False
            if save_config:
                conn.save_config()
                saved = True
                _logger.info("Config saved on %s", host)
    except NetmikoAuthenticationException as exc:
        _logger.error("SSH auth failed for %s@%s: %s", username, host, exc)
        raise
    except NetmikoTimeoutException as exc:
        _logger.error("SSH timeout connecting to %s: %s", host, exc)
        raise

    _logger.debug("SSH run_config_commands done: %s@%s", username, host)
    return {
        "host": host,
        "device_type": device_type,
        "commands": commands,
        "config_output": config_output,
        "saved": saved,
    }
