# -*- coding: utf-8 -*-
"""MyridTV 画布/产物存储域（后端拆分第4刀）：画布 json 读写、格式迁移归一、记录 CRUD
（列表/摘要/创建/保存/元数据/回收站/清倒）、导出入包、路由解析 + artifact 身份/分段/
合并/墓碑纯函数族。

逐字迁移自 rh_official_proxy.py 连续块 L(canvas_file_path)..L(next_blender_node_position)
（783 行 35 函数 17 常量，可逆还原行级 diff=0）。行为零变更。
configure() 注入：USER_DATA_DIR/APP_DIR 值 + LOG_FILE getter（write_app_config 重绑）+
resolve_canvas_asset_versions/resolve_user_asset_path 闭包（def 在块后，延迟解析）。
CANVAS_AGENT_ROUTE_CONTEXT / CANVAS_AGENT_CURRENT_PHASE / CONVERSATION_CONTAINER_TYPES /
INDEPENDENT_DOC_TYPES 单例与常量归本模块，主文件留别名再导出（引用面 6/2/1/1）。
主文件对块外仍调用的 24 函数留同名薄代理，调用点不改。
"""
import hashlib
import json
import re
import time
import uuid
from pathlib import Path

import urllib.parse

from myridtv_core import (
    ApiError,
    CanvasConflictError,
    append_log,
    deep_merge,
    parse_number,
    read_json_file,
    write_json_file,
)

_USER_DATA_DIR = None
_APP_DIR = None
_log_file = lambda: None
_r_resolve_canvas_asset_versions = lambda canvas: None
_r_resolve_user_asset_path = lambda url_path: None
_r_prune_canvas_history = lambda canvas_id: None


def configure(user_data_dir, app_dir, log_file_getter,
              resolve_canvas_asset_versions, resolve_user_asset_path,
              prune_canvas_history):
    global _USER_DATA_DIR, _APP_DIR, _log_file
    global _r_resolve_canvas_asset_versions, _r_resolve_user_asset_path
    global _r_prune_canvas_history
    _USER_DATA_DIR = user_data_dir
    _r_prune_canvas_history = prune_canvas_history
    _APP_DIR = app_dir
    _log_file = log_file_getter
    _r_resolve_canvas_asset_versions = resolve_canvas_asset_versions
    _r_resolve_user_asset_path = resolve_user_asset_path


def canvas_file_path(canvas_id):
    safe_id = str(canvas_id or "").strip()
    if not safe_id:
        raise ApiError(400, "缺少 canvas_id")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", safe_id):
        raise ApiError(400, "canvas_id 非法")
    return _USER_DATA_DIR / "data" / "canvases" / f"{safe_id}.json"


def smart_canvas_path(canvas_id):
    return canvas_file_path(canvas_id)


def default_canvas_kind(data=None):
    raw = data if isinstance(data, dict) else {}
    kind = str(raw.get("kind") or "").strip().lower()
    if kind in ("smart", "classic"):
        return kind
    icon = str(raw.get("icon") or "").strip()
    if icon == "sparkles":
        return "smart"
    return "classic"


def default_canvas_title(kind):
    return "Smart Canvas" if kind == "smart" else "Canvas"


# ====== 画布格式版本与迁移入口 ======
# 以后加/改画布字段，只在这里写迁移分支（v1 -> v2 ...），不要再往各处散落兼容代码。
# 读画布时只做内存迁移（不改盘）；写画布时统一由本函数盖上当前版本号。
CANVAS_FORMAT_VERSION = 1
CANVAS_FORMAT_FIELD = "formatVersion"
CANVAS_MIGRATION_LOGGED = set()


def migrate_canvas_format(canvas_id, canvas):
    """把画布数据升到当前格式版本（就地修改 canvas 并返回）。

    v0 -> v1：补 formatVersion 字段（历史画布都没有），并保证基础结构存在。
    """
    if not isinstance(canvas, dict):
        return canvas
    raw = canvas.get(CANVAS_FORMAT_FIELD)
    try:
        version = int(str(raw).strip()) if raw is not None else 0
    except Exception:
        version = 0
    if version < 1:
        canvas.setdefault("nodes", [])
        canvas.setdefault("connections", [])
        canvas.setdefault("artifacts", [])
        canvas.setdefault("deleted", [])
        version = 1
    if canvas.get(CANVAS_FORMAT_FIELD) != version:
        canvas[CANVAS_FORMAT_FIELD] = version
        key = (str(canvas_id), version)
        if key not in CANVAS_MIGRATION_LOGGED:
            CANVAS_MIGRATION_LOGGED.add(key)
            try:
                append_log(_log_file(), "[CanvasFormat] canvas={} 迁移到 formatVersion={}".format(canvas_id, version))
            except Exception:
                pass
    return canvas


def normalize_canvas_structure(canvas_id, data):
    now_ms = int(time.time() * 1000)
    canvas = dict(data) if isinstance(data, dict) else {}
    kind = default_canvas_kind(canvas)
    canvas.setdefault("id", canvas_id)
    canvas.setdefault("kind", kind)
    canvas.setdefault("title", default_canvas_title(kind))
    canvas.setdefault("icon", "sparkles" if kind == "smart" else "layers")
    canvas.setdefault("owner", "")
    canvas.setdefault("color", "")
    canvas.setdefault("pinned", False)
    canvas.setdefault("created_at", now_ms)
    canvas.setdefault("updated_at", now_ms)
    canvas.setdefault("nodes", [])
    canvas.setdefault("connections", [])
    canvas.setdefault("logs", [])
    canvas.setdefault("deleted", [])
    canvas.setdefault("artifacts", [])  # Phase 8：Agent 持久产物侧边栏（按 canvas 隔离，与 nodes 同级）
    # 画布输入模式：connections（连线，默认，旧画布行为不变）/ objects（无线 Set-Get）
    if canvas.get("inputMode") not in ("connections", "objects"):
        canvas["inputMode"] = "connections"
    canvas.setdefault("viewport", {"x": 0, "y": 0, "scale": 1})
    canvas.setdefault("settings", {})
    return migrate_canvas_format(canvas_id, canvas)


NODE_TOMBSTONE_LIMIT = 500

ARTIFACT_LIMIT = 300

# Phase 8：默认路由策略。文档/结构化文本 -> sidebar；媒体 -> canvas。
# 需求第四/五条：不要把图片、视频、音频改成必须先进 Sidebar。
ARTIFACT_SIDEBAR_TYPES = {
    "markdown", "document", "brief", "creative_brief", "script",
    "story_outline", "story_bible", "character_bible", "character_profile",
    "world_bible", "world_setting", "visual_direction", "brainstorm",
    "table", "csv", "html", "interactive", "deck", "presentation",
    "text", "note", "outline", "analysis", "report",
}
ARTIFACT_CANVAS_TYPES = {
    "image", "video", "audio", "generated_image", "generated_video",
    "generated_audio", "media",
}
# 安全总开关：文档类默认进 Sidebar 而不是直接建 Canvas Node（需求第五条 / 验收 E）。
# 若线上出现误伤，把这里改 False 即可回退到旧行为（文本仍建节点）。
ARTIFACT_TEXT_DEFAULT_SIDEBAR = True

# 当前 Agent run 的用户原话。工具执行链路里拿不到 payload，
# 用它把"放到画布"/"保存成文档"这类显式意图透传给 route_artifact（需求第三十二条）。
CANVAS_AGENT_ROUTE_CONTEXT = {"user_text": ""}

# ===== Agent→Canvas Mutation 收口（老王 46 条验收规格）=====
# 所有节点创建通道统一经 CanvasMutationManager 的硬守卫 + Ledger。
# 安全 import：模块缺失也不影响后端启动（守卫降级为既有 Artifact Gate）。
try:
    import canvas_mutation_manager as _cmm
except Exception:  # pragma: no cover - 模块缺失时降级
    _cmm = None

# 阶段上下文：Agent 编排循环设置当前阶段（ASSET_DISCOVERY / REFERENCE_ASSET_GENERATION /
# VIDEO_PROMPT 等）。设置后，MutationManager 的阶段守卫即生效，发现阶段禁止建节点。
# 未设置时阶段守卫不激活（向后兼容现有 Agent 直接调工具的流程）。
CANVAS_AGENT_CURRENT_PHASE = {"phase": ""}


# 显式用户意图 -> 目标（需求第三十二条：显式用户操作优先级最高）
ARTIFACT_EXPLICIT_CANVAS_HINTS = (
    "放到画布", "放到画布上", "加入画布", "加入canvas", "创建成节点", "建成节点",
    "生成节点", "放到canvas", "放到 canvas", "加到画布",
)
ARTIFACT_EXPLICIT_SIDEBAR_HINTS = (
    "保存成文档", "存成文档", "保存为文件", "存到文件", "保存成文件",
    "只要文档", "不用建节点", "不要建节点",
)


# =====================================================================
# Phase 9 · Conversation Artifact 分层模型
# ---------------------------------------------------------------------
#   一个 Canvas 可以有多个 Conversation（= 一次完整 Agent 头脑风暴 / 会话）
#   一个 Conversation 内部再按 Section -> Item 分层。
#   Section 不是 Artifact，不单独占 Sidebar 一级条目。
#
#   关键：所有 ID 都是确定性推导（不是 uuid），所以
#     - 同一会话 + 同一类型            -> 永远同一个 Conversation Artifact
#     - 同一会话 + 同一板块            -> 永远同一个 Section（连改 5 次仍是 1 个）
#     - 重试 / stream replay / 409 重存 -> 天然幂等，不会裂成多份
# =====================================================================

# 容器型产物：这类类型的产物内部按 Section 组织，是一级 Conversation 条目。
# 收窄原则：只有"一轮讨论会自然产出多个板块"的创意/结构型类型才算容器；
# script / markdown / report 这类"成品文档"保持独立文件，不并进会话
# （与前端 CONVERSATION_CONTAINER_TYPES 必须逐项一致）。
CONVERSATION_CONTAINER_TYPES = frozenset((
    "brainstorm", "creative_session", "document_session", "research_session",
    "story_bible", "character_bible", "world_bible",
    "story_outline", "outline", "visual_direction", "creative_brief", "brief",
))

# 独立文档型：这类产物保持 Sidebar 一级独立条目（如 project.md），
# 即使在会话内产生也不吸进 Conversation 容器（需求：Conversation 与文档共存）。
# 必须与前端 INDEPENDENT_DOC_TYPES 逐项一致。
INDEPENDENT_DOC_TYPES = frozenset((
    "document", "markdown", "file", "table", "csv",
    "html", "interactive", "deck", "presentation",
))

# 板块类型：Section 的语义分类（决定默认图标与去重键）
SECTION_TYPE_META = {
    "character":  {"label": "核心人物", "icon": "users"},
    "story":      {"label": "故事设定", "icon": "book-open"},
    "scene":      {"label": "关键场面", "icon": "clapperboard"},
    "world":      {"label": "世界观",   "icon": "globe"},
    "visual":     {"label": "视觉方向", "icon": "palette"},
    "direction":  {"label": "方案方向", "icon": "compass"},
    "custom":     {"label": "其他",     "icon": "shapes"},
}

# 标题关键词 -> 板块类型（Agent 没显式给 section_type 时按标题推断）
_SECTION_TYPE_KEYWORDS = (
    ("character", ("人物", "角色", "人设", "character", "主角")),
    ("story",     ("故事", "剧情", "梗概", "大纲", "story", "plot", "主线")),
    ("scene",     ("场面", "场景", "分镜", "镜头", "scene", "关键场", "高潮")),
    ("world",     ("世界观", "势力", "world", "地理", "规则", "设定集")),
    ("visual",    ("视觉", "美术", "色彩", "摄影", "灯光", "材质", "visual", "画风")),
    ("direction", ("方向", "结局", "方案", "候选", "direction", "版本")),
)


def _artifact_hash(*parts):
    """FNV-1a 32-bit。必须与前端 artifactHash() 逐字节一致，否则前后端会算出不同的
    artifactId / sectionId，同一轮 Brainstorm 会裂成两份。

    两个易错点（都踩过）：
      1. 按 UTF-16 code unit 迭代，与 JS 的 charCodeAt 对齐（不能用 Python 的码点迭代，
         遇到 emoji 等非 BMP 字符两边会分叉）。
      2. 全程保持 32 位无符号；JS 侧必须用 Math.imul，否则 h*16777619 超过 2^53 会丢精度。
    """
    h = 2166136261
    for p in parts:
        raw = str(p if p is not None else "")
        buf = raw.encode("utf-16-le", "surrogatepass")
        for i in range(0, len(buf) - 1, 2):
            h = ((h ^ (buf[i] | (buf[i + 1] << 8))) * 16777619) & 0xFFFFFFFF
        if len(buf) % 2:
            h = ((h ^ buf[-1]) * 16777619) & 0xFFFFFFFF
    return format(h, "08x")


def conversation_artifact_id(canvas_id, conversation_id, artifact_type="brainstorm"):
    """Conversation Artifact 的确定性 ID。同一 canvas + 同一会话 + 同一类型 -> 同一 ID。"""
    return "conv_" + _artifact_hash(
        str(canvas_id or ""),
        str(conversation_id or ""),
        str(artifact_type or "brainstorm").strip().lower(),
    )


def artifact_section_id(conversation_id, section_type, section_title):
    """Section 的确定性 ID。优先按 type 去重（连改 5 次"核心人物"仍是 1 个 Section）。"""
    stype = str(section_type or "").strip().lower()
    stitle = str(section_title or "").strip()
    if stype:
        return "sec_" + _artifact_hash(str(conversation_id or ""), "t:" + stype)
    return "sec_" + _artifact_hash(str(conversation_id or ""), "n:" + stitle.lower())


def artifact_item_id(section_id, item_title):
    """Item 的确定性 ID。无名 Item 归并为该 Section 的主条目。"""
    t = str(item_title or "").strip()
    if not t:
        return str(section_id or "") + "_main"
    return "item_" + _artifact_hash(str(section_id or ""), t.lower())


def infer_section_type(title="", explicit=""):
    """显式 section_type 优先；否则按标题关键词推断；都落空返回 custom。"""
    e = str(explicit or "").strip().lower()
    if e in SECTION_TYPE_META:
        return e
    t = str(title or "").lower()
    for stype, kws in _SECTION_TYPE_KEYWORDS:
        for kw in kws:
            if kw.lower() in t:
                return stype
    return "custom"


def section_type_label(stype):
    return (SECTION_TYPE_META.get(str(stype or "custom").strip().lower())
            or SECTION_TYPE_META["custom"])["label"]


def _merge_items(*sources):
    """Item 并集：按 id 去重，同 id 取 updatedAt 较新的一份。"""
    merged, order = {}, []
    for source in sources:
        if not isinstance(source, list):
            continue
        for it in source:
            if not isinstance(it, dict):
                continue
            iid = str(it.get("id") or "").strip()
            if not iid:
                iid = "item_" + _artifact_hash(str(it.get("title") or "").lower())
            prev = merged.get(iid)
            if prev is None:
                merged[iid] = dict(it, id=iid)
                order.append(iid)
                continue
            if int(it.get("updatedAt") or 0) >= int(prev.get("updatedAt") or 0):
                merged[iid] = dict(it, id=iid)
    return [merged[i] for i in order]


def _merge_sections(*sources):
    """Section 并集：按 id 去重并保留 order；内部 items 再做一次并集。

    返回 None 表示两个来源都没有 sections 字段（调用方保持原样，不写空数组）。
    """
    has_any = False
    merged, order = {}, []
    for source in sources:
        if not isinstance(source, list):
            continue
        has_any = True
        for sec in source:
            if not isinstance(sec, dict):
                continue
            sid = str(sec.get("id") or "").strip()
            if not sid:
                sid = "sec_" + _artifact_hash(str(sec.get("type") or ""), str(sec.get("title") or "").lower())
            prev = merged.get(sid)
            if prev is None:
                merged[sid] = dict(sec, id=sid, items=_merge_items(sec.get("items")))
                order.append(sid)
                continue
            newer = int(sec.get("updatedAt") or 0) >= int(prev.get("updatedAt") or 0)
            base = dict(sec) if newer else dict(prev)
            base["id"] = sid
            base["items"] = _merge_items(prev.get("items"), sec.get("items"))
            base.setdefault("order", len(order))
            merged[sid] = base
    if not has_any:
        return None
    out = [merged[i] for i in order]
    out.sort(key=lambda s: int(s.get("order") or 0))
    for i, s in enumerate(out):
        s["order"] = i
    return out


def _merge_artifacts(*sources):
    """Phase 8：合并 Artifact 列表（按 id/artifactId 去重、保留 updatedAt 最新、上限截断）。

    与 _merge_node_tombstones 同构：没有它，多端保存会让同一份文档裂成多份
    （stream replay / retry / 409 重存都会触发，需求第二十二条）。
    """
    merged = {}
    order = []
    for source in sources:
        if not isinstance(source, list):
            continue
        for item in source:
            if not isinstance(item, dict):
                continue
            aid = str(item.get("id") or item.get("artifactId") or "").strip()
            if not aid:
                continue
            prev = merged.get(aid)
            if prev is None:
                merged[aid] = dict(item)
                order.append(aid)
                continue
            # 同 id：保留 updatedAt 较新的一份（update，不 append duplicate）
            _newer = int(item.get("updatedAt") or item.get("updated_at") or 0) >= int(prev.get("updatedAt") or prev.get("updated_at") or 0)
            _base = dict(item) if _newer else dict(prev)
            # Phase 9：sections 是分层内容，不能整体覆盖 —— 做双向并集后按 id 去重
            _secs = _merge_sections(prev.get("sections"), item.get("sections"))
            if _secs is not None:
                _base["sections"] = _secs
            merged[aid] = _base
    out = [merged[a] for a in order]
    if len(out) > ARTIFACT_LIMIT:
        out = out[-ARTIFACT_LIMIT:]
    return out


def route_artifact(artifact_type=None, role=None, tool_name=None, user_text=None, existing=None):
    """Phase 8：Artifact Router —— 决定产物去 canvas / sidebar / both。

    返回 dict: {"destination": "canvas"|"sidebar"|"both", "reason": str}

    优先级（需求第三十一/三十二条）：
      1. 显式用户操作（"放到画布" / "保存成文档"）最高
      2. tool_name（canvas_create_text_node vs canvas_generate_images）
      3. artifact_type / role
      4. 兜底 canvas（保守：宁可走已存在的媒体流程）
    绝不基于 LLM 的一句自然语言直接决定 createNode。
    """
    atype = str(artifact_type or "").strip().lower()
    arole = str(role or "").strip().lower()
    tool = str(tool_name or "").strip().lower()
    text = str(user_text or "")

    # 1) 显式用户意图
    low = text.lower()
    for hint in ARTIFACT_EXPLICIT_CANVAS_HINTS:
        if hint in text or hint in low:
            return {"destination": "both", "reason": "explicit_canvas:" + hint}
    for hint in ARTIFACT_EXPLICIT_SIDEBAR_HINTS:
        if hint in text or hint in low:
            return {"destination": "sidebar", "reason": "explicit_sidebar:" + hint}

    # 2) 工具判定：文本节点工具 -> sidebar（需求第五条）；生成工具 -> canvas（需求第五条后半）
    if tool == "canvas_create_text_node":
        if ARTIFACT_TEXT_DEFAULT_SIDEBAR:
            return {"destination": "sidebar", "reason": "tool:text_node_default_sidebar"}
        return {"destination": "canvas", "reason": "tool:text_node_legacy_canvas"}
    if tool in ("canvas_create_generation_node", "canvas_generate_images"):
        return {"destination": "canvas", "reason": "tool:generation"}
    if tool.startswith("canvas_"):
        # 其余画布工具（update/link/delete/search/state）不产生新 Artifact
        return {"destination": "canvas", "reason": "tool:canvas_mutation"}

    # 3) 类型 / 角色判定
    if atype in ARTIFACT_CANVAS_TYPES or arole in ("media", "generation", "output"):
        return {"destination": "canvas", "reason": "type:media"}
    if atype in ARTIFACT_SIDEBAR_TYPES or arole in ("text", "container"):
        return {"destination": "sidebar", "reason": "type:document"}

    # 4) 兜底：已有 placement 则保持，否则 canvas（保守）
    if existing:
        return {"destination": existing, "reason": "keep_existing"}
    return {"destination": "canvas", "reason": "fallback_canvas"}


def _merge_node_tombstones(*sources):
    """Phase 4：合并节点删除墓碑（按 id 去重、保留最新 at、上限截断）。

    墓碑项形如 {"id","at","by"}。没有墓碑，多端画布合并会把已删节点"复活"
    （前端 mergeSmartNodeLists 的 "仅本地存在就保留" 语义）。
    """
    merged = {}
    for src in sources:
        if not isinstance(src, list):
            continue
        for item in src:
            if not isinstance(item, dict):
                continue
            nid = str(item.get("id") or "").strip()
            if not nid:
                continue
            try:
                at = int(item.get("at") or 0)
            except Exception:
                at = 0
            prev = merged.get(nid)
            if prev is None or at >= int(prev.get("at") or 0):
                merged[nid] = {"id": nid, "at": at, "by": str(item.get("by") or "")}
    out = sorted(merged.values(), key=lambda t: int(t.get("at") or 0))
    if len(out) > NODE_TOMBSTONE_LIMIT:
        out = out[-NODE_TOMBSTONE_LIMIT:]
    return out


def _drop_tombstoned_nodes(record):
    """按 record["deleted"] 墓碑过滤 nodes/connections，杜绝陈旧客户端复活已删节点。"""
    dead = {str(t.get("id")) for t in (record.get("deleted") or []) if isinstance(t, dict) and t.get("id")}
    if not dead:
        return record
    record["nodes"] = [n for n in (record.get("nodes") or []) if str((n or {}).get("id")) not in dead]
    record["connections"] = [
        c for c in (record.get("connections") or [])
        if str((c or {}).get("from")) not in dead and str((c or {}).get("to")) not in dead
    ]
    return record


def canvas_summary(canvas):
    safe_canvas = normalize_canvas_structure(str((canvas or {}).get("id") or ""), canvas)
    return {
        "id": safe_canvas.get("id"),
        "title": safe_canvas.get("title") or default_canvas_title(default_canvas_kind(safe_canvas)),
        "icon": safe_canvas.get("icon") or ("sparkles" if safe_canvas.get("kind") == "smart" else "layers"),
        "kind": safe_canvas.get("kind") or default_canvas_kind(safe_canvas),
        "owner": safe_canvas.get("owner") or "",
        "color": safe_canvas.get("color") or "",
        "cover": safe_canvas.get("cover") or "",
        "pinned": bool(safe_canvas.get("pinned")),
        "created_at": int(safe_canvas.get("created_at") or 0),
        "updated_at": int(safe_canvas.get("updated_at") or 0),
        "deleted_at": int(safe_canvas.get("deleted_at") or 0),
        "node_count": len(safe_canvas.get("nodes") or []),
        "asset_node_count": sum(1 for _n in (safe_canvas.get("nodes") or []) if (_n.get("images") or [])),
    }


def read_canvas_record(canvas_id, include_deleted=True):
    path = canvas_file_path(canvas_id)
    if not path.exists():
        raise ApiError(404, f"目标画布不存在: {canvas_id}")
    canvas = normalize_canvas_structure(canvas_id, read_json_file(path, {}))
    try:
        # 引用策略解析：带 assetId 的引用按 latest/pinned 解析到目标版本（无引用时零开销）
        _r_resolve_canvas_asset_versions(canvas)
    except Exception as exc:
        append_log(_log_file(), "[AssetVersion] resolve failed canvas={} err={}".format(canvas_id, exc))
    if canvas.get("deleted_at") and not include_deleted:
        raise ApiError(404, "目标画布已在回收站")
    return canvas


def list_canvas_records(include_deleted=False):
    canvas_dir = _USER_DATA_DIR / "data" / "canvases"
    try:
        files = list(canvas_dir.glob("*.json"))
    except Exception:
        files = []
    records_by_id = {}
    for path in files:
        canvas_id = path.stem
        try:
            canvas = normalize_canvas_structure(canvas_id, read_json_file(path, {}))
        except Exception:
            continue
        real_id = str(canvas.get("id") or "").strip()
        if not real_id or path.name != f"{real_id}.json":
            continue
        deleted = bool(canvas.get("deleted_at"))
        if include_deleted:
            if deleted:
                records_by_id[real_id] = canvas_summary(canvas)
        elif not deleted:
            records_by_id[real_id] = canvas_summary(canvas)
    records = list(records_by_id.values())
    records.sort(key=lambda item: (int(item.get("pinned") or 0), int(item.get("updated_at") or 0), int(item.get("created_at") or 0)), reverse=True)
    return records


def create_canvas_record(payload=None):
    payload = payload if isinstance(payload, dict) else {}
    canvas_id = uuid.uuid4().hex
    kind = default_canvas_kind(payload)
    now_ms = int(time.time() * 1000)
    canvas = normalize_canvas_structure(canvas_id, {
        "id": canvas_id,
        "title": str(payload.get("title") or "").strip() or default_canvas_title(kind),
        "icon": str(payload.get("icon") or "").strip() or ("sparkles" if kind == "smart" else "layers"),
        "kind": kind,
        "owner": str(payload.get("owner") or "").strip(),
        "color": str(payload.get("color") or "").strip(),
        "pinned": bool(payload.get("pinned")),
        "created_at": now_ms,
        "updated_at": now_ms,
        "nodes": payload.get("nodes") if isinstance(payload.get("nodes"), list) else [],
        "connections": payload.get("connections") if isinstance(payload.get("connections"), list) else [],
        "logs": payload.get("logs") if isinstance(payload.get("logs"), list) else [],
        "viewport": payload.get("viewport") if isinstance(payload.get("viewport"), dict) else {"x": 0, "y": 0, "scale": 1},
        "settings": payload.get("settings") if isinstance(payload.get("settings"), dict) else {},
    })
    path = canvas_file_path(canvas_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_file(path, canvas)
    return canvas


def save_canvas_record(canvas_id, payload=None):
    payload = payload if isinstance(payload, dict) else {}
    current = read_canvas_record(canvas_id, include_deleted=True)
    if current.get("deleted_at"):
        raise ApiError(409, "目标画布已在回收站，不能保存")
    base_updated_at = int(parse_number(payload.get("base_updated_at"), 0) or 0)
    current_updated_at = int(current.get("updated_at") or 0)
    if base_updated_at and current_updated_at and base_updated_at < current_updated_at:
        raise CanvasConflictError(current)

    kind = default_canvas_kind({**current, **payload})
    now_ms = int(time.time() * 1000)
    saved = normalize_canvas_structure(canvas_id, {
        **current,
        "title": str(payload.get("title") or current.get("title") or default_canvas_title(kind)).strip() or default_canvas_title(kind),
        "icon": str(payload.get("icon") or current.get("icon") or ("sparkles" if kind == "smart" else "layers")).strip() or ("sparkles" if kind == "smart" else "layers"),
        "kind": kind,
        "owner": str(payload.get("owner") if payload.get("owner") is not None else current.get("owner") or "").strip(),
        "color": str(payload.get("color") if payload.get("color") is not None else current.get("color") or "").strip(),
        "pinned": bool(payload.get("pinned")) if "pinned" in payload else bool(current.get("pinned")),
        "nodes": payload.get("nodes") if isinstance(payload.get("nodes"), list) else list(current.get("nodes") or []),
        "connections": payload.get("connections") if isinstance(payload.get("connections"), list) else list(current.get("connections") or []),
        "logs": payload.get("logs") if isinstance(payload.get("logs"), list) else list(current.get("logs") or []),
        "viewport": payload.get("viewport") if isinstance(payload.get("viewport"), dict) else dict(current.get("viewport") or {"x": 0, "y": 0, "scale": 1}),
        "settings": payload.get("settings") if isinstance(payload.get("settings"), dict) else dict(current.get("settings") or {}),
        "deleted": _merge_node_tombstones(current.get("deleted"), payload.get("deleted")),
        "artifacts": _merge_artifacts(current.get("artifacts"), payload.get("artifacts")),
        "inputMode": (payload.get("inputMode") if payload.get("inputMode") in ("connections", "objects")
                      else (current.get("inputMode") if current.get("inputMode") in ("connections", "objects") else "connections")),
        "updated_at": now_ms,
    })
    saved.pop("deleted_at", None)
    _drop_tombstoned_nodes(saved)
    write_json_file(canvas_file_path(canvas_id), saved)
    return saved


def update_canvas_meta(canvas_id, patch=None):
    patch = patch if isinstance(patch, dict) else {}
    current = read_canvas_record(canvas_id, include_deleted=False)
    kind = default_canvas_kind(current)
    now_ms = int(time.time() * 1000)
    if "pinned" in patch:
        pinned = bool(patch.get("pinned"))
    else:
        pinned = bool(current.get("pinned"))
    updated = normalize_canvas_structure(canvas_id, {
        **current,
        "title": str(patch.get("title") if patch.get("title") is not None else current.get("title") or default_canvas_title(kind)).strip() or default_canvas_title(kind),
        "icon": str(patch.get("icon") if patch.get("icon") is not None else current.get("icon") or ("sparkles" if kind == "smart" else "layers")).strip() or ("sparkles" if kind == "smart" else "layers"),
        "owner": str(patch.get("owner") if patch.get("owner") is not None else current.get("owner") or "").strip(),
        "color": str(patch.get("color") if patch.get("color") is not None else current.get("color") or "").strip(),
        "cover": str(patch.get("cover") if patch.get("cover") is not None else current.get("cover") or "").strip(),
        "pinned": pinned,
        "updated_at": now_ms,
    })
    write_json_file(canvas_file_path(canvas_id), updated)
    return updated


def touch_canvas_record(canvas_id):
    current = read_canvas_record(canvas_id, include_deleted=False)
    current["updated_at"] = int(time.time() * 1000)
    write_json_file(canvas_file_path(canvas_id), current)
    return current


def trash_canvas_record(canvas_id):
    current = read_canvas_record(canvas_id, include_deleted=False)
    now_ms = int(time.time() * 1000)
    current["deleted_at"] = now_ms
    current["updated_at"] = now_ms
    write_json_file(canvas_file_path(canvas_id), current)
    return current


def restore_canvas_record(canvas_id):
    current = read_canvas_record(canvas_id, include_deleted=True)
    if not current.get("deleted_at"):
        return current
    current.pop("deleted_at", None)
    current["updated_at"] = int(time.time() * 1000)
    write_json_file(canvas_file_path(canvas_id), current)
    return current


def purge_canvas_record(canvas_id):
    path = canvas_file_path(canvas_id)
    if not path.exists():
        raise ApiError(404, f"目标画布不存在: {canvas_id}")
    path.unlink()
    return {"ok": True, "id": canvas_id}


def purge_all_trash_records():
    """永久清空回收站：删除所有 deleted_at > 0 的画布文件，返回清理数量与列表。"""
    canvas_dir = _USER_DATA_DIR / "data" / "canvases"
    if not canvas_dir.exists():
        return {"ok": True, "purged": 0, "ids": []}
    purged_ids = []
    for path in canvas_dir.iterdir():
        if not path.is_file() or path.suffix != ".json":
            continue
        try:
            data = read_json_file(path, {})
        except Exception:
            continue
        if data.get("deleted_at"):
            try:
                path.unlink()
                purged_ids.append(path.stem)
            except Exception as exc:
                append_log(_log_file(), f"purge_all_trash failed for {path.name}: {exc}")
    return {"ok": True, "purged": len(purged_ids), "ids": purged_ids}


# ====== 画布导出 / 导入（带格式版本的信封）======
# 导出文件结构：{app, version, exportedAt, source, media, canvas}
#   - version 是"导出文件格式"版本（与画布自身 formatVersion 分开：一个是文件信封，一个是数据格式）
#   - 导入时：带信封的按版本校验（高于当前支持版本直接拒绝）；裸画布 JSON 也接受（老文件/手工文件）
CANVAS_EXPORT_APP = "myridtv"
CANVAS_EXPORT_VERSION = 1


def app_version_string():
    try:
        return (_APP_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def collect_canvas_media_urls(value, urls=None):
    """递归收集画布结构里引用到的 /assets/ 地址（去重）。"""
    if urls is None:
        urls = set()
    if isinstance(value, str):
        if value.startswith("/assets/"):
            urls.add(value.split("?", 1)[0].split("#", 1)[0])
    elif isinstance(value, dict):
        for item in value.values():
            collect_canvas_media_urls(item, urls)
    elif isinstance(value, list):
        for item in value:
            collect_canvas_media_urls(item, urls)
    return urls


def missing_canvas_media(urls):
    """哪些媒体地址在本机找不到实体文件（导入后提示用）。"""
    missing = []
    for url in urls:
        try:
            _r_resolve_user_asset_path(url)
        except Exception:
            missing.append(url)
    return missing


def export_canvas_payload(canvas_id):
    canvas = read_canvas_record(canvas_id, include_deleted=True)
    payload = {key: value for key, value in canvas.items() if key != "deleted_at"}
    media = sorted(collect_canvas_media_urls(payload))
    return {
        "app": CANVAS_EXPORT_APP,
        "version": CANVAS_EXPORT_VERSION,
        "exportedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": {
            "canvas_id": canvas_id,
            "canvas_format_version": int(payload.get(CANVAS_FORMAT_FIELD) or CANVAS_FORMAT_VERSION),
            "app_version": app_version_string(),
        },
        "media": {"count": len(media), "urls": media},
        "canvas": payload,
    }


def import_canvas_payload(payload):
    """导入画布：始终新建一张画布，绝不覆盖已有画布。"""
    data = payload if isinstance(payload, dict) else {}
    if isinstance(data.get("data"), dict):
        data = data["data"]
    notes = []
    if isinstance(data.get("canvas"), dict):
        raw_file_version = data.get("version")
        try:
            file_version = int(raw_file_version)
        except Exception:
            file_version = 0
        if file_version > CANVAS_EXPORT_VERSION:
            raise ApiError(400, "导出文件格式版本 {} 高于当前支持的 {}，请先升级 MyridTV 再导入".format(
                file_version, CANVAS_EXPORT_VERSION))
        raw = dict(data["canvas"])
        notes.append("导出文件 v{}".format(file_version))
    else:
        raw = dict(data)
        notes.append("裸画布数据（无导出信封）")
    raw.pop("deleted_at", None)
    media = sorted(collect_canvas_media_urls(raw))
    new_id = uuid.uuid4().hex
    now_ms = int(time.time() * 1000)
    title = str(raw.get("title") or "").strip() or "导入的画布"
    canvas = normalize_canvas_structure(new_id, {
        **raw,
        "id": new_id,
        "title": title,
        "created_at": now_ms,
        "updated_at": now_ms,
        "deleted": [],
        "deleted_at": None,
    })
    canvas.pop("deleted_at", None)
    write_json_file(canvas_file_path(new_id), canvas)
    missing = missing_canvas_media(media)
    append_log(_log_file(), "[CanvasImport] new={} title={} media={} missing={}".format(
        new_id, title[:40], len(media), len(missing)))
    if notes:
        notes.append("画布数据格式已对齐到 formatVersion={}".format(canvas.get(CANVAS_FORMAT_FIELD, CANVAS_FORMAT_VERSION)))
    return {
        "ok": True,
        "canvas": canvas,
        "notes": notes,
        "media": {"count": len(media), "missingCount": len(missing), "missing": missing[:50]},
    }


def parse_canvas_route(request_path):
    prefix = "/api/canvases"
    if request_path == prefix:
        return ("collection", "")
    if request_path == prefix + "/trash":
        return ("trash", "")
    if request_path == prefix + "/trash/purge-all":
        return ("trashPurgeAll", "")
    if request_path == prefix + "/import":
        return ("import", "")
    if not request_path.startswith(prefix + "/"):
        return (None, "")
    tail = request_path[len(prefix) + 1:]
    for suffix, route_name in (
        ("/export", "export"),
        ("/meta", "meta"),
        ("/touch", "touch"),
        ("/restore", "restore"),
        ("/purge", "purge"),
    ):
        if tail.endswith(suffix):
            return (route_name, urllib.parse.unquote(tail[:-len(suffix)]))
    return ("item", urllib.parse.unquote(tail))


