---
name: EVE-NG Automatic Authentication
version: 1.0
description: Ensures the agent is authenticated into the EVE-NG platform before performing any environment actions, with an automatic fallback to register the user if login fails.
usage: Trigger this skill automatically as a pre-requisite block before executing any other EVE-NG task or tool call.
dependencies: eve-mcp toolset (specifically `eve-mcp:login` and `eve-mcp:add_user`)
---

## Objective
To successfully establish an authenticated session with the EVE-NG server so that subsequent network automation and lab tasks can be executed without unauthorized errors.

## Step-by-Step Instructions
1. **Initiate Login:** Before running any requested EVE-NG operations, call the `eve-mcp:login` tool to authenticate.
2. **Handle Failure (Fallback Registration):** If the login attempt fails (e.g., due to an unexisting account), immediately call the `eve-mcp:add_user` tool using the following exact profile:
   * **EVE_HOST:** `192.168.112.128`
   * **EVE_USERNAME:** `eve-mcp`
   * **EVE_PASSWORD:** `eve`
3. **Re-authenticate:** Once the user creation process returns a success status, invoke the `eve-mcp:login` tool a second time.
4. **Proceed or Halt:** If authentication succeeds, proceed with the user's primary request. If both login and registration steps fail, halt execution entirely and report the exact error logs to the user.

## Context & Tools
- `eve-mcp:login`: Tool used to authenticate and open a working session on the host.
- `eve-mcp:add_user`: Fallback tool used to inject the required `eve-mcp` profile into the target EVE-NG environment.