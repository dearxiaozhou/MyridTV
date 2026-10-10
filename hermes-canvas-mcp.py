"""Hermes stdio adapter for the authoritative MyridTV MCP backend (MCP 1/2)."""
import asyncio
import json
from mcp.server import Server
try:
    from mcp.server.stdio import stdio_server
except ImportError:
    from mcp.server import stdio_server
try:
    import mcp_types as types
except ImportError:
    from mcp import types
from myridtv_mcp_client import load_tools, call_tool as forward_tool


async def _on_list_tools(ctx=None, params=None):
    return types.ListToolsResult(tools=[types.Tool(**t) for t in await asyncio.to_thread(load_tools)])


async def _on_call_tool(ctx, params):
    name = params.get("name") if isinstance(params, dict) else params.name
    arguments = params.get("arguments", {}) if isinstance(params, dict) else params.arguments or {}
    try:
        result = await asyncio.to_thread(forward_tool, name, arguments)
        return types.CallToolResult(**result)
    except Exception as exc:
        return types.CallToolResult(isError=True, content=[types.TextContent(type="text", text=json.dumps(
            {"ok": False, "error": str(exc), "error_code": "bridge_failed",
             "retry_hint": "读取状态核对；重试写操作时复用原 idempotency_key"}, ensure_ascii=False))])


if hasattr(Server, "list_tools"):
    app = Server("myridtv-canvas")

    @app.list_tools()
    async def list_tools():
        result = await _on_list_tools()
        return result.tools

    @app.call_tool()
    async def call_tool(name, arguments):
        return await _on_call_tool(None, {"name": name, "arguments": arguments})
else:
    app = Server("myridtv-canvas", on_list_tools=_on_list_tools, on_call_tool=_on_call_tool)


async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
