"""Codex stdio adapter for the authoritative MyridTV MCP backend."""
import asyncio
import json

try:
    from mcp.server import Server, stdio_server
except ImportError:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult
from myridtv_mcp_client import load_tools, call_tool as forward_tool

app = Server("myridtv-canvas-codex")


@app.list_tools()
async def list_tools():
    return [Tool(**t) for t in await asyncio.to_thread(load_tools)]


@app.call_tool()
async def call_tool(name, arguments):
    try:
        result = await asyncio.to_thread(forward_tool, name, arguments)
        return CallToolResult(**result)
    except Exception as exc:
        return CallToolResult(isError=True, content=[TextContent(
            type="text", text=json.dumps({"ok": False, "error": str(exc),
            "error_code": "bridge_failed", "retry_hint": "读取状态核对；重试写操作时复用原 idempotency_key"}, ensure_ascii=False))])


async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
