# -*- coding: utf-8 -*-
"""MyridTV Agent 交互护栏（后端拆分第13刀C-X3c）：自动选卡、present_interaction
强制/违规检测、批操作违规检测与纠错提示词、三组交互标记常量。

逐字迁移自 rh_official_proxy.py 连续块 L(_agent_auto_choose_card_from_reply)..
L(_codex_bridge_extract_thread_id)（7 函数 + 3 常量 199 行，可逆还原行级 diff=0）。
行为零变更。configure() 注入两闭包：_agent_result_created_nodes /
_agent_take_pending_interaction（留主文件，def 在注入点之后）。
CANVAS_AGENT_CURRENT_SESSION 直引 myridtv_agent_tools、CANVAS_AGENT_LOADED_SKILLS
直引 myridtv_agent（单例同对象）。主文件对被仍引用的 5 函数留同名薄代理。
"""
import re
import time
import uuid

import myridtv_agent
import myridtv_agent_tools

_r_result_created_nodes = None
_r_take_pending_interaction = None


def configure(result_created_nodes, take_pending_interaction):
    global _r_result_created_nodes, _r_take_pending_interaction
    _r_result_created_nodes = result_created_nodes
    _r_take_pending_interaction = take_pending_interaction


def _agent_auto_choose_card_from_reply(text):
    """从回复文本里识别 A./B./C. 并列可选项，自动转成 choose 卡片。
    不依赖 LLM 主动调用 present_im_interaction，只要它产出并列候选就自动卡片化。
    返回 interaction 卡片 dict 或 None。"""
    raw = str(text or "")
    if not raw.strip():
        return None
    # 匹配 A.xxx / B.xxx / C.xxx（支持 A、B、C、D，1.2.3. 编号，A、B、C 顿号形式）
    lines = raw.splitlines()
    finds = []  # (letter_id, text)
    # 通用模式：字母 紧跟 标题（可含 ** 加粗、《》书名号），后接 ——/：/空格 描述
    item_re = re.compile(
        r"^(?:[-*•]\s*)?(?:[\*\*]?)\s*([A-Da-d])\s*[\*\*]?\s*[.、:：)）]?\s*"
        r"(?:\*?\*?《?([^——《】\n]{1,30})》?\*?\*?)?\s*"
        r"[———\-—:：\s]*(.*)$"
    )
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 剥掉行首符号：- · • * # 等
        line = re.sub(r"^[\s\-*•·]+", "", line)
        # 剥掉 \*\* 加粗标记，只留 A《标题》——描述
        line = re.sub(r"^\*\*", "", line)
        line = re.sub(r"\*\*", "", line)
        # 匹配 A《标题》——描述 / A 标题——描述 / A.标题 描述
        m = re.match(r"^([A-Da-d])\s*[.、:：)）]?\s*(《[^》]+》|[^——:：\s]{1,24})?\s*(?:——|—|－|:：|－|\s)([\s\S]*)$", line)
        if m:
            title = (m.group(2) or "方案" + m.group(1).upper()).strip().strip("《》")
            desc = (m.group(3) or "").strip()
            finds.append((m.group(1).upper(), title, desc))
            continue
        # 兜底：A 标题[——描述] 无空格分隔
        m = re.match(r"^([A-Da-d])\s*[\*\*]?\s*[.、:：)）]?\s*(《?[^——《】\n]{1,24}》?)(.*)$", line)
        if m:
            title = m.group(2).strip().strip("《》")
            desc = m.group(3).strip().lstrip("———－-:：")
            finds.append((m.group(1).upper(), title, desc))
    if len(finds) < 2:
        return None
    options = []
    for i, (oid, title, desc) in enumerate(finds):
        title = (title or "方案" + oid)[:24]
        desc = (desc or "").strip()
        if not desc:
            desc = title
        options.append({"id": oid, "label": title, "desc": desc[:80],
                        "default": i == 0, "action": "goto_phase3_" + oid})
    return {
        "card_id": "imc_auto_{}".format(uuid.uuid4().hex[:8]),
        "intent": "choose",
        "title": "请选择其中一个方向",
        "options": options,
        "fields": [],
        "default_id": options[0]["id"],
        "allow_custom": True,
        "asset_id": "",
        "created_at": int(time.time() * 1000),
        "resolved": False,
    }


# —— 交互合规检测（harness 层：确定性规则，不依赖模型自觉）——
# 违反信号（二元判断，机械强制）：该出卡没出卡 / 谎称发了卡
INTERACTION_FAKE_CARD_MARKERS = [
    "卡片已准备", "卡片已经", "卡片已", "请点击", "请点选", "见上方", "见下文",
    "纸牌已", "卡片就", "已铺好", "选一个", "请你选", "请选择", "点一下",
    # 谎称"正在发/要发"但实际没调工具（2026-09-03 短片流程：正文写"现在发确认卡片"却无 tool 调用）
    "发确认卡片", "发确认卡", "发卡片", "发一张卡片", "发了个卡", "发了个卡片",
    "发了卡片", "卡片如下", "卡片在下", "弹卡片", "弹出卡片", "卡片已发",
    "发起了确认", "发一张确认", "输出一张卡", "下面这张卡", "下方卡片",
]
# 列出编号选项却没出卡（正文 A/B/C 或 1/2/3 + 提问）
INTERACTION_OPTION_PATTERNS = re.compile(
    r"(\b[A-Da-d]\s*[.、:：)]|\b[1-4]\s*[.、:：)]|\b[一二三四]\s*[、.])\s*(?:[（(【])?[^，。\n]{1,30}"
    r"(?:【】|《》|[\u4e00-\u9fa5A-Za-z0-9]{1,12})"
)
INTERACTION_OPTION_PROMPT_MARKERS = ["哪个", "选", "请选择", "请选", "喜欢的", "心意", "中意", "哪一个"]


def _agent_has_present_interaction(tool_log):
    """本轮 tool_log 里是否真正调用了 present_im_interaction。"""
    for entry in tool_log or []:
        if str(entry.get("name") or "") == "present_im_interaction":
            return True
    return False


def _agent_detect_interaction_violation(text):
    """检测回复文本是否违规：谎称发了卡 / 列了编号选项让用户选却没出卡。
    返回违规类型字符串；无违规返回空串。"""
    raw = str(text or "")
    if not raw.strip():
        return ""
    # 1) 谎称发了卡：正文出现卡片元叙述 + 同轮没有任何 present_im_interaction 调用
    if any(marker in raw for marker in INTERACTION_FAKE_CARD_MARKERS):
        return "fake_card"
    # 2) 该出卡没出卡：列出 A/B/C 或 1/2/3 编号选项 + 提问"选哪个"，却没调用交互工具
    has_option = bool(INTERACTION_OPTION_PATTERNS.search(raw))
    has_prompt = any(m in raw for m in INTERACTION_OPTION_PROMPT_MARKERS)
    if has_option and has_prompt:
        return "listed_options_no_card"
    return ""


def _agent_interaction_correction_prompt(violation):
    """生成回灌给模型的纠正 prompt，让它用 present_im_interaction 出卡。"""
    if violation == "fake_card":
        return (
            "【纠正】你上一轮声称已展示卡片/请用户点选，但没有真正调用 present_im_interaction 工具，"
            "用户看不到任何可点击的卡片，这种描述是无效的。"
            "这轮必须调用 present_im_interaction（intent=choose）把选项做成结构化卡片，"
            "每个 option 写具体 title + 差异化 desc，default 预选一个。"
            "如果确实不该出卡，请直接说结论，不要用\"卡片已准备/请点击\"这类表述。"
        )
    return (
        "【纠正】你列出了 A/B/C 或编号选项让用户选，却没有调用 present_im_interaction 工具，"
        "用户无法点击选择，这种正文编号不算有效的交互。"
        "这轮必须调用 present_im_interaction（intent=choose）把选项做成结构化卡片，"
        "每个 option 写具体 title + 差异化 desc，default 预选一个。"
    )


# —— "一次性全建"未批量建的检测（用户选了一次性全建，但主链没用 canvas_batch_operations 一次建完）——
def _agent_detected_batch_violation(messages, tool_log):
    """检测：本轮 messages 里用户上一轮选了"一次性全建"，但 tool_log 只有逐个
    canvas_create_generation_node / canvas_create_text_node，没调 canvas_batch_operations。
    返回违规类型或空串。"""
    # 1) 判断用户是否上一轮选了"一次性全建"
    user_texts = [str(m.get("content") or m.get("text") or "") for m in (messages or []) if isinstance(m, dict) and str(m.get("role") or "") == "user"]
    chose_bulk = any(("一次性全建" in t or "一次性把所有素材" in t or "全建好" in t) for t in user_texts)
    if not chose_bulk:
        return ""
    # 2) 本轮是否真正调用了 canvas_batch_operations（一次建多个）
    names = [str(e.get("name") or "") for e in (tool_log or [])]
    if "canvas_batch_operations" in names:
        return ""
    # 3) 若只逐个建了少量节点（仍没批量），判定违规
    created_count = sum(1 for n in names if n in ("canvas_create_generation_node", "canvas_create_text_node"))
    if created_count > 0:
        return "bulk_not_batched"
    return ""


def _agent_batch_correction_prompt(violation):
    """生成批量建纠正 prompt。"""
    if violation == "bulk_not_batched":
        return (
            "【纠正】用户已经选择了「一次性把所有素材节点全建好」，你必须**调用一次 canvas_batch_operations**，"
            "在一条 operations 数组里 add_node 建完素材清单的全部节点（角色+场景+道具），一次性建完并连线。"
            "禁止逐个 canvas_create_generation_node、禁止再弹 confirm 卡逐个问、禁止再确认基准图。"
            "建完后才弹一次 confirm 请用户确认素材齐全。"
        )
    return ""


def _build_canvas_agent_result(text, tool_log=None, raw=None, output_mode="", extra=None, session_id=""):
    tool_log = tool_log if isinstance(tool_log, list) else []
    created_nodes = _r_result_created_nodes(tool_log)
    suggestions = []
    labels = "ABCDEFGH"
    for index, item in enumerate(created_nodes[:8]):
        title = str((item or {}).get("title") or "").strip()
        node_id = str((item or {}).get("node_id") or "").strip()
        if not node_id:
            continue
        suggestions.append({
            "key": labels[index],
            "label": title or "节点 {}".format(index + 1),
            "action": "locate_node",
            "node_id": node_id,
        })
    quick_actions = []
    if created_nodes:
        # 只保留"执行全部"，删除"定位全部"（用户要求）
        if any(item.get("type") == "smart-image" and item.get("status") in {"created", "running"} for item in created_nodes):
            quick_actions.append({"id": "run", "label": "执行全部"})
    extra = dict(extra) if isinstance(extra, dict) else {}
    # 只挂真实交互事件产生的卡片（present_im_interaction 登记的）。
    # 不做"从正文 A/B/C 提取成卡"——那是错误路径，会反向鼓励模型写文本而不是调工具。
    pending = _r_take_pending_interaction(session_id or myridtv_agent_tools.CANVAS_AGENT_CURRENT_SESSION.get("session_id") or "")
    if pending:
        extra["interaction"] = pending
    # 本轮加载的技能名，供前端在回复里展示"本次加载的技能"
    if myridtv_agent.CANVAS_AGENT_LOADED_SKILLS.get("skills"):
        extra["loaded_skills"] = list(myridtv_agent.CANVAS_AGENT_LOADED_SKILLS["skills"])
    return {
        "version": "deepseek-ui-v1",
        "text": str(text or "").strip(),
        "output_mode": str(output_mode or "").strip() or "text",
        "tool_log": tool_log,
        "created_nodes": created_nodes,
        "suggestions": suggestions,
        "quick_actions": quick_actions,
        "raw": raw if isinstance(raw, dict) else {},
        **(extra or {}),
    }


