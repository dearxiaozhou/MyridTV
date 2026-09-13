#!/usr/bin/env python3
"""
WcsTV Canvas MCP server for Codex.

This is the Codex-facing semantic interface for the local infinite canvas.
It talks only to the WcsTV local proxy at http://127.0.0.1:3107.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


BACKEND = "http://127.0.0.1:3107"
SERVER_NAME = "wcstv-canvas"

app = Server(SERVER_NAME)


def _json_content(payload: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


def _request_json(method: str, path: str, payload: Any | None = None, timeout: int = 15) -> Any:
    url = f"{BACKEND}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = raw
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"{method} {url} failed: {exc}") from exc


def _unwrap_canvas(response: Any) -> dict[str, Any]:
    if isinstance(response, dict) and isinstance(response.get("canvas"), dict):
        return response["canvas"]
    if isinstance(response, dict):
        return response
    raise RuntimeError("WcsTV returned an unexpected canvas payload")


def _list_canvases_raw() -> list[dict[str, Any]]:
    response = _request_json("GET", "/api/canvases")
    if isinstance(response, list):
        return response
    canvases = response.get("canvases") if isinstance(response, dict) else None
    return canvases if isinstance(canvases, list) else []


def _latest_canvas_id() -> str:
    canvases = _list_canvases_raw()
    if not canvases:
        raise RuntimeError("No WcsTV canvases were found")
    canvases.sort(key=lambda item: item.get("updated_at") or item.get("last_modified") or 0, reverse=True)
    canvas_id = str(canvases[0].get("id") or "").strip()
    if not canvas_id:
        raise RuntimeError("Latest WcsTV canvas has no id")
    return canvas_id


def _get_canvas(canvas_id: str = "") -> dict[str, Any]:
    resolved = canvas_id.strip() or _latest_canvas_id()
    response = _request_json("GET", f"/api/canvases/{urllib.parse.quote(resolved)}")
    return _unwrap_canvas(response)


def _save_canvas(canvas: dict[str, Any]) -> dict[str, Any]:
    canvas_id = str(canvas.get("id") or "").strip()
    if not canvas_id:
        raise RuntimeError("Cannot save a canvas without an id")
    canvas["updated_at"] = int(time.time() * 1000)
    response = _request_json("PUT", f"/api/canvases/{urllib.parse.quote(canvas_id)}", canvas)
    return response if isinstance(response, dict) else {"ok": True, "response": response}


def _canvas_summary(canvas: dict[str, Any], max_nodes: int = 80) -> dict[str, Any]:
    nodes = canvas.get("nodes") if isinstance(canvas.get("nodes"), list) else []
    edges = canvas.get("edges") if isinstance(canvas.get("edges"), list) else []
    slim_nodes = [_node_summary(node) for node in nodes[:max_nodes] if isinstance(node, dict)]
    return {
        "id": canvas.get("id"),
        "title": canvas.get("title"),
        "kind": canvas.get("kind"),
        "updated_at": canvas.get("updated_at"),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": slim_nodes,
        "truncated": len(nodes) > max_nodes,
    }


def _node_summary(node: dict[str, Any]) -> dict[str, Any]:
    text = _node_text(node)
    images = node.get("images") if isinstance(node.get("images"), list) else []
    return {
        "id": node.get("id"),
        "type": node.get("type"),
        "title": node.get("title") or node.get("label"),
        "x": node.get("x"),
        "y": node.get("y"),
        "w": node.get("w") or node.get("width"),
        "h": node.get("h") or node.get("height"),
        "text": text[:1200],
        "image_count": len(images),
    }


def _node_text(node: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("title", "label", "content", "text", "promptDraftText", "runPrompt"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return "\n".join(dict.fromkeys(parts))


def _find_node(canvas: dict[str, Any], node_id: str) -> dict[str, Any]:
    for node in canvas.get("nodes") or []:
        if isinstance(node, dict) and str(node.get("id")) == node_id:
            return node
    raise RuntimeError(f"Node not found: {node_id}")


def _tool_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="wcstv_health",
            description="Check whether the local WcsTV proxy is reachable.",
            inputSchema=_tool_schema({}),
        ),
        Tool(
            name="wcstv_list_canvases",
            description="List WcsTV canvases available through the local proxy.",
            inputSchema=_tool_schema({}),
        ),
        Tool(
            name="wcstv_get_canvas",
            description="Get a summarized canvas state. Defaults to the most recently updated canvas.",
            inputSchema=_tool_schema(
                {
                    "canvas_id": {"type": "string", "description": "Canvas id. Omit for latest canvas."},
                    "include_full": {"type": "boolean", "description": "Return the full raw canvas JSON."},
                }
            ),
        ),
        Tool(
            name="wcstv_search_canvas",
            description="Search node text/title/prompt fields in a canvas.",
            inputSchema=_tool_schema(
                {
                    "query": {"type": "string", "description": "Search text."},
                    "canvas_id": {"type": "string", "description": "Canvas id. Omit for latest canvas."},
                    "limit": {"type": "number", "description": "Maximum matches to return."},
                },
                ["query"],
            ),
        ),
        Tool(
            name="wcstv_create_text_node",
            description="Create a text note node on a WcsTV canvas.",
            inputSchema=_tool_schema(
                {
                    "text": {"type": "string", "description": "Node text content."},
                    "title": {"type": "string", "description": "Optional node title."},
                    "x": {"type": "number", "description": "Canvas x coordinate."},
                    "y": {"type": "number", "description": "Canvas y coordinate."},
                    "width": {"type": "number", "description": "Node width."},
                    "height": {"type": "number", "description": "Node height."},
                    "canvas_id": {"type": "string", "description": "Canvas id. Omit for latest canvas."},
                },
                ["text"],
            ),
        ),
        Tool(
            name="wcstv_update_node",
            description="Update text/title/position/size fields on an existing canvas node.",
            inputSchema=_tool_schema(
                {
                    "node_id": {"type": "string", "description": "Node id to update."},
                    "text": {"type": "string", "description": "Replacement text content."},
                    "title": {"type": "string", "description": "Replacement title."},
                    "x": {"type": "number", "description": "Canvas x coordinate."},
                    "y": {"type": "number", "description": "Canvas y coordinate."},
                    "width": {"type": "number", "description": "Node width."},
                    "height": {"type": "number", "description": "Node height."},
                    "canvas_id": {"type": "string", "description": "Canvas id. Omit for latest canvas."},
                },
                ["node_id"],
            ),
        ),
        Tool(
            name="wcstv_delete_node",
            description="Delete a node and edges connected to it from a WcsTV canvas.",
            inputSchema=_tool_schema(
                {
                    "node_id": {"type": "string", "description": "Node id to delete."},
                    "canvas_id": {"type": "string", "description": "Canvas id. Omit for latest canvas."},
                },
                ["node_id"],
            ),
        ),
        Tool(
            name="wcstv_connect_nodes",
            description="Create an edge between two existing WcsTV canvas nodes.",
            inputSchema=_tool_schema(
                {
                    "from_id": {"type": "string", "description": "Source node id."},
                    "to_id": {"type": "string", "description": "Target node id."},
                    "label": {"type": "string", "description": "Optional edge label."},
                    "canvas_id": {"type": "string", "description": "Canvas id. Omit for latest canvas."},
                },
                ["from_id", "to_id"],
            ),
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    args = arguments or {}
    try:
        if name == "wcstv_health":
            return _json_content(_request_json("GET", "/health"))

        if name == "wcstv_list_canvases":
            return _json_content({"ok": True, "canvases": _list_canvases_raw()})

        if name == "wcstv_get_canvas":
            canvas = _get_canvas(str(args.get("canvas_id") or ""))
            if bool(args.get("include_full")):
                return _json_content({"ok": True, "canvas": canvas})
            return _json_content({"ok": True, "canvas": _canvas_summary(canvas)})

        if name == "wcstv_search_canvas":
            query = str(args.get("query") or "").strip().lower()
            if not query:
                raise RuntimeError("query is required")
            limit = int(args.get("limit") or 20)
            canvas = _get_canvas(str(args.get("canvas_id") or ""))
            matches = []
            for node in canvas.get("nodes") or []:
                if not isinstance(node, dict):
                    continue
                haystack = _node_text(node).lower()
                if query in haystack:
                    matches.append(_node_summary(node))
                    if len(matches) >= limit:
                        break
            return _json_content({"ok": True, "canvas_id": canvas.get("id"), "matches": matches})

        if name == "wcstv_create_text_node":
            text = str(args.get("text") or "").strip()
            if not text:
                raise RuntimeError("text is required")
            canvas = _get_canvas(str(args.get("canvas_id") or ""))
            node = {
                "id": f"codex_{uuid.uuid4().hex[:12]}",
                "type": "note",
                "title": str(args.get("title") or "Codex Note").strip(),
                "text": text,
                "content": text,
                "x": float(args.get("x") if args.get("x") is not None else 0),
                "y": float(args.get("y") if args.get("y") is not None else 0),
                "w": float(args.get("width") if args.get("width") is not None else 360),
                "h": float(args.get("height") if args.get("height") is not None else 220),
                "created_at": int(time.time() * 1000),
            }
            nodes = canvas.setdefault("nodes", [])
            if not isinstance(nodes, list):
                raise RuntimeError("Canvas nodes field is not a list")
            nodes.append(node)
            result = _save_canvas(canvas)
            return _json_content({"ok": True, "node": _node_summary(node), "save": result})

        if name == "wcstv_update_node":
            canvas = _get_canvas(str(args.get("canvas_id") or ""))
            node = _find_node(canvas, str(args.get("node_id") or ""))
            if "text" in args:
                text = str(args.get("text") or "")
                node["text"] = text
                node["content"] = text
            if "title" in args:
                node["title"] = str(args.get("title") or "")
            for source, target in (("x", "x"), ("y", "y"), ("width", "w"), ("height", "h")):
                if source in args:
                    node[target] = float(args[source])
            result = _save_canvas(canvas)
            return _json_content({"ok": True, "node": _node_summary(node), "save": result})

        if name == "wcstv_delete_node":
            node_id = str(args.get("node_id") or "")
            if not node_id:
                raise RuntimeError("node_id is required")
            canvas = _get_canvas(str(args.get("canvas_id") or ""))
            canvas["nodes"] = [
                node for node in (canvas.get("nodes") or [])
                if not isinstance(node, dict) or str(node.get("id")) != node_id
            ]
            canvas["edges"] = [
                edge for edge in (canvas.get("edges") or [])
                if not isinstance(edge, dict)
                or (str(edge.get("from") or edge.get("source")) != node_id and str(edge.get("to") or edge.get("target")) != node_id)
            ]
            result = _save_canvas(canvas)
            return _json_content({"ok": True, "deleted": node_id, "save": result})

        if name == "wcstv_connect_nodes":
            from_id = str(args.get("from_id") or "")
            to_id = str(args.get("to_id") or "")
            if not from_id or not to_id:
                raise RuntimeError("from_id and to_id are required")
            canvas = _get_canvas(str(args.get("canvas_id") or ""))
            _find_node(canvas, from_id)
            _find_node(canvas, to_id)
            edge = {
                "id": f"codex_edge_{uuid.uuid4().hex[:12]}",
                "from": from_id,
                "to": to_id,
                "source": from_id,
                "target": to_id,
                "label": str(args.get("label") or ""),
                "created_at": int(time.time() * 1000),
            }
            edges = canvas.setdefault("edges", [])
            if not isinstance(edges, list):
                raise RuntimeError("Canvas edges field is not a list")
            edges.append(edge)
            result = _save_canvas(canvas)
            return _json_content({"ok": True, "edge": edge, "save": result})

        raise RuntimeError(f"Unknown tool: {name}")
    except Exception as exc:
        return _json_content({"ok": False, "error": str(exc), "tool": name})


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    try:
        import asyncio

        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
