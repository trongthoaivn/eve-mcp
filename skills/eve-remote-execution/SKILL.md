---
name: EVE-NG Remote Command and Configuration Execution
version: 1.0
description: Guides console connection, SSH script configuration, and running CLI commands directly on active EVE-NG node operating systems.
usage: Use this skill when asked to execute CLI commands, push startup or interface configurations, retrieve output from a node, or run scripts across multiple nodes.
dependencies: eve-mcp toolset (specifically `eve-mcp:remote_command`, `eve-mcp:remote_commands`, `eve-mcp:remote_config`, `eve-mcp:remote_node`, `eve-mcp:ssh_run_command`, `eve-mcp:ssh_run_commands`, `eve-mcp:ssh_configure`)
---

## Objective
To interact directly with the operating system (CLI) of EVE-NG nodes via console, Telnet, or SSH to execute commands and configure features.

## Step-by-Step Instructions

1. **Verify Prerequisites:**
   * Make sure you are logged in using `eve-authentication` first.
   * Node must be in a `running` state (use `eve-node-management` to check status and start the node if necessary).
     - *Note:* Newly started nodes typically take 5 to 10 minutes to boot up completely. Make sure to wait until the node is fully booted before running commands.

2. **Establish Remote Sessions:**
   * Use `remote_node` to acquire the connection URI (e.g. telnet:// or vnc:// address) for a node console.

3. **Determine and Navigate CLI Modes:**
   * Before executing any configuration or operational commands, always identify the device's current CLI mode by inspecting the prompt (e.g., User EXEC `Router>`, Privileged EXEC `Router#`, or Global Config `Router(config)#`).
   * **Reset Session Mode:** Whenever starting a new command execution or configuration block, send `end` first to exit all sub-configuration modes and return to Privileged EXEC mode, then navigate to the target mode.
   * Navigate or escalate to the appropriate mode required for your commands before sending them:
     - Use `enable` to enter privileged EXEC mode.
     - Use `configure terminal` (or `conf t`) to enter global configuration mode.
     - Refer to [Cisco IOS Patterns](/skills/cisco-ios-patterns/SKILL.md) for detail on prompt hierarchies and commands.

4. **Remote Console Operations (Non-SSH):**
   * Use `remote_node` to connect via console port and execute commands.
   * **Alternative: Upload Startup Configuration (Highly Reliable):** If interactive console configuration via `remote_node` fails due to Netmiko prompt-matching, EULA, or initialization errors (e.g., `terminal width 511` error):
     - Use `eve-mcp:upload_node_config` to upload and activate (`enable=true`) the startup configuration directly.
     - If the node is currently running, stop the node (`eve-mcp:stop_node`), wipe the node (`eve-mcp:wipe_node`) to clear runtime state, and start it again (`eve-mcp:start_node`). The device will boot directly with the correct configuration.
   * **Bypassing Initial Configuration Dialog (First Boot Gotcha):** Freshly booted devices (e.g. Cisco vIOS L2 switches) often display an initial configuration wizard asking `Would you like to enter the initial configuration dialog? [yes/no]:`. 
     - *Problem:* While stuck on this prompt, standard MCP tools like `remote_node` (using Netmiko) will fail with a `Login failed` error because they expect a standard `Switch>` or `Switch#` prompt.
     - *Solution:* Use the `eve-mcp:bypass_initial_config` tool to automatically connect via raw TCP socket and send `no` to bypass the prompt. Note: You must wait 3-5 minutes after running this bypass before proceeding with further tool executions to ensure the device has fully completed its boot process. **Important:** After the bypass completes, you must set the hostname of the device (e.g., via `remote_node` with config commands) before proceeding with other configurations. Once ready, you can use the standard MCP remote execution tools.
   * **Configuring VPCS Nodes (`vpcs` template):**
     - VPCS nodes are lightweight emulators and do NOT support Cisco-specific initialization commands (like `terminal width` or `terminal length`).
     - When configuring VPCS nodes, set the Netmiko `device_type` to `generic_telnet` and only run VPCS-compatible commands (e.g., `ip dhcp` to obtain IP, `save` to save config, `ping` to test connectivity).
     - If standard Netmiko telnet fails due to prompt scraping issues on VPCS (`PC1>`), send an empty string `""` command first to wake up the prompt, or use raw socket telnet connections as a fallback.

5. **SSH-Based Configuration (Direct Management Network):**
   * If the node has management IP connectivity and SSH is enabled, use `ssh_run_command` to execute shell or CLI commands.
   * Use `ssh_run_commands` to execute a list of sequential commands.
   * Use `ssh_configure` to connect via SSH and apply configuration commands. This is preferred for routers/switches when SSH is already configured, as it is faster and more reliable than raw console input.

6. **Handling MCP Failures:**
   * **CRITICAL:** When encountering an error on the MCP (Server/Tool) side that cannot be fixed, you must stop immediately and notify the user. Under no circumstances should you create standalone scripts or code to run outside the MCP system.

## Context & Tools
- `eve-mcp:remote_node`: Retrieve telnet/vnc connection URLs and execute console commands.
- `eve-mcp:upload_node_config` / `eve-mcp:enable_node_config`: Upload and enable startup configurations.
- `eve-mcp:remote_command`: Send console inputs/commands to a node.
- `eve-mcp:remote_commands`: Send sequence of console inputs.
- `eve-mcp:remote_config`: Apply configuration commands via console.
- `eve-mcp:ssh_run_command` / `eve-mcp:ssh_run_commands`: Execute SSH commands.
- `eve-mcp:ssh_configure`: Apply configuration via SSH.
