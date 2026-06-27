from fastmcp import FastMCP
import controllers.eve_ng_controller as eve_ng_controller
import controllers.remote_controller as remote_controller

mcp = FastMCP("EveMcpServer")

# Register all EVE-NG MCP tools
eve_ng_controller.register(mcp)

# Register all SSH/remote tools
remote_controller.register(mcp)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
