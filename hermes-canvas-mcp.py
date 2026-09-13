"""
MyridTV Canvas MCP Server
作为语义接口层，把无限画布抽象成结构化对象，通过 MCP 暴露给 Agent。
"""
import json, os, sys, urllib.request, urllib.parse
from typing import Any
try:
    from mcp.server import Server, stdio_server
except ImportError:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent

BACKEND = "http://127.0.0.1:3107"

canvas_cache = {"id": None, "data": None}


def _get_canvas_id() -> str:
    """获取最近编辑的画布 ID"""
    try:
        req = urllib.request.Request(f"{BACKEND}/api/canvases")
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        canvases = data if isinstance(data, list) else data.get("canvases", [])
        if not canvases:
            return ""
        # 按 last_modified 排序取最新的
        canvases.sort(key=lambda c: c.get("last_modified", 0), reverse=True)
        return str(canvases[0].get("id", ""))
    except Exception as e:
        return ""

def _fetch_canvas(canvas_id: str = "") -> dict:
    """从后端获取画布数据"""
    cid = canvas_id or _get_canvas_id()
    if not cid:
        return {"ok": False, "error": "未找到画布"}
    try:
        req = urllib.request.Request(f"{BACKEND}/api/canvases/{urllib.parse.quote(cid)}")
        with urllib.request.urlopen(req, timeout=5) as r:
            resp = json.loads(r.read())
        data = resp.get("canvas", resp)
        canvas_cache["id"] = cid
        canvas_cache["data"] = data
        return data
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _save_canvas(canvas_id: str, data: dict) -> dict:
    """保存画布数据到后端"""
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{BACKEND}/api/canvases/{urllib.parse.quote(canvas_id)}",
            data=body,
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------- MCP Server ----------

app = Server("myridtv-canvas")

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="canvas_list_canvases",
            description="列出所有画布及基本信息",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="canvas_get_state",
            description="获取当前画布完整状态（节点、连线、视口）",
            inputSchema={
                "type": "object",
                "properties": {
                    "canvas_id": {"type": "string", "description": "画布 ID（可选，默认最近编辑的画布）"}
                },
            },
        ),
        Tool(
            name="canvas_get_selection",
            description="获取当前选中节点",
            inputSchema={
                "type": "object",
                "properties": {
                    "canvas_id": {"type": "string", "description": "画布 ID（可选）"}
                },
            },
        ),
        Tool(
            name="canvas_search",
            description="按名称或内容搜索节点",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "canvas_id": {"type": "string", "description": "画布 ID（可选）"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="canvas_create_node",
            description="创建新节点",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "节点类型: image/text/card/group"},
                    "x": {"type": "number", "description": "X 坐标"},
                    "y": {"type": "number", "description": "Y 坐标"},
                    "width": {"type": "number", "description": "宽度"},
                    "height": {"type": "number", "description": "高度"},
                    "content": {"type": "string", "description": "节点内容/提示词"},
                    "label": {"type": "string", "description": "节点标签"},
                    "canvas_id": {"type": "string", "description": "画布 ID（可选）"},
                },
                "required": ["type", "x", "y"],
            },
        ),
        Tool(
            name="canvas_delete_node",
            description="删除指定节点",
            inputSchema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "节点 ID"},
                    "canvas_id": {"type": "string", "description": "画布 ID（可选）"},
                },
                "required": ["node_id"],
            },
        ),
        Tool(
            name="canvas_update_node",
            description="更新节点属性",
            inputSchema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "节点 ID"},
                    "content": {"type": "string", "description": "新内容"},
                    "x": {"type": "number", "description": "新 X 坐标"},
                    "y": {"type": "number", "description": "新 Y 坐标"},
                    "width": {"type": "number", "description": "新宽度"},
                    "height": {"type": "number", "description": "新高度"},
                    "label": {"type": "string", "description": "新标签"},
                    "canvas_id": {"type": "string", "description": "画布 ID（可选）"},
                },
                "required": ["node_id"],
            },
        ),
        Tool(
            name="canvas_connect_nodes",
            description="连接两个节点",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_id": {"type": "string", "description": "源节点 ID"},
                    "to_id": {"type": "string", "description": "目标节点 ID"},
                    "label": {"type": "string", "description": "连线标签"},
                    "canvas_id": {"type": "string", "description": "画布 ID（可选）"},
                },
                "required": ["from_id", "to_id"],
            },
        ),
        Tool(
            name="canvas_snapshot",
            description="保存当前画布快照",
            inputSchema={
                "type": "object",
                "properties": {
                    "canvas_id": {"type": "string", "description": "画布 ID（可选）"}
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list:
    cid = arguments.get("canvas_id", "")

    if name == "canvas_list_canvases":
        try:
            req = urllib.request.Request(f"{BACKEND}/api/canvases")
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read())
            canvases = data if isinstance(data, list) else data.get("canvases", [])
            summary = []
            for c in canvases:
                summary.append({
                    "id": c.get("id", ""),
                    "title": c.get("title", c.get("name", "未命名")),
                    "nodes": c.get("node_count", 0),
                    "modified": c.get("last_modified", ""),
                })
            return [TextContent(type="text", text=json.dumps(summary, ensure_ascii=False, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]

    # 获取画布数据
    canvas = _fetch_canvas(cid)
    if "error" in canvas:
        return [TextContent(type="text", text=json.dumps(canvas, ensure_ascii=False))]

    nodes = canvas.get("nodes", canvas.get("data", {}).get("nodes", []))
    edges = canvas.get("edges", canvas.get("data", {}).get("edges", []))
    selection = canvas.get("data", {}).get("selectedIds", [])
    cid = canvas_cache["id"]

    if name == "canvas_get_state":
        return [TextContent(type="text", text=json.dumps({
            "canvas_id": cid,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "selected_ids": selection,
            "nodes": [{ "id": n.get("id"), "type": n.get("type"), "label": n.get("label", n.get("title", "")),
                        "x": n.get("x"), "y": n.get("y"), "w": n.get("width"), "h": n.get("height") }
                      for n in nodes],
            "edges": edges,
        }, ensure_ascii=False, indent=2))]

    if name == "canvas_get_selection":
        selected_nodes = [n for n in nodes if n.get("id") in selection]
        return [TextContent(type="text", text=json.dumps({
            "selected_ids": selection,
            "nodes": selected_nodes,
        }, ensure_ascii=False, indent=2))]

    if name == "canvas_search":
        q = arguments.get("query", "").lower()
        matches = [n for n in nodes if q in str(n.get("label", n.get("title", ""))).lower()
                   or q in str(n.get("content", "")).lower()
                   or q in str(n.get("id", "")).lower()]
        return [TextContent(type="text", text=json.dumps({
            "query": q,
            "matches": len(matches),
            "nodes": matches,
        }, ensure_ascii=False, indent=2))]

    if name == "canvas_create_node":
        import uuid
        node_id = f"hermes_{uuid.uuid4().hex[:8]}"
        new_node = {
            "id": node_id,
            "type": arguments.get("type", "text"),
            "x": arguments.get("x", 0),
            "y": arguments.get("y", 0),
            "width": arguments.get("width", 300),
            "height": arguments.get("height", 200),
            "label": arguments.get("label", ""),
            "content": arguments.get("content", ""),
        }
        # 保存到画布
        data = canvas.get("data", canvas)
        node_list = data.get("nodes", [])
        node_list.append(new_node)
        data["nodes"] = node_list
        result = _save_canvas(cid, data)
        if result.get("ok"):
            return [TextContent(type="text", text=json.dumps({"ok": True, "node_id": node_id}, ensure_ascii=False))]
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    if name == "canvas_delete_node":
        node_id = arguments.get("node_id", "")
        data = canvas.get("data", canvas)
        data["nodes"] = [n for n in data.get("nodes", []) if n.get("id") != node_id]
        data["edges"] = [e for e in data.get("edges", [])
                         if e.get("from", e.get("source")) != node_id
                         and e.get("to", e.get("target")) != node_id]
        result = _save_canvas(cid, data)
        return [TextContent(type="text", text=json.dumps({"ok": True, "deleted": node_id}, ensure_ascii=False))]

    if name == "canvas_update_node":
        node_id = arguments.get("node_id", "")
        data = canvas.get("data", canvas)
        for n in data.get("nodes", []):
            if n.get("id") == node_id:
                if "content" in arguments: n["content"] = arguments["content"]
                if "x" in arguments: n["x"] = arguments["x"]
                if "y" in arguments: n["y"] = arguments["y"]
                if "width" in arguments: n["width"] = arguments["width"]
                if "height" in arguments: n["height"] = arguments["height"]
                if "label" in arguments: n["label"] = arguments["label"]
                break
        result = _save_canvas(cid, data)
        return [TextContent(type="text", text=json.dumps({"ok": True, "node_id": node_id}, ensure_ascii=False))]

    if name == "canvas_connect_nodes":
        from_id = arguments.get("from_id", "")
        to_id = arguments.get("to_id", "")
        import uuid
        edge_id = f"e_{uuid.uuid4().hex[:8]}"
        data = canvas.get("data", canvas)
        edges = data.get("edges", [])
        edges.append({
            "id": edge_id,
            "from": from_id,
            "to": to_id,
            "label": arguments.get("label", ""),
        })
        data["edges"] = edges
        result = _save_canvas(cid, data)
        return [TextContent(type="text", text=json.dumps({"ok": True, "edge_id": edge_id}, ensure_ascii=False))]

    if name == "canvas_snapshot":
        data = canvas.get("data", canvas)
        data["snapshot_at"] = __import__("time").time()
        result = _save_canvas(cid, data)
        return [TextContent(type="text", text=json.dumps({"ok": True, "canvas_id": cid}, ensure_ascii=False))]

    return [TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}))]


async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
