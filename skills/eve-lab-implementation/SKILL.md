---
name: EVE-NG Lab Implementation
version: 2.0
description: Guides creating labs by generating UNL topology files and importing them via eve-mcp:import_lab, then parsing topology inputs, validating configuration requirements, drafting commands, handling errors, and executing configurations.
usage: Use this skill when creating a new lab from scratch (topology design → UNL generation → import), or when modifying an existing lab based on input requirements like topology diagrams, text specifications, XML descriptions, or configuration requests.
dependencies: eve-authentication, eve-lab-management, eve-node-management, eve-network-connectivity, eve-remote-execution, cisco-ios-patterns
---

## Objective

To create labs by synthesising topology and device requirements into a UNL file and importing it via `eve-mcp:import_lab`, then optionally apply device configurations, handle execution failures gracefully, and verify the resulting network state.

---

## ⛔ Mandatory Error Handling Principle (Applies to ALL Phases)

> **Any error that occurs during execution MUST be handled according to the following procedure — NO exceptions.**

When an error is encountered (MCP tool error, server error, network error, validation error, or any other error):

1. **STOP IMMEDIATELY** — Do not continue executing any subsequent steps.
2. **NOTIFY THE USER** — Clearly present:
   * What the specific error is (error message, error code if available).
   * Which step was being executed when the error occurred.
   * Possible root cause(s) of the error.
3. **PROPOSE RESOLUTION OPTIONS** — Provide at least one option:
   * How to fix the error and retry.
   * Alternative approach (if available).
   * Skip the failed step and continue with remaining steps (if feasible).
   * Abort the entire process and rollback (if necessary).
4. **WAIT FOR USER DECISION** — **Do NOT continue on your own**, **do NOT auto-retry**, **do NOT write scripts to bypass the error**. Only proceed once the user has confirmed a resolution approach.

**Strictly prohibited:**
* Silently ignoring or swallowing errors.
* Automatically retrying without user consent.
* Writing custom scripts or modifying workspace code to bypass MCP tool errors.
* Proceeding to subsequent steps when a prior step has failed.

---

## Phase 1 — Lab Creation (UNL Generation & Import)

Use this phase when a **new lab** needs to be created on the EVE-NG server.

### Step 1: Gather & Confirm Topology Requirements

* Review all provided inputs (topology images, text notes, structured files, verbal descriptions).
* Identify and compile a complete list of:
  * **Devices:** name, type/template (e.g. `viosl2`, `iosv`, `csr1000v`, `veos`), number of Ethernet/Serial interfaces, CPU, RAM, icon, console type.
  * **Networks:** point-to-point links, shared segments (bridges), cloud connections.
  * **Connections:** which interface on which device connects to which network.
  * **Initial configs (optional):** startup configs to embed in the UNL (base64-encoded).
  * **Canvas layout:** approximate `left`/`top` positions for nodes and networks.
* **Reconfirm with User:** Present the compiled device list and connection matrix to the user and get explicit approval before proceeding.

### Step 2: Validate Device Templates & Images on the Server

> **⚠ CRITICAL — Do NOT skip this step.**

Before generating the UNL file, you **MUST** verify that every required device template and image exists on the EVE-NG server:

1. Call `eve-mcp:list_node_templates` to get all available templates.
2. For each unique template required by the topology, call `eve-mcp:node_template_detail` with the `node_type` to check available images.
3. **If a required template is missing or has no usable image:**
   * **STOP immediately.**
   * Notify the user with a clear message listing the missing template(s) and/or image(s).
   * Provide guidance on how to install the missing template/image on the EVE-NG server.
   * **Do NOT proceed** until the user confirms the template/image has been installed, or provides an alternative template to use.

Example notification:
```
⚠ The following device template(s)/image(s) are not available on the EVE-NG server:

  - Template: "viosl2" — Image: "viosl2-adventerprisek9-m-15.0-20140605" → NOT FOUND
  - Template: "iosv" — No images available

Please install the required images on the EVE-NG server and confirm,
or specify alternative templates/images to use.
```

### Step 3: Generate the UNL File

Once all templates/images are confirmed available, generate a `.unl` XML file following this structure:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<lab name="LAB_NAME" id="UNIQUE_UUID" version="1" author="AUTHOR_NAME">
  <description>Lab description text</description>
  <body>Detailed lab documentation in Markdown format (optional)</body>
  <topology>
    <nodes>
      <!-- One <node> per device -->
      <node id="NODE_ID" name="HOSTNAME" type="qemu" template="TEMPLATE"
            image="IMAGE_NAME" console="telnet" cpu="CPU_COUNT"
            ram="RAM_MB" ethernet="ETH_COUNT" uuid="UNIQUE_UUID"
            delay="0" icon="ICON.png" config="0_OR_1"
            left="X_POS" top="Y_POS">
        <!-- One <interface> per connected interface -->
        <interface id="IF_ID" name="IF_NAME" type="ethernet"
                   network_id="NET_ID"/>
      </node>
    </nodes>
    <networks>
      <!-- One <network> per L2 segment or point-to-point link -->
      <network id="NET_ID" type="bridge" name="NET_LABEL"
               left="X_POS" top="Y_POS"/>
    </networks>
  </topology>
  <objects>
    <configs>
      <!-- Optional: base64-encoded startup configs, keyed by node id -->
      <config id="NODE_ID">BASE64_ENCODED_CONFIG</config>
    </configs>
  </objects>
</lab>
```

**UNL Generation Rules:**

| Field | Rule |
|---|---|
| `lab.id`, `node.uuid` | Generate a unique UUID v4 for each |
| `node.id` | Sequential integer starting from 1 |
| `node.type` | Usually `qemu` for virtual devices; use `dynamips` or `iol` when appropriate |
| `node.template` | Must match a template confirmed in Step 2 |
| `node.image` | Must match an image confirmed in Step 2 |
| `node.ethernet` | Total number of Ethernet interfaces the node should have (must be ≥ the highest interface id + 1) |
| `interface.id` | Zero-based index matching the device's interface numbering |
| `interface.network_id` | References a `<network>` id to form the connection |
| `network.type` | `bridge` for shared segments; for point-to-point links between exactly two interfaces, `bridge` is also used |
| `config` attribute on `<node>` | Set to `1` if a startup config is provided in `<objects><configs>`, otherwise `0` |
| Startup configs | Base64-encode the full startup config text and place it in `<config id="NODE_ID">` |

**Canvas Layout Guidelines:**
* Space nodes at least 150px apart horizontally and vertically.
* Place network labels between the nodes they connect.
* Use logical groupings (e.g., core switches at top, access at bottom).

### Step 4: Save, Zip & Import the Lab File

1. Save the generated UNL content to a temporary `.unl` file in the workspace (e.g., `scratch/lab_name.unl`).
2. **Present the UNL file to the user** for review.
3. **Zip the `.unl` file:** The EVE-NG server requires labs to be imported as `.zip` files. You must package the `.unl` file into a `.zip` archive (e.g., `scratch/lab_name.zip`).
4. Call `eve-mcp:import_lab` with:
   * `path`: the local file path of the compressed `.zip` file
   * `folder`: the target folder on the server (default: `/`)
5. Verify the import was successful by checking the response.
6. If the import fails:
   * **STOP immediately.**
   * Notify the user of the exact error.
   * Suggest fixes (e.g., duplicate lab name, permission issues, malformed XML, or incorrect zip packaging).
   * Ask the user how to proceed.

### Step 5: Post-Import Verification

After successful import:
1. Call `eve-mcp:get_lab` to confirm the lab exists on the server.
2. Call `eve-mcp:get_lab_topology` to verify nodes and networks match the intended topology.
3. Call `eve-mcp:list_nodes` to confirm all nodes were created with the correct templates and settings.
4. Report the verification results to the user.

---

## Phase 2 — Lab Configuration (Apply & Verify Device Configs)

Use this phase when configuring devices in an **existing lab** (either just created via Phase 1, or a pre-existing lab).

### Step 1: Parse & Verify Topology Inputs

* Review all provided inputs, which may include topology images, text notes, structured text files, or XML files describing the lab setup.
* Identify and compile a list of all devices, their types/templates, interface connections, IP addressing schemes, and physical/logical topology structure.
* **Reconfirm with User:** Print out the list of discovered devices and connections to verify with the user before proceeding. If any parsed details are ambiguous, unclear, or contain potential errors, stop and explicitly notify the user to seek clarification or corrections.

### Step 2: Validate Configuration Requirements

* Extract and confirm the exact configuration requirements (such as VLAN IDs, IP address blocks, routing protocols like OSPF/BGP, ACLs, and hostnames) to be applied on each node.
* Reconfirm the configuration scope and target state with the user. If there are any ambiguities, gaps, or conflicting requirements, present them to the user for clarification first.
* **Mandatory Command Preview:** Always compile the draft of CLI commands to be executed on each node and present this list to the user for review and explicit approval BEFORE executing any changes.

### Step 3: Establish Verification Criteria

* Define how the final implementation success will be measured (e.g., successful end-to-end pings, routing table convergence, specific `show` command outputs).
* Confirm the verification commands and steps with the user.

### Step 4: Draft and Order Command Lists

* Compile a sequential list of CLI commands to be executed on each node.
* Ensure syntax accuracy and follow best practices (such as saving configurations, using correct subnet masks/wildcard masks, entering correct configuration modes, and using structured blocks).
* Present these planned commands to the user for confirmation.

### Step 5: Execute and Handle MCP Failures

* **Apply Startup Configurations (Preferred for QEMU Nodes):** To ensure QEMU nodes (like Cisco `vios` and `viosl2`) boot up with their configurations applied immediately and to avoid Netmiko prompt-matching, EULA, or setup dialog errors:
  1. Call `eve-mcp:upload_node_config` for each QEMU node to upload and activate (`enable=true`) its startup configuration.
  2. If the nodes are currently running, call `eve-mcp:stop_node` followed by `eve-mcp:wipe_node` to clear previous runtime states, and then `eve-mcp:start_node` to boot them up fresh with the uploaded startup configurations.
* **Start Nodes & Wait:** Use `eve-mcp:start_all_nodes` (or `eve-mcp:start_node`) to boot up all nodes. Wait 3 to 5 minutes for them to fully boot.
* **Configure VPCS Nodes (`vpcs` template):**
  - VPCS nodes are lightweight emulators and do NOT support Cisco-specific initialization commands (like `terminal width` or `terminal length`).
  - When configuring VPCS nodes, set the Netmiko `device_type` to `generic_telnet` (to disable Cisco auto-initializations) and send ONLY VPCS-compatible commands:
    - Request IP via DHCP: `ip dhcp`
    - Save configuration: `save`
    - Verify connectivity: `ping <IP>`
  - If standard Netmiko telnet fails due to prompt scraping issues on VPCS, use raw socket telnet connections as a fallback to execute these simple commands.
* **CRITICAL:** If an MCP tool or server-side error occurs, do not attempt to write custom python scripts or modify the workspace code to bypass the MCP tool. Instead:
  1. Stop immediately.
  2. Notify the user of the exact error and description.
  3. Suggest alternative solutions or methods to fix the issue.
  4. Ask the user for explicit confirmation on whether and how to proceed.

### Step 6: Output Confirmation Results

* Print the verified and confirmed information, including execution logs and successful verification outputs, clearly to the user.

---

## Context & Tools

### Lab Creation (Phase 1)
- `eve-mcp:list_node_templates`: List all available node templates on the server.
- `eve-mcp:node_template_detail`: Check available images for a specific template.
- `eve-mcp:import_lab`: Import a packaged `.zip` file (containing the `.unl` file) to create the lab.
- `eve-mcp:get_lab`: Verify lab was created successfully.
- `eve-mcp:get_lab_topology`: Verify topology matches intended design.
- `eve-mcp:list_nodes`: Verify all nodes were created.

### Lab Configuration (Phase 2)
- `eve-mcp:get_lab_topology`: Get topology data to cross-check.
- `eve-mcp:upload_node_config` / `eve-mcp:enable_node_config`: Upload and enable startup configurations.
- `eve-mcp:remote_config` / `eve-mcp:ssh_configure`: Apply drafted commands.
- `eve-mcp:remote_command` / `eve-mcp:ssh_run_command`: Run verification commands.

## Related Skills
- [EVE-NG Remote Command and Configuration Execution](/skills/eve-remote-execution/SKILL.md)
