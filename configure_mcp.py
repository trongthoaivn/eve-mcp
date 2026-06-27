import os
import sys
import json
import argparse

def main():
    parser = argparse.ArgumentParser(description="Configure MCP server in config files.")
    parser.add_argument("--config-file", required=True, help="Path to config file")
    parser.add_argument("--command", required=True, help="Command to run")
    parser.add_argument("--arg", help="Argument to pass to command")
    parser.add_argument("--with-env", action="store_true", help="Include EVE environment variables")
    
    args = parser.parse_args()
    
    # 1. Prepare entry
    args_list = []
    if args.arg:
        args_list.append(args.arg)
        
    entry = {
        "command": args.command,
        "args": args_list
    }
    
    if args.with_env:
        entry["env"] = {
            "EVE_HOST": os.environ.get("EVE_HOST", ""),
            "EVE_USERNAME": os.environ.get("EVE_USERNAME", ""),
            "EVE_PASSWORD": os.environ.get("EVE_PASSWORD", ""),
            "EVE_PROTOCOL": os.environ.get("EVE_PROTOCOL", "http"),
            "EVE_SSL_VERIFY": os.environ.get("EVE_SSL_VERIFY", "false"),
            "EVE_DISABLE_INSECURE_WARNINGS": os.environ.get("EVE_DISABLE_INSECURE_WARNINGS", "true")
        }
        
    # 2. Read existing config
    config_data = {}
    if os.path.exists(args.config_file):
        try:
            with open(args.config_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    config_data = json.loads(content)
        except Exception as e:
            print(f"Warning: Failed to parse JSON from {args.config_file}: {e}", file=sys.stderr)
            
    # Ensure mcpServers exists
    if "mcpServers" not in config_data or not isinstance(config_data["mcpServers"], dict):
        config_data["mcpServers"] = {}
        
    # Update entry
    config_data["mcpServers"]["eve-mcp"] = entry
    
    # 3. Create parent directories if they don't exist
    parent_dir = os.path.dirname(args.config_file)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)
        
    # 4. Write config file
    try:
        with open(args.config_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        print(f"Successfully configured: {args.config_file}")
    except Exception as e:
        print(f"Error: Failed to write to {args.config_file}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
