# -*- coding: utf-8 -*-
"""CanvasMutationManager —— Agent → Canvas 节点创建的【唯一受控入口】。

设计目标（对应老王 46 条验收规格）：
- 模型即使犯错，也不可能在 Prompt Ready 以前往 Canvas 写入垃圾节点。
- 所有 Canvas 修改统一经过本模块，每次 mutation 记录到 Ledger（correlationId + 阶段 + 校验结果）。
- 最底层硬守卫（#41）：缺 assetId / 空 prompt / promptStatus!=ready / 非法类型 / 重复 assetId 一律拒绝。
- Edge 只能按 Stable ID 创建（#8），禁止按名称猜测。

本模块不依赖 rh_official_proxy，可独立被单元测试/确定性 E2E 直接 import。
后端 nodeStore / Agent Tool 通过本模块落地节点。
"""
import time
import uuid

# ---- Asset / Video 状态机（#33）----
ASSET_STATES = [
    "DISCOVERED", "SELECTED", "PROMPT_GENERATING", "PROMPT_READY",
    "VALIDATING", "READY_TO_COMMIT", "CANVAS_COMMITTED",
    "GENERATING", "GENERATED", "FAILED",
]
VIDEO_STATES = [
    "SHOT_READY", "CHECKING_REFERENCES", "REFERENCES_READY",
    "VIDEO_PROMPT_GENERATING", "VIDEO_PROMPT_READY", "VIDEO_NODE_COMMITTED",
    "VIDEO_GENERATING", "VIDEO_GENERATED",
]

# 允许成为 Canvas 节点的资产类型（白名单，#41 INVALID_ASSET_TYPE）
ALLOWED_ASSET_TYPES = {
    "character", "location", "prop", "scene",
    "smart-prompt", "smart-image", "smart-video",
}
# 生成类（prompt 即文生图/文生视频提示词）
GENERATION_TYPES = {"smart-image", "smart-video", "image", "video", "generation"}

# 占位/未就绪提示词信号：出现任一即视为"还没拿到真提示词"，禁止建生成节点
PLACEHOLDER_PROMPT_MARKERS = (
    "待生成", "待定", "待写", "待补充", "待完善", "待产出", "占位", "占位符",
    "稍后", "稍后补充", "暂无", "提示词占位", "生成提示词", "提示词待定",
    "to be decided", "tbd", "todo", "placeholder", "待填",
)


def _is_placeholder_prompt(prompt):
    """确定性判断：这条 prompt 是否还是占位/未就绪（拿到真提示词了吗）。"""
    s = str(prompt or "").strip()
    if not s:
        return True
    low = s.lower()
    for m in PLACEHOLDER_PROMPT_MARKERS:
        if m in low:
            return True
    return False
# 禁止在“资产发现/提示词生成中”阶段提交节点（#2/#3 阶段守卫）
NON_COMMITTABLE_PHASES = {
    "ASSET_DISCOVERY", "ASSET_EXTRACTION", "DISCOVERED",
    "PROMPT_GENERATING", "SELECTED",
}

# ---- 进程内 Ledger（开发模式 Mutation Timeline 数据源，#39/#40）----
_LEDGER = []


def reset_ledger():
    """测试隔离用：清空 Ledger。"""
    _LEDGER.clear()


def get_ledger():
    return list(_LEDGER)


def _next_id(prefix):
    return "{}_{}".format(prefix, uuid.uuid4().hex[:12])


def _now():
    return time.time()


def record_mutation(mutation_id, task_id, phase, source_event, event_type,
                    artifact_id, node_id, asset_type, prompt_status,
                    validation_result, block_reason="", reason=""):
    """写入一条 Ledger 记录（任何 Canvas Mutation 都必须能在 Timeline 追踪来源，#39）。"""
    rec = {
        "mutation_id": mutation_id,
        "task_id": task_id or "",
        "phase": (phase or "").upper(),
        "source_event": source_event or "",
        "event_type": event_type,           # CREATE_NODE / CREATE_NODE_BLOCKED / CREATE_EDGE / CREATE_EDGE_SKIP
        "artifact_id": artifact_id or "",
        "node_id": node_id or "",
        "asset_type": asset_type or "",
        "prompt_status": prompt_status or "",
        "validation_result": validation_result,   # PASS / REJECT / PASS_DUPLICATE / SKIP_DUP
        "block_reason": block_reason or "",
        "reason": reason or "",
        "ts": _now(),
    }
    _LEDGER.append(rec)
    return rec


# ---- 校验（#41 最底层硬守卫）----
def validate_asset_node(asset, *, phase="", allow_optional=False):
    """返回 (ok, block_reason, details)。asset 为归一化资产 dict。

    归一化字段：
      assetId / artifactId : 稳定资产 ID（必填）
      assetType / type     : 资产类型（白名单）
      prompt / promptDraftText / text : 文生图/文生视频/文本提示词（必非空）
      promptStatus         : PROMPT_READY 才允许提交（缺省按有无 prompt 推断）
      importance           : critical/important/optional（optional 默认不进 Canvas，由调用方决定）
    """
    if not isinstance(asset, dict):
        return False, "NOT_DICT", {}
    aid = str(asset.get("assetId") or asset.get("artifactId") or "").strip()
    if not aid:
        return False, "MISSING_ASSET_ID", {}
    atype = str(asset.get("assetType") or asset.get("type") or "").strip().lower()
    if atype and atype not in ALLOWED_ASSET_TYPES:
        return False, "INVALID_ASSET_TYPE", {"assetType": atype}
    prompt = str(asset.get("prompt") or asset.get("promptDraftText")
                 or asset.get("text") or asset.get("content") or "").strip()
    if not prompt:
        return False, "EMPTY_PROMPT", {}
    # 生成节点：占位/未就绪提示词一律拒绝（拿到真提示词前禁止建节点）
    if atype in GENERATION_TYPES and _is_placeholder_prompt(prompt):
        return False, "PLACEHOLDER_PROMPT", {"prompt": prompt[:40]}
    imp = str(asset.get("importance") or "").strip().lower()
    if imp == "optional" and not allow_optional:
        return False, "OPTIONAL_NOT_COMMITTED", {"importance": imp}
    ps = str(asset.get("promptStatus") or "").strip().upper()
    if not ps:
        # 缺省：有非空 prompt 即视为 PROMPT_READY（向后兼容现有文本/生成节点）
        ps = "PROMPT_READY"
    if ps != "PROMPT_READY":
        return False, "PROMPT_NOT_READY", {"promptStatus": ps}
    pu = (phase or "").upper()
    if pu and pu in NON_COMMITTABLE_PHASES:
        return False, "PHASE_NOT_COMMITTABLE", {"phase": pu}
    return True, "", {"promptStatus": ps, "assetType": atype or "unknown"}


def validate_video_node(asset, *, required_asset_ids=None, ready_asset_ids=None):
    """视频节点提交前校验（#5/#7）：所有 REQUIRED 资产必须 Ready。"""
    if not isinstance(asset, dict):
        return False, "NOT_DICT", {}
    vid = str(asset.get("assetId") or asset.get("artifactId") or asset.get("shotId") or "").strip()
    if not vid:
        return False, "MISSING_VIDEO_ID", {}
    prompt = str(asset.get("prompt") or asset.get("promptDraftText") or "").strip()
    if not prompt:
        return False, "EMPTY_PROMPT", {}
    ps = str(asset.get("promptStatus") or "").strip().upper() or "PROMPT_READY"
    if ps != "PROMPT_READY":
        return False, "PROMPT_NOT_READY", {"promptStatus": ps}
    # 引用完整性（#5 缺资产 BLOCK）
    required = list(required_asset_ids or [])
    ready = set(ready_asset_ids or [])
    missing = [r for r in required if r not in ready]
    if missing:
        return False, "MISSING_REQUIRED_ASSET", {"missing": missing}
    return True, "", {"promptStatus": ps}


# ---- 受控提交入口 ----
def commit_asset_node(asset, canvas, *, task_id="", phase="", source_event="", allow_optional=False):
    """唯一受控资产节点创建入口（#10/#12）。

    - canvas: 当前画布 dict（函数内只增 nodes / 不负责落盘，落盘由调用方负责）
    - 返回 dict: {ok, rejected, node_id, deduped, reason, block_reason}
    - 任何结果都写 Ledger。
    """
    ok, reason, details = validate_asset_node(asset, phase=phase, allow_optional=allow_optional)
    aid = str(asset.get("assetId") or asset.get("artifactId") or "").strip()
    atype = str(asset.get("assetType") or asset.get("type") or "").strip().lower()
    mutation_id = _next_id("mutation")
    if not ok:
        record_mutation(mutation_id, task_id, phase, source_event, "CREATE_NODE_BLOCKED",
                        aid, "", atype, details.get("promptStatus", ""), "REJECT",
                        block_reason=reason, reason=reason)
        return {"ok": False, "rejected": True, "node_id": None,
                "deduped": False, "reason": reason, "block_reason": reason}
    nodes = canvas.setdefault("nodes", [])
    # INVARIANT 4：同 assetId 最多一个有效节点 → 更新既存，不新建（#9 去重）
    existing = next((n for n in nodes if isinstance(n, dict)
                     and str(n.get("artifactId") or n.get("assetId") or "") == aid), None)
    if existing is not None:
        existing.update({k: v for k, v in asset.items() if k not in ("id",)})
        existing["artifactId"] = aid
        existing["__origin"] = "mutation_manager"
        record_mutation(mutation_id, task_id, phase, source_event, "CREATE_NODE",
                        aid, existing.get("id"), atype, "PROMPT_READY",
                        "PASS_DUPLICATE", reason="duplicate_update")
        return {"ok": True, "rejected": False, "node_id": existing.get("id"),
                "deduped": True, "reason": "duplicate_update"}
    node = dict(asset)
    node["id"] = node.get("id") or _next_id("agent")
    node["artifactId"] = aid
    node["__origin"] = "mutation_manager"
    if "status" not in node:
        node["status"] = "ready"
    nodes.append(node)
    record_mutation(mutation_id, task_id, phase, source_event, "CREATE_NODE",
                    aid, node["id"], atype, "PROMPT_READY", "PASS",
                    reason="committed")
    return {"ok": True, "rejected": False, "node_id": node["id"],
            "deduped": False, "reason": "committed"}


def commit_video_node(asset, canvas, *, task_id="", phase="", source_event="",
                      required_asset_ids=None, ready_asset_ids=None):
    """视频节点提交入口（#8/#21）。引用完整性校验 + 按 ID 连线。"""
    ok, reason, details = validate_video_node(
        asset, required_asset_ids=required_asset_ids, ready_asset_ids=ready_asset_ids)
    vid = str(asset.get("assetId") or asset.get("artifactId") or asset.get("shotId") or "").strip()
    atype = "smart-video"
    mutation_id = _next_id("mutation")
    if not ok:
        record_mutation(mutation_id, task_id, phase, source_event, "CREATE_NODE_BLOCKED",
                        vid, "", atype, details.get("promptStatus", ""), "REJECT",
                        block_reason=reason, reason=reason)
        return {"ok": False, "rejected": True, "node_id": None,
                "deduped": False, "reason": reason, "block_reason": reason}
    nodes = canvas.setdefault("nodes", [])
    existing = next((n for n in nodes if isinstance(n, dict)
                     and str(n.get("artifactId") or n.get("assetId") or n.get("shotId") or "") == vid), None)
    if existing is not None:
        record_mutation(mutation_id, task_id, phase, source_event, "CREATE_NODE",
                        vid, existing.get("id"), atype, "PROMPT_READY",
                        "PASS_DUPLICATE", reason="duplicate_update")
        return {"ok": True, "rejected": False, "node_id": existing.get("id"),
                "deduped": True, "reason": "duplicate_update"}
    node = dict(asset)
    node["id"] = node.get("id") or vid           # 稳定 id = video_shot_xxx
    node["artifactId"] = vid
    node["type"] = "smart-video"
    node["__origin"] = "mutation_manager"
    node["status"] = "ready"
    nodes.append(node)
    # 按 Stable ID 连线（#8/#9）：只连 shot 显式引用的资产（三类引用全部拼接，禁止 or 短路）
    ref_ids = (list(asset.get("characterRefs") or [])
               + list(asset.get("locationRefs") or [])
               + list(asset.get("propRefs") or []))
    ref_ids = [str(r) for r in ref_ids if r]
    edges_created = []
    for rid in dict.fromkeys(ref_ids):
        ec = create_edge(canvas, rid, node["id"], kind="input")
        if ec.get("created"):
            edges_created.append({"from": rid, "to": node["id"]})
    record_mutation(mutation_id, task_id, phase, source_event, "CREATE_NODE",
                    vid, node["id"], atype, "PROMPT_READY", "PASS",
                    reason="video_committed edges={}".format(len(edges_created)))
    return {"ok": True, "rejected": False, "node_id": node["id"],
            "deduped": False, "edges": edges_created, "reason": "video_committed"}


def create_edge(canvas, source_id, target_id, *, kind="input"):
    """确定性 Edge 创建（#8）。只按 Stable ID，禁止名称匹配。返回 {ok, created, reason}。"""
    source_id, target_id = str(source_id or "").strip(), str(target_id or "").strip()
    if not source_id or not target_id or source_id == target_id:
        return {"ok": False, "created": False, "reason": "INVALID_EDGE_IDS"}
    conns = canvas.setdefault("connections", [])
    if any(c.get("from") == source_id and c.get("to") == target_id and c.get("kind") == kind
           for c in conns):
        record_mutation(_next_id("mutation"), "", "", "", "CREATE_EDGE_SKIP",
                        source_id, target_id, "", "", "SKIP_DUP",
                        reason="edge_exists")
        return {"ok": True, "created": False, "reason": "exists"}
    conns.append({"from": source_id, "to": target_id, "kind": kind})
    record_mutation(_next_id("mutation"), "", "", "", "CREATE_EDGE",
                    source_id, target_id, "", "", "PASS", reason="edge_created")
    return {"ok": True, "created": True, "reason": "created"}


class InvalidCanvasMutationError(Exception):
    """运行时强制异常（#28）：非法创建不被静默放过。"""
    pass
