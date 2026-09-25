# -*- coding: utf-8 -*-
"""chat / agent-models 域（后端拆分第28刀自 rh_official_proxy.py 逐字外移）：
媒体 URL 双向换算、聊天消息规整、codex-local 上游解析、chat target 解析、
Agent 模型清单拉取。值型全局走 getter 闭包（LOG_FILE 被 write_app_config
重绑，禁值注入）；跨域函数直引属主模块。"""
import os
import re
import json
from pathlib import Path
import base64
import time
import shutil
import mimetypes
import urllib.parse
import io
import myridtv_http
import myridtv_core
import myridtv_provider
import myridtv_agent
import myridtv_volcengine
import myridtv_agent_generation

_G_USER_DATA_DIR = lambda: None
_G_ASSETS_DIR = lambda: None
_G_LOG_FILE = lambda: None
_G_CODEX_LOCAL_UPSTREAMS = lambda: None
_G_CODEX_LOCAL_DEFAULT_MODEL = lambda: None
_r_read_chat_key = lambda *a, **k: None
_r_resolve_agent_entry = lambda *a, **k: None


def configure(getters, closures):
    global _G_USER_DATA_DIR, _G_ASSETS_DIR, _G_LOG_FILE
    global _G_CODEX_LOCAL_UPSTREAMS, _G_CODEX_LOCAL_DEFAULT_MODEL
    global _r_read_chat_key, _r_resolve_agent_entry
    _G_USER_DATA_DIR = getters['USER_DATA_DIR']
    _G_ASSETS_DIR = getters['ASSETS_DIR']
    _G_LOG_FILE = getters['LOG_FILE']
    _G_CODEX_LOCAL_UPSTREAMS = getters['CODEX_LOCAL_UPSTREAMS']
    _G_CODEX_LOCAL_DEFAULT_MODEL = getters['CODEX_LOCAL_DEFAULT_MODEL']
    _r_read_chat_key = closures['read_chat_key']
    _r_resolve_agent_entry = closures['resolve_agent_entry']


# 块内主文件残留函数跨域调用改写：read_chat_key(/resolve_agent_entry( → _r_ 前缀
def canvas_source_url_for_media_url(url):
    target = str(url or "").strip()
    if not target:
        return ""
    clean_target = target.split("?", 1)[0].split("#", 1)[0]
    canvases_dir = _G_USER_DATA_DIR() / "data" / "canvases"
    try:
        files = list(canvases_dir.glob("*.json"))
    except Exception:
        files = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in data.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            for image in node.get("images") or []:
                if not isinstance(image, dict):
                    continue
                image_url = str(image.get("url") or "").strip()
                if not image_url:
                    continue
                clean_image_url = image_url.split("?", 1)[0].split("#", 1)[0]
                if target in (image_url, clean_image_url) or clean_target in (image_url, clean_image_url):
                    source_url = str(image.get("source_url") or image.get("sourceUrl") or "").strip()
                    if re.match(r"^https?://", source_url, re.I):
                        return source_url
    return ""


def chat_media_url_to_model_url(url):
    text = str(url or "").strip()
    if not text:
        return ""
    if text.lower().startswith("data:image/") or re.match(r"^https?://", text, re.I):
        return text

    clean = text.split("?", 1)[0].split("#", 1)[0]
    source_url = canvas_source_url_for_media_url(text) or canvas_source_url_for_media_url(clean)
    if source_url:
        return source_url

    local_path = None
    if clean.startswith("/assets/"):
        rel = urllib.parse.unquote(clean[len("/assets/"):].lstrip("/"))
        local_path = _G_ASSETS_DIR() / rel
    elif clean.startswith("assets/"):
        rel = urllib.parse.unquote(clean[len("assets/"):].lstrip("/"))
        local_path = _G_ASSETS_DIR() / rel
    else:
        candidate = Path(urllib.parse.unquote(clean))
        if candidate.is_absolute():
            local_path = candidate

    if local_path:
        try:
            resolved = local_path.resolve()
            user_root = _G_USER_DATA_DIR().resolve()
            assets_root = _G_ASSETS_DIR().resolve()
            # Only inline local files from the MyridTV data dir, the assets dir (资产根已迁到安装目录 D:\APP\MyridTV\assets，2026-09 迁移后这里必须同步放行，否则画布节点图全部静默不内联、Agent 读图=瞎猜), or explicit absolute files.
            if resolved.exists() and (str(resolved).startswith(str(user_root)) or str(resolved).startswith(str(assets_root)) or Path(clean).is_absolute()):
                mime_type = mimetypes.guess_type(str(resolved))[0] or "image/png"
                if not mime_type.startswith("image/"):
                    return ""
                raw = resolved.read_bytes()
                data = raw
                # 压缩大图，控制上下文 token 用量（最长边 1280 / JPEG 82）
                # 2048 时一张 2K 输出图≈21万 token；1280 对"看图理解/风格判断"足够，token 降约 60%
                try:
                    from PIL import Image
                    if len(raw) > 256 * 1024:
                        img = Image.open(io.BytesIO(raw))
                        img.thumbnail((1280, 1280), Image.LANCZOS)
                        if img.mode in ("RGBA", "LA", "P", "L"):
                            out = io.BytesIO()
                            img.save(out, format="PNG", optimize=True)
                            mime_type = "image/png"
                        else:
                            out = io.BytesIO()
                            img.convert("RGB").save(out, format="JPEG", quality=82)
                            mime_type = "image/jpeg"
                        data = out.getvalue()
                except Exception:
                    data = raw
                if len(data) > 3 * 1024 * 1024:
                    # 压缩后仍过大：跳过内联，避免上下文超限
                    myridtv_core.append_log(_G_LOG_FILE(), f"agent image inline skipped oversized url={text} bytes={len(data)}")
                    return ""
                encoded = base64.b64encode(data).decode("ascii")
                return f"data:{mime_type};base64,{encoded}"
        except Exception as exc:
            myridtv_core.append_log(_G_LOG_FILE(), f"agent image inline failed url={text}: {exc}")
            return ""
    return text


def _agent_canvas_node_image_by_id(node_id, image_index=0):
    """按画布节点 id 反查节点图片的真实本地路径/url。

    画布内图片名可能与本地文件名不一致（用户 @ 时前端传的 url 可能是画布内名），
    用 nodeId 直接找画布节点，取节点图片的真实文件（local_path / url 解析）。
    返回：本地存在的绝对路径，或 /assets/ 相对 url，找不到返回 None。
    """
    node_id = str(node_id or "").strip()
    if not node_id:
        return None
    canvases_dir = _G_USER_DATA_DIR() / "data" / "canvases"
    try:
        files = list(canvases_dir.glob("*.json"))
    except Exception:
        files = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in data.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            if str(node.get("id") or "") != node_id:
                continue
            images = node.get("images") or []
            try:
                idx = int(image_index or 0)
            except Exception:
                idx = 0
            if not images or idx >= len(images):
                return None
            img = images[idx]
            if not isinstance(img, dict):
                return None
            local_path = str(img.get("local_path") or "").strip()
            if local_path and os.path.exists(local_path):
                return local_path
            url = str(img.get("url") or "").strip()
            if url:
                local = myridtv_agent_generation._agent_local_path_for_url(url)
                if local and os.path.exists(local):
                    return local
                return url
    return None


def payload_image_content_blocks(payload):
    blocks = []
    seen = set()
    raw_images = payload.get("images") or payload.get("image_urls") or []
    if isinstance(raw_images, (str, dict)):
        raw_images = [raw_images]
    for item in (raw_images[:4] if isinstance(raw_images, list) else raw_images if isinstance(raw_images, (str, dict)) else []):
        if isinstance(item, dict):
            raw_url = item.get("source_url") or item.get("sourceUrl") or item.get("url") or item.get("path") or ""
            # 画布内图片名可能≠本地文件名：用 nodeId 反查画布节点取真实图片路径
            node_id = str(item.get("nodeId") or item.get("node_id") or "").strip()
            if node_id:
                node_img = _agent_canvas_node_image_by_id(node_id, item.get("imageIndex"))
                if node_img:
                    raw_url = node_img
        else:
            raw_url = item
        model_url = chat_media_url_to_model_url(raw_url)
        if not model_url or model_url in seen:
            continue
        seen.add(model_url)
        blocks.append({"type": "image_url", "image_url": {"url": model_url}})
    return blocks


def normalize_chat_messages(payload):
    messages = []
    system_prompt = myridtv_agent.canvas_agent_augmented_system_prompt(payload)
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for item in payload.get("messages") or payload.get("history") or []:
        if not isinstance(item, dict):
            continue
        role = item.get("role") if item.get("role") in ("system", "user", "assistant") else "user"
        content = item.get("content") or item.get("text") or ""
        if str(content).strip():
            messages.append({"role": role, "content": str(content)})
    message = str(payload.get("message") or "").strip()
    image_blocks = payload_image_content_blocks(payload)
    if message or image_blocks:
        if image_blocks:
            content = []
            if message:
                content.append({"type": "text", "text": message})
            content.extend(image_blocks)
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": message})
    if not messages:
        raise RuntimeError("消息为空")
    return messages


def is_codex_local_upstream(value):
    text = str(value or "").strip().lower().rstrip("/")
    return text in _G_CODEX_LOCAL_UPSTREAMS()


def codex_local_model_choices():
    models = [_G_CODEX_LOCAL_DEFAULT_MODEL(), "gpt-5.5", "gpt-5.4-mini"]
    config_path = Path.home() / ".codex" / "config.toml"
    try:
        raw = config_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        raw = ""
    match = re.search(r'(?m)^\s*model\s*=\s*"([^"]+)"', raw)
    if match:
        model = str(match.group(1) or "").strip()
        if model and model not in models:
            models.append(model)
    return models


def resolve_codex_executable():
    env_candidates = [
        os.environ.get("MYRIDTV_CODEX_EXE"),
        os.environ.get("CODEX_EXE"),
    ]
    for raw in env_candidates:
        text = str(raw or "").strip().strip('"')
        if text and Path(text).exists():
            return text
    for name in ("codex", "codex.exe"):
        found = shutil.which(name)
        if found:
            return found
    local_appdata = Path(os.environ.get("LOCALAPPDATA") or "")
    if local_appdata:
        alias_path = local_appdata / "Microsoft" / "WindowsApps" / "codex.exe"
        if alias_path.exists():
            return str(alias_path)
    windows_apps = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "WindowsApps"
    if windows_apps.exists():
        matches = sorted(
            windows_apps.glob("OpenAI.Codex_*_x64__*/app/resources/codex.exe"),
            key=lambda path: str(path),
            reverse=True,
        )
        if matches:
            return str(matches[0])
    raise RuntimeError(
        "未找到 Codex 可执行文件。请确认 Codex 桌面应用已安装，"
        "或设置环境变量 MYRIDTV_CODEX_EXE 指向 codex.exe。"
    )


def payload_prefers_codex_local(payload):
    agent_id, entry = _r_resolve_agent_entry((payload or {}).get("agent_id"))
    upstream_base = str((payload or {}).get("upstream_base_url") or entry.get("upstream_base_url") or "").strip()
    return is_codex_local_upstream(upstream_base)


def resolve_chat_target(payload):
    agent_id, entry = _r_resolve_agent_entry(payload.get("agent_id"))
    provider_id = str(payload.get("provider") or payload.get("provider_id") or entry.get("provider_id") or "").strip()
    model = str(payload.get("model") or entry.get("model") or "").strip()
    upstream_base = str(payload.get("upstream_base_url") or "").strip().rstrip("/")
    # Agent 复用自定义平台：优先用所选平台的请求地址（平台是地址/Key 的唯一来源）。
    if not upstream_base and provider_id:
        try:
            for provider in myridtv_provider.read_api_providers():
                if str(provider.get("id") or "") == provider_id:
                    upstream_base = str(provider.get("base_url") or "").strip().rstrip("/")
                    if upstream_base:
                        break
        except Exception:
            pass
    # 兼容旧配置（如 codex://local 桥接地址）。
    if not upstream_base:
        upstream_base = str(entry.get("upstream_base_url") or "").strip().rstrip("/")
    agent_label = str(entry.get("name") or agent_id or "Agent")
    if not model:
        raise RuntimeError(f"Agent「{agent_label}」未配置模型，请先在 API 设置里选择聊天模型。")
    if not upstream_base:
        raise RuntimeError(f"Agent「{agent_label}」未选择 LLM 平台，请先在 API 设置里选择自定义平台。")
    key = _r_read_chat_key(provider_id, entry)
    if not key:
        raise RuntimeError(f"未找到 Agent「{agent_label}」所用平台的 API Key，请先在该平台配置中保存 API Key。")
    myridtv_core.append_log(_G_LOG_FILE(), "agent chat target agent_id={} provider={} model={} upstream={} key_tail={}".format(
        agent_id, provider_id, model, upstream_base, key[-4:] if key else ""))
    return provider_id, model, upstream_base, key


def fetch_agent_models(payload=None):
    payload = payload if isinstance(payload, dict) else {}
    _, entry = _r_resolve_agent_entry(payload.get("agent_id"))
    provider_id = str(payload.get("provider") or payload.get("provider_id") or entry.get("provider_id") or "").strip()
    upstream_base = str(payload.get("upstream_base_url") or entry.get("upstream_base_url") or "").strip().rstrip("/")
    if is_codex_local_upstream(upstream_base):
        models = codex_local_model_choices()
        return {
            "ok": True,
            "all": models,
            "chat_models": models,
            "model_count": len(models),
            "total": len(models),
            "source": "codex://local",
        }
    # Agent 复用自定义平台：未显式给上游地址时，从所选平台读取地址和 Key。
    if not upstream_base and provider_id:
        try:
            for provider in myridtv_provider.read_api_providers():
                if str(provider.get("id") or "") == provider_id:
                    upstream_base = str(provider.get("base_url") or "").strip().rstrip("/")
                    if upstream_base:
                        break
        except Exception:
            pass
    if not upstream_base:
        raise RuntimeError("Agent 未选择 LLM 平台，请先在 API 设置里选择自定义平台。")
    key = str(payload.get("api_key") or "").strip() or _r_read_chat_key(provider_id, entry)
    if not key:
        raise RuntimeError("所选平台未保存 API Key，请先在该平台配置中填写并保存 API Key。")
    saved_models = []
    try:
        saved_models = list(entry.get("chat_models") or [])
    except Exception:
        saved_models = []
    try:
        for provider in myridtv_provider.read_api_providers():
            if str(provider.get("id") or "") == provider_id:
                saved_models = list(provider.get("chat_models") or []) + saved_models
                break
    except Exception:
        pass
    saved_models = myridtv_core.unique_strings([str(m) for m in saved_models if str(m or "").strip()])
    if myridtv_volcengine.is_volcengine_plan_base(upstream_base):
        models = myridtv_volcengine.volcengine_plan_chat_models(saved_models)
        return {
            "ok": True,
            "all": models,
            "chat_models": models,
            "model_count": len(models),
            "total": len(models),
            "source": "volcengine-plan-builtin",
            "message": "火山推理计划(plan)端点不提供在线模型列表，已使用后端内置模型清单，可直接在下拉中选择。",
        }
    urls = [f"{upstream_base}/models"]
    if not upstream_base.endswith("/v1"):
        urls.append(f"{upstream_base}/v1/models")
    last_error = None
    data = None
    source = urls[0]
    for url in urls:
        try:
            data = myridtv_http.request_json(url, "GET", headers={"Authorization": f"Bearer {key}"}, timeout=30)
            source = url
            break
        except Exception as exc:
            last_error = exc
    is_plan_endpoint = "/api/plan/" in upstream_base
    if data is None or is_plan_endpoint:
        if saved_models:
            return {
                "ok": True,
                "all": saved_models,
                "chat_models": saved_models,
                "model_count": len(saved_models),
                "total": len(saved_models),
                "source": "saved",
                "message": (
                    "该端点不提供模型列表（如火山推理计划 plan 端点），已显示已保存的模型；也可直接在模型框输入模型名。"
                    if is_plan_endpoint
                    else "未能实时拉取模型列表，已回退显示已保存的模型；也可直接在模型框输入模型名。"
                ),
            }
        if is_plan_endpoint:
            return {
                "ok": True,
                "all": [],
                "chat_models": [],
                "model_count": 0,
                "total": 0,
                "source": "plan-endpoint",
                "message": "火山推理计划 plan 端点不提供模型列表，请直接在模型框输入模型名（如 deepseek-v4-flash）后保存。",
            }
        raise last_error or RuntimeError("上游模型列表请求失败")
    raw_models = data.get("data") if isinstance(data, dict) else []
    models = myridtv_core.unique_strings([
        str(item.get("id") or "").strip()
        for item in (raw_models or [])
        if isinstance(item, dict) and item.get("id")
    ])
    if not models:
        if saved_models:
            return {"ok": True, "all": saved_models, "chat_models": saved_models, "model_count": len(saved_models), "total": len(saved_models), "source": "saved",
                    "message": "上游未返回模型列表，已回退显示已保存的模型；也可直接在模型框输入模型名。"}
        raise RuntimeError("上游未返回可用模型")
    return {"ok": True, "all": models, "chat_models": models, "model_count": len(models), "total": len(models), "source": source}

def is_retryable_chat_error(exc):
    text = str(exc)
    return any(token in text.lower() for token in (
        "unexpected_eof",
        "eof occurred",
        "ssl",
        "timed out",
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "remote end closed",
        "http 502",
        "http 503",
        "http 504",
    ))


def request_chat_json_with_retry(url, body, headers, attempts=3, timeout=120):
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            if attempt > 1:
                myridtv_core.append_log(_G_LOG_FILE(), f"agent chat retry attempt={attempt} url={url}")
            return myridtv_http.request_json(url, "POST", body, headers, timeout=timeout)
        except Exception as exc:
            last_exc = exc
            retryable = is_retryable_chat_error(exc)
            myridtv_core.append_log(_G_LOG_FILE(), f"agent chat attempt={attempt} failed retryable={retryable}: {exc}")
            if not retryable or attempt >= attempts:
                break
            time.sleep(min(1.5 * attempt, 4))
    raise RuntimeError(f"Agent 上游请求被中断，已重试 {attempts} 次仍失败：{last_exc}") from last_exc
