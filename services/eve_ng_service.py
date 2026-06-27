"""
eve_ng_service.py
-----------------
Service layer that wraps the evengsdk library (EvengClient / EvengApi) and
exposes every available API method as a clean, exception-safe Python call.

Environment variables consumed (via python-dotenv / os.environ):
    EVE_HOST       - EVE-NG server hostname / IP  (required)
    EVE_USERNAME   - Login username               (required)
    EVE_PASSWORD   - Login password               (required)
    EVE_PROTOCOL   - http | https                 (default: http)
    EVE_PORT       - Server port                  (optional)
    EVE_SSL_VERIFY - true | false                 (default: true)
    EVE_DISABLE_INSECURE_WARNINGS - true | false  (default: false)
    EVE_SESSION_FILE - path to persist session cookies (default: .eve_session.json)

Session persistence
-------------------
After a successful login, the HTTP session cookies returned by EVE-NG are
written to ``EVE_SESSION_FILE``.  On the next call, those cookies are loaded
and validated with a lightweight server-status ping before reuse, so the MCP
server can survive restarts without forcing a fresh login every time.

If the saved session has expired (EVE-NG returns 401 / raises an exception),
the code automatically falls back to a full username/password login and
overwrites the session file with the fresh cookies.

Public helpers (also exposed as MCP tools via the controller):
    reset_session() - invalidate in-memory + on-disk session (force re-login)
    logout()        - call the EVE-NG logout endpoint then reset session

Internal helpers:
    _get_client()  - singleton EvengClient (lazy, cached, session-aware)
    _api()         - shortcut to client.api (EvengApi)
    normalise_response() - from utilities.sdk_helpers, coerce result to dict
"""

import json
import logging
import os
import pathlib
import socket
import time
from typing import Dict, Optional

from dotenv import load_dotenv
from evengsdk.client import EvengClient

from utilities.sdk_helpers import normalise_response

load_dotenv()

_logger = logging.getLogger("eve_mcp")

# Path where session cookies are persisted between runs
_SESSION_FILE = pathlib.Path(os.getenv("EVE_SESSION_FILE", ".eve_session.json"))


# ---------------------------------------------------------------------------
# Session persistence helpers
# ---------------------------------------------------------------------------

def _save_session(client: EvengClient) -> None:
    """Persist the session cookies from *client* to :data:`_SESSION_FILE`."""
    try:
        cookies = dict(client.session.cookies)
        _SESSION_FILE.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
        _logger.debug("Session cookies saved to %s", _SESSION_FILE)
    except Exception as exc:
        _logger.warning("Could not save session: %s", exc)


def _restore_session(client: EvengClient) -> bool:
    """Load cookies from :data:`_SESSION_FILE` into *client* and validate them.

    Returns ``True`` when the restored session is still accepted by the server,
    ``False`` otherwise (file missing, corrupt, or session expired).
    """
    if not _SESSION_FILE.exists():
        return False
    try:
        cookies = json.loads(_SESSION_FILE.read_text(encoding="utf-8"))
        client.session.cookies.update(cookies)
        # Lightweight validation: any authenticated endpoint will do
        client.api.get_server_status()
        _logger.info("EVE-NG session restored from %s", _SESSION_FILE)
        return True
    except Exception as exc:
        _logger.debug("Saved session is invalid (%s) — will re-login", exc)
        # Remove stale file so the next call does a clean login
        _SESSION_FILE.unlink(missing_ok=True)
        # Clear the bad cookies from the session object
        client.session.cookies.clear()
        return False


# ---------------------------------------------------------------------------
# Singleton client / api instances
# ---------------------------------------------------------------------------

_client: Optional[EvengClient] = None


def _build_client(
    host: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    protocol: Optional[str] = None,
    port: Optional[int] = None,
    ssl_verify: Optional[bool] = None,
) -> tuple:
    """Construct an *unauthenticated* EvengClient.

    Each parameter falls back to its corresponding environment variable when
    not supplied explicitly, so callers can override only what they need.

    Returns ``(client, username, password)``.
    """
    _host     = host     or os.getenv("EVE_HOST")
    _username = username or os.getenv("EVE_USERNAME")
    _password = password or os.getenv("EVE_PASSWORD")
    _protocol = protocol or os.getenv("EVE_PROTOCOL", "http")
    _ssl_verify = (
        ssl_verify
        if ssl_verify is not None
        else os.getenv("EVE_SSL_VERIFY", "true").lower() == "true"
    )
    _disable_warnings = (
        os.getenv("EVE_DISABLE_INSECURE_WARNINGS", "false").lower() == "true"
    )

    if not all([_host, _username, _password]):
        raise EnvironmentError(
            "host, username, and password are required "
            "(pass explicitly or set EVE_HOST / EVE_USERNAME / EVE_PASSWORD)."
        )

    if port is None:
        port_str = os.getenv("EVE_PORT")
        _port = int(port_str) if port_str else None
    else:
        _port = port

    client = EvengClient(
        host=_host,
        protocol=_protocol,
        port=_port,
        ssl_verify=_ssl_verify,
        disable_insecure_warnings=_disable_warnings,
    )
    return client, _username, _password


def _get_client() -> EvengClient:
    """Return a cached, authenticated EvengClient instance.

    Login flow
    ----------
    1. Return the in-memory singleton if it already exists.
    2. Build a new client from env vars, then try to restore the saved session.
    3. If the saved session is still valid, skip re-login.
    4. Otherwise perform a fresh username/password login and persist the new
       session cookies to disk for future calls.
    """
    global _client
    if _client is not None:
        return _client

    client, username, password = _build_client()

    if not _restore_session(client):
        _logger.info("Logging in to EVE-NG as %s ...", username)
        client.login(username=username, password=password)
        _save_session(client)
        _logger.info("Login successful — session saved to %s", _SESSION_FILE)

    _client = client
    return _client


def _api():
    """Return the EvengApi instance from the authenticated client."""
    return _get_client().api


# ---------------------------------------------------------------------------
# Public session-management helpers
# ---------------------------------------------------------------------------

def login(
    host: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    protocol: Optional[str] = None,
    port: Optional[int] = None,
    ssl_verify: Optional[bool] = None,
) -> Dict:
    """Authenticate against EVE-NG and replace the active session.

    Any parameter not supplied falls back to the corresponding environment
    variable, so partial overrides are supported (e.g. only change the host).
    On success the new session is cached in-memory and persisted to disk.

    :param host:       EVE-NG server hostname or IP
    :param username:   Login username
    :param password:   Login password
    :param protocol:   'http' or 'https' (default: env / 'http')
    :param port:       Server port (default: env / protocol default)
    :param ssl_verify: Whether to verify TLS certificates (default: env / True)
    :returns: Dict with connection details (password is never echoed back).
    """
    global _client

    # Always start with a clean slate so stale cookies don't interfere
    if _SESSION_FILE.exists():
        _SESSION_FILE.unlink()
    _client = None

    client, _username, _password = _build_client(
        host=host,
        username=username,
        password=password,
        protocol=protocol,
        port=port,
        ssl_verify=ssl_verify,
    )

    _logger.info("Logging in to EVE-NG at %s as %s ...", client.host, _username)
    client.login(username=_username, password=_password)
    _save_session(client)
    _client = client
    _logger.info("Login successful — session saved to %s", _SESSION_FILE)

    return {
        "status": "logged_in",
        "host": client.host,
        "username": _username,
        "protocol": client.protocol,
        "session_file": str(_SESSION_FILE),
    }


def reset_session() -> Dict:
    """Invalidate the current session (in-memory + on-disk) and force a fresh
    login on the next API call.

    Call this when EVE-NG returns authentication errors or after changing
    credentials.
    """
    global _client
    _client = None
    if _SESSION_FILE.exists():
        _SESSION_FILE.unlink()
        _logger.info("Session file %s deleted", _SESSION_FILE)
    _logger.info("Session reset — next API call will trigger a fresh login")
    return {"status": "session_reset", "session_file": str(_SESSION_FILE)}


def logout() -> Dict:
    """Call the EVE-NG logout endpoint, then reset the local session.

    This invalidates the server-side session in addition to clearing local
    cookies.
    """
    global _client
    if _client is not None:
        try:
            _client.logout()
            _logger.info("Logged out from EVE-NG successfully")
        except Exception as exc:
            _logger.warning("Logout call failed: %s", exc)
    return reset_session()



# ===========================================================================
# Server / System
# ===========================================================================

def get_server_status() -> Dict:
    """Return EVE-NG server status."""
    return normalise_response(_api().get_server_status())


# ===========================================================================
# Node Templates
# ===========================================================================

def list_node_templates() -> Dict:
    """List all available node templates on the EVE-NG server."""
    return normalise_response(_api().list_node_templates())


def node_template_detail(node_type: str) -> Dict:
    """Return details for a single node template including available images.

    :param node_type: e.g. 'iosv', 'csr1000v', 'veos', ...
    """
    return normalise_response(_api().node_template_detail(node_type))


# ===========================================================================
# Users
# ===========================================================================

def list_users() -> Dict:
    """Return list of all EVE-NG users."""
    return normalise_response(_api().list_users())


def list_user_roles() -> Dict:
    """Return available user roles."""
    return normalise_response(_api().list_user_roles())


def get_user(username: str) -> Dict:
    """Return details for a specific user.

    :param username: EVE-NG username
    """
    return normalise_response(_api().get_user(username))


def add_user(
    username: str,
    password: str,
    role: str = "user",
    name: str = "",
    email: str = "",
    expiration: str = "-1",
) -> Dict:
    """Create a new EVE-NG user.

    :param username: unique alphanumeric login name
    :param password: login password
    :param role: 'user' or 'admin' (default: 'user')
    :param name: full display name
    :param email: user email address
    :param expiration: UNIX timestamp or '-1' for never
    """
    return normalise_response(
        _api().add_user(
            username=username,
            password=password,
            role=role,
            name=name,
            email=email,
            expiration=expiration,
        )
    )


def edit_user(username: str, data: dict) -> Dict:
    """Update an existing user's details.

    :param username: target user
    :param data: dict of fields to update (e.g. {'email': 'new@example.com'})
    """
    return normalise_response(_api().edit_user(username=username, data=data))


def delete_user(username: str) -> Dict:
    """Delete a user from EVE-NG.

    :param username: username to delete
    """
    return normalise_response(_api().delete_user(username))


# ===========================================================================
# Networks
# ===========================================================================

def list_networks() -> Dict:
    """List available network types (bridge, pnet0-pnet9, ...)."""
    return normalise_response(_api().list_networks())


# ===========================================================================
# Folders
# ===========================================================================

def list_folders() -> Dict:
    """List all folders on the EVE-NG server including contained labs."""
    return normalise_response(_api().list_folders())


def get_folder(folder: str) -> Dict:
    """Return details for a specific folder.

    :param folder: folder path (e.g. 'my_labs')
    """
    return normalise_response(_api().get_folder(folder))


# ===========================================================================
# Labs
# ===========================================================================

def get_lab(path: str) -> Dict:
    """Return details for a single lab.

    :param path: lab path including parent folder (e.g. '/my_folder/my_lab')
    """
    return normalise_response(_api().get_lab(path))


def create_lab(
    name: str,
    path: str = "/",
    version: str = "1",
    description: str = "",
    author: str = "",
    body: str = "",
) -> Dict:
    """Create a new lab on the EVE-NG server.

    :param name: lab name (no .unl extension)
    :param path: destination folder path (default: '/')
    :param version: lab version string (default: '1')
    :param description: short description
    :param author: lab author
    :param body: detailed lab body / notes
    """
    return normalise_response(
        _api().create_lab(
            name=name,
            path=path,
            version=version,
            description=description,
            author=author,
            body=body,
        )
    )


def edit_lab(path: str, data: dict) -> Dict:
    """Edit lab metadata.

    :param path: lab path including parent folder
    :param data: dict of fields to update
    """
    return normalise_response(_api().edit_lab(path=path, data=data))


def delete_lab(path: str) -> Dict:
    """Delete a lab from the EVE-NG server.

    :param path: lab path including parent folder
    """
    return normalise_response(_api().delete_lab(path))


def close_lab(path: str) -> Dict:
    """Close an open lab (stops all nodes and removes it from memory).

    :param path: lab path including parent folder
    """
    return normalise_response(_api().close_lab(path))


def lock_lab(path: str) -> Dict:
    """Lock a lab to prevent editing.

    :param path: lab path including parent folder
    """
    return normalise_response(_api().lock_lab(path))


def unlock_lab(path: str) -> Dict:
    """Unlock a previously locked lab.

    :param path: lab path including parent folder
    """
    return normalise_response(_api().unlock_lab(path))


def export_lab(path: str, filename: str = None) -> Dict:
    """Export a lab as a .zip / .unl file.

    :param path: lab path on EVE-NG server
    :param filename: local filename to save the exported file (optional)
    """
    success, saved_as = _api().export_lab(path=path, filename=filename)
    return {"success": success, "filename": saved_as}


def import_lab(path: str, folder: str = "/") -> Dict:
    """Import a lab from a local .unl / .zip file.

    :param path: local file path of the .unl/.zip to import
    :param folder: destination folder on the server (default: '/')
    """
    return normalise_response(_api().import_lab(path=path, folder=folder))


def get_lab_topology(path: str) -> Dict:
    """Return the topology (nodes + links) for a lab.

    :param path: lab path including parent folder
    """
    return normalise_response(_api().get_lab_topology(path))


def export_all_nodes(path: str) -> Dict:
    """Export (save) startup configs of all nodes in a lab.

    :param path: lab path including parent folder
    """
    return normalise_response(_api().export_all_nodes(path))


def get_lab_pictures(path: str) -> Dict:
    """Return all pictures / diagrams associated with a lab.

    :param path: lab path including parent folder
    """
    return normalise_response(_api().get_lab_pictures(path))


def get_lab_picture_details(path: str, picture_id: int) -> Dict:
    """Return details for a specific lab picture.

    :param path: lab path including parent folder
    :param picture_id: numeric picture ID
    """
    return normalise_response(_api().get_lab_picture_details(path, picture_id))


# ===========================================================================
# Lab Networks
# ===========================================================================

def list_lab_networks(path: str) -> Dict:
    """List all networks defined within a lab.

    :param path: lab path including parent folder
    """
    return normalise_response(_api().list_lab_networks(path))


def get_lab_network(path: str, net_id: int) -> Dict:
    """Return details for a specific lab network.

    :param path: lab path including parent folder
    :param net_id: network ID
    """
    return normalise_response(_api().get_lab_network(path, net_id))


def get_lab_network_by_name(path: str, name: str) -> Dict:
    """Return a lab network by its name.

    :param path: lab path including parent folder
    :param name: network name
    """
    return normalise_response(_api().get_lab_network_by_name(path, name))


def add_lab_network(
    path: str,
    network_type: str,
    name: str = "",
    left: int = 0,
    top: int = 0,
    visibility: int = 1,
) -> Dict:
    """Add a new network to a lab.

    :param path: lab path including parent folder
    :param network_type: network type (e.g. 'bridge', 'pnet0')
    :param name: network name/label
    :param left: horizontal position on canvas
    :param top: vertical position on canvas
    :param visibility: 1 = visible, 0 = hidden
    """
    return normalise_response(
        _api().add_lab_network(
            path,
            network_type=network_type,
            name=name,
            left=left,
            top=top,
            visibility=visibility,
        )
    )


def edit_lab_network(path: str, net_id: int, data: dict) -> Dict:
    """Edit an existing lab network.

    :param path: lab path including parent folder
    :param net_id: network ID to edit
    :param data: dict of fields to update
    """
    return normalise_response(_api().edit_lab_network(path, net_id, data=data))


def list_lab_links(path: str) -> Dict:
    """List all links in a lab.

    :param path: lab path including parent folder
    """
    return normalise_response(_api().list_lab_links(path))


# ===========================================================================
# Nodes
# ===========================================================================

def list_nodes(path: str) -> Dict:
    """List all nodes in a lab.

    :param path: lab path including parent folder
    """
    return normalise_response(_api().list_nodes(path))


def get_node(path: str, node_id: int) -> Dict:
    """Return details for a specific node.

    :param path: lab path including parent folder
    :param node_id: numeric node ID
    """
    return normalise_response(_api().get_node(path, node_id))


def get_node_by_name(path: str, name: str) -> Dict:
    """Return a node by its name.

    :param path: lab path including parent folder
    :param name: node name/label
    """
    return normalise_response(_api().get_node_by_name(path, name))


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

    :param path: lab path including parent folder
    :param node_type: node type (e.g. 'qemu', 'dynamips')
    :param template: node template name (e.g. 'iosv', 'veos')
    :param name: node label/name
    :param image: specific image to use (empty = template default)
    :param left: horizontal canvas position
    :param top: vertical canvas position
    :param ram: RAM in MB (default: 512)
    :param cpu: number of vCPUs (default: 1)
    :param ethernet: number of Ethernet interfaces (default: 4)
    :param serial: number of Serial interfaces (default: 0)
    :param console: console type - 'telnet' | 'vnc' (default: 'telnet')
    :param delay: startup delay in seconds (default: 0)
    :param icon: icon filename for canvas display
    """
    return normalise_response(
        _api().add_node(
            path,
            node_type=node_type,
            template=template,
            name=name,
            image=image,
            left=left,
            top=top,
            ram=ram,
            cpu=cpu,
            ethernet=ethernet,
            serial=serial,
            console=console,
            delay=delay,
            icon=icon,
        )
    )


def delete_node(path: str, node_id: int) -> Dict:
    """Delete a node from a lab.

    :param path: lab path including parent folder
    :param node_id: numeric node ID to delete
    """
    return normalise_response(_api().delete_node(path, node_id))


def start_node(path: str, node_id: int) -> Dict:
    """Start a single node.

    :param path: lab path including parent folder
    :param node_id: numeric node ID
    """
    return normalise_response(_api().start_node(path, node_id))


def stop_node(path: str, node_id: int) -> Dict:
    """Stop (halt) a single node.

    :param path: lab path including parent folder
    :param node_id: numeric node ID
    """
    return normalise_response(_api().stop_node(path, node_id))


def start_all_nodes(path: str) -> Dict:
    """Start all nodes in a lab.

    :param path: lab path including parent folder
    """
    return normalise_response(_api().start_all_nodes(path))


def stop_all_nodes(path: str) -> Dict:
    """Stop all nodes in a lab.

    :param path: lab path including parent folder
    """
    return normalise_response(_api().stop_all_nodes(path))


def wipe_node(path: str, node_id: int) -> Dict:
    """Wipe (reset) a single node's startup config.

    :param path: lab path including parent folder
    :param node_id: numeric node ID
    """
    return normalise_response(_api().wipe_node(path, node_id))


def wipe_all_nodes(path: str) -> Dict:
    """Wipe startup configs for all nodes in a lab.

    :param path: lab path including parent folder
    """
    return normalise_response(_api().wipe_all_nodes(path))


def export_node(path: str, node_id: int) -> Dict:
    """Export (save) startup config of a single node.

    :param path: lab path including parent folder
    :param node_id: numeric node ID
    """
    return normalise_response(_api().export_node(path, node_id))


def enable_node_config(path: str, node_id: int) -> Dict:
    """Enable startup config for a node.

    :param path: lab path including parent folder
    :param node_id: numeric node ID
    """
    return normalise_response(_api().enable_node_config(path, node_id))


def get_node_interfaces(path: str, node_id: int) -> Dict:
    """Return the interfaces of a specific node.

    :param path: lab path including parent folder
    :param node_id: numeric node ID
    """
    return normalise_response(_api().get_node_interfaces(path, node_id))


def get_node_configs(path: str) -> Dict:
    """Return all node startup configs in a lab.

    :param path: lab path including parent folder
    """
    return normalise_response(_api().get_node_configs(path))


def get_node_config_by_id(path: str, config_id: int) -> Dict:
    """Return the startup config for a specific node by config ID.

    :param path: lab path including parent folder
    :param config_id: configuration ID
    """
    return normalise_response(_api().get_node_config_by_id(path, config_id))


def upload_node_config(path: str, node_id: int, config: str, enable: bool = True) -> Dict:
    """Upload a startup config to a node.

    :param path: lab path including parent folder
    :param node_id: numeric node ID
    :param config: startup config text
    :param enable: enable the startup config after upload (default: True)
    """
    res = _api().upload_node_config(path, node_id, config=config)
    if enable:
        _api().enable_node_config(path, node_id)
    return normalise_response(res)


# ===========================================================================
# Node Connections
# ===========================================================================

def connect_node(path: str, node_id: int, connections: dict) -> Dict:
    """Connect node interfaces to networks or other nodes.

    :param path: lab path including parent folder
    :param node_id: source node ID
    :param connections: dict mapping interface index to network/node destination
    """
    return normalise_response(_api().connect_node(path, node_id, connections))


def connect_node_to_cloud(
    path: str, node_id: int, node_interface: int, cloud_id: int
) -> Dict:
    """Connect a node interface to a cloud/bridge network.

    :param path: lab path including parent folder
    :param node_id: source node ID
    :param node_interface: interface index on the node
    :param cloud_id: target cloud/bridge network ID
    """
    return normalise_response(
        _api().connect_node_to_cloud(path, node_id, node_interface, cloud_id)
    )


def connect_node_to_node(
    path: str,
    src_node_id: int,
    src_interface: int,
    dst_node_id: int,
    dst_interface: int,
) -> Dict:
    """Create a point-to-point link between two nodes.

    :param path: lab path including parent folder
    :param src_node_id: source node ID
    :param src_interface: source interface index
    :param dst_node_id: destination node ID
    :param dst_interface: destination interface index
    """
    src_node = get_node(path, src_node_id)
    dst_node = get_node(path, dst_node_id)

    src_name = src_node.get("data", {}).get("name")
    dst_name = dst_node.get("data", {}).get("name")

    if not src_name or not dst_name:
        return {"code": 404, "status": "fail", "message": "Source or destination node not found"}

    src_ints = get_node_interfaces(path, src_node_id).get("data", {}).get("ethernet", [])
    dst_ints = get_node_interfaces(path, dst_node_id).get("data", {}).get("ethernet", [])

    if src_interface < 0 or src_interface >= len(src_ints):
        return {"code": 400, "status": "fail", "message": f"Invalid source interface index {src_interface}"}
    if dst_interface < 0 or dst_interface >= len(dst_ints):
        return {"code": 400, "status": "fail", "message": f"Invalid destination interface index {dst_interface}"}

    src_label = src_ints[src_interface].get("name")
    dst_label = dst_ints[dst_interface].get("name")

    return normalise_response(
        _api().connect_node_to_node(
            path, src_name, src_label, dst_name, dst_label
        )
    )


def connect_p2p_interface(
    path: str, src_node_id: int, src_interface: int, dst_node_id: int, dst_interface: int
) -> Dict:
    """Connect a P2P interface between two nodes (EVE-NG Pro).

    :param path: lab path including parent folder
    :param src_node_id: source node ID
    :param src_interface: source interface index
    :param dst_node_id: destination node ID
    :param dst_interface: destination interface index
    """
    return normalise_response(
        _api().connect_p2p_interface(
            path, src_node_id, src_interface, dst_node_id, dst_interface
        )
    )

# ===========================================================================
# Remote Access / Workarounds
# ===========================================================================

def bypass_initial_config(path: str, node_id: int) -> Dict:
    """Connect to a node's console via raw socket and bypass the initial
    configuration dialog (e.g. 'Would you like to enter the initial configuration dialog? [yes/no]:').

    :param path: lab path including parent folder
    :param node_id: numeric node ID
    """
    
    node_resp = get_node(path, node_id)
    if not node_resp or node_resp.get("status") != "success":
        return {"code": 404, "status": "fail", "message": f"Could not retrieve node {node_id}"}
    
    node_data = node_resp.get("data", {})
    url_str = node_data.get("url", "")
    port = node_data.get("port")
    
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
        return {"code": 400, "status": "fail", "message": "Could not resolve console port for node"}

    client = _get_client()
    host = client.host
    
    _logger.info("Bypassing initial config for node %s at %s:%s", node_id, host, port)
    
    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            sock.settimeout(5)
            # Give the banner a moment to print
            time.sleep(2)
            
            # Read whatever is there
            try:
                data = sock.recv(4096).decode("utf-8", errors="ignore")
                _logger.debug("Initial socket read: %r", data)
            except socket.timeout:
                data = ""
            
            # Send 'no' and newlines
            sock.sendall(b"no\r\n")
            time.sleep(1)
            sock.sendall(b"\r\n\r\n\r\n")
            time.sleep(1)
            
            # Read result
            try:
                data2 = sock.recv(4096).decode("utf-8", errors="ignore")
                _logger.debug("Socket read after bypass: %r", data2)
            except socket.timeout:
                pass
                
        return {"status": "success", "message": "Bypass command sent. Please wait 3-5 minutes before executing further commands."}
    except Exception as e:
        _logger.error("Error bypassing initial config: %s", e)
        return {"code": 500, "status": "fail", "message": str(e)}
