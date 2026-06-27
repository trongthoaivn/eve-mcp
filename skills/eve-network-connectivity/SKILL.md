---
name: EVE-NG Network and Connectivity Management
version: 1.0
description: Handles adding lab networks, connecting nodes to networks (bridges/clouds), connecting nodes directly, and configuring point-to-point interfaces.
usage: Use this skill when asked to connect nodes, link a node to an external cloud or management network, or manage network connections within a lab.
dependencies: eve-mcp toolset (specifically `eve-mcp:list_networks`, `eve-mcp:list_lab_networks`, `eve-mcp:get_lab_network`, `eve-mcp:get_lab_network_by_name`, `eve-mcp:add_lab_network`, `eve-mcp:edit_lab_network`, `eve-mcp:list_lab_links`, `eve-mcp:connect_node`, `eve-mcp:connect_node_to_cloud`, `eve-mcp:connect_node_to_node`, `eve-mcp:connect_p2p_interface`)
---

## Objective
To configure, retrieve, and connect network interfaces, links, bridges, and external clouds to form a complete network topology.

## Step-by-Step Instructions

1. **Verify Prerequisites:**
   * Ensure login has succeeded using the `eve-authentication` skill before performing connectivity modifications.

2. **Understand Lab Networks & Links:**
   * Use `list_lab_networks` to view all network networks configured within a lab.
   * Use `list_lab_links` to view current active links/cables connecting nodes to networks or other nodes.
   * Use `list_networks` to list global network templates available on the EVE-NG server (e.g. pnet0, pnet1, bridge, etc.).

3. **Add and Edit Lab Networks:**
   * Use `add_lab_network` to add a new network interface/bridge inside the lab.
   * Use `edit_lab_network` to modify network properties (e.g., name, type, coordinates).

4. **Connect Nodes:**
   * Use `connect_node_to_node` to connect an interface of one node directly to an interface of another node (P2P link).
   * Use `connect_node_to_cloud` or `connect_node` to link a node interface to a cloud network (e.g., linking a management port to `pnet0` for external SSH access).
   * Use `connect_p2p_interface` to specifically link interface IDs directly.

## Context & Tools
- `eve-mcp:list_networks`: List EVE-NG server system network types (pnet/bridge).
- `eve-mcp:list_lab_networks`: List networks defined inside the active lab.
- `eve-mcp:add_lab_network`: Add a network object to the lab.
- `eve-mcp:edit_lab_network`: Edit a lab network's settings.
- `eve-mcp:list_lab_links`: List active node/network interconnections.
- `eve-mcp:connect_node_to_node`: Create a direct link between two nodes.
- `eve-mcp:connect_node_to_cloud`: Connect a node interface to a system cloud network.
- `eve-mcp:connect_p2p_interface`: Connect two specific interfaces directly.
