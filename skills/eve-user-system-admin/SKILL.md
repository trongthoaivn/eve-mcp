---
name: EVE-NG User and System Administration
version: 1.0
description: Manages server status check, node templates availability, folder structure navigation, and user accounts management.
usage: Use this skill when asked to check EVE-NG health, list node templates, navigate lab folders, or manage user accounts and roles.
dependencies: eve-mcp toolset (specifically `eve-mcp:get_server_status`, `eve-mcp:list_node_templates`, `eve-mcp:node_template_detail`, `eve-mcp:list_folders`, `eve-mcp:get_folder`, `eve-mcp:list_users`, `eve-mcp:list_user_roles`, `eve-mcp:get_user`, `eve-mcp:add_user`, `eve-mcp:edit_user`, `eve-mcp:delete_user`)
---

## Objective
To manage platform settings, check server capacity, browse folders, verify template configurations, and administer user access/permissions on the EVE-NG server.

## Step-by-Step Instructions

1. **Verify Prerequisites:**
   * Always authenticate using the `eve-authentication` skill prior to querying system or user administrative tools.

2. **Check Server Capacity & Templates:**
   * Call `get_server_status` to monitor server load (CPU, memory, disk, and version).
   * Use `list_node_templates` to see which vendor/device templates are supported (e.g. iol, qemu, dynamips).
   * Retrieve specific requirements for a template using `node_template_detail`.

3. **Navigate Folders:**
   * EVE-NG structures labs in folders. Use `list_folders` to view directories on the server.
   * Use `get_folder` to fetch information and nested content of a specific folder.

4. **Manage Users & Security:**
   * List existing accounts using `list_users`.
   * Look up role definitions using `list_user_roles`.
   * Add new users using `add_user`, edit user parameters with `edit_user`, or remove access using `delete_user`.

## Context & Tools
- `eve-mcp:get_server_status`: Check system health and resource consumption.
- `eve-mcp:list_node_templates`: List available node images templates.
- `eve-mcp:node_template_detail`: Retrieve requirements for a node template.
- `eve-mcp:list_folders` / `eve-mcp:get_folder`: Directory browsing.
- `eve-mcp:list_users` / `eve-mcp:get_user`: View users profiles.
- `eve-mcp:add_user` / `eve-mcp:edit_user` / `eve-mcp:delete_user`: Perform CRUD on user accounts.
