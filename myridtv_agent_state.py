# -*- coding: utf-8 -*-
"""MyridTV Agent 状态读取层（后端拆分第13刀C-X1）：配置图像模型选择三函数、HTML 转义、
Agent 回调本地 HTTP、最新画布/画布 JSON/节点摘要读取、canvas_get_state 与
canvas_search_nodes 两个只读工具。

逐字迁移自 rh_official_proxy.py 连续块 L(_agent_default_image_model)..L(_agent_category_
from_title)（10 函数 133 行，可逆还原行级 diff=0）。行为零变更。
configure() 注入：CANVAS_AGENT_DEFAULT_PROVIDER 值（import 时定、零重绑）、PORT getter
（write_app_config 会 global 重绑，必须闭包延迟读）、normalize_model 闭包（留主文件，
def 在注入点之后）；read_api_providers 直引 myridtv_provider。
主文件对被仍引用的 7 函数留同名薄代理，调用点不改。
"""
import json
import re
import urllib.parse
import urllib.request

from myridtv_core import unique_strings

import myridtv_provider

_DEFAULT_PROVIDER = ""
_port_getter = lambda: 3107
_r_normalize_model = None


def configure(default_provider, port_getter, normalize_model):
    global _DEFAULT_PROVIDER, _port_getter, _r_normalize_model
    _DEFAULT_PROVIDER = default_provider
    _port_getter = port_getter
    _r_normalize_model = normalize_model


def _agent_default_image_model():
    """默认模型=用户 provider 配置里的第一个文生图模型（用户配置为准，禁硬编码）"""
    return _agent_select_configured_image_model(_DEFAULT_PROVIDER, "", [])


def _agent_configured_image_models(provider_id):
    provider_id = str(provider_id or "").strip()
    if provider_id == "custom-api-3":
        provider_id = "runninghub"
    if not provider_id:
        return []
    try:
        for provider in myridtv_provider.read_api_providers() or []:
            if str(provider.get("id") or "").strip() != provider_id:
                continue
            return unique_strings(provider.get("image_models") or [])
    except Exception:
        return []
    return []


def _agent_select_configured_image_model(provider_id, requested_model="", refs=None):
    refs = refs or []
    configured = _agent_configured_image_models(provider_id)
    normalized_models = unique_strings(
        str(m or "").strip().replace("rhart-image-g-2-offcial", "rhart-image-g-2-official")
        for m in configured
    )
    requested = str(requested_model or "").strip().replace("rhart-image-g-2-offcial", "rhart-image-g-2-official")
    if normalized_models:
        if requested:
            normalized_requested = _r_normalize_model(requested, refs)
            if normalized_requested in normalized_models:
                return normalized_requested
            if requested in normalized_models:
                return requested
        preferred_suffixes = ["/image-to-image", "/edit"] if refs else ["/text-to-image"]
        for suffix in preferred_suffixes:
            for model in normalized_models:
                if model.endswith(suffix):
                    return _r_normalize_model(model, refs)
        return _r_normalize_model(normalized_models[0], refs)
    if provider_id in {_DEFAULT_PROVIDER, "custom-api-3"}:
        raise RuntimeError("未找到默认生图模型：请在 API 设置的 RunningHub 下配置生图模型")
    if requested:
        return _r_normalize_model(requested, refs)
    raise RuntimeError("未找到默认生图模型：请先配置生图平台和模型")


def _agent_html_escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _agent_http(method, path, payload=None, timeout=30):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = "http://127.0.0.1:{}{}".format(_port_getter(), path)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with opener.open(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except Exception as exc:
        return {"ok": False, "error": "{}".format(exc)}


def _agent_latest_canvas_id():
    resp = _agent_http("GET", "/api/canvases")
    canvases = resp if isinstance(resp, list) else (resp.get("canvases") if isinstance(resp, dict) else [])
    canvases = [c for c in canvases if isinstance(c, dict)]
    if not canvases:
        raise RuntimeError("没有找到画布")
    canvases.sort(key=lambda c: c.get("updated_at") or c.get("last_modified") or 0, reverse=True)
    cid = str(canvases[0].get("id") or "").strip()
    if not cid:
        raise RuntimeError("最新画布没有 id")
    return cid


def _agent_get_canvas(canvas_id=""):
    cid = str(canvas_id or "").strip() or _agent_latest_canvas_id()
    resp = _agent_http("GET", "/api/canvases/{}".format(urllib.parse.quote(cid)))
    canvas = resp.get("canvas") if isinstance(resp, dict) and isinstance(resp.get("canvas"), dict) else None
    if not canvas:
        raise RuntimeError("画布读取失败: {}".format(resp.get("error") or resp))
    return cid, canvas


def _agent_node_summary(node):
    parts = []
    for key in ("title", "label", "content", "text", "promptDraftText", "runPrompt"):
        val = node.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
    image_urls = []
    for img in node.get("images") or []:
        if isinstance(img, dict) and img.get("url"):
            image_urls.append(str(img["url"]))
        elif isinstance(img, str) and img:
            image_urls.append(img)
        if len(image_urls) >= 3:
            break
    return {
        "id": node.get("id"),
        "type": node.get("type"),
        "title": node.get("title") or node.get("label"),
        "text": ("\n".join(dict.fromkeys(parts)))[:800],
        "image_count": len(node.get("images") or []) if isinstance(node.get("images"), list) else 0,
        "image_urls": image_urls,
    }


def _agent_tool_get_state(args):
    cid, canvas = _agent_get_canvas(str(args.get("canvas_id") or ""))
    nodes = [n for n in (canvas.get("nodes") or []) if isinstance(n, dict)]
    slim = [_agent_node_summary(n) for n in nodes[:120]]
    return {"ok": True, "canvas_id": cid, "title": canvas.get("title"),
            "node_count": len(nodes), "nodes": slim,
            "truncated": len(nodes) > 120}


def _agent_tool_search_nodes(args):
    query = str(args.get("query") or "").strip().lower()
    if not query:
        return {"ok": False, "error": "query 必填"}
    state = _agent_tool_get_state({"canvas_id": args.get("canvas_id") or ""})
    if not state.get("ok"):
        return state
    limit = max(1, min(int(args.get("limit") or 20), 50))
    matches = [n for n in state.get("nodes", []) if query in str(n.get("text") or "").lower()][:limit]
    return {"ok": True, "canvas_id": state.get("canvas_id"), "matches": matches}


