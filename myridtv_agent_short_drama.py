# -*- coding: utf-8 -*-
"""MyridTV Agent 短剧模式域（后端拆分第13刀C-X4）：短剧请求识别、上下文提取、
回执字段解析、模式/参数/剧本参数卡构建、看板（board）结果与执行缓存。

逐字迁移自 rh_official_proxy.py 连续块 L(_agent_short_drama_mode_card_result)..
L(submit_codex_chat)（12 函数 418 行，可逆还原行级 diff=0）。行为零变更。
_Agent_SHORT_DRAMA_BOARD_EXECUTED 单例随块入本模块（全部读写在块内）。
configure() 注入 LOG_FILE getter。依赖属性链直引 myridtv_agent_batch /
myridtv_agent_tools / myridtv_agent_guard（运行期解析，monkeypatch 穿透）。
CANVAS_AGENT_ALLOW_TEXT_FALLBACK_NODES 块外仍有引用，主文件留薄别名。
"""
import json
import re
import time

from myridtv_core import append_log

import myridtv_agent_batch
import myridtv_agent_tools
import myridtv_agent_guard

CANVAS_AGENT_ALLOW_TEXT_FALLBACK_NODES = False
_agent_SHORT_DRAMA_BOARD_EXECUTED = {}
_log_file = lambda: None


def configure(log_file_getter):
    global _log_file
    _log_file = log_file_getter


def _agent_short_drama_mode_card_result(payload):
    """入口首轮兜底：短剧请求先展示制作模式卡，避免直接进入长文本流程。"""
    payload = payload if isinstance(payload, dict) else {}
    message = str(payload.get("message") or "").strip()
    if not message:
        return None
    latest_user = ""
    for item in reversed((payload.get("messages") or payload.get("history") or [])):
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "") != "user":
            continue
        latest_user = str(item.get("content") or item.get("text") or "").strip()
        if latest_user:
            break
    # 前端的 message 里会拼接历史和"用户当前请求"。兜底只应该拦截入口首轮，
    # 用户点击模式卡后的回执如"我选择：A"必须放行给主链继续。
    gate_text = latest_user or message
    if latest_user and latest_user != message:
        message = latest_user
    compact = re.sub(r"\s+", "", message)
    is_shortcut_request = "请先按短剧制作板流程给我选择模式卡" in message or "不要直接生成分镜" in message
    if not _agent_is_short_drama_request(compact):
        return None
    explicit_markers = ("快速出片", "专业制作", "已有剧本", "我选择", "已确认", "标准分镜", "Shot", "Clip")
    if not is_shortcut_request and any(marker in gate_text for marker in explicit_markers):
        return None
    session_id = str(payload.get("agent_session_id") or payload.get("session_id") or "").strip()
    if session_id:
        myridtv_agent_tools.CANVAS_AGENT_CURRENT_SESSION["session_id"] = session_id
    card_args = {
        "intent": "choose",
        "title": "选择短剧模式",
        "options": [
            {
                "id": "A",
                "label": "快速出片",
                "desc": "少确认，直接生成短剧制作板和可执行节点。",
                "default": True,
                "action": "short_drama_fast",
            },
            {
                "id": "B",
                "label": "专业制作",
                "desc": "保留内容确认和生成确认，适合认真控剧本、素材和镜头。",
                "action": "short_drama_pro",
            },
            {
                "id": "C",
                "label": "已有剧本",
                "desc": "跳过创意发散，直接解析剧本并拆分镜、Clip、素材和视频节点。",
                "action": "short_drama_script",
            },
        ],
        "default_id": "A",
    }
    result = myridtv_agent_tools._agent_tool_present_interaction(card_args, session_id=session_id)
    return myridtv_agent_guard._build_canvas_agent_result(
        "先选一个制作模式，我会按这个模式搭短剧制作板。",
        tool_log=[{"name": "present_im_interaction", "args": card_args, "result": result}],
        raw={"short_drama_mode_card": True},
    )


def _agent_latest_user_text(payload):
    payload = payload if isinstance(payload, dict) else {}
    for item in reversed((payload.get("messages") or payload.get("history") or [])):
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "") != "user":
            continue
        text = str(item.get("content") or item.get("text") or "").strip()
        if text:
            return text
    return str(payload.get("message") or "").strip()


def _agent_short_drama_context_text(payload):
    payload = payload if isinstance(payload, dict) else {}
    parts = [str(payload.get("message") or "")]
    for item in (payload.get("messages") or payload.get("history") or []):
        if isinstance(item, dict):
            parts.append(str(item.get("content") or item.get("text") or ""))
    return "\n".join(parts)


def _agent_is_short_drama_request(text):
    compact = re.sub(r"\s+", "", str(text or ""))
    if any(marker in compact for marker in ("创作短剧", "剧情短片", "短剧制作板")):
        return True
    if "短剧" not in compact and "微剧" not in compact:
        return False
    return any(marker in compact for marker in ("成片", "视频", "拍", "剧本", "分镜", "剧情", "镜头", "画布", "制作"))


def _agent_short_drama_parse_receipt_fields(text):
    fields = {}
    for key, value in re.findall(r"([A-Za-z0-9_\-\u4e00-\u9fff]+)\s*=\s*([^，,\n]+)", str(text or "")):
        fields[str(key).strip()] = str(value).strip()
    return fields


def _agent_short_drama_param_card_result(payload):
    """模式选择后的确定性参数卡，避免快速出片入口被上游长请求拖住。"""
    payload = payload if isinstance(payload, dict) else {}
    latest = _agent_latest_user_text(payload)
    context = _agent_short_drama_context_text(payload)
    if not _agent_is_short_drama_request(context):
        return None
    if not (re.search(r"我选择\s*[:： ]", latest) and ("A" in latest or "快速出片" in latest)):
        return None
    session_id = str(payload.get("agent_session_id") or payload.get("session_id") or "").strip()
    if session_id:
        myridtv_agent_tools.CANVAS_AGENT_CURRENT_SESSION["session_id"] = session_id
    card_args = {
        "intent": "collect",
        "title": "确认快速出片参数",
        "fields": [
            {"key": "idea", "label": "故事一句话", "type": "text", "default": "都市反转短剧：一次意外消息引发误会，主角在三段关键选择里完成反转。"},
            {"key": "duration", "label": "总时长", "type": "select", "default": "30秒", "options": [
                {"value": "15秒", "label": "15秒"}, {"value": "30秒", "label": "30秒"}, {"value": "60秒", "label": "60秒"}
            ]},
            {"key": "clip_count", "label": "镜头数", "type": "select", "default": "3", "options": [
                {"value": "3", "label": "3镜头"}, {"value": "5", "label": "5镜头"}, {"value": "8", "label": "8镜头"}
            ]},
            {"key": "aspect_ratio", "label": "画幅", "type": "select", "default": "9:16", "options": [
                {"value": "9:16", "label": "竖屏 9:16"}, {"value": "16:9", "label": "横屏 16:9"}, {"value": "1:1", "label": "方图 1:1"}
            ]},
            {"key": "style", "label": "视觉风格", "type": "text", "default": "写实短剧，电影感灯光，强情绪表演"},
        ],
    }
    result = myridtv_agent_tools._agent_tool_present_interaction(card_args, session_id=session_id)
    return myridtv_agent_guard._build_canvas_agent_result(
        "已进入快速出片。先确认这组参数，提交后我会在画布生成短剧制作板和可执行节点。",
        tool_log=[{"name": "present_im_interaction", "args": card_args, "result": result}],
        raw={"short_drama_param_card": True},
    )


def _agent_short_drama_script_param_card_result(payload):
    """已有剧本模式：收剧本和少量生成参数。"""
    payload = payload if isinstance(payload, dict) else {}
    latest = _agent_latest_user_text(payload)
    context = _agent_short_drama_context_text(payload)
    if not _agent_is_short_drama_request(context):
        return None
    if not (re.search(r"我选择\s*[:： ]", latest) and ("C" in latest or "已有剧本" in latest)):
        return None
    session_id = str(payload.get("agent_session_id") or payload.get("session_id") or "").strip()
    if session_id:
        myridtv_agent_tools.CANVAS_AGENT_CURRENT_SESSION["session_id"] = session_id
    card_args = {
        "intent": "collect",
        "title": "导入完整剧本",
        "fields": [
            {"key": "script", "label": "完整剧本", "type": "text", "default": "第一场：地铁车厢内。女孩捡到一部旧手机，屏幕弹出一条明天的求救视频。她抬头，发现视频里的男人正坐在对面。"},
            {"key": "duration", "label": "总时长", "type": "select", "default": "60秒", "options": [
                {"value": "30秒", "label": "30秒"}, {"value": "60秒", "label": "60秒"}, {"value": "90秒", "label": "90秒"}
            ]},
            {"key": "clip_count", "label": "拆分镜头", "type": "select", "default": "5", "options": [
                {"value": "3", "label": "3镜头"}, {"value": "5", "label": "5镜头"}, {"value": "8", "label": "8镜头"}
            ]},
            {"key": "aspect_ratio", "label": "画幅", "type": "select", "default": "9:16", "options": [
                {"value": "9:16", "label": "竖屏 9:16"}, {"value": "16:9", "label": "横屏 16:9"}, {"value": "1:1", "label": "方图 1:1"}
            ]},
        ],
    }
    result = myridtv_agent_tools._agent_tool_present_interaction(card_args, session_id=session_id)
    return myridtv_agent_guard._build_canvas_agent_result(
        "已进入已有剧本模式。把完整剧本和基础参数确认一下，我会把后续角色、场景、Clip 和视频节点补到画布。",
        tool_log=[{"name": "present_im_interaction", "args": card_args, "result": result}],
        raw={"short_drama_script_param_card": True},
    )


def _agent_short_drama_field_value(text, key, next_keys):
    source = str(text or "")
    start = source.find(str(key) + "=")
    if start < 0:
        return ""
    start += len(str(key)) + 1
    end = len(source)
    for marker in next_keys:
        idx = source.find("，{}=".format(marker), start)
        if idx >= 0:
            end = min(end, idx)
    return source[start:end].strip(" ，,\n\r\t")


# Phase 1 (P2): 短剧制作板幂等缓存。
# 旧逻辑每次命中 marker 文本都会批量重建 6+N 个节点，重试 / 重发同一消息会重复落库。
# 按 session + 关键参数指纹缓存成功结果，命中直接返回，不重复建节点。
# 区分 "board"（仅准备）与 "board_exec"（用户明确执行后落地）。
_AGENT_SHORT_DRAMA_BOARD_EXECUTED = {}

def _agent_short_drama_board_key(payload, mode):
    session_id = str(payload.get("agent_session_id") or payload.get("session_id")
                     or myridtv_agent_tools.CANVAS_AGENT_CURRENT_SESSION.get("session_id") or "").strip()
    latest = _agent_latest_user_text(payload)
    fields = _agent_short_drama_parse_receipt_fields(latest)
    idea = fields.get("idea") or fields.get("故事一句话") or ""
    duration = fields.get("duration") or fields.get("总时长") or ""
    clip = fields.get("clip_count") or fields.get("镜头数") or ""
    aspect = fields.get("aspect_ratio") or fields.get("画幅") or ""
    script = (fields.get("script") or fields.get("完整剧本") or "")[:200]
    return "{}|{}|{}|{}|{}|{}|{}".format(mode, session_id, idea, duration, clip, aspect, script)


def _agent_user_intends_execute(payload):
    """本轮用户消息是否明确指示执行/落地制作板（而非仅确认参数）。"""
    latest = _agent_latest_user_text(payload)
    if not latest:
        return False
    execute_markers = ("执行制作板", "执行剧本制作板", "落画布", "确认执行", "开始生成", "执行计划")
    return any(marker in latest for marker in execute_markers)


def _agent_short_drama_script_board_result(payload):
    """完整剧本提交后的后续制作板。"""
    payload = payload if isinstance(payload, dict) else {}
    latest = _agent_latest_user_text(payload)
    context = _agent_short_drama_context_text(payload)
    if not _agent_is_short_drama_request(context):
        return None
    # 支持 "完整剧本="（进入准备态）或 "执行剧本制作板"（进入落地态）
    if not any(marker in latest for marker in ("script=", "完整剧本=", "执行剧本制作板", "执行制作板", "落画布", "确认执行", "开始生成", "执行计划")):
        return None
    fields = _agent_short_drama_parse_receipt_fields(latest)
    script = _agent_short_drama_field_value(latest, "script", ("duration", "clip_count", "aspect_ratio")) or _agent_short_drama_field_value(latest, "完整剧本", ("总时长", "拆分镜头", "画幅"))
    duration = fields.get("duration") or fields.get("总时长") or "60秒"
    clip_count_text = fields.get("clip_count") or fields.get("拆分镜头") or "5"
    aspect = fields.get("aspect_ratio") or fields.get("画幅") or "9:16"
    try:
        clip_count = max(1, min(8, int(float(re.findall(r"\d+", str(clip_count_text))[0]))))
    except Exception:
        clip_count = 5
    if not script:
        script = "第一场：地铁车厢内。女孩捡到一部旧手机，屏幕弹出一条明天的求救视频。她抬头，发现视频里的男人正坐在对面。"
    brief = (
        "模式：已有剧本\n"
        "总时长：{duration}\n"
        "拆分镜头：{clip_count}\n"
        "画幅：{aspect}\n\n"
        "后续链路：解析剧本 -> 角色/场景基准 -> Clip 视频节点 -> 执行 -> 选结果/重拍/合成。"
    ).format(duration=duration, clip_count=clip_count, aspect=aspect)
    script_node = "完整剧本\n{}".format(script)
    breakdown = (
        "剧本解析\n"
        "角色：从剧本中提取主要人物，优先稳定主角外貌和服装。\n"
        "场景：按场次提取地铁/室内/街边等空间，先生成基准图。\n"
        "节奏：前 3 秒强钩子，中段冲突升级，结尾保留反转或续集钩子。\n"
        "一致性：每个 Clip 视频节点引用角色和场景基准。"
    )
    clip_lines = []
    for index in range(1, clip_count + 1):
        if index == 1:
            beat = "剧本开场钩子"
        elif index == clip_count:
            beat = "结尾反转/钩子"
        else:
            beat = "按剧本顺序推进冲突"
        clip_lines.append("Clip {idx:02d}｜{beat}｜{duration} 内｜{aspect}".format(idx=index, beat=beat, duration=duration, aspect=aspect))
    ops = [
        {"op_type": "add_node", "params": {"node_type": "text", "title": "剧本制作板｜已有剧本", "text": brief, "x": 80, "y": 80}},
        {"op_type": "add_node", "params": {"node_type": "text", "title": "完整剧本", "text": script_node, "x": 440, "y": 80}},
        {"op_type": "add_node", "params": {"node_type": "text", "title": "剧本解析与一致性规则", "text": breakdown, "x": 800, "y": 80}},
        {"op_type": "add_node", "params": {"node_type": "text", "title": "剧本 Clip 表", "text": "Clip 表\n" + "\n".join(clip_lines), "x": 80, "y": 330}},
        {"op_type": "add_node", "params": {"node_type": "generation", "title": "剧本角色基准图", "prompt": "{script}。提取主角定妆照，短剧写实，{aspect}，服装清晰，面部稳定".format(script=script[:160], aspect=aspect), "x": 440, "y": 330}},
        {"op_type": "add_node", "params": {"node_type": "generation", "title": "剧本场景基准图", "prompt": "{script}。提取主要场景，短剧写实，{aspect}，可作为视频首帧参考".format(script=script[:160], aspect=aspect), "x": 800, "y": 330}},
    ]
    for index in range(1, clip_count + 1):
        ops.append({"op_type": "add_node", "params": {
            "node_type": "generation",
            "title": "剧本 Clip {idx:02d} 视频节点".format(idx=index),
            "prompt": "{script}。根据完整剧本生成 Clip {idx:02d}，短剧视频镜头，{aspect}，动作明确，情绪连贯，保持角色和场景一致。".format(script=script[:180], idx=index, aspect=aspect),
            "x": 80 + ((index - 1) % 4) * 360,
            "y": 820 + ((index - 1) // 4) * 470,
        }})
    # 仅提交剧本 ≠ 落地：先给预览，等用户明确说「执行剧本制作板」才真正建节点。
    if not _agent_user_intends_execute(payload):
        preview_lines = ["- {}".format(op.get("params", {}).get("title", op.get("op_type"))) for op in ops]
        preview = (
            "已准备好剧本制作板，共 {} 个节点：\n".format(len(ops))
            + "\n".join(preview_lines)
            + "\n\n请回复「执行剧本制作板」或「执行制作板」，我才会把它们落到画布；"
            + "点「取消本次操作」或说「算了」则不建任何节点。"
        )
        return myridtv_agent_guard._build_canvas_agent_result(
            preview,
            raw={"short_drama_script_board_ready": True, "node_count": len(ops), "operations": ops},
        )
    batch_args = {"operations": ops}
    key = _agent_short_drama_board_key(payload, "script_exec")
    cached = _AGENT_SHORT_DRAMA_BOARD_EXECUTED.get(key)
    if cached is not None:
        append_log(_log_file(), "short-drama script board idempotent skip key={}".format(key))
        return cached
    batch_result = myridtv_agent_batch._agent_tool_batch_operations(batch_args, payload.get("generation_preset") if isinstance(payload.get("generation_preset"), dict) else None)
    result = myridtv_agent_guard._build_canvas_agent_result(
        "已按完整剧本补齐后续制作板：剧本原文、解析规则、Clip 表、角色/场景基准图和剧本 Clip 视频节点。下一步执行基准图与 Clip 节点，按结果选择重拍或合成。",
        tool_log=[{"name": "canvas_batch_operations", "args": batch_args, "result": batch_result}],
        raw={"short_drama_script_board": True, "save_ok": bool(batch_result.get("save_ok")) if isinstance(batch_result, dict) else False},
    )
    if isinstance(batch_result, dict) and bool(batch_result.get("save_ok")):
        _AGENT_SHORT_DRAMA_BOARD_EXECUTED[key] = result
    return result


def _agent_short_drama_board_result(payload):
    """参数提交后的确定性制作板落画布。"""
    payload = payload if isinstance(payload, dict) else {}
    latest = _agent_latest_user_text(payload)
    context = _agent_short_drama_context_text(payload)
    if not (_agent_is_short_drama_request(context) or "快速出片" in context):
        return None
    # 支持 "参数已确认"（进入准备态）或 "执行制作板"（进入落地态）
    if not any(marker in latest for marker in ("参数已确认", "我填写", "故事一句话=", "idea=", "执行制作板", "落画布", "确认执行", "开始生成", "执行计划")):
        return None
    fields = _agent_short_drama_parse_receipt_fields(latest)
    idea = fields.get("idea") or fields.get("故事一句话") or "都市反转短剧：一次意外消息引发误会，主角在三段关键选择里完成反转。"
    duration = fields.get("duration") or fields.get("总时长") or "30秒"
    clip_count_text = fields.get("clip_count") or fields.get("镜头数") or "3"
    aspect = fields.get("aspect_ratio") or fields.get("画幅") or "9:16"
    style = fields.get("style") or fields.get("视觉风格") or "写实短剧，电影感灯光，强情绪表演"
    try:
        clip_count = max(1, min(8, int(float(re.findall(r"\d+", str(clip_count_text))[0]))))
    except Exception:
        clip_count = 3
    brief = (
        "模式：快速出片\n"
        "故事一句话：{idea}\n"
        "总时长：{duration}\n"
        "镜头数：{clip_count}\n"
        "画幅：{aspect}\n"
        "视觉风格：{style}\n\n"
        "用户链路：1 选模式 -> 2 确认参数 -> 3 生成制作板 -> 4 执行节点 -> 5 选结果/重拍/合成。"
    ).format(idea=idea, duration=duration, clip_count=clip_count, aspect=aspect, style=style)
    synopsis = (
        "剧情梗概\n"
        "开场：主角收到一个会改变关系的消息，误会快速升级。\n"
        "发展：主角做出看似错误的选择，暴露人物处境和情绪压力。\n"
        "反转：最后一个细节证明主角早有判断，误会变成主动布局。\n"
        "结尾钩子：留一个未解释的来电/门铃/监控画面，方便续集。"
    )
    clip_lines = []
    for index in range(1, clip_count + 1):
        if index == 1:
            beat = "钩子开场：消息/门铃/监控画面引爆冲突"
        elif index == clip_count:
            beat = "反转收束：主角揭示真实目的，留下续集钩子"
        else:
            beat = "冲突升级：误会加深，人物关系出现选择压力"
        clip_lines.append("Clip {idx:02d}｜{beat}｜约 {sec}｜{aspect}｜{style}".format(
            idx=index, beat=beat, sec=duration, aspect=aspect, style=style
        ))
    clip_table = "Clip 表\n" + "\n".join(clip_lines)
    material = (
        "素材清单\n"
        "1. 角色基准图：主角半身、表情强、服装统一。\n"
        "2. 场景基准图：室内/街边/门口，保留短剧真实感。\n"
        "3. 每个 Clip 视频节点：按 Clip 表逐条执行，生成后选择最佳结果。\n"
        "4. 重拍规则：人脸漂移、动作不连贯、情绪不到位时回到对应节点重拍。"
    )
    ops = [
        {"op_type": "add_node", "params": {"node_type": "text", "title": "短剧制作板｜快速出片", "text": brief, "x": 80, "y": 80}},
        {"op_type": "add_node", "params": {"node_type": "text", "title": "剧情梗概", "text": synopsis, "x": 440, "y": 80}},
        {"op_type": "add_node", "params": {"node_type": "text", "title": "素材清单与重拍规则", "text": material, "x": 800, "y": 80}},
        {"op_type": "add_node", "params": {"node_type": "text", "title": "Clip 表", "text": clip_table, "x": 80, "y": 330}},
        {"op_type": "add_node", "params": {"node_type": "generation", "title": "角色基准图", "prompt": "{idea}。主角角色设定，{style}，{aspect}，清晰面部，短剧人物定妆照".format(idea=idea, style=style, aspect=aspect), "x": 440, "y": 330}},
        {"op_type": "add_node", "params": {"node_type": "generation", "title": "场景基准图", "prompt": "{idea}。核心场景空间，{style}，{aspect}，真实短剧布景，可作为视频首帧参考".format(idea=idea, style=style, aspect=aspect), "x": 800, "y": 330}},
    ]
    for index in range(1, clip_count + 1):
        ops.append({"op_type": "add_node", "params": {
            "node_type": "generation",
            "title": "Clip {idx:02d} 视频节点".format(idx=index),
            "prompt": "{idea}。Clip {idx:02d}，{style}，{aspect}，短剧镜头，人物动作明确，情绪强，适合视频生成。".format(idea=idea, idx=index, style=style, aspect=aspect),
            "x": 80 + ((index - 1) % 4) * 360,
            "y": 820 + ((index - 1) // 4) * 470,
        }})
    # 参数确认 ≠ 落地：先给预览，等用户明确说「执行制作板」才真正建节点，
    # 避免一次性倾倒占位/待生成节点到画布。
    if not _agent_user_intends_execute(payload):
        preview_lines = ["- {}".format(op.get("params", {}).get("title", op.get("op_type"))) for op in ops]
        preview = (
            "已准备好短剧制作板，共 {} 个节点：\n".format(len(ops))
            + "\n".join(preview_lines)
            + "\n\n请回复「执行制作板」，我才会把它们落到画布；"
            + "点「取消本次操作」或说「算了」则不建任何节点。"
        )
        return myridtv_agent_guard._build_canvas_agent_result(
            preview,
            raw={"short_drama_board_ready": True, "node_count": len(ops), "operations": ops},
        )
    batch_args = {"operations": ops}
    key = _agent_short_drama_board_key(payload, "board_exec")
    cached = _AGENT_SHORT_DRAMA_BOARD_EXECUTED.get(key)
    if cached is not None:
        append_log(_log_file(), "short-drama board idempotent skip key={}".format(key))
        return cached
    batch_result = myridtv_agent_batch._agent_tool_batch_operations(batch_args, payload.get("generation_preset") if isinstance(payload.get("generation_preset"), dict) else None)
    result = myridtv_agent_guard._build_canvas_agent_result(
        "已生成短剧制作板：Brief、剧情梗概、素材清单、Clip 表、角色/场景基准图和 Clip 视频节点。下一步直接在画布执行基准图与 Clip 节点，生成后选择结果、重拍或合成。",
        tool_log=[{"name": "canvas_batch_operations", "args": batch_args, "result": batch_result}],
        raw={"short_drama_board": True, "save_ok": bool(batch_result.get("save_ok")) if isinstance(batch_result, dict) else False},
    )
    if isinstance(batch_result, dict) and bool(batch_result.get("save_ok")):
        _AGENT_SHORT_DRAMA_BOARD_EXECUTED[key] = result
    return result


# Phase 1 (P1): 关闭"从自由文本启发式建画布节点"。
# 旧逻辑在 codex 返回非 JSON 时，会用正则从正文"抠"标题段落建立生成节点，
# 甚至调用 _codex_bridge_default_generation_nodes 凭空造"方案 A/B/C"三个空壳节点。
# 重构原则：LLM/工具结果不等于 Artifact，候选节点须经用户确认(Approval)后才落库。
# 默认 False = 禁止自动建节点，仅保留纯文本回复。如需回退旧行为改为 True。
CANVAS_AGENT_ALLOW_TEXT_FALLBACK_NODES = False


