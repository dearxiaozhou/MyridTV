"""
MyridTV Canvas MCP Server (Hermes) —— 统一转发层

所有工具请求直接转发到后端 3107 的 JSON-RPC 端点 POST /mcp，
与前端 / 内置 Agent 走同一条收口：
    _agent_batch_build_* + Artifact Gate（单写点/墓碑） + 后端 _normalize_node

不再本地手搓节点、不再自管画布读写，因此：
  - 节点字段格式与画布主通道完全一致（type 白名单、w/h 尺寸键、text/promptDraftText 别名）
  - 自动获得 409 冲突处理（_agent_canvas_repo_upsert_node 已处理）
  - 连线字段正确读取后端的 connections（不再恒空）
  - 工具 schema 实时从后端 tools/list 同步，不会与主通道漂移
"""
import asyncio
import json
import itertools
import urllib.request
from typing import Any

from mcp.server import Server
try:
    from mcp.server.stdio import stdio_server
except ImportError:  # mcp 1.x
    from mcp.server import stdio_server  # type: ignore
try:
    import mcp_types as types  # mcp 2.x
except ImportError:  # mcp 1.x
    from mcp import types  # type: ignore

BACKEND = "http://127.0.0.1:3107"
_REQ_ID = itertools.count(1)
BACKEND_TOOLS = None  # 懒加载：首次 list_tools 时连后端拉取


def _mcp_post(method, params=None):
    """向后端 POST /mcp 发一条 JSON-RPC 请求，返回解析后的响应 dict。"""
    payload = {"jsonrpc": "2.0", "id": next(_REQ_ID), "method": method, "params": params or {}}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BACKEND}/mcp", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        resp = json.loads(r.read().decode("utf-8"))
    if "error" in resp:
        raise RuntimeError(str(resp["error"]))
    return resp


def _mcp_call_tool(name, arguments):
    """转发一次 tools/call，并把后端回传的 text 反序列化成 dict 返回。"""
    resp = _mcp_post("tools/call", {"name": name, "arguments": arguments})
    result = resp.get("result", {}) or {}
    content = result.get("content") or []
    if content and isinstance(content[0], dict) and content[0].get("type") == "text":
        try:
            return json.loads(content[0]["text"])
        except Exception:
            return {"raw": content[0]["text"]}
    if result.get("isError"):
        return {"error": result.get("content")}
    return result


# 后端连不上时的兜底 schema（与 myridtv_mcp.MCP_TOOLS 同名工具一致），
# 仅保证 server 能启动并列出基础工具；实际调用仍会转发到后端。
_FALLBACK_TOOLS = [
    {"name": "canvas_list_canvases", "description": "列出所有画布", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "canvas_get_state", "description": "获取画布状态", "inputSchema": {"type": "object", "properties": {"canvas_id": {"type": "string"}}}},
    {"name": "canvas_get_selection", "description": "获取选中节点", "inputSchema": {"type": "object", "properties": {"canvas_id": {"type": "string"}}}},
    {"name": "canvas_search", "description": "搜索节点", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "canvas_id": {"type": "string"}}, "required": ["query"]}},
    {"name": "canvas_create_node", "description": "创建节点（与画布 Agent/人工同一落库链路）。type=text|generation；x/y 可省=自动空位", "inputSchema": {"type": "object", "properties": {"type": {"type": "string"}, "text": {"type": "string"}, "content": {"type": "string"}, "prompt": {"type": "string"}, "title": {"type": "string"}, "label": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}, "width": {"type": "number"}, "height": {"type": "number"}, "provider_id": {"type": "string"}, "model": {"type": "string"}, "size": {"type": "string"}, "canvas_id": {"type": "string"}}, "required": ["type"]}},
    {"name": "canvas_delete_node", "description": "删除节点", "inputSchema": {"type": "object", "properties": {"node_id": {"type": "string"}, "canvas_id": {"type": "string"}}, "required": ["node_id"]}},
    {"name": "canvas_update_node", "description": "更新节点（与人工编辑同字段族：text/content/prompt 改正文，尺寸 w/h）", "inputSchema": {"type": "object", "properties": {"node_id": {"type": "string"}, "text": {"type": "string"}, "content": {"type": "string"}, "prompt": {"type": "string"}, "title": {"type": "string"}, "label": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}, "w": {"type": "number"}, "h": {"type": "number"}, "canvas_id": {"type": "string"}}, "required": ["node_id"]}},
    {"name": "canvas_connect_nodes", "description": "连接节点", "inputSchema": {"type": "object", "properties": {"from_id": {"type": "string"}, "to_id": {"type": "string"}, "label": {"type": "string"}, "canvas_id": {"type": "string"}}, "required": ["from_id", "to_id"]}},
    {"name": "canvas_snapshot", "description": "保存快照", "inputSchema": {"type": "object", "properties": {"canvas_id": {"type": "string"}}}},
    {"name": "canvas_create_text_node", "description": "创建智能画布原生文本节点(type=smart-prompt)", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, "title": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}, "canvas_id": {"type": "string"}}, "required": ["text"]}},
    {"name": "canvas_create_generation_node", "description": "创建图片生成节点(type=smart-image,待生成)", "inputSchema": {"type": "object", "properties": {"prompt": {"type": "string"}, "title": {"type": "string"}, "model": {"type": "string"}, "size": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}, "canvas_id": {"type": "string"}}, "required": ["prompt"]}},
    {"name": "canvas_generate_images", "description": "提交图片生成任务并回填画布节点(异步)", "inputSchema": {"type": "object", "properties": {"prompt": {"type": "string"}, "node_id": {"type": "string"}, "model": {"type": "string"}, "size": {"type": "string"}, "reference_image_urls": {"type": "array", "items": {"type": "string"}}, "canvas_id": {"type": "string"}}, "required": ["prompt"]}},
]


def _fetch_backend_tools():
    try:
        resp = _mcp_post("tools/list")
        tools = (resp.get("result", {}) or {}).get("tools", [])
        if tools:
            return tools
    except Exception:
        pass
    return _FALLBACK_TOOLS


def _load_tools():
    global BACKEND_TOOLS
    if BACKEND_TOOLS is None:
        BACKEND_TOOLS = _fetch_backend_tools()
    return BACKEND_TOOLS


async def _on_list_tools(ctx, params):
    tools = await asyncio.to_thread(_load_tools)
    return types.ListToolsResult(
        tools=[
            types.Tool(
                name=t["name"],
                description=t.get("description", ""),
                inputSchema=t.get("inputSchema", {"type": "object", "properties": {}}),
            )
            for t in tools
        ]
    )


async def _on_call_tool(ctx, params):
    name = getattr(params, "name", None) or (params or {}).get("name")
    arguments = getattr(params, "arguments", None) or (params or {}).get("arguments") or {}
    try:
        result = await asyncio.to_thread(_mcp_call_tool, name, arguments)
    except Exception as e:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]
        )
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    )


app = Server("myridtv-canvas", on_list_tools=_on_list_tools, on_call_tool=_on_call_tool)


# ---- mcp 1.x 兜底：装饰器式注册（2.x 的 Server 没有 list_tools/call_tool 装饰器）----
if hasattr(Server, "list_tools"):
    try:
        app.list_tools()(lambda: _on_list_tools(None, None))
        app.call_tool()(lambda name, arguments: _on_call_tool(None, {"name": name, "arguments": arguments}))
    except Exception:
        pass


async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
