# -*- coding: utf-8 -*-
"""MyridTV canvas-agent 配置域（后端拆分第3刀）：Agent 对话历史(jsonl+_index)、规则文件、
技能(skills)读写与 @调用解析、config_payload。

逐字迁移自 rh_official_proxy.py 块 L(canvas_agent_history_path)..L(_RH_TLS_CTX_CACHE) 前
（可逆还原行级 diff=0）。行为零变更。
本模块导出单例 CANVAS_AGENT_LOADED_SKILLS={"skills":[[]}]}（块内写、主文件 submit 链读，
主文件定义行替换为别名=同一对象，避免 configure 时序雷）。
configure() 注入：7 个路径/上限常量（定义均早于注入点，值直传安全）+ _log_file getter
（LOG_FILE 被 write_app_config global 重绑）+ agents_meta_payload（区段外唯一函数依赖，
def 在注入点之后，主文件用 lambda 闭包延迟解析）。
主文件对区段外仍调用的函数保留同名薄代理，调用点不改。
"""
import json
import re
import time
import uuid

from myridtv_core import ApiError, append_log, safe_agent_skill_name

# 本轮实际注入的技能名列表（供前端在回复里展示"加载的技能"）——单例归本模块，主文件别名共享
CANVAS_AGENT_LOADED_SKILLS = {"skills": []}

_CFG_HISTORY_DIR = None
_CFG_HISTORY_INDEX_FILE = None
_CFG_RULES_FILE = None
_CFG_SKILLS_DIR = None
_CFG_MAX_INVOKED = 5
_CFG_RULES_MAX = 32768
_CFG_SKILL_MAX = 24576
_USER_DATA_DIR = None
_log_file = lambda: None
_x_agents_meta_payload = lambda: []


def configure(history_dir, history_index_file, rules_file, skills_dir,
              max_invoked, rules_max, skill_max, user_data_dir,
              log_file_getter, agents_meta_payload):
    global _CFG_HISTORY_DIR, _CFG_HISTORY_INDEX_FILE, _CFG_RULES_FILE, _CFG_SKILLS_DIR
    global _CFG_MAX_INVOKED, _CFG_RULES_MAX, _CFG_SKILL_MAX, _USER_DATA_DIR
    global _log_file, _x_agents_meta_payload
    _CFG_HISTORY_DIR = history_dir
    _CFG_HISTORY_INDEX_FILE = history_index_file
    _CFG_RULES_FILE = rules_file
    _CFG_SKILLS_DIR = skills_dir
    _CFG_MAX_INVOKED = max_invoked
    _CFG_RULES_MAX = rules_max
    _CFG_SKILL_MAX = skill_max
    _USER_DATA_DIR = user_data_dir
    _log_file = log_file_getter
    _x_agents_meta_payload = agents_meta_payload


def canvas_agent_history_path(canvas_id=""):
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", str(canvas_id or "default").strip() or "default")
    return _CFG_HISTORY_DIR / f"{name}.json"


def read_limited_text(path, max_chars):
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except Exception as exc:
        append_log(_log_file(), f"read text failed path={path}: {exc}")
        return ""
    return text[:max_chars]


def ensure_canvas_agent_config_files():
    try:
        _CFG_RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CFG_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        if not _CFG_RULES_FILE.exists():
            _CFG_RULES_FILE.write_text(
                "# MyridTV Agent 全局规则\n\n"
                "- 默认使用中文回答，除非用户明确要求其他语言。\n"
                "- 处理无限画布任务时，优先结合用户选中的节点、引用图片和当前画布上下文。\n"
                "- 对图片优化类请求，给出可直接执行的修改建议或提示词，不要只泛泛解释。\n",
                encoding="utf-8",
            )
        default_skill = _CFG_SKILLS_DIR / "服装优化.md"
        default_skill_marker = _CFG_SKILLS_DIR / ".default_skill_deleted"
        if not default_skill.exists() and not default_skill_marker.exists():
            default_skill.write_text(
                "# 服装优化\n\n"
                "用于优化人物、模特、制服、角色服饰或商业服装图。\n\n"
                "执行要点：\n"
                "- 保留人物身份、姿势、构图和原图主要光照。\n"
                "- 优先提升服装剪裁、面料质感、褶皱逻辑、配色统一性和细节完整度。\n"
                "- 避免改变脸部、肢体数量、背景主体和品牌标识，除非用户明确要求。\n"
                "- 输出时给出一段可直接用于图像编辑/重绘的中文提示词。\n",
                encoding="utf-8",
            )
    except Exception as exc:
        append_log(_log_file(), f"ensure canvas agent config failed: {exc}")


def read_canvas_agent_rules():
    ensure_canvas_agent_config_files()
    return read_limited_text(_CFG_RULES_FILE, _CFG_RULES_MAX).strip()


def write_canvas_agent_rules(content):
    text = str(content or "")
    if len(text) > _CFG_RULES_MAX:
        raise ApiError(400, f"全局规则过长，最多 {_CFG_RULES_MAX} 字符")
    ensure_canvas_agent_config_files()
    _CFG_RULES_FILE.write_text(text.rstrip() + ("\n" if text.strip() else ""), encoding="utf-8")
    return read_canvas_agent_rules()


def list_canvas_agent_skills():
    ensure_canvas_agent_config_files()
    skills = []
    try:
        files = sorted(_CFG_SKILLS_DIR.glob("*.md"), key=lambda path: path.stem.casefold())
    except Exception:
        files = []
    for path in files:
        name = safe_agent_skill_name(path.stem)
        if not name:
            continue
        try:
            stat = path.stat()
            size = stat.st_size
            updated_at = int(stat.st_mtime * 1000)
        except Exception:
            size = 0
            updated_at = 0
        skills.append({"name": name, "file": path.name, "size": size, "updatedAt": updated_at})
    return skills[:200]


def canvas_agent_skill_path(name):
    safe_name = safe_agent_skill_name(name)
    if not safe_name:
        raise ApiError(400, "技能名无效")
    path = (_CFG_SKILLS_DIR / f"{safe_name}.md").resolve()
    root = _CFG_SKILLS_DIR.resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise ApiError(400, "技能路径无效")
    return path


def read_canvas_agent_skill(name):
    ensure_canvas_agent_config_files()
    path = canvas_agent_skill_path(name)
    return {
        "name": path.stem,
        "file": path.name,
        "content": read_limited_text(path, _CFG_SKILL_MAX),
    }


def write_canvas_agent_skill(name, content):
    text = str(content or "")
    if len(text) > _CFG_SKILL_MAX:
        raise ApiError(400, f"技能内容过长，最多 {_CFG_SKILL_MAX} 字符")
    ensure_canvas_agent_config_files()
    path = canvas_agent_skill_path(name)
    path.write_text(text.rstrip() + ("\n" if text.strip() else ""), encoding="utf-8")
    return read_canvas_agent_skill(path.stem)


def delete_canvas_agent_skill(name):
    path = canvas_agent_skill_path(name)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    # 内置默认技能删除后打标记，避免 ensure 自动重建（用户要求 2026-08-16）
    if path.stem == "服装优化":
        try:
            (_CFG_SKILLS_DIR / ".default_skill_deleted").write_text("1", encoding="utf-8")
        except Exception:
            pass
    return {"name": path.stem, "deleted": True}


def extract_invoked_skill_names(text):
    found = []
    for match in re.finditer(r"[@＠]([^\s@＠#＃，,。；;：:（）()\[\]{}<>《》\"'“”‘’]+)", str(text or "")):
        name = safe_agent_skill_name(match.group(1))
        if name and name not in found:
            found.append(name)
    return found[:_CFG_MAX_INVOKED]


def payload_invoked_skill_names(payload):
    found = []
    explicit = payload.get("skill_names") or payload.get("skills") or []
    if isinstance(explicit, str):
        explicit = [explicit]
    if isinstance(explicit, list):
        for item in explicit:
            name = safe_agent_skill_name(item)
            if name and name not in found:
                found.append(name)
    for name in extract_invoked_skill_names(payload.get("message") or ""):
        if name not in found:
            found.append(name)
    return found[:_CFG_MAX_INVOKED]


def _skill_trigger_words(content):
    """从技能正文头部解析 <!-- trigger: ... --> 触发表述，返回关键词列表。"""
    text = str(content or "")
    m = re.search(r"<!--\s*trigger:([\s\S]*?)-->", text)
    if not m:
        return []
    raw = m.group(1)
    # 触发词支持中文逗号/空格/顿号分隔，也支持 | 符号
    tokens = re.split(r"[，,｜|\s、]+", raw)
    return [t.strip() for t in tokens if t.strip()]


def _match_invoked_skill_names(user_text):
    """根据用户消息内容，按技能触发词做自动匹配，返回应注入的技能名列表（不依赖 @ 标记）。"""
    user_text = str(user_text or "")
    if not user_text.strip():
        return []
    scored = []
    try:
        skills = list_canvas_agent_skills()
    except Exception:
        return []
    for entry in skills:
        name = entry.get("name") or ""
        if not name:
            continue
        try:
            skill = read_canvas_agent_skill(name)
            content = str(skill.get("content") or "")
        except Exception:
            continue
        terms = _skill_trigger_words(content)
        if not terms:
            continue
        # 命中计分：每个出现的触发词 +1（去重）
        hits = set()
        for term in terms:
            if term and term in user_text:
                hits.add(term)
        if hits:
            scored.append((len(hits), name, len(hits)))
    # 按命中数排序，命中更多的优先；最多注入 3 个
    scored.sort(key=lambda x: (-x[0], x[1]))
    # 只取命中数 >=1 的，最多3个，且排除与显式 @ 重复的（由调用方去重）
    return [name for _, name, _ in scored[:3]]


def _agent_has_flow_skill(payload):
    """本轮是否命中了「流程型技能」（如叙事短片主链）。命中后应跳过通用候选交互引导，避免与技能的阶段推进冲突。"""
    user_text = str(payload.get("message") or "")
    for item in payload.get("messages") or payload.get("history") or []:
        if isinstance(item, dict) and str(item.get("role") or "") == "user":
            user_text += " " + str(item.get("content") or item.get("text") or "")
    names = set(_match_invoked_skill_names(user_text))
    # 流程型技能名：命中即代表要走完整阶段流程，候选交互引导会让模型倾向只输出候选卡片，冲突。
    flow_skills = {"叙事短片主链"}
    return bool(names & flow_skills)


def canvas_agent_augmented_system_prompt(payload):
    parts = []
    base_prompt = str(payload.get("system_prompt") or "").strip()
    if base_prompt:
        parts.append(base_prompt)
    rules = read_canvas_agent_rules()
    if rules:
        parts.append("## MyridTV Agent 全局规则\n" + rules)
    # 1) 显式 @ 标记的技能
    invoked = []
    for name in payload_invoked_skill_names(payload):
        skill = read_canvas_agent_skill(name)
        content = str(skill.get("content") or "").strip()
        if content:
            invoked.append((skill.get("name") or name, content[:_CFG_SKILL_MAX]))
    invoked_names = {n for n, _ in invoked}
    # 2) 自动意图匹配：根据用户需求自动命中技能（无需 @）
    user_text = str(payload.get("message") or "")
    for item in payload.get("messages") or payload.get("history") or []:
        if isinstance(item, dict) and str(item.get("role") or "") == "user":
            user_text += " " + str(item.get("content") or item.get("text") or "")
    for name in _match_invoked_skill_names(user_text):
        if name in invoked_names:
            continue
        skill = read_canvas_agent_skill(name)
        content = str(skill.get("content") or "").strip()
        if content:
            invoked.append((skill.get("name") or name, content[:_CFG_SKILL_MAX]))
            invoked_names.add(name)
    if invoked:
        skill_sections = [
            "请根据本轮用户需求，使用以下技能作为工作方法。按你的判断一步步执行，不要把这些技能的调用过程展示给用户（你在执行过程中调用了技能，但用户无需看到触发细节）。"
        ]
        for name, content in invoked:
            skill_sections.append(f"### 技能：{name}\n{content}")
        parts.append("## MyridTV Agent 调用技能\n" + "\n\n".join(skill_sections))
    # 记录本轮实际注入的技能名，供前端在回复里展示"加载的技能"
    CANVAS_AGENT_LOADED_SKILLS["skills"] = [n for n, _ in invoked]
    return "\n\n".join(parts).strip()


def canvas_agent_config_payload(include_rules=True):
    return {
        "ok": True,
        "rules": read_canvas_agent_rules() if include_rules else "",
        "rules_file": str(_CFG_RULES_FILE),
        "skills_dir": str(_CFG_SKILLS_DIR),
        "skills": list_canvas_agent_skills(),
        "invocation": {"prefix": "@", "example": "@服装优化"},
        "agents": _x_agents_meta_payload(),
    }


def normalize_canvas_agent_history_item(item):
    if not isinstance(item, dict):
        return None
    session_id = str(item.get("id") or "").strip()
    if not session_id:
        return None
    messages = []
    for raw in item.get("messages") or []:
        if not isinstance(raw, dict):
            continue
        role = "user" if str(raw.get("role") or "").strip() == "user" else "assistant"
        text = str(raw.get("text") or raw.get("content") or "").strip()
        refs = raw.get("refs") if isinstance(raw.get("refs"), list) else []
        source_refs = raw.get("sourceRefs") if isinstance(raw.get("sourceRefs"), list) else []
        if not text and not refs and not source_refs:
            continue
        safe_msg = {
            "id": str(raw.get("id") or uuid.uuid4().hex),
            "role": role,
            "text": text,
            "refs": refs,
            "sourceRefs": source_refs,
        }
        # 保留对话内选择/头脑风暴/执行计划等状态，历史重开后仍可见可选内容与选中态
        if raw.get("chosenId"):
            safe_msg["chosenId"] = str(raw["chosenId"])
        if isinstance(raw.get("brainstormCard"), dict):
            safe_msg["brainstormCard"] = raw["brainstormCard"]
        if isinstance(raw.get("actionPlan"), dict):
            safe_msg["actionPlan"] = raw["actionPlan"]
        if raw.get("brainstormLocked"):
            safe_msg["brainstormLocked"] = bool(raw["brainstormLocked"])
        if raw.get("brainstormChosenId"):
            safe_msg["brainstormChosenId"] = str(raw["brainstormChosenId"])
        if isinstance(raw.get("brainstormNodeIds"), list):
            safe_msg["brainstormNodeIds"] = [str(nid) for nid in raw["brainstormNodeIds"] if str(nid or "").strip()]
        if raw.get("brainstormExecuted"):
            safe_msg["brainstormExecuted"] = bool(raw["brainstormExecuted"])
        # 保留本轮生成的节点 ID，历史重开后「执行/定位」按钮仍能定位本条消息的节点
        if isinstance(raw.get("nodeIds"), list):
            safe_msg["nodeIds"] = [str(nid) for nid in raw["nodeIds"] if str(nid or "").strip()]
        # 保留交互卡片（选择/表单/确认/进度/产物），历史重开后选项卡可重建
        if isinstance(raw.get("interaction"), dict):
            safe_msg["interaction"] = raw["interaction"]
        # 保留本轮加载的技能名，历史重开仍可见
        if isinstance(raw.get("loadedSkills"), list):
            safe_msg["loadedSkills"] = [str(s) for s in raw["loadedSkills"] if str(s or "").strip()]
        messages.append(safe_msg)
    if not messages:
        return None
    return {
        "id": session_id,
        "title": str(item.get("title") or "").strip() or "新对话",
        "updatedAt": int(item.get("updatedAt") or int(time.time() * 1000)),
        "messages": messages,
        "lastReply": str(item.get("lastReply") or "").strip(),
        "lastReplyRefs": item.get("lastReplyRefs") if isinstance(item.get("lastReplyRefs"), list) else [],
    }


def read_canvas_agent_history(canvas_id=""):
    path = canvas_agent_history_path(canvas_id)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        normalized = normalize_canvas_agent_history_item(item)
        if normalized:
            result.append(normalized)
    result.sort(key=lambda item: int(item.get("updatedAt") or 0), reverse=True)
    return result[:24]


def write_canvas_agent_history(canvas_id="", history_list=None):
    path = canvas_agent_history_path(canvas_id)
    normalized = []
    for item in history_list or []:
        safe_item = normalize_canvas_agent_history_item(item)
        if safe_item:
            normalized.append(safe_item)
    normalized.sort(key=lambda item: int(item.get("updatedAt") or 0), reverse=True)
    normalized = normalized[:24]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return normalized


def canvas_agent_history_canvas_title(canvas_id="", fallback=""):
    title = str(fallback or "").strip()
    if title:
        return title
    safe_id = str(canvas_id or "").strip()
    if not safe_id:
        return "默认画布"
    canvas_path = _USER_DATA_DIR / "data" / "canvases" / f"{safe_id}.json"
    try:
        data = json.loads(canvas_path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    return str(data.get("title") or safe_id).strip() or safe_id


def canvas_agent_history_index_entries_for_canvas(canvas_id="", history_list=None, canvas_title=""):
    safe_canvas_id = str(canvas_id or "").strip()
    resolved_title = canvas_agent_history_canvas_title(safe_canvas_id, canvas_title)
    entries = []
    for item in history_list or []:
        if not isinstance(item, dict):
            continue
        messages = item.get("messages") or []
        entries.append({
            "entry_id": f"{safe_canvas_id}::{str(item.get('id') or '').strip()}",
            "canvas_id": safe_canvas_id,
            "canvas_title": resolved_title,
            "session_id": str(item.get("id") or "").strip(),
            "title": str(item.get("title") or "").strip() or "新对话",
            "updatedAt": int(item.get("updatedAt") or 0),
            "message_count": len(messages) if isinstance(messages, list) else 0,
            "lastReply": str(item.get("lastReply") or "").strip(),
        })
    return [entry for entry in entries if entry["session_id"]]


def normalize_canvas_agent_history_index_entry(entry):
    if not isinstance(entry, dict):
        return None
    canvas_id = str(entry.get("canvas_id") or "").strip()
    session_id = str(entry.get("session_id") or "").strip()
    if not session_id:
        return None
    return {
        "entry_id": str(entry.get("entry_id") or f"{canvas_id}::{session_id}").strip() or f"{canvas_id}::{session_id}",
        "canvas_id": canvas_id,
        "canvas_title": str(entry.get("canvas_title") or canvas_agent_history_canvas_title(canvas_id)).strip() or canvas_agent_history_canvas_title(canvas_id),
        "session_id": session_id,
        "title": str(entry.get("title") or "").strip() or "新对话",
        "updatedAt": int(entry.get("updatedAt") or 0),
        "message_count": int(entry.get("message_count") or 0),
        "lastReply": str(entry.get("lastReply") or "").strip(),
    }


def write_canvas_agent_history_index(entries=None):
    normalized = []
    for entry in entries or []:
        safe_entry = normalize_canvas_agent_history_index_entry(entry)
        if safe_entry:
            normalized.append(safe_entry)
    normalized.sort(key=lambda item: int(item.get("updatedAt") or 0), reverse=True)
    _CFG_HISTORY_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CFG_HISTORY_INDEX_FILE.write_text(json.dumps(normalized[:400], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return normalized[:400]


def rebuild_canvas_agent_history_index():
    entries = []
    try:
        files = list(_CFG_HISTORY_DIR.glob("*.json"))
    except Exception:
        files = []
    for path in files:
        if path.name == _CFG_HISTORY_INDEX_FILE.name:
            continue
        canvas_id = path.stem
        entries.extend(canvas_agent_history_index_entries_for_canvas(canvas_id, read_canvas_agent_history(canvas_id)))
    return write_canvas_agent_history_index(entries)


_CANVAS_LIFECYCLE_CACHE = {}  # canvas_id -> (mtime, exists, deleted)


def canvas_lifecycle_state(canvas_id):
    """画布文件存活状态（exists / 是否回收站 deleted）。带 mtime 缓存，供历史索引过滤孤儿会话。"""
    safe_id = str(canvas_id or "").strip()
    if not safe_id or safe_id == "default":
        # 空 canvas_id / default = 默认画布与全局桥接会话，永远保留
        return (True, False)
    path = _USER_DATA_DIR / "data" / "canvases" / f"{safe_id}.json"
    try:
        stat_mtime = path.stat().st_mtime if path.exists() else -1
    except Exception:
        stat_mtime = -1
    cached = _CANVAS_LIFECYCLE_CACHE.get(safe_id)
    if cached and cached[0] == stat_mtime:
        return (cached[1], cached[2])
    exists = stat_mtime >= 0
    deleted = False
    if exists:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            deleted = bool(data.get("deleted_at"))
        except Exception:
            deleted = False
    _CANVAS_LIFECYCLE_CACHE[safe_id] = (stat_mtime, exists, deleted)
    return (exists, deleted)


def prune_canvas_agent_history_files(canvas_id):
    """画布被彻底删除(purge)时联动清掉它的 Agent 对话历史文件与索引条目。"""
    safe_id = str(canvas_id or "").strip()
    if not safe_id:
        return False
    removed = False
    path = canvas_agent_history_path(safe_id)
    try:
        if path.exists():
            path.unlink()
            removed = True
    except Exception as exc:
        append_log(_log_file(), f"prune canvas agent history failed canvas={safe_id}: {exc}")
    try:
        sync_canvas_agent_history_index(safe_id, [])
    except Exception as exc:
        append_log(_log_file(), f"sync history index after prune failed canvas={safe_id}: {exc}")
    _CANVAS_LIFECYCLE_CACHE.pop(safe_id, None)
    return removed


def read_canvas_agent_history_index():
    try:
        raw = json.loads(_CFG_HISTORY_INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return rebuild_canvas_agent_history_index()
    if not isinstance(raw, list):
        return rebuild_canvas_agent_history_index()
    result = []
    for entry in raw:
        safe_entry = normalize_canvas_agent_history_index_entry(entry)
        if not safe_entry:
            continue
        # 孤儿过滤：画布已进回收站或被 purge 时，它的历史不再出现在「其他画布最近对话」；
        # 回收站恢复后自动重新可见（历史文件只在 purge 时才被删）。
        exists, deleted = canvas_lifecycle_state(safe_entry.get("canvas_id") or "")
        if not exists or deleted:
            continue
        result.append(safe_entry)
    result.sort(key=lambda item: int(item.get("updatedAt") or 0), reverse=True)
    return result[:400]


def sync_canvas_agent_history_index(canvas_id="", history_list=None, canvas_title=""):
    safe_canvas_id = str(canvas_id or "").strip()
    current = [entry for entry in read_canvas_agent_history_index() if entry.get("canvas_id") != safe_canvas_id]
    current.extend(canvas_agent_history_index_entries_for_canvas(safe_canvas_id, history_list, canvas_title))
    return write_canvas_agent_history_index(current)


