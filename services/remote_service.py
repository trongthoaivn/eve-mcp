"""
remote_service.py
-----------------
Service layer that uses Netmiko to SSH into network devices and execute
show / configuration commands.  Also provides a raw-socket console bypass
utility for devices that are stuck on the Cisco initial configuration dialog.

Design decisions
----------------
- Each call opens a fresh SSH connection, runs commands, then closes.
  This avoids persistent-connection management and works reliably with
  devices that limit concurrent sessions.
- Three public entry points cover 99% of automation needs:
    run_command()          – single show/exec command
    run_commands()         – list of show/exec commands, results keyed by command
    run_config_commands()  – push config-mode commands (optionally save)
    bypass_console_dialog()– raw-socket bypass for Cisco initial config dialog
- All exceptions are surfaced to the caller (the controller's wrap_errors
  will convert them to {"error": "..."} for the MCP client).

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
import socket
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
    """Prepare a Cisco SSH/Telnet session before sending real commands.

    Handles three phases in sequence — all wrapped in a broad try/except so
    any unexpected failure is logged as a warning and execution continues:

    **Phase 1 – Bypass initial configuration dialog**
        Freshly booted Cisco devices may present a setup wizard prompt
        (``Would you like to enter the initial configuration dialog?``).
        The function reads the channel buffer and, if such a pattern is
        detected, sends ``no`` followed by several newlines to clear it.

    **Phase 2 – Normalise CLI mode (send ``end``)**
        After bypassing (or if no dialog was present), ``end`` is sent to
        exit any lingering sub-configuration mode and return the device to
        Privileged EXEC.  ``end`` is a no-op when already at EXEC level,
        so this is always safe to call.

    **Phase 3 – Disable console logging**
        Pushes a set of init commands (loaded from
        ``services/command/cisco_init_commands.txt`` if present) to prevent
        incoming syslog messages from corrupting prompt detection.
    """
    dev_type_lower = device_type.lower()
    if "cisco" not in dev_type_lower:
        return

    _logger.debug("Preparing Cisco session (bypass dialog → normalise mode → init cmds).")

    try:
        # -------------------------------------------------------------------
        # Phase 1: Bypass initial configuration dialog
        # -------------------------------------------------------------------
        _INIT_DIALOG_PATTERNS = [
            "would you like to enter the initial configuration dialog",
            "would you like to enter basic management setup",
            "continue with configuration dialog",
            "would you like to terminate autoinstall",
        ]

        # Wake up the console and flush any pending output
        conn.clear_buffer()
        for _ in range(3):
            conn.write_channel("\n")
            time.sleep(0.3)

        buffer = conn.read_channel()

        if any(p in buffer.lower() for p in _INIT_DIALOG_PATTERNS):
            _logger.info(
                "Initial configuration dialog detected — sending 'no' to bypass."
            )
            conn.write_channel("no\n")
            time.sleep(2)
            # Some devices follow up with a secondary prompt; flush it
            for _ in range(5):
                conn.write_channel("\n")
                time.sleep(0.5)
            conn.clear_buffer()
            _logger.info("Initial configuration dialog bypassed.")
        else:
            # No dialog — still flush the wake-up output
            conn.clear_buffer()

        # -------------------------------------------------------------------
        # Phase 2: Normalise CLI mode — always send 'end'
        # Exits any sub-config mode safely; no-op at EXEC level.
        # -------------------------------------------------------------------
        _logger.debug("Sending 'end' to normalise CLI mode.")
        conn.write_channel("end\n")
        time.sleep(0.5)
        conn.clear_buffer()

        # -------------------------------------------------------------------
        # Phase 3: Disable console logging (init commands)
        # -------------------------------------------------------------------
        current_dir = os.path.dirname(os.path.abspath(__file__))
        commands_file = os.path.join(current_dir, "command", "cisco_init_commands.txt")
        init_cmds: list = []
        try:
            if os.path.exists(commands_file):
                with open(commands_file, "r", encoding="utf-8") as f:
                    init_cmds = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.startswith("#")
                    ]
        except Exception as read_err:
            _logger.warning("Could not read Cisco init commands file: %s", read_err)

        if not init_cmds:
            init_cmds = ["no logging console", "line con 0", "logging synchronous"]

        try:
            conn.config_mode()
            conn.send_config_set(init_cmds)
            conn.exit_config_mode()
        except Exception as cfg_err:
            _logger.warning(
                "Standard config_mode failed: %s — trying timing fallback.", cfg_err
            )
            conn.clear_buffer()
            conn.send_command_timing("configure terminal")
            for cmd in init_cmds:
                conn.send_command_timing(cmd)
            conn.send_command_timing("end")
            conn.clear_buffer()

    except Exception as exc:
        _logger.warning(
            "Failed to prepare Cisco session: %s — proceeding anyway.", exc
        )


# ---------------------------------------------------------------------------
# Raw-socket console bypass
# ---------------------------------------------------------------------------

def bypass_console_dialog(
    host: str,
    port: int,
    conn_timeout: int = 10,
    read_timeout: int = 5,
) -> Dict:
    """Connect to a device console via raw TCP socket and bypass the Cisco
    initial configuration dialog.

    Use this function **before** attempting any Netmiko connection when a
    freshly booted Cisco device is stuck on the prompt::

        Would you like to enter the initial configuration dialog? [yes/no]:

    At that point Netmiko cannot establish a session because it cannot match
    its expected prompt pattern.  This function connects via a bare TCP socket
    (no SSH/Telnet negotiation overhead), reads whatever is in the buffer,
    sends ``no`` to dismiss the dialog, then closes the socket.

    After calling this function the device typically needs **3 to 5 minutes**
    to finish booting before normal Netmiko connections will succeed.

    :param host:         Device IP address or hostname (EVE-NG server address
                         for console-port forwarding setups).
    :param port:         Console TCP port (e.g. the EVE-NG forwarded port for
                         the node's console interface).
    :param conn_timeout: TCP connect timeout in seconds (default: 10).
    :param read_timeout: Socket read timeout in seconds (default: 5).
    :returns: Dict with ``status`` and ``message`` keys.
    """
    _logger.info(
        "bypass_console_dialog: connecting to %s:%s via raw socket", host, port
    )
    try:
        with socket.create_connection((host, port), timeout=conn_timeout) as sock:
            sock.settimeout(read_timeout)

            # Give the device banner a moment to print
            time.sleep(2)

            # Read initial buffer (may contain the dialog prompt)
            try:
                banner = sock.recv(4096).decode("utf-8", errors="ignore")
                _logger.debug("Console banner: %r", banner)
            except socket.timeout:
                banner = ""

            # Send 'no' to dismiss the initial configuration dialog
            sock.sendall(b"no\r\n")
            time.sleep(1)

            # Flush any follow-up prompts (some platforms ask again)
            sock.sendall(b"\r\n\r\n\r\n")
            time.sleep(1)

            # Drain the response
            try:
                response = sock.recv(4096).decode("utf-8", errors="ignore")
                _logger.debug("Console response after bypass: %r", response)
            except socket.timeout:
                response = ""

        _logger.info("bypass_console_dialog: bypass command sent to %s:%s", host, port)
        return {
            "status": "success",
            "host": host,
            "port": port,
            "message": (
                "Bypass command sent. Wait 3-5 minutes before attempting "
                "further Netmiko connections."
            ),
        }

    except Exception as exc:  # noqa: BLE001
        _logger.error(
            "bypass_console_dialog failed for %s:%s – %s", host, port, exc
        )
        raise




# ---------------------------------------------------------------------------
# Auto-bypass helpers  (raw socket bypass + Netmiko retry in one call)
# ---------------------------------------------------------------------------

def _with_auto_bypass(host, console_port, conn_timeout, bypass_wait, poll_interval, executor):
    """Internal: try executor(), bypass dialog on failure, poll until device ready.

    Sequence:
    1. executor() - return immediately if Netmiko connects.
    2. Any failure -> bypass_console_dialog() sends "no" via raw TCP.
    3. Retry executor() every poll_interval s for up to bypass_wait s total.
    4. Raise TimeoutError if device never becomes ready.
    """
    # Phase 1 - direct Netmiko attempt
    try:
        _logger.info("auto_bypass: trying direct connection to %s", host)
        return executor()
    except Exception as direct_err:
        _logger.info(
            "auto_bypass: direct connection failed (%s) - bypassing console port %s",
            direct_err, console_port,
        )

    # Phase 2 - raw-socket bypass
    bypass_console_dialog(host, console_port, conn_timeout=conn_timeout)

    # Phase 3 - poll until Netmiko can connect
    deadline = time.monotonic() + bypass_wait
    attempt = 0
    while time.monotonic() < deadline:
        remaining = int(deadline - time.monotonic())
        attempt += 1
        sleep_for = min(poll_interval, remaining)
        _logger.info(
            "auto_bypass: waiting %ds then retrying (attempt=%d, remaining=%ds)",
            sleep_for, attempt, remaining,
        )
        time.sleep(sleep_for)
        try:
            return executor()
        except Exception as retry_err:
            _logger.debug("auto_bypass: not ready (attempt=%d): %s", attempt, retry_err)

    raise TimeoutError(
        f"Device {host}:{console_port} did not become ready within {bypass_wait}s "
        f"after bypass (tried {attempt} time(s) every {poll_interval}s)."
    )


def bypass_and_run_command(
    host: str,
    console_port: int,
    username: str,
    password: str,
    command: str,
    device_type: str = "cisco_ios",
    ssh_port: int = 22,
    secret: str = "",
    timeout: int = 30,
    conn_timeout: int = 10,
    ssh_strict: bool = False,
    expect_string=None,
    use_textfsm: bool = False,
    bypass_wait: int = 300,
    poll_interval: int = 30,
) -> Dict:
    """Run a single exec-mode command, auto-bypassing Cisco initial config dialog.

    Tries normal Netmiko first; if that fails, sends "no" via raw TCP to
    console_port, then retries every poll_interval s for up to bypass_wait s.

    :param host:          Device IP / hostname for Netmiko.
    :param console_port:  Console TCP port for the raw-socket bypass.
    :param username:      SSH / Telnet username.
    :param password:      SSH / Telnet password.
    :param command:       Exec-mode command to run.
    :param device_type:   Netmiko device type (default: cisco_ios).
    :param ssh_port:      SSH port for Netmiko (default: 22).
    :param secret:        Enable secret for privilege escalation.
    :param timeout:       Command timeout in seconds (default: 30).
    :param conn_timeout:  TCP connection timeout in seconds (default: 10).
    :param ssh_strict:    Enforce strict SSH host-key checking.
    :param expect_string: Regex to wait for after the command.
    :param use_textfsm:   Parse output with TextFSM / NTC templates.
    :param bypass_wait:   Max seconds to wait after bypass (default: 300).
    :param poll_interval: Seconds between Netmiko retries (default: 30).
    """
    def _execute() -> Dict:
        return run_command(
            host, username, password, command,
            device_type, ssh_port, secret, timeout, conn_timeout, ssh_strict,
            expect_string, use_textfsm,
        )
    return _with_auto_bypass(host, console_port, conn_timeout, bypass_wait, poll_interval, _execute)


def bypass_and_run_commands(
    host: str,
    console_port: int,
    username: str,
    password: str,
    commands: List[str],
    device_type: str = "cisco_ios",
    ssh_port: int = 22,
    secret: str = "",
    timeout: int = 30,
    conn_timeout: int = 10,
    ssh_strict: bool = False,
    bypass_wait: int = 300,
    poll_interval: int = 30,
) -> Dict:
    """Run multiple exec-mode commands, auto-bypassing Cisco initial config dialog.

    Same bypass-and-retry logic as bypass_and_run_command but sends a list of
    commands over a single Netmiko session.

    :param host:          Device IP / hostname for Netmiko.
    :param console_port:  Console TCP port for the raw-socket bypass.
    :param username:      SSH / Telnet username.
    :param password:      SSH / Telnet password.
    :param commands:      Ordered list of exec-mode commands.
    :param device_type:   Netmiko device type (default: cisco_ios).
    :param ssh_port:      SSH port for Netmiko (default: 22).
    :param secret:        Enable secret.
    :param timeout:       Command timeout in seconds (default: 30).
    :param conn_timeout:  TCP connection timeout in seconds (default: 10).
    :param ssh_strict:    Enforce strict SSH host-key checking.
    :param bypass_wait:   Max seconds to wait after bypass (default: 300).
    :param poll_interval: Seconds between Netmiko retries (default: 30).
    """
    def _execute() -> Dict:
        return run_commands(
            host, username, password, commands,
            device_type, ssh_port, secret, timeout, conn_timeout, ssh_strict,
        )
    return _with_auto_bypass(host, console_port, conn_timeout, bypass_wait, poll_interval, _execute)


def bypass_and_configure(
    host: str,
    console_port: int,
    username: str,
    password: str,
    commands: List[str],
    device_type: str = "cisco_ios",
    ssh_port: int = 22,
    secret: str = "",
    timeout: int = 60,
    conn_timeout: int = 10,
    ssh_strict: bool = False,
    save_config: bool = False,
    bypass_wait: int = 300,
    poll_interval: int = 30,
) -> Dict:
    """Push configuration commands, auto-bypassing Cisco initial config dialog.

    Enters config mode, sends all commands, exits, optionally saves. Uses the
    same bypass-and-retry logic as bypass_and_run_command.

    :param host:          Device IP / hostname for Netmiko.
    :param console_port:  Console TCP port for the raw-socket bypass.
    :param username:      SSH / Telnet username.
    :param password:      SSH / Telnet password.
    :param commands:      Config commands (no conf t / end needed).
    :param device_type:   Netmiko device type (default: cisco_ios).
    :param ssh_port:      SSH port for Netmiko (default: 22).
    :param secret:        Enable secret.
    :param timeout:       Command timeout in seconds (default: 60).
    :param conn_timeout:  TCP connection timeout in seconds (default: 10).
    :param ssh_strict:    Enforce strict SSH host-key checking.
    :param save_config:   Write running-config to startup after changes.
    :param bypass_wait:   Max seconds to wait after bypass (default: 300).
    :param poll_interval: Seconds between Netmiko retries (default: 30).
    """
    def _execute() -> Dict:
        return run_config_commands(
            host, username, password, commands,
            device_type, ssh_port, secret, timeout, conn_timeout, ssh_strict,
            save_config,
        )
    return _with_auto_bypass(host, console_port, conn_timeout, bypass_wait, poll_interval, _execute)

# ---------------------------------------------------------------------------
# Public service functions (Netmiko)
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
