"""
remote_controller.py
---------------------
FastMCP controller that registers SSH/Netmiko tools.

Architecture (v2 – async job-based)
------------------------------------
All SSH operations are slow-blocking (Netmiko opens a real TCP/SSH session).
To avoid holding up the MCP event loop, every SSH tool now:

  1. Submits the work to the shared ``job_manager`` as a background asyncio
     task (using ``asyncio.to_thread`` to run the blocking Netmiko call off
     the event loop).
  2. Returns a ``{job_id, job_key, status}`` dict **immediately**.

The caller is expected to:
  - Poll ``ssh_job_status(job_id)`` until the job is in a terminal state.
  - Retrieve the result with ``ssh_job_result(job_id)`` once done.
  - Optionally cancel a running job with ``ssh_cancel_job(job_id)``.

job_key scheme (prevents duplicate sessions to the same host)
--------------------------------------------------------------
  ssh:cmd:{host}   – one ssh_run_command  per host at a time
  ssh:cmds:{host}  – one ssh_run_commands per host at a time
  ssh:cfg:{host}   – one ssh_configure    per host at a time

Tool groups
-----------
  SSH Exec         : ssh_run_command, ssh_run_commands
  SSH Config       : ssh_configure
  Job mgmt         : ssh_job_status, ssh_job_result, ssh_cancel_job
  Bypass + Exec    : ssh_bypass_and_run_command, ssh_bypass_and_run_commands
  Bypass + Config  : ssh_bypass_and_configure
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import services.remote_service as svc
from services.job_manager_service import (
    DuplicateJobError,
    JobCancelledError,
    JobFailedError,
    JobNotDoneError,
    JobTimedOutError,
    ProgressReporter,
    job_manager,
)
from utilities.sdk_helpers import wrap_errors


def register(mcp):
    """Register all Netmiko SSH tools onto the given FastMCP instance."""

    # -----------------------------------------------------------------------
    # SSH – Exec mode (show / display commands)
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def ssh_run_command(
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
        """SSH into a network device and run a single exec-mode command (async).

        The operation is queued as a background job.  The tool returns a
        ``job_id`` immediately; use ``ssh_job_status`` to poll progress and
        ``ssh_job_result`` to retrieve the output once the job finishes.

        :param host:          Device IP address or hostname
        :param username:      SSH username
        :param password:      SSH password
        :param command:       Command to execute, e.g. ``'show ip interface brief'``
        :param device_type:   Netmiko platform string (default: ``'cisco_ios'``).
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
        job_key = f"ssh:cmd:{host}"
        ttl = timeout + conn_timeout + 60  # generous buffer

        async def _task(progress: ProgressReporter) -> Dict:
            await progress(0, f"Connecting to {host}:{port} …")
            result = await asyncio.to_thread(
                svc.run_command,
                host, username, password, command,
                device_type, port, secret, timeout, conn_timeout, ssh_strict,
                expect_string, use_textfsm,
            )
            await progress(100, "Command completed.")
            return result

        try:
            job_id = await job_manager.submit(_task, job_key=job_key, ttl=ttl)
        except DuplicateJobError as exc:
            return {"error": str(exc), "job_key": job_key}

        return {
            "job_id": job_id,
            "job_key": job_key,
            "status": "pending",
            "message": (
                "Job submitted. Poll ssh_job_status(job_id) every 60 s "
                "until status is 'completed', then call ssh_job_result(job_id)."
            ),
        }

    # -----------------------------------------------------------------------

    @mcp.tool()
    async def ssh_run_commands(
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
        """SSH into a network device and run multiple exec-mode commands (async).

        Opens a single SSH connection, executes every command in order,
        then closes.  Returns a ``job_id`` immediately.

        :param host:         Device IP address or hostname
        :param username:     SSH username
        :param password:     SSH password
        :param commands:     Ordered list of commands to run
        :param device_type:  Netmiko platform string (default: ``'cisco_ios'``)
        :param port:         SSH port (default: 22)
        :param secret:       Enable / privilege-escalation secret (Cisco)
        :param timeout:      Command timeout in seconds (default: 30)
        :param conn_timeout: TCP connection timeout in seconds (default: 10)
        :param ssh_strict:   Enforce strict SSH host-key checking (default: False)
        """
        job_key = f"ssh:cmds:{host}"
        ttl = timeout * len(commands) + conn_timeout + 60

        async def _task(progress: ProgressReporter) -> Dict:
            await progress(0, f"Connecting to {host}:{port} ({len(commands)} commands) …")
            result = await asyncio.to_thread(
                svc.run_commands,
                host, username, password, commands,
                device_type, port, secret, timeout, conn_timeout, ssh_strict,
            )
            await progress(100, f"All {len(commands)} commands completed.")
            return result

        try:
            job_id = await job_manager.submit(_task, job_key=job_key, ttl=ttl)
        except DuplicateJobError as exc:
            return {"error": str(exc), "job_key": job_key}

        return {
            "job_id": job_id,
            "job_key": job_key,
            "status": "pending",
            "message": (
                "Job submitted. Poll ssh_job_status(job_id) every 60 s "
                "until status is 'completed', then call ssh_job_result(job_id)."
            ),
        }

    # -----------------------------------------------------------------------
    # SSH – Configuration mode
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def ssh_configure(
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
        """SSH into a network device and push configuration commands (async).

        Enters configuration mode automatically, sends all commands, exits
        config mode, and optionally writes the running config to startup.
        Returns a ``job_id`` immediately.

        :param host:         Device IP address or hostname
        :param username:     SSH username
        :param password:     SSH password
        :param commands:     Configuration commands (do NOT include 'conf t' / 'end')
        :param device_type:  Netmiko platform string (default: ``'cisco_ios'``)
        :param port:         SSH port (default: 22)
        :param secret:       Enable / privilege-escalation secret (Cisco)
        :param timeout:      Command timeout in seconds (default: 60)
        :param conn_timeout: TCP connection timeout in seconds (default: 10)
        :param ssh_strict:   Enforce strict SSH host-key checking (default: False)
        :param save_config:  Write running-config to startup after applying changes
        """
        job_key = f"ssh:cfg:{host}"
        ttl = timeout + conn_timeout + 120  # config ops can be slower

        async def _task(progress: ProgressReporter) -> Dict:
            await progress(0, f"Connecting to {host}:{port} for config push …")
            result = await asyncio.to_thread(
                svc.run_config_commands,
                host, username, password, commands,
                device_type, port, secret, timeout, conn_timeout, ssh_strict,
                save_config,
            )
            await progress(100, "Configuration applied.")
            return result

        try:
            job_id = await job_manager.submit(_task, job_key=job_key, ttl=ttl)
        except DuplicateJobError as exc:
            return {"error": str(exc), "job_key": job_key}

        return {
            "job_id": job_id,
            "job_key": job_key,
            "status": "pending",
            "message": (
                "Job submitted. Poll ssh_job_status(job_id) every 60 s "
                "until status is 'completed', then call ssh_job_result(job_id)."
            ),
        }

    # -----------------------------------------------------------------------
    # Job management tools
    # -----------------------------------------------------------------------

    @mcp.tool()
    def ssh_job_status(job_id: str) -> Dict[str, Any]:
        """Poll the status of a background SSH job.

        Returns the current :class:`JobInfo` as a dict.  Key fields:

        * ``status``   – ``pending`` | ``running`` | ``completed`` |
                         ``failed`` | ``timed_out`` | ``cancelled``
        * ``progress`` – ``{percent, message}`` if the task has reported progress
        * ``error``    – error message when ``status`` is ``failed``/``timed_out``

        **Polling guidance**: call this tool every **60 seconds** until
        ``status`` is one of ``completed``, ``failed``, ``timed_out``, or
        ``cancelled``, then call ``ssh_job_result`` to retrieve the output.

        :param job_id: The ``job_id`` returned by one of the SSH submit tools.
        """
        try:
            info = job_manager.get_status(job_id)
            return info.to_dict()
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    # -----------------------------------------------------------------------

    @mcp.tool()
    def ssh_job_result(job_id: str) -> Dict[str, Any]:
        """Retrieve the result of a completed SSH job and remove it from memory.

        This is a **read-once** call: after a successful return the job entry
        is evicted.  Always check ``ssh_job_status`` first to confirm the job
        has finished before calling this tool.

        :param job_id: The ``job_id`` returned by one of the SSH submit tools.
        """
        try:
            result = job_manager.get_result(job_id)
            return {"status": "completed", "result": result}
        except JobNotDoneError as exc:
            return {"status": "running", "message": str(exc)}
        except JobFailedError as exc:
            return {"status": "failed", "error": str(exc)}
        except JobTimedOutError as exc:
            return {"status": "timed_out", "error": str(exc)}
        except JobCancelledError as exc:
            return {"status": "cancelled", "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    # -----------------------------------------------------------------------

    @mcp.tool()
    def ssh_cancel_job(job_id: str) -> Dict[str, Any]:
        """Cancel a running SSH background job.

        The job is kept in the registry with status ``cancelled`` until
        ``ssh_job_result`` is called (which evicts it).  The ``job_key``
        is released immediately so a new job can be submitted for the same
        host.

        :param job_id: The ``job_id`` to cancel.
        """
        try:
            sent = job_manager.cancel(job_id)
            if sent:
                return {"cancelled": True, "message": "Cancellation signal sent."}
            return {
                "cancelled": False,
                "message": "Job was already in a terminal state; no action taken.",
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    # -----------------------------------------------------------------------
    # Bypass + Execute  (one-shot: bypass dialog then run, as a background job)
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def ssh_bypass_and_run_command(
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
        expect_string: Optional[str] = None,
        use_textfsm: bool = False,
        bypass_wait: int = 300,
        poll_interval: int = 30,
    ) -> Dict:
        """Run a single exec-mode command in one call, auto-bypassing the Cisco
        initial configuration dialog if the device is still booting.

        The tool first tries a normal Netmiko connection.  If that fails
        (device stuck on setup wizard), it sends ``no`` via raw TCP to
        *console_port*, then retries Netmiko every *poll_interval* seconds
        for up to *bypass_wait* seconds.  The entire operation runs as a
        background job — returns a ``job_id`` immediately.

        Poll ``ssh_job_status(job_id)`` every 60 s; retrieve with
        ``ssh_job_result(job_id)`` when status is ``completed``.

        :param host:          Device IP / hostname.
        :param console_port:  Console TCP port (for raw-socket bypass).
        :param username:      SSH / Telnet username.
        :param password:      SSH / Telnet password.
        :param command:       Exec-mode command to run.
        :param device_type:   Netmiko device type (default: ``'cisco_ios'``).
        :param ssh_port:      SSH port for Netmiko (default: 22).
        :param secret:        Enable secret.
        :param timeout:       Command timeout in seconds (default: 30).
        :param conn_timeout:  TCP connect timeout in seconds (default: 10).
        :param ssh_strict:    Enforce strict SSH host-key checking.
        :param expect_string: Regex to wait for after the command.
        :param use_textfsm:   Parse with TextFSM / NTC templates.
        :param bypass_wait:   Max seconds to wait after bypass (default: 300).
        :param poll_interval: Seconds between Netmiko retries (default: 30).
        """
        job_key = f"ssh:cmd:{host}"
        ttl = bypass_wait + timeout + conn_timeout + 60

        async def _task(progress: ProgressReporter) -> Dict:
            await progress(0, f"Connecting to {host} (will bypass dialog if needed) ...")
            result = await asyncio.to_thread(
                svc.bypass_and_run_command,
                host, console_port, username, password, command,
                device_type, ssh_port, secret, timeout, conn_timeout, ssh_strict,
                expect_string, use_textfsm, bypass_wait, poll_interval,
            )
            await progress(100, "Command completed.")
            return result

        try:
            job_id = await job_manager.submit(_task, job_key=job_key, ttl=ttl)
        except DuplicateJobError as exc:
            return {"error": str(exc), "job_key": job_key}

        return {
            "job_id": job_id,
            "job_key": job_key,
            "status": "pending",
            "message": (
                "Job submitted (bypass + run). Poll ssh_job_status(job_id) every 60 s "
                "until status is 'completed', then call ssh_job_result(job_id)."
            ),
        }

    # -----------------------------------------------------------------------

    @mcp.tool()
    async def ssh_bypass_and_run_commands(
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
        """Run multiple exec-mode commands in one call, auto-bypassing the Cisco
        initial configuration dialog if the device is still booting.

        Returns a ``job_id`` immediately.  Poll ``ssh_job_status`` every 60 s.

        :param host:          Device IP / hostname.
        :param console_port:  Console TCP port (for raw-socket bypass).
        :param username:      SSH / Telnet username.
        :param password:      SSH / Telnet password.
        :param commands:      Ordered list of exec-mode commands.
        :param device_type:   Netmiko device type (default: ``'cisco_ios'``).
        :param ssh_port:      SSH port for Netmiko (default: 22).
        :param secret:        Enable secret.
        :param timeout:       Command timeout in seconds (default: 30).
        :param conn_timeout:  TCP connect timeout in seconds (default: 10).
        :param ssh_strict:    Enforce strict SSH host-key checking.
        :param bypass_wait:   Max seconds to wait after bypass (default: 300).
        :param poll_interval: Seconds between Netmiko retries (default: 30).
        """
        job_key = f"ssh:cmds:{host}"
        ttl = bypass_wait + timeout * len(commands) + conn_timeout + 60

        async def _task(progress: ProgressReporter) -> Dict:
            await progress(0, f"Connecting to {host} ({len(commands)} commands, bypass if needed) ...")
            result = await asyncio.to_thread(
                svc.bypass_and_run_commands,
                host, console_port, username, password, commands,
                device_type, ssh_port, secret, timeout, conn_timeout, ssh_strict,
                bypass_wait, poll_interval,
            )
            await progress(100, f"All {len(commands)} commands completed.")
            return result

        try:
            job_id = await job_manager.submit(_task, job_key=job_key, ttl=ttl)
        except DuplicateJobError as exc:
            return {"error": str(exc), "job_key": job_key}

        return {
            "job_id": job_id,
            "job_key": job_key,
            "status": "pending",
            "message": (
                "Job submitted (bypass + run commands). Poll ssh_job_status(job_id) every 60 s "
                "until status is 'completed', then call ssh_job_result(job_id)."
            ),
        }

    # -----------------------------------------------------------------------

    @mcp.tool()
    async def ssh_bypass_and_configure(
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
        """Push configuration commands in one call, auto-bypassing the Cisco
        initial configuration dialog if the device is still booting.

        Preferred tool for first-boot device setup: combines the old
        ``bypass_initial_config`` + wait + ``ssh_configure`` flow into a
        single background job.  Returns a ``job_id`` immediately.

        Poll ``ssh_job_status(job_id)`` every 60 s until ``status`` is
        ``completed``, then call ``ssh_job_result(job_id)`` for the result.

        :param host:          Device IP / hostname.
        :param console_port:  Console TCP port (for raw-socket bypass).
        :param username:      SSH / Telnet username.
        :param password:      SSH / Telnet password.
        :param commands:      Config commands (no ``conf t`` / ``end`` needed).
        :param device_type:   Netmiko device type (default: ``'cisco_ios'``).
        :param ssh_port:      SSH port for Netmiko (default: 22).
        :param secret:        Enable secret.
        :param timeout:       Command timeout in seconds (default: 60).
        :param conn_timeout:  TCP connect timeout in seconds (default: 10).
        :param ssh_strict:    Enforce strict SSH host-key checking.
        :param save_config:   Write running-config to startup after changes.
        :param bypass_wait:   Max seconds to wait after bypass (default: 300).
        :param poll_interval: Seconds between Netmiko retries (default: 30).
        """
        job_key = f"ssh:cfg:{host}"
        ttl = bypass_wait + timeout + conn_timeout + 120

        async def _task(progress: ProgressReporter) -> Dict:
            await progress(0, f"Connecting to {host} (config push, bypass if needed) ...")
            result = await asyncio.to_thread(
                svc.bypass_and_configure,
                host, console_port, username, password, commands,
                device_type, ssh_port, secret, timeout, conn_timeout, ssh_strict,
                save_config, bypass_wait, poll_interval,
            )
            await progress(100, "Configuration applied.")
            return result

        try:
            job_id = await job_manager.submit(_task, job_key=job_key, ttl=ttl)
        except DuplicateJobError as exc:
            return {"error": str(exc), "job_key": job_key}

        return {
            "job_id": job_id,
            "job_key": job_key,
            "status": "pending",
            "message": (
                "Job submitted (bypass + configure). Poll ssh_job_status(job_id) every 60 s "
                "until status is 'completed', then call ssh_job_result(job_id)."
            ),
        }

    # -----------------------------------------------------------------------

    @mcp.tool()
    def ssh_bypass_console_dialog(
        host: str,
        console_port: int,
        conn_timeout: int = 10,
        read_timeout: int = 5,
    ) -> Dict:
        """Connect to a device console via raw TCP socket and bypass the Cisco
        initial configuration dialog.

        This is a non-job, synchronous, raw-socket helper. It sends 'no' and
        newlines to the console to dismiss the initial config wizard.

        :param host:          Device IP address or hostname.
        :param console_port:  Console TCP port.
        :param conn_timeout:  TCP connect timeout (default: 10).
        :param read_timeout:  Socket read timeout (default: 5).
        """
        return wrap_errors(
            svc.bypass_console_dialog,
            host, console_port, conn_timeout, read_timeout
        )
