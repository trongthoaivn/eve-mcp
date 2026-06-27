"""
remote_controller.py
---------------------
FastMCP controller that registers SSH/Netmiko tools.

Each tool opens a fresh SSH connection, runs the requested command(s),
then closes the connection — no persistent sessions are maintained.

Tool groups
-----------
  SSH Exec   : ssh_run_command, ssh_run_commands
  SSH Config : ssh_configure
"""

from __future__ import annotations

from typing import Dict, List, Optional

import services.remote_service as svc
from utilities.sdk_helpers import wrap_errors


def register(mcp):
    """Register all Netmiko SSH tools onto the given FastMCP instance.

    :param mcp: FastMCP application instance
    """

    # -----------------------------------------------------------------------
    # SSH – Exec mode (show / display commands)
    # -----------------------------------------------------------------------

    @mcp.tool()
    def ssh_run_command(
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
        """SSH into a network device and run a single exec-mode command.

        Returns the raw text output (or a TextFSM-parsed structure when
        ``use_textfsm=True`` and an NTC template exists for the command).

        :param host:          Device IP address or hostname
        :param username:      SSH username
        :param password:      SSH password
        :param command:       Command to execute, e.g. 'show ip interface brief'
        :param device_type:   Netmiko platform string (default: 'cisco_ios').
                              Common values: cisco_ios, cisco_nxos, cisco_xr,
                              arista_eos, juniper_junos, linux, huawei
        :param port:          SSH port (default: 22)
        :param secret:        Enable / privilege-escalation secret (Cisco)
        :param timeout:       Command output timeout in seconds (default: 30)
        :param conn_timeout:  TCP connection timeout in seconds (default: 10)
        :param ssh_strict:    Enforce strict SSH host-key checking (default: False)
        :param expect_string: Regex to wait for after sending the command
        :param use_textfsm:   Parse output with TextFSM / NTC templates
        """
        return wrap_errors(
            svc.run_command,
            host, username, password, command,
            device_type, port, secret, timeout, conn_timeout, ssh_strict,
            expect_string, use_textfsm,
        )

    @mcp.tool()
    def ssh_run_commands(
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
        """SSH into a network device and run multiple exec-mode commands.

        Opens a single SSH connection, executes every command in order,
        then closes. Returns a list of ``{command, output}`` pairs.

        :param host:         Device IP address or hostname
        :param username:     SSH username
        :param password:     SSH password
        :param commands:     Ordered list of commands to run
        :param device_type:  Netmiko platform string (default: 'cisco_ios')
        :param port:         SSH port (default: 22)
        :param secret:       Enable / privilege-escalation secret (Cisco)
        :param timeout:      Command output timeout in seconds (default: 30)
        :param conn_timeout: TCP connection timeout in seconds (default: 10)
        :param ssh_strict:   Enforce strict SSH host-key checking (default: False)
        """
        return wrap_errors(
            svc.run_commands,
            host, username, password, commands,
            device_type, port, secret, timeout, conn_timeout, ssh_strict,
        )

    # -----------------------------------------------------------------------
    # SSH – Configuration mode
    # -----------------------------------------------------------------------

    @mcp.tool()
    def ssh_configure(
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
        """SSH into a network device and push configuration commands.

        Enters configuration mode automatically, sends all commands, exits
        config mode, and optionally writes the running config to startup.

        :param host:         Device IP address or hostname
        :param username:     SSH username
        :param password:     SSH password
        :param commands:     Configuration commands (do NOT include 'conf t' / 'end')
        :param device_type:  Netmiko platform string (default: 'cisco_ios')
        :param port:         SSH port (default: 22)
        :param secret:       Enable / privilege-escalation secret (Cisco)
        :param timeout:      Command output timeout in seconds (default: 60)
        :param conn_timeout: TCP connection timeout in seconds (default: 10)
        :param ssh_strict:   Enforce strict SSH host-key checking (default: False)
        :param save_config:  Write running-config to startup after applying changes
        """
        return wrap_errors(
            svc.run_config_commands,
            host, username, password, commands,
            device_type, port, secret, timeout, conn_timeout, ssh_strict,
            save_config,
        )
