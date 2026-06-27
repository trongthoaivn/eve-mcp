---
name: EVE-NG Node Management
version: 1.0
description: Manages individual nodes within a lab, including adding, starting, stopping, wiping, exporting configs, and configuring interfaces.
usage: Use this skill when asked to control node state (start/stop/wipe), add nodes, fetch node interfaces, or manage node startup configurations.
dependencies: eve-mcp toolset (specifically `eve-mcp:list_nodes`, `eve-mcp:get_node`, `eve-mcp:get_node_by_name`, `eve-mcp:add_node`, `eve-mcp:delete_node`, `eve-mcp:start_node`, `eve-mcp:stop_node`, `eve-mcp:start_all_nodes`, `eve-mcp:stop_all_nodes`, `eve-mcp:wipe_node`, `eve-mcp:wipe_all_nodes`, `eve-mcp:export_node`, `eve-mcp:enable_node_config`, `eve-mcp:get_node_interfaces`, `eve-mcp:get_node_configs`, `eve-mcp:get_node_config_by_id`, `eve-mcp:upload_node_config`)
---

## Objective
To manage the lifecycle, state, and internal configuration files of network virtual nodes (routers, switches, firewalls, hosts) in an EVE-NG topology.

## Step-by-Step Instructions

1. **Verify Prerequisites:**
   * Log in to EVE-NG using the `eve-authentication` skill before performing node operations.

2. **Add a Node to a Lab:**
   * When using `add_node`, you must provide the lab path and the node configuration parameters (template, name, CPU, RAM, image, etc.).
   * Check template availability and details first via user/system admin tools if needed.

3. **Retrieve Node Information:**
   * Use `list_nodes` to get a list of all nodes in a specific lab.
   * Use `get_node` or `get_node_by_name` to retrieve specific node configurations.
   * Use `get_node_interfaces` to view the list of interfaces (Ethernet, Serial, etc.) on the node.

4. **Control Node Power & State:**
   * To boot a node, use `start_node`. To boot all nodes, use `start_all_nodes`.
   * To shut down a node, use `stop_node`. To stop all nodes, use `stop_all_nodes`.
   * To clear a node's NVRAM / configuration back to default, use `wipe_node` (node must be stopped first). Use `wipe_all_nodes` for the entire lab.

5. **Manage Node Startup Configurations:**
   * Use `get_node_configs` to list configurations stored on the node.
   * Use `get_node_config_by_id` or `upload_node_config` to read/write startup configurations.
   * Use `enable_node_config` to enable/disable startup configurations for a node.
   * Use `export_node` to export the current running config of a node to EVE-NG.

## Context & Tools
- `eve-mcp:list_nodes`: List nodes in a lab.
- `eve-mcp:get_node` / `eve-mcp:get_node_by_name`: Retrieve node configuration.
- `eve-mcp:add_node`: Add a new node.
- `eve-mcp:delete_node`: Delete a node from a lab.
- `eve-mcp:start_node` / `eve-mcp:stop_node`: Start or stop a node.
- `eve-mcp:start_all_nodes` / `eve-mcp:stop_all_nodes`: Control all nodes.
- `eve-mcp:wipe_node` / `eve-mcp:wipe_all_nodes`: Clear startup configuration.
- `eve-mcp:get_node_interfaces`: Get interfaces on a node.
- `eve-mcp:upload_node_config`: Write config file to a node.
- `eve-mcp:enable_node_config`: Enable startup config file.
- `eve-mcp:export_node`: Export node running config.
