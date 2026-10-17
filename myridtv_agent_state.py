# -*- coding: utf-8 -*-
"""MyridTV Agent 状态读取层（后端拆分第13刀C-X1）：配置图像模型选择三函数、HTML 转义、
Agent 回调本地 HTTP、最新画布/画布 JSON/节点摘要读取、canvas_get_state 与
canvas_search_nodes 两个只读工具。

逐字迁移自 rh_official_proxy.py 连续块 L(_agent_default_image_model)..L(_agent_category_
from_title)（10 函数 133 行，可逆还原行级 diff=0）。行为零变更。
configure() 注入：_DEFAULT_PROVIDER 值（import 时定、零重绑）、PORT getter
（write_app_config 会 global 重绑，必须闭包延迟读）、normalize_model 闭包（留主文件，
def 在注入点之后）；read_api_providers 直引 myridtv_provider。
主文件对被仍引用的 7 函数留同名薄代理，调用点不改。
"""
import json
import re
import time
import uuid
import urllib.parse
import urllib.request

from myridtv_core import unique_strings, parse_number

import myridtv_provider
import myridtv_canvas_store
import myridtv_agent_tools

_DEFAULT_PROVIDER = ""
_port_getter = lambda: 3107
_r_normalize_model = None
_r_canvas_node_image_by_id = None
_r_canvas_repo_upsert_node = None
_r_link_artifact_node = None
_r_upsert_sidebar_artifact = None


def configure(default_provider, port_getter, normalize_model,
              canvas_node_image_by_id, canvas_repo_upsert_node,
              link_artifact_node, upsert_sidebar_artifact):
    global _DEFAULT_PROVIDER, _port_getter, _r_normalize_model
    global _r_canvas_node_image_by_id, _r_canvas_repo_upsert_node
    global _r_link_artifact_node, _r_upsert_sidebar_artifact
    _DEFAULT_PROVIDER = default_provider
    _port_getter = port_getter
    _r_normalize_model = normalize_model
    _r_canvas_node_image_by_id = canvas_node_image_by_id
    _r_canvas_repo_upsert_node = canvas_repo_upsert_node
    _r_link_artifact_node = link_artifact_node
    _r_upsert_sidebar_artifact = upsert_sidebar_artifact


def _agent_default_image_model():
    """默认模型=用户 provider 配置里的第一个文生图模型（用户配置为准，禁硬编码）"""
    return _agent_select_configured_image_model(_DEFAULT_PROVIDER, "", [])


def _agent_configured_image_models(provider_id):
    provider_id = str(provider_id or "").strip()
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
    if provider_id == _DEFAULT_PROVIDER:
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
    from myridtv_canvas_gateway import enroll_existing
    enroll_existing(cid,canvas)
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


# ===== 第13刀C-X2 追加：节点构建辅助区 =====
def _agent_category_from_title(title):
    """从节点 title（如"人物·苏焰"、"场景·废弃工厂"、"道具·信物"）提取类别关键词。
    返回小写类别字符串，无类别返回空串。分类决定画布上的列。"""
    t = str(title or "")
    if not t:
        return ""
    # 取"类别·名称"中的类别段，或直接扫描关键词
    seg = t.split("·")[0].split("：")[0].split(":")[0].strip() if ("·" in t or "：" in t or ":" in t) else t
    for kw in ("人物", "角色", "person", "character"):
        if kw in seg.lower() or kw in t:
            return "人物"
    for kw in ("场景", "scene", "环境", "背景"):
        if kw in t:
            return "场景"
    for kw in ("道具", "物品", "prop", "item", "asset", "素材"):
        if kw in t:
            return "道具"
    for kw in ("剧本", "script", "笔记", "note", "文档", "clip", "分镜", "清单"):
        if kw in t:
            return "文档"
    return ""


def _agent_find_empty_position(canvas, x, y, w, h, step=36, category=None, node_type=None, text_len=0):
    """按类别分列 + 纵向对齐排列，互不重叠。
    - 文本节点(smart-prompt)实际非常宽(632)，列间距必须 ≥ 节点宽，避免左右列互相压盖。
    - 人物/角色 → 列0；场景 → 列1；道具/物品 → 列2；文档/剧本/笔记 → 列3。
    - 同类纵向递增 y，互不重叠。"""
    nodes_list = canvas.get("nodes") if isinstance(canvas.get("nodes"), list) else []
    # 文本节点实际渲染宽高（smart-prompt 632 宽，高度随内容）
    is_text = str(node_type or "") == "smart-prompt" or any(k in str(category or "") for k in ("剧本", "script", "note", "笔记", "文档", "clip", "分镜", "清单"))
    is_gen = str(node_type or "") in ("smart-image", "generation", "image", "gen")
    # 用真实尺寸判断重叠
    width = max(1.0, float(w or (632 if is_text else 320)))
    height = max(1.0, float(h or (420.0 if is_text else 420.0)))
    # 文本节点高度按内容估算（约 每8行+40，最低 400）
    if is_text and text_len:
        est_h = min(1400.0, 400.0 + (text_len // 8) * 12.0)
        height = max(height, est_h)
    # 类别 → 列基准 x；列间距按节点宽拉大（文本 632 宽 → 列距 700）
    col_gap = 700.0 if is_text else 380.0
    cat = str(category or "").strip().lower()
    col_xs = {
        "person": 0.0, "character": 0.0, "人物": 0.0, "角色": 0.0,
        "scene": col_gap, "场景": col_gap,
        "prop": col_gap * 2, "item": col_gap * 2, "道具": col_gap * 2, "物品": col_gap * 2, "asset": col_gap * 2, "素材": col_gap * 2,
        "doc": col_gap * 3, "文档": col_gap * 3, "剧本": col_gap * 3, "clip": col_gap * 3, "cliptable": col_gap * 3,
    }
    is_doc = any(k in cat for k in ("剧本", "script", "note", "笔记", "文档", "text", "clip", "分镜", "清单", "doc"))
    base_x = col_gap * 3 if is_doc else col_xs.get(cat, col_gap * 2 if not is_text else col_gap * 3)

    def overlaps(px, py):
        for n in nodes_list:
            if not isinstance(n, dict):
                continue
            try:
                nx = float(n.get("x") or 0)
                ny = float(n.get("y") or 0)
                # 用节点声明宽高，缺省按文本/图片判断（文本 632）
                nt = str(n.get("type") or "")
                nw = float(n.get("w") or (632 if nt == "smart-prompt" else 320))
                nh = float(n.get("h") or (400 if nt == "smart-prompt" else 420))
            except (TypeError, ValueError):
                continue
            if nw <= 0 or nh <= 0:
                continue
            if px < nx + nw and px + width > nx and py < ny + nh and py + height > ny:
                return True
        return False

    # 在该列基准 x 上，从顶部向下找不重叠的位置
    px, py = base_x, 0.0
    for i in range(500):
        if not overlaps(px, py):
            return px, py
        py += step if step else 36
    return base_x, 0.0


def _agent_tool_create_text_node(args, session_id=""):
    text = str(args.get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "text 必填"}
    cid, canvas = _agent_get_canvas(str(args.get("canvas_id") or ""))
    # ---- Phase 8：Artifact Router（需求第二/五/三十三条）----
    # Router 是唯一分流点。destination=='canvas' 时仍走原有 Gate+Adapter，
    # 不新增第二条建节点路径，因此不会出现双重创建。
    _atype = str(args.get("artifact_type") or args.get("artifactType") or "").strip().lower()
    if not _atype:
        _atype = "text"
    _route = myridtv_canvas_store.route_artifact(
        artifact_type=_atype,
        role="text",
        tool_name="canvas_create_text_node",
        user_text=str(args.get("user_text") or args.get("userText")
                      or myridtv_canvas_store.CANVAS_AGENT_ROUTE_CONTEXT.get("user_text") or ""),
    )
    _dest = str(_route.get("destination") or "canvas")
    _art_id = ""
    if _dest in ("sidebar", "both"):
        _aok, _aid, _asave = _r_upsert_sidebar_artifact(
            cid, canvas,
            title=str(args.get("title") or "Agent 笔记").strip(),
            content=text,
            artifact_type=_atype,
            source_event_id=str(args.get("event_id") or ""),
            # Phase 9：一轮 Agent 会话 = 一个 Conversation Artifact
            conversation_id=str(session_id or myridtv_agent_tools.CANVAS_AGENT_CURRENT_SESSION.get("session_id") or ""),
            conversation_title=str(myridtv_canvas_store.CANVAS_AGENT_ROUTE_CONTEXT.get("user_text") or "")[:40],
            section_type=str(args.get("section_type") or args.get("sectionType") or "").strip(),
            section_title=str(args.get("section_title") or args.get("sectionTitle") or "").strip(),
            item_title=str(args.get("item_title") or args.get("itemTitle") or "").strip(),
        )
        if not _aok:
            # 保存失败：不创建空 artifact，也不降级成空节点（需求第四十一条）
            return {"ok": False, "error": _aid}
        _art_id = _aid
    if _dest == "sidebar":
        return {"ok": True, "node_id": None, "artifact_id": _art_id,
                "destination": "sidebar", "save_ok": True, "reason": _route.get("reason")}
    # 使用智能画布原生文本节点 smart-prompt（前端 promptNodeBodyHtml 渲染 node.text）；
    # 旧 type:'note' 在 smart-canvas 无渲染分支，会兜底成空上传占位节点。
    node_x, node_y = _agent_find_empty_position(canvas, args.get("x"), args.get("y"), 316, 194, category=_agent_category_from_title(args.get("title")), node_type="smart-prompt", text_len=len(text))
    node = {
        "id": "agent_" + uuid.uuid4().hex[:12],
        "type": "smart-prompt",
        "title": str(args.get("title") or "Agent 笔记").strip(),
        "text": text, "content": text,
        "promptDraftText": text,
        "promptDraftHtml": _agent_html_escape(text),
        "promptDraftTouched": True,
        "llmEnabled": False,
        "llmSystemEnabled": False,
        "llmSystemPrompt": "You are a helpful prompt assistant.",
        "llmInstruction": "",
        "x": node_x, "y": node_y,
        "w": 316, "h": 194,
        "created_at": int(time.time() * 1000),
        "__origin": "agent_tool_text",
        "status": "ready",
        "role": "text",
    }
    if _art_id:
        node["artifactId"] = _art_id   # 需求第十四条：Node 与 Artifact 共享身份
    ok, nid, save_ok, deduped = _r_canvas_repo_upsert_node(cid, canvas, node, "agent_tool_text", args)
    if not ok:
        return {"ok": False, "error": nid}
    if not _art_id:
        return {"ok": True, "node_id": nid, "save_ok": save_ok,
                "destination": "canvas", "reason": _route.get("reason")}
    _r_link_artifact_node(cid, canvas, _art_id, nid)
    return {"ok": True, "node_id": nid, "save_ok": save_ok, "artifact_id": _art_id,
            "destination": "both", "reason": _route.get("reason")}


_GENERATION_RATIO_TO_ASPECT = {
    "square": "1:1", "landscape": "3:2", "portrait": "2:3",
    "landscape43": "4:3", "portrait43": "3:4", "wide": "16:9",
    "story": "9:16", "ultrawide": "21:9", "ultratall": "9:21",
}


def _agent_pick_last_generation_settings(nodes):
    """当前画布内最近创建的、带 runSettings 的生成节点。"""
    best = None
    for n in nodes or []:
        if not isinstance(n, dict) or str(n.get("type") or "") != "smart-image":
            continue
        rs = n.get("runSettings")
        if not isinstance(rs, dict) or not (rs.get("provider_id") or rs.get("model")):
            continue
        ts = parse_number(n.get("created_at"), 0) or 0
        if best is None or ts >= best[0]:
            best = (ts, rs)
    return best[1] if best else None


def _agent_last_generation_run_settings(canvas=None, cid=""):
    """新建节点参数继承源：当前画布最近生成节点 -> 最近更新的画布 -> None。"""
    if isinstance(canvas, dict):
        rs = _agent_pick_last_generation_settings(canvas.get("nodes"))
        if rs:
            return rs
    if cid and canvas is None:
        try:
            detail = _agent_http("GET", "/api/canvases/{}".format(urllib.parse.quote(str(cid))), timeout=10)
            cvd = detail.get("canvas") if isinstance(detail, dict) else None
            rs = _agent_pick_last_generation_settings((cvd or {}).get("nodes") if isinstance(cvd, dict) else None)
            if rs:
                return rs
        except Exception:
            pass
    try:
        resp = _agent_http("GET", "/api/canvases")
        items = resp if isinstance(resp, list) else (resp.get("canvases") if isinstance(resp, dict) else [])
        items = [c for c in items if isinstance(c, dict) and str(c.get("id") or "").strip()]
        items.sort(key=lambda c: parse_number(c.get("updated_at"), 0) or 0, reverse=True)
        checked = 0
        for c in items:
            if cid and str(c.get("id")) == str(cid):
                continue
            if checked >= 8:
                break
            checked += 1
            detail = _agent_http("GET", "/api/canvases/{}".format(urllib.parse.quote(str(c.get("id")))), timeout=10)
            cvd = detail.get("canvas") if isinstance(detail, dict) else None
            rs = _agent_pick_last_generation_settings((cvd or {}).get("nodes") if isinstance(cvd, dict) else None)
            if rs:
                return rs
    except Exception:
        pass
    return None


def _agent_first_configured_image_provider():
    """无任何继承源时的兜底：第一个启用了生图模型的平台（不绑定 runninghub）。"""
    try:
        for provider in myridtv_provider.read_api_providers() or []:
            if not isinstance(provider, dict) or provider.get("enabled") is False:
                continue
            if (provider.get("image_models") or []):
                return str(provider.get("id") or "").strip()
    except Exception:
        pass
    return _DEFAULT_PROVIDER


def _agent_default_run_settings(args, preset=None, canvas=None, cid=""):
    preset = preset if isinstance(preset, dict) else {}
    explicit_provider = str(args.get("provider_id") or preset.get("provider_id") or "").strip()
    explicit_model = str(args.get("model") or preset.get("model") or "").strip()
    # 参数继承：没显式指定平台/模型时，复制最近一个生成节点的 runSettings；
    # 新开软件/没有任何生成节点 -> 走全默认（第一个已配模型的平台 + 默认尺寸）。
    inherited = {}
    if not (explicit_provider and explicit_model):
        rs = _agent_last_generation_run_settings(canvas, cid) or {}
        ratio = str(rs.get("customRatio") or "").strip() or _GENERATION_RATIO_TO_ASPECT.get(str(rs.get("ratio") or "").strip(), "")
        inherited = {
            "provider_id": str(rs.get("provider_id") or "").strip(),
            "model": str(rs.get("model") or "").strip(),
            "aspectRatio": ratio,
            "resolution": str(rs.get("resolution") or "").strip(),
            "quality": str(rs.get("quality") or "").strip(),
            "count": rs.get("count"),
        } if rs else {}
    provider_id = explicit_provider or inherited.get("provider_id") or _agent_first_configured_image_provider()
    refs = args.get("reference_image_urls") or args.get("reference_images") or []
    if not isinstance(refs, list):
        refs = [refs]
    refs = [r for r in refs if str(r or "").strip()]
    model = _agent_select_configured_image_model(provider_id, explicit_model or inherited.get("model") or "", refs)
    size = str(args.get("size") or preset.get("size") or "3840x2160")
    aspect = str(args.get("aspect_ratio") or args.get("aspectRatio")
                 or preset.get("aspectRatio") or preset.get("aspect_ratio")
                 or inherited.get("aspectRatio") or "16:9")
    resolution = str(args.get("resolution") or preset.get("resolution") or inherited.get("resolution") or "4k")
    quality = str(args.get("quality") or preset.get("quality") or inherited.get("quality") or "high")
    count = args.get("count") or preset.get("count") or inherited.get("count") or 1
    return {
        "provider_id": provider_id,
        "model": model,
        "size": size,
        "aspectRatio": aspect,
        "resolution": resolution,
        "quality": quality,
        "n": count,
    }


def _agent_reference_image_url(item):
    if isinstance(item, dict):
        url = item.get("url") or item.get("path") or item.get("local_path") or item.get("localPath")
        if not url:
            node_id = str(item.get("nodeId") or item.get("node_id") or "").strip()
            if node_id:
                node_img = _r_canvas_node_image_by_id(node_id, item.get("imageIndex"))
                if node_img:
                    url = node_img
    else:
        url = item
    return str(url or "").strip()


def _agent_normalize_reference_items(refs):
    items = refs if isinstance(refs, list) else ([refs] if refs else [])
    normalized = []
    seen = set()
    for item in items:
        url = _agent_reference_image_url(item)
        if not url or url in seen:
            continue
        seen.add(url)
        source = item if isinstance(item, dict) else {}
        normalized.append({
            "url": url,
            "name": "图片{}".format(len(normalized) + 1),
            "sourceName": str(source.get("name") or source.get("title") or "").strip(),
            "nodeId": str(source.get("nodeId") or source.get("node_id") or "").strip(),
            "imageIndex": int(parse_number(source.get("imageIndex"), 0) or 0),
            "kind": str(source.get("kind") or "image").strip() or "image",
        })
    return normalized


def _agent_payload_reference_images(payload):
    return _agent_normalize_reference_items((payload or {}).get("images") or [])


def _agent_merge_payload_refs_into_tool_args(name, args, payload):
    safe_args = dict(args if isinstance(args, dict) else {})
    if str(name or "").startswith("canvas_"):
        canvas_id = str((safe_args.get("canvas_id") or (payload or {}).get("canvas_id") or "")).strip()
        if canvas_id:
            safe_args["canvas_id"] = canvas_id
    if name not in {"canvas_create_generation_node", "canvas_generate_images", "canvas_create_video_node"}:
        return safe_args
    explicit_refs = safe_args.get("reference_image_urls") or safe_args.get("reference_images") or []
    explicit_refs = _agent_normalize_reference_items(explicit_refs)
    if explicit_refs:
        safe_args["reference_image_urls"] = explicit_refs
        return safe_args
    payload_refs = _agent_payload_reference_images(payload)
    if payload_refs:
        safe_args["reference_image_urls"] = payload_refs
    return safe_args


def _agent_ratio_key(aspect):
    text = str(aspect or "").strip().lower()
    return {
        "1:1": "square", "2:3": "portrait", "3:2": "landscape",
        "3:4": "portrait43", "4:3": "landscape43",
        "9:16": "story", "16:9": "wide", "21:9": "ultrawide", "9:21": "ultratall",
    }.get(text, "square")


def _agent_run_settings_for_storage(settings):
    # 对齐前端 settingsForStorage 结构(smart-canvas.js settings 对象)
    return {
        "engine": "api",
        "apiKind": "image",
        "provider_id": settings.get("provider_id") or "",
        "model": settings.get("model") or "",
        "ratio": _agent_ratio_key(settings.get("aspectRatio") or ""),
        "resolution": settings.get("resolution") or "2k",
        "customRatio": "",
        "customRatioWidth": "",
        "customRatioHeight": "",
        "customSize": "",
        "customWidth": "",
        "customHeight": "",
        "quality": settings.get("quality") or "medium",
        "count": settings.get("n") or 1,
        "videoProvider": "",
        "videoModel": "",
        "videoDuration": 5,
        "videoAspect": "16:9",
        "videoResolution": "",
        "videoEnhancePrompt": False,
        "videoEnableUpsample": False,
        "videoWatermark": False,
        "videoCameraFixed": False,
        "videoGenerateAudio": False,
        "videoMultimodal": False,
        "videoUseFrameRoles": False,
        "videoReferenceMode": "mixed",
        "videoTrustedAsset": False,
        "videoTrustedSource": "library",
        "videoTempShLinks": [],        "comfyMode": "custom",
        "comfyWorkflow": "",
        "comfyParams": {},
        "rhConfigKey": "",
        "rhPayment": "free",
        "rhInstanceType": "",
        "rhParams": {},
        "rhRandomActive": {},
        "width": 3840,
        "height": 2160,
        "enhanceStrength": 0.5,
        "enhanceUpscale": False,
        "enhanceUpscaleRes": 2048,
        "editUpscale": False,
        "editUpscaleRes": 2048,
        "promptH": 124,
    }
