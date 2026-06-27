"""
eve_ng_controller.py
--------------------
FastMCP controller that registers all EVE-NG MCP tools.

Each @mcp.tool() function delegates to eve_ng_service and returns a
structured result.  Error handling is centralised so every tool
consistently returns a JSON-serialisable dict.

Tool groups
-----------
  Session       : login, logout, reset_session
  System        : get_server_status
  Templates     : list_node_templates, node_template_detail
  Users         : list_users, list_user_roles, get_user, add_user,
                  edit_user, delete_user
  Networks      : list_networks
  Folders       : list_folders, get_folder
  Labs          : get_lab, create_lab, edit_lab, delete_lab, close_lab,
                  lock_lab, unlock_lab, export_lab, import_lab,
                  get_lab_topology, export_all_nodes,
                  get_lab_pictures, get_lab_picture_details
  Lab Networks  : list_lab_networks, get_lab_network, get_lab_network_by_name,
                  add_lab_network, edit_lab_network, list_lab_links
  Nodes         : list_nodes, get_node, get_node_by_name, add_node,
                  delete_node, start_node, stop_node, start_all_nodes,
                  stop_all_nodes, wipe_node, wipe_all_nodes, export_node,
                  enable_node_config, get_node_interfaces, get_node_configs,
                  get_node_config_by_id, upload_node_config
  Connections   : connect_node, connect_node_to_cloud, connect_node_to_node,
                  connect_p2p_interface
  Remote Access : remote_command, remote_commands, remote_config, remote_node
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import services.eve_ng_service as svc
import services.remote_service as remote_svc
from utilities.sdk_helpers import wrap_errors


def register(mcp):
    """Register all EVE-NG tools onto the given FastMCP instance.

    :param mcp: FastMCP application instance
    """

    # -----------------------------------------------------------------------
    # Session
    # -----------------------------------------------------------------------

    @mcp.tool()
    def login(
        host: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        protocol: Optional[str] = None,
        port: Optional[int] = None,
        ssl_verify: Optional[bool] = None,
    ) -> Dict:
        """Authenticate against an EVE-NG server and replace the active session.

        All parameters are optional and fall back to the corresponding
        environment variable (EVE_HOST, EVE_USERNAME, EVE_PASSWORD, etc.),
        so you can override only what you need.

        :param host:       EVE-NG server hostname or IP
        :param username:   Login username
        :param password:   Login password
        :param protocol:   'http' or 'https'
        :param port:       Server port number
        :param ssl_verify: Verify TLS certificate (True/False)
        """
        return wrap_errors(svc.login, host, username, password, protocol, port, ssl_verify)

    @mcp.tool()
    def reset_session() -> Dict:
        """Invalidate the current EVE-NG session (in-memory + on-disk cookie file)
        and force a fresh login on the next API call.

        Use this when credentials change or when EVE-NG returns auth errors.
        """
        return wrap_errors(svc.reset_session)

    @mcp.tool()
    def logout() -> Dict:
        """Log out from EVE-NG (invalidates the server-side session) and clear
        the local session cookie file.

        After this call the next API tool invocation will trigger a fresh login.
        """
        return wrap_errors(svc.logout)

    # -----------------------------------------------------------------------
    # System
    # -----------------------------------------------------------------------

    @mcp.tool()
    def get_server_status() -> Dict:
        """Return EVE-NG server status information (version, CPU, RAM, etc.)."""
        return wrap_errors(svc.get_server_status)

    # -----------------------------------------------------------------------
    # Node Templates
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_node_templates() -> Dict:
        """List all available node templates on the EVE-NG server."""
        return wrap_errors(svc.list_node_templates)

    @mcp.tool()
    def node_template_detail(node_type: str) -> Dict:
        """Return details and available images for a node template.

        :param node_type: Template name, e.g. 'iosv', 'csr1000v', 'veos'
        """
        return wrap_errors(svc.node_template_detail, node_type)

    # -----------------------------------------------------------------------
    # Users
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_users() -> Dict:
        """Return a list of all EVE-NG users."""
        return wrap_errors(svc.list_users)

    @mcp.tool()
    def list_user_roles() -> Dict:
        """Return the available EVE-NG user roles."""
        return wrap_errors(svc.list_user_roles)

    @mcp.tool()
    def get_user(username: str) -> Dict:
        """Return details for a specific EVE-NG user.

        :param username: The login username to look up
        """
        return wrap_errors(svc.get_user, username)

    @mcp.tool()
    def add_user(
        username: str,
        password: str,
        role: str = "user",
        name: str = "",
        email: str = "",
        expiration: str = "-1",
    ) -> Dict:
        """Create a new EVE-NG user account.

        :param username: Unique alphanumeric login name
        :param password: Login password
        :param role: User role: 'user' or 'admin' (default: 'user')
        :param name: User's full display name (optional)
        :param email: User email address (optional)
        :param expiration: UNIX timestamp for expiry, or '-1' for never (default: '-1')
        """
        return wrap_errors(svc.add_user, username, password, role, name, email, expiration)

    @mcp.tool()
    def edit_user(username: str, data: dict) -> Dict:
        """Update an existing EVE-NG user's details.

        :param username: Login name of the user to update
        :param data: Dictionary of fields to update, e.g. {"email": "new@example.com"}
        """
        return wrap_errors(svc.edit_user, username, data)

    @mcp.tool()
    def delete_user(username: str) -> Dict:
        """Delete an EVE-NG user account.

        :param username: Login name of the user to delete
        """
        return wrap_errors(svc.delete_user, username)

    # -----------------------------------------------------------------------
    # Networks
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_networks() -> Dict:
        """List available network types on the EVE-NG server (bridge, pnet0-pnet9, etc.)."""
        return wrap_errors(svc.list_networks)

    # -----------------------------------------------------------------------
    # Folders
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_folders() -> Dict:
        """List all lab folders on the EVE-NG server, including contained labs."""
        return wrap_errors(svc.list_folders)

    @mcp.tool()
    def get_folder(folder: str) -> Dict:
        """Return details for a specific lab folder.

        :param folder: Folder path, e.g. 'my_labs' or '/my_labs'
        """
        return wrap_errors(svc.get_folder, folder)

    # -----------------------------------------------------------------------
    # Labs
    # -----------------------------------------------------------------------

    @mcp.tool()
    def get_lab(path: str) -> Dict:
        """Return metadata for a single lab.

        :param path: Lab path including parent folder, e.g. '/my_folder/my_lab'
        """
        return wrap_errors(svc.get_lab, path)

    @mcp.tool()
    def create_lab(
        name: str,
        path: str = "/",
        version: str = "1",
        description: str = "",
        author: str = "",
        body: str = "",
    ) -> Dict:
        """Create a new lab on the EVE-NG server.

        :param name: Lab name without .unl extension
        :param path: Destination folder path (default: '/')
        :param version: Lab version string (default: '1')
        :param description: Short lab description (optional)
        :param author: Lab author name (optional)
        :param body: Detailed lab notes / body text (optional)
        """
        return wrap_errors(svc.create_lab, name, path, version, description, author, body)

    @mcp.tool()
    def edit_lab(path: str, data: dict) -> Dict:
        """Edit metadata fields for an existing lab.

        :param path: Lab path including parent folder
        :param data: Dict of fields to update, e.g. {"description": "new description"}
        """
        return wrap_errors(svc.edit_lab, path, data)

    @mcp.tool()
    def delete_lab(path: str) -> Dict:
        """Delete a lab from the EVE-NG server permanently.

        :param path: Lab path including parent folder
        """
        return wrap_errors(svc.delete_lab, path)

    @mcp.tool()
    def close_lab(path: str) -> Dict:
        """Close an open lab (stops all nodes and frees server memory).

        :param path: Lab path including parent folder
        """
        return wrap_errors(svc.close_lab, path)

    @mcp.tool()
    def lock_lab(path: str) -> Dict:
        """Lock a lab to prevent users from modifying it.

        :param path: Lab path including parent folder
        """
        return wrap_errors(svc.lock_lab, path)

    @mcp.tool()
    def unlock_lab(path: str) -> Dict:
        """Unlock a previously locked lab.

        :param path: Lab path including parent folder
        """
        return wrap_errors(svc.unlock_lab, path)

    @mcp.tool()
    def export_lab(path: str, filename: Optional[str] = None) -> Dict:
        """Export a lab as a downloadable .zip / .unl file.

        :param path: Lab path on the EVE-NG server
        :param filename: Local filename to save the export (optional, uses server name by default)
        """
        return wrap_errors(svc.export_lab, path, filename)

    @mcp.tool()
    def import_lab(path: str, folder: str = "/") -> Dict:
        """Import a lab from a local .unl or .zip file.

        :param path: Local file path of the lab archive to import
        :param folder: Destination folder on the server (default: '/')
        """
        return wrap_errors(svc.import_lab, path, folder)

    @mcp.tool()
    def get_lab_topology(path: str) -> Dict:
        """Return the topology (nodes and connections) for a lab.

        :param path: Lab path including parent folder
        """
        return wrap_errors(svc.get_lab_topology, path)

    @mcp.tool()
    def export_all_nodes(path: str) -> Dict:
        """Save startup configs of all nodes in a lab to the server.

        :param path: Lab path including parent folder
        """
        return wrap_errors(svc.export_all_nodes, path)

    @mcp.tool()
    def get_lab_pictures(path: str) -> Dict:
        """Return all pictures / diagrams associated with a lab.

        :param path: Lab path including parent folder
        """
        return wrap_errors(svc.get_lab_pictures, path)

    @mcp.tool()
    def get_lab_picture_details(path: str, picture_id: int) -> Dict:
        """Return details for a specific lab picture / diagram.

        :param path: Lab path including parent folder
        :param picture_id: Numeric picture ID
        """
        return wrap_errors(svc.get_lab_picture_details, path, picture_id)

    # -----------------------------------------------------------------------
    # Lab Networks
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_lab_networks(path: str) -> Dict:
        """List all virtual networks defined within a lab.

        :param path: Lab path including parent folder
        """
        return wrap_errors(svc.list_lab_networks, path)

    @mcp.tool()
    def get_lab_network(path: str, net_id: int) -> Dict:
        """Return details for a specific network within a lab.

        :param path: Lab path including parent folder
        :param net_id: Numeric network ID
        """
        return wrap_errors(svc.get_lab_network, path, net_id)

    @mcp.tool()
    def get_lab_network_by_name(path: str, name: str) -> Dict:
        """Return a lab network identified by its name.

        :param path: Lab path including parent folder
        :param name: Network name / label
        """
        return wrap_errors(svc.get_lab_network_by_name, path, name)

    @mcp.tool()
    def add_lab_network(
        path: str,
        network_type: str,
        name: str = "",
        left: int = 0,
        top: int = 0,
        visibility: int = 1,
    ) -> Dict:
        """Add a new virtual network to a lab.

        :param path: Lab path including parent folder
        :param network_type: Network type, e.g. 'bridge', 'pnet0'
        :param name: Network label (optional)
        :param left: Horizontal canvas position (default: 0)
        :param top: Vertical canvas position (default: 0)
        :param visibility: 1 = visible, 0 = hidden (default: 1)
        """
        return wrap_errors(svc.add_lab_network, path, network_type, name, left, top, visibility)

    @mcp.tool()
    def edit_lab_network(path: str, net_id: int, data: dict) -> Dict:
        """Edit an existing virtual network in a lab.

        :param path: Lab path including parent folder
        :param net_id: Network ID to edit
        :param data: Dictionary of fields to update
        """
        return wrap_errors(svc.edit_lab_network, path, net_id, data)

    @mcp.tool()
    def list_lab_links(path: str) -> Dict:
        """List all links (connections) within a lab.

        :param path: Lab path including parent folder
        """
        return wrap_errors(svc.list_lab_links, path)

    # -----------------------------------------------------------------------
    # Nodes
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_nodes(path: str) -> Dict:
        """List all nodes in a lab.

        :param path: Lab path including parent folder
        """
        return wrap_errors(svc.list_nodes, path)

    @mcp.tool()
    def get_node(path: str, node_id: int) -> Dict:
        """Return details for a specific node in a lab.

        :param path: Lab path including parent folder
        :param node_id: Numeric node ID
        """
        return wrap_errors(svc.get_node, path, node_id)

    @mcp.tool()
    def get_node_by_name(path: str, name: str) -> Dict:
        """Return a node identified by its name/label.

        :param path: Lab path including parent folder
        :param name: Node name / label
        """
        return wrap_errors(svc.get_node_by_name, path, name)

    @mcp.tool()
    def add_node(
        path: str,
        node_type: str,
        template: str,
        name: str = "",
        image: str = "",
        left: int = 0,
        top: int = 0,
        ram: int = 512,
        cpu: int = 1,
        ethernet: int = 4,
        serial: int = 0,
        console: str = "telnet",
        delay: int = 0,
        icon: str = "Router.png",
    ) -> Dict:
        """Add a new node to a lab.

        :param path: Lab path including parent folder
        :param node_type: Node type, e.g. 'qemu', 'dynamips', 'iol'
        :param template: Template name, e.g. 'iosv', 'veos', 'csr1000v'
        :param name: Node label / hostname (optional)
        :param image: Specific image filename to use (empty = template default)
        :param left: Horizontal canvas position (default: 0)
        :param top: Vertical canvas position (default: 0)
        :param ram: RAM allocation in MB (default: 512)
        :param cpu: Number of virtual CPUs (default: 1)
        :param ethernet: Number of Ethernet interfaces (default: 4)
        :param serial: Number of Serial interfaces (default: 0)
        :param console: Console type, 'telnet' or 'vnc' (default: 'telnet')
        :param delay: Startup delay in seconds (default: 0)
        :param icon: Canvas icon filename (default: 'Router.png')
        """
        return wrap_errors(
            svc.add_node,
            path, node_type, template, name, image, left, top,
            ram, cpu, ethernet, serial, console, delay, icon,
        )

    @mcp.tool()
    def delete_node(path: str, node_id: int) -> Dict:
        """Delete a node from a lab.

        :param path: Lab path including parent folder
        :param node_id: Numeric node ID to delete
        """
        return wrap_errors(svc.delete_node, path, node_id)

    @mcp.tool()
    def start_node(path: str, node_id: int) -> Dict:
        """Start a single node in a lab.

        :param path: Lab path including parent folder
        :param node_id: Numeric node ID to start
        """
        return wrap_errors(svc.start_node, path, node_id)

    @mcp.tool()
    def stop_node(path: str, node_id: int) -> Dict:
        """Stop (power off) a single node in a lab.

        :param path: Lab path including parent folder
        :param node_id: Numeric node ID to stop
        """
        return wrap_errors(svc.stop_node, path, node_id)

    @mcp.tool()
    def start_all_nodes(path: str) -> Dict:
        """Start all nodes in a lab simultaneously.

        :param path: Lab path including parent folder
        """
        return wrap_errors(svc.start_all_nodes, path)

    @mcp.tool()
    def stop_all_nodes(path: str) -> Dict:
        """Stop all running nodes in a lab.

        :param path: Lab path including parent folder
        """
        return wrap_errors(svc.stop_all_nodes, path)

    @mcp.tool()
    def wipe_node(path: str, node_id: int) -> Dict:
        """Wipe (reset to factory default) a single node's startup config.

        :param path: Lab path including parent folder
        :param node_id: Numeric node ID to wipe
        """
        return wrap_errors(svc.wipe_node, path, node_id)

    @mcp.tool()
    def wipe_all_nodes(path: str) -> Dict:
        """Wipe startup configs for all nodes in a lab.

        :param path: Lab path including parent folder
        """
        return wrap_errors(svc.wipe_all_nodes, path)

    @mcp.tool()
    def export_node(path: str, node_id: int) -> Dict:
        """Save the running startup config of a single node to the server.

        :param path: Lab path including parent folder
        :param node_id: Numeric node ID
        """
        return wrap_errors(svc.export_node, path, node_id)

    @mcp.tool()
    def enable_node_config(path: str, node_id: int) -> Dict:
        """Enable the startup config feature for a node.

        :param path: Lab path including parent folder
        :param node_id: Numeric node ID
        """
        return wrap_errors(svc.enable_node_config, path, node_id)

    @mcp.tool()
    def get_node_interfaces(path: str, node_id: int) -> Dict:
        """Return the interface list for a specific node.

        :param path: Lab path including parent folder
        :param node_id: Numeric node ID
        """
        return wrap_errors(svc.get_node_interfaces, path, node_id)

    @mcp.tool()
    def get_node_configs(path: str) -> Dict:
        """Return all node startup configs for a lab.

        :param path: Lab path including parent folder
        """
        return wrap_errors(svc.get_node_configs, path)

    @mcp.tool()
    def get_node_config_by_id(path: str, config_id: int) -> Dict:
        """Return the startup config for a node by its config ID.

        :param path: Lab path including parent folder
        :param config_id: Configuration record ID
        """
        return wrap_errors(svc.get_node_config_by_id, path, config_id)

    @mcp.tool()
    def upload_node_config(
        path: str, node_id: int, config: str, enable: bool = True
    ) -> Dict:
        """Upload a startup configuration to a node.

        :param path: Lab path including parent folder
        :param node_id: Numeric node ID
        :param config: Full startup config text to upload
        :param enable: Whether to activate the config immediately (default: True)
        """
        return wrap_errors(svc.upload_node_config, path, node_id, config, enable)

    # -----------------------------------------------------------------------
    # Node Connections
    # -----------------------------------------------------------------------

    @mcp.tool()
    def connect_node(path: str, node_id: int, connections: dict) -> Dict:
        """Connect one or more node interfaces to networks or other nodes.

        :param path: Lab path including parent folder
        :param node_id: Source node ID
        :param connections: Mapping of interface index (str) to destination ID,
                            e.g. {"0": 1, "1": 2}
        """
        return wrap_errors(svc.connect_node, path, node_id, connections)

    @mcp.tool()
    def connect_node_to_cloud(
        path: str, node_id: int, node_interface: int, cloud_id: int
    ) -> Dict:
        """Connect a node interface to a cloud (bridge/pnet) network.

        :param path: Lab path including parent folder
        :param node_id: Source node ID
        :param node_interface: Interface index on the source node
        :param cloud_id: Target cloud network ID
        """
        return wrap_errors(svc.connect_node_to_cloud, path, node_id, node_interface, cloud_id)

    @mcp.tool()
    def connect_node_to_node(
        path: str,
        src_node_id: int,
        src_interface: int,
        dst_node_id: int,
        dst_interface: int,
    ) -> Dict:
        """Create a direct link between two node interfaces.

        :param path: Lab path including parent folder
        :param src_node_id: Source node ID
        :param src_interface: Source node interface index
        :param dst_node_id: Destination node ID
        :param dst_interface: Destination node interface index
        """
        return wrap_errors(
            svc.connect_node_to_node,
            path, src_node_id, src_interface, dst_node_id, dst_interface,
        )

    @mcp.tool()
    def connect_p2p_interface(
        path: str,
        src_node_id: int,
        src_interface: int,
        dst_node_id: int,
        dst_interface: int,
    ) -> Dict:
        """Connect a P2P interface between two nodes (EVE-NG Pro feature).

        :param path: Lab path including parent folder
        :param src_node_id: Source node ID
        :param src_interface: Source interface index
        :param dst_node_id: Destination node ID
        :param dst_interface: Destination interface index
        """
        return wrap_errors(
            svc.connect_p2p_interface,
            path, src_node_id, src_interface, dst_node_id, dst_interface,
        )

    # -----------------------------------------------------------------------
    # Remote Access (SSH via Netmiko)
    # -----------------------------------------------------------------------

    @mcp.tool()
    def remote_command(
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
        """SSH into a network device and execute a single exec-mode command.

        Opens an SSH connection via Netmiko, runs the command, then closes
        the connection.  Works with any device reachable from the MCP server
        (including EVE-NG nodes that have management access).

        :param host:          Device IP address or hostname
        :param username:      SSH login username
        :param password:      SSH login password
        :param command:       Exec-mode command to run, e.g. 'show ip interface brief'
        :param device_type:   Netmiko device type (default: 'cisco_ios').
                              Other common values: 'cisco_nxos', 'cisco_xr',
                              'arista_eos', 'juniper_junos', 'linux', 'huawei'
        :param port:          SSH port (default: 22)
        :param secret:        Enable / privilege-escalation secret (Cisco devices)
        :param timeout:       Command read timeout in seconds (default: 30)
        :param conn_timeout:  TCP connection timeout in seconds (default: 10)
        :param ssh_strict:    Enforce strict SSH host-key checking (default: False)
        :param expect_string: Optional regex pattern to wait for after the command
        :param use_textfsm:   Parse output with TextFSM/NTC templates (default: False)
        :returns: Dict with 'host', 'device_type', 'command', and 'output' keys.
        """
        return wrap_errors(
            remote_svc.run_command,
            host, username, password, command,
            device_type, port, secret, timeout, conn_timeout, ssh_strict,
            expect_string, use_textfsm,
        )

    @mcp.tool()
    def remote_commands(
        host: str,
        username: str,
        password: str,
        commands: list,
        device_type: str = "cisco_ios",
        port: int = 22,
        secret: str = "",
        timeout: int = 30,
        conn_timeout: int = 10,
        ssh_strict: bool = False,
    ) -> Dict:
        """SSH into a network device and execute multiple exec-mode commands.

        Opens a single SSH connection, runs all commands sequentially in
        exec mode, then closes the connection.  Results are returned as a
        list so callers can inspect each command's output individually.

        :param host:         Device IP address or hostname
        :param username:     SSH login username
        :param password:     SSH login password
        :param commands:     List of exec-mode commands to run
        :param device_type:  Netmiko device type (default: 'cisco_ios')
        :param port:         SSH port (default: 22)
        :param secret:       Enable / privilege-escalation secret (Cisco devices)
        :param timeout:      Command read timeout in seconds (default: 30)
        :param conn_timeout: TCP connection timeout in seconds (default: 10)
        :param ssh_strict:   Enforce strict SSH host-key checking (default: False)
        :returns: Dict with 'host', 'device_type', and 'results' (list of
                  {command, output} dicts) keys.
        """
        return wrap_errors(
            remote_svc.run_commands,
            host, username, password, commands,
            device_type, port, secret, timeout, conn_timeout, ssh_strict,
        )

    @mcp.tool()
    def remote_config(
        host: str,
        username: str,
        password: str,
        commands: list,
        device_type: str = "cisco_ios",
        port: int = 22,
        secret: str = "",
        timeout: int = 60,
        conn_timeout: int = 10,
        ssh_strict: bool = False,
        save_config: bool = False,
    ) -> Dict:
        """SSH into a network device and push configuration-mode commands.

        Enters configuration mode (e.g. 'conf t' on Cisco IOS), sends all
        commands in sequence, exits config mode, and optionally saves the
        running-config to startup-config.

        :param host:         Device IP address or hostname
        :param username:     SSH login username
        :param password:     SSH login password
        :param commands:     List of configuration commands (do NOT include
                             'conf t' or 'end' — Netmiko handles those)
        :param device_type:  Netmiko device type (default: 'cisco_ios')
        :param port:         SSH port (default: 22)
        :param secret:       Enable / privilege-escalation secret (Cisco devices)
        :param timeout:      Command read timeout in seconds (default: 60)
        :param conn_timeout: TCP connection timeout in seconds (default: 10)
        :param ssh_strict:   Enforce strict SSH host-key checking (default: False)
        :param save_config:  Write running-config to startup-config after
                             applying changes (default: False)
        :returns: Dict with 'host', 'device_type', 'commands',
                  'config_output', and 'saved' keys.
        """
        return wrap_errors(
            remote_svc.run_config_commands,
            host, username, password, commands,
            device_type, port, secret, timeout, conn_timeout, ssh_strict,
            save_config,
        )

    @mcp.tool()
    def remote_node(
        path: str,
        node_id: Optional[int] = None,
        node_name: Optional[str] = None,
        command: Optional[str] = None,
        commands: Optional[list] = None,
        config_commands: Optional[list] = None,
        save_config: bool = False,
        username: str = "",
        password: str = "",
        secret: str = "",
        device_type: Optional[str] = None,
        timeout: int = 30,
    ) -> Dict:
        """Remote into a specific EVE-NG node using its console port and execute commands.

        This tool resolves the console connection port and host for the target node,
        and uses Netmiko to connect and execute show or configuration commands.

        :param path:            Lab path including parent folder, e.g. '/my_labs/my_lab'
        :param node_id:         Numeric node ID (optional if node_name is provided)
        :param node_name:       Node name / label (optional if node_id is provided)
        :param command:         A single exec command to run (e.g. 'show ip interface brief')
        :param commands:        A list of exec commands to run
        :param config_commands: A list of configuration commands to run
        :param save_config:     Save configuration after running config commands (default: False)
        :param username:        Username for device login (default: empty for console)
        :param password:        Password for device login (default: empty for console)
        :param secret:          Secret for enable mode escalation (default: empty)
        :param device_type:     Explicit Netmiko device type (e.g., 'cisco_ios_telnet').
                                If not specified, it is automatically guessed from the template.
        :param timeout:         Timeout in seconds for operations (default: 30)
        """
        def _execute_remote(host: str, port: int, dev_type: str):
            if command:
                return remote_svc.run_command(
                    host=host,
                    username=username,
                    password=password,
                    command=command,
                    device_type=dev_type,
                    port=port,
                    secret=secret,
                    timeout=timeout,
                )
            elif commands:
                return remote_svc.run_commands(
                    host=host,
                    username=username,
                    password=password,
                    commands=commands,
                    device_type=dev_type,
                    port=port,
                    secret=secret,
                    timeout=timeout,
                )
            elif config_commands:
                return remote_svc.run_config_commands(
                    host=host,
                    username=username,
                    password=password,
                    commands=config_commands,
                    device_type=dev_type,
                    port=port,
                    secret=secret,
                    timeout=timeout,
                    save_config=save_config,
                )
            else:
                raise ValueError("Must provide one of: command, commands, or config_commands")

        def _resolve_and_execute():
            if node_id is not None:
                node_resp = svc.get_node(path, node_id)
                if not node_resp or node_resp.get("status") != "success":
                    raise ValueError(f"Could not retrieve node {node_id}: {node_resp}")
                node_data = node_resp.get("data", {})
            elif node_name is not None:
                node_resp = svc.get_node_by_name(path, node_name)
                if "result" in node_resp and node_resp["result"] is None:
                    raise ValueError(f"Node '{node_name}' not found in lab '{path}'")
                node_data = node_resp
            else:
                raise ValueError("Either node_id or node_name must be provided")

            url_str = node_data.get("url", "")
            port = node_data.get("port")
            template = node_data.get("template", "")
            console_type = node_data.get("console", "telnet")

            if not port and url_str:
                if "://" in url_str:
                    try:
                        from urllib.parse import urlparse
                        parsed = urlparse(url_str)
                        if parsed.port:
                            port = parsed.port
                    except Exception:
                        pass
                if not port:
                    parts = url_str.split(":")
                    if len(parts) >= 2:
                        try:
                            port = int(parts[-1])
                        except ValueError:
                            pass

            if not port:
                raise ValueError(f"Could not resolve console port for node (data: {node_data})")

            client = svc._get_client()
            host = client.host

            if not device_type:
                t = template.lower().strip()
                mapping = {
                    "iosv": "cisco_ios",
                    "iol": "cisco_ios",
                    "vios": "cisco_ios",
                    "viosl2": "cisco_ios",
                    "csr1000v": "cisco_ios",
                    "csr1000vng": "cisco_ios",
                    "asa": "cisco_asa",
                    "asav": "cisco_asa",
                    "veos": "arista_eos",
                    "vsrx": "juniper_junos",
                    "junos": "juniper_junos",
                    "linux": "linux",
                    "mikrotik": "mikrotik_routeros",
                    "panos": "paloalto_panos",
                    "fortinet": "fortinet",
                    "vyos": "vyos",
                }
                base_type = mapping.get(t, "cisco_ios")
                if console_type == "telnet":
                    supported_telnets = {
                        "cisco_ios_telnet", "arista_eos_telnet", "juniper_junos_telnet",
                        "cisco_xe_telnet", "huawei_telnet", "paloalto_panos_telnet",
                        "hp_comware_telnet", "brocade_fastiron_telnet"
                    }
                    telnet_type = f"{base_type}_telnet"
                    dev_type = telnet_type if telnet_type in supported_telnets else "generic_telnet"
                else:
                    dev_type = base_type
            else:
                dev_type = device_type

            return _execute_remote(host, port, dev_type)

        return wrap_errors(_resolve_and_execute)

    @mcp.tool()
    def bypass_initial_config(path: str, node_id: int) -> Dict:
        """Connect to a node's console via raw socket and bypass the initial
        configuration dialog (e.g., sending 'no' to the yes/no prompt).
        Note: You must wait 3-5 minutes after running this bypass before
        proceeding with other commands.

        :param path: Lab path including parent folder
        :param node_id: Numeric node ID
        """
        return wrap_errors(svc.bypass_initial_config, path, node_id)
