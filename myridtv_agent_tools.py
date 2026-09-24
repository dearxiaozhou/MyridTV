# -*- coding: utf-8 -*-
"""MyridTV Agent 工具层（后端拆分第13刀B）：图片分析工具（modlens 双级缓存）、
技能保存/列表工具、交互卡片呈现与领取（present_interaction/take_pending）、
工具 schema 表 CANVAS_AGENT_TOOLS、会话/交互登记单例。

逐字迁移自 rh_official_proxy.py 连续块 L(_modlens_cache_key_file)..L(canvas_agent_
execute_tool)（8 函数 + 5 顶层定义 388 行，可逆还原行级 diff=0）。行为零变更。
configure() 注入：MODLENS_CACHE/MODLENS_CACHE_DIR/MODLENS_CACHE_KEY_MAX 同对象
（零重绑）、_agent_get_canvas/_agent_local_path_for_url 闭包；技能三函数直引
myridtv_agent。CANVAS_AGENT_INTERACTIONS/LOCK/CURRENT_SESSION 单例与
CANVAS_AGENT_TOOLS 表归本模块，主文件别名再导出（同对象，块外 10/3/1/1 处读写
跨模块互见）。LOADED_SKILLS 仍归 myridtv_agent（本模块再引）。
"""
import base64
import hashlib
import os
import subprocess
import io
import json
import re
import threading
import time
import uuid

from myridtv_core import ApiError

import myridtv_agent

MODLENS_CACHE = None
MODLENS_CACHE_DIR = None
MODLENS_CACHE_KEY_MAX = 0
_r_agent_get_canvas = None
_r_agent_local_path_for_url = None


def configure(modlens_cache, modlens_cache_dir, modlens_cache_key_max,
              agent_get_canvas, agent_local_path_for_url):
    global MODLENS_CACHE, MODLENS_CACHE_DIR, MODLENS_CACHE_KEY_MAX
    global _r_agent_get_canvas, _r_agent_local_path_for_url
    MODLENS_CACHE = modlens_cache
    MODLENS_CACHE_DIR = modlens_cache_dir
    MODLENS_CACHE_KEY_MAX = modlens_cache_key_max
    _r_agent_get_canvas = agent_get_canvas
    _r_agent_local_path_for_url = agent_local_path_for_url


def _modlens_cache_key_file(cache_key):
    """把缓存键（图片路径|prompt）映射成安全文件名：长键哈希截断。"""
    try:
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:24]
        return MODLENS_CACHE_DIR / (digest + ".json")
    except Exception:
        return None

def _modlens_cache_disk_get(cache_key):
    try:
        f = _modlens_cache_key_file(cache_key)
        if f is None or not f.exists():
            return None
        data = json.loads(f.read_text(encoding="utf-8"))
        return data.get("evidence") if isinstance(data, dict) else None
    except Exception:
        return None

def _modlens_cache_disk_put(cache_key, evidence):
    try:
        f = _modlens_cache_key_file(cache_key)
        if f is None:
            return
        MODLENS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"key": cache_key[:MODLENS_CACHE_KEY_MAX], "evidence": evidence},
                                ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

def _agent_tool_analyze_image(args):
    """用 ModLens 视觉引擎分析画布图片，返回结构化 JSON 证据（OCR/版面/语义）。

    需要本机已安装：npm i -g @liustack/modlens，且配置了任一视觉引擎
    （agy 登录 / Gemini key / OpenAI 兼容端点如 qwen-vl、GLM）。
    同一图片 + 同一 prompt 的结果会缓存（MODLENS_CACHE），重复分析秒回。
    """
    image_url = str(args.get("image_url") or "").strip()
    node_id = str(args.get("node_id") or "").strip()
    if not image_url and node_id:
        cid, canvas = _r_agent_get_canvas(str(args.get("canvas_id") or ""))
        for n in canvas.get("nodes") or []:
            if isinstance(n, dict) and str(n.get("id")) == str(node_id):
                for img in n.get("images") or []:
                    if isinstance(img, dict) and img.get("url"):
                        image_url = str(img["url"]).strip()
                        break
                break
    if not image_url:
        return {"ok": False, "error": "请提供 image_url(图片 /assets/ 路径或本地路径)或 node_id(画布节点 id)"}
    target = image_url
    if str(image_url).startswith("/assets/"):
        local = _r_agent_local_path_for_url(image_url)
        if local:
            target = local
    if not re.match(r"^https?://", str(target)) and not os.path.exists(str(target)):
        return {"ok": False, "error": "图片不存在: {}".format(target)}
    cmd = ["cmd", "/c", "modlens", "-i", str(target)]
    prompt = str(args.get("prompt") or "").strip()
    if prompt:
        cmd += ["--prompt", prompt]
    # 同一图片 + 同一 prompt 缓存结果，重复分析直接秒回（ModLens 单次 40-60s）。
    # 缓存双写内存 + 磁盘文件，代理重启后仍然命中。
    cache_key = "{}|{}".format(str(target), prompt)
    cached = MODLENS_CACHE.get(cache_key)
    if cached is None:
        cached = _modlens_cache_disk_get(cache_key)
        if cached is not None:
            MODLENS_CACHE[cache_key] = cached
    if cached is not None:
        return {
            "ok": True,
            "image": str(target),
            "evidence": cached,
            "cached": True,
            "note": "以上是视觉引擎(ModLens)对图片的结构化分析(全文OCR/版面区块/语义实体与关系,来自缓存)。请基于它理解图片内容并继续;如需要更细可以指定 prompt 再次分析局部。",
        }
    # ModLens/agy 偶发失败：单次执行，超时 75s 快速失败（正常 40-60s，超时不拖分钟级）
    last_detail = ""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=75,
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        last_detail = "看图超时(>75s)"
        return {"ok": False, "error": "看图超时(>75s),请换一张更小的图片后重试"}
    except FileNotFoundError:
        return {"ok": False, "error": "未找到 modlens 命令,请先安装: npm i -g @liustack/modlens"}
    if proc.returncode != 0:
        last_detail = (str(proc.stderr or "") + "\n" + str(proc.stdout or "")).strip()[:500]
        return {"ok": False, "error": "modlens 分析失败: {}".format(last_detail)}
    raw = (proc.stdout or "").strip()
    if not raw:
        last_detail = "modlens 无输出"
        return {"ok": False, "error": "modlens 无输出"}
    evidence = raw[:8000]
    MODLENS_CACHE[cache_key] = evidence
    _modlens_cache_disk_put(cache_key, evidence)
    if len(MODLENS_CACHE) > 300:
        # 简单防膨胀：清掉一半（先进先出）
        for k in list(MODLENS_CACHE.keys())[:150]:
            MODLENS_CACHE.pop(k, None)
    return {
        "ok": True,
        "image": str(target),
        "evidence": evidence,
        "note": "以上是视觉引擎(ModLens)对图片的结构化分析(全文OCR/版面区块/语义实体与关系)。请基于它理解图片内容并继续;如需要更细可以指定 prompt 再次分析局部。",
    }


def _agent_tool_save_skill(args):
    """把对话中提炼的方法/工作流保存为可复用技能，之后用户或自己可 @技能名 调用。"""
    name = str(args.get("name") or "").strip()
    content = str(args.get("content") or "").strip()
    if not name:
        return {"ok": False, "error": "技能名必填"}
    if not content:
        return {"ok": False, "error": "技能内容必填"}
    try:
        saved = myridtv_agent.write_canvas_agent_skill(name, content)
    except ApiError as exc:
        return {"ok": False, "error": exc.detail}
    except Exception as exc:
        return {"ok": False, "error": "保存技能失败: {}".format(exc)}
    return {
        "ok": True,
        "skill": saved,
        "skills": myridtv_agent.list_canvas_agent_skills(),
        "note": "技能已保存。后续对话中可用 @{} 调用它。".format(saved.get("name") or name),
    }


def _agent_tool_list_skills(args):
    """列出已保存的技能（名称/大小/更新时间），避免重名覆盖。"""
    skills = myridtv_agent.list_canvas_agent_skills()
    previews = []
    for skill in skills[:30]:
        try:
            content = myridtv_agent.read_canvas_agent_skill(skill.get("name") or "")
            preview = str(content.get("content") or "").strip().replace("\n", " ")[:120]
        except Exception:
            preview = ""
        previews.append({"name": skill.get("name"), "preview": preview})
    return {"ok": True, "skills": skills, "previews": previews, "count": len(skills)}


# 交互卡片状态：session_id -> {card_id, intent, title, options, fields, default_id, ...}
CANVAS_AGENT_INTERACTIONS = {}
CANVAS_AGENT_INTERACTIONS_LOCK = threading.Lock()
# 当前执行的会话 id（由 submit 入口按 payload.agent_session_id 设置，供画布操作类工具读取）
CANVAS_AGENT_CURRENT_SESSION = {"session_id": ""}
# 本轮实际注入的技能名列表（供前端在回复里展示"加载的技能"）
CANVAS_AGENT_LOADED_SKILLS = myridtv_agent.CANVAS_AGENT_LOADED_SKILLS  # 单例归模块（第3刀）


def _agent_tool_present_interaction(args, session_id=None):
    """向用户展示结构化交互卡片(选择/表单/确认/进度/产物)。
    不执行画布操作,只登记本轮要展示的卡片,由前端按 interaction 字段渲染。"""
    args = args if isinstance(args, dict) else {}
    if not session_id:
        session_id = str(CANVAS_AGENT_CURRENT_SESSION.get("session_id") or "")
    intent = str(args.get("intent") or "choose").strip()
    title = str(args.get("title") or "").strip()
    card_id = "imc_{}".format(uuid.uuid4().hex[:10])
    options = args.get("options") if isinstance(args.get("options"), list) else []
    fields = args.get("fields") if isinstance(args.get("fields"), list) else []
    default_id = str(args.get("default_id") or "").strip()
    # 给每个选项补唯一 id(缺省按 A/B/C),并找默认项
    normalized_options = []
    labels = "ABCDEFGH"
    for idx, opt in enumerate(options):
        if not isinstance(opt, dict):
            continue
        oid = str(opt.get("id") or labels[idx] or ("opt" + str(idx))).strip()
        item = {
            "id": oid,
            "label": str(opt.get("label") or opt.get("title") or oid).strip(),
            "desc": str(opt.get("desc") or "").strip(),
            "default": bool(opt.get("default")),
            "action": str(opt.get("action") or "").strip(),
        }
        if item["default"] and not default_id:
            default_id = oid
        normalized_options.append(item)
    if not default_id and normalized_options:
        default_id = normalized_options[0]["id"]
    # 规范化 collect 字段：把每个字段的 options 归一化成 [{value,label},...]，容错字符串数组/id/label
    normalized_fields = []
    for f in fields or []:
        if not isinstance(f, dict):
            continue
        nf = dict(f)
        ftype = str(f.get("type") or "").strip().lower()
        raw_opts = f.get("options")
        if ftype == "select" and not isinstance(raw_opts, list):
            raw_opts = f.get("choices") or f.get("items") or []
        if ftype == "select" and isinstance(raw_opts, list):
            opts_norm = []
            for o in raw_opts:
                if isinstance(o, str):
                    opts_norm.append({"value": o, "label": o})
                elif isinstance(o, dict):
                    val = o.get("value") if o.get("value") is not None else o.get("id")
                    lab = o.get("label") if o.get("label") is not None else (val if val is not None else "")
                    if val is not None:
                        opts_norm.append({"value": val, "label": lab})
            nf["options"] = opts_norm
        nf["type"] = ftype or "text"
        normalized_fields.append(nf)
    # 精简卡片标题：去掉括号参数串 / 长因子串，只留核心短语（如"确认 Clip 表"）
    title_clean = str(title or "").strip()
    if len(title_clean) > 20 or ("（" in title_clean or "(" in title_clean or "·" in title_clean):
        # 循环按 括号 → 中点 → 冒号 截断，直到只剩核心短语或够短
        for sep in ["（", "(", "·", "：", ":"]:
            idx = title_clean.find(sep)
            if idx > 0:
                title_clean = title_clean[:idx].strip()
                break
        # 若仍含分隔符（如"确认 Clip 表 · 升职潜规则"），再按中点截一次
        for sep in ["（", "(", "·", "：", ":"]:
            idx = title_clean.find(sep)
            if idx > 0:
                title_clean = title_clean[:idx].strip()
                break
        if len(title_clean) > 20:
            title_clean = title_clean[:20].rstrip("，。；,;")
    if not title_clean:
        title_clean = title or "请确认"
    card = {
        "card_id": card_id,
        "intent": intent,
        "title": title_clean,
        "options": normalized_options,
        "fields": normalized_fields,
        "default_id": default_id,
        "allow_custom": bool(args.get("allow_custom")),
        "asset_id": str(args.get("asset_id") or "").strip(),
        "created_at": int(time.time() * 1000),
        "resolved": False,
    }
    try:
        with CANVAS_AGENT_INTERACTIONS_LOCK:
            if session_id:
                CANVAS_AGENT_INTERACTIONS[str(session_id)] = card
    except Exception:
        pass
    return {
        "ok": True,
        "presented": True,
        "card_id": card_id,
        "intent": intent,
        "note": "交互卡片已展示,等待用户回执。本轮应立即结束,不要再发起其他动作。",
    }


def _agent_take_pending_interaction(session_id=""):
    """取出该会话最近一次未解决的交互卡片,供 _build_canvas_agent_result 挂到返回上。"""
    try:
        with CANVAS_AGENT_INTERACTIONS_LOCK:
            card = CANVAS_AGENT_INTERACTIONS.get(str(session_id or ""))
            if isinstance(card, dict) and not card.get("resolved"):
                return card
            return None
    except Exception:
        return None


CANVAS_AGENT_TOOLS = [
    {"type": "function", "function": {
        "name": "canvas_get_state",
        "description": "读取当前 MyridTV 无限画布的状态:画布 id、标题和节点列表(节点类型/标题/文本摘要/图片数量)。开始任务前先用它了解画布上有什么。",
        "parameters": {"type": "object", "properties": {
            "canvas_id": {"type": "string", "description": "画布 id,省略则用最新画布"}
        }}}},
    {"type": "function", "function": {
        "name": "canvas_search_nodes",
        "description": "按关键词搜索画布节点(标题/正文/提示词),返回匹配节点摘要。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "canvas_id": {"type": "string", "description": "画布 id,省略则用最新画布"},
            "limit": {"type": "number", "description": "最大返回数,默认 20"}
        }, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "canvas_create_text_node",
        "description": "在画布上创建文本节点(剧本、脚本、设定、方案等)。",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "文本内容"},
            "title": {"type": "string", "description": "节点标题"},
            "section_title": {"type": "string", "description": "头脑风暴板块名(如 核心人物/故事设定/关键场面/世界观)。同一会话同一板块会合并更新,不会重复新建"},
            "section_type": {"type": "string", "enum": ["character", "story", "scene", "world", "visual", "direction", "custom"], "description": "板块类型,不给则按 section_title 自动推断"},
            "item_title": {"type": "string", "description": "板块内的条目名(如 林澜/司徒岳/方案A),板块只有一个条目时留空"},
            "x": {"type": "number"}, "y": {"type": "number"},
            "canvas_id": {"type": "string"}
        }, "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "canvas_create_generation_node",
        "description": "在画布上建立图片生成节点：把提示词、引用的图片和当前生图预设同步到节点，节点进入待生成状态。返回 node_id。生成不在此工具内执行——用户会在画布节点上点执行按钮生成，或必要时再用 canvas_generate_images。",
        "parameters": {"type": "object", "properties": {
            "prompt": {"type": "string", "description": "图片生成提示词(中文,含主体/环境/构图/光线/风格)"},
            "title": {"type": "string", "description": "节点标题,如 '苏焰 特写'"},
            "reference_image_urls": {"type": "array", "items": {"type": "string"}, "description": "参考图:画布节点图片的 /assets/ 路径或本地路径,可为空"},
            "aspect_ratio": {"type": "string", "description": "比例:人物/竖版 3:4,场景/横版 4:3,其他 1:1/16:9/9:16"},
            "resolution": {"type": "string", "description": "1k/2k/4k,默认 2k"},
            "size": {"type": "string", "description": "像素尺寸,如 2048x1536,默认按比例"},
            "model": {"type": "string", "description": "生成模型；默认使用 API 设置里当前生图平台配置的模型，不要填写未配置的模型"},
            "canvas_id": {"type": "string"}
        }, "required": ["prompt"]}}},
    {"type": "function", "function": {
        "name": "canvas_generate_images",
        "description": "（通常不需要）立即生成图片并回填节点，会阻塞等待任务完成。仅在用户明确要求马上出图时才使用；常规流程用 canvas_create_generation_node 建好节点后由用户在画布上点执行按钮生成。",
        "parameters": {"type": "object", "properties": {
            "prompt": {"type": "string", "description": "图片生成提示词"},
            "node_id": {"type": "string", "description": "已创建的生成节点 id(用 canvas_create_generation_node 得到)"},
            "aspect_ratio": {"type": "string", "description": "比例:人物/竖版 3:4,场景/横版 4:3"},
            "resolution": {"type": "string", "description": "1k/2k/4k,默认 2k"},
            "size": {"type": "string"},
            "model": {"type": "string"},
            "reference_image_urls": {"type": "array", "items": {"type": "string"}, "description": "参考图:画布节点图片的 /assets/ 路径或本地路径,也可为空"},
            "canvas_id": {"type": "string"}
        }, "required": ["prompt"]}}},
    {"type": "function", "function": {
        "name": "canvas_check_generation",
        "description": "查询生图任务状态。succeeded 时结果已回填节点;running 时请稍后再次调用;failed 时修改提示词重试。",
        "parameters": {"type": "object", "properties": {
            "task_id": {"type": "string", "description": "生图任务 id"},
            "node_id": {"type": "string", "description": "要回填的节点 id"},
            "canvas_id": {"type": "string"}
        }, "required": ["task_id"]}}},
    {"type": "function", "function": {
        "name": "canvas_update_node",
        "description": "更新画布节点的文本或标题。",
        "parameters": {"type": "object", "properties": {
            "node_id": {"type": "string"},
            "text": {"type": "string"}, "title": {"type": "string"},
            "canvas_id": {"type": "string"}
        }, "required": ["node_id"]}}},
    {"type": "function", "function": {
        "name": "canvas_batch_operations",
        "description": "对画布执行一批标准化操作(原子性:任一操作失败全部回滚,返回 batch_id 供撤销)。op_type 只允许:add_node(新增节点,params.node_type=text/generation)、update_node、delete_node、add_link(params.from_id/to_id)、delete_link、set_variable(params.name/value)、layer_operate(params.action=show/hide/front/back)。LLM 禁止生成节点 id,新增节点 id 由软件分配;引用已有节点必须用画布上真实存在的 id。适合:一次创建多个节点并连线、整理画布、批量修改。",
        "parameters": {"type": "object", "properties": {
            "operations": {"type": "array", "items": {"type": "object"}, "description": "操作数组,每项 {op_type, target_id, params}"},
            "canvas_id": {"type": "string"}
        }, "required": ["operations"]}}},
    {"type": "function", "function": {
        "name": "canvas_undo_batch",
        "description": "一键撤销某次 canvas_batch_operations 的全部变更(恢复执行前快照)。",
        "parameters": {"type": "object", "properties": {
            "batch_id": {"type": "string", "description": "canvas_batch_operations 返回的 batch_id"}
        }, "required": ["batch_id"]}}},
    {"type": "function", "function": {
        "name": "canvas_add_link",
        "description": "在两个节点之间创建连线(from→to)。",
        "parameters": {"type": "object", "properties": {
            "from_id": {"type": "string", "description": "起点节点 id(输出方)"},
            "to_id": {"type": "string", "description": "终点节点 id(输入方)"},
            "canvas_id": {"type": "string"}
        }, "required": ["from_id", "to_id"]}}},
    {"type": "function", "function": {
        "name": "canvas_delete_node",
        "description": "删除画布节点及其相关连线。",
        "parameters": {"type": "object", "properties": {
            "node_id": {"type": "string"},
            "canvas_id": {"type": "string"}
        }, "required": ["node_id"]}}},
    {"type": "function", "function": {
        "name": "canvas_list_skills",
        "description": "列出已保存的技能(名称/更新时间/内容预览),避免重名覆盖。保存新技能前先调用它检查是否已有同名技能。",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "canvas_save_skill",
        "description": "把对话中提炼的方法/工作流/风格偏好保存为可复用技能,之后对话中用 @技能名 调用。当用户教你一套方法、或你在本次对话中总结出可复用的创作流程时,主动调用它保存。同名会覆盖,保存前建议先用 canvas_list_skills 查看。",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "技能名(短、便于 @ 调用),如 '电商套图' '国风海报'"},
            "content": {"type": "string", "description": "技能内容:可复用的方法步骤/提示词模板/风格偏好,上限 24576 字符"}
        }, "required": ["name", "content"]}}},
    {"type": "function", "function": {
        "name": "present_im_interaction",
        "description": "向用户展示一个结构化交互卡片,请求用户点击/选择/确认。用于需要用户决策的等待点:有限方向选一(choose)、缺已知参数收集(collect)、高成本动作前确认(confirm)、长任务进度(progress)、最终产物交付(artifact)。一卡一决策,发出后本轮立即结束等待用户回执。卡片是唯一的决策入口,禁止用正文编号/打字代替。",
        "parameters": {"type": "object", "properties": {
            "intent": {"type": "string", "enum": ["choose", "collect", "confirm", "progress", "artifact"], "description": "卡片类型"},
            "title": {"type": "string", "description": "卡片标题,一句说明这次要用户做什么"},
            "options": {"type": "array", "items": {"type": "object"}, "description": "choose/confirm 用:选项数组,每项 {id, label, desc?, default?, action?}。id 交互内唯一;default 选项预选中;action 写选中后进入哪个阶段"},
            "fields": {"type": "array", "items": {"type": "object"}, "description": "collect 用:字段数组,每项 {key, label, type(select/text/textarea/upload), options?, required?, default?, allow_skip?}"},
            "default_id": {"type": "string", "description": "choose/confirm 预选选项 id,不传则用 options 里 default=true 的项"},
            "asset_id": {"type": "string", "description": "progress/artifact 用:关联的真实产物 id"},
            "allow_custom": {"type": "boolean", "description": "choose 是否允许混搭/自己调整的逃生项,默认 false"}
        }, "required": ["intent", "title"]}}},
]


