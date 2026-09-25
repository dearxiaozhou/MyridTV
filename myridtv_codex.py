# -*- coding: utf-8 -*-
"""MyridTV Codex 桥纯函数族（后端拆分第13刀A）：附件/图片缓存读写、消息压缩与协议
指令、回复 JSON/工具调用/线程id/生成节点抽取、标题拆分与节点数推断、会话重置判定。

逐字迁移自 rh_official_proxy.py 连续块 L(_codex_bridge_file_suffix)..L(_agent_auto_
choose_card_from_reply)（18 函数 502 行，可逆还原行级 diff=0）。行为零变更。
_run_codex_bridge_exec/persistent 与 submit_codex_chat（编排层）留主文件，第14步收。
configure() 注入：ASSETS_DIR/CODEX_LOCAL_IMAGE_CACHE_DIR 值（import 时定、零重绑）、
LOG_FILE getter、_agent_canvas_node_image_by_id/_agent_sanitize_messages 两个 agent
层函数闭包（lambda 延迟解析）。主文件对被仍引用的函数留薄代理，调用点不改。
"""
import base64
import hashlib
import json
import mimetypes
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from websockets.sync.client import connect as ws_connect

from myridtv_core import append_log
from myridtv_core import read_json_file as _core_read_json_file, write_json_file as _core_write_json_file

_ASSETS_DIR = None
_IMAGE_CACHE_DIR = None
_log_file = lambda: None
_r_canvas_node_image_by_id = None
_r_sanitize_messages = None


_G_USER_DATA_DIR = None
_G_CODEX_APP_SERVER_BRIDGE = None
_G_CODEX_LOCAL_DEFAULT_MODEL = None
_G_CODEX_LOCAL_DEFAULT_RUNTIME_MODEL = None
_G_CODEX_LOCAL_REPLY_DIR = None
_G_CODEX_LOCAL_WORKSPACE = None
_G_CODEX_LOCAL_PERSIST_SESSIONS = None
_r_resolve_codex_executable = None


_G_CODEX_APP_SERVER_PORT_FILE = None
_r_resolve_codex_executable = None
CODEX_APP_SERVER_BRIDGE = None

# 35刀：codex 会话缓存单例（LOCK/CACHE 归模块，主文件同对象别名；
# CACHE_FILE 依赖注入值 USER_DATA_DIR → configure 内构造，cut9 处方）。
CODEX_LOCAL_SESSION_LOCK = threading.Lock()
CODEX_LOCAL_SESSION_CACHE = {}
_CODEX_SESSION_CACHE_FILE = None


def configure(assets_dir, image_cache_dir, log_file_getter,
              canvas_node_image_by_id, sanitize_messages,
              codex_globals, resolve_codex_executable):
    global _ASSETS_DIR, _IMAGE_CACHE_DIR, _log_file
    global _r_canvas_node_image_by_id, _r_sanitize_messages
    global _r_resolve_codex_executable
    global _G_CODEX_APP_SERVER_PORT_FILE
    global CODEX_APP_SERVER_BRIDGE
    global _G_USER_DATA_DIR
    global _G_CODEX_APP_SERVER_BRIDGE
    global _G_CODEX_LOCAL_DEFAULT_MODEL
    global _G_CODEX_LOCAL_DEFAULT_RUNTIME_MODEL
    global _G_CODEX_LOCAL_REPLY_DIR
    global _G_CODEX_LOCAL_WORKSPACE
    global _G_CODEX_LOCAL_PERSIST_SESSIONS
    _ASSETS_DIR = assets_dir
    _IMAGE_CACHE_DIR = image_cache_dir
    _log_file = log_file_getter
    _r_canvas_node_image_by_id = canvas_node_image_by_id
    _r_sanitize_messages = sanitize_messages
    _r_resolve_codex_executable = resolve_codex_executable
    _G_CODEX_APP_SERVER_PORT_FILE = codex_globals.get('CODEX_APP_SERVER_PORT_FILE')
    global _G_CODEX_APP_SERVER_BRIDGE
    _G_CODEX_APP_SERVER_BRIDGE = codex_globals['CODEX_APP_SERVER_BRIDGE']
    _G_USER_DATA_DIR = codex_globals['USER_DATA_DIR']
    _G_CODEX_APP_SERVER_BRIDGE = codex_globals['CODEX_APP_SERVER_BRIDGE']
    _G_CODEX_LOCAL_DEFAULT_MODEL = codex_globals['CODEX_LOCAL_DEFAULT_MODEL']
    _G_CODEX_LOCAL_DEFAULT_RUNTIME_MODEL = codex_globals['CODEX_LOCAL_DEFAULT_RUNTIME_MODEL']
    _G_CODEX_LOCAL_REPLY_DIR = codex_globals['CODEX_LOCAL_REPLY_DIR']
    _G_CODEX_LOCAL_WORKSPACE = codex_globals['CODEX_LOCAL_WORKSPACE']
    _G_CODEX_LOCAL_PERSIST_SESSIONS = codex_globals['CODEX_LOCAL_PERSIST_SESSIONS']


    global _CODEX_SESSION_CACHE_FILE
    _CODEX_SESSION_CACHE_FILE = codex_globals['USER_DATA_DIR'] / "data" / "codex_bridge_sessions.json"
    CODEX_LOCAL_SESSION_CACHE.update(_codex_bridge_read_session_cache())


def _codex_bridge_file_suffix(mime_type, fallback=".png"):
    ext = mimetypes.guess_extension(str(mime_type or "").split(";", 1)[0].strip()) or fallback
    if ext == ".jpe":
        ext = ".jpg"
    return ext


def _codex_bridge_image_bytes_from_url(raw_url):
    text = str(raw_url or "").strip()
    if not text:
        return None, None
    if text.lower().startswith("data:image/"):
        header, _, b64part = text.partition(",")
        mime_type = header[5:].split(";", 1)[0] if header.startswith("data:") else "image/png"
        try:
            return base64.b64decode(b64part), mime_type
        except Exception:
            return None, None
    if re.match(r"^https?://", text, re.I):
        try:
            req = urllib.request.Request(text, headers={"User-Agent": "MyridTV-Codex-Bridge/1.0"})
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.read(), resp.headers.get_content_type() or "image/png"
        except Exception as exc:
            append_log(_log_file(), "codex bridge image download failed url={}: {}".format(text, exc))
            return None, None
    clean = text.split("?", 1)[0].split("#", 1)[0]
    if clean.startswith("/assets/"):
        rel = urllib.parse.unquote(clean[len("/assets/"):].lstrip("/"))
        local_path = _ASSETS_DIR / rel
    elif clean.startswith("assets/"):
        rel = urllib.parse.unquote(clean[len("assets/"):].lstrip("/"))
        local_path = _ASSETS_DIR / rel
    else:
        local_path = Path(urllib.parse.unquote(clean))
    try:
        resolved = local_path.resolve()
        if resolved.exists():
            return resolved.read_bytes(), mimetypes.guess_type(str(resolved))[0] or "image/png"
    except Exception as exc:
        append_log(_log_file(), "codex bridge local image read failed url={}: {}".format(text, exc))
    return None, None


def _codex_bridge_attachment_files(payload):
    file_paths = []
    raw_images = payload.get("images") or payload.get("image_urls") or []
    if isinstance(raw_images, (str, dict)):
        raw_images = [raw_images]
    _IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(raw_images[:4]):
        if isinstance(item, dict):
            raw_url = item.get("source_url") or item.get("sourceUrl") or item.get("url") or item.get("path") or ""
            node_id = str(item.get("nodeId") or item.get("node_id") or "").strip()
            if node_id:
                node_img = _r_canvas_node_image_by_id(node_id, item.get("imageIndex"))
                if node_img:
                    raw_url = node_img
        else:
            raw_url = item
        image_bytes, mime_type = _codex_bridge_image_bytes_from_url(raw_url)
        if not image_bytes:
            continue
        suffix = _codex_bridge_file_suffix(mime_type)
        digest = hashlib.sha256(image_bytes).hexdigest()
        target = _IMAGE_CACHE_DIR / ("img_{}{}".format(digest, suffix))
        if not target.exists():
            target.write_bytes(image_bytes)
        file_paths.append(str(target))
    return file_paths


def _codex_bridge_prompt_text(payload, messages):
    sanitized = _r_sanitize_messages([dict(m) for m in messages])
    title_text = str((payload or {}).get("message") or "").strip()
    if not title_text:
        for msg in reversed(sanitized):
            if str(msg.get("role") or "") == "user" and str(msg.get("content") or "").strip():
                title_text = str(msg.get("content") or "").strip()
                break
    title_text = " ".join(title_text.split())
    if len(title_text) > 120:
        title_text = title_text[:117] + "..."
    lines = [
        "用户请求：{}".format(title_text or "MyridTV 无限画布本地 Myrid-Agent Bridge 请求"),
        "",
        "桥接说明：你正在通过 MyridTV 无限画布的本地 Myrid-Agent Bridge 回答用户。",
        "这是直接调用本机 Agent CLI 的模式，不走当前画布里的 DeepSeek API 链路。",
        "你可以根据对话和附带图片给出分析、创意、提示词和操作建议。",
        "除非消息里已经明确给出实际结果，否则不要声称你已经创建、修改或删除了画布节点。",
        "回答默认使用中文，保持具体、可执行。",
        "",
        "以下是当前对话上下文：",
    ]
    role_map = {"system": "系统", "user": "用户", "assistant": "助手", "tool": "工具结果"}
    for msg in sanitized:
        role = role_map.get(msg.get("role"), "用户")
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        lines.append("{}：{}".format(role, content))
    return "\n".join(lines).strip()


def _codex_bridge_compact_messages(messages, max_history=4, max_chars=700):
    compacted = []
    system_messages = []
    non_system = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "user")
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        trimmed = content if role == "system" or len(content) <= max_chars else (content[:max_chars] + "...(已截断)")
        item = {"role": role, "content": trimmed}
        if role == "system":
            system_messages.append(item)
        else:
            non_system.append(item)
    if system_messages:
        merged_system = "\n\n".join(item["content"] for item in system_messages if item.get("content"))
        compacted.append({"role": "system", "content": merged_system})
    older = non_system[:-max_history]
    recent = non_system[-max_history:]
    if older:
        summary_lines = []
        for item in older[-6:]:
            role = "用户" if item.get("role") == "user" else "助手"
            text = str(item.get("content") or "").replace("\n", " ").strip()
            if not text:
                continue
            summary_lines.append("{}: {}".format(role, text[:180]))
        if summary_lines:
            compacted.append({
                "role": "system",
                "content": "更早对话摘要：\n{}".format("\n".join(summary_lines))[: max_chars * 2],
            })
    compacted.extend(recent)
    return compacted


def _codex_bridge_protocol_instruction(tools, preset=None):
    tool_defs = []
    for item in tools or []:
        fn = (item or {}).get("function") or {}
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        tool_defs.append({
            "name": name,
            "description": fn.get("description") or "",
            "parameters": fn.get("parameters") or {},
        })
    lines = [
        "## 本地工具协议",
        "你可以通过返回 JSON 触发画布工具。",
        "【最高优先级格式规则】你的整个回复必须是且仅是一个 JSON 对象：第一个字符必须是 {，最后一个字符必须是 }。绝对禁止 Markdown 代码块、解释性文字、前后缀说明。",
        "JSON 格式必须是：",
        '{"assistant_reply":"给用户看的自然语言回复","tool_calls":[{"name":"工具名","arguments":{}}],"done":true}',
        "正确示例（需要建节点时）：",
        '{"assistant_reply":"我来创建三个方案节点","tool_calls":[{"name":"canvas_create_text_node","arguments":{"title":"方案A","prompt":"..."}},{"name":"canvas_create_generation_node","arguments":{"title":"方案A图","prompt":"... @图片1 参考人物发型"}}],"done":false}',
        "错误示例（禁止）：```json\\n{...}\\n``` 或 在 JSON 前后加任何文字。",
        "规则：",
        "1. 需要先查看画布、搜索素材、创建节点、更新节点时，必须用 tool_calls，不要只在文字里建议。",
        "2. 当用户要求把提示词/方案真正落到画布时，优先调用 canvas_create_generation_node 或 canvas_create_text_node。",
        "3. 只有用户明确要求马上出图，才调用 canvas_generate_images；否则只创建待生成节点。",
        "4. 如果本轮要调用工具，assistant_reply 要简短说明正在做什么；执行结果会在下一轮以“工具结果”提供给你。",
        "5. 当任务已经完成且不再需要工具时，返回 done=true；如果还要继续调用工具，返回 done=false。",
        "6. 如果不需要任何工具，tool_calls 返回空数组。",
        "7. 只要用了参考图，写入画布的生成提示词里就必须逐张写出 @图片1/@图片2/...，并明确说明每张图分别参考什么；编号严格按当前会话输入链图片顺序决定。如果用了多张，必须 @每一张分别说明。",
    ]
    if isinstance(preset, dict) and preset:
        lines.append("当前生图预设：{}".format(json.dumps({
            "provider_id": preset.get("provider_id") or "runninghub",
            "model": preset.get("model") or "按 API 设置中已配置的模型自动选择",
            "aspectRatio": preset.get("aspectRatio") or "4:3",
            "resolution": preset.get("resolution") or "2k",
            "quality": preset.get("quality") or "medium",
        }, ensure_ascii=False)))
    if tool_defs:
        lines.append("可用工具：")
        lines.append(json.dumps(tool_defs, ensure_ascii=False))
    return "\n".join(lines).strip()


def _codex_bridge_extract_json(text):
    raw = str(text or "").strip()
    if not raw:
        return None
    candidates = [raw]
    fenced = raw
    if fenced.startswith("```"):
        fenced = re.sub(r"^```(?:json)?\s*", "", fenced, flags=re.IGNORECASE)
        fenced = re.sub(r"\s*```$", "", fenced).strip()
        candidates.append(fenced)
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start:end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    # 括号配平扫描：从混杂文本（前后缀文字/markdown 残片）里抠出最外层 JSON 对象
    idx = 0
    n = len(raw)
    while idx < n:
        ch = raw[idx]
        if ch != "{":
            idx += 1
            continue
        depth = 0
        in_str = False
        esc = False
        for pos in range(idx, n):
            c = raw[pos]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    fragment = raw[idx:pos + 1]
                    try:
                        parsed = json.loads(fragment)
                    except Exception:
                        break
                    if isinstance(parsed, dict) and ("tool_calls" in parsed or "assistant_reply" in parsed):
                        return parsed
                    break
        idx += 1
    return None


def _codex_bridge_normalize_tool_calls(payload):
    if isinstance(payload, dict):
        raw_calls = payload.get("tool_calls")
        if raw_calls is None:
            raw_calls = payload.get("actions")
        if raw_calls is None and payload.get("name"):
            raw_calls = [payload]
    else:
        raw_calls = payload
    if not isinstance(raw_calls, list):
        return []
    calls = []
    for item in raw_calls:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("tool") or "").strip()
        arguments = item.get("arguments")
        if arguments is None:
            arguments = item.get("args")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except Exception:
                arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        if name:
            calls.append({"name": name, "arguments": arguments})
    return calls


def _codex_bridge_request_wants_canvas_nodes(payload):
    text = str((payload or {}).get("message") or "").strip()
    if not text:
        return False
    hints = ["节点", "创建到画布", "建到画布", "创建节点", "建节点", "拆成", "拆为", "海报节点", "分镜节点", "提示词节点"]
    return any(token in text for token in hints)


def _agent_chinese_count_to_int(value, default=3):
    raw = str(value or "").strip()
    if not raw:
        return default
    if raw.isdigit():
        return max(1, min(8, int(raw)))
    table = {
        "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8,
    }
    if raw in table:
        return table[raw]
    if raw.startswith("十"):
        return 8
    if raw.endswith("十"):
        return 8
    if "十" in raw:
        return 8
    return default


def _codex_bridge_requested_node_count(text, default=3):
    raw = str(text or "")
    patterns = [
        r"([0-9一二两三四五六七八九十]+)\s*个[^\n，。；;]{0,24}(?:节点|方案|海报|分镜|镜头|提示词)",
        r"(?:创建|建立|生成|拆成|拆为)\s*([0-9一二两三四五六七八九十]+)\s*个",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw)
        if match:
            return _agent_chinese_count_to_int(match.group(1), default)
    return default


def _codex_bridge_split_titles(text):
    raw = str(text or "").strip()
    if not raw:
        return []
    raw = re.split(r"[。；;]", raw, maxsplit=1)[0].strip()
    raw = re.sub(r"\s*(?:方案|方向|节点)?\s*$", "", raw).strip()
    return [
        part.strip(" -*`'\"“”‘’，,。；;")
        for part in re.split(r"[、,，/／]+", raw)
        if part.strip(" -*`'\"“”‘’，,。；;")
    ]


def _codex_bridge_titles_from_text(text):
    raw = str(text or "").replace("\r\n", "\n")
    titles = []
    inline_match = re.search(
        r"(?m)(?:创建|建立|生成|拆成|拆为)\s*[0-9一二两三四五六七八九十]+\s*个[^\n]{0,32}(?:生图|生成|画布|海报|分镜)?(?:节点|方案|海报|分镜|镜头)?\s*[:：]\s*([^\n]+)",
        raw,
    )
    if inline_match:
        titles.extend(_codex_bridge_split_titles(inline_match.group(1)))
    quoted = re.findall(r"[“\"']([^”\"']{2,80})[”\"']", raw)
    for quote in quoted:
        if re.search(r"[、,，/／]", quote):
            titles.extend(_codex_bridge_split_titles(quote))
        else:
            titles.append(quote.strip(" -*`'\"“”‘’，,。；;"))
    seen = set()
    result = []
    for title in titles:
        if title and title not in seen:
            seen.add(title)
            result.append(title)
    return result[:8]


def _codex_bridge_default_generation_nodes(text, fallback_prompt=""):
    source = str(fallback_prompt or text or "").strip()
    count = _codex_bridge_requested_node_count(source or text, 3)
    titles = _codex_bridge_titles_from_text(source) or _codex_bridge_titles_from_text(text)
    labels = ["方案 A", "方案 B", "方案 C", "方案 D", "方案 E", "方案 F", "方案 G", "方案 H"]
    while len(titles) < count:
        titles.append(labels[len(titles)])
    return [
        {
            "title": title,
            "prompt": "主题：{}\n\n请根据以下需求生成完整中文生图提示词，并保持可直接执行：\n{}".format(title, source or title).strip(),
        }
        for title in titles[:count]
    ]


def _codex_bridge_extract_generation_nodes(text, fallback_prompt=""):
    raw = str(text or "").replace("\r\n", "\n")
    cutoff = re.search(r"(?m)^\s*(?:建议(?:画布)?节点命名|统一参数|如果你把画布工具|如果把画布工具|如果你需要我继续)", raw)
    if cutoff:
        raw = raw[:cutoff.start()].rstrip()
    heading_re = re.compile(
        r"(?m)^\s*(?:\*\*)?\s*(?:(?:(海报节点|关键场景节点|分镜节点|镜头节点|场景节点|节点|海报|镜头|场景|分镜)\s*([0-9一二三四五六七八九十]+))|([0-9]+)[\.\:：、])\s*(?:[:：｜|]\s*)?([^\n*`]+?)\s*(?:\*\*)?\s*$"
    )
    matches = list(heading_re.finditer(raw))
    items = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        title = str(match.group(4) or "").strip().strip("*` ")
        title = re.sub(r"^[\|\uff5c:：\-·\s]+", "", title).strip()
        body = raw[start:end].strip()
        body = re.sub(r"^[:：\-\s]+", "", body)
        body = re.sub(r"(?m)^\s*```(?:text|json)?\s*$", "", body)
        body = re.sub(r"(?m)^\s*```\s*$", "", body).strip()
        body = re.sub(r"(?m)^\s*标题\s*[:：]\s*", "", body, count=1)
        body = re.sub(r"(?m)^\s*(?:提示词|prompt)\s*[:：]\s*", "", body, count=1)
        body = body.strip()
        if not body:
            continue
        if not title:
            title = "Agent 节点 {}".format(len(items) + 1)
        items.append({"title": title, "prompt": body})
    if items:
        return items[:8]
    titles = _codex_bridge_titles_from_text(raw)
    prompt_seed = raw
    if not titles and re.search(r"(?:创建|建立|生成).{0,40}节点", raw):
        quoted = re.findall(r"[“\"']([^”\"']{2,40})[”\"']", raw)
        for quote in quoted:
            titles.extend(_codex_bridge_split_titles(quote))
        prompt_seed = raw
    if not titles:
        return []
    prompt_match = re.search(r"(?s)(?:可直接使用的提示词|提示词|prompt)\s*[:：]\s*(.+)$", raw, flags=re.IGNORECASE)
    prompt_body = (prompt_match.group(1) if prompt_match else prompt_seed).strip()
    prompt_body = re.sub(r"(?m)^\s*[>\-]\s*", "", prompt_body).strip()
    prompt_body = _codex_bridge_cleanup_fallback_text(prompt_body)
    if not prompt_body or len(prompt_body) < 20:
        prompt_body = str(fallback_prompt or "").strip()
    return [
        {"title": title, "prompt": "主题：{}\n\n{}".format(title, prompt_body or title).strip()}
        for title in titles[:8]
    ]


def _agent_result_created_nodes(tool_log):
    items = []
    seen = set()
    for entry in tool_log or []:
        result = entry.get("result") if isinstance(entry, dict) else {}
        args = entry.get("args") if isinstance(entry, dict) else {}
        node_id = str((result or {}).get("node_id") or (result or {}).get("nodeId") or "").strip()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        items.append({
            "node_id": node_id,
            "title": str((args or {}).get("title") or "").strip(),
            "status": str((result or {}).get("status") or ("running" if (result or {}).get("task_id") else "created")).strip() or "created",
            "type": "smart-image" if str((entry or {}).get("name") or "").strip() in ("canvas_create_generation_node", "canvas_generate_images") else "smart-prompt",
            "task_id": str((result or {}).get("task_id") or "").strip(),
        })
    return items


def _codex_bridge_cleanup_fallback_text(text):
    lines = str(text or "").replace("\r\n", "\n").split("\n")
    blocked_markers = (
        "当前没有暴露",
        "未挂载",
        "Bridge 会话没有加载",
        "没有拿到",
        "没有暴露",
        "没有可调用的",
        "无法实际创建节点",
        "不能直接替你创建节点",
        "不能直接创建节点",
        "不能直接创建画布节点",
        "不能真实创建画布节点",
        "不能真实创建节点",
        "不能声称已经创建完成",
        "不能声称已经创建",
        "直接复制到画布生成节点里使用",
        "直接复制到 MyridTV 画布生成节点里",
        "不能直接把节点写进 MyridTV 画布",
        "如果画布 Bridge 把",
        "请重新连接或启用画布工具后",
    )
    cleaned = []
    skip_blank_tail = False
    for raw in lines:
        line = str(raw or "")
        if any(marker in line for marker in blocked_markers):
            skip_blank_tail = True
            continue
        if skip_blank_tail and not line.strip():
            continue
        skip_blank_tail = False
        cleaned.append(line)
    text = "\n".join(cleaned).strip()
    if "可以先把这" in text and "关键场景海报节点内容给你" in text:
        text = text.replace("可以先把这 3 个关键场景海报节点内容给你，", "", 1).strip()
    if text.startswith("先给你 3 个"):
        text = text[text.find("：") + 1:].strip() if "：" in text else text
    return text


def _codex_bridge_should_reset_session(error_text, had_session=False):
    text = str(error_text or "")
    if not text:
        return False
    lowered = text.lower()
    if had_session and ("unknown session" in lowered or "not found" in lowered or "no session" in lowered):
        return True
    reset_markers = (
        "thread-store conflict",
        "already has an active writer",
        "thread/resume failed",
        "thread not found",
        "active writer",
    )
    return any(marker in lowered for marker in reset_markers)


# ===== 第15刀追加：codex bridge 执行族（app-server/persistent） =====
def _codex_bridge_extract_thread_id(stdout_lines):
    for line in stdout_lines:
        try:
            event = json.loads(line)
        except Exception:
            continue
        if event.get("type") == "thread.started":
            thread_id = str(event.get("thread_id") or "").strip()
            if thread_id:
                return thread_id
    return ""


def _run_codex_bridge_exec(prompt_text, model, attachment_files, session_id=""):
    model = str(model or "").strip()
    if model == _G_CODEX_LOCAL_DEFAULT_MODEL:
        model = _G_CODEX_LOCAL_DEFAULT_RUNTIME_MODEL
    codex_executable = _r_resolve_codex_executable()
    _G_CODEX_LOCAL_REPLY_DIR.mkdir(parents=True, exist_ok=True)
    output_file = _G_CODEX_LOCAL_REPLY_DIR / ("codex_bridge_reply_{}.txt".format(uuid.uuid4().hex))
    base_args = [
        "--ignore-user-config",
        "--skip-git-repo-check",
        "--json",
        "--output-last-message",
        str(output_file),
    ]
    if session_id:
        cmd = [codex_executable, "exec", "resume", session_id]
        if model:
            cmd.extend(["-m", model])
        for image_path in attachment_files:
            cmd.extend(["-i", image_path])
        cmd.extend(base_args)
        cmd.append("-")
    else:
        cmd = [
            codex_executable,
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--sandbox",
            "read-only",
            "--json",
            "--color",
            "never",
            "-C",
            str(_G_CODEX_LOCAL_WORKSPACE),
            "--add-dir",
            str(_G_USER_DATA_DIR),
            "--output-last-message",
            str(output_file),
            "-",
        ]
        if model:
            cmd[2:2] = ["-m", model]
        for image_path in attachment_files:
            cmd[2:2] = ["-i", image_path]
    timeout = 300
    try:
        proc = subprocess.run(
            cmd,
            input=prompt_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("本地 Myrid-Agent Bridge 超时，请稍后重试。")
    except FileNotFoundError as exc:
        raise RuntimeError("本地 Myrid-Agent Bridge 未找到可执行文件：{}".format(exc))
    stdout_lines = [line.strip() for line in str(proc.stdout or "").splitlines() if line.strip()]
    thread_id = _codex_bridge_extract_thread_id(stdout_lines) or str(session_id or "").strip()
    final_text = ""
    if output_file.exists():
        try:
            final_text = output_file.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            final_text = ""
        try:
            output_file.unlink(missing_ok=True)
        except Exception:
            pass
    if not final_text:
        for line in stdout_lines:
            try:
                event = json.loads(line)
            except Exception:
                continue
            if event.get("type") == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message":
                    final_text = str(item.get("text") or "").strip()
    if not final_text:
        combined = "\n".join(stdout_lines)
        for chunk in re.findall(r"\{.*?\}(?=\s*\{|$)", combined):
            try:
                event = json.loads(chunk)
            except Exception:
                continue
            if event.get("type") == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message":
                    final_text = str(item.get("text") or "").strip()
    if proc.returncode != 0 and not final_text:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(("本地 Myrid-Agent Bridge 调用失败: " + detail[:600]).strip())
    if not final_text:
        raise RuntimeError("本地 Myrid-Agent Bridge 没有返回有效回复。")
    return {
        "text": final_text,
        "returncode": proc.returncode,
        "stdout_events": len(stdout_lines),
        "thread_id": thread_id,
    }


def _run_codex_bridge_persistent(prompt_text, model, attachment_files, session_id=""):
    runtime_model = str(model or "").strip()
    if runtime_model == _G_CODEX_LOCAL_DEFAULT_MODEL or not runtime_model:
        runtime_model = _G_CODEX_LOCAL_DEFAULT_RUNTIME_MODEL
    thread_id = str(session_id or "").strip()
    try:
        thread_id = _G_CODEX_APP_SERVER_BRIDGE.ensure_thread(thread_id, runtime_model)
        result = _G_CODEX_APP_SERVER_BRIDGE.run_turn(thread_id, prompt_text, runtime_model, attachment_files)
    except Exception as exc:
        _G_CODEX_APP_SERVER_BRIDGE.reset()
        raise RuntimeError("本地 Myrid-Agent 常驻 Bridge 调用失败: {}".format(str(exc)[:400]))
    return {
        "text": str(result.get("text") or "").strip(),
        "returncode": 0,
        "stdout_events": 0,
        "thread_id": thread_id,
        "bridge_mode": "app_server_ws",
    }

# ===== 第25刀追加：codex app-server 桥（进程内 WS 单例） =====
def _codex_app_server_find_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _codex_app_server_image_block(image_path):
    try:
        resolved = str(Path(image_path).resolve())
    except Exception:
        return None
    return {
        "type": "localImage",
        "path": resolved,
    }


class CodexAppServerBridge:
    def __init__(self):
        self._lock = threading.RLock()
        self._proc = None
        self._ws = None
        self._ws_url = ""
        self._http_readyz = ""
        self._seq = 0
        self._initialized = False

    def _next_id(self):
        self._seq += 1
        return "myrid-{}".format(self._seq)

    def _creationflags(self):
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)

    def _close_ws(self):
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            pass
        self._ws = None

    def _stop_proc(self):
        proc = self._proc
        self._proc = None
        if not proc:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def reset(self):
        with self._lock:
            self._close_ws()
            self._stop_proc()
            self._initialized = False
            self._ws_url = ""
            self._http_readyz = ""

    def ensure_ready(self):
        with self._lock:
            if self._proc and self._proc.poll() is None and self._ws is not None and self._initialized:
                return
            self.reset()
            port = _codex_app_server_find_port()
            self._ws_url = "ws://127.0.0.1:{}".format(port)
            self._http_readyz = "http://127.0.0.1:{}/readyz".format(port)
            cmd = [_r_resolve_codex_executable(), "app-server", "--listen", self._ws_url]
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(_G_CODEX_LOCAL_WORKSPACE),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=self._creationflags(),
            )
            deadline = time.time() + 20
            last_error = ""
            while time.time() < deadline:
                if self._proc.poll() is not None:
                    break
                try:
                    with urllib.request.urlopen(self._http_readyz, timeout=1.5) as resp:
                        if resp.status == 200:
                            break
                except Exception as exc:
                    last_error = str(exc)
                time.sleep(0.25)
            if self._proc.poll() is not None:
                output = ""
                try:
                    output = str(self._proc.stdout.read() or "").strip()
                except Exception:
                    pass
                self.reset()
                raise RuntimeError("Myrid-Agent app-server 启动失败: {}".format((output or last_error or "unknown error")[:400]))
            self._ws = ws_connect(self._ws_url, open_timeout=60, close_timeout=5, max_size=10_000_000)
            init_id = self._next_id()
            self._send({"jsonrpc": "2.0", "id": init_id, "method": "initialize", "params": {
                "clientInfo": {"name": "myridtv-codex-bridge", "version": "0.1"},
                "capabilities": {"experimentalApi": True, "requestAttestation": False, "optOutNotificationMethods": []},
            }})
            self._read_until_response(init_id)
            self._send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
            self._initialized = True
            _core_write_json_file(_G_CODEX_APP_SERVER_PORT_FILE, {"ws_url": self._ws_url, "readyz": self._http_readyz, "updated_at": int(time.time())})

    def _send(self, payload):
        self._ws.send(json.dumps(payload, ensure_ascii=False))

    def _recv(self):
        raw = self._ws.recv()
        return json.loads(raw)

    def _read_until_response(self, request_id):
        while True:
            message = self._recv()
            if message.get("id") == request_id:
                return message

    def _start_thread(self, model):
        request_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "thread/start",
            "params": {
                "model": model or _G_CODEX_LOCAL_DEFAULT_RUNTIME_MODEL,
                "cwd": str(_G_CODEX_LOCAL_WORKSPACE),
                "approvalPolicy": "never",
                "sandbox": "read-only",
            },
        })
        response = self._read_until_response(request_id)
        if response.get("error"):
            raise RuntimeError("Codex thread/start 失败: {}".format(str(response.get("error"))[:300]))
        return str((((response.get("result") or {}).get("thread") or {}).get("id") or "")).strip()

    def _turn(self, thread_id, message_text, model, attachment_files):
        request_id = self._next_id()
        input_blocks = [{"type": "text", "text": message_text, "text_elements": []}]
        for image_path in attachment_files[:4]:
            block = _codex_app_server_image_block(image_path)
            if block:
                input_blocks.append(block)
        self._send({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "turn/start",
            "params": {
                "threadId": thread_id,
                "input": input_blocks,
                "model": model or _G_CODEX_LOCAL_DEFAULT_RUNTIME_MODEL,
            },
        })
        response = self._read_until_response(request_id)
        if response.get("error"):
            raise RuntimeError("Codex turn/start 失败: {}".format(str(response.get("error"))[:300]))
        turn = (response.get("result") or {}).get("turn") or {}
        turn_id = str(turn.get("id") or "").strip()
        final_text = ""
        while True:
            message = self._recv()
            method = str(message.get("method") or "")
            params = message.get("params") or {}
            if method == "item/completed":
                item = params.get("item") or {}
                if item.get("type") == "agentMessage":
                    final_text = str(item.get("text") or final_text or "").strip()
            if method == "turn/completed":
                turn_info = params.get("turn") or {}
                if str(turn_info.get("id") or "").strip() != turn_id:
                    continue
                if not final_text:
                    for item in turn_info.get("items") or []:
                        if isinstance(item, dict) and item.get("type") == "agentMessage":
                            final_text = str(item.get("text") or "").strip()
                return {
                    "text": final_text,
                    "turn_id": turn_id,
                    "thread_id": thread_id,
                }

    def run_turn(self, thread_id, message_text, model, attachment_files):
        with self._lock:
            self.ensure_ready()
            return self._turn(thread_id, message_text, model, attachment_files)

    def ensure_thread(self, thread_id, model):
        with self._lock:
            self.ensure_ready()
            if thread_id:
                return thread_id
            return self._start_thread(model)


CODEX_APP_SERVER_BRIDGE = CodexAppServerBridge()
_G_CODEX_APP_SERVER_BRIDGE = CODEX_APP_SERVER_BRIDGE

def _codex_bridge_read_session_cache():
    data = _core_read_json_file(_CODEX_SESSION_CACHE_FILE, {})
    return data if isinstance(data, dict) else {}


def _codex_bridge_write_session_cache():
    with CODEX_LOCAL_SESSION_LOCK:
        _core_write_json_file(_CODEX_SESSION_CACHE_FILE, CODEX_LOCAL_SESSION_CACHE)


def _codex_bridge_session_key(payload, model):
    canvas_id = str((payload or {}).get("canvas_id") or "").strip() or "default"
    agent_id = str((payload or {}).get("agent_id") or "").strip() or "codex"
    runtime_model = str(model or _G_CODEX_LOCAL_DEFAULT_MODEL).strip() or _G_CODEX_LOCAL_DEFAULT_MODEL
    # Reuse one Codex thread per canvas/agent/model. Including each UI chat
    # session here created many identical visible Codex sidebar entries.
    return "{}::{}::{}".format(canvas_id, agent_id, runtime_model)


def _codex_bridge_session_record(payload, model):
    key = _codex_bridge_session_key(payload, model)
    with CODEX_LOCAL_SESSION_LOCK:
        record = CODEX_LOCAL_SESSION_CACHE.get(key)
    return key, record if isinstance(record, dict) else None


def _codex_bridge_store_session_record(key, thread_id, model):
    if not key or not thread_id:
        return
    now = int(time.time())
    with CODEX_LOCAL_SESSION_LOCK:
        CODEX_LOCAL_SESSION_CACHE[key] = {
            "thread_id": str(thread_id).strip(),
            "model": str(model or "").strip(),
            "updated_at": now,
        }
    _codex_bridge_write_session_cache()


def _codex_bridge_clear_session_record(key):
    if not key:
        return
    changed = False
    with CODEX_LOCAL_SESSION_LOCK:
        if key in CODEX_LOCAL_SESSION_CACHE:
            del CODEX_LOCAL_SESSION_CACHE[key]
            changed = True
    if changed:
        _codex_bridge_write_session_cache()
