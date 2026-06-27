---
name: EVE-NG Lab Management
version: 1.0
description: Manages the lifecycle of EVE-NG labs, including creation, retrieval, modification, deletion, export, import, and topology/picture retrieval.
usage: Use this skill when asked to create, duplicate, inspect, export/import, lock/unlock, or retrieve lab layout details.
dependencies: eve-mcp toolset (specifically `eve-mcp:create_lab`, `eve-mcp:get_lab`, `eve-mcp:edit_lab`, `eve-mcp:delete_lab`, `eve-mcp:close_lab`, `eve-mcp:lock_lab`, `eve-mcp:unlock_lab`, `eve-mcp:export_lab`, `eve-mcp:import_lab`, `eve-mcp:get_lab_topology`, `eve-mcp:export_all_nodes`, `eve-mcp:get_lab_pictures`, `eve-mcp:get_lab_picture_details`)
---

## Objective
To efficiently handle lab configurations, exports, topology information, and general lab lifecycle management within the EVE-NG environment.

## Step-by-Step Instructions

1. **Verify Prerequisites:**
   * Always ensure you are logged in using the `eve-authentication` skill before performing any lab operations.

2. **Retrieve Lab Details:**
   * Use `get_lab` to fetch basic details of a lab by path (e.g., `/TestLab.unet`).
   * Use `get_lab_topology` to fetch the network topology, nodes, and links inside the lab.

3. **Create or Modify a Lab:**
   * When creating a lab via `create_lab`, ensure you specify the `path` (including filename with `.unet` extension), `name`, and optional description.
   * To edit properties (such as description or layout), use `edit_lab`.

4. **Import/Export & Backup:**
   * Use `export_lab` to get the lab package or configuration.
   * Use `import_lab` to restore or import a `.zip` / `.unl` lab export to the server.
   * Use `export_all_nodes` to export startup/saved configurations of all nodes inside the lab.

5. **Locking & Locking Status:**
   * Use `lock_lab` or `unlock_lab` to control edit permissions on the lab.
   * Call `close_lab` when you are done working with a lab so that resources are freed.

## Context & Tools
- `eve-mcp:get_lab`: Fetch lab configuration metadata.
- `eve-mcp:create_lab`: Create a new lab at a specified path.
- `eve-mcp:edit_lab`: Modify an existing lab.
- `eve-mcp:delete_lab`: Permanently delete a lab.
- `eve-mcp:get_lab_topology`: Retrieve nodes, links, and connections in a lab.
- `eve-mcp:export_lab`: Export a lab layout.
- `eve-mcp:import_lab`: Import a lab structure.
- `eve-mcp:export_all_nodes`: Export node startup configs.
- `eve-mcp:close_lab`: Close an active lab.
- `eve-mcp:lock_lab` / `eve-mcp:unlock_lab`: Lock or unlock lab editing.
- `eve-mcp:get_lab_pictures` / `eve-mcp:get_lab_picture_details`: Retrieve lab topology images and coordinates.
