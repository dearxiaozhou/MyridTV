"""
MyridTV Canvas MCP Server - 作为语义接口层，通过 MCP 暴露画布工具给 AI Agent。
支持 SSE (HTTP) 和 stdio 两种传输模式。

启动方式：
  命令行:   python canvas-mcp-server.py [--port 47330] [--mode sse|stdio]
  MyridTV集成: 自动作为后台线程启动 SSE 模式
"""

import json, os, sys, time, uuid, urllib.request, urllib.parse
from typing import Any

CANVAS_PORT = 47330
BACKEND = "http://127.0.0.1:3107"

# ---------- Canvas API 封装 ----------

canvas_cache = {"id": None, "data": None}

def _get_canvas_id() -> str:
    try:
        req = urllib.request.Request(f"{BACKEND}/api/canvases")
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        canvases = data if isinstance(data, list) else data.get("canvases", [])
        if not canvases: return ""
        canvases.sort(key=lambda c: c.get("last_modified", 0), reverse=True)
        return str(canvases[0].get("id", ""))
    except: return ""

def _fetch_canvas(canvas_id: str = "") -> dict:
    cid = canvas_id or _get_canvas_id()
    if not cid: return {"ok": False, "error": "未找到画布"}
    try:
        req = urllib.request.Request(f"{BACKEND}/api/canvases/{urllib.parse.quote(cid)}")
        with urllib.request.urlopen(req, timeout=5) as r:
            resp = json.loads(r.read())
        data = resp.get("canvas", resp)
        canvas_cache["id"] = cid; canvas_cache["data"] = data
        return data
    except Exception as e: return {"ok": False, "error": str(e)}

def _save_canvas(canvas_id: str, data: dict) -> dict:
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(f"{BACKEND}/api/canvases/{urllib.parse.quote(canvas_id)}",
            data=body, method="PUT", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return {"ok": True}
    except Exception as e: return {"ok": False, "error": str(e)}

# ---------- MCP 工具处理 ----------

def _late_handler(function_name: str):
    def _handler(args):
        return globals()[function_name](args)
    return _handler

TOOL_DEFS = {
    "canvas_list_canvases": {
        "description": "列出所有画布及基本信息",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": _late_handler("_handle_list_canvases"),
    },
    "canvas_get_state": {
        "description": "获取当前画布完整状态（节点、连线、视口）",
        "inputSchema": {"type": "object", "properties": {
            "canvas_id": {"type": "string", "description": "画布 ID（可选）"}
        }},
        "handler": _late_handler("_handle_get_state"),
    },
    "canvas_get_selection": {
        "description": "获取当前选中节点",
        "inputSchema": {"type": "object", "properties": {
            "canvas_id": {"type": "string"}
        }},
        "handler": _late_handler("_handle_get_selection"),
    },
    "canvas_search": {
        "description": "按名称或内容搜索节点",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string"}, "canvas_id": {"type": "string"}
        }, "required": ["query"]},
        "handler": _late_handler("_handle_search"),
    },
    "canvas_create_node": {
        "description": "创建新节点",
        "inputSchema": {"type": "object", "properties": {
            "type": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"},
            "width": {"type": "number"}, "height": {"type": "number"},
            "content": {"type": "string"}, "label": {"type": "string"},
            "canvas_id": {"type": "string"},
        }, "required": ["type", "x", "y"]},
        "handler": _late_handler("_handle_create_node"),
    },
    "canvas_delete_node": {
        "description": "删除指定节点",
        "inputSchema": {"type": "object", "properties": {
            "node_id": {"type": "string"}, "canvas_id": {"type": "string"}
        }, "required": ["node_id"]},
        "handler": _late_handler("_handle_delete_node"),
    },
    "canvas_update_node": {
        "description": "更新节点属性",
        "inputSchema": {"type": "object", "properties": {
            "node_id": {"type": "string"}, "content": {"type": "string"},
            "x": {"type": "number"}, "y": {"type": "number"},
            "width": {"type": "number"}, "height": {"type": "number"},
            "label": {"type": "string"}, "canvas_id": {"type": "string"},
        }, "required": ["node_id"]},
        "handler": _late_handler("_handle_update_node"),
    },
    "canvas_connect_nodes": {
        "description": "连接两个节点",
        "inputSchema": {"type": "object", "properties": {
            "from_id": {"type": "string"}, "to_id": {"type": "string"},
            "label": {"type": "string"}, "canvas_id": {"type": "string"},
        }, "required": ["from_id", "to_id"]},
        "handler": _late_handler("_handle_connect"),
    },
    "canvas_snapshot": {
        "description": "保存当前画布快照",
        "inputSchema": {"type": "object", "properties": {
            "canvas_id": {"type": "string"}
        }},
        "handler": _late_handler("_handle_snapshot"),
    },
}

def _handle_list_canvases(args):
    try:
        req = urllib.request.Request(f"{BACKEND}/api/canvases")
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        canvases = data if isinstance(data, list) else data.get("canvases", [])
        return {"result": [{"id": c.get("id"), "title": c.get("title", c.get("name", "未命名")),
                            "nodes": c.get("node_count", 0)} for c in canvases]}
    except Exception as e:
        return {"error": str(e)}

def _handle_get_state(args):
    canvas = _fetch_canvas(args.get("canvas_id", ""))
    if "error" in canvas: return {"error": canvas["error"]}
    cid = canvas_cache["id"]
    nodes = canvas.get("nodes", canvas.get("data", {}).get("nodes", []))
    edges = canvas.get("edges", canvas.get("data", {}).get("edges", []))
    return {"result": {
        "canvas_id": cid, "node_count": len(nodes), "edge_count": len(edges),
        "nodes": [{"id": n.get("id"), "type": n.get("type"),
                    "label": n.get("label", n.get("title", "")),
                    "x": n.get("x"), "y": n.get("y")} for n in nodes],
        "edges": edges,
    }}

def _handle_get_selection(args):
    canvas = _fetch_canvas(args.get("canvas_id", ""))
    if "error" in canvas: return {"error": canvas["error"]}
    nodes = canvas.get("nodes", canvas.get("data", {}).get("nodes", []))
    selection = canvas.get("data", {}).get("selectedIds", [])
    selected_nodes = [n for n in nodes if n.get("id") in selection]
    return {"result": {"selected_ids": selection, "nodes": selected_nodes}}

def _handle_search(args):
    canvas = _fetch_canvas(args.get("canvas_id", ""))
    if "error" in canvas: return {"error": canvas["error"]}
    nodes = canvas.get("nodes", canvas.get("data", {}).get("nodes", []))
    q = args.get("query", "").lower()
    matches = [n for n in nodes if q in str(n.get("label", n.get("title", ""))).lower()
               or q in str(n.get("content", "")).lower()]
    return {"result": {"query": q, "matches": len(matches), "nodes": matches}}

def _handle_create_node(args):
    cid = args.get("canvas_id", "") or _get_canvas_id()
    if not cid: return {"error": "未找到画布"}
    canvas = _fetch_canvas(cid)
    node_id = f"hm_{uuid.uuid4().hex[:8]}"
    new_node = {"id": node_id, "type": args.get("type", "text"),
                "x": args.get("x", 0), "y": args.get("y", 0),
                "width": args.get("width", 300), "height": args.get("height", 200),
                "label": args.get("label", ""), "content": args.get("content", "")}
    data = canvas.get("data", canvas)
    node_list = data.get("nodes", []); node_list.append(new_node)
    data["nodes"] = node_list
    _save_canvas(cid, data)
    return {"result": {"node_id": node_id}}

def _handle_delete_node(args):
    cid = args.get("canvas_id", "") or _get_canvas_id()
    node_id = args.get("node_id", "")
    canvas = _fetch_canvas(cid)
    data = canvas.get("data", canvas)
    data["nodes"] = [n for n in data.get("nodes", []) if n.get("id") != node_id]
    data["edges"] = [e for e in data.get("edges", [])
                     if e.get("from", e.get("source")) != node_id
                     and e.get("to", e.get("target")) != node_id]
    _save_canvas(cid, data)
    return {"result": {"deleted": node_id}}

def _handle_update_node(args):
    cid = args.get("canvas_id", "") or _get_canvas_id()
    node_id = args.get("node_id", "")
    canvas = _fetch_canvas(cid)
    data = canvas.get("data", canvas)
    for n in data.get("nodes", []):
        if n.get("id") == node_id:
            for k in ("content", "x", "y", "width", "height", "label"):
                if k in args: n[k] = args[k]
            break
    _save_canvas(cid, data)
    return {"result": {"node_id": node_id}}

def _handle_connect(args):
    cid = args.get("canvas_id", "") or _get_canvas_id()
    edge_id = f"e_{uuid.uuid4().hex[:8]}"
    canvas = _fetch_canvas(cid)
    data = canvas.get("data", canvas)
    edges = data.get("edges", [])
    edges.append({"id": edge_id, "from": args["from_id"],
                  "to": args["to_id"], "label": args.get("label", "")})
    data["edges"] = edges
    _save_canvas(cid, data)
    return {"result": {"edge_id": edge_id}}

def _handle_snapshot(args):
    cid = args.get("canvas_id", "") or _get_canvas_id()
    canvas = _fetch_canvas(cid)
    data = canvas.get("data", canvas)
    data["snapshot_at"] = time.time()
    _save_canvas(cid, data)
    return {"result": {"canvas_id": cid}}


# ========== Stdio MCP Server ==========

def handle_mcp_request(request: dict) -> dict:
    """处理一个 MCP JSON-RPC 请求"""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "myridtv-canvas", "version": "0.2.0"},
        }}
    if method == "tools/list":
        tools = []
        for name, defn in TOOL_DEFS.items():
            tool = {key: value for key, value in defn.items() if key != "handler"}
            tool["name"] = name
            tools.append(tool)
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        if name not in TOOL_DEFS:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Tool not found: {name}"}}
        handler = TOOL_DEFS[name]["handler"]
        try:
            result = handler(args)
            if "error" in result:
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": result["error"]}}
            content = json.dumps(result["result"], ensure_ascii=False)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": content}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(e)}}
    if method == "notifications/initialized":
        return None  # 不需要回复
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}


def stdio_main():
    """stdio 模式：通过 stdin/stdout 通信"""
    import sys
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_mcp_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            continue


# ========== SSE (HTTP) MCP Server ==========

def sse_main(port=CANVAS_PORT):
    """SSE 模式：通过 HTTP + SSE 通信"""
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class MCPHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send_json(self, data, status=200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

        def do_GET(self):
            if self.path == "/health":
                self._send_json({"ok": True, "service": "myridtv-canvas-mcp", "version": "0.2.0"})
            elif self.path == "/mcp":
                # SSE endpoint
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                # 发初始化事件
                init = json.dumps({"jsonrpc": "2.0", "method": "endpoint",
                                    "params": {"url": f"http://127.0.0.1:{port}/mcp"}})
                self.wfile.write(f"event: endpoint\ndata: {init}\n\n".encode())
                self.wfile.flush()
            else:
                self._send_json({"error": "not found"}, 404)

        def do_POST(self):
            if self.path == "/mcp":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode() if length else "{}"
                try:
                    request = json.loads(body)
                    response = handle_mcp_request(request)
                    self._send_json(response or {})
                except Exception as e:
                    self._send_json({"jsonrpc": "2.0", "error": {"code": -32700, "message": str(e)}}, 400)

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()

    server = HTTPServer(("127.0.0.1", port), MCPHandler)
    print(f"[canvas-mcp] SSE mode on http://127.0.0.1:{port}/mcp")
    server.serve_forever()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=CANVAS_PORT, help=f"端口 (默认 {CANVAS_PORT})")
    parser.add_argument("--mode", choices=["stdio", "sse"], default="stdio",
                        help="传输模式: stdio (Hermes子进程) 或 sse (HTTP)")
    args = parser.parse_args()
    if args.mode == "sse":
        sse_main(args.port)
    else:
        stdio_main()
