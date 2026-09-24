# -*- coding: utf-8 -*-
"""MyridTV Agent 停止请求与流程纪律拦截（后端拆分第16刀）：stop 请求登记/
查询（STOP_REQUESTS/STOP_LOCK 单例归本模块，主 submit_codex_chat 的 discard
处走薄别名同对象）、premature 建节点检测（回执授权放行/既有建节点放行/
产出诉求拦截）与纠错提示词。

逐字迁移自 rh_official_proxy.py 连续块（2 顶层 + 4 函数 63 行，可逆还原行级
diff=0）。行为零变更。configure() 同对象引用注入 CANVAS_AGENT_RECEIPTS/
CANVAS_AGENT_RECEIPTS_LOCK（定义留主文件 submit_receipt 域，零重绑纯内容写，
跨模块读写互见——第5刀 task_state 同款零改写处方）。
"""
import threading

CANVAS_AGENT_STOP_REQUESTS = set()
CANVAS_AGENT_STOP_LOCK = threading.Lock()
CANVAS_AGENT_RECEIPTS = None
CANVAS_AGENT_RECEIPTS_LOCK = None


def configure(receipts, receipts_lock):
    global CANVAS_AGENT_RECEIPTS, CANVAS_AGENT_RECEIPTS_LOCK
    CANVAS_AGENT_RECEIPTS = receipts
    CANVAS_AGENT_RECEIPTS_LOCK = receipts_lock


CANVAS_AGENT_STOP_REQUESTS = set()
CANVAS_AGENT_STOP_LOCK = threading.Lock()


def request_canvas_agent_stop(request_id):
    request_id = str(request_id or "").strip()
    if not request_id:
        return False
    with CANVAS_AGENT_STOP_LOCK:
        CANVAS_AGENT_STOP_REQUESTS.add(request_id)
    return True


def _canvas_agent_stop_requested(request_id):
    if not request_id:
        return False
    with CANVAS_AGENT_STOP_LOCK:
        return request_id in CANVAS_AGENT_STOP_REQUESTS


def _agent_detect_premature_creation(tool_calls, messages, tool_log):
    """流程纪律拦截（harness 层确定性检测）：本轮大模型调用了「创建类」工具
    （canvas_create_text_node / canvas_create_generation_node / canvas_batch_operations / canvas_generate_images），
    但流程还没到落地环节——用户当前诉求仍是"提取/整理/输出内容"（清单、分析、方案、提示词文本），
    且此前没有交互卡片回执确认过落地。返回违规类型字符串；无违规返回空串。"""
    names = [str((tc.get("function") or {}).get("name") or "") for tc in (tool_calls or []) if isinstance(tc, dict)]
    creating = [n for n in names if n in {
        "canvas_create_text_node", "canvas_create_generation_node",
        "canvas_batch_operations", "canvas_generate_images",
    }]
    if not creating:
        return ""
    # 1) 会话里有过交互回执（用户在卡片上点选/确认过）→ 视为已授权落地，放行
    with CANVAS_AGENT_RECEIPTS_LOCK:
        if any(bool(r.get("resolved")) for r in CANVAS_AGENT_RECEIPTS.values()):
            return ""
    # 2) 本轮之前已经有真实建节点的工具调用（同一请求的多轮里先出卡再建）→ 放行
    if any(str(e.get("name") or "") in {"canvas_create_text_node", "canvas_create_generation_node", "canvas_batch_operations"} for e in (tool_log or [])):
        return ""
    # 3) 用户最新诉求是"要内容/要清单/要分析/要方案"，明显还在产出阶段 → 拦截
    latest_user = ""
    for m in reversed(messages or []):
        if isinstance(m, dict) and str(m.get("role") or "") == "user":
            latest_user = str(m.get("content") or "")
            break
    extract_signals = (
        "提取", "整理", "总结", "分析", "清单", "列出来", "梳理", "总结出", "归纳",
        "资产清单", "素材清单", "有哪些", "盘点", "给我看", "输出", "写出来", "列一下",
    )
    if latest_user and any(sig in latest_user for sig in extract_signals):
        return "premature_creation"
    return ""


def _agent_premature_creation_correction():
    return (
        "【纠正·流程纪律】流程还没到落地环节，禁止现在创建画布节点。"
        "用户当前要的是内容产出（提取/清单/分析/方案/提示词文本），不是画布操作。"
        "这轮请直接在回复正文里输出完整内容（清单、分析、提示词等），不要调用任何 canvas_create_* 工具；"
        "只有当用户明确说「创建节点/建到画布/落地」或先通过交互卡片确认后，才允许调用创建类工具。"
    )


