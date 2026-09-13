import base64
import ctypes
import ctypes.wintypes
import hashlib
import io
import json
import mimetypes
import math
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from websockets.sync.client import connect as ws_connect

import comfy_flow_service
import agent_task_runtime as agent_runtime
import task_store
from myridtv_core import (
    ApiError,
    CanvasConflictError,
    read_json_file,
    write_json_file,
    append_log,
    parse_number,
    parse_positive_int,
    deep_merge,
    unique_strings,
    mask_secret,
    clean_asset_name,
    clean_prompt_name,
    safe_agent_skill_name,
    default_asset_library,
    default_prompt_library,
    _task_console_ts,
)
from comfy_flow_compiler import CompileError as ComfyCompileError
from comfy_flow_compiler import compile_prompt as compile_comfy_prompt
from comfy_flow_compiler import describe_workflow as describe_comfy_workflow

# Keep the local app independent from system proxy applications. Remote API
# calls use a direct connection by default; opt in with MYRIDTV_USE_EXTERNAL_PROXY=1.
if os.environ.get("MYRIDTV_USE_EXTERNAL_PROXY", "0").strip().lower() not in {"1", "true", "yes", "on"}:
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))


# ============================================
# 窗口样式自动修复（修复 frameless 窗口的缩放/拖动/系统菜单问题）
# ============================================

def _fix_window_style_worker():
    """后台线程：等待主窗口出现并自动修复样式"""
    # Windows API 常量
    GWL_STYLE = -16
    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_SYSMENU = 0x00080000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000
    WS_POPUP = 0x80000000
    WS_OVERLAPPEDWINDOW = 0x00CF0000
    
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_FRAMECHANGED = 0x0020
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    
    def find_window():
        found = []
        def enum_callback(hwnd, lparam):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                title = buf.value.lower()
                if 'myridtv' in title or 'wcstv' in title:
                    found.append((hwnd, buf.value))
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        return found
    
    def fix_window(hwnd):
        old_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
        # 检查是否已经是正常样式
        if (old_style & WS_CAPTION) and (old_style & WS_THICKFRAME) and (old_style & WS_SYSMENU):
            return False
        # 修复样式
        if old_style & WS_POPUP:
            new_style = (old_style & ~WS_POPUP) | WS_OVERLAPPEDWINDOW
        else:
            new_style = old_style | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE)
        return True
    
    # 最多等待 30 秒
    for _ in range(60):
        time.sleep(0.5)
        windows = find_window()
        if windows:
            # 再等一下，确保窗口完全初始化
            time.sleep(0.5)
            for hwnd, title in windows:
                try:
                    fix_window(hwnd)
                except:
                    pass
            break


def _start_window_fix():
    """启动窗口自动修复的后台线程"""
    try:
        t = threading.Thread(target=_fix_window_style_worker, daemon=True)
        t.start()
    except:
        pass

SCRIPT_PATH = Path(__file__).resolve()
APP_DIR = SCRIPT_PATH.parent if (SCRIPT_PATH.parent / "_internal").exists() else SCRIPT_PATH.parent.parent
ROOT = APP_DIR / "_internal" if (APP_DIR / "_internal").exists() else SCRIPT_PATH.parent
CONFIG_FILE = ROOT / "data" / "app_config.json"
USER_DATA_DIR = Path(os.environ.get("MYRIDTV_USER_DATA_DIR") or (Path(os.environ.get("APPDATA", str(APP_DIR))) / "MyridTV"))
# 资产与输出统一放在软件安装目录下（用户要求 2026-08-16）。
# 覆盖安装/在线升级只覆盖程序文件（installer [Files] 不删除未知目录），assets 子目录会保留。
ASSETS_DIR = Path(os.environ.get("MYRIDTV_ASSETS_DIR") or (APP_DIR / "assets"))
def _migrate_legacy_assets():
    """把旧版 %APPDATA%\\MyridTV\\assets 整体迁移到安装目录（直接覆盖；用户已备份 C 盘目录）。"""
    try:
        legacy = USER_DATA_DIR / "assets"
        marker = ASSETS_DIR / ".legacy_migrated"
        if not legacy.exists() or marker.exists():
            return
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        for item in legacy.iterdir():
            dest = ASSETS_DIR / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            elif item.is_file():
                shutil.copy2(item, dest)
        marker.write_text("1", encoding="utf-8")
    except Exception as exc:
        try:
            print("assets migration failed:", exc)
        except Exception:
            pass
_migrate_legacy_assets()
BLENDER_IMPORT_DIR = ASSETS_DIR / "blender_imports"
# —— Blender 预演（画布 → Blender → 画布）——
PREVIZ_DIR = ASSETS_DIR / "blender" / "previz"
BLENDER_BIN = os.environ.get("MYRIDTV_BLENDER_BIN") or r"D:\blender\blender-4.5.2-windows-x64\blender.exe"
PREVIZ_FPS = int(os.environ.get("MYRIDTV_PREVIZ_FPS") or "24")
PREVIZ_BLACK_SEC = 0.4
CANVAS_AGENT_HISTORY_DIR = USER_DATA_DIR / "data" / "canvas_agent_history"
CANVAS_AGENT_HISTORY_INDEX_FILE = CANVAS_AGENT_HISTORY_DIR / "_index.json"
CANVAS_AGENT_RULES_FILE = USER_DATA_DIR / "data" / "canvas_agent_rules.md"
CANVAS_AGENT_SKILLS_DIR = USER_DATA_DIR / "data" / "canvas_agent_skills"
CANVAS_AGENT_RULES_MAX_CHARS = 32768
CANVAS_AGENT_SKILL_MAX_CHARS = 24576
CANVAS_AGENT_MAX_INVOKED_SKILLS = 5
DEFAULT_AGENTS = {
    "codex": {
        "name": "Myrid-Agent",
        "provider_id": "",
        "model": "",
        "preferred_model_pattern": "",
        "upstream_base_url": "",
        "api_key_env": "MYRIDTV_AGENT_API_KEY",
        "fallback_api_key_env": "API_PROVIDER_CUSTOM_API_KEY",
    },
}
DEFAULT_CONFIG = {
    "server": {"host": "127.0.0.1", "port": 3000, "base_url": "http://127.0.0.1:3000"},
    "proxy": {"host": "127.0.0.1", "port": 3107, "base_url": "http://127.0.0.1:3107"},
    "agent": {
        "active_id": "codex",
        "agents": DEFAULT_AGENTS,
    },
    "runninghub": {"api_key_envs": ["API_PROVIDER_CUSTOM_API_3_KEY", "RUNNINGHUB_API_KEY"]},
    "paths": {
        "env_file": "API/.env",
        "logs_dir": "data/logs",
        "proxy_log": "data/logs/rh_official_proxy.log",
        "startup_log": "data/logs/startup.log",
    },
    "runtime": {"python_exe": "", "python_env": "MYRIDTV_PYTHON_EXE"},
    "user_data": {"root_env": "MYRIDTV_USER_DATA_DIR", "default_dir": "%APPDATA%\\MyridTV", "mode": "junction"},
    "setup": {"completed": False, "completed_at": "", "dismissed_at": ""},
}


def normalize_agent_section(section):
    """归一化 agent 配置：旧单对象 -> 多 Agent map；补齐缺失 Agent 与字段。

    旧结构 {"model": "...", "upstream_base_url": "...", "has_key": true, ...}
    自动折叠进 agents.codex（保留 has_key/key_preview/key_env 等扩展字段）；
    active_id 缺失时默认 "codex"。返回 {"active_id", "agents"}。
    """
    section = dict(section or {})
    legacy = {
        key: value
        for key, value in section.items()
        if key not in ("agents", "active_id") and value is not None and value != ""
    }
    agents_raw = section.get("agents")
    agents = {}
    if isinstance(agents_raw, dict):
        for aid, entry in agents_raw.items():
            if not isinstance(entry, dict):
                continue
            base = dict(DEFAULT_AGENTS.get(aid, {}))
            for key, value in entry.items():
                if value is not None and value != "":
                    base[key] = value
            if not base.get("name"):
                base["name"] = DEFAULT_AGENTS.get(aid, {}).get("name") or aid
            agents[aid] = base
    if legacy:
        base = dict(DEFAULT_AGENTS["codex"])
        base.update(legacy)
        base["name"] = "Myrid-Agent"
        agents["codex"] = base
    for aid, defaults in DEFAULT_AGENTS.items():
        if aid not in agents:
            agents[aid] = dict(defaults)
    active_id = str(section.get("active_id") or "codex")
    if active_id not in agents:
        active_id = "codex" if "codex" in agents else next(iter(agents))
    # 顶层镜像活动 Agent 的关键字段，兼容仍读取扁平 agent.provider_id 的旧前端（如画布）。
    active_entry = agents.get(active_id) or {}
    return {
        "active_id": active_id,
        "agents": agents,
        "provider_id": str(active_entry.get("provider_id") or ""),
        "model": str(active_entry.get("model") or ""),
        "preferred_model_pattern": str(active_entry.get("preferred_model_pattern") or ""),
        "upstream_base_url": str(active_entry.get("upstream_base_url") or ""),
    }


def active_agent_entry(config=None):
    """返回当前激活 Agent 的配置条目（无则取第一个）。"""
    config = config if isinstance(config, dict) else APP_CONFIG
    section = config.get("agent") or {}
    agents = section.get("agents") if isinstance(section.get("agents"), dict) else {}
    if not agents:
        agents = dict(DEFAULT_AGENTS)
    active_id = str(section.get("active_id") or "codex")
    entry = agents.get(active_id)
    if entry is None:
        entry = next(iter(agents.values()), dict(DEFAULT_AGENTS["codex"]))
    return entry


def resolve_agent_entry(agent_id=None, config=None):
    """按 agent_id 解析 Agent 配置条目；未指定或不存在时回退到激活 Agent。

    返回 (agent_id, entry)。
    """
    config = config if isinstance(config, dict) else APP_CONFIG
    section = config.get("agent") or {}
    agents = section.get("agents") if isinstance(section.get("agents"), dict) else {}
    if not agents:
        agents = dict(DEFAULT_AGENTS)
    requested = str(agent_id or "").strip() or str(section.get("active_id") or "codex")
    if requested not in agents:
        requested = "codex" if "codex" in agents else next(iter(agents))
    return requested, agents[requested]


def load_app_config():
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    merged = deep_merge(DEFAULT_CONFIG, data if isinstance(data, dict) else {})
    merged["agent"] = normalize_agent_section(merged.get("agent"))
    return merged


def root_path(value, fallback):
    text = str(value or fallback or "").strip()
    path = Path(text)
    return path if path.is_absolute() else ROOT / path


def write_app_config(config):
    global APP_CONFIG, SERVER_CONFIG, PROXY_CONFIG, AGENT_CONFIG, RUNNINGHUB_CONFIG, PATHS_CONFIG, ENV_FILE, APP_BASE, PORT, LOG_FILE
    merged = deep_merge(DEFAULT_CONFIG, config if isinstance(config, dict) else {})
    merged["agent"] = normalize_agent_section(merged.get("agent"))
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(merged, ensure_ascii=False, indent=2)
    CONFIG_FILE.write_text(raw + "\n", encoding="utf-8")
    static_config = ROOT / "static" / "app_config.json"
    try:
        static_config.write_text(raw + "\n", encoding="utf-8")
    except Exception:
        pass
    APP_CONFIG = merged
    SERVER_CONFIG = APP_CONFIG.get("server") or {}
    PROXY_CONFIG = APP_CONFIG.get("proxy") or {}
    AGENT_CONFIG = active_agent_entry(APP_CONFIG)
    RUNNINGHUB_CONFIG = APP_CONFIG.get("runninghub") or {}
    PATHS_CONFIG = APP_CONFIG.get("paths") or {}
    ENV_FILE = root_path(PATHS_CONFIG.get("env_file"), "API/.env")
    LOG_FILE = root_path(PATHS_CONFIG.get("proxy_log"), "data/logs/rh_official_proxy.log")
    APP_BASE = str(SERVER_CONFIG.get("base_url") or f"http://{SERVER_CONFIG.get('host', '127.0.0.1')}:{SERVER_CONFIG.get('port', 3000)}").rstrip("/")
    PORT = int(PROXY_CONFIG.get("port") or 3107)
    append_log(LOG_FILE, f"app-config saved agent_active={APP_CONFIG['agent'].get('active_id')} agents={','.join(APP_CONFIG['agent'].get('agents', {}).keys())}")
    return merged


APP_CONFIG = load_app_config()
SERVER_CONFIG = APP_CONFIG.get("server") or {}
PROXY_CONFIG = APP_CONFIG.get("proxy") or {}
AGENT_CONFIG = active_agent_entry(APP_CONFIG)
RUNNINGHUB_CONFIG = APP_CONFIG.get("runninghub") or {}
PATHS_CONFIG = APP_CONFIG.get("paths") or {}
ENV_FILE = root_path(PATHS_CONFIG.get("env_file"), "API/.env")
LOG_FILE = root_path(PATHS_CONFIG.get("proxy_log"), "data/logs/rh_official_proxy.log")
APP_BASE = str(SERVER_CONFIG.get("base_url") or f"http://{SERVER_CONFIG.get('host', '127.0.0.1')}:{SERVER_CONFIG.get('port', 3000)}").rstrip("/")
PORT = int(PROXY_CONFIG.get("port") or 3107)
TASKS = {}
TASKS_LOCK = threading.Lock()
PERSISTENT_TASKS_FILE = USER_DATA_DIR / "data" / "canvas_tasks.json"
STATIC_VERSION = "2026.09.12.clickpop56"
OUTPUT_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
OUTPUT_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
RUNNINGHUB_ALLOWED_RESOLUTIONS = ("1k", "2k", "4k")
RUNNINGHUB_POLL_TIMEOUT_SECONDS = 1800
CODEX_LOCAL_UPSTREAMS = {"codex://local", "codex://cli", "codex://bridge"}
CODEX_LOCAL_DEFAULT_MODEL = "codex-default"
CODEX_LOCAL_DEFAULT_RUNTIME_MODEL = "gpt-5.5"
CODEX_LOCAL_WORKSPACE = Path(os.environ.get("MYRIDTV_CODEX_WORKSPACE") or APP_DIR)
CODEX_LOCAL_ATTACHMENTS_DIR = USER_DATA_DIR / "data" / "codex_bridge"
CODEX_LOCAL_SESSION_CACHE_FILE = USER_DATA_DIR / "data" / "codex_bridge_sessions.json"
CODEX_LOCAL_IMAGE_CACHE_DIR = CODEX_LOCAL_ATTACHMENTS_DIR / "images"
CODEX_LOCAL_REPLY_DIR = CODEX_LOCAL_ATTACHMENTS_DIR / "replies"
CODEX_LOCAL_SESSION_LOCK = threading.Lock()
CODEX_LOCAL_SESSION_CACHE = {}
CODEX_APP_SERVER_LOCK = threading.Lock()
CODEX_APP_SERVER_PORT_FILE = USER_DATA_DIR / "data" / "codex_app_server_port.json"
CODEX_LOCAL_PERSIST_SESSIONS = str(os.environ.get("MYRIDTV_CODEX_PERSIST_SESSIONS") or "").strip().lower() in {"1", "true", "yes", "on"}


TASKS = {}

# 任务表持久化：SQLite 单行 upsert（见 task_store.py）。
# 首次启动会把老的 canvas_tasks.json 一次性导入并归档为 .migrated_<ts>，此后不再读写该 json。
# 注意：不要把自己的 TASKS_LOCK 传给 store —— 调用方（set_task_state/recover_stale_tasks 等）
# 已持有 TASKS_LOCK，非重入锁会自锁死。store 用独立内部锁，锁序固定为 TASKS_LOCK -> store lock。
TASK_STORE = task_store.TaskStore(
    USER_DATA_DIR / "data" / "canvas_tasks.db",
    legacy_json_path=PERSISTENT_TASKS_FILE,
)
TASKS = TASK_STORE.load_all()


def _agent_task_log(category, message):
    append_log(LOG_FILE, "[{}] {}".format(category, message))


def _agent_mark_task_failed(task, turn, exc):
    """上游/配置异常时收尾任务：置 failed + 记原因。

    背景：submit_chat 抛异常时任务从不收尾，任务表里会永久留一条假 running
    （今天已踩两次：401 Invalid API-key、key 串平台）。
    """
    reason = str(exc or "").strip()[:300]
    now_ms = int(time.time() * 1000)
    try:
        if isinstance(task, dict):
            if str(task.get("status") or "") in {"pending", "running", "waiting_user", "paused"}:
                task["status"] = "failed"
            task["error"] = reason
            task["failed_at"] = now_ms
            task["updated_at"] = now_ms
        if isinstance(turn, dict):
            turn["status"] = "failed"
            turn["error"] = reason
            turn["updated_at"] = now_ms
        _agent_save_tasks()
        _agent_task_log("AgentTask", "task={} status=failed error={}".format(
            (task or {}).get("task_id") if isinstance(task, dict) else "", reason[:160]))
    except Exception as _e:
        append_log(LOG_FILE, "agent mark-task-failed error: {}".format(_e))


def _agent_task_for_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    conversation_id = str(payload.get("agent_session_id") or payload.get("session_id") or "").strip()
    canvas_id = str(payload.get("canvas_id") or "").strip()
    task_id = str(payload.get("task_id") or payload.get("agent_task_id") or "").strip()
    user_text = _agent_latest_user_text(payload) if "_agent_latest_user_text" in globals() else str(payload.get("message") or "")
    with TASKS_LOCK:
        task = agent_runtime.ensure_task(TASKS, conversation_id, canvas_id, user_text, task_id)
        persist_tasks_locked()
    _agent_task_log("AgentTask", "task={} workflow={} step={} status={}".format(
        task.get("task_id"), task.get("workflow_type"), task.get("current_step_id"), task.get("status")))
    return task


def _agent_save_tasks():
    with TASKS_LOCK:
        return persist_tasks_locked()


def _agent_attach_runtime_result(result, task, turn=None, validation=None):
    if not isinstance(result, dict):
        result = {"text": str(result or "")}
    task_payload = agent_runtime.serialize_task(task)
    step_payload = agent_runtime.serialize_step(task)
    progress = (task or {}).get("progress") if isinstance(task, dict) else {}
    result["task"] = task_payload
    result["step"] = step_payload
    result["progress"] = progress
    if validation is not None:
        result["workflow_validation"] = validation
    agent_result = result.get("agent_result")
    if isinstance(agent_result, dict):
        agent_result["task"] = task_payload
        agent_result["step"] = step_payload
        agent_result["progress"] = progress
        if validation is not None:
            agent_result["workflow_validation"] = validation
    return result


def positive_env_int(name, default, minimum=1, maximum=None):
    try:
        value = int(str(os.environ.get(name) or "").strip() or default)
    except Exception:
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


COMFY_WORKFLOW_POLL_TIMEOUT_SECONDS = positive_env_int("COMFY_WORKFLOW_POLL_TIMEOUT_SECONDS", 3600, 60, 21600)
RUNNINGHUB_DEFAULT_IMAGE_MODELS = [
    "seedream-v5-lite/text-to-image",
    "seedream-v5-lite/image-to-image",
    "rhart-image-g-2-official/text-to-image",
    "rhart-image-g-2-official/image-to-image",
    "rhart-image-g-2/text-to-image",
    "rhart-image-g-2/image-to-image",
    "rhart-image-n-g31-flash/image-to-image",
    "rhart-image-n-pro-official/edit",
]
STATIC_PATCHES = {
    ROOT / "static" / "index.html": [
        "/static/online.html",
        "/static/canvas.html",
        "/static/smart-canvas.html",
        "/static/js/i18n.js",
        "/static/api-settings.html",
        "/static/comfyui-settings.html",
        "/static/asset-manager.html",
    ],
    ROOT / "static" / "smart-canvas.html": ["/static/css/smart-canvas.css", "/static/js/smart-canvas.js", "/static/js/i18n.js"],
    ROOT / "static" / "canvas.html": [
        "/static/css/canvas.css",
        "/static/css/canvas-prism.css",
        "/static/js/canvas.js",
        "/static/js/canvas-prism.js",
        "/static/js/i18n.js",
    ],
ROOT / "static" / "api-settings.html": ["/static/js/api-settings.js", "/static/css/api-settings.css", "/static/js/api-settings-provider-repair.js", "/static/js/i18n.js"],
ROOT / "static" / "comfyui-settings.html": ["/static/js/comfyui-settings.js", "/static/css/comfyui-settings.css", "/static/js/i18n.js"],
ROOT / "static" / "asset-manager.html": ["/static/js/asset-manager.js", "/static/css/asset-manager.css", "/static/js/i18n.js"],
}


def patch_static_versions_once():
    for path, urls in STATIC_PATCHES.items():
        try:
            text = path.read_text(encoding="utf-8")
            updated = text
            for url in urls:
                pattern = re.compile(rf"({re.escape(url)}\?v=)[^\"'<>\s]+")
                updated = pattern.sub(lambda match: f"{match.group(1)}{STATIC_VERSION}", updated)
            if updated != text:
                path.write_text(updated, encoding="utf-8")
        except Exception:
            pass


def patch_static_versions_loop():
    while True:
        patch_static_versions_once()
        time.sleep(5)


def read_env_values():
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {}
    values = {}
    for line in lines:
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_env_values(updates=None, removals=None):
    updates = {str(key).strip(): "" if value is None else str(value) for key, value in (updates or {}).items() if str(key).strip()}
    removals = {str(name).strip() for name in (removals or []) if str(name).strip()}
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        lines = []
    result_lines = []
    written = set()
    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()
        if "=" not in line or stripped.startswith("#"):
            result_lines.append(line)
            continue
        key, _ = line.split("=", 1)
        name = key.strip()
        if name in removals:
            written.add(name)
            continue
        if name in updates:
            result_lines.append(f"{name}={updates[name]}")
            written.add(name)
        else:
            result_lines.append(line)
    for name, value in updates.items():
        if name not in written:
            result_lines.append(f"{name}={value}")
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(result_lines).rstrip() + "\n", encoding="utf-8")
    return read_env_values()


def read_env_key():
    keys = RUNNINGHUB_CONFIG.get("api_key_envs") or ("API_PROVIDER_CUSTOM_API_3_KEY", "RUNNINGHUB_API_KEY")
    values = read_env_values()
    for key in keys:
        if values.get(key):
            return values[key]
    return ""


def read_chat_key(provider_id="", agent_entry=None):
    entry = agent_entry if isinstance(agent_entry, dict) else AGENT_CONFIG
    env_names = {
        "custom-api": "API_PROVIDER_CUSTOM_API_KEY",
        "custom-api-3": "API_PROVIDER_CUSTOM_API_3_KEY",
        "volcengine": "VOLCENGINE_ARK_API_KEY",
    }
    configured_provider = str(entry.get("provider_id") or "").strip()
    configured_key_env = str(entry.get("api_key_env") or "MYRIDTV_AGENT_API_KEY").strip()
    if configured_provider and configured_key_env:
        env_names[configured_provider] = configured_key_env
    values = read_env_values()
    key_name = env_names.get(str(provider_id or "").strip())
    if key_name and values.get(key_name):
        return values[key_name]
    # Agent 复用自定义平台配置：平台 Key 按 API_PROVIDER_<ID>_KEY 保存。
    if str(provider_id or "").strip():
        provider_env = provider_key_env_name(provider_id)
        if provider_env and values.get(provider_env):
            return values[provider_env]
    if str(provider_id or "").strip() == "volcengine":
        try:
            ark_key = volcengine_ark_api_key()
            if ark_key:
                return ark_key
        except Exception:
            pass
    fallback_names = [
        entry.get("api_key_env"),
        entry.get("fallback_api_key_env"),
        "MYRIDTV_AGENT_API_KEY",
        "WCSTV_AGENT_API_KEY",
        "API_PROVIDER_CUSTOM_API_KEY",
    ]
    for name in fallback_names:
        if name and values.get(str(name)):
            return values[str(name)]
    return ""


def agent_key_meta(agent_id=None):
    values = read_env_values()
    if agent_id is not None:
        _, entry = resolve_agent_entry(agent_id)
    else:
        entry = AGENT_CONFIG
    primary_name = str(entry.get("api_key_env") or "MYRIDTV_AGENT_API_KEY").strip() or "MYRIDTV_AGENT_API_KEY"
    fallback_name = str(entry.get("fallback_api_key_env") or "API_PROVIDER_CUSTOM_API_KEY").strip() or "API_PROVIDER_CUSTOM_API_KEY"
    primary_value = values.get(primary_name, "")
    fallback_value = values.get(fallback_name, "")
    active_name = primary_name if primary_value else (fallback_name if fallback_value else primary_name)
    active_value = primary_value or fallback_value or ""
    preview = ""
    if active_value:
        tail = active_value[-4:] if len(active_value) >= 4 else active_value
        preview = f"••••••••{tail}"
    return {
        "key_env": active_name,
        "has_key": bool(active_value),
        "key_preview": preview,
        "primary_key_env": primary_name,
        "fallback_key_env": fallback_name,
    }


def agents_meta_payload():
    """完整多 Agent 配置 + 每 Agent Key 元信息，供设置页/画布读取。"""
    section = APP_CONFIG.get("agent") or {}
    agents = section.get("agents") if isinstance(section.get("agents"), dict) else {}
    result = {}
    for aid, entry in agents.items():
        merged = dict(entry) if isinstance(entry, dict) else {}
        merged.update(agent_key_meta(aid))
        result[aid] = merged
    return {
        "active_id": str(section.get("active_id") or "codex"),
        "agents": result,
    }


def provider_key_env_name(provider_id):
    provider_id = str(provider_id or "").strip()
    if provider_id == "volcengine":
        return "ARK_API_KEY"
    if provider_id == "runninghub" or provider_id == "custom-api-3":
        return "API_PROVIDER_CUSTOM_API_3_KEY"
    if provider_id == "custom-api":
        return "API_PROVIDER_CUSTOM_API_KEY"
    # 平台 Key 优先按 API_PROVIDER_<ID>_KEY 推导（custom-api-2 → API_PROVIDER_CUSTOM_API_2_KEY）。
    # 注意：不能因为「该平台就是 Agent 当前平台」就返回 Agent 自己的 Key 变量——
    # Agent 切平台后那个变量通常不存在，会一路掉到兜底 Key（串平台 → 401）。
    safe = re.sub(r"[^A-Za-z0-9]+", "_", provider_id).strip("_").upper()
    if safe:
        return f"API_PROVIDER_{safe}_KEY"
    if provider_id == str(AGENT_CONFIG.get("provider_id") or "").strip():
        return str(AGENT_CONFIG.get("api_key_env") or "MYRIDTV_AGENT_API_KEY").strip() or "MYRIDTV_AGENT_API_KEY"
    return "API_PROVIDER_CUSTOM_API_KEY"


def provider_wallet_key_env_name(provider_id):
    provider_id = str(provider_id or "").strip()
    if provider_id == "runninghub":
        return "RUNNINGHUB_API_KEY"
    safe = re.sub(r"[^A-Za-z0-9]+", "_", provider_id).strip("_").upper()
    return f"API_PROVIDER_{safe}_WALLET_KEY" if safe else "API_PROVIDER_WALLET_KEY"


def enrich_api_provider_key_meta(providers):
    values = read_env_values()
    result = []
    for provider in providers if isinstance(providers, list) else []:
        if not isinstance(provider, dict):
            continue
        item = dict(provider)
        key_env = provider_key_env_name(item.get("id"))
        key_value = values.get(key_env, "")
        item["key_env"] = key_env
        item["has_key"] = bool(key_value)
        item["key_preview"] = mask_secret(key_value)
        # 火山推理计划 plan 端点不提供模型列表；仅在用户没有保存任何对话模型时用内置清单引导，
        # 已保存的以用户配置为准（删掉的模型不再复活）。
        if is_volcengine_plan_base(item.get("base_url")) and not (item.get("chat_models") or []):
            item["chat_models"] = volcengine_plan_chat_models(item.get("chat_models"))
        if str(item.get("id") or "").strip() == "runninghub":
            wallet_env = provider_wallet_key_env_name(item.get("id"))
            wallet_value = values.get(wallet_env, "")
            item["wallet_key_env"] = wallet_env
            item["has_wallet_key"] = bool(wallet_value)
            item["wallet_key_preview"] = mask_secret(wallet_value)
        result.append(item)
    return result


def persist_api_provider_keys(raw_providers):
    updates = {}
    removals = []
    for record in raw_providers if isinstance(raw_providers, list) else []:
        if not isinstance(record, dict):
            continue
        provider_id = str(record.get("id") or "").strip()
        if not provider_id:
            continue
        key_env = provider_key_env_name(provider_id)
        wallet_env = provider_wallet_key_env_name(provider_id)
        if bool(record.get("clear_key")):
            removals.append(key_env)
        else:
            key_value = str(record.get("api_key") or "").strip()
            if key_value:
                updates[key_env] = key_value
        if bool(record.get("clear_wallet_key")):
            removals.append(wallet_env)
        else:
            wallet_key = str(record.get("wallet_api_key") or "").strip()
            if wallet_key:
                updates[wallet_env] = wallet_key
    if updates or removals:
        write_env_values(updates, removals)


def canvas_agent_history_path(canvas_id=""):
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", str(canvas_id or "default").strip() or "default")
    return CANVAS_AGENT_HISTORY_DIR / f"{name}.json"


def read_limited_text(path, max_chars):
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except Exception as exc:
        append_log(LOG_FILE, f"read text failed path={path}: {exc}")
        return ""
    return text[:max_chars]


def ensure_canvas_agent_config_files():
    try:
        CANVAS_AGENT_RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        CANVAS_AGENT_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        if not CANVAS_AGENT_RULES_FILE.exists():
            CANVAS_AGENT_RULES_FILE.write_text(
                "# MyridTV Agent 全局规则\n\n"
                "- 默认使用中文回答，除非用户明确要求其他语言。\n"
                "- 处理无限画布任务时，优先结合用户选中的节点、引用图片和当前画布上下文。\n"
                "- 对图片优化类请求，给出可直接执行的修改建议或提示词，不要只泛泛解释。\n",
                encoding="utf-8",
            )
        default_skill = CANVAS_AGENT_SKILLS_DIR / "服装优化.md"
        default_skill_marker = CANVAS_AGENT_SKILLS_DIR / ".default_skill_deleted"
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
        append_log(LOG_FILE, f"ensure canvas agent config failed: {exc}")


def read_canvas_agent_rules():
    ensure_canvas_agent_config_files()
    return read_limited_text(CANVAS_AGENT_RULES_FILE, CANVAS_AGENT_RULES_MAX_CHARS).strip()


def write_canvas_agent_rules(content):
    text = str(content or "")
    if len(text) > CANVAS_AGENT_RULES_MAX_CHARS:
        raise ApiError(400, f"全局规则过长，最多 {CANVAS_AGENT_RULES_MAX_CHARS} 字符")
    ensure_canvas_agent_config_files()
    CANVAS_AGENT_RULES_FILE.write_text(text.rstrip() + ("\n" if text.strip() else ""), encoding="utf-8")
    return read_canvas_agent_rules()


def list_canvas_agent_skills():
    ensure_canvas_agent_config_files()
    skills = []
    try:
        files = sorted(CANVAS_AGENT_SKILLS_DIR.glob("*.md"), key=lambda path: path.stem.casefold())
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
    path = (CANVAS_AGENT_SKILLS_DIR / f"{safe_name}.md").resolve()
    root = CANVAS_AGENT_SKILLS_DIR.resolve()
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
        "content": read_limited_text(path, CANVAS_AGENT_SKILL_MAX_CHARS),
    }


def write_canvas_agent_skill(name, content):
    text = str(content or "")
    if len(text) > CANVAS_AGENT_SKILL_MAX_CHARS:
        raise ApiError(400, f"技能内容过长，最多 {CANVAS_AGENT_SKILL_MAX_CHARS} 字符")
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
            (CANVAS_AGENT_SKILLS_DIR / ".default_skill_deleted").write_text("1", encoding="utf-8")
        except Exception:
            pass
    return {"name": path.stem, "deleted": True}


def extract_invoked_skill_names(text):
    found = []
    for match in re.finditer(r"[@＠]([^\s@＠#＃，,。；;：:（）()\[\]{}<>《》\"'“”‘’]+)", str(text or "")):
        name = safe_agent_skill_name(match.group(1))
        if name and name not in found:
            found.append(name)
    return found[:CANVAS_AGENT_MAX_INVOKED_SKILLS]


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
    return found[:CANVAS_AGENT_MAX_INVOKED_SKILLS]


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
            invoked.append((skill.get("name") or name, content[:CANVAS_AGENT_SKILL_MAX_CHARS]))
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
            invoked.append((skill.get("name") or name, content[:CANVAS_AGENT_SKILL_MAX_CHARS]))
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


def canvas_agent_vision_config():
    """后台视觉识别配置：主模型不支持视觉时，自动调视觉模型把图片转文字。"""
    v = APP_CONFIG.get("vision") if isinstance(APP_CONFIG, dict) else {}
    if not isinstance(v, dict):
        v = {}
    enabled = v.get("enabled")
    if not isinstance(enabled, bool):
        enabled = str(enabled or "").lower() in ("1", "true", "yes", "on") if enabled not in (None, "") else True
    deleted = bool(str(v.get("deleted_at") or "").strip())
    if deleted:
        # 已删除的视觉平台：模型/地址/Key 一律返回空，不回填默认值（否则前端又显示地址）
        return {
            "enabled": False,
            "model": "",
            "base_url": "",
            "api_key": "",
            "has_key": False,
            "deleted": True,
            "deleted_at": str(v.get("deleted_at") or ""),
        }
    return {
        "enabled": bool(enabled) if enabled is not None else True,
        "model": str(v.get("model") or "glm-4v-flash").strip() or "glm-4v-flash",
        "base_url": str(v.get("base_url") or "").strip() or "https://open.bigmodel.cn/api/paas/v4",
        "api_key": str(v.get("api_key") or "").strip(),
        "has_key": bool(str(v.get("api_key") or "").strip()),
        "deleted": deleted,
        "deleted_at": str(v.get("deleted_at") or ""),
    }


def save_canvas_agent_vision_config(vision):
    """保存后台视觉识别配置（app_config.json 顶层 vision 字段）。

    vision={"delete": True} 表示删除视觉平台：清空模型/地址/Key 并关闭视觉识别，
    不影响任何 API 平台（不写 api_providers.json）。
    """
    global APP_CONFIG
    if not isinstance(vision, dict):
        return canvas_agent_vision_config()
    config = dict(APP_CONFIG)
    if vision.get("delete") is True:
        config["vision"] = {
            "enabled": False,
            "model": "",
            "base_url": "",
            "deleted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        write_app_config(config)
        APP_CONFIG = config
        append_log(LOG_FILE, "[VisionPlatformDeleted] vision config cleared")
        return canvas_agent_vision_config()
    base_url = str(vision.get("base_url") or "").strip() or "https://open.bigmodel.cn/api/paas/v4"
    api_key = str(vision.get("api_key") or "").strip()
    config["vision"] = {
        "enabled": bool(vision.get("enabled", True)),
        "model": str(vision.get("model") or "glm-4v-flash").strip() or "glm-4v-flash",
        "base_url": base_url,
    }
    if api_key:
        config["vision"]["api_key"] = api_key
    write_app_config(config)
    APP_CONFIG = config
    return canvas_agent_vision_config()


def canvas_agent_config_payload(include_rules=True):
    return {
        "ok": True,
        "rules": read_canvas_agent_rules() if include_rules else "",
        "rules_file": str(CANVAS_AGENT_RULES_FILE),
        "skills_dir": str(CANVAS_AGENT_SKILLS_DIR),
        "skills": list_canvas_agent_skills(),
        "invocation": {"prefix": "@", "example": "@服装优化"},
        "agents": agents_meta_payload(),
        "vision": canvas_agent_vision_config(),
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
    canvas_path = USER_DATA_DIR / "data" / "canvases" / f"{safe_id}.json"
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
    CANVAS_AGENT_HISTORY_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    CANVAS_AGENT_HISTORY_INDEX_FILE.write_text(json.dumps(normalized[:400], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return normalized[:400]


def rebuild_canvas_agent_history_index():
    entries = []
    try:
        files = list(CANVAS_AGENT_HISTORY_DIR.glob("*.json"))
    except Exception:
        files = []
    for path in files:
        if path.name == CANVAS_AGENT_HISTORY_INDEX_FILE.name:
            continue
        canvas_id = path.stem
        entries.extend(canvas_agent_history_index_entries_for_canvas(canvas_id, read_canvas_agent_history(canvas_id)))
    return write_canvas_agent_history_index(entries)


def read_canvas_agent_history_index():
    try:
        raw = json.loads(CANVAS_AGENT_HISTORY_INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return rebuild_canvas_agent_history_index()
    if not isinstance(raw, list):
        return rebuild_canvas_agent_history_index()
    result = []
    for entry in raw:
        safe_entry = normalize_canvas_agent_history_index_entry(entry)
        if safe_entry:
            result.append(safe_entry)
    result.sort(key=lambda item: int(item.get("updatedAt") or 0), reverse=True)
    return result[:400]


def sync_canvas_agent_history_index(canvas_id="", history_list=None, canvas_title=""):
    safe_canvas_id = str(canvas_id or "").strip()
    current = [entry for entry in read_canvas_agent_history_index() if entry.get("canvas_id") != safe_canvas_id]
    current.extend(canvas_agent_history_index_entries_for_canvas(safe_canvas_id, history_list, canvas_title))
    return write_canvas_agent_history_index(current)


def request_json(url, method="GET", payload=None, headers=None, timeout=120):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36")
    req.add_header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            detail = json.loads(raw)
        except Exception:
            detail = raw
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def request_multipart_json(url, fields=None, files=None, headers=None, timeout=120):
    boundary = "----MyridTV" + uuid.uuid4().hex
    body = bytearray()
    for name, value in (fields or {}).items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value or "").encode("utf-8"))
        body.extend(b"\r\n")
    for file_info in files or []:
        field_name = str(file_info.get("name") or "file")
        file_name = str(file_info.get("filename") or "upload.bin")
        content_type = str(file_info.get("content_type") or "application/octet-stream")
        raw = file_info.get("data") or b""
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{file_name}"\r\n'.encode("utf-8")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(raw)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    req = urllib.request.Request(url, data=bytes(body), method="POST")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36")
    req.add_header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            detail = json.loads(raw)
        except Exception:
            detail = raw
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def request_multipart_text(url, fields=None, files=None, headers=None, timeout=180):
    boundary = "----MyridTV" + uuid.uuid4().hex
    body = bytearray()
    for name, value in (fields or {}).items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value or "").encode("utf-8"))
        body.extend(b"\r\n")
    for file_info in files or []:
        field_name = str(file_info.get("name") or "file")
        file_name = str(file_info.get("filename") or "upload.bin")
        content_type = str(file_info.get("content_type") or "application/octet-stream")
        raw = file_info.get("data") or b""
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{file_name}"\r\n'.encode("utf-8")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(raw)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    req = urllib.request.Request(url, data=bytes(body), method="POST")
    req.add_header("Accept", "text/plain, application/json;q=0.9, */*;q=0.8")
    req.add_header("User-Agent", "MyridTV/1.0")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace").strip()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code}: {raw}") from exc


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
                append_log(LOG_FILE, f"agent chat retry attempt={attempt} url={url}")
            return request_json(url, "POST", body, headers, timeout=timeout)
        except Exception as exc:
            last_exc = exc
            retryable = is_retryable_chat_error(exc)
            append_log(LOG_FILE, f"agent chat attempt={attempt} failed retryable={retryable}: {exc}")
            if not retryable or attempt >= attempts:
                break
            time.sleep(min(1.5 * attempt, 4))
    raise RuntimeError(f"Agent 上游请求被中断，已重试 {attempts} 次仍失败：{last_exc}") from last_exc


def _codex_bridge_read_session_cache():
    data = read_json_file(CODEX_LOCAL_SESSION_CACHE_FILE, {})
    return data if isinstance(data, dict) else {}


def _codex_bridge_write_session_cache():
    with CODEX_LOCAL_SESSION_LOCK:
        write_json_file(CODEX_LOCAL_SESSION_CACHE_FILE, CODEX_LOCAL_SESSION_CACHE)


def _codex_bridge_session_key(payload, model):
    canvas_id = str((payload or {}).get("canvas_id") or "").strip() or "default"
    agent_id = str((payload or {}).get("agent_id") or "").strip() or "codex"
    runtime_model = str(model or CODEX_LOCAL_DEFAULT_MODEL).strip() or CODEX_LOCAL_DEFAULT_MODEL
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


CODEX_LOCAL_SESSION_CACHE.update(_codex_bridge_read_session_cache())


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
            cmd = [resolve_codex_executable(), "app-server", "--listen", self._ws_url]
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(CODEX_LOCAL_WORKSPACE),
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
            write_json_file(CODEX_APP_SERVER_PORT_FILE, {"ws_url": self._ws_url, "readyz": self._http_readyz, "updated_at": int(time.time())})

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
                "model": model or CODEX_LOCAL_DEFAULT_RUNTIME_MODEL,
                "cwd": str(CODEX_LOCAL_WORKSPACE),
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
                "model": model or CODEX_LOCAL_DEFAULT_RUNTIME_MODEL,
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


def persistent_task_payload(state):
    if not isinstance(state, dict):
        return {}
    safe = {}
    for key, value in state.items():
        if key.startswith("_"):
            continue
        try:
            json.dumps(value, ensure_ascii=False)
        except Exception:
            continue
        safe[key] = value
    safe["persistent"] = True
    return safe


def persist_tasks_locked(task_id=None):
    """写任务表：给了 task_id 只写这一行（热路径），否则整表同步一次事务。

    注意：本函数自身不加锁，必须在 TASKS_LOCK 内调用。
    """
    if task_id is not None:
        safe_id = str(task_id)
        state = TASKS.get(safe_id)
        if isinstance(state, dict) and state.get("persistent"):
            TASK_STORE.upsert(safe_id, persistent_task_payload(state))
        return
    TASK_STORE.upsert_many({
        task_id: persistent_task_payload(state)
        for task_id, state in TASKS.items()
        if isinstance(state, dict) and state.get("persistent")
    })


def set_task_state(task_id, state, persistent=False):
    safe_id = str(task_id or "").strip()
    if not safe_id:
        return {}
    safe_state = dict(state or {})
    if persistent or safe_state.get("persistent"):
        safe_state["persistent"] = True
    with TASKS_LOCK:
        TASKS[safe_id] = safe_state
        if safe_state.get("persistent"):
            persist_tasks_locked(safe_id)
    return safe_state


def update_task_state(task_id, **updates):
    safe_id = str(task_id or "").strip()
    if not safe_id:
        return {}
    with TASKS_LOCK:
        current = dict(TASKS.get(safe_id) or {})
        current.update(updates)
        TASKS[safe_id] = current
        if current.get("persistent"):
            persist_tasks_locked(safe_id)
    return current


def get_task_state(task_id):
    safe_id = str(task_id or "").strip()
    if not safe_id:
        return {}
    with TASKS_LOCK:
        return dict(TASKS.get(safe_id) or {})


def load_persistent_tasks():
    data = TASK_STORE.load_all()
    if not isinstance(data, dict):
        return
    with TASKS_LOCK:
        for task_id, state in data.items():
            if isinstance(state, dict) and task_id:
                TASKS[str(task_id)] = persistent_task_payload(state)


# ====== 启动自愈：上一次进程遗留的僵尸任务 ======
# 进程退出/崩溃时，任务表会永久残留 in-flight 状态：前端一直转圈、任务再也无法重新提交。
# 只有真正的僵尸态才收尾；waiting_user / paused 是健康的「等用户 / 已暂停」休息态，绝不动。
STALE_AGENT_TASK_STATUSES = {"pending", "running"}
STALE_MEDIA_TASK_STATUSES = {"pending", "running", "queued", "processing", "submitting"}


def recover_stale_tasks(source="MyridTV 后端重启"):
    """启动时把上一次进程遗留的 in-flight 任务收尾为 failed，并写明中断原因。

    Agent 任务里未收尾的 turn 一并置 failed，避免前端停在「思考中」。
    返回被收尾的 task_id 列表。
    """
    now = int(time.time() * 1000)
    reason = "{}，任务已中断并标记为失败，可重新提交".format(source)
    recovered = []
    with TASKS_LOCK:
        for task_id, state in TASKS.items():
            if not isinstance(state, dict):
                continue
            status = str(state.get("status") or "").strip().lower()
            is_agent = isinstance(state.get("turns"), list) or bool(state.get("workflow_type"))
            allowed = STALE_AGENT_TASK_STATUSES if is_agent else STALE_MEDIA_TASK_STATUSES
            if status not in allowed:
                continue
            tid = str(task_id or state.get("task_id") or "")
            state["status"] = "failed"
            state["error"] = reason
            state["failed_at"] = now
            state["updated_at"] = now
            if is_agent:
                for turn in reversed(state.get("turns") or []):
                    if isinstance(turn, dict) and str(turn.get("status") or "").strip().lower() in STALE_AGENT_TASK_STATUSES:
                        turn["status"] = "failed"
                        turn["error"] = reason
                        turn["updated_at"] = now
                        break
            recovered.append(tid)
        if recovered:
            persist_tasks_locked()
    for tid in recovered:
        _agent_task_log("StartupRecovery", "task={} -> failed ({})".format(tid, reason))
    if recovered:
        _agent_task_log("StartupRecovery", "已收尾 {} 个僵尸任务".format(len(recovered)))
    return recovered


# ====== 任务运行控制台（task-console）======
TASK_CONSOLE_CANCELLED = set()
TASK_CONSOLE_CANCELLED_LOCK = threading.Lock()
# 高成本模型关键词（官方贵档/4K档）
TASK_CONSOLE_COSTLY_MODEL_PAT = re.compile(r"official|g-2-official|4k|seedance|premium", re.I)


def _task_console_kind(task_id, state):
    tid = str(task_id or "")
    backend = str(state.get("backend") or "")
    if state.get("workflow_type") == "video_creation":
        return "智能体任务"
    if backend == "volcengine-ark":
        return "视频"
    if backend == "blender-previz":
        return "视频"
    if backend == "comfyui":
        return "ComfyUI"
    if backend == "runninghub-workflow":
        return "RunningHub 工作流"
    submit = state.get("submit") if isinstance(state.get("submit"), dict) else {}
    if state.get("rh_task_id") or backend == "runninghub-official":
        model = str(state.get("model") or "")
        if "/image-to-image" in model or state.get("mode") == "i2i":
            return "图生图"
        return "生图"
    if tid.startswith("rhproxy"):
        return "生图"
    if tid.startswith("volc"):
        return "视频"
    return "其他"


def _task_console_platform(state):
    backend = str(state.get("backend") or "")
    provider = str(state.get("provider_id") or "")
    if backend == "volcengine-ark" or provider == "volcengine":
        return "火山方舟"
    if backend == "blender-previz" or provider == "blender":
        return "Blender"
    if backend == "comfyui" or provider == "comfyui":
        return "ComfyUI"
    if backend.startswith("runninghub") or provider == "runninghub":
        return "RunningHub"
    if state.get("rh_task_id"):
        return "RunningHub"
    if provider:
        return provider
    return backend or "未知"


def _task_console_model(state):
    for key in ("model",):
        val = str(state.get(key) or "").strip()
        if val:
            return val
    body = state.get("submit") if isinstance(state.get("submit"), dict) else None
    if body:
        val = str(body.get("model") or "").strip()
        if val:
            return val
    return "—"


def _task_console_risks(task_id, state):
    risks = []
    kind = state.get("_kind") or ""
    model = _task_console_model(state)
    resolution = str(state.get("resolution") or (state.get("submit") or {}).get("resolution") if isinstance(state.get("submit"), dict) else state.get("resolution") or "").lower()
    if TASK_CONSOLE_COSTLY_MODEL_PAT.search(model):
        risks.append("高成本模型")
    if "4k" in str(resolution).lower():
        risks.append("4K 分辨率")
    try:
        n = int(state.get("count") or state.get("n") or 1)
    except Exception:
        n = 1
    if n >= 4:
        risks.append("多张并发(%d)" % n)
    if kind == "视频":
        risks.append("视频任务成本高")
    if kind == "RunningHub 工作流":
        risks.append("云端工作流")
    return risks


def _task_console_origin(task_id, state):
    tid = str(task_id or "")
    if tid.startswith("rhproxy"):
        return "画布节点执行"
    if tid.startswith("volc"):
        return "画布节点执行"
    if tid.startswith("task_"):
        return "Myrid-Agent"
    if state.get("source") == "mcp":
        return "MCP 工具"
    if state.get("source") == "agent":
        return "智能体"
    return str(state.get("source") or "画布节点执行")


def task_console_snapshot():
    now = time.time()
    items = []
    with TASKS_LOCK:
        raw = {tid: dict(st) for tid, st in TASKS.items() if isinstance(st, dict)}
    for tid, st in raw.items():
        kind = _task_console_kind(tid, st)
        st["_kind"] = kind
        submit = st.get("submit") if isinstance(st.get("submit"), dict) else {}
        resolution = str(st.get("resolution") or submit.get("resolution") or "").strip()
        count = st.get("count") or st.get("n") or 1
        try:
            count = int(count)
        except Exception:
            count = 1
        result = st.get("result") if isinstance(st.get("result"), dict) else {}
        out_images = result.get("images") if isinstance(result.get("images"), list) else []
        out_videos = result.get("videos") if isinstance(result.get("videos"), list) else []
        items.append({
            "task_id": tid,
            "kind": kind,
            "status": str(st.get("status") or "unknown"),
            "platform": _task_console_platform(st),
            "model": _task_console_model(st),
            "resolution": resolution or "—",
            "count": count,
            "origin": _task_console_origin(tid, st),
            "canvas_id": str(st.get("canvas_id") or ""),
            "canvas_title": str(st.get("canvas_title") or ""),
            "node_id": str(st.get("node_id") or ""),
            "mode": str(st.get("mode") or ("i2i" if (st.get("reference_images") or st.get("reference_image_urls")) else "t2i")),
            "provider_task_id": str(st.get("provider_task_id") or st.get("rh_task_id") or ""),
            "created_at": _task_console_ts(st.get("created_at")),
            "completed_at": _task_console_ts(st.get("completed_at")),
            "error": str(st.get("error") or st.get("last_error") or "")[:300],
            "outputs": len(out_images) + len(out_videos),
            "risks": _task_console_risks(tid, st),
        })
    items.sort(key=lambda x: _task_console_ts(x.get("created_at")), reverse=True)
    # 统计：今日
    day_start = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, 0))
    today = [it for it in items if _task_console_ts(it.get("created_at")) >= day_start]
    today_ok = [it for it in today if it.get("status") == "succeeded"]
    today_fail = [it for it in today if it.get("status") == "failed"]
    model_calls = {}
    for it in today:
        key = it["platform"] + " / " + it["model"]
        entry = model_calls.setdefault(key, {"calls": 0, "failed": 0, "outputs": 0})
        entry["calls"] += 1
        if it["status"] == "failed":
            entry["failed"] += 1
        entry["outputs"] += it["outputs"]
    stats = {
        "today_total": len(today),
        "today_success": len(today_ok),
        "today_failed": len(today_fail),
        "today_failure_rate": round(len(today_fail) * 100.0 / len(today), 1) if today else 0.0,
        "today_outputs": sum(it["outputs"] for it in today_ok),
        "running": sum(1 for it in items if it["status"] == "running"),
        "models": [
            {"key": k, **v, "failure_rate": round(v["failed"] * 100.0 / v["calls"], 1) if v["calls"] else 0.0}
            for k, v in sorted(model_calls.items(), key=lambda kv: -kv[1]["calls"])
        ],
    }
    return {"ok": True, "tasks": items, "stats": stats, "now": now}


class _TaskConsoleCancelled(RuntimeError):
    pass


def task_console_stop(payload):
    task_ids = payload.get("task_ids") if isinstance(payload.get("task_ids"), list) else []
    if not task_ids and payload.get("task_id"):
        task_ids = [payload.get("task_id")]
    stopped, missing = [], []
    with TASKS_LOCK:
        for tid in task_ids:
            tid = str(tid or "").strip()
            if not tid:
                continue
            st = TASKS.get(tid)
            if not isinstance(st, dict):
                missing.append(tid)
                continue
            if str(st.get("status")) == "running":
                with TASK_CONSOLE_CANCELLED_LOCK:
                    TASK_CONSOLE_CANCELLED.add(tid)
                # 立刻标记取消；轮询线程检测到后不再覆盖状态
                st["status"] = "cancelled"
                st["error"] = "用户手动停止"
                st["completed_at"] = time.time()
                if st.get("persistent"):
                    persist_tasks_locked()
                stopped.append(tid)
            else:
                missing.append(tid)
    return {"ok": True, "stopped": stopped, "skipped": missing}


def _task_console_is_cancelled(task_id):
    with TASK_CONSOLE_CANCELLED_LOCK:
        return str(task_id or "") in TASK_CONSOLE_CANCELLED


load_persistent_tasks()
# 本次进程刚启动，此时 TASKS 里任何 in-flight 状态都必然是上次进程的残留
recover_stale_tasks()
if TASK_STORE.migrated_from:
    _agent_task_log("TaskStore", "canvas_tasks.json 已迁移到 SQLite: " + TASK_STORE.migrated_from)


def providers_file_path():
    return USER_DATA_DIR / "data" / "api_providers.json"


def asset_library_file_path():
    return USER_DATA_DIR / "data" / "asset_library.json"


def prompt_library_file_path():
    return USER_DATA_DIR / "data" / "prompt_libraries.json"


def comfy_instances_file_path():
    return USER_DATA_DIR / "data" / "comfyui_instances.json"


def workflow_search_roots():
    return [
        (ROOT / "workflows" / "custom", False),
        (ROOT / "workflows", True),
    ]


def workflow_file_candidates(name):
    safe_name = str(name or "").strip()
    if not safe_name:
        raise ApiError(400, "缺少工作流名称")
    if "/" in safe_name or "\\" in safe_name or ".." in safe_name:
        raise ApiError(400, "工作流名称非法")
    file_name = safe_name if safe_name.lower().endswith(".json") else f"{safe_name}.json"
    config_name = file_name[:-5] + ".config.json"
    candidates = []
    for root, builtin in workflow_search_roots():
        candidates.append((root / file_name, root / config_name, builtin))
    return file_name, candidates


def workflow_title_from_name(name):
    return str(name or "").replace(".json", "").strip() or "未命名工作流"


def workflow_field_count(config):
    if not isinstance(config, dict):
        return 0
    fields = config.get("fields")
    return len(fields) if isinstance(fields, list) else 0


def api_provider_default_image_models():
    return {
        "volcengine": {
            "image_models": [
                "doubao-seedream-3-0-t2i-250415",
                "doubao-seedream-4-0-250828",
                "doubao-seedream-4-5-251128",
                "doubao-seedream-5-0-260128",
            ],
            "video_models": [
                "doubao-seedance-1-0-lite-i2v-250428",
                "doubao-seedance-1-0-lite-t2v-250428",
                "doubao-seedance-1-0-pro-250528",
                "doubao-seedance-1-0-pro-fast-251015",
                "doubao-seedance-1-5-pro-251215",
                "doubao-seedance-2-0-260128",
                "doubao-seedance-2-0-fast-260128",
                "doubao-seedance-2-0-mini-260615",
            ],
        },
    }


def ensure_api_provider_models(providers):
    defaults = api_provider_default_image_models()
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        pid = str(provider.get("id") or "").strip()
        if pid in defaults:
            for key in ("image_models", "video_models"):
                fallback_list = defaults[pid].get(key)
                if fallback_list is None:
                    continue
                current = provider.get(key)
                if not isinstance(current, list):
                    provider[key] = list(fallback_list)
                elif key == "image_models" and pid == "volcengine":
                    continue
                elif not current:
                    # 内置清单只在用户列表为空时兜底；非空一律以用户保存的为准（删掉的模型不再复活）
                    provider[key] = list(fallback_list)
    return providers


def read_api_providers():
    path = providers_file_path()
    data = read_json_file(path, [])
    fallback = ROOT / "static" / "runninghub" / "api_providers.json"
    fallback_data = read_json_file(fallback, [])
    cleaned_fallback = sanitize_api_providers(fallback_data if isinstance(fallback_data, list) else [])
    if isinstance(data, list) and data:
        cleaned = sanitize_api_providers(data)
        if cleaned:
            result = ensure_api_provider_models(cleaned)
            return enrich_api_provider_key_meta(apply_user_model_prefs(result))
    result = ensure_api_provider_models(cleaned_fallback) if cleaned_fallback else []
    return enrich_api_provider_key_meta(apply_user_model_prefs(result))


def apply_user_model_prefs(providers):
    prefs = read_user_model_prefs()
    if not prefs:
        return providers
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        pid = str(provider.get("id") or "").strip()
        if pid in prefs:
            for key in ("image_models", "video_models"):
                if key in prefs[pid]:
                    provider[key] = list(prefs[pid][key])
    return providers


def merge_builtin_runninghub_entries(providers, fallback_providers):
    if not isinstance(providers, list) or not isinstance(fallback_providers, list):
        return providers
    current = next((item for item in providers if isinstance(item, dict) and str(item.get("id") or "").strip() == "runninghub"), None)
    fallback = next((item for item in fallback_providers if isinstance(item, dict) and str(item.get("id") or "").strip() == "runninghub"), None)
    if not current or not fallback:
        return providers
    for key in ("rh_apps", "rh_workflows"):
        existing = current.get(key) if isinstance(current.get(key), list) else []
        if existing:
            continue
        current[key] = [dict(item) for item in (fallback.get(key) or []) if isinstance(item, dict)]
    return providers


API_PROVIDER_ALLOWED_KEYS = {
    "id",
    "name",
    "base_url",
    "protocol",
    "image_generation_endpoint",
    "image_edit_endpoint",
    "enabled",
    "primary",
    "image_models",
    "chat_models",
    "video_models",
    "model_display_names",
    "model_protocols",
    "ms_loras",
    "ms_defaults_version",
    "rh_apps",
    "rh_workflows",
    "volcengine_project_name",
    "volcengine_region",
    "wallet_api_key",
    "imageOrder",
    "connection_ok",
    "required",
    "clear_key",
    "clear_wallet_key",
    "clear_volcengine_access_key_id",
    "clear_volcengine_secret_access_key",
}
API_PROVIDER_REQUIRED_HINTS = {
    "base_url",
    "protocol",
    "image_models",
    "chat_models",
    "video_models",
    "model_display_names",
    "rh_apps",
    "rh_workflows",
    "ms_loras",
    "model_protocols",
}
API_PROVIDER_LIST_KEYS = {"image_models", "chat_models", "video_models", "rh_apps", "rh_workflows", "ms_loras"}
REMOVED_NATIVE_PROVIDER_IDS = {"modelscope"}
API_PROVIDER_BOOL_KEYS = {
    "enabled",
    "primary",
    "connection_ok",
    "required",
    "clear_key",
    "clear_wallet_key",
    "clear_volcengine_access_key_id",
    "clear_volcengine_secret_access_key",
}

BUILTIN_PROVIDER_IDENTITIES = {
    "modelscope": {
        "name": "ModelScope",
        "protocol": "openai",
        "base_url": "https://api-inference.modelscope.cn/v1",
    },
    "runninghub": {
        "name": "RunningHub",
        "protocol": "runninghub",
        "base_url": "https://www.runninghub.ai",
    },
    "volcengine": {
        "name": "火山引擎",
        "protocol": "volcengine",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    },
}


def repair_builtin_provider_identity(provider):
    if not isinstance(provider, dict):
        return provider
    identity = BUILTIN_PROVIDER_IDENTITIES.get(str(provider.get("id") or "").strip())
    if identity:
        # 协议和地址是内置平台身份，保持强制；名称允许用户自定义，仅在为空时回退默认。
        # RunningHub 已解锁（2026-09-10 用户要求全可修改）：协议与地址以用户配置为准，不再强制回填。
        if str(provider.get("id") or "").strip() != "runninghub":
            provider["protocol"] = identity["protocol"]
            provider["base_url"] = identity["base_url"]
        if not str(provider.get("name") or "").strip():
            provider["name"] = identity["name"]
    return provider


def sanitize_api_provider_record(record):
    if not isinstance(record, dict):
        return None
    provider_id = str(record.get("id") or "").strip()
    if provider_id in REMOVED_NATIVE_PROVIDER_IDS:
        return None
    if not provider_id or "::" in provider_id:
        return None
    if provider_id.startswith("app:") or provider_id.startswith("workflow:"):
        return None
    if not any(key in record for key in API_PROVIDER_REQUIRED_HINTS) and provider_id not in {
        "modelscope",
        "runninghub",
        "volcengine",
        "custom-api",
        "custom-api-2",
        "custom-api-3",
    }:
        return None
    safe = {"id": provider_id}
    for key in API_PROVIDER_ALLOWED_KEYS:
        if key == "id" or key not in record:
            continue
        safe[key] = record.get(key)
    for key in API_PROVIDER_LIST_KEYS:
        value = safe.get(key)
        if isinstance(value, list):
            continue
        safe[key] = []
    if provider_id != "runninghub":
        safe["rh_apps"] = []
        safe["rh_workflows"] = []
    model_display_names = safe.get("model_display_names")
    safe["model_display_names"] = model_display_names if isinstance(model_display_names, dict) else {}
    model_protocols = safe.get("model_protocols")
    safe["model_protocols"] = model_protocols if isinstance(model_protocols, dict) else {}
    for key in API_PROVIDER_BOOL_KEYS:
        if key in safe:
            safe[key] = bool(safe.get(key))
    return repair_builtin_provider_identity(safe)


def sanitize_api_providers(items):
    cleaned = []
    seen = set()
    for item in items or []:
        safe = sanitize_api_provider_record(item)
        if not safe:
            continue
        provider_id = safe.get("id")
        if provider_id in seen:
            continue
        seen.add(provider_id)
        cleaned.append(safe)
    return cleaned


def read_asset_library():
    data = read_json_file(asset_library_file_path(), default_asset_library())
    return data if isinstance(data, dict) else default_asset_library()


def write_asset_library(library):
    safe = library if isinstance(library, dict) else default_asset_library()
    safe["updated_at"] = int(time.time() * 1000)
    write_json_file(asset_library_file_path(), safe)
    return safe


def asset_library_payload(library, **extra):
    return {"ok": True, "library": write_asset_library(library), **extra}


def asset_libraries_list(library):
    libs = library.get("libraries") if isinstance(library, dict) else []
    if not isinstance(libs, list) or not libs:
        defaults = default_asset_library()
        library.clear()
        library.update(defaults)
        libs = library.get("libraries") or []
    return libs


def find_asset_library_record(library, library_id="", required=True):
    libs = asset_libraries_list(library)
    wanted = str(library_id or library.get("active_library_id") or "default").strip()
    lib = next((item for item in libs if str(item.get("id") or "") == wanted), None)
    if lib is None and not wanted:
        lib = libs[0] if libs else None
    if lib is None and required:
        raise ApiError(404, "资产库不存在")
    if lib is not None and not isinstance(lib.get("categories"), list):
        lib["categories"] = []
    return lib


def find_asset_category_record(library, category_id="", library_id="", required=True):
    wanted = str(category_id or "").strip()
    libs = [find_asset_library_record(library, library_id)] if str(library_id or "").strip() else asset_libraries_list(library)
    for lib in libs:
        if not lib:
            continue
        cats = lib.get("categories")
        if not isinstance(cats, list):
            cats = []
            lib["categories"] = cats
        for cat in cats:
            if str(cat.get("id") or "") == wanted:
                if not isinstance(cat.get("items"), list):
                    cat["items"] = []
                return lib, cat
    if required:
        raise ApiError(404, "资产分组不存在")
    return None, None


def find_asset_item_record(library, item_id="", library_id="", required=True):
    wanted = str(item_id or "").strip()
    libs = [find_asset_library_record(library, library_id)] if str(library_id or "").strip() else asset_libraries_list(library)
    for lib in libs:
        if not lib:
            continue
        cats = lib.get("categories")
        if not isinstance(cats, list):
            cats = []
            lib["categories"] = cats
        for cat in cats:
            items = cat.get("items")
            if not isinstance(items, list):
                items = []
                cat["items"] = items
            for item in items:
                if str(item.get("id") or "") == wanted:
                    return lib, cat, item
    if required:
        raise ApiError(404, "素材不存在")
    return None, None, None


def find_asset_category(library, library_id="", category_id=""):
    libs = library.get("libraries") if isinstance(library, dict) else []
    if not isinstance(libs, list) or not libs:
        library.update(default_asset_library())
        libs = library.get("libraries") or []
    lib = next((item for item in libs if str(item.get("id") or "") == str(library_id or "")), None)
    if lib is None:
        lib = libs[0]
    cats = lib.get("categories") if isinstance(lib.get("categories"), list) else []
    image_cats = [cat for cat in cats if str(cat.get("type") or "image") == "image"]
    cat = next((item for item in image_cats if str(item.get("id") or "") == str(category_id or "")), None)
    if cat is None:
        if image_cats:
            cat = image_cats[0]
        else:
            cat = {"id": "images", "name": "图片", "type": "image", "items": []}
            cats.append(cat)
            lib["categories"] = cats
    if not isinstance(cat.get("items"), list):
        cat["items"] = []
    return lib, cat


# ====== 资产版本链：同一素材的 v1/v2/... + 引用可"跟最新"或"钉旧版" ======
# 条目结构（向后兼容：老的 url/name 仍是"当前版本指针"）：
#   item = { id, url, name, kind, created_at, updated_at,
#            versions:[{version_id, url, name, kind, created_at, note?}], current_version_id }
# 画布节点里引用资产时带：
#   image = { url, name, assetId, assetVersionMode:"latest"|"pinned", assetVersionId? }
#   - latest：读画布时解析到条目当前版本（源素材重跑出新版，引用处自动跟）
#   - pinned：解析到 assetVersionId 指定的那一版（已出片的镜头钉住不动）

ASSET_VERSION_INDEX_CACHE = {"mtime": None, "index": {}}


def asset_item_versions(item):
    """返回条目的版本链；老条目（没有 versions）自动把自身当作 v1 补齐。"""
    if not isinstance(item, dict):
        return []
    versions = item.get("versions")
    if not isinstance(versions, list) or not versions:
        url = str(item.get("url") or "").strip()
        if not url:
            return []
        head = {
            "version_id": str(item.get("current_version_id") or ("v1_" + str(item.get("id") or uuid.uuid4().hex[:8]))),
            "url": url,
            "name": str(item.get("name") or ""),
            "kind": str(item.get("kind") or "image"),
            "created_at": int(item.get("created_at") or 0),
        }
        item["versions"] = [head]
        item["current_version_id"] = head["version_id"]
        return item["versions"]
    return versions


def append_asset_version(item, url, name="", kind="", note=""):
    """给条目追加一个新版本。返回 (version_entry, created?)；同一地址不重复登记。"""
    versions = asset_item_versions(item)
    target_url = str(url or "").strip()
    if not target_url:
        raise ApiError(400, "新版本缺少素材地址")
    for existing in versions:
        if str(existing.get("url") or "") == target_url:
            return existing, False
    now_ms = int(time.time() * 1000)
    entry = {
        "version_id": "v{}_{}".format(len(versions) + 1, uuid.uuid4().hex[:8]),
        "url": target_url,
        "name": str(name or item.get("name") or "").strip(),
        "kind": str(kind or item.get("kind") or "image").strip(),
        "created_at": now_ms,
    }
    if note:
        entry["note"] = str(note)[:200]
    versions.append(entry)
    item["versions"] = versions
    item["current_version_id"] = entry["version_id"]
    # 当前版本指针（老代码读 url/name/kind 依然正确）
    item["url"] = target_url
    if entry["name"]:
        item["name"] = entry["name"]
    if entry["kind"]:
        item["kind"] = entry["kind"]
    item["updated_at"] = now_ms
    return entry, True


def asset_version_index():
    """{item_id: item} 索引，按资产库文件 mtime 缓存，避免每次读画布都解析大文件。"""
    try:
        path = asset_library_file_path()
        mtime = path.stat().st_mtime
    except Exception:
        return {}
    cache = ASSET_VERSION_INDEX_CACHE
    if cache.get("mtime") == mtime:
        return cache.get("index") or {}
    index = {}
    try:
        library = read_asset_library()
        for lib in library.get("libraries") or []:
            for cat in lib.get("categories") or []:
                for item in cat.get("items") or []:
                    if isinstance(item, dict) and item.get("id"):
                        index[str(item["id"])] = item
    except Exception:
        index = {}
    ASSET_VERSION_INDEX_CACHE["mtime"] = mtime
    ASSET_VERSION_INDEX_CACHE["index"] = index
    return index


def add_asset_library_version(payload):
    """把一张图登记为某个已有素材的新版本。payload: {item_id, url, name?, kind?, note?}"""
    payload = payload if isinstance(payload, dict) else {}
    item_id = str(payload.get("item_id") or payload.get("assetId") or "").strip()
    url = str(payload.get("url") or "").strip()
    if not item_id:
        raise ApiError(400, "缺少 item_id（要更新哪个素材）")
    if not url:
        raise ApiError(400, "缺少 url（新版本的素材地址）")
    library = read_asset_library()
    _lib, _cat, item = find_asset_item_record(library, item_id, payload.get("library_id") or "")
    entry, created = append_asset_version(
        item, url,
        name=str(payload.get("name") or ""),
        kind=str(payload.get("kind") or payload.get("mediaKind") or ""),
        note=str(payload.get("note") or ""))
    saved = write_asset_library(library)
    ASSET_VERSION_INDEX_CACHE["mtime"] = None
    append_log(LOG_FILE, "[AssetVersion] item={} version={} created={}".format(item_id, entry.get("version_id"), created))
    return {
        "ok": True,
        "library": saved,
        "item": item,
        "version": entry,
        "created": created,
        "versionCount": len(item.get("versions") or []),
    }


def resolve_canvas_asset_versions(canvas):
    """按引用策略把画布里的资产引用解析到目标版本（就地改 canvas，返回解析条数）。

    - mode=latest：解析到条目当前版本 → 素材重跑出新版，引用处自动跟
    - mode=pinned：解析到 assetVersionId 指定那版 → 钉住不动
    只处理带 assetId 的引用；老的纯 url 引用一律不碰。
    """
    if not isinstance(canvas, dict):
        return 0
    refs = []
    for node in canvas.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        for image in node.get("images") or []:
            if isinstance(image, dict) and str(image.get("assetId") or "").strip():
                refs.append(image)
    if not refs:
        return 0
    index = asset_version_index()
    if not index:
        return 0
    resolved = 0
    for image in refs:
        item = index.get(str(image.get("assetId") or "").strip())
        if not item:
            continue
        versions = asset_item_versions(item)
        if not versions:
            continue
        mode = str(image.get("assetVersionMode") or "latest").strip().lower()
        target = None
        if mode == "pinned":
            want = str(image.get("assetVersionId") or "").strip()
            target = next((v for v in versions if str(v.get("version_id")) == want), None)
        if target is None:
            want = str(item.get("current_version_id") or "").strip()
            target = next((v for v in versions if str(v.get("version_id")) == want), versions[-1])
        url = str(target.get("url") or "").strip()
        if not url or url == str(image.get("url") or ""):
            continue
        image["url"] = url
        # 只同步地址与类型，不改用户给这条引用起的名字
        if target.get("kind"):
            image["kind"] = str(target.get("kind"))
        image["assetVersionId"] = str(target.get("version_id") or "")
        resolved += 1
    return resolved


def add_asset_library_items(payload):
    payload = payload if isinstance(payload, dict) else {}
    library = read_asset_library()
    library_id = str(payload.get("library_id") or library.get("active_library_id") or "default")
    category_id = str(payload.get("category_id") or "")
    lib, cat = find_asset_category(library, library_id, category_id)
    raw_items = payload.get("items") if isinstance(payload.get("items"), list) else [payload]
    created = []
    now_ms = int(time.time() * 1000)
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url") or "").strip()
        if not url:
            continue
        item = {
            "id": str(raw.get("id") or f"asset_{uuid.uuid4().hex[:10]}"),
            "url": url,
            "name": str(raw.get("name") or Path(urllib.parse.urlparse(url).path).name or "asset"),
            "kind": str(raw.get("kind") or raw.get("mediaKind") or "image"),
            "created_at": now_ms,
            "updated_at": now_ms,
        }
        cat["items"].append(item)
        created.append(item)
    saved = write_asset_library(library)
    return {"ok": True, "library": saved, "item": created[0] if created else None, "items": created}


def create_asset_library_record(payload):
    library = read_asset_library()
    name = clean_asset_name(payload.get("name"), "资产库名称")
    lib = {
        "id": f"asset_lib_{uuid.uuid4().hex[:10]}",
        "name": name,
        "type": "asset",
        "categories": [],
        "created_at": int(time.time() * 1000),
    }
    asset_libraries_list(library).append(lib)
    library["active_library_id"] = lib["id"]
    return asset_library_payload(library, asset_library=lib)


def update_asset_library_record(library_id, payload):
    library = read_asset_library()
    lib = find_asset_library_record(library, library_id)
    lib["name"] = clean_asset_name(payload.get("name"), "资产库名称")
    lib["updated_at"] = int(time.time() * 1000)
    return asset_library_payload(library, asset_library=lib)


def delete_asset_library_record(library_id):
    library = read_asset_library()
    wanted = str(library_id or "").strip()
    libs = asset_libraries_list(library)
    if len(libs) <= 1:
        raise ApiError(400, "至少保留一个资产库")
    before = len(libs)
    library["libraries"] = [lib for lib in libs if str(lib.get("id") or "") != wanted]
    if len(library["libraries"]) == before:
        raise ApiError(404, "资产库不存在")
    if str(library.get("active_library_id") or "") == wanted:
        library["active_library_id"] = library["libraries"][0].get("id") if library["libraries"] else ""
    return asset_library_payload(library)


def create_asset_category_record(payload):
    library = read_asset_library()
    lib = find_asset_library_record(library, payload.get("library_id") or "")
    name = clean_asset_name(payload.get("name"), "分组名称")
    category_type = str(payload.get("type") or "image").strip() or "image"
    cat = {
        "id": f"asset_cat_{uuid.uuid4().hex[:10]}",
        "name": name,
        "type": category_type,
        "items": [],
        "created_at": int(time.time() * 1000),
    }
    cats = lib.get("categories")
    if not isinstance(cats, list):
        cats = []
        lib["categories"] = cats
    cats.append(cat)
    return asset_library_payload(library, category=cat)


def update_asset_category_record(category_id, payload):
    library = read_asset_library()
    _lib, cat = find_asset_category_record(library, category_id, payload.get("library_id") or "")
    cat["name"] = clean_asset_name(payload.get("name"), "分组名称")
    if "type" in payload:
        cat["type"] = str(payload.get("type") or cat.get("type") or "image").strip() or "image"
    cat["updated_at"] = int(time.time() * 1000)
    return asset_library_payload(library, category=cat)


def delete_asset_category_record(category_id):
    library = read_asset_library()
    lib, _cat = find_asset_category_record(library, category_id)
    lib["categories"] = [cat for cat in lib.get("categories", []) if str(cat.get("id") or "") != str(category_id or "")]
    return asset_library_payload(library)


def update_asset_item_record(item_id, payload):
    library = read_asset_library()
    _lib, _cat, item = find_asset_item_record(library, item_id, payload.get("library_id") or "")
    item["name"] = clean_asset_name(payload.get("name"), "素材名称")
    item["updated_at"] = int(time.time() * 1000)
    return asset_library_payload(library, item=item)


def delete_asset_item_record(item_id):
    library = read_asset_library()
    _lib, cat, _item = find_asset_item_record(library, item_id)
    cat["items"] = [item for item in cat.get("items", []) if str(item.get("id") or "") != str(item_id or "")]
    return asset_library_payload(library)


def delete_asset_items_record(payload):
    ids = {str(item or "").strip() for item in (payload.get("ids") if isinstance(payload, dict) else []) or []}
    ids.discard("")
    library = read_asset_library()
    removed = 0
    for lib in asset_libraries_list(library):
        for cat in lib.get("categories", []) if isinstance(lib.get("categories"), list) else []:
            if not isinstance(cat.get("items"), list):
                cat["items"] = []
                continue
            before = len(cat["items"])
            cat["items"] = [item for item in cat["items"] if str(item.get("id") or "") not in ids]
            removed += before - len(cat["items"])
    return asset_library_payload(library, removed=removed)


def move_asset_items_record(payload):
    payload = payload if isinstance(payload, dict) else {}
    ids = {str(item or "").strip() for item in payload.get("ids") or []}
    ids.discard("")
    library = read_asset_library()
    target_library_id = str(payload.get("target_library_id") or payload.get("library_id") or "").strip()
    target_category_id = str(payload.get("target_category_id") or payload.get("category_id") or "").strip()
    _target_lib, target_cat = find_asset_category_record(library, target_category_id, target_library_id)
    moved_items = []
    for lib in asset_libraries_list(library):
        for cat in lib.get("categories", []) if isinstance(lib.get("categories"), list) else []:
            items = cat.get("items")
            if not isinstance(items, list):
                cat["items"] = []
                continue
            remaining = []
            for item in items:
                if str(item.get("id") or "") in ids:
                    moved_items.append(item)
                else:
                    remaining.append(item)
            cat["items"] = remaining
    now_ms = int(time.time() * 1000)
    for item in moved_items:
        item["updated_at"] = now_ms
        target_cat.setdefault("items", []).append(item)
    return asset_library_payload(library, moved=len(moved_items), items=moved_items)


def crop_asset_items_record(payload):
    payload = payload if isinstance(payload, dict) else {}
    ids = {str(item or "").strip() for item in payload.get("ids") or []}
    ids.discard("")
    library = read_asset_library()
    target_library_id = str(payload.get("target_library_id") or payload.get("library_id") or "").strip()
    target_category_id = str(payload.get("target_category_id") or payload.get("category_id") or "").strip()
    if target_category_id:
        _target_lib, target_cat = find_asset_category_record(library, target_category_id, target_library_id)
    else:
        _target_lib, target_cat, _item = find_asset_item_record(library, next(iter(ids), ""), target_library_id)
    added = []
    now_ms = int(time.time() * 1000)
    for item_id in ids:
        _lib, _cat, item = find_asset_item_record(library, item_id, payload.get("library_id") or "", required=False)
        if not item:
            continue
        clone = dict(item)
        clone["id"] = f"asset_{uuid.uuid4().hex[:10]}"
        clone["name"] = f"{str(item.get('name') or 'asset')} 裁剪"
        clone["created_at"] = now_ms
        clone["updated_at"] = now_ms
        target_cat.setdefault("items", []).append(clone)
        added.append(clone)
    return asset_library_payload(library, added=len(added), items=added)

def read_prompt_libraries():
    data = read_json_file(prompt_library_file_path(), default_prompt_library())
    return data if isinstance(data, dict) else default_prompt_library()


PROMPT_BUILTIN_CATEGORY_IDS = {"view", "storyboard", "character", "product", "lighting", "custom"}


def write_prompt_libraries(library):
    safe = library if isinstance(library, dict) else default_prompt_library()
    if not isinstance(safe.get("libraries"), list) or not safe.get("libraries"):
        safe = default_prompt_library()
    safe["updated_at"] = int(time.time() * 1000)
    write_json_file(prompt_library_file_path(), safe)
    return safe


def prompt_library_payload(library, **extra):
    return {"ok": True, "library": write_prompt_libraries(library), **extra}


def prompt_libraries_list(library):
    libs = library.get("libraries") if isinstance(library, dict) else []
    if not isinstance(libs, list) or not libs:
        defaults = default_prompt_library()
        library.clear()
        library.update(defaults)
        libs = library.get("libraries") or []
    return libs


def find_prompt_library_record(library, library_id="", required=True):
    libs = prompt_libraries_list(library)
    wanted = str(library_id or library.get("active_library_id") or "system").strip()
    lib = next((item for item in libs if str(item.get("id") or "") == wanted), None)
    if lib is None and not wanted:
        lib = libs[0] if libs else None
    if lib is None and required:
        raise ApiError(404, "提示词库不存在")
    if lib is not None:
        lib.setdefault("items", [])
        lib.setdefault("categories", [])
    return lib


def find_prompt_category_record(library, category_id="", required=True):
    wanted = str(category_id or "").strip()
    for lib in prompt_libraries_list(library):
        cats = lib.get("categories")
        if not isinstance(cats, list):
            cats = []
            lib["categories"] = cats
        for cat in cats:
            if str(cat.get("id") or "") == wanted:
                return lib, cat
    if required:
        raise ApiError(404, "提示词分组不存在")
    return None, None


def find_prompt_item_record(library, item_id="", library_id="", required=True):
    wanted = str(item_id or "").strip()
    libs = [find_prompt_library_record(library, library_id)] if library_id else prompt_libraries_list(library)
    for lib in libs:
        items = lib.get("items")
        if not isinstance(items, list):
            items = []
            lib["items"] = items
        for item in items:
            if str(item.get("id") or "") == wanted:
                return lib, item
    if required:
        raise ApiError(404, "提示词不存在")
    return None, None


def create_prompt_library_record(payload):
    library = read_prompt_libraries()
    name = clean_prompt_name(payload.get("name"), "提示词库名称")
    lib = {
        "id": f"prompt_lib_{uuid.uuid4().hex[:10]}",
        "name": name,
        "type": "prompt",
        "readonly": False,
        "categories": [],
        "items": [],
        "created_at": int(time.time() * 1000),
    }
    prompt_libraries_list(library).append(lib)
    library["active_library_id"] = lib["id"]
    return prompt_library_payload(library, prompt_library=lib)


def update_prompt_library_record(library_id, payload):
    library = read_prompt_libraries()
    lib = find_prompt_library_record(library, library_id)
    lib["name"] = clean_prompt_name(payload.get("name"), "提示词库名称")
    return prompt_library_payload(library, prompt_library=lib)


def delete_prompt_library_record(library_id):
    library = read_prompt_libraries()
    wanted = str(library_id or "").strip()
    if wanted == "system":
        raise ApiError(400, "系统提示词库不能删除")
    libs = prompt_libraries_list(library)
    before = len(libs)
    library["libraries"] = [lib for lib in libs if str(lib.get("id") or "") != wanted]
    if len(library["libraries"]) == before:
        raise ApiError(404, "提示词库不存在")
    library["active_library_id"] = "system" if any(lib.get("id") == "system" for lib in library["libraries"]) else (library["libraries"][0].get("id") if library["libraries"] else "")
    return prompt_library_payload(library)


def create_prompt_category_record(payload):
    library = read_prompt_libraries()
    lib = find_prompt_library_record(library, payload.get("library_id") or "system")
    name = clean_prompt_name(payload.get("name"), "分组名称")
    cat = {"id": f"prompt_cat_{uuid.uuid4().hex[:10]}", "name": name}
    cats = lib.get("categories")
    if not isinstance(cats, list):
        cats = []
        lib["categories"] = cats
    cats.append(cat)
    return prompt_library_payload(library, category=cat)


def update_prompt_category_record(category_id, payload):
    wanted = str(category_id or "").strip()
    if wanted in PROMPT_BUILTIN_CATEGORY_IDS:
        raise ApiError(400, "内置分组不能编辑")
    library = read_prompt_libraries()
    _lib, cat = find_prompt_category_record(library, wanted)
    cat["name"] = clean_prompt_name(payload.get("name"), "分组名称")
    return prompt_library_payload(library, category=cat)


def delete_prompt_category_record(category_id):
    wanted = str(category_id or "").strip()
    if wanted in PROMPT_BUILTIN_CATEGORY_IDS:
        raise ApiError(400, "内置分组不能删除")
    library = read_prompt_libraries()
    lib, _cat = find_prompt_category_record(library, wanted)
    lib["categories"] = [cat for cat in lib.get("categories", []) if str(cat.get("id") or "") != wanted]
    for item in lib.get("items", []) if isinstance(lib.get("items"), list) else []:
        if str(item.get("category") or "") == wanted:
            item["category"] = "custom"
    return prompt_library_payload(library)


def prompt_item_from_payload(payload, existing=None):
    now_ms = int(time.time() * 1000)
    item = dict(existing or {})
    item["id"] = str(item.get("id") or payload.get("id") or f"prompt_{uuid.uuid4().hex[:10]}")
    item["name"] = clean_prompt_name(payload.get("name"), "提示词名称")
    item["scene"] = str(payload.get("scene") or "").strip()
    item["positive"] = clean_prompt_name(payload.get("positive"), "正向提示词")
    item["negative"] = str(payload.get("negative") or "").strip()
    item["category"] = str(payload.get("category") or item.get("category") or "custom").strip() or "custom"
    item.setdefault("created_at", now_ms)
    item["updated_at"] = now_ms
    return item


def create_prompt_item_record(payload):
    library = read_prompt_libraries()
    lib = find_prompt_library_record(library, payload.get("library_id") or "system")
    item = prompt_item_from_payload(payload)
    items = lib.get("items")
    if not isinstance(items, list):
        items = []
        lib["items"] = items
    items.append(item)
    return prompt_library_payload(library, item=item)


def update_prompt_item_record(item_id, payload):
    library = read_prompt_libraries()
    lib, item = find_prompt_item_record(library, item_id, payload.get("library_id") or "")
    updated = prompt_item_from_payload(payload, existing=item)
    items = lib.get("items") if isinstance(lib.get("items"), list) else []
    for index, current in enumerate(items):
        if str(current.get("id") or "") == str(item_id or ""):
            items[index] = updated
            break
    return prompt_library_payload(library, item=updated)


def delete_prompt_item_record(item_id):
    library = read_prompt_libraries()
    lib, _item = find_prompt_item_record(library, item_id)
    lib["items"] = [item for item in lib.get("items", []) if str(item.get("id") or "") != str(item_id or "")]
    return prompt_library_payload(library)


def delete_prompt_items_record(payload):
    ids = {str(item or "").strip() for item in (payload.get("ids") if isinstance(payload, dict) else []) or []}
    ids.discard("")
    library = read_prompt_libraries()
    for lib in prompt_libraries_list(library):
        if isinstance(lib.get("items"), list):
            lib["items"] = [item for item in lib["items"] if str(item.get("id") or "") not in ids]
    return prompt_library_payload(library)


def read_comfy_instances():
    data = read_json_file(comfy_instances_file_path(), {"instances": []})
    if isinstance(data, dict):
        items = data.get("instances")
        return normalize_comfy_instances(items)
    if isinstance(data, list):
        return normalize_comfy_instances(data)
    return []


def normalize_comfy_instances(instances):
    safe = []
    seen = set()
    for item in instances if isinstance(instances, list) else []:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        safe.append(text)
    return safe


def list_workflow_records():
    seen = set()
    records = []
    for root, builtin in workflow_search_roots():
        try:
            files = sorted(root.glob("*.json"))
        except Exception:
            files = []
        for path in files:
            if path.name.endswith(".config.json"):
                continue
            normalized_name = path.name
            if normalized_name in seen:
                continue
            seen.add(normalized_name)
            config_path = path.with_suffix(".config.json")
            config = read_json_file(config_path, {})
            record = {
                "name": normalized_name,
                "title": str(config.get("title") or workflow_title_from_name(normalized_name)).strip() or workflow_title_from_name(normalized_name),
                "field_count": workflow_field_count(config),
                "builtin": bool(builtin),
                "path": str(path),
            }
            group = config.get("group") if isinstance(config.get("group"), dict) else None
            if group and str(group.get("id") or "").strip():
                record["group"] = {"id": str(group.get("id")), "title": str(group.get("title") or group.get("id"))}
            records.append(record)
    records.sort(key=lambda item: (not bool(item.get("builtin")), str(item.get("title") or "").lower(), str(item.get("name") or "").lower()))
    return records


def find_workflow_files(name):
    file_name, candidates = workflow_file_candidates(name)
    for workflow_path, config_path, builtin in candidates:
        if workflow_path.exists():
            return file_name, workflow_path, config_path, builtin
    raise ApiError(404, f"Workflow not found: {file_name}")


def read_workflow_record(name):
    file_name, workflow_path, config_path, builtin = find_workflow_files(name)
    workflow = read_json_file(workflow_path, None)
    if not isinstance(workflow, dict):
        raise ApiError(500, f"工作流文件损坏: {file_name}")
    config = read_json_file(config_path, {})
    if not isinstance(config, dict):
        config = {}
    config.setdefault("title", workflow_title_from_name(file_name))
    config.setdefault("fields", [])
    config.setdefault("mini_cards", {})
    return {
        "name": file_name,
        "workflow": workflow,
        "config": config,
        "builtin": bool(builtin),
    }


def build_local_config_payload():
    providers = read_api_providers()
    image_models = []
    chat_models = []
    video_models = []
    ms_chat_models = []
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        image_models.extend([item for item in (provider.get("image_models") or []) if isinstance(item, str) and item.strip()])
        chat_models.extend([item for item in (provider.get("chat_models") or []) if isinstance(item, str) and item.strip()])
        video_models.extend([item for item in (provider.get("video_models") or []) if isinstance(item, str) and item.strip()])
        if str(provider.get("id") or "").strip() == "modelscope":
            ms_chat_models.extend([item for item in (provider.get("chat_models") or []) if isinstance(item, str) and item.strip()])
    return {
        "image_models": sorted(set(image_models)),
        "chat_models": sorted(set(chat_models)),
        "video_models": sorted(set(video_models)),
        "ms_chat_models": sorted(set(ms_chat_models)),
        "api_providers": providers,
        "comfy_instances": read_comfy_instances(),
        "image_model": (sorted(set(image_models))[0] if image_models else ""),
    }


def output_asset_kind_for_name(name=""):
    ext = str(Path(str(name or "")).suffix or "").lower()
    if ext in OUTPUT_VIDEO_EXTS:
        return "video"
    if ext in OUTPUT_IMAGE_EXTS:
        return "image"
    return ""


def output_asset_subdir_for_kind(kind="image"):
    text = str(kind or "").strip().lower()
    if text == "video":
        return "videos"
    if text == "image":
        return "images"
    return ""


def output_asset_fallback_paths(decoded):
    text = str(decoded or "").replace("\\", "/")
    if not text.startswith("output/"):
        return []
    name = Path(text).name
    if not name:
        return []
    root = ASSETS_DIR / "output"
    kind = output_asset_kind_for_name(name)
    candidates = []
    if text.startswith("output/history/"):
        candidates.append(root / "images" / "history" / name)
        return [path.resolve() for path in candidates]
    if text.startswith("output/images/history/"):
        candidates.append(root / "history" / name)
    elif text.startswith("output/images/"):
        candidates.extend([root / "images" / "history" / name, root / "history" / name])
    elif text.startswith("output/videos/"):
        candidates.append(root / name)
    else:
        if kind == "video":
            candidates.append(root / "videos" / name)
        else:
            candidates.extend([root / "images" / name, root / "images" / "history" / name, root / "history" / name])
    return [path.resolve() for path in candidates]


def resolve_user_asset_path(url_path):
    raw = urllib.parse.urlparse(str(url_path or "")).path or ""
    if not raw.startswith("/assets/"):
        raise ApiError(404, "asset not found")
    relative = raw[len("/assets/"):]
    if not relative:
        raise ApiError(404, "asset not found")
    decoded = urllib.parse.unquote(relative)
    target = (ASSETS_DIR / decoded).resolve()
    asset_root = ASSETS_DIR.resolve()
    try:
        target.relative_to(asset_root)
    except Exception as exc:
        raise ApiError(403, "forbidden") from exc
    if not target.exists() or not target.is_file():
        if decoded.startswith("output/"):
            for fallback in output_asset_fallback_paths(decoded):
                try:
                    fallback.relative_to(asset_root)
                except Exception as exc:
                    raise ApiError(403, "forbidden") from exc
                if fallback.exists() and fallback.is_file():
                    return fallback
        raise ApiError(404, "asset not found")
    return target


def canvas_thumbnail_path(source_url, max_edge=640):
    raw_url = str(source_url or "")
    parsed_path = urllib.parse.urlparse(raw_url).path or ""
    if not parsed_path.startswith("/assets/"):
        raise ApiError(404, "asset not found")
    source = resolve_user_asset_path(parsed_path)
    mime_type = mimetypes.guess_type(source.name)[0] or ""
    if not mime_type.startswith("image/"):
        raise ApiError(415, "thumbnail source must be an image")

    edge = max(160, min(1024, int(max_edge or 640)))
    stat = source.stat()
    cache_key = hashlib.sha256(
        f"{source}|{stat.st_mtime_ns}|{stat.st_size}|{edge}".encode("utf-8")
    ).hexdigest()
    cache_dir = USER_DATA_DIR / "cache" / "canvas_thumbnails"
    target = cache_dir / f"{cache_key}.webp"
    if target.exists() and target.is_file():
        return target

    try:
        from PIL import Image, ImageOps
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            image.thumbnail((edge, edge), Image.Resampling.LANCZOS)
            payload = io.BytesIO()
            image.save(payload, "WEBP", quality=76, method=4)
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(422, "unable to create canvas thumbnail") from exc

    cache_dir.mkdir(parents=True, exist_ok=True)
    temporary = cache_dir / f".{cache_key}.{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_bytes(payload.getvalue())
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
    return target


def canvas_image_info(source_url):
    raw_url = str(source_url or "")
    parsed_path = urllib.parse.urlparse(raw_url).path or ""
    if not parsed_path.startswith("/assets/"):
        raise ApiError(404, "asset not found")
    source = resolve_user_asset_path(parsed_path)
    mime_type = mimetypes.guess_type(source.name)[0] or ""
    if not mime_type.startswith("image/"):
        raise ApiError(415, "source must be an image")
    try:
        from PIL import Image, ImageOps
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            width, height = image.size
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(422, "unable to read image info") from exc
    stat = source.stat()
    return {
        "ok": True,
        "width": int(width),
        "height": int(height),
        "mime": mime_type,
        "size": int(stat.st_size),
    }


def user_model_prefs_path():
    return USER_DATA_DIR / "data" / "user_model_prefs.json"


def read_user_model_prefs():
    try:
        data = json.loads(user_model_prefs_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def write_user_model_prefs(providers):
    prefs = {}
    for p in providers if isinstance(providers, list) else []:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "").strip()
        if not pid:
            continue
        entry = {}
        for key in ("image_models", "video_models"):
            models = p.get(key)
            if isinstance(models, list):
                entry[key] = list(models)
        if entry:
            prefs[pid] = entry
    write_json_file(user_model_prefs_path(), prefs)


def write_api_providers(providers):
    persist_api_provider_keys(providers)
    safe = sanitize_api_providers(providers if isinstance(providers, list) else [])
    write_json_file(providers_file_path(), safe)
    write_user_model_prefs(providers)
    return enrich_api_provider_key_meta(safe)


def write_comfy_instances(instances):
    safe = normalize_comfy_instances(instances)
    write_json_file(comfy_instances_file_path(), {"instances": safe})
    return safe


def comfy_instance_base():
    instances = read_comfy_instances()
    raw = instances[0] if instances else "127.0.0.1:8188"
    base = str(raw or "").strip()
    if not base:
        base = "127.0.0.1:8188"
    if not re.match(r"^https?://", base, re.I):
        base = "http://" + base
    return base.rstrip("/")


def comfy_request_json(base, path, method="GET", payload=None, timeout=120):
    raw = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(base + path, data=raw, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    return json.loads(body.decode("utf-8") or "{}")


def apply_comfy_workflow_fields(workflow, config, fields):
    result = json.loads(json.dumps(workflow if isinstance(workflow, dict) else {}))
    safe_config = config if isinstance(config, dict) else {}
    safe_fields = fields if isinstance(fields, dict) else {}
    applied_media = []
    for field in safe_config.get("fields") or []:
        if not isinstance(field, dict):
            continue
        node_id = str(field.get("node") or "").strip()
        input_key = str(field.get("input") or "").strip()
        if not node_id or not input_key or node_id not in result:
            continue
        supplied = field.get("id") in safe_fields
        value = safe_fields.get(field.get("id"), field.get("default"))
        field_type = str(field.get("type") or "").lower()
        field_id = field.get("id")
        if field_type in ("number", "slider"):
            try:
                value = float(value)
                if value.is_integer():
                    value = int(value)
            except Exception:
                pass
        elif field_type == "boolean":
            value = bool(value)
        result.setdefault(node_id, {}).setdefault("inputs", {})[input_key] = value
        if field_type in {"image", "video", "audio"}:
            applied_media.append({
                "id": str(field_id or ""),
                "type": field_type,
                "node": node_id,
                "input": input_key,
                "value": str(value or "")[:240],
                "supplied": supplied,
            })
    if applied_media:
        append_log(LOG_FILE, "comfy workflow media fields applied " + json.dumps(applied_media, ensure_ascii=False))
    return result


def comfy_output_asset_url(base, item, prompt_id, kind="image", canvas_title="", canvas_id=""):
    filename = str(item.get("filename") or "").strip()
    if not filename:
        return ""
    params = {
        "filename": filename,
        "type": str(item.get("type") or "output"),
        "subfolder": str(item.get("subfolder") or ""),
    }
    url = base + "/view?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=120) as response:
        raw = response.read()
    media_kind = str(kind or "image").strip().lower() or "image"
    canvas_folder = canvas_output_folder_name(canvas_title, canvas_id) if canvas_title or canvas_id else ""
    output_dir = asset_output_media_dir(media_kind, canvas_folder)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^0-9A-Za-z._-]+", "_", filename)
    target = output_dir / f"comfy_{prompt_id}_{safe_name}"
    target.write_bytes(raw)
    return asset_output_url(target.name, media_kind, canvas_folder=canvas_folder)


# 工作流卡片节点依赖的服务层：节点元数据缓存与异步任务队列。
# 宿主能力在这里注入，服务层不反向 import 本模块。
comfy_flow_service.configure(
    base_provider=comfy_instance_base,
    asset_saver=comfy_output_asset_url,
    cache_path=USER_DATA_DIR / "cache" / "comfy_object_info.json",
    job_store_path=USER_DATA_DIR / "data" / "comfy_jobs.json",
)


def select_comfy_output_nodes(history):
    outputs = history.get("outputs") if isinstance(history, dict) else {}
    if not isinstance(outputs, dict):
        return []
    image_nodes = []
    video_nodes = []
    for node_id, node_output in outputs.items():
        if not isinstance(node_output, dict):
            continue
        if node_output.get("images"):
            image_nodes.append((str(node_id), node_output))
        elif node_output.get("videos") or node_output.get("gifs") or node_output.get("video"):
            video_nodes.append((str(node_id), node_output))
    if len(image_nodes) > 1:
        return [image_nodes[-1]]
    if image_nodes:
        return image_nodes
    if len(video_nodes) > 1:
        return [video_nodes[-1]]
    return video_nodes


def run_comfy_workflow(name, payload):
    record = read_workflow_record(name)
    config = payload.get("config") if isinstance(payload.get("config"), dict) else record.get("config")
    modes = payload.get("modes") if isinstance(payload.get("modes"), dict) else None
    if modes:
        # 画布生成节点传来的节点开关（bypass / mute），交给编译器改写整张图。
        # 这一步是必需的：ComfyUI 的 /prompt 不认识 mode 字段，bypass 得自己算。
        # 先应用暴露字段（提示词/参数），再叠加节点开关，两者可同时生效。
        base_prompt = apply_comfy_workflow_fields(
            record.get("workflow") if isinstance(record.get("workflow"), dict) else {},
            config,
            payload.get("fields"),
        )
        if isinstance(payload.get("params"), dict) and payload.get("params"):
            base_prompt = json.loads(json.dumps(base_prompt or {}))
            for node_id, overrides in payload.get("params", {}).items():
                if not isinstance(overrides, dict) or str(node_id) not in base_prompt:
                    continue
                base_prompt[str(node_id)].setdefault("inputs", {}).update(overrides)
        prompt, _report = compile_comfy_prompt(
            base_prompt or {},
            {},
            modes,
            comfy_flow_service.load_object_info(),
        )
    elif isinstance(payload.get("params"), dict):
        # Canvas custom-Comfy calls already provide node/input overrides.
        # Keep this path local to Comfy workflow execution; legacy API modes
        # continue to use their existing compatibility handler.
        prompt = json.loads(json.dumps(record.get("workflow") if isinstance(record.get("workflow"), dict) else {}))
        for node_id, overrides in payload.get("params", {}).items():
            if not isinstance(overrides, dict) or str(node_id) not in prompt:
                continue
            prompt[str(node_id)].setdefault("inputs", {}).update(overrides)
    else:
        prompt = apply_comfy_workflow_fields(record.get("workflow"), config, payload.get("fields"))
    if not prompt:
        raise ApiError(400, "工作流为空")
    base = comfy_instance_base()
    client_id = str(payload.get("client_id") or uuid.uuid4().hex)
    submitted = comfy_request_json(base, "/prompt", "POST", {"prompt": prompt, "client_id": client_id}, timeout=120)
    prompt_id = str(submitted.get("prompt_id") or "")
    if not prompt_id:
        raise ApiError(502, "ComfyUI 未返回 prompt_id")
    started_at = time.time()
    append_log(LOG_FILE, f"comfy workflow submitted name={name} prompt_id={prompt_id} timeout={COMFY_WORKFLOW_POLL_TIMEOUT_SECONDS}s")
    history = {}
    deadline = started_at + COMFY_WORKFLOW_POLL_TIMEOUT_SECONDS
    while time.time() < deadline:
        history_all = comfy_request_json(base, "/history/" + urllib.parse.quote(prompt_id), "GET", timeout=30)
        history = history_all.get(prompt_id) if isinstance(history_all, dict) else None
        if history:
            break
        time.sleep(1)
    if not history:
        elapsed = int(time.time() - started_at)
        append_log(LOG_FILE, f"comfy workflow timeout name={name} prompt_id={prompt_id} elapsed={elapsed}s")
        raise ApiError(504, f"ComfyUI 执行超时：已等待 {elapsed} 秒，工作流可能仍在后台运行。")
    canvas_title = str(payload.get("canvas_title") or "").strip()
    canvas_id = str(payload.get("canvas_id") or "").strip()
    images = []
    videos = []
    output_nodes = select_comfy_output_nodes(history)
    for _node_id, node_output in output_nodes:
        for item in node_output.get("images") or []:
            url = comfy_output_asset_url(base, item, prompt_id, "image", canvas_title, canvas_id)
            if url:
                images.append(url)
        for item in (node_output.get("videos") or []) + (node_output.get("gifs") or []):
            url = comfy_output_asset_url(base, item, prompt_id, "video", canvas_title, canvas_id)
            if url:
                videos.append(url)
    append_log(LOG_FILE, f"comfy workflow succeeded name={name} prompt_id={prompt_id} elapsed={int(time.time() - started_at)}s images={len(images)} videos={len(videos)}")
    return {"ok": True, "prompt_id": prompt_id, "images": images, "videos": videos}


def recent_comfy_outputs(payload=None):
    payload = payload if isinstance(payload, dict) else {}
    limit = max(1, min(20, int(payload.get("limit") or 6)))
    base = comfy_instance_base()
    history_all = comfy_request_json(base, "/history", "GET", timeout=30)
    # 只归档 MyridTV 自己提交的任务：外部（含 ComfyUI 网页手动跑）的 prompt 不落盘，
    # 防止窗口 focus 时把别人的图拷进 assets/output/images/history。
    known_ids = set()
    try:
        for job in comfy_flow_service.MANAGER.list_jobs(limit=100):
            pid = str(job.get("prompt_id") or "").strip()
            if pid:
                known_ids.add(pid)
    except Exception:
        pass
    rows = []
    if isinstance(history_all, dict):
        for prompt_id, history in history_all.items():
            if str(prompt_id) not in known_ids:
                continue
            if not isinstance(history, dict):
                continue
            order = 0
            prompt_info = history.get("prompt")
            if isinstance(prompt_info, list) and prompt_info:
                try:
                    order = int(prompt_info[0])
                except Exception:
                    order = 0
            images = []
            videos = []
            for _node_id, node_output in select_comfy_output_nodes(history):
                if not isinstance(node_output, dict):
                    continue
                for item in node_output.get("images") or []:
                    url = comfy_output_asset_url(base, item, str(prompt_id), "image")
                    if url:
                        images.append(url)
                for item in (node_output.get("videos") or []) + (node_output.get("gifs") or []):
                    url = comfy_output_asset_url(base, item, str(prompt_id), "video")
                    if url:
                        videos.append(url)
            if images or videos:
                rows.append({"prompt_id": str(prompt_id), "order": order, "images": images, "videos": videos})
    rows.sort(key=lambda item: int(item.get("order") or 0), reverse=True)
    return {"ok": True, "outputs": rows[:limit]}


def comfy_workflow_split_clusters(workflow):
    """多管线集合检测：按输出节点沿上游回溯聚簇。

    返回 (clusters, dropped)：
    - clusters: [{"nodes": {id: node}, "save_id": 输出节点id}, ...]，按簇规模降序
    - dropped: 未归属任何簇的节点 id 集合（悬空预览、未连线节点、多余原图 SaveImage）
    只有聚出 >=2 个互不重叠的簇才视为集合；单输出或交叠图（同一链上双 SaveImage）返回 ([], set())。
    """
    if not isinstance(workflow, dict) or not workflow:
        return [], set()

    def upstream(nid):
        seen = set()
        stack = [nid]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            node = workflow.get(cur)
            if not isinstance(node, dict):
                continue
            for value in (node.get("inputs") or {}).values():
                if isinstance(value, list) and len(value) == 2 and str(value[0]) in workflow:
                    stack.append(str(value[0]))
        return seen

    save_ids = [str(nid) for nid, node in workflow.items()
                if isinstance(node, dict) and str(node.get("class_type") or "").lower() in ("saveimage", "vhs_videocombine")]
    if len(save_ids) < 2:
        return [], set()
    clusters = []
    claimed = set()
    for sid in sorted(save_ids, key=lambda x: -len(upstream(x))):
        nodes = upstream(sid)
        if not nodes or (nodes & claimed):
            continue  # 与更大簇共享节点（同一链上的双 SaveImage）→ 不独立成簇
        claimed |= nodes
        clusters.append({"nodes": {nid: workflow[nid] for nid in nodes}, "save_id": sid})
    if len(clusters) < 2:
        return [], set()
    clusters.sort(key=lambda c: -len(c["nodes"]))
    dropped = {str(nid) for nid in workflow if nid not in claimed}
    return clusters, dropped


def create_workflow_record(name, workflow):
    file_name, _ = workflow_file_candidates(name)
    workflow_path = ROOT / "workflows" / "custom" / file_name
    if workflow_path.exists():
        raise ApiError(409, f"工作流已存在: {file_name}")

    # 多管线集合导入：一个 json 文件里装了几条互不重叠的生成管线时，
    # 自动拆成 N 个独立工作流注册成同一组（组名 = 导入名），画布端按组折叠显示。
    clusters, dropped = comfy_workflow_split_clusters(workflow)
    if clusters:
        base_title = workflow_title_from_name(file_name)
        group = {"id": re.sub(r"\.json$", "", file_name), "title": base_title}
        for index, cluster in enumerate(clusters, start=1):
            member_name = f"{base_title}-{index}.json" if len(clusters) > 1 else file_name
            member_path = ROOT / "workflows" / "custom" / member_name
            if member_path.exists():
                raise ApiError(409, f"工作流已存在: {member_name}")
            write_json_file(member_path, cluster["nodes"])
            config_path = member_path.with_suffix(".config.json")
            if not config_path.exists():
                write_json_file(config_path, {
                    "title": f"{base_title}-{index}",
                    "fields": [],
                    "mini_cards": {},
                    "group": group,
                    "imported_from": file_name,
                })
        append_log(LOG_FILE, f"comfy workflow pack imported {file_name} -> {len(clusters)} members, dropped={len(dropped)} nodes")
        first = read_workflow_record(f"{base_title}-1.json" if len(clusters) > 1 else file_name)
        first["pack"] = {
            "id": group["id"],
            "title": base_title,
            "members": [{"name": f"{base_title}-{i}.json", "title": f"{base_title}-{i}"} for i in range(1, len(clusters) + 1)],
        }
        return first

    write_json_file(workflow_path, workflow if isinstance(workflow, dict) else {})
    config_path = workflow_path.with_suffix(".config.json")
    if not config_path.exists():
        write_json_file(config_path, {"title": workflow_title_from_name(file_name), "fields": [], "mini_cards": {}})
    return read_workflow_record(file_name)


def save_workflow_config(name, config):
    file_name, workflow_path, config_path, _builtin = find_workflow_files(name)
    if not workflow_path.exists():
        raise ApiError(404, f"Workflow not found: {file_name}")
    safe = config if isinstance(config, dict) else {}
    safe.setdefault("title", workflow_title_from_name(file_name))
    safe.setdefault("fields", [])
    safe.setdefault("mini_cards", {})
    write_json_file(config_path, safe)
    return read_workflow_record(file_name)


def delete_workflow_record(name):
    file_name, workflow_path, config_path, builtin = find_workflow_files(name)
    if builtin:
        raise ApiError(403, "内置工作流不能删除")
    if workflow_path.exists():
        workflow_path.unlink()
    if config_path.exists():
        config_path.unlink()
    return {"ok": True, "name": file_name}


def parse_workflow_route(request_path):
    prefix = "/api/workflows"
    if request_path == prefix:
        return ("collection", "")
    if not request_path.startswith(prefix + "/"):
        return (None, "")
    tail = request_path[len(prefix) + 1:]
    for suffix, route_name in (
        ("/config", "config"),
        ("/run", "run"),
    ):
        if tail.endswith(suffix):
            return (route_name, urllib.parse.unquote(tail[:-len(suffix)]))
    return ("item", urllib.parse.unquote(tail))


def guess_kind_from_name(name, mime_type=""):
    mime_text = str(mime_type or "").lower()
    if mime_text.startswith("video/"):
        return "video"
    if mime_text.startswith("audio/"):
        return "audio"
    text = str(name or "").lower()
    if re.search(r"\.(mp4|webm|mov|m4v|avi|mkv)$", text):
        return "video"
    if re.search(r"\.(mp3|wav|m4a|aac|ogg|flac)$", text):
        return "audio"
    return "image"


def sanitize_file_name(name, mime_type="", fallback="blender-frame.png"):
    raw = str(name or fallback).strip() or fallback
    raw = raw.replace("\\", "_").replace("/", "_")
    raw = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._") or fallback
    if "." not in Path(raw).name:
        ext = mimetypes.guess_extension(str(mime_type or "").strip(), strict=False) or ".png"
        if ext == ".jpe":
            ext = ".jpg"
        raw += ext
    return raw[:180]


def decode_blender_payload_asset(payload):
    mime_type = str(payload.get("mime_type") or "image/png").strip() or "image/png"
    file_name = sanitize_file_name(payload.get("file_name") or payload.get("name") or "blender-frame.png", mime_type=mime_type)
    encoded = str(payload.get("file_base64") or payload.get("image_base64") or "").strip()
    if not encoded:
        raise RuntimeError("缺少 file_base64 或 image_base64")
    if "," in encoded and encoded.lower().startswith("data:"):
        header, encoded = encoded.split(",", 1)
        detected_mime = header.split(";", 1)[0].split(":", 1)[-1].strip()
        if detected_mime and not payload.get("mime_type"):
            mime_type = detected_mime
    encoded = re.sub(r"\s+", "", encoded)
    try:
        data = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise RuntimeError("file_base64 无法解码") from exc
    return {
        "file_name": file_name,
        "mime_type": mime_type,
        "data": data,
    }


def save_blender_payload_asset(payload):
    decoded = decode_blender_payload_asset(payload)
    file_name = decoded["file_name"]
    mime_type = decoded["mime_type"]
    data = decoded["data"]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    unique_name = f"{stamp}_{uuid.uuid4().hex[:8]}_{file_name}"
    # 插件回传（视频/截图）统一走画布输出目录 assets/output/<画布名>/{videos,images}/
    is_video = str(mime_type or "").startswith("video")
    if is_video:
        sub = "videos"
    else:
        sub = "images"
    canvas_title = ""
    try:
        cid = str(payload.get("canvas_id") or "").strip()
        if cid:
            cpath = smart_canvas_path(cid)
            if cpath.exists():
                canvas_title = str((read_json_file(cpath, {}) or {}).get("title") or "").strip()
    except Exception:
        canvas_title = ""
    folder = canvas_title or "未命名画布"
    target_dir = ASSETS_DIR / "output" / folder / sub
    url = f"/assets/output/{urllib.parse.quote(folder)}/{sub}/{urllib.parse.quote(unique_name)}"
    target = target_dir / unique_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {
        "name": file_name,
        "url": url,
        "local_path": str(target),
        "mime_type": mime_type,
        "kind": guess_kind_from_name(file_name, mime_type),
        "size_bytes": len(data),
    }


def canvas_file_path(canvas_id):
    safe_id = str(canvas_id or "").strip()
    if not safe_id:
        raise ApiError(400, "缺少 canvas_id")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", safe_id):
        raise ApiError(400, "canvas_id 非法")
    return USER_DATA_DIR / "data" / "canvases" / f"{safe_id}.json"


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
                append_log(LOG_FILE, "[CanvasFormat] canvas={} 迁移到 formatVersion={}".format(canvas_id, version))
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
    }


def read_canvas_record(canvas_id, include_deleted=True):
    path = canvas_file_path(canvas_id)
    if not path.exists():
        raise ApiError(404, f"目标画布不存在: {canvas_id}")
    canvas = normalize_canvas_structure(canvas_id, read_json_file(path, {}))
    try:
        # 引用策略解析：带 assetId 的引用按 latest/pinned 解析到目标版本（无引用时零开销）
        resolve_canvas_asset_versions(canvas)
    except Exception as exc:
        append_log(LOG_FILE, "[AssetVersion] resolve failed canvas={} err={}".format(canvas_id, exc))
    if canvas.get("deleted_at") and not include_deleted:
        raise ApiError(404, "目标画布已在回收站")
    return canvas


def list_canvas_records(include_deleted=False):
    canvas_dir = USER_DATA_DIR / "data" / "canvases"
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
    canvas_dir = USER_DATA_DIR / "data" / "canvases"
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
                append_log(LOG_FILE, f"purge_all_trash failed for {path.name}: {exc}")
    return {"ok": True, "purged": len(purged_ids), "ids": purged_ids}


# ====== 画布导出 / 导入（带格式版本的信封）======
# 导出文件结构：{app, version, exportedAt, source, media, canvas}
#   - version 是"导出文件格式"版本（与画布自身 formatVersion 分开：一个是文件信封，一个是数据格式）
#   - 导入时：带信封的按版本校验（高于当前支持版本直接拒绝）；裸画布 JSON 也接受（老文件/手工文件）
CANVAS_EXPORT_APP = "myridtv"
CANVAS_EXPORT_VERSION = 1


def app_version_string():
    try:
        return (APP_DIR / "VERSION").read_text(encoding="utf-8").strip()
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
            resolve_user_asset_path(url)
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
    append_log(LOG_FILE, "[CanvasImport] new={} title={} media={} missing={}".format(
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


def next_blender_node_position(canvas, node_type=None, node_title=None):
    nodes = canvas.get("nodes") or []
    # 排版规则：四区域固定布局
    # 1. 文本列（普通文本/剧本/大纲）：x=0，y 递增（竖排），间距 320px
    # 2. 人物列（角色卡/人物设定）：x=420，y 递增（竖排），间距 320px
    # 3. 资产行（图片生成节点/参考素材）：y=0，x 从 840 递增（横排），间距 420px
    # 4. 视频区（镜头/分镜/视频预览）：x=840，y 从 360 递增，间距 320px

    def is_text_node(node):
        # 普通文本节点：type=smart-prompt 或无类型（兼容旧节点），非人物
        t = node.get("type")
        title = str(node.get("title") or "").lower()
        return (t in ("smart-prompt", None, "")) and not any(k in title for k in ["角色", "人物", "主角", "配角"])

    def is_character_node(node):
        # 人物角色节点：type=smart-prompt 或无类型，标题含角色相关词
        t = node.get("type")
        title = str(node.get("title") or "").lower()
        return (t in ("smart-prompt", None, "")) and any(k in title for k in ["角色", "人物", "主角", "配角"])

    def is_asset_node(node):
        # 资产节点：type=smart-image 或空（图片生成/参考素材）
        t = node.get("type")
        return t in ("smart-image", "", None)

    def is_video_node(node):
        # 视频/镜头节点：标题含视频/镜头/分镜，放在x840 y360开始
        title = str(node.get("title") or "").lower()
        return any(k in title for k in ["视频", "镜头", "分镜", "动画"])

    def node_height(node):
        explicit_h = parse_number(node.get("h"), 0) or 0
        scale = parse_number(node.get("scale"), 2) or 2
        base = explicit_h if explicit_h > 24 else 210 * max(scale, 1)
        return max(base, 210) + 320  # + 间距

    def node_width(node):
        explicit_w = parse_number(node.get("w"), 0) or 0
        scale = parse_number(node.get("scale"), 2) or 2
        base = explicit_w if explicit_w > 24 else 280 * max(scale, 1)
        return max(base, 280) + 420  # + 间距

    # 统计各区域最大位置
    # 文本区域统计
    text_nodes = [n for n in nodes if is_text_node(n)]
    max_y_text = 0
    if text_nodes:
        max_y_text = max((parse_number(n.get("y"), 0) or 0) + node_height(n) for n in text_nodes)

    # 人物区域统计
    char_nodes = [n for n in nodes if is_character_node(n)]
    max_y_char = 0
    if char_nodes:
        max_y_char = max((parse_number(n.get("y"), 0) or 0) + node_height(n) for n in char_nodes)

    # 资产区域统计（不含视频）
    asset_nodes = [n for n in nodes if is_asset_node(n) and not is_video_node(n)]
    max_x_asset = 840 - 420  # 第一个资产从840开始，所以初始是 840 - 间距
    if asset_nodes:
        max_x_asset = max((parse_number(n.get("x"), 0) or 0) + node_width(n) for n in asset_nodes)

    # 视频区域统计
    video_nodes = [n for n in nodes if is_video_node(n)]
    max_y_video = 360 - 320  # 第一个视频从360开始
    if video_nodes:
        max_y_video = max((parse_number(n.get("y"), 0) or 0) + node_height(n) for n in video_nodes)

    # 根据当前节点类型选择位置
    node_t = node_type
    if node_t is None:
        node_t = "smart-image"  # 默认资产
    title_lower = str(node_title).lower()

    if (node_t == "smart-prompt" and not any(k in title_lower for k in ["角色", "人物", "主角", "配角"])):
        # 普通文本：左列 x=0，y递增
        return {"x": 0, "y": round(max_y_text, 3)}
    elif (node_t == "smart-prompt" and any(k in title_lower for k in ["角色", "人物", "主角", "配角"])):
        # 人物角色：中列 x=420，y递增
        return {"x": 420, "y": round(max_y_char, 3)}
    elif (node_t in ("smart-image", "", None) and any(k in title_lower for k in ["视频", "镜头", "分镜", "动画"])):
        # 视频镜头：右列下区 x=840，y从360递增
        return {"x": 840, "y": round(max_y_video, 3)}
    else:
        # 资产/参考图片：右上横排 y=0，x从840递增
        return {"x": round(max_x_asset, 3), "y": 0}

    # 兜底：原逻辑
    image_nodes = [node for node in nodes if isinstance(node, dict) and (node.get("type") in ("smart-image", "", None))]
    anchor = max(
        image_nodes,
        key=lambda node: (
            (parse_number(node.get("x"), 0) or 0) + node_width(node),
            (parse_number(node.get("y"), 0) or 0),
            parse_number(node.get("created_at"), 0) or 0,
        ),
    )
    return {
        "x": round((parse_number(anchor.get("x"), 0) or 0) + node_width(anchor) + 96, 3),
        "y": round((parse_number(anchor.get("y"), 0) or 0), 3),
    }


def build_blender_media_item(saved_asset, payload):
    camera_name = str(payload.get("camera_name") or "").strip()
    title_name = str(payload.get("node_title") or payload.get("title") or "").strip()
    display_name = camera_name or title_name or "Viewport"
    item = {
        "url": saved_asset["url"],
        "name": display_name,
        "kind": saved_asset["kind"],
        "source": "blender",
        "source_file_name": saved_asset["name"],
        "local_path": saved_asset.get("local_path") or "",
    }
    width = parse_positive_int(payload.get("width"))
    height = parse_positive_int(payload.get("height"))
    if width:
        item["natural_w"] = width
    if height:
        item["natural_h"] = height
    return item


def default_blender_node_title(items_payloads, saved_assets, payload):
    custom_title = str(payload.get("batch_title") or payload.get("node_title") or payload.get("title") or "").strip()
    if custom_title:
        return custom_title
    kinds = {str(asset.get("kind") or "image") for asset in saved_assets}
    names = []
    for item in items_payloads:
        name = str(item.get("camera_name") or item.get("node_title") or item.get("title") or "").strip()
        if name and name not in names:
            names.append(name)
    if len(saved_assets) == 1:
        if names:
            return names[0]
        return "动画参考" if "video" in kinds else "Viewport"
    if kinds == {"video"}:
        return "动画组"
    if kinds == {"image"}:
        return "机位组"
    return "媒体组"


def build_blender_node(saved_assets, items_payloads, payload, position):
    now_ms = int(time.time() * 1000)
    primary_item = items_payloads[0] if items_payloads else {}
    camera_names = [str(item.get("camera_name") or "").strip() for item in items_payloads]
    camera_names = [name for name in camera_names if name]
    title = default_blender_node_title(items_payloads, saved_assets, payload)
    meta = {
        "source": "blender",
        "camera_name": camera_names[0] if len(camera_names) == 1 else "",
        "camera_names": camera_names if len(camera_names) > 1 else [],
        "blend_file": str(payload.get("blend_file") or "").strip(),
        "scene_name": str(payload.get("scene_name") or "").strip(),
        "view_layer": str(payload.get("view_layer") or "").strip(),
        "batch_size": len(saved_assets),
        "media_kind": saved_assets[0]["kind"] if len(saved_assets) == 1 else "group",
    }
    frame_value = parse_positive_int(primary_item.get("frame"))
    start_frame = parse_positive_int(primary_item.get("start_frame"))
    end_frame = parse_positive_int(primary_item.get("end_frame"))
    duration_seconds = parse_number(primary_item.get("duration_seconds"))
    if frame_value is not None:
        meta["frame"] = frame_value
    if start_frame is not None:
        meta["start_frame"] = start_frame
    if end_frame is not None:
        meta["end_frame"] = end_frame
    if duration_seconds is not None:
        meta["duration_seconds"] = duration_seconds
    meta = {key: value for key, value in meta.items() if value not in ("", None)}
    images = [build_blender_media_item(saved_asset, item_payload) for saved_asset, item_payload in zip(saved_assets, items_payloads)]
    first_kind = images[0]["kind"] if images else "image"
    scale = 1.4 if len(images) > 1 else 2
    return {
        "id": f"smart_{uuid.uuid4().hex[:12]}",
        "type": "smart-image",
        "x": parse_number(position.get("x"), 180) or 180,
        "y": parse_number(position.get("y"), 180) or 180,
        "title": title,
        "images": images,
        "created_at": now_ms,
        "scale": scale,
        "outputKind": first_kind if len({img.get('kind') for img in images}) == 1 else "image",
        "blender": meta,
    }


def normalize_blender_payload_items(payload):
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return [payload]
    merged_items = []
    for index, raw_item in enumerate(raw_items, 1):
        if not isinstance(raw_item, dict):
            raise RuntimeError(f"items[{index - 1}] 不是对象")
        merged = dict(payload)
        merged.pop("items", None)
        merged.update(raw_item)
        merged_items.append(merged)
    return merged_items


def append_blender_assets_to_canvas(payload):
    canvas_id = str(payload.get("canvas_id") or "").strip()
    path = smart_canvas_path(canvas_id)
    if not path.exists():
        raise RuntimeError(f"目标画布不存在: {canvas_id}")
    canvas = normalize_canvas_structure(canvas_id, read_json_file(path, {}))
    if canvas.get("deleted_at"):
        raise RuntimeError("目标画布已在回收站中，不能导入")
    items_payloads = normalize_blender_payload_items(payload)
    saved_assets = [save_blender_payload_asset(item_payload) for item_payload in items_payloads]
    # 传递节点类型和标题给位置计算函数
    node_type = payload.get("type")
    node_title = payload.get("title") or payload.get("prompt")
    next_position = next_blender_node_position(canvas, node_type, node_title)
    position = {
        "x": parse_number(payload.get("x"), next_position["x"]),
        "y": parse_number(payload.get("y"), next_position["y"]),
    }
    node = build_blender_node(saved_assets, items_payloads, payload, position)
    canvas["nodes"] = list(canvas.get("nodes") or [])
    canvas["nodes"].append(node)
    canvas["updated_at"] = int(time.time() * 1000)
    write_json_file(path, canvas)
    return {
        "ok": True,
        "canvas_id": canvas_id,
        "canvas_path": str(path),
        "updated_at": canvas["updated_at"],
        "node_id": node["id"],
        "node": node,
        "asset": ({
            **saved_assets[0],
            "app_url": f"{APP_BASE}{saved_assets[0]['url']}",
        } if len(saved_assets) == 1 else None),
        "assets": [
            {
                **saved_asset,
                "app_url": f"{APP_BASE}{saved_asset['url']}",
            }
            for saved_asset in saved_assets
        ],
    }


def append_blender_frame_to_canvas(payload):
    return append_blender_assets_to_canvas(payload)


def append_blender_batch_to_canvas(payload):
    return append_blender_assets_to_canvas(payload)


def append_blender_animation_to_canvas(payload):
    return append_blender_assets_to_canvas(payload)


def blender_connection_status(canvas_id=""):
    safe_canvas_id = str(canvas_id or "").strip()
    if not safe_canvas_id:
        return {"ok": False, "connected": False, "reason": "missing_canvas_id", "message": "未填写画布 ID"}
    try:
        canvas_path = smart_canvas_path(safe_canvas_id)
    except Exception as exc:
        return {"ok": False, "connected": False, "reason": "invalid_canvas_id", "message": str(exc)}
    if not canvas_path.exists():
        return {"ok": False, "connected": False, "reason": "canvas_missing", "message": "目标画布不存在"}
    canvas_data = normalize_canvas_structure(safe_canvas_id, read_json_file(canvas_path, {}))
    if canvas_data.get("deleted_at"):
        return {"ok": False, "connected": False, "reason": "canvas_deleted", "message": "目标画布已在回收站"}
    # 连接检查：本服务（3107）能响应请求即视为连接正常（push-animation 由本服务处理）
    # 不再依赖 3000 端口画布 app（用户环境通常只跑 3107 后端 + 桌面应用）
    return {
        "ok": True,
        "connected": True,
        "reason": "connected",
        "message": "连接正常",
        "canvas_id": safe_canvas_id,
        "canvas_title": str(canvas_data.get("title") or "").strip(),
    }


def canvas_source_url_for_media_url(url):
    target = str(url or "").strip()
    if not target:
        return ""
    clean_target = target.split("?", 1)[0].split("#", 1)[0]
    canvases_dir = USER_DATA_DIR / "data" / "canvases"
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
        local_path = ASSETS_DIR / rel
    elif clean.startswith("assets/"):
        rel = urllib.parse.unquote(clean[len("assets/"):].lstrip("/"))
        local_path = ASSETS_DIR / rel
    else:
        candidate = Path(urllib.parse.unquote(clean))
        if candidate.is_absolute():
            local_path = candidate

    if local_path:
        try:
            resolved = local_path.resolve()
            user_root = USER_DATA_DIR.resolve()
            # Only inline local files from the MyridTV data directory or explicit absolute files.
            if resolved.exists() and (str(resolved).startswith(str(user_root)) or Path(clean).is_absolute()):
                mime_type = mimetypes.guess_type(str(resolved))[0] or "image/png"
                if not mime_type.startswith("image/"):
                    return ""
                raw = resolved.read_bytes()
                data = raw
                # 压缩大图，控制上下文 token 用量（最长边 2048 / JPEG 82）
                try:
                    from PIL import Image
                    if len(raw) > 256 * 1024:
                        img = Image.open(io.BytesIO(raw))
                        img.thumbnail((2048, 2048), Image.LANCZOS)
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
                    append_log(LOG_FILE, f"agent image inline skipped oversized url={text} bytes={len(data)}")
                    return ""
                encoded = base64.b64encode(data).decode("ascii")
                return f"data:{mime_type};base64,{encoded}"
        except Exception as exc:
            append_log(LOG_FILE, f"agent image inline failed url={text}: {exc}")
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
    canvases_dir = USER_DATA_DIR / "data" / "canvases"
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
                local = _agent_local_path_for_url(url)
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
    system_prompt = canvas_agent_augmented_system_prompt(payload)
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
    return text in CODEX_LOCAL_UPSTREAMS


def codex_local_model_choices():
    models = [CODEX_LOCAL_DEFAULT_MODEL, "gpt-5.5", "gpt-5.4-mini"]
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
    agent_id, entry = resolve_agent_entry((payload or {}).get("agent_id"))
    upstream_base = str((payload or {}).get("upstream_base_url") or entry.get("upstream_base_url") or "").strip()
    return is_codex_local_upstream(upstream_base)


def resolve_chat_target(payload):
    agent_id, entry = resolve_agent_entry(payload.get("agent_id"))
    provider_id = str(payload.get("provider") or payload.get("provider_id") or entry.get("provider_id") or "").strip()
    model = str(payload.get("model") or entry.get("model") or "").strip()
    upstream_base = str(payload.get("upstream_base_url") or "").strip().rstrip("/")
    # Agent 复用自定义平台：优先用所选平台的请求地址（平台是地址/Key 的唯一来源）。
    if not upstream_base and provider_id:
        try:
            for provider in read_api_providers():
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
    key = read_chat_key(provider_id, entry)
    if not key:
        raise RuntimeError(f"未找到 Agent「{agent_label}」所用平台的 API Key，请先在该平台配置中保存 API Key。")
    append_log(LOG_FILE, "agent chat target agent_id={} provider={} model={} upstream={} key_tail={}".format(
        agent_id, provider_id, model, upstream_base, key[-4:] if key else ""))
    return provider_id, model, upstream_base, key


def fetch_agent_models(payload=None):
    payload = payload if isinstance(payload, dict) else {}
    _, entry = resolve_agent_entry(payload.get("agent_id"))
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
            for provider in read_api_providers():
                if str(provider.get("id") or "") == provider_id:
                    upstream_base = str(provider.get("base_url") or "").strip().rstrip("/")
                    if upstream_base:
                        break
        except Exception:
            pass
    if not upstream_base:
        raise RuntimeError("Agent 未选择 LLM 平台，请先在 API 设置里选择自定义平台。")
    key = str(payload.get("api_key") or "").strip() or read_chat_key(provider_id, entry)
    if not key:
        raise RuntimeError("所选平台未保存 API Key，请先在该平台配置中填写并保存 API Key。")
    saved_models = []
    try:
        saved_models = list(entry.get("chat_models") or [])
    except Exception:
        saved_models = []
    try:
        for provider in read_api_providers():
            if str(provider.get("id") or "") == provider_id:
                saved_models = list(provider.get("chat_models") or []) + saved_models
                break
    except Exception:
        pass
    saved_models = unique_strings([str(m) for m in saved_models if str(m or "").strip()])
    if is_volcengine_plan_base(upstream_base):
        models = volcengine_plan_chat_models(saved_models)
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
            data = request_json(url, "GET", headers={"Authorization": f"Bearer {key}"}, timeout=30)
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
    models = unique_strings([
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


# ============ Canvas Agent Tools (function calling) ============
CANVAS_AGENT_MAX_TOOL_TURNS = 10
# 交互违规（该出卡没出卡/谎称发了卡）时，回灌纠正后的最多重试次数
CANVAS_AGENT_MAX_INTERACTION_RETRIES = 2

# Agent 对话推理强度：默认 minimal —— 实测同一上游、同一问题，长输出 77.4s/8919tok → 13.6s/1031tok
# （glm-5.3-flash 默认先生成大量隐藏思考 reasoning token，非流式下用户只能干等）。
# 关闭方式：环境变量 MYRIDTV_AGENT_REASONING_EFFORT 设为空串。
CANVAS_AGENT_REASONING_EFFORT = os.environ.get("MYRIDTV_AGENT_REASONING_EFFORT", "minimal").strip()
_canvas_agent_reasoning_effort = {"enabled": bool(CANVAS_AGENT_REASONING_EFFORT)}
CANVAS_AGENT_DEFAULT_PROVIDER = "runninghub"


def _agent_default_image_model():
    """默认模型=用户 provider 配置里的第一个文生图模型（用户配置为准，禁硬编码）"""
    return _agent_select_configured_image_model(CANVAS_AGENT_DEFAULT_PROVIDER, "", [])


def _agent_configured_image_models(provider_id):
    provider_id = str(provider_id or "").strip()
    if provider_id == "custom-api-3":
        provider_id = "runninghub"
    if not provider_id:
        return []
    try:
        for provider in read_api_providers() or []:
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
            normalized_requested = normalize_model(requested, refs)
            if normalized_requested in normalized_models:
                return normalized_requested
            if requested in normalized_models:
                return requested
        preferred_suffixes = ["/image-to-image", "/edit"] if refs else ["/text-to-image"]
        for suffix in preferred_suffixes:
            for model in normalized_models:
                if model.endswith(suffix):
                    return normalize_model(model, refs)
        return normalize_model(normalized_models[0], refs)
    if provider_id in {CANVAS_AGENT_DEFAULT_PROVIDER, "custom-api-3"}:
        raise RuntimeError("未找到默认生图模型：请在 API 设置的 RunningHub 下配置生图模型")
    if requested:
        return normalize_model(requested, refs)
    raise RuntimeError("未找到默认生图模型：请先配置生图平台和模型")


def _agent_html_escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _agent_http(method, path, payload=None, timeout=30):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = "http://127.0.0.1:{}{}".format(PORT, path)
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
        _atype = "script" if str(args.get("kind") or "").strip().lower() == "script" else "text"
    _route = route_artifact(
        artifact_type=_atype,
        role="text",
        tool_name="canvas_create_text_node",
        user_text=str(args.get("user_text") or args.get("userText")
                      or CANVAS_AGENT_ROUTE_CONTEXT.get("user_text") or ""),
    )
    _dest = str(_route.get("destination") or "canvas")
    _art_id = ""
    if _dest in ("sidebar", "both"):
        _aok, _aid, _asave = _agent_upsert_sidebar_artifact(
            cid, canvas,
            title=str(args.get("title") or "Agent 笔记").strip(),
            content=text,
            artifact_type=_atype,
            source_event_id=str(args.get("event_id") or ""),
            # Phase 9：一轮 Agent 会话 = 一个 Conversation Artifact
            conversation_id=str(session_id or CANVAS_AGENT_CURRENT_SESSION.get("session_id") or ""),
            conversation_title=str(CANVAS_AGENT_ROUTE_CONTEXT.get("user_text") or "")[:40],
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
        "kind": "script",
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
    ok, nid, save_ok, deduped = _agent_canvas_repo_upsert_node(cid, canvas, node, "agent_tool_text", args)
    if not ok:
        return {"ok": False, "error": nid}
    if not _art_id:
        return {"ok": True, "node_id": nid, "save_ok": save_ok,
                "destination": "canvas", "reason": _route.get("reason")}
    _agent_link_artifact_node(cid, canvas, _art_id, nid)
    return {"ok": True, "node_id": nid, "save_ok": save_ok, "artifact_id": _art_id,
            "destination": "both", "reason": _route.get("reason")}


def _agent_default_run_settings(args, preset=None):
    preset = preset if isinstance(preset, dict) else {}
    provider_id = str(args.get("provider_id") or preset.get("provider_id") or CANVAS_AGENT_DEFAULT_PROVIDER)
    refs = args.get("reference_image_urls") or args.get("reference_images") or []
    if not isinstance(refs, list):
        refs = [refs]
    refs = [r for r in refs if str(r or "").strip()]
    model = _agent_select_configured_image_model(provider_id, args.get("model") or preset.get("model") or "", refs)
    size = str(args.get("size") or preset.get("size") or "3840x2160")
    aspect = str(args.get("aspect_ratio") or args.get("aspectRatio")
                 or preset.get("aspectRatio") or preset.get("aspect_ratio") or "16:9")
    resolution = str(args.get("resolution") or preset.get("resolution") or "4k")
    quality = str(args.get("quality") or preset.get("quality") or "high")
    return {
        "provider_id": provider_id,
        "model": model,
        "size": size,
        "aspectRatio": aspect,
        "resolution": resolution,
        "quality": quality,
        "n": 1,
    }


def _agent_reference_image_url(item):
    if isinstance(item, dict):
        url = item.get("url") or item.get("path") or item.get("local_path") or item.get("localPath")
        if not url:
            node_id = str(item.get("nodeId") or item.get("node_id") or "").strip()
            if node_id:
                node_img = _agent_canvas_node_image_by_id(node_id, item.get("imageIndex"))
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
    if name not in {"canvas_create_generation_node", "canvas_generate_images"}:
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
        "videoTempShLinks": [],
        "msgenModel": "zimage",
        "msCustomModel": "",
        "msRatio": "square",
        "msResolution": "1k",
        "msCustomRatio": "",
        "msCustomRatioWidth": "",
        "msCustomRatioHeight": "",
        "msCustomSize": "",
        "msCustomWidth": "",
        "msCustomHeight": "",
        "comfyMode": "custom",
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


def _agent_tool_create_generation_node(args, preset=None):
    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        return {"ok": False, "error": "prompt 必填"}
    cid, canvas = _agent_get_canvas(str(args.get("canvas_id") or ""))
    settings = _agent_default_run_settings(args, preset)
    node_x, node_y = _agent_find_empty_position(canvas, args.get("x"), args.get("y"), 320, 420, category=_agent_category_from_title(args.get("title")), node_type="smart-image")
    # 引用图片 → 写入节点引用 + 输入连线
    refs = _agent_normalize_reference_items(args.get("reference_image_urls") or args.get("reference_images") or [])
    ref_node_ids = []
    run_refs = []
    for ref in refs:
        url = str((ref or {}).get("url") or "").strip()
        if not url:
            continue
        node_id = str((ref or {}).get("nodeId") or "").strip()
        image_index = int(parse_number((ref or {}).get("imageIndex"), 0) or 0)
        match = next((n for n in (canvas.get("nodes") or [])
                      if any(str(img.get("url") or "") == url for img in (n.get("images") or []) if isinstance(img, dict))
                      or (node_id and str(n.get("id") or "") == node_id)), None)
        if match and not node_id:
            node_id = str(match.get("id") or "")
        run_refs.append({
            "url": url,
            "name": str((ref or {}).get("name") or "图片{}".format(len(run_refs) + 1)).strip() or "图片{}".format(len(run_refs) + 1),
            "sourceName": str((ref or {}).get("sourceName") or match.get("title") or "").strip() if isinstance(match, dict) else str((ref or {}).get("sourceName") or "").strip(),
            "nodeId": node_id,
            "imageIndex": image_index,
            "kind": "image",
        })
        if node_id and node_id != "": 
            ref_node_ids.append(node_id)
    # 提示词里统一使用 @图片1/@图片2…，严格继承当前会话输入链顺序。
    # 如果模型没明确写参考关系，这里至少补成“参考@图片N生成”。
    prompt_with_refs = prompt
    for r in run_refs:
        token = "@" + str(r.get("name") or "").strip()
        if not token:
            continue
        if token not in prompt_with_refs:
            prompt_with_refs += " 参考{}生成".format(token)
        elif "参考{}".format(token) not in prompt_with_refs:
            prompt_with_refs += " 参考{}".format(token)
    node = {
        "id": "agent_" + uuid.uuid4().hex[:12],
        "type": "smart-image",
        "title": str(args.get("title") or "Agent 生成").strip(),
        "promptDraftText": prompt_with_refs,
        "promptDraftHtml": _agent_html_escape(prompt_with_refs),
        "promptDraftTouched": True,
        "runPrompt": prompt_with_refs,
        "runPromptRefs": run_refs,
        "runInputRefs": run_refs,
        "inputNodeIds": list(dict.fromkeys(ref_node_ids)),
        "runSettings": _agent_run_settings_for_storage(settings),
        "images": [],
        "x": node_x, "y": node_y,
        "created_at": int(time.time() * 1000),
        "__origin": "agent_tool_generation",
        "status": "pending",
        "role": "generation",
    }
    ok, nid, deduped = _agent_prepare_node_for_canvas(cid, canvas, node, "agent_tool_generation", args)
    if not ok:
        return {"ok": False, "error": nid}
    if not deduped:
        if not isinstance(canvas.get("nodes"), list):
            canvas["nodes"] = []
        canvas["nodes"].append(node)
    if ref_node_ids:
        connections = canvas.get("connections")
        if not isinstance(connections, list):
            connections = []
            canvas["connections"] = connections
        for rid in dict.fromkeys(ref_node_ids):
            if rid != nid and not any(c.get("from") == rid and c.get("to") == nid and c.get("kind") == "input" for c in connections):
                connections.append({"from": rid, "to": nid, "kind": "input"})
    save = _agent_http("PUT", "/api/canvases/{0}".format(urllib.parse.quote(cid)), canvas, timeout=30)
    return {"ok": True, "node_id": nid, "canvas_id": cid, "save_ok": save.get("ok", save.get("canvas") is not None), "deduped": deduped}


def _agent_extract_image_urls(task_state):
    result = task_state.get("result") if isinstance(task_state, dict) else None
    if not isinstance(result, dict):
        return []
    urls = []
    for img in result.get("images") or []:
        if isinstance(img, str):
            urls.append(img)
        elif isinstance(img, dict) and img.get("url"):
            urls.append(img["url"])
    return urls


def _agent_localize_urls(urls):
    if not urls:
        return
    try:
        _agent_http("POST", "/api/localize-generated-media",
                    {"items": [{"url": u} for u in urls], "kind": "image"}, timeout=120)
    except Exception:
        pass


def _agent_png_size(path):
    try:
        with open(path, "rb") as f:
            head = f.read(26)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return None, None
        import struct
        w, h = struct.unpack(">II", head[16:24])
        return w, h
    except Exception:
        return None, None


def _agent_local_path_for_url(url):
    if not str(url).startswith("/assets/"):
        return ""
    # 画布名可能是中文，url 中是 URL 编码（%E8%B6%85...），必须先 unquote 才能匹配磁盘路径
    rel = urllib.parse.unquote(str(url)[len("/assets/"):])
    return os.path.join(str(ASSETS_DIR), rel.replace("/", os.sep))


def _agent_add_pending_task_to_node(canvas_id, node_id, task_id, kind="image"):
    """把后端任务 ID 写入节点的 pendingTasks，让前端能够按标准流程轮询并回填。"""
    cid = str(canvas_id or "").strip()
    nid = str(node_id or "").strip()
    tid = str(task_id or "").strip()
    if not cid or not nid or not tid:
        return False
    _, canvas = _agent_get_canvas(cid)
    if not isinstance(canvas, dict):
        return False
    node = None
    for n in canvas.get("nodes") or []:
        if isinstance(n, dict) and str(n.get("id")) == nid:
            node = n
            break
    if node is None:
        return False
    pending = node.get("pendingTasks") or []
    if not isinstance(pending, list):
        pending = []
    # 去重
    if not any(str(p.get("taskId") or "") == tid for p in pending if isinstance(p, dict)):
        pending.append({"taskId": tid, "kind": str(kind or "image")})
    node["pendingTasks"] = pending
    node["pending"] = len(pending)
    save = _agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(cid)), canvas, timeout=30)
    return save.get("ok", save.get("canvas") is not None)


def _agent_attach_result_to_node(cid, canvas, node_id, urls):
    node = None
    for n in canvas.get("nodes") or []:
        if isinstance(n, dict) and str(n.get("id")) == str(node_id):
            node = n
            break
    if node is None:
        return False
    images = []
    try:
        for url in urls:
            w, h = _agent_png_size(_agent_local_path_for_url(url))
            item = {"url": url, "name": str(url).rsplit("/", 1)[-1], "kind": "image", "generatedResult": True}
            if w and h:
                item["natural_w"] = w
                item["natural_h"] = h
            images.append(item)
        # 与前端标准流程一致：append 而非覆盖，保留节点已有图片
        existing = node.get("images") or []
        if not isinstance(existing, list):
            existing = []
        node["images"] = existing + images
        node["status"] = "ready"  # 状态机：生成/回填成功 -> ready
        # 补前端重跑归档所需时间戳：nodeHasCompletedGeneration 认 runAt/runFinishedAt，
        # 缺失会让用户下次点"运行"时被判定为首跑、旧图不进历史分组
        _now_ms = int(time.time() * 1000)
        if not node.get("runStartedAt"):
            node["runStartedAt"] = _now_ms
        node["runFinishedAt"] = _now_ms
        node["runElapsedMs"] = max(0, _now_ms - int(node.get("runStartedAt") or _now_ms))
    except Exception as _exc:
        # 状态机：生成或回填异常 -> failed（渲染层红色告警）；promptDraftText 仍保留，供用户显式重跑
        node["status"] = "failed"
        append_log(LOG_FILE, "[CanvasNodeAttachFailed] node={} reason={}".format(node_id, _exc))
    save = _agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(cid)), canvas, timeout=30)
    return save.get("ok", save.get("canvas") is not None)


def _agent_wait_localized(task_id, attempts=6):
    urls = []
    for _ in range(attempts):
        st = _agent_http("GET", "/api/canvas-image-tasks/{}".format(urllib.parse.quote(task_id)))
        urls = _agent_extract_image_urls(st)
        if urls and all(str(u).startswith("/assets/") for u in urls):
            return urls
        _agent_localize_urls(urls)
        time.sleep(3)
    return urls


def _agent_submit_generation(args, preset=None):
    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        return {"ok": False, "error": "prompt 必填"}
    cid = str(args.get("canvas_id") or "").strip() or _agent_latest_canvas_id()
    nid = str(args.get("node_id") or "").strip()
    node_title = str(args.get("node_title") or "").strip()
    settings = _agent_default_run_settings(args, preset)
    refs = _agent_normalize_reference_items(args.get("reference_image_urls") or args.get("reference_images") or [])
    if str(settings["provider_id"] or "").strip() == "comfy":
        # 本地 ComfyUI 工作流生图：model 即工作流名
        workflow_name = str(settings["model"] or "").strip()
        if not workflow_name:
            return {"ok": False, "error": "未选择 ComfyUI 工作流"}
        try:
            record = read_workflow_record(workflow_name)
        except Exception as exc:
            return {"ok": False, "error": "读取 ComfyUI 工作流失败: {}".format(exc)}
        config = record.get("config") if isinstance(record.get("config"), dict) else {}
        fields = config.get("fields") if isinstance(config.get("fields"), list) else []
        values = {}
        prompt_field = next((f for f in fields if str(f.get("name") or "").strip() in ("提示词", "Prompt") or "prompt" in str(f.get("type") or "").lower()), None)
        if prompt_field and prompt_field.get("id"):
            values[prompt_field["id"]] = prompt
        canvas_title = str(args.get("canvas_title") or _volcengine_canvas_title_for_output(cid)).strip()
        try:
            resp = _agent_http("POST", "/api/workflows/{}/run".format(urllib.parse.quote(workflow_name)),
                               {"config": config, "fields": values, "canvas_id": cid, "canvas_title": canvas_title}, timeout=3700)
        except Exception as exc:
            return {"ok": False, "error": "ComfyUI 工作流执行失败: {}".format(str(exc)[:200])}
        raw_images = [str(u) for u in (resp.get("images") or []) if str(u).strip()]
        if not raw_images:
            return {"ok": False, "error": "ComfyUI 工作流未返回图片: {}".format(str(resp)[:240])}
        # 统一落盘到画布同名文件夹（与 API 分支同一套逻辑）
        localized = localize_canvas_task_result({"images": raw_images}, {
            "canvas_title": canvas_title,
            "canvas_id": cid,
            "node_title": node_title,
        })
        images = [str((img or {}).get("url") or img) for img in (localized.get("images") or [])]
        return {"ok": True, "task_id": "", "images": images, "canvas_id": cid, "comfy": True}
    payload = {
        "prompt": prompt,
        "provider_id": settings["provider_id"],
        "model": settings["model"],
        "size": settings["size"],
        "quality": settings["quality"],
        "n": settings["n"],
        "reference_images": [str((r or {}).get("url") or "").strip() for r in refs if str((r or {}).get("url") or "").strip()],
        "canvas_id": cid,
        "canvas_title": str(args.get("canvas_title") or _volcengine_canvas_title_for_output(cid)),
        "node_id": nid,
        "node_title": node_title,
        "resolution": settings["resolution"],
        "aspectRatio": settings["aspectRatio"],
    }
    resp = _agent_http("POST", "/api/canvas-image-tasks", payload, timeout=30)
    task_id = str(resp.get("task_id") or "").strip()
    if not task_id:
        return {"ok": False, "error": "提交生图失败: {}".format(resp)}
    return {"ok": True, "task_id": task_id, "canvas_id": cid}


def _agent_tool_generate_images(args, preset=None):
    node_id = str(args.get("node_id") or "").strip()
    cid = ""
    if node_id:
        cid, canvas = _agent_get_canvas(str(args.get("canvas_id") or ""))
    else:
        created = _agent_tool_create_generation_node(args, preset)
        if not created.get("ok"):
            return created
        node_id = str(created.get("node_id") or "")
        cid = str(created.get("canvas_id") or "")
    # 优先使用传入的 node_title，否则从节点标题取
    if not str(args.get("node_title") or "").strip() and node_id and cid:
        try:
            _, canvas = _agent_get_canvas(cid)
            node = next((n for n in (canvas.get("nodes") or []) if isinstance(n, dict) and str(n.get("id")) == str(node_id)), None)
            if node and str(node.get("title") or "").strip():
                args = {**args, "node_title": str(node.get("title") or "").strip()}
        except Exception:
            pass
    sub = _agent_submit_generation(args, preset)
    if not sub.get("ok"):
        return sub
    if sub.get("images"):
        # ComfyUI 同步完成：直接回填节点
        attached = False
        if node_id and sub.get("images"):
            try:
                attached = _agent_attach_result_to_node(cid, _agent_get_canvas(cid)[1], node_id, sub["images"])
            except Exception:
                attached = False
        return {"ok": True, "status": "succeeded", "task_id": sub.get("task_id") or "", "node_id": node_id,
                "images": sub["images"], "attached_to_node": attached, "comfy": True}
    task_id = sub["task_id"]
    # 把 task_id 写入 node.pendingTasks，让前端能够按标准流程轮询并自动回填
    if node_id and task_id:
        try:
            _agent_add_pending_task_to_node(cid, node_id, task_id, "image")
        except Exception as exc:
            append_log(LOG_FILE, f"[CanvasAgent] 无法写入 pendingTasks node={node_id} task={task_id}: {exc}")
    # 异步语义：提交后立即返回，不再在本工具内同步轮询等待（生图常需 1-5 分钟，
    # 同步等待会占住 agent 轮次让用户干等）。生成完成后图片会自动回填画布节点，
    # 需要时用 canvas_check_generation / canvas_get_state 查询。
    return {"ok": True, "status": "running", "task_id": task_id, "node_id": node_id,
            "canvas_id": cid,
            "message": "生图任务已提交,图片生成完成后会自动回填到画布节点。无需轮询等待,可先回复用户已提交。"}


def _agent_tool_check_generation(args):
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        return {"ok": False, "error": "task_id 必填"}
    node_id = str(args.get("node_id") or "").strip()
    cid = str(args.get("canvas_id") or "").strip()
    st = _agent_http("GET", "/api/canvas-image-tasks/{}".format(urllib.parse.quote(task_id)))
    status = st.get("status") or "running"
    if status == "succeeded":
        urls = _agent_wait_localized(task_id)
        attached = False
        if urls and node_id:
            try:
                if not cid:
                    cid = _agent_latest_canvas_id()
                attached = _agent_attach_result_to_node(cid, _agent_get_canvas(cid)[1], node_id, urls)
            except Exception as exc:
                return {"ok": True, "status": "succeeded", "task_id": task_id, "images": urls,
                        "attached_error": str(exc)}
        return {"ok": True, "status": "succeeded", "task_id": task_id, "node_id": node_id,
                "images": urls, "attached_to_node": attached}
    if status == "failed":
        return {"ok": False, "status": "failed", "task_id": task_id,
                "error": st.get("error") or st.get("message") or "生图失败"}
    return {"ok": True, "status": "running", "task_id": task_id, "node_id": node_id,
            "canvas_id": cid, "message": "任务仍在生成中,请稍后再次调用本工具"}


def _agent_tool_update_node(args):
    node_id = str(args.get("node_id") or "").strip()
    if not node_id:
        return {"ok": False, "error": "node_id 必填"}
    cid, canvas = _agent_get_canvas(str(args.get("canvas_id") or ""))
    node = None
    for n in canvas.get("nodes") or []:
        if isinstance(n, dict) and str(n.get("id")) == str(node_id):
            node = n
            break
    if node is None:
        return {"ok": False, "error": "节点不存在: {}".format(node_id)}
    if "text" in args and args.get("text") is not None:
        node["text"] = str(args.get("text"))
        node["content"] = str(args.get("text"))
    if "title" in args and args.get("title") is not None:
        node["title"] = str(args.get("title"))
    save = _agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(cid)), canvas, timeout=30)
    return {"ok": True, "node_id": node_id, "save_ok": save.get("ok", save.get("canvas") is not None)}


def _agent_should_create_canvas_node(node):
    """Artifact Gate：后端 Agent 自动建节点前的唯一合法性闸门。

    只有具备明确身份且有真实内容的节点才允许进入画布；
    空壳节点（无 id / 无 type / 无 title·text·images 任一内容）一律拦截，
    杜绝“模型说了一段话就变成了空节点”的污染。
    注意：generation 占位节点(images=[]) 凭借 promptDraftText 通过本闸门，
    因为它代表“用户授权的待生成任务”，不等同于空壳。
    """
    if not isinstance(node, dict):
        return False, "node 不是 dict"
    nid = str(node.get("id") or "").strip()
    if not nid:
        return False, "缺少 id"
    ntype = str(node.get("type") or "").strip()
    if not ntype:
        return False, "缺少 type"
    title = str(node.get("title") or "").strip()
    text = str(node.get("text") or node.get("content") or node.get("promptDraftText") or "").strip()
    images = node.get("images") if isinstance(node.get("images"), list) else []
    if not (title or text or images):
        return False, "空壳(无 title/text/images)"
    return True, ""


def _agent_ensure_artifactId(node, args):
    """Artifact 契约：解析/补全 artifactId（结构化产物的唯一幂等键）。

    优先级 node.artifactId > args.artifactId > args.artifact_id > args.intent_id；
    都没有时兜底：生成类用 node.id（不崩，同 id 天然去重），
    文本类基于 title+text 哈希（跨重试/重放稳定去重）。
    """
    aid = str(node.get("artifactId") or (args or {}).get("artifactId") or (args or {}).get("artifact_id") or (args or {}).get("intent_id") or "").strip()
    if aid:
        return aid
    ntype = str(node.get("type") or "")
    is_gen = ntype in ("smart-image", "generation", "image", "gen", "video", "smart-video")
    if is_gen:
        return str(node.get("id") or "agent_" + uuid.uuid4().hex[:12])
    import hashlib
    payload = str(node.get("title") or "") + "|" + str(node.get("text") or node.get("content") or node.get("promptDraftText") or "")
    return "art-" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _agent_prepare_node_for_canvas(cid, canvas, node, origin, args=None):
    """建节点合法性决策单一权威（Artifact 双写归一核心）：

    1) 解析/补全 artifactId
    2) artifactId 去重：同 artifactId 已建节点 -> 复用(deduped=True)，不再建重复节点
    3) Artifact Gate：空壳/无身份拦截
    返回 (ok, node_id_or_error, deduped)
    """
    if not isinstance(node, dict):
        return False, "node 不是 dict", False
    aid = _agent_ensure_artifactId(node, args)
    node["artifactId"] = aid
    node["__origin"] = origin
    provenance = (args or {}).get("provenance") if isinstance(args, dict) else None
    if isinstance(provenance, dict):
        node["provenance"] = dict(provenance)
        node.setdefault("created_by", "agent")
        node.setdefault("conversation_id", provenance.get("conversation_id") or "")
        node.setdefault("task_id", provenance.get("task_id") or "")
        node.setdefault("step_id", provenance.get("step_id") or "")
        node.setdefault("turn_id", provenance.get("turn_id") or "")
        node.setdefault("tool_call_id", provenance.get("tool_call_id") or "")
    nodes_list = canvas.get("nodes") if isinstance(canvas.get("nodes"), list) else []
    existing = next((n for n in nodes_list if isinstance(n, dict) and str(n.get("artifactId") or "") == aid), None)
    if existing is not None:
        append_log(LOG_FILE, "[ArtifactDedup] artifactId={} reuse_node={}".format(aid, existing.get("id")))
        return True, existing["id"], True
    ok, reason = _agent_should_create_canvas_node(node)
    if not ok:
        append_log(LOG_FILE, "[CanvasNodeRejected] origin={} reason={} title={}".format(origin, reason, str(node.get("title"))[:40]))
        return False, "节点被 Artifact Gate 拦截: {}".format(reason), False
    # ---- CanvasMutationManager 收口（#10/#28/#41）----
    # 既有 Artifact Gate 通过后再过一层硬守卫：空 prompt / 非法类型 / 重复 / 阶段守卫，
    # 并写入 Ledger（开发模式 Mutation Timeline 数据源，#39）。模型即使犯错也不可能在
    # Prompt Ready 以前写入垃圾节点。
    if _cmm is not None:
        _mgr_ok, _mgr_reason, _mgr_det = _cmm.validate_asset_node(
            node, phase=CANVAS_AGENT_CURRENT_PHASE.get("phase") or "")
        if not _mgr_ok:
            append_log(LOG_FILE, "[CanvasMutationBlocked] origin={} reason={} title={}".format(
                origin, _mgr_reason, str(node.get("title"))[:40]))
            return False, "节点被 MutationManager 拦截: {}".format(_mgr_reason), False
    return True, node["id"], False


def _agent_canvas_repo_upsert_node(cid, canvas, node, origin, args=None):
    """Canvas Repo：后端唯一受 Artifact Gate 保护的节点落库入口（即时写通道共用）。

    A1 与 MCP 经此落库；A2(含输入连线)与批量通道复用 _agent_prepare_node_for_canvas
    做去重+Gate 决策，仅因需额外连线/整体提交而保留各自 save。
    返回 (ok, node_id_or_error, save_ok, deduped)。
    """
    ok, nid, deduped = _agent_prepare_node_for_canvas(cid, canvas, node, origin, args)
    if not ok:
        return False, nid, False, deduped
    if deduped:
        save = _agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(str(cid))), canvas, timeout=30)
        return True, nid, save.get("ok", save.get("canvas") is not None), True
    nodes_list = canvas.get("nodes") if isinstance(canvas.get("nodes"), list) else []
    canvas["nodes"] = nodes_list
    nodes_list.append(node)
    save = _agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(str(cid))), canvas, timeout=30)
    return True, node["id"], save.get("ok", save.get("canvas") is not None), False


def _agent_upsert_conversation_artifact(cid, canvas, title="", content="", artifact_type="brainstorm",
                                        conversation_id="", conversation_title="",
                                        section_type="", section_title="", item_title="",
                                        item_id="", resource_id="", source_run_id="", source_event_id="",
                                        defer_save=False, metadata=None):
    """Phase 9：Conversation Artifact 容器模式 —— "一轮对话 = 一个整体产物"。

    与旧行为的本质区别：artifact id 由 (canvasId, conversationId, type) 确定性推导，
    所以同一轮头脑风暴产生的 人物/故事/场面/世界观 会合并成同一个 Conversation
    的不同 Section，而不是 4 个平铺的 Sidebar 一级条目（需求第二/六/二十七条）。

    返回 (ok, artifact_id, save_ok)。
    """
    if not cid or not isinstance(canvas, dict) or not str(conversation_id or "").strip():
        return False, "缺少 canvas 或 conversation_id", False

    atype = str(artifact_type or "brainstorm").strip().lower()
    aid = conversation_artifact_id(cid, conversation_id, atype)
    now = int(time.time() * 1000)

    arts = canvas.get("artifacts") if isinstance(canvas.get("artifacts"), list) else []
    canvas["artifacts"] = arts
    hit = None
    for a in arts:
        if isinstance(a, dict) and str(a.get("id") or "") == aid:
            hit = a
            break

    if hit is None:
        # 标题优先级：显式 conversation_title > 首个 Section 标题 > 类型标签 > Brainstorm
        seed = str(conversation_title or "").strip() or str(title or "").strip()
        if not seed and atype not in CONVERSATION_CONTAINER_TYPES:
            seed = atype[:60]
        hit = {
            "id": aid,
            "canvasId": str(cid),
            "conversationId": str(conversation_id),
            "artifactType": atype,
            "kind": "conversation",
            "title": seed or "Brainstorm",
            "content": "",
            "sections": [],
            "resourceId": str(resource_id or ""),
            "canvasNodeId": "",
            "sourceRunId": str(source_run_id or ""),
            "sourceEventId": str(source_event_id or ""),
            "version": 1,
            "createdAt": now,
            "updatedAt": now,
        }
        arts.append(hit)

    secs = hit.get("sections") if isinstance(hit.get("sections"), list) else []
    hit["sections"] = secs

    # 板块名取值链：显式 section_title > 产物 title > 退化成类型标签
    sec_name = str(section_title or title or "").strip()
    stype = infer_section_type(sec_name, section_type)
    stitle = sec_name or section_type_label(stype)
    # 去重键：有名字就按名字；连名字都没有才按类型。
    # 不能仅因语义类型相同就合并 —— 「悲剧结局/开放结局/反转结局」都推断成 direction，
    # 但它们明明是三个不同板块。
    if sec_name:
        sid = artifact_section_id(conversation_id, "", sec_name)
    else:
        sid = artifact_section_id(conversation_id, stype, "")

    sec = None
    for s in secs:
        if isinstance(s, dict) and str(s.get("id") or "") == sid:
            sec = s
            break
    if sec is None:
        sec = {
            "id": sid,
            "type": stype,
            "title": stitle,
            "order": len(secs),
            "items": [],
            "createdAt": now,
            "updatedAt": now,
        }
        secs.append(sec)

    items = sec.get("items") if isinstance(sec.get("items"), list) else []
    sec["items"] = items
    iid = str(item_id or "").strip() or artifact_item_id(sid, item_title)
    # 板块从「一整块文本」升级成「具名条目」时，撤掉之前那个匿名占位条目。
    # 否则 核心人物 会同时挂着 "林澜/司徒岳" 旧块 + 林澜 + 司徒岳 三条。
    if str(item_title or "").strip() and len(items) == 1:
        _only = items[0]
        if (isinstance(_only, dict)
                and not str(_only.get("title") or "").strip()
                and str(_only.get("id") or "").endswith("_main")):
            items = []
            sec["items"] = items
    item = None
    for it in items:
        if isinstance(it, dict) and str(it.get("id") or "") == iid:
            item = it
            break
    if item is None:
        item = {
            "id": iid,
            "title": str(item_title or "").strip(),
            "content": "",
            "order": len(items),
            "metadata": dict(metadata or {}),
            "createdAt": now,
            "updatedAt": now,
        }
        items.append(item)
    item["content"] = str(content or "")
    item["updatedAt"] = now
    if metadata:
        item.setdefault("metadata", {})
        try:
            item["metadata"].update(dict(metadata))
        except Exception:
            item["metadata"] = dict(metadata)
    sec["updatedAt"] = now

    secs.sort(key=lambda s: int(s.get("order") or 0))
    for i, s in enumerate(secs):
        s["order"] = i

    hit["updatedAt"] = now
    hit["version"] = int(hit.get("version") or 1) + 1
    # content 保留一份扁平镜像，供旧前端 / 全文检索兜底读取（不作为 Sidebar 分层来源）
    hit["content"] = _flatten_conversation_content(hit)

    if defer_save:
        return True, aid, True
    save = _agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(str(cid))), canvas, timeout=30)
    save_ok = bool(save.get("ok", save.get("canvas") is not None)) if isinstance(save, dict) else False
    if not save_ok:
        return False, "conversation artifact 保存失败", False
    return True, aid, True


def _flatten_conversation_content(art):
    """把 Conversation 的 Section/Item 拍平成 Markdown 文本（仅作镜像，不参与分层导航）。"""
    parts = []
    for sec in (art.get("sections") or []):
        if not isinstance(sec, dict):
            continue
        parts.append("## " + str(sec.get("title") or "").strip())
        for it in (sec.get("items") or []):
            if not isinstance(it, dict):
                continue
            t = str(it.get("title") or "").strip()
            body = str(it.get("content") or "").strip()
            if t:
                parts.append("### " + t)
            if body:
                parts.append(body)
    return "\n\n".join(parts)


def _agent_upsert_sidebar_artifact(cid, canvas, title="", content="", artifact_type="text",
                                   resource_id="", source_run_id="", source_event_id="",
                                   defer_save=False, conversation_id="", conversation_title="",
                                   section_type="", section_title="", item_title="",
                                   item_id="", metadata=None):
    """Phase 8：Sidebar Artifact 落库（与 _agent_canvas_repo_upsert_node 同构）。

    Phase 9：当传入 conversation_id 且类型属于容器型时，改走
    _agent_upsert_conversation_artifact（分层模式）；否则完全保持 Phase 8 旧行为。
    """
    _conv = str(conversation_id or "").strip()
    _atype = str(artifact_type or "text").strip().lower()
    _has_section = bool(str(section_type or "").strip() or str(section_title or "").strip())
    # Phase 9 兜底：会话内的非文档产物（text/note/script/analysis...）一律归入
    # 会话容器，哪怕 LLM 忘了带 section_title —— 用产物 title 退化成板块名，
    # 绝不退回旧的"每次 uuid 新建平铺条目"。只有独立文档型保持一级条目。
    if _conv and (_atype not in INDEPENDENT_DOC_TYPES):
        return _agent_upsert_conversation_artifact(
            cid, canvas, title=title, content=content, artifact_type=_atype,
            conversation_id=_conv, conversation_title=conversation_title,
            section_type=section_type, section_title=section_title,
            item_title=item_title, item_id=item_id,
            resource_id=resource_id, source_run_id=source_run_id,
            source_event_id=source_event_id, defer_save=defer_save, metadata=metadata,
        )
    """Phase 8：Sidebar Artifact 落库（与 _agent_canvas_repo_upsert_node 同构）。

    三条保证：
      - 去重：按 artifactId 合并，同 id -> update 不 append（需求第二十二/二十三条）
      - 失败不留痕：保存失败回滚内存态，绝不留下空 artifact（需求第四十一条）
      - 绑定 canvas：写进 canvas["artifacts"]，天然按 canvasId 隔离（需求第八/二十八条）
    返回 (ok, artifact_id, save_ok)。
    """
    if not cid or not isinstance(canvas, dict):
        return False, "缺少 canvas", False
    now = int(time.time() * 1000)
    aid = "artifact_" + uuid.uuid4().hex[:12]
    art = {
        "id": aid,
        "title": str(title or "").strip() or "未命名产物",
        "artifactType": str(artifact_type or "text").strip().lower(),
        "content": str(content or ""),
        "resourceId": str(resource_id or ""),
        "canvasId": str(cid),
        "sourceRunId": str(source_run_id or ""),
        "sourceEventId": str(source_event_id or ""),
        "canvasNodeId": "",
        "version": 1,
        "createdAt": now,
        "updatedAt": now,
    }
    prev_list = canvas.get("artifacts") if isinstance(canvas.get("artifacts"), list) else []
    canvas["artifacts"] = _merge_artifacts(prev_list, [art])
    if defer_save:
        # 批量通道：只改内存，由调用方末尾统一落盘（避免 N 次 PUT）
        return True, aid, True
    save = _agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(str(cid))), canvas, timeout=30)
    save_ok = bool(save.get("ok", save.get("canvas") is not None)) if isinstance(save, dict) else False
    if not save_ok:
        canvas["artifacts"] = prev_list
        return False, "artifact 保存失败", False
    return True, aid, True


def _agent_link_artifact_node(cid, canvas, artifact_id, node_id):
    """destination=='both'：把 canvasNodeId 回写进 artifact，
    建立 Artifact <-> Canvas Node 双向引用（需求第十四条）。"""
    if not artifact_id or not node_id or not isinstance(canvas, dict):
        return False
    arts = canvas.get("artifacts") if isinstance(canvas.get("artifacts"), list) else []
    hit = None
    for a in arts:
        if isinstance(a, dict) and str(a.get("id") or "") == str(artifact_id):
            hit = a
            break
    if hit is None:
        return False
    hit["canvasNodeId"] = str(node_id)
    hit["updatedAt"] = int(time.time() * 1000)
    save = _agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(str(cid))), canvas, timeout=30)
    return bool(save.get("ok", save.get("canvas") is not None)) if isinstance(save, dict) else False


# ============ 统一批量操作协议（对标 operations 契约，所有 Agent 通道共用） ============
AGENT_BATCH_DIR = USER_DATA_DIR / "data" / "agent_batches"
AGENT_OP_TYPES = {"add_node", "update_node", "delete_node", "add_link", "delete_link", "set_variable", "layer_operate"}


def _agent_batch_build_text_node(canvas, params):
    text = str(params.get("text") or params.get("content") or "").strip()
    if not text:
        raise ValueError("add_node(text) 缺少 text")
    node_x, node_y = _agent_find_empty_position(canvas, params.get("x"), params.get("y"), 316, 194, category=_agent_category_from_title(params.get("title")), node_type="smart-prompt", text_len=len(text))
    return {
        "id": "agent_" + uuid.uuid4().hex[:12],
        "type": "smart-prompt",
        "title": str(params.get("title") or "Agent 笔记").strip(),
        "kind": "script",
        "text": text, "content": text,
        "promptDraftText": text,
        "promptDraftHtml": _agent_html_escape(text),
        "promptDraftTouched": True,
        "llmEnabled": False, "llmSystemEnabled": False,
        "llmSystemPrompt": "You are a helpful prompt assistant.",
        "llmInstruction": "",
        "x": node_x, "y": node_y, "w": 316, "h": 194,
        "created_at": int(time.time() * 1000),
        "status": "ready",
        "role": "text",
    }


def _agent_batch_build_generation_node(canvas, params, preset):
    prompt = str(params.get("prompt") or params.get("text") or "").strip()
    if not prompt:
        raise ValueError("add_node(generation) 缺少 prompt")
    settings = _agent_default_run_settings(params, preset)
    node_x, node_y = _agent_find_empty_position(canvas, params.get("x"), params.get("y"), 320, 420, category=_agent_category_from_title(params.get("title")), node_type="smart-image")
    refs = _agent_normalize_reference_items(params.get("reference_image_urls") or params.get("reference_images") or [])
    ref_node_ids, run_refs = [], []
    for ref in refs:
        url = str((ref or {}).get("url") or "").strip()
        if not url:
            continue
        node_id = str((ref or {}).get("nodeId") or "").strip()
        match = next((n for n in (canvas.get("nodes") or [])
                      if any(str(img.get("url") or "") == url for img in (n.get("images") or []) if isinstance(img, dict))
                      or (node_id and str(n.get("id") or "") == node_id)), None)
        if match and not node_id:
            node_id = str(match.get("id") or "")
        run_refs.append({
            "url": url,
            "name": str((ref or {}).get("name") or "图片{}".format(len(run_refs) + 1)).strip() or "图片{}".format(len(run_refs) + 1),
            "sourceName": str((ref or {}).get("sourceName") or (match.get("title") if isinstance(match, dict) else "") or "").strip(),
            "nodeId": node_id,
            "imageIndex": int(parse_number((ref or {}).get("imageIndex"), 0) or 0),
            "kind": "image",
        })
        if node_id:
            ref_node_ids.append(node_id)
    prompt_with_refs = prompt
    for r in run_refs:
        token = "@" + str(r.get("name") or "").strip()
        if token and token not in prompt_with_refs:
            prompt_with_refs += " 参考{}生成".format(token)
    return {
        "id": "agent_" + uuid.uuid4().hex[:12],
        "type": "smart-image",
        "title": str(params.get("title") or "Agent 生成").strip(),
        "promptDraftText": prompt_with_refs,
        "promptDraftHtml": _agent_html_escape(prompt_with_refs),
        "promptDraftTouched": True,
        "runPrompt": prompt_with_refs,
        "runPromptRefs": run_refs,
        "runInputRefs": run_refs,
        "inputNodeIds": list(dict.fromkeys(ref_node_ids)),
        "runSettings": _agent_run_settings_for_storage(settings),
        "images": [],
        "x": node_x, "y": node_y,
        "created_at": int(time.time() * 1000),
        "status": "pending",
        "role": "generation",
    }, list(dict.fromkeys(ref_node_ids))


def _agent_validate_operations(ops, node_ids):
    """执行前统一校验：op_type 合法性 + target 存在性。返回错误列表。"""
    errors = []
    pending_ids = set(node_ids)
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            errors.append("operations[{}]: 不是对象".format(i))
            continue
        t = str(op.get("op_type") or "").strip()
        if t not in AGENT_OP_TYPES:
            errors.append("operations[{}]: 非法 op_type '{}',只允许 {}".format(i, t, "/".join(sorted(AGENT_OP_TYPES))))
            continue
        params = op.get("params") if isinstance(op.get("params"), dict) else {}
        target = str(op.get("target_id") or params.get("node_id") or params.get("id") or "").strip()
        if t == "update_node":
            if not target:
                errors.append("operations[{}]: update_node 缺少 target_id".format(i))
            elif target not in pending_ids:
                errors.append("operations[{}]: 节点不存在: {}".format(i, target))
        elif t == "delete_node":
            if not target:
                errors.append("operations[{}]: delete_node 缺少 target_id".format(i))
            elif target not in pending_ids:
                errors.append("operations[{}]: 节点不存在: {}".format(i, target))
            else:
                pending_ids.discard(target)
        elif t == "add_link":
            f = str(params.get("from_id") or op.get("from_id") or "").strip()
            to = str(params.get("to_id") or op.get("to_id") or "").strip()
            if not f or not to:
                errors.append("operations[{}]: add_link 缺少 from_id/to_id".format(i))
            else:
                if f not in pending_ids:
                    errors.append("operations[{}]: add_link from 节点不存在: {}".format(i, f))
                if to not in pending_ids:
                    errors.append("operations[{}]: add_link to 节点不存在: {}".format(i, to))
        elif t == "delete_link":
            if not (str(params.get("from_id") or "") or str(params.get("to_id") or "")):
                errors.append("operations[{}]: delete_link 需要 from_id/to_id(至少其一)".format(i))
        elif t == "set_variable":
            if not str(params.get("name") or "").strip():
                errors.append("operations[{}]: set_variable 缺少 name".format(i))
        elif t == "layer_operate":
            if not target:
                errors.append("operations[{}]: layer_operate 缺少 target_id".format(i))
            elif target not in pending_ids:
                errors.append("operations[{}]: 节点不存在: {}".format(i, target))
    return errors


def _agent_apply_operation(canvas, op, preset, results, cid=None, session_id=""):
    t = str(op.get("op_type") or "").strip()
    params = op.get("params") if isinstance(op.get("params"), dict) else {}
    provenance = op.get("provenance") if isinstance(op.get("provenance"), dict) else params.get("provenance")
    target = str(op.get("target_id") or params.get("node_id") or params.get("id") or "").strip()
    nodes_list = canvas.get("nodes") if isinstance(canvas.get("nodes"), list) else []
    connections = canvas.get("connections")
    if not isinstance(connections, list):
        connections = []
        canvas["connections"] = connections
    if t == "add_node":
        node_type = str(params.get("node_type") or params.get("type") or "text").strip().lower()
        # Phase 5：artifactId 作为严格幂等键（intent_id/dedup_key 向后兼容映射）
        artifact_id = str(params.get("artifact_id") or params.get("artifactId") or params.get("intent_id") or params.get("dedup_key") or "").strip()
        if node_type in ("generation", "image", "smart-image", "gen"):
            node, ref_ids = _agent_batch_build_generation_node(canvas, params, preset)
            node["__origin"] = "agent_batch"
            ok, nid, deduped = _agent_prepare_node_for_canvas(None, canvas, node, "agent_batch", {"artifactId": artifact_id, "intent_id": artifact_id, "provenance": provenance})
            if not ok:
                append_log(LOG_FILE, "[CanvasNodeRejected] origin=agent_batch reason={} title={}".format(nid, str(node.get("title"))[:40]))
                results.append({"op": "add_node", "skipped": "gate", "reason": nid, "title": node.get("title")})
            else:
                if not deduped:
                    nodes_list.append(node)
                    for rid in ref_ids:
                        if rid != node["id"] and not any(c.get("from") == rid and c.get("to") == node["id"] and c.get("kind") == "input" for c in connections):
                            connections.append({"from": rid, "to": node["id"], "kind": "input"})
                results.append({"op": "add_node", "node_id": nid, "title": node.get("title"), "type": "smart-image", "artifactId": artifact_id, "deduped": deduped})
        else:
            # Phase 8：批量文本节点同样过 Router。只有 destination=='canvas' 才继续建节点，
            # 因此不会与既有 Artifact Gate 形成两条建节点路径（需求第三十三条）。
            _btype = str(params.get("artifact_type") or params.get("artifactType") or "").strip().lower() or "text"
            _broute = route_artifact(
                artifact_type=_btype,
                role="text",
                tool_name="canvas_batch_operations",
                user_text=str(CANVAS_AGENT_ROUTE_CONTEXT.get("user_text") or ""),
            )
            if str(_broute.get("destination") or "canvas") == "sidebar" and cid:
                _bok, _bid, _ = _agent_upsert_sidebar_artifact(
                    cid, canvas,
                    title=str(params.get("title") or "Agent 笔记").strip(),
                    content=str(params.get("text") or params.get("content") or ""),
                    artifact_type=_btype,
                    defer_save=True,
                    # Phase 9：一轮 Agent 会话 = 一个 Conversation Artifact
                    conversation_id=str(session_id or CANVAS_AGENT_CURRENT_SESSION.get("session_id") or ""),
                    conversation_title=str(CANVAS_AGENT_ROUTE_CONTEXT.get("user_text") or "")[:40],
                    section_type=str(params.get("section_type") or params.get("sectionType") or "").strip(),
                    section_title=str(params.get("section_title") or params.get("sectionTitle") or params.get("section") or "").strip(),
                    item_title=str(params.get("item_title") or params.get("itemTitle") or "").strip(),
                )
                if _bok:
                    results.append({"op": "add_node", "node_id": None, "artifact_id": _bid,
                                    "title": params.get("title"), "type": "sidebar-artifact",
                                    "destination": "sidebar", "reason": _broute.get("reason")})
                    return
            node = _agent_batch_build_text_node(canvas, params)
            node["__origin"] = "agent_batch"
            ok, nid, deduped = _agent_prepare_node_for_canvas(None, canvas, node, "agent_batch", {"artifactId": artifact_id, "intent_id": artifact_id, "provenance": provenance})
            if not ok:
                append_log(LOG_FILE, "[CanvasNodeRejected] origin=agent_batch reason={} title={}".format(nid, str(node.get("title"))[:40]))
                results.append({"op": "add_node", "skipped": "gate", "reason": nid, "title": node.get("title")})
            else:
                if not deduped:
                    nodes_list.append(node)
                results.append({"op": "add_node", "node_id": nid, "title": node.get("title"), "type": "smart-prompt", "artifactId": artifact_id, "deduped": deduped})
    elif t == "update_node":
        node = next((n for n in nodes_list if str(n.get("id")) == target), None)
        if node is None:
            raise ValueError("节点不存在: {}".format(target))
        for key in ("text", "title"):
            if params.get(key) is not None:
                node[key] = str(params[key])
                if key == "text":
                    node["content"] = str(params[key])
                    if node.get("type") == "smart-prompt":
                        node["promptDraftText"] = str(params[key])
                        node["promptDraftHtml"] = _agent_html_escape(str(params[key]))
                        node["promptDraftTouched"] = True
        if params.get("x") is not None or params.get("y") is not None:
            if params.get("x") is not None:
                node["x"] = float(params["x"])
            if params.get("y") is not None:
                node["y"] = float(params["y"])
        if params.get("prompt") is not None and node.get("type") == "smart-image":
            node["promptDraftText"] = str(params["prompt"])
            node["promptDraftHtml"] = _agent_html_escape(str(params["prompt"]))
            node["runPrompt"] = str(params["prompt"])
        results.append({"op": "update_node", "node_id": target})
    elif t == "delete_node":
        before = len(nodes_list)
        canvas["nodes"] = [n for n in nodes_list if str(n.get("id")) != target]
        canvas["connections"] = [c for c in connections if c.get("from") != target and c.get("to") != target]
        # Phase 4：写墓碑，防止前端合并时复活
        canvas["deleted"] = _merge_node_tombstones(
            canvas.get("deleted"), [{"id": target, "at": int(time.time() * 1000), "by": "agent"}]
        )
        results.append({"op": "delete_node", "node_id": target, "removed": before - len(canvas["nodes"]), "tombstoned": True})
    elif t == "add_link":
        f = str(params.get("from_id") or "").strip()
        to = str(params.get("to_id") or "").strip()
        kind = str(params.get("kind") or "input").strip() or "input"
        if f == to:
            raise ValueError("add_link: 不能连接节点到自身")
        if any(c.get("from") == f and c.get("to") == to and c.get("kind") == kind for c in connections):
            results.append({"op": "add_link", "from": f, "to": to, "skipped": "已存在"})
        else:
            connections.append({"from": f, "to": to, "kind": kind})
            results.append({"op": "add_link", "from": f, "to": to})
    elif t == "delete_link":
        f = str(params.get("from_id") or "").strip()
        to = str(params.get("to_id") or "").strip()
        before = len(connections)
        canvas["connections"] = [c for c in connections
                                 if not ((not f or c.get("from") == f) and (not to or c.get("to") == to))]
        results.append({"op": "delete_link", "from": f, "to": to, "removed": before - len(canvas["connections"])})
    elif t == "set_variable":
        settings = canvas.get("settings")
        if not isinstance(settings, dict):
            settings = {}
            canvas["settings"] = settings
        variables = settings.get("agent_variables")
        if not isinstance(variables, dict):
            variables = {}
            settings["agent_variables"] = variables
        name = str(params.get("name") or "").strip()
        value = params.get("value")
        variables[name] = value
        results.append({"op": "set_variable", "name": name, "value": value})
    elif t == "layer_operate":
        node = next((n for n in nodes_list if str(n.get("id")) == target), None)
        if node is None:
            raise ValueError("节点不存在: {}".format(target))
        action = str(params.get("action") or "").strip().lower()
        if action in ("hide", "visible_off"):
            node["visible"] = False
        elif action in ("show", "visible_on"):
            node["visible"] = True
        elif action == "front":
            nodes_list.remove(node)
            nodes_list.append(node)
        elif action == "back":
            nodes_list.remove(node)
            nodes_list.insert(0, node)
        else:
            raise ValueError("layer_operate: 非法 action '{}',只允许 show/hide/front/back".format(action))
        results.append({"op": "layer_operate", "node_id": target, "action": action})


def _agent_tool_batch_operations(args, preset=None, session_id=""):
    ops = args.get("operations")
    if not isinstance(ops, list):
        return {"ok": False, "error": "operations 数组必填"}
    ops = [op for op in ops if isinstance(op, dict) and str(op.get("op_type") or "").strip()][:50]
    if not ops:
        return {"ok": True, "batch_id": "", "results": [], "note": "空操作数组,未做任何变更"}
    cid, canvas = _agent_get_canvas(str(args.get("canvas_id") or ""))
    node_ids = {str(n.get("id")) for n in (canvas.get("nodes") or []) if isinstance(n, dict)}
    errors = _agent_validate_operations(ops, node_ids)
    if errors:
        return {"ok": False, "error": "操作校验失败,未执行任何变更", "errors": errors[:10]}
    snapshot = json.dumps(canvas, ensure_ascii=False)
    results = []
    batch_provenance = args.get("provenance") if isinstance(args.get("provenance"), dict) else None
    try:
        for op in ops:
            if batch_provenance and isinstance(op, dict):
                op = dict(op)
                params = op.get("params") if isinstance(op.get("params"), dict) else {}
                params = dict(params)
                params.setdefault("provenance", batch_provenance)
                op["params"] = params
                op.setdefault("provenance", batch_provenance)
            _agent_apply_operation(canvas, op, preset, results, cid, session_id=session_id)
    except Exception as exc:
        restored = json.loads(snapshot)
        canvas.clear()
        canvas.update(restored)
        _agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(cid)), canvas, timeout=30)
        return {"ok": False, "error": "执行失败已回滚: {}".format(exc), "rolled_back": True}
    save = _agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(cid)), canvas, timeout=30)
    created = [r for r in results if isinstance(r, dict) and r.get("op") == "add_node"]
    if created:
        append_log(LOG_FILE, "[CanvasBatchCreate] origin=agent_batch canvas={} count={} ids={}".format(
            cid, len(created), ",".join(str(r.get("node_id")) for r in created[:12])))
    batch_id = "batch_" + uuid.uuid4().hex[:12]
    try:
        AGENT_BATCH_DIR.mkdir(parents=True, exist_ok=True)
        (AGENT_BATCH_DIR / (batch_id + ".json")).write_text(json.dumps({
            "batch_id": batch_id, "canvas_id": cid, "created_at": int(time.time() * 1000),
            "snapshot": json.loads(snapshot), "operations": ops,
        }, ensure_ascii=False), encoding="utf-8")
    except Exception:
        batch_id = ""
    return {"ok": True, "batch_id": batch_id, "canvas_id": cid, "executed": len(results),
            "results": results, "save_ok": save.get("ok", save.get("canvas") is not None)}


def _agent_tool_undo_batch(args):
    batch_id = str(args.get("batch_id") or "").strip()
    if not batch_id:
        return {"ok": False, "error": "batch_id 必填"}
    path = AGENT_BATCH_DIR / (batch_id + ".json")
    if not path.exists():
        return {"ok": False, "error": "批次不存在或已过期: {}".format(batch_id)}
    data = json.loads(path.read_text(encoding="utf-8"))
    cid = str(data.get("canvas_id") or "")
    snapshot = data.get("snapshot")
    if not cid or not isinstance(snapshot, dict):
        return {"ok": False, "error": "批次快照损坏"}
    cur_cid, canvas = _agent_get_canvas(cid)
    canvas["nodes"] = snapshot.get("nodes") or []
    canvas["connections"] = snapshot.get("connections") or []
    if isinstance(snapshot.get("settings"), dict):
        canvas["settings"] = snapshot["settings"]
    save = _agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(cid)), canvas, timeout=30)
    return {"ok": True, "batch_id": batch_id, "canvas_id": cid,
            "undone_ops": len(data.get("operations") or []),
            "save_ok": save.get("ok", save.get("canvas") is not None)}


def _agent_tool_add_link(args):
    return _agent_tool_batch_operations({"operations": [{
        "op_type": "add_link",
        "params": {"from_id": args.get("from_id"), "to_id": args.get("to_id"), "kind": args.get("kind") or "input"},
    }, ], "canvas_id": args.get("canvas_id")})


def _agent_tool_delete_node(args):
    return _agent_tool_batch_operations({"operations": [{
        "op_type": "delete_node", "target_id": args.get("node_id"),
    }], "canvas_id": args.get("canvas_id")})


MODLENS_CACHE = {}
MODLENS_CACHE_DIR = USER_DATA_DIR / "data" / "modlens_cache"
MODLENS_CACHE_KEY_MAX = 64

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
        cid, canvas = _agent_get_canvas(str(args.get("canvas_id") or ""))
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
        local = _agent_local_path_for_url(image_url)
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
        saved = write_canvas_agent_skill(name, content)
    except ApiError as exc:
        return {"ok": False, "error": exc.detail}
    except Exception as exc:
        return {"ok": False, "error": "保存技能失败: {}".format(exc)}
    return {
        "ok": True,
        "skill": saved,
        "skills": list_canvas_agent_skills(),
        "note": "技能已保存。后续对话中可用 @{} 调用它。".format(saved.get("name") or name),
    }


def _agent_tool_list_skills(args):
    """列出已保存的技能（名称/大小/更新时间），避免重名覆盖。"""
    skills = list_canvas_agent_skills()
    previews = []
    for skill in skills[:30]:
        try:
            content = read_canvas_agent_skill(skill.get("name") or "")
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
CANVAS_AGENT_LOADED_SKILLS = {"skills": []}


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


def canvas_agent_execute_tool(name, args, preset=None, session_id=""):
    try:
        if name == "canvas_get_state":
            return _agent_tool_get_state(args)
        if name == "canvas_search_nodes":
            return _agent_tool_search_nodes(args)
        if name == "canvas_create_text_node":
            return _agent_tool_create_text_node(args, session_id=session_id)
        if name == "canvas_create_generation_node":
            return _agent_tool_create_generation_node(args, preset)
        if name == "canvas_generate_images":
            return _agent_tool_generate_images(args, preset)
        if name == "canvas_check_generation":
            return _agent_tool_check_generation(args)
        if name == "canvas_update_node":
            return _agent_tool_update_node(args)
        if name == "canvas_batch_operations":
            return _agent_tool_batch_operations(args, preset, session_id=session_id)
        if name == "canvas_undo_batch":
            return _agent_tool_undo_batch(args)
        if name == "canvas_add_link":
            return _agent_tool_add_link(args)
        if name == "canvas_delete_node":
            return _agent_tool_delete_node(args)
        if name == "canvas_analyze_image":
            return _agent_tool_analyze_image(args)
        if name == "canvas_list_skills":
            return _agent_tool_list_skills(args)
        if name == "canvas_save_skill":
            return _agent_tool_save_skill(args)
        if name == "present_im_interaction":
            return _agent_tool_present_interaction(args, session_id=session_id)
        return {"ok": False, "error": "未知工具: {}".format(name)}
    except Exception as exc:
        return {"ok": False, "error": "工具执行异常: {}".format(exc)}


# 交互回执：session_id -> {card_id, selection, submitted_at, resolved}
CANVAS_AGENT_RECEIPTS = {}
CANVAS_AGENT_RECEIPTS_LOCK = threading.Lock()


def submit_canvas_agent_interaction_receipt(payload):
    """接收用户对交互卡片的回执（点选/填写/确认）。
    只登记回执并标记卡片已解决；是否推进由前端用该回执重新发起一轮对话。"""
    payload = payload if isinstance(payload, dict) else {}
    session_id = str(payload.get("session_id") or payload.get("agent_session_id") or "").strip()
    card_id = str(payload.get("card_id") or "").strip()
    intent = str(payload.get("intent") or "").strip()
    if not session_id or not card_id:
        return {"ok": False, "error": "缺少 session_id 或 card_id"}
    receipt_selection = payload.get("selection")
    option_label = ""
    try:
        card = CANVAS_AGENT_INTERACTIONS.get(str(session_id))
        if isinstance(card, dict) and receipt_selection is not None:
            for opt in card.get("options") or []:
                if isinstance(opt, dict) and str(opt.get("id") or "") == str(receipt_selection):
                    option_label = str(opt.get("label") or "").strip()
                    break
    except Exception:
        option_label = ""
    receipt = {
        "card_id": card_id,
        "selection": receipt_selection,
        "selection_label": option_label,
        "fields": payload.get("fields") if isinstance(payload.get("fields"), dict) else {},
        "confirmed": bool(payload.get("confirmed")),
        "submitted_at": int(time.time() * 1000),
        "resolved": True,
    }
    try:
        with CANVAS_AGENT_RECEIPTS_LOCK:
            CANVAS_AGENT_RECEIPTS[str(session_id)] = receipt
            # 同时把对应交互卡片标记为已解决
            card = CANVAS_AGENT_INTERACTIONS.get(str(session_id))
            if card:
                card["resolved"] = True
    except Exception:
        pass
    try:
        with TASKS_LOCK:
            task = next((t for t in TASKS.values()
                         if isinstance(t, dict) and str(t.get("conversation_id") or "") == session_id
                         and t.get("status") in {"waiting_user", "running", "paused"}), None)
            if task:
                agent_runtime.record_decision(task, receipt)
                persist_tasks_locked()
                _agent_task_log("Decision", "task={} step={} card={} selection={} confirmed={}".format(
                    task.get("task_id"), task.get("current_step_id"), card_id, receipt_selection, receipt["confirmed"]))
    except Exception as exc:
        _agent_task_log("Decision", "record failed card={} error={}".format(card_id, exc))
    # 构造回执文本，供前端作为新 user 消息发给 LLM 推进
    receipt_text = ""
    if intent == "confirm" and not receipt["confirmed"]:
        # 确认卡选了"需要修改"：明确让主链停下，收集用户具体修改意见，不要继续执行
        receipt_text = "需要修改，我还没满意。请先别继续往下走，听我要改哪里：{}(如需补充请直接告诉我)".format(receipt["selection"] or "")
    elif receipt["confirmed"]:
        receipt_text = "已确认，请继续执行。"
    elif receipt["selection"] is not None:
        suffix = "（{}）".format(option_label) if option_label else ""
        receipt_text = "我选择：{}{}".format(receipt["selection"], suffix)
    if receipt["fields"]:
        receipt_text = "我填写：{}".format("，".join("{}={}".format(k, v) for k, v in receipt["fields"].items()))
    return {
        "ok": True,
        "receipt": receipt,
        "receipt_text": receipt_text or "已收到。",
    }


def get_canvas_agent_interaction(session_id=""):
    """读取某会话当前待展示的交互卡片（供前端轮询/渲染）。"""
    try:
        with CANVAS_AGENT_INTERACTIONS_LOCK:
            card = CANVAS_AGENT_INTERACTIONS.get(str(session_id or ""))
        return {"ok": True, "interaction": card}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def canvas_agent_tools_schema():
    return CANVAS_AGENT_TOOLS


def _agent_sanitize_messages(messages):
    out = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(str(block.get("text") or ""))
                    elif block.get("type") == "image_url":
                        url = block.get("image_url")
                        if isinstance(url, dict):
                            url = url.get("url") or ""
                        parts.append("[图片: {}]".format(url))
                    else:
                        parts.append(str(block))
                else:
                    parts.append(str(block))
            m = dict(m)
            m["content"] = "\n".join(p for p in parts if p)
        out.append(m)
    return out


def _agent_inject_tool_guidance(messages, preset=None):
    guidance = ("\n\n## 画布工具\n"
                "你可以调用工具直接在画布上工作:canvas_get_state 查看画布;canvas_search_nodes 搜索素材;"
                "对话中【引用图片】开头的文字就是后台视觉模型(GLM)对图片的识别描述,直接把它当作图片内容使用;"
                "canvas_create_text_node 写剧本/脚本/方案;【头脑风暴分层】同一次会话里产出多个板块(人物/故事/场面/世界观/视觉/结局方案)时,必须带 section_title(板块名,如'核心人物'),同一会话同一板块会合并更新而不是重复新建,整轮讨论会成为侧边栏里的一个整体产物;板块内还有多个并列条目(如林澜/司徒岳)时再带 item_title;canvas_create_generation_node 把图片提示词+引用图+生图预设同步到画布生成节点(建立待生成节点,返回 node_id);"
                "canvas_update_node 修改节点;canvas_check_generation 查询生成任务状态。"
                "canvas_batch_operations 批量执行标准化操作(add_node/update_node/delete_node/add_link/delete_link/set_variable/layer_operate,原子性,失败全回滚,适合一次建多个节点并连线);"
                "canvas_undo_batch 撤销某次批量操作;canvas_add_link 连线;canvas_delete_node 删除节点。"
                "canvas_generate_images 仅在用户明确要求马上出图时才使用(会阻塞等待生成完成)。"
                "生图标准流程:需要生成图片时,用 canvas_create_generation_node 在画布建立生成节点即可——不要在对话框内阻塞等待生成;用户会在画布节点上点执行按钮生成,然后你可以用 canvas_get_state 读取节点状态/生成结果。"
                "只要用了参考图,生成提示词里就必须逐张写出 @图片1/@图片2/... ,并明确说明每张图分别参考什么(如人物/服装/构图/配色/材质/光效);"
                "这些编号严格按当前会话输入链图片顺序决定,如果用了多张图,必须 @每一张,不要合并成笼统的“参考上图/参考图片”。"
                "canvas_list_skills 查看已保存的技能;canvas_save_skill 把对话中提炼的可复用方法/工作流/风格偏好保存为技能,"
                "之后用户或自己可 @技能名 调用。当用户教你一套方法、或你总结出可复用的创作流程时,主动保存成技能。"
                "present_im_interaction 用于需要用户决策的等待点:把选择/表单/确认/进度/产物以结构化卡片展示给用户点击。"
                "【硬性要求】当你要给用户几个方向/方案/风格让他选、要收集已知参数(画幅/时长/旁白/比例)、要在高成本动作(生成素材/视频)前请用户确认、要展示生成进度、要交付最终产物时,"
                "必须调用 present_im_interaction 工具把内容做成结构化卡片(choose/collect/confirm/progress/artifact),通过 tool_calls 而不是正文。"
                "严格禁止:在正文写 A./B./C. 编号列选项、写“回复1或2”、让用户打字回答本该是选择题的、把该确认的写成文字问句。"
                "一卡一决策,发出卡片后本轮立即结束,等待用户回执,不要同轮继续执行未授权动作。"
                "把 options 的 id 写成 A/B/C,label 写清晰标题,desc 写一句可感知的差异化描述,default 预选一个最稳妥的;collect 的字段值闭集用 select 下拉。")
    guidance += (
        "\n\n## 短剧制作板流程\n"
        "当用户点击剧情短片、说创作短剧/拍剧情视频/做微剧,且没有明确给出完整标准分镜或已选制作模式时,"
        "第一轮必须调用 present_im_interaction(intent=choose) 发模式卡,只给三项:快速出片、专业制作、已有剧本。"
        "不要直接生成大纲/剧本/分镜,也不要同时询问比例/时长/风格。"
        "用户选模式后,把短剧创作收敛为用户侧五步:选模式→生成短剧制作板→确认内容→执行节点→选结果/重拍/合成。"
        "内部可以按叙事短片主链的九阶段推演,但用户侧不要连续暴露大纲确认、剧本确认、素材确认、Clip表确认。"
        "短剧制作板应优先落到画布,包含 Brief、剧本/梗概、素材清单、Clip表、素材生成节点、视频生成节点。"
        "能一次创建多个节点时优先 canvas_batch_operations,并把相关节点连线;对话里只说明已创建哪些制作板节点和下一步可执行动作。"
    )
    if isinstance(preset, dict) and preset:
        preset_desc = "当前生图预设(用户配置):平台={provider_id},模型={model},比例={aspectRatio},分辨率={resolution},质量={quality}。生成图片时默认使用这些参数,除非用户明确要求不同的参数。".format(
            provider_id=preset.get("provider_id") or "runninghub",
            model=preset.get("model") or "按 API 设置中已配置的模型自动选择",
            aspectRatio=preset.get("aspectRatio") or "4:3",
            resolution=preset.get("resolution") or "2k",
            quality=preset.get("quality") or "medium",
        )
        guidance += "\n\n" + preset_desc
    for i, m in enumerate(messages):
        if m.get("role") == "system":
            messages[i] = dict(m)
            messages[i]["content"] = str(m.get("content") or "") + guidance
            return messages
    return [{"role": "system", "content": guidance}] + messages


def _agent_append_system(messages, text):
    if not text:
        return messages
    for i, m in enumerate(messages):
        if m.get("role") == "system":
            messages[i] = dict(m)
            messages[i]["content"] = str(m.get("content") or "") + "\n\n" + text
            return messages
    return [{"role": "system", "content": text}] + messages


def _agent_reply_rules():
    """回复与建议格式规则：建议用 A./B./C. 编号；用户采纳后只简短确认并执行。"""
    return (
        "## 回复与建议格式\n"
        "1. 当你的回复给用户可选择的行动建议时,用 A./B./C. 编号输出,每项不超过一句话,保持简洁。\n"
        "2. 用户采纳某项建议(回复如'选A'、'用B'、'A')时,只做最简短的确认并立即执行,不要重复展开建议内容、不要长篇解释。\n"
        "3. 只要调用了参考图片来生成或改写提示词,就必须逐张写出 @图片1/@图片2/... ,并说明这张图具体参考什么;这些编号严格按当前会话输入链图片顺序决定。如果用了多张,必须 @每一张分别说明,不能笼统写“参考图片”。"
    )


def _agent_brainstorm_guidance(brainstorm):
    stage = str((brainstorm or {}).get("stage") or "方向探索")
    decisions = (brainstorm or {}).get("decisions") or []
    decision_lines = "\n".join(
        "- {}: {}".format(d.get("key"), d.get("value"))
        for d in decisions if isinstance(d, dict)
    ) or "（暂无）"
    json_example = '{"stage":"当前阶段","question":"需要用户决策的问题","candidates":[{"id":"A","title":"候选标题","desc":"一句话描述","prompt":"该候选对应的画面/视频生成提示词","tags":["标签"]}],"decisions":[{"key":"决策项","value":"已确认值"}],"done":false}'
    rules = (
        "## 头脑风暴模式\n"
        "你正在以一问一答的方式帮用户开发创意(类似专业创意头脑风暴)。规则：\n"
        "当前阶段：" + stage + "。已确认决策：\n" + decision_lines + "\n"
        "1. 每次回复**只输出一个 JSON 对象**，不要输出任何其他文字、解释、代码块或 markdown。\n"
        "2. JSON 格式：\n" + json_example + "\n"
        "3. **字符串值内部禁止使用英文双引号**，需要引号时一律用中文引号「」或单引号，否则 JSON 会解析失败。\n"
        "4. 阶段推进：方向探索→深化→确认→落地。\n"
        "   - 方向探索：给 2-3 个明显不同的候选方向，让用户选一个或说“换一批”。\n"
        "   - 深化：基于选定方向，逐个问关键细节（受众/卖点/场景/调性/结构），每次只问一个问题，可给子候选。\n"
        "   - 确认：汇总已确认内容，让用户确认是否完成。\n"
        "   - 落地：调用 canvas_create_text_node 工具把创意简报/角色/世界观/剧本/分镜写入画布，然后 done=true，在 question 里说明已写入哪些节点。\n"
        "5. candidates 每次最多 3 个；用户说“换一批”就重新给一批完全不同的候选。\n"
        "6. decisions 每轮都要带上全部已确认项（累加），不要丢失。\n"
        "7. 一次只问一个问题，一次最多给 3 个候选。\n"
        "8. **每个候选都必须带 prompt 字段**：该候选方向对应的、可直接用于图片/视频生成的画面提示词（具体、可视、含主体/场景/光影/镜头）。用户点选候选后，软件会按每个候选各建一个生成节点，prompt 分开使用。"
    )
    return rules


def _agent_candidate_interaction_guidance():
    """默认候选交互引导：不依赖任何开关。当回复适合给出多个可选方向/方案/风格时，
    用带 prompt 的 candidates JSON，前端会渲染成可选卡片，点选后只建所选候选的节点。"""
    json_example = '{"stage":"方向探索","question":"需要用户决策的问题","candidates":[{"id":"A","title":"候选标题","desc":"一句话描述","prompt":"该候选对应的画面/视频生成提示词","tags":["标签"]}],"decisions":[],"done":false}'
    return (
        "## 候选交互（默认启用）\n"
        "当你的回复适合给出多个明显不同的可选方向/方案/风格/调性（例如用户要几个方案、几个方向、几个镜头思路）时，"
        "用候选卡片的形式输出，规则：\n"
        "1. 只输出一个 JSON 对象，不要附加任何解释文字、代码块或 markdown。\n"
        "2. JSON 格式：\n" + json_example + "\n"
        "3. **字符串值内部禁止使用英文双引号**，需要引号时用中文引号「」或单引号，否则 JSON 解析失败。\n"
        "4. candidates 每次最多 3 个，每个候选**必须带 prompt 字段**（该候选可直接用于图片/视频生成的画面提示词，具体、可视、含主体/场景/光影/镜头）。\n"
        "5. 若用户只是问某一个具体问题、不需要对比选择，则**正常用文本回答**，不要输出 JSON。\n"
    )


def _model_supports_vision(model):
    """判断模型是否原生支持视觉输入（支持则直接传图，否则走后台视觉转文字）。"""
    m = str(model or "").lower()
    return any(k in m for k in [
        "glm-4v", "vl", "vision", "qwen-vl", "qwen2.5-vl", "qwen3-vl",
        "gpt-4", "gpt-4o", "gpt-4.1", "omni", "gemini", "doubao-1-5-vision",
        "kimi-latest", "moonshot-v1-8k-vision", "claude-3", "grok-4.1-vision",
    ])


VISION_CACHE = {}
VISION_CACHE_DIR = USER_DATA_DIR / "data" / "vision_cache"

def _vision_cache_key_file(cache_key):
    try:
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:24]
        return VISION_CACHE_DIR / (digest + ".json")
    except Exception:
        return None

def _vision_cache_disk_get(cache_key):
    try:
        f = _vision_cache_key_file(cache_key)
        if f is None or not f.exists():
            return None
        data = json.loads(f.read_text(encoding="utf-8"))
        return data.get("desc") if isinstance(data, dict) else None
    except Exception:
        return None

def _vision_cache_disk_put(cache_key, desc):
    try:
        f = _vision_cache_key_file(cache_key)
        if f is None:
            return
        VISION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"key": cache_key[:64], "desc": desc}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _vision_describe_image(data_url, prompt="请详细描述这张图片的内容：主体、环境、构图、光线、风格、画面中的文字等。用中文回答。"):
    """后台视觉通道：调视觉模型（默认智谱 glm-4v-flash 免费）把图片转成文字描述。"""
    vconf = canvas_agent_vision_config()
    key = str(vconf.get("api_key") or "").strip()
    if not key:
        try:
            key = str((read_env_values() or {}).get("GLM_API_KEY") or "").strip()
        except Exception:
            key = ""
    if not key:
        return ""
    base_url = str(vconf.get("base_url") or "https://open.bigmodel.cn/api/paas/v4").strip().rstrip("/")
    # 视觉识别用图在通道内独立压缩（最长边 1024 / JPEG 80 / 去透明）——
    # 识别内容足够，比主链路 2048 快 2-4 倍；压缩失败降级用原图。
    payload_url = str(data_url or "")
    try:
        from PIL import Image
        header, _, b64part = payload_url.partition(",")
        if ";base64" in header.lower() and b64part:
            img = Image.open(io.BytesIO(base64.b64decode(b64part)))
            img.thumbnail((1024, 1024), Image.LANCZOS)
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=80)
            payload_url = "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode("ascii")
    except Exception:
        payload_url = str(data_url or "")
    # 缓存 key：压缩后图片内容 hash + prompt 前缀（同一素材重复引用秒回）
    cache_key = ""
    try:
        header, _, b64part = payload_url.partition(",")
        img_bytes = base64.b64decode(b64part) if b64part else b""
        if img_bytes:
            cache_key = hashlib.md5(img_bytes).hexdigest() + "|" + prompt[:30]
    except Exception:
        cache_key = ""
    if cache_key:
        cached = VISION_CACHE.get(cache_key)
        if cached is None:
            cached = _vision_cache_disk_get(cache_key)
            if cached is not None:
                VISION_CACHE[cache_key] = cached
        if cached:
            return cached
    body = {
        "model": str(vconf.get("model") or "glm-4v-flash").strip() or "glm-4v-flash",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": payload_url}},
        ]}],
        "temperature": 0.3,
    }
    desc = ""
    try:
        data = request_json("{}/chat/completions".format(base_url), "POST",
                            body, headers={"Authorization": "Bearer {}".format(key)}, timeout=120)
        choices = data.get("choices") or []
        msg = (choices[0].get("message") if choices and isinstance(choices[0], dict) else {}) or {}
        desc = str(msg.get("content") or "").strip()
    except Exception as exc:
        append_log(LOG_FILE, "vision describe failed: {}".format(exc))
        desc = ""
    if desc and cache_key:
        VISION_CACHE[cache_key] = desc
        _vision_cache_disk_put(cache_key, desc)
    return desc


def _agent_auto_vision_messages(messages, model):
    """后台视觉通道入口：主模型不支持视觉时，把 messages 里的图片自动转成文字描述。

    有图时自己走视觉 API（glm-4v-flash 免费），转成文字给主模型读——
    不需要暴露视觉模型给用户选，也不用等 Agent 手动调 ModLens。
    """
    if _model_supports_vision(model):
        return messages
    vconf = canvas_agent_vision_config()
    if not vconf["enabled"]:
        return messages
    if not isinstance(messages, list):
        return messages
    # 收集所有图片 url（去重）
    all_urls = []
    for m in messages:
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if isinstance(b, dict) and b.get("type") == "image_url":
                u = str((b.get("image_url") or {}).get("url") or "").strip()
                if u:
                    all_urls.append(u)
    unique_urls = list(dict.fromkeys(all_urls))
    if not unique_urls:
        return messages
    # 多图并行描述（单图直接调）
    desc_map = {}
    if len(unique_urls) == 1:
        desc_map[unique_urls[0]] = _vision_describe_image(unique_urls[0])
    else:
        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(4, len(unique_urls))) as ex:
                futures = {ex.submit(_vision_describe_image, u): u for u in unique_urls}
                for fut in futures:
                    desc_map[futures[fut]] = fut.result() or ""
        except Exception:
            for u in unique_urls:
                desc_map[u] = _vision_describe_image(u)
    # 替换图片块为文字描述
    seen = set()
    changed = False
    for m in messages:
        content = m.get("content")
        if not isinstance(content, list):
            continue
        new_blocks = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "image_url":
                url = str((b.get("image_url") or {}).get("url") or "").strip()
                if url and url not in seen and desc_map.get(url):
                    seen.add(url)
                    new_blocks.append({"type": "text", "text": "【引用图片】{}".format(desc_map[url])})
                    changed = True
                    continue
                new_blocks.append(b)
            else:
                new_blocks.append(b)
        if changed:
            m["content"] = new_blocks
    if changed:
        append_log(LOG_FILE, "agent auto-vision: {} image(s) described via GLM (model={})".format(len(desc_map), model))
    return messages


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
            append_log(LOG_FILE, "codex bridge image download failed url={}: {}".format(text, exc))
            return None, None
    clean = text.split("?", 1)[0].split("#", 1)[0]
    if clean.startswith("/assets/"):
        rel = urllib.parse.unquote(clean[len("/assets/"):].lstrip("/"))
        local_path = ASSETS_DIR / rel
    elif clean.startswith("assets/"):
        rel = urllib.parse.unquote(clean[len("assets/"):].lstrip("/"))
        local_path = ASSETS_DIR / rel
    else:
        local_path = Path(urllib.parse.unquote(clean))
    try:
        resolved = local_path.resolve()
        if resolved.exists():
            return resolved.read_bytes(), mimetypes.guess_type(str(resolved))[0] or "image/png"
    except Exception as exc:
        append_log(LOG_FILE, "codex bridge local image read failed url={}: {}".format(text, exc))
    return None, None


def _codex_bridge_attachment_files(payload):
    file_paths = []
    raw_images = payload.get("images") or payload.get("image_urls") or []
    if isinstance(raw_images, (str, dict)):
        raw_images = [raw_images]
    CODEX_LOCAL_IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(raw_images[:4]):
        if isinstance(item, dict):
            raw_url = item.get("source_url") or item.get("sourceUrl") or item.get("url") or item.get("path") or ""
            node_id = str(item.get("nodeId") or item.get("node_id") or "").strip()
            if node_id:
                node_img = _agent_canvas_node_image_by_id(node_id, item.get("imageIndex"))
                if node_img:
                    raw_url = node_img
        else:
            raw_url = item
        image_bytes, mime_type = _codex_bridge_image_bytes_from_url(raw_url)
        if not image_bytes:
            continue
        suffix = _codex_bridge_file_suffix(mime_type)
        digest = hashlib.sha256(image_bytes).hexdigest()
        target = CODEX_LOCAL_IMAGE_CACHE_DIR / ("img_{}{}".format(digest, suffix))
        if not target.exists():
            target.write_bytes(image_bytes)
        file_paths.append(str(target))
    return file_paths


def _codex_bridge_prompt_text(payload, messages):
    sanitized = _agent_sanitize_messages([dict(m) for m in messages])
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
    created_nodes = _agent_result_created_nodes(tool_log)
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
    pending = _agent_take_pending_interaction(session_id or CANVAS_AGENT_CURRENT_SESSION.get("session_id") or "")
    if pending:
        extra["interaction"] = pending
    # 本轮加载的技能名，供前端在回复里展示"本次加载的技能"
    if CANVAS_AGENT_LOADED_SKILLS.get("skills"):
        extra["loaded_skills"] = list(CANVAS_AGENT_LOADED_SKILLS["skills"])
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
    if model == CODEX_LOCAL_DEFAULT_MODEL:
        model = CODEX_LOCAL_DEFAULT_RUNTIME_MODEL
    codex_executable = resolve_codex_executable()
    CODEX_LOCAL_REPLY_DIR.mkdir(parents=True, exist_ok=True)
    output_file = CODEX_LOCAL_REPLY_DIR / ("codex_bridge_reply_{}.txt".format(uuid.uuid4().hex))
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
            str(CODEX_LOCAL_WORKSPACE),
            "--add-dir",
            str(USER_DATA_DIR),
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
    if runtime_model == CODEX_LOCAL_DEFAULT_MODEL or not runtime_model:
        runtime_model = CODEX_LOCAL_DEFAULT_RUNTIME_MODEL
    thread_id = str(session_id or "").strip()
    try:
        thread_id = CODEX_APP_SERVER_BRIDGE.ensure_thread(thread_id, runtime_model)
        result = CODEX_APP_SERVER_BRIDGE.run_turn(thread_id, prompt_text, runtime_model, attachment_files)
    except Exception as exc:
        CODEX_APP_SERVER_BRIDGE.reset()
        raise RuntimeError("本地 Myrid-Agent 常驻 Bridge 调用失败: {}".format(str(exc)[:400]))
    return {
        "text": str(result.get("text") or "").strip(),
        "returncode": 0,
        "stdout_events": 0,
        "thread_id": thread_id,
        "bridge_mode": "app_server_ws",
    }


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
        CANVAS_AGENT_CURRENT_SESSION["session_id"] = session_id
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
    result = _agent_tool_present_interaction(card_args, session_id=session_id)
    return _build_canvas_agent_result(
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
        CANVAS_AGENT_CURRENT_SESSION["session_id"] = session_id
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
    result = _agent_tool_present_interaction(card_args, session_id=session_id)
    return _build_canvas_agent_result(
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
        CANVAS_AGENT_CURRENT_SESSION["session_id"] = session_id
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
    result = _agent_tool_present_interaction(card_args, session_id=session_id)
    return _build_canvas_agent_result(
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
                     or CANVAS_AGENT_CURRENT_SESSION.get("session_id") or "").strip()
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
        return _build_canvas_agent_result(
            preview,
            raw={"short_drama_script_board_ready": True, "node_count": len(ops), "operations": ops},
        )
    batch_args = {"operations": ops}
    key = _agent_short_drama_board_key(payload, "script_exec")
    cached = _AGENT_SHORT_DRAMA_BOARD_EXECUTED.get(key)
    if cached is not None:
        append_log(LOG_FILE, "short-drama script board idempotent skip key={}".format(key))
        return cached
    batch_result = _agent_tool_batch_operations(batch_args, payload.get("generation_preset") if isinstance(payload.get("generation_preset"), dict) else None)
    result = _build_canvas_agent_result(
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
        return _build_canvas_agent_result(
            preview,
            raw={"short_drama_board_ready": True, "node_count": len(ops), "operations": ops},
        )
    batch_args = {"operations": ops}
    key = _agent_short_drama_board_key(payload, "board_exec")
    cached = _AGENT_SHORT_DRAMA_BOARD_EXECUTED.get(key)
    if cached is not None:
        append_log(LOG_FILE, "short-drama board idempotent skip key={}".format(key))
        return cached
    batch_result = _agent_tool_batch_operations(batch_args, payload.get("generation_preset") if isinstance(payload.get("generation_preset"), dict) else None)
    result = _build_canvas_agent_result(
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


def submit_codex_chat(payload):
    codex_session_id = str(payload.get("agent_session_id") or payload.get("session_id") or "").strip()
    CANVAS_AGENT_CURRENT_SESSION["session_id"] = codex_session_id
    script_board_result = _agent_short_drama_script_board_result(payload)
    if script_board_result:
        return finish_runtime(script_board_result)
    board_result = _agent_short_drama_board_result(payload)
    if board_result:
        return finish_runtime(board_result)
    script_param_card = _agent_short_drama_script_param_card_result(payload)
    if script_param_card:
        return finish_runtime(script_param_card)
    param_card = _agent_short_drama_param_card_result(payload)
    if param_card:
        return finish_runtime(param_card)
    mode_card = _agent_short_drama_mode_card_result(payload)
    if mode_card:
        return finish_runtime(mode_card)
    messages = normalize_chat_messages(payload)
    messages = _agent_sanitize_messages(messages)
    tools = payload.get("tools") or canvas_agent_tools_schema()
    preset = payload.get("generation_preset")
    preset = preset if isinstance(preset, dict) else {}
    if tools:
        messages = _agent_inject_tool_guidance(messages, preset)
    brainstorm = payload.get("brainstorm")
    if isinstance(brainstorm, dict) and brainstorm:
        messages = _agent_append_system(messages, _agent_brainstorm_guidance(brainstorm))
    messages = _agent_append_system(messages, _agent_reply_rules())
    # 默认候选交互：命中流程型技能（叙事短片主链）时跳过，避免压过技能的阶段推进
    if not _agent_has_flow_skill(payload):
        messages = _agent_append_system(messages, _agent_candidate_interaction_guidance())
    if tools:
        messages = _agent_append_system(messages, _codex_bridge_protocol_instruction(tools, preset))
    messages = _codex_bridge_compact_messages(messages)
    model = str(payload.get("model") or "").strip()
    if model == CODEX_LOCAL_DEFAULT_MODEL:
        model = ""
    session_key, session_record = ("", None)
    if CODEX_LOCAL_PERSIST_SESSIONS:
        session_key, session_record = _codex_bridge_session_record(payload, model or CODEX_LOCAL_DEFAULT_MODEL)
    if session_record:
        latest_user = next((msg for msg in reversed(messages) if msg.get("role") == "user"), None)
        system_messages = [msg for msg in messages if msg.get("role") == "system"]
        resumed_messages = []
        if system_messages:
            resumed_messages.append(system_messages[0])
        if latest_user:
            resumed_messages.append(latest_user)
        if resumed_messages:
            messages = resumed_messages
    attachment_files = _codex_bridge_attachment_files(payload)
    tool_log = []
    last_meta = {"returncode": 0, "stdout_events": 0}
    try:
        max_turns = CANVAS_AGENT_MAX_TOOL_TURNS if tools else 1
        for turn in range(max_turns + 1):
            prompt_text = _codex_bridge_prompt_text(payload, messages)
            active_session_id = str((session_record or {}).get("thread_id") or "").strip()
            try:
                if CODEX_LOCAL_PERSIST_SESSIONS:
                    result = _run_codex_bridge_persistent(prompt_text, model, attachment_files, active_session_id)
                else:
                    result = _run_codex_bridge_exec(prompt_text, model, attachment_files, "")
                    result["bridge_mode"] = "exec_ephemeral"
            except RuntimeError as app_server_exc:
                if not CODEX_LOCAL_PERSIST_SESSIONS:
                    raise
                append_log(LOG_FILE, "codex app-server bridge fallback: {}".format(str(app_server_exc)[:300]))
                try:
                    result = _run_codex_bridge_exec(prompt_text, model, attachment_files, active_session_id)
                except RuntimeError as exc:
                    error_text = str(exc)
                    if _codex_bridge_should_reset_session(error_text, bool(active_session_id)):
                        append_log(LOG_FILE, "codex bridge reset stale/conflict session={}".format(active_session_id or "-"))
                        _codex_bridge_clear_session_record(session_key)
                        session_record = None
                        result = _run_codex_bridge_exec(prompt_text, model, attachment_files, "")
                    else:
                        raise
            final_text = result.get("text") or ""
            last_meta = result
            thread_id = str(result.get("thread_id") or "").strip()
            if CODEX_LOCAL_PERSIST_SESSIONS and thread_id:
                _codex_bridge_store_session_record(session_key, thread_id, model or CODEX_LOCAL_DEFAULT_MODEL)
                session_record = {"thread_id": thread_id, "model": model or CODEX_LOCAL_DEFAULT_MODEL}
            if not tools:
                append_log(LOG_FILE, "codex bridge ok model={} images={} returncode={} session={} mode={}".format(model or CODEX_LOCAL_DEFAULT_MODEL, len(attachment_files), result.get("returncode") or 0, thread_id or active_session_id or "new", result.get("bridge_mode") or "exec"))
                return {
                    "text": final_text,
                    "raw": {
                        "provider": "codex-local",
                        "model": model or CODEX_LOCAL_DEFAULT_MODEL,
                        "returncode": result.get("returncode") or 0,
                        "stdout_events": result.get("stdout_events") or 0,
                        "tool_turns": 0,
                        "thread_id": thread_id or active_session_id,
                        "bridge_mode": result.get("bridge_mode") or "exec",
                    },
                    "tool_log": [],
                    "agent_result": _build_canvas_agent_result(
                        final_text,
                        [],
                        {"provider": "codex-local", "model": model or CODEX_LOCAL_DEFAULT_MODEL},
                        "plain_text",
                        session_id=codex_session_id,
                    ),
                }
            parsed = _codex_bridge_extract_json(final_text)
            if not parsed:
                fallback_nodes = []
                if CANVAS_AGENT_ALLOW_TEXT_FALLBACK_NODES and _codex_bridge_request_wants_canvas_nodes(payload):
                    fallback_nodes = _codex_bridge_extract_generation_nodes(final_text, (payload or {}).get("message") or "")
                    if not fallback_nodes and _codex_bridge_request_wants_canvas_nodes(payload):
                        fallback_nodes = _codex_bridge_extract_generation_nodes((payload or {}).get("message") or "", (payload or {}).get("message") or "")
                    if not fallback_nodes and _codex_bridge_request_wants_canvas_nodes(payload):
                        fallback_nodes = _codex_bridge_default_generation_nodes(final_text, (payload or {}).get("message") or "")
                if tools and fallback_nodes:
                    for node in fallback_nodes:
                        args = _agent_merge_payload_refs_into_tool_args("canvas_create_generation_node", {
                            "title": str(node.get("title") or "").strip(),
                            "prompt": str(node.get("prompt") or "").strip(),
                            "canvas_id": str((payload or {}).get("canvas_id") or ""),
                        }, payload)
                        result_data = canvas_agent_execute_tool("canvas_create_generation_node", args, preset, codex_session_id)
                        tool_log.append({"name": "canvas_create_generation_node", "args": args, "result": result_data})
                    created_count = len([entry for entry in tool_log if str((entry.get("result") or {}).get("node_id") or "").strip()])
                    if created_count:
                        final_text = _codex_bridge_cleanup_fallback_text(final_text)
                        final_text = "{}\n\n已自动创建 {} 个画布生成节点，可直接点击执行。".format(final_text.strip(), created_count).strip()
                        append_log(LOG_FILE, "codex bridge fallback-created-nodes model={} count={}".format(model or CODEX_LOCAL_DEFAULT_MODEL, created_count))
                        return {
                            "text": final_text,
                            "raw": {
                                "provider": "codex-local",
                                "model": model or CODEX_LOCAL_DEFAULT_MODEL,
                                "returncode": result.get("returncode") or 0,
                                "stdout_events": result.get("stdout_events") or 0,
                                "tool_turns": len(tool_log),
                                "output_mode": "plain_text_fallback_nodes",
                            },
                            "tool_log": tool_log,
                            "agent_result": _build_canvas_agent_result(
                                final_text,
                                tool_log,
                                {"provider": "codex-local", "model": model or CODEX_LOCAL_DEFAULT_MODEL},
                                "plain_text_fallback_nodes",
                                session_id=codex_session_id,
                            ),
                        }
                if fallback_nodes and not CANVAS_AGENT_ALLOW_TEXT_FALLBACK_NODES:
                    append_log(LOG_FILE, "codex bridge fallback nodes suppressed (CANVAS_AGENT_ALLOW_TEXT_FALLBACK_NODES=False) count={}".format(len(fallback_nodes)))
                append_log(LOG_FILE, "codex bridge non-json fallback model={} turn={}".format(model or CODEX_LOCAL_DEFAULT_MODEL, turn + 1))
                return {
                    "text": final_text,
                    "raw": {
                        "provider": "codex-local",
                        "model": model or CODEX_LOCAL_DEFAULT_MODEL,
                        "returncode": result.get("returncode") or 0,
                        "stdout_events": result.get("stdout_events") or 0,
                        "tool_turns": len(tool_log),
                        "thread_id": thread_id or active_session_id,
                        "bridge_mode": result.get("bridge_mode") or "exec",
                        "output_mode": "plain_text",
                    },
                    "tool_log": tool_log,
                    "agent_result": _build_canvas_agent_result(
                        final_text,
                        tool_log,
                        {"provider": "codex-local", "model": model or CODEX_LOCAL_DEFAULT_MODEL},
                        "plain_text",
                        session_id=codex_session_id,
                    ),
                }
            assistant_reply = str(parsed.get("assistant_reply") or parsed.get("text") or parsed.get("reply") or "").strip()
            tool_calls = _codex_bridge_normalize_tool_calls(parsed)
            done = bool(parsed.get("done"))
            if not tool_calls:
                text = assistant_reply or final_text
                append_log(LOG_FILE, "codex bridge ok model={} images={} returncode={} tool_calls={}".format(model or CODEX_LOCAL_DEFAULT_MODEL, len(attachment_files), result.get("returncode") or 0, len(tool_log)))
                return {
                    "text": text,
                    "raw": {
                        "provider": "codex-local",
                        "model": model or CODEX_LOCAL_DEFAULT_MODEL,
                        "returncode": result.get("returncode") or 0,
                        "stdout_events": result.get("stdout_events") or 0,
                        "tool_turns": len(tool_log),
                        "thread_id": thread_id or active_session_id,
                        "bridge_mode": result.get("bridge_mode") or "exec",
                        "done": done,
                        "output_mode": "json_protocol",
                    },
                    "tool_log": tool_log,
                    "agent_result": _build_canvas_agent_result(
                        text,
                        tool_log,
                        {"provider": "codex-local", "model": model or CODEX_LOCAL_DEFAULT_MODEL},
                        "json_protocol",
                        {"done": done},
                        session_id=codex_session_id,
                    ),
                }
            messages.append({"role": "assistant", "content": assistant_reply or "我现在开始执行画布操作。"})
            CANVAS_AGENT_ROUTE_CONTEXT["user_text"] = _agent_latest_user_text(payload)
            for tc in tool_calls:
                name = tc.get("name") or ""
                args = _agent_merge_payload_refs_into_tool_args(name, tc.get("arguments") or {}, payload)
                result_data = canvas_agent_execute_tool(name, args, preset, codex_session_id)
                tool_log.append({"name": name, "args": args, "result": result_data})
                tool_content = json.dumps(result_data, ensure_ascii=False)
                if len(tool_content) > 8000:
                    tool_content = tool_content[:8000] + "...(结果已截断)"
                messages.append({"role": "tool", "content": "{} => {}".format(name, tool_content)})
        return {
            "text": "我已经执行了一部分画布操作，但工具调用达到轮次上限。请看画布里的新增节点，再告诉我是否继续。",
            "raw": {
                "provider": "codex-local",
                "model": model or CODEX_LOCAL_DEFAULT_MODEL,
                "returncode": last_meta.get("returncode") or 0,
                "stdout_events": last_meta.get("stdout_events") or 0,
                "tool_turns": len(tool_log),
                "thread_id": last_meta.get("thread_id") or "",
                "bridge_mode": last_meta.get("bridge_mode") or "exec",
                "done": False,
                "output_mode": "json_protocol",
            },
            "tool_log": tool_log,
            "agent_result": _build_canvas_agent_result(
                "我已经执行了一部分画布操作，但工具调用达到轮次上限。请看画布里的新增节点，再告诉我是否继续。",
                tool_log,
                {"provider": "codex-local", "model": model or CODEX_LOCAL_DEFAULT_MODEL},
                "json_protocol",
                {"done": False},
                session_id=codex_session_id,
            ),
        }
    finally:
        pass


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


def submit_chat(payload):
    payload = payload if isinstance(payload, dict) else {}
    # 本请求的会话 id：显式从 payload 取，沿调用链传递，
    # 不再依赖全局 CANVAS_AGENT_CURRENT_SESSION（并发会话会互相覆盖）。
    agent_session_id = str(payload.get("agent_session_id") or payload.get("session_id") or "").strip()
    task = _agent_task_for_payload(payload)
    turn = agent_runtime.begin_turn(task, _agent_latest_user_text(payload))

    def finish_runtime(result, assistant_text=None, tool_log=None, interaction=None):
        if not isinstance(result, dict):
            result = {"text": str(result or "")}
        agent_result = result.get("agent_result") if isinstance(result.get("agent_result"), dict) else {}
        resolved_text = str(assistant_text if assistant_text is not None else (agent_result.get("text") or result.get("text") or ""))
        resolved_tool_log = tool_log if isinstance(tool_log, list) else (agent_result.get("tool_log") if isinstance(agent_result.get("tool_log"), list) else result.get("tool_log") or [])
        resolved_interaction = interaction if isinstance(interaction, dict) else (agent_result.get("interaction") if isinstance(agent_result.get("interaction"), dict) else result.get("interaction"))
        if isinstance(resolved_interaction, dict):
            agent_runtime.record_interaction(task, turn, resolved_interaction)
        if result.get("stopped"):
            task["status"] = "paused"
            validation = {"complete": False, "reason": "paused_by_user"}
        else:
            validation = agent_runtime.advance_step_if_complete(task, resolved_text, resolved_tool_log, resolved_interaction)
        turn["message"]["text"] = resolved_text
        turn["result"]["created_nodes"] = [
            str((item.get("result") or {}).get("node_id") or "")
            for item in resolved_tool_log
            if isinstance(item, dict) and str((item.get("result") or {}).get("node_id") or "").strip()
        ]
        turn["status"] = "waiting_user" if isinstance(resolved_interaction, dict) else "completed"
        turn["updated_at"] = int(time.time() * 1000)
        _agent_save_tasks()
        _agent_task_log("Workflow", "task={} step={} status={} validation={}".format(
            task.get("task_id"), task.get("current_step_id"), task.get("status"), validation))
        return _agent_attach_runtime_result(result, task, turn, validation)

    if payload_prefers_codex_local(payload):
        try:
            return finish_runtime(submit_codex_chat(payload))
        except Exception as _exc:
            _agent_mark_task_failed(task, turn, _exc)
            raise
    CANVAS_AGENT_CURRENT_SESSION["session_id"] = agent_session_id
    script_board_result = _agent_short_drama_script_board_result(payload)
    if script_board_result:
        return script_board_result
    board_result = _agent_short_drama_board_result(payload)
    if board_result:
        return board_result
    script_param_card = _agent_short_drama_script_param_card_result(payload)
    if script_param_card:
        return script_param_card
    param_card = _agent_short_drama_param_card_result(payload)
    if param_card:
        return param_card
    mode_card = _agent_short_drama_mode_card_result(payload)
    if mode_card:
        return mode_card
    request_id = str(payload.get("request_id") or "").strip()
    if request_id:
        with CANVAS_AGENT_STOP_LOCK:
            CANVAS_AGENT_STOP_REQUESTS.discard(request_id)
    try:
        provider_id, model, upstream_base, key = resolve_chat_target(payload)
    except Exception as _exc:
        _agent_mark_task_failed(task, turn, _exc)
        raise
    messages = normalize_chat_messages(payload)
    messages = _agent_auto_vision_messages(messages, model)
    messages = _agent_sanitize_messages(messages)
    tools = payload.get("tools") or canvas_agent_tools_schema()
    preset = payload.get("generation_preset")
    preset = preset if isinstance(preset, dict) else {}
    if tools:
        messages = _agent_inject_tool_guidance(messages, preset)
    brainstorm = payload.get("brainstorm")
    if isinstance(brainstorm, dict) and brainstorm:
        messages = _agent_append_system(messages, _agent_brainstorm_guidance(brainstorm))
    messages = _agent_append_system(messages, _agent_reply_rules())
    # 默认候选交互：不依赖开关，适合给可选项时自动出候选卡片。
    # 但当命中流程型技能（如叙事短片主链）时跳过，避免候选引导压过技能的阶段推进。
    if not _agent_has_flow_skill(payload):
        messages = _agent_append_system(messages, _agent_candidate_interaction_guidance())
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if _canvas_agent_reasoning_effort["enabled"]:
        body["reasoning_effort"] = CANVAS_AGENT_REASONING_EFFORT
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    tool_log = []
    data = None
    _interaction_retries = 0
    for _turn in range(CANVAS_AGENT_MAX_TOOL_TURNS + 1):
        # 阶段守卫：按任务当前步骤写入 Mutation 阶段。
        # 资产发现/提取/提示词生成三个阶段禁建节点（与步骤 forbidden_tools 同源），其余为空=不激活。
        CANVAS_AGENT_CURRENT_PHASE["phase"] = agent_runtime.step_phase(task)
        if _canvas_agent_stop_requested(request_id):
            append_log(LOG_FILE, "agent chat stopped by user at turn {}".format(_turn + 1))
            task["status"] = "paused"
            return finish_runtime({"text": "", "raw": None, "tool_log": tool_log, "stopped": True}, "", tool_log)
        _t0 = time.time()
        try:
            data = request_chat_json_with_retry(
                f"{upstream_base}/chat/completions",
                body,
                {"Authorization": f"Bearer {key}"},
                attempts=3,
                timeout=300,
            )
        except Exception as _exc:
            append_log(LOG_FILE, "agent chat turn {} failed after {:.0f}s: {}".format(_turn + 1, time.time() - _t0, _exc))
            # 上游/模型不支持 reasoning_effort → 关掉开关并原样重试（保证换模型不会因此报错）
            if _canvas_agent_reasoning_effort["enabled"] and "reasoning_effort" in str(_exc):
                _canvas_agent_reasoning_effort["enabled"] = False
                append_log(LOG_FILE, "agent reasoning_effort not supported upstream, disabled and retrying")
                body.pop("reasoning_effort", None)
                continue
            _agent_mark_task_failed(task, turn, _exc)
            raise
        append_log(LOG_FILE, "agent chat turn {} ok in {:.0f}s model={}".format(_turn + 1, time.time() - _t0, model))
        choices = data.get("choices") or []
        message = (choices[0].get("message") if choices and isinstance(choices[0], dict) else {}) or {}
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            text = message.get("content") or ""
            # —— 交互合规拦截（harness 层确定性检测，非提示词）：该出卡没出卡/谎称发了卡 → 回灌纠正重试 ——
            if not _agent_has_present_interaction(tool_log):
                violation = _agent_detect_interaction_violation(text)
                if violation and _interaction_retries < CANVAS_AGENT_MAX_INTERACTION_RETRIES:
                    append_log(LOG_FILE, "agent interaction violation turn={} type={} retrying".format(_turn + 1, violation))
                    messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": []})
                    messages.append({"role": "user", "content": _agent_interaction_correction_prompt(violation)})
                    _interaction_retries += 1
                    continue
            return finish_runtime({
                "text": text,
                "raw": data,
                "tool_log": tool_log,
                "agent_result": _build_canvas_agent_result(
                    text,
                    tool_log,
                    {"provider": provider_id, "model": model},
                    "openai_compatible",
                    session_id=agent_session_id,
                ),
            }, text, tool_log)
        if _canvas_agent_stop_requested(request_id):
            append_log(LOG_FILE, "agent chat stopped before tool execution turn={}".format(_turn + 1))
            task["status"] = "paused"
            return finish_runtime({"text": "", "raw": data, "tool_log": tool_log, "stopped": True}, "", tool_log)
        # —— 流程纪律拦截：还没到落地环节就建节点 → 拦下工具调用，回灌纠正 ——
        premature = _agent_detect_premature_creation(tool_calls, messages, tool_log)
        if premature and _interaction_retries < CANVAS_AGENT_MAX_INTERACTION_RETRIES:
            append_log(LOG_FILE, "agent premature creation blocked turn={} tools={}".format(_turn + 1, ",".join(
                str((tc.get("function") or {}).get("name") or "") for tc in tool_calls if isinstance(tc, dict))))
            messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
            for tc in tool_calls:
                messages.append({"role": "tool", "tool_call_id": str((tc.get("id") or "")),
                                 "content": "已拦截：流程还没到创建节点环节，用户只要内容产出。请直接在正文输出内容。"})
            messages.append({"role": "user", "content": _agent_premature_creation_correction()})
            _interaction_retries += 1
            body["messages"] = messages
            continue
        messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            args = _agent_merge_payload_refs_into_tool_args(name, args, payload)
            args = agent_runtime.attach_provenance(args, task, turn, str(tc.get("id") or ""))
            CANVAS_AGENT_ROUTE_CONTEXT["user_text"] = _agent_latest_user_text(payload)
            policy = agent_runtime.authorize_tool(task, name, args)
            _agent_task_log("ToolPolicy", "task={} step={} tool={} result={} reason={}".format(
                task.get("task_id"), task.get("current_step_id"), name,
                "allowed" if policy.get("allowed") else "blocked", policy.get("reason")))
            if not policy.get("allowed"):
                result = {
                    "ok": False,
                    "blocked": True,
                    "error": policy.get("message"),
                    "reason": policy.get("reason"),
                    "missing": policy.get("missing") or [],
                }
                tool_log.append({"name": name, "args": args, "result": result, "policy": policy})
                agent_runtime.record_tool_run(task, turn, name, args, result, policy)
                messages.append({"role": "tool", "tool_call_id": str(tc.get("id") or ""),
                                 "content": json.dumps(result, ensure_ascii=False)})
                continue
            _tt0 = time.time()
            result = canvas_agent_execute_tool(name, args, preset, agent_session_id)
            append_log(LOG_FILE, "agent tool {} done in {:.0f}s".format(name, time.time() - _tt0))
            tool_log.append({"name": name, "args": args, "result": result})
            agent_runtime.record_tool_run(task, turn, name, args, result, policy)
            tool_content = json.dumps(result, ensure_ascii=False)
            # 工具结果截断，避免 ModLens 等大输出撑大上下文拖慢后续轮次
            if len(tool_content) > 8000:
                tool_content = tool_content[:8000] + "...(结果已截断)"
            messages.append({"role": "tool", "tool_call_id": str(tc.get("id") or ""),
                             "content": tool_content})
        # —— 批量建违规拦截：用户选"一次性全建"，但本轮逐个建且没调 canvas_batch_operations → 回灌纠正重试 ——
        bviol = _agent_detected_batch_violation(messages, tool_log)
        if bviol and _interaction_retries < CANVAS_AGENT_MAX_INTERACTION_RETRIES:
            append_log(LOG_FILE, "agent batch violation turn={} type={} retrying".format(_turn + 1, bviol))
            messages.append({"role": "user", "content": _agent_batch_correction_prompt(bviol)})
            _interaction_retries += 1
            continue
        body["messages"] = messages
        body["tools"] = tools
    return finish_runtime({
        "text": "工具调用达到轮次上限,任务可能未完成。",
        "raw": data,
        "tool_log": tool_log,
        "agent_result": _build_canvas_agent_result(
            "工具调用达到轮次上限,任务可能未完成。",
            tool_log,
            {"provider": provider_id, "model": model},
            "openai_compatible",
            session_id=agent_session_id,
        ),
    }, "工具调用达到轮次上限,任务可能未完成。", tool_log)


def upload_reference(ref):
    url = ref.get("url") if isinstance(ref, dict) else str(ref or "")
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    uploaded = runninghub_upload_binary_media(url)
    return uploaded.get("downloadUrl") or ""


def normalize_model(model, refs):
    model = str(model or "").strip().replace("rhart-image-g-2-offcial", "rhart-image-g-2-official")
    if not refs and model.endswith("/image-to-image"):
        return model.replace("/image-to-image", "/text-to-image")
    if refs and model.endswith("/text-to-image"):
        image_model = model.replace("/text-to-image", "/image-to-image")
        if image_model.startswith("rhart-image-g-2-official/"):
            return image_model
    return model


def parse_size_dimensions(value):
    match = re.match(r"^\s*(\d+)\s*[xX*]\s*(\d+)\s*$", str(value or ""))
    if not match:
        return None
    width = int(match.group(1))
    height = int(match.group(2))
    if width <= 0 or height <= 0:
        return None
    return width, height


def derive_resolution_from_size(value):
    dims = parse_size_dimensions(value)
    if not dims:
        return ""
    width, height = dims
    longest = max(width, height)
    if longest <= 1024:
        return "1k"
    if longest <= 2048:
        return "2k"
    return "4k"


def derive_aspect_ratio_from_size(value):
    dims = parse_size_dimensions(value)
    if not dims:
        return ""
    width, height = dims
    divisor = math.gcd(width, height) or 1
    return f"{width // divisor}:{height // divisor}"


RH_ALLOWED_ASPECT_RATIOS = ("1:1","3:2","2:3","5:4","4:5","16:9","9:16","21:9","3:4","4:3","9:21","1:2","2:1","1:3","3:1")
RH_ASPECT_KEY_ALIASES = {
    "square":"1:1","landscape":"3:2","portrait":"2:3","landscape43":"4:3",
    "portrait43":"3:4","wide":"16:9","story":"9:16","ultrawide":"21:9","ultratall":"9:21",
}
def _normalize_rh_aspect_ratio(value, size=None):
    """出口防御：把比例 key(wide/square…)或畸形写法规范成 RunningHub 合法文本，绝不把 'wide' 原样发出去。"""
    text = str(value or "").strip()
    key = text.lower().replace(" ", "").replace("：", ":")
    if key in RH_ASPECT_KEY_ALIASES:
        return RH_ASPECT_KEY_ALIASES[key]
    cand = key.replace("x", ":").replace("/", ":")
    if ":" in cand and cand.replace(":", "").isdigit() and cand in RH_ALLOWED_ASPECT_RATIOS:
        return cand
    if text in RH_ALLOWED_ASPECT_RATIOS:
        return text
    derived = derive_aspect_ratio_from_size(size) if size else ""
    return derived if derived in RH_ALLOWED_ASPECT_RATIOS else "16:9"


def build_official_body(payload, model, refs):
    resolution = str(payload.get("resolution") or "").strip().lower()
    if resolution not in RUNNINGHUB_ALLOWED_RESOLUTIONS:
        size_value = str(payload.get("size") or "").strip()
        size_lower = size_value.lower()
        resolution = size_lower if size_lower in RUNNINGHUB_ALLOWED_RESOLUTIONS else derive_resolution_from_size(size_value) or "1k"
    aspect_ratio = str(payload.get("aspectRatio") or "").strip() or derive_aspect_ratio_from_size(payload.get("size")) or "16:9"
    aspect_ratio = _normalize_rh_aspect_ratio(aspect_ratio, payload.get("size"))
    body = {
        "prompt": payload.get("prompt") or "",
        "resolution": resolution,
        "aspectRatio": aspect_ratio,
    }
    if model.startswith("rhart-image-g-2-official/"):
        body["quality"] = payload.get("quality") or "medium"
    if refs:
        body["imageUrls"] = [upload_reference(ref) for ref in refs]
    return body


def runninghub_provider_models(providers=None):
    items = providers if isinstance(providers, list) else read_api_providers()
    models = []
    for provider in items or []:
        if not isinstance(provider, dict):
            continue
        protocol = str(provider.get("protocol") or "").strip().lower()
        provider_id = str(provider.get("id") or "").strip().lower()
        base_url = str(provider.get("base_url") or "").strip().lower()
        if protocol == "runninghub" or provider_id == "runninghub" or "runninghub" in base_url or provider_id == "custom-api-3":
            models.extend(item for item in (provider.get("image_models") or []) if isinstance(item, str))
    return unique_strings(models or RUNNINGHUB_DEFAULT_IMAGE_MODELS)


def runninghub_preferred_image_model(reference_images=None, providers=None):
    refs = reference_images or []
    models = runninghub_provider_models(providers)
    preferred_suffixes = ["/image-to-image", "/edit"] if refs else ["/text-to-image"]
    for suffix in preferred_suffixes:
        for model in models:
            if str(model).endswith(suffix):
                return normalize_model(model, refs)
    for model in models:
        normalized = normalize_model(model, refs)
        if refs and normalized.endswith("/image-to-image"):
            return normalized
        if not refs and normalized.endswith("/text-to-image"):
            return normalized
    raise RuntimeError("未找到可用的 RunningHub 生图模型：请在 API 设置中配置 image_models")


def legacy_generate_reference_images(payload):
    refs = []
    for ref in (payload.get("reference_images") or []):
        text = str(ref.get("url") if isinstance(ref, dict) else ref or "").strip()
        if text and text not in refs:
            refs.append(text)
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    for value in params.values():
        if not isinstance(value, dict):
            continue
        text = str(value.get("image") or value.get("url") or "").strip()
        if text and text not in refs:
            refs.append(text)
    return refs


def resolve_legacy_generate_payload(payload, providers=None):
    refs = legacy_generate_reference_images(payload or {})
    width = parse_positive_int((payload or {}).get("width")) or 1024
    height = parse_positive_int((payload or {}).get("height")) or 1024
    resolved = {
        "prompt": str((payload or {}).get("prompt") or ""),
        "model": runninghub_preferred_image_model(refs, providers),
        "reference_images": refs,
        "size": str((payload or {}).get("size") or f"{width}x{height}"),
    }
    for key in ("resolution", "aspectRatio", "quality"):
        value = str((payload or {}).get(key) or "").strip()
        if value:
            resolved[key] = value
    return resolved


def runninghub_task_key():
    key = read_env_key()
    if not key:
        raise RuntimeError("未找到 RunningHub API Key，请检查 API/.env")
    return key


def runninghub_task_auth_headers():
    return {"Authorization": f"Bearer {runninghub_task_key()}"}


def guess_upload_filename(source_url, content_type="application/octet-stream", fallback_prefix="upload"):
    path = urllib.parse.urlparse(str(source_url or "")).path or ""
    name = os.path.basename(path)
    if name:
        return name
    ext = mimetypes.guess_extension(content_type or "application/octet-stream") or ".bin"
    return f"{fallback_prefix}-{uuid.uuid4().hex[:8]}{ext}"


def local_media_source_bytes(source_url):
    text = str(source_url or "").strip()
    if not text:
        raise RuntimeError("缺少素材地址")
    if text.startswith("data:"):
        header, sep, encoded = text.partition(",")
        if not sep:
            raise RuntimeError("data URL 格式错误")
        content_type = header[5:].split(";", 1)[0].strip() or "application/octet-stream"
        if ";base64" in header.lower():
            raw = base64.b64decode(encoded)
        else:
            raw = urllib.parse.unquote_to_bytes(encoded)
        return raw, f"data-{uuid.uuid4().hex[:8]}{generated_asset_extension('', content_type, '.bin')}", content_type
    if text.startswith("/assets/"):
        target = resolve_user_asset_path(text)
        return target.read_bytes(), target.name, mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    if text.startswith("/static/"):
        relative = urllib.parse.urlparse(text).path[len("/static/"):]
        target = (ROOT / "static" / urllib.parse.unquote(relative)).resolve()
        return target.read_bytes(), target.name, mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    if text.startswith("/output/"):
        relative = urllib.parse.urlparse(text).path[len("/output/"):]
        target = (USER_DATA_DIR / "output" / urllib.parse.unquote(relative)).resolve()
        return target.read_bytes(), target.name, mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    if text.startswith("file://"):
        parsed = urllib.parse.urlparse(text)
        target = Path(urllib.request.url2pathname(parsed.path))
        return target.read_bytes(), target.name, mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    if re.match(r"^[A-Za-z]:\\", text) and Path(text).exists():
        target = Path(text)
        return target.read_bytes(), target.name, mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    request = urllib.request.Request(
        text,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        raw = response.read()
        content_type = response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0].strip()
    return raw, guess_upload_filename(text, content_type), content_type


def asset_output_dir():
    return ASSETS_DIR / "output"


def asset_output_media_dir(kind="image", canvas_folder=""):
    subdir = output_asset_subdir_for_kind(kind)
    root = asset_output_dir() / str(canvas_folder) if canvas_folder else asset_output_dir()
    result = root / subdir if subdir else root
    result.mkdir(parents=True, exist_ok=True)
    return result


def asset_output_history_dir(kind="image", canvas_folder=""):
    if str(kind or "").strip().lower() == "image":
        return asset_output_media_dir("image", canvas_folder) / "history"
    return (asset_output_dir() / str(canvas_folder) if canvas_folder else asset_output_dir()) / "history"


def asset_output_url(local_name, kind="image", history=False, canvas_folder=""):
    quoted = urllib.parse.quote(str(local_name or ""))
    subdir = output_asset_subdir_for_kind(kind)
    prefix = f"/assets/output/{urllib.parse.quote(str(canvas_folder), safe='')}" if canvas_folder else "/assets/output"
    if history and str(kind or "").strip().lower() == "image":
        return f"{prefix}/images/history/{quoted}"
    if subdir:
        return f"{prefix}/{subdir}/{quoted}"
    return f"{prefix}/{quoted}"


def output_lookup_dirs():
    root = asset_output_dir()
    return (
        root / "images",
        root / "videos",
        root / "images" / "history",
        root / "history",
        root,
    )


def resolve_open_folder_target(url, name="", local_path=""):
    """Resolve canvas image URL/name to a local output file for Explorer /select."""
    text = str(url or "").strip()
    parsed_path = urllib.parse.urlparse(text).path if text else ""
    asset_root = ASSETS_DIR.resolve()

    local_text = str(local_path or "").strip()
    if local_text:
        try:
            if local_text.lower().startswith("file:"):
                parsed_local = urllib.parse.urlparse(local_text)
                local_target = Path(urllib.request.url2pathname(parsed_local.path)).resolve()
            else:
                local_target = Path(local_text).resolve()
            local_target.relative_to(asset_root)
            return local_target
        except Exception:
            pass

    if parsed_path.startswith("/assets/"):
        try:
            return resolve_user_asset_path(text)
        except ApiError:
            pass

    if parsed_path.startswith("/assets/output/"):
        rel = urllib.parse.unquote(parsed_path[len("/assets/output/"):])
        target = (asset_output_dir() / rel).resolve()
        try:
            target.relative_to(asset_root)
        except Exception:
            return asset_output_dir()
        if target.exists():
            return target
        return target

    clean_name = Path(str(name or "").split("?", 1)[0].split("#", 1)[0]).name
    if clean_name:
        for folder in output_lookup_dirs():
            target = (folder / clean_name).resolve()
            try:
                target.relative_to(asset_root)
            except Exception:
                continue
            if target.exists():
                return target
        return (asset_output_dir() / clean_name).resolve()

    return asset_output_dir()


def asset_input_dir():
    return ASSETS_DIR / "input"


def generated_asset_extension(file_name="", content_type="", default_ext=".png"):
    for source in (str(file_name or ""), str(content_type or "")):
        if "." in source:
            match = re.search(r"(\.[A-Za-z0-9]{2,8})(?:$|\?)", source)
            if match:
                return match.group(1).lower()
    guessed = mimetypes.guess_extension(str(content_type or "").split(";", 1)[0].strip() or "")
    return (guessed or default_ext or ".png").lower()


def extract_multipart_boundary(content_type=""):
    match = re.search(r'boundary="?([^";]+)"?', str(content_type or ""), re.IGNORECASE)
    return match.group(1) if match else ""


def parse_multipart_files(raw_body, content_type):
    boundary = extract_multipart_boundary(content_type)
    if not boundary:
        raise RuntimeError("上传请求缺少 multipart boundary")
    marker = ("--" + boundary).encode("utf-8")
    files = []
    for part in raw_body.split(marker):
        part = part.strip()
        if not part or part == b"--":
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"--"):
            part = part[:-2]
        header_blob, separator, data = part.partition(b"\r\n\r\n")
        if not separator:
            continue
        header_lines = header_blob.decode("utf-8", "replace").split("\r\n")
        headers = {}
        for line in header_lines:
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
        disposition = headers.get("content-disposition", "")
        filename_match = re.search(r'filename="([^"]*)"', disposition)
        field_match = re.search(r'name="([^"]*)"', disposition)
        if not filename_match:
            continue
        file_name = filename_match.group(1).strip() or f"upload-{uuid.uuid4().hex[:8]}"
        field_name = field_match.group(1).strip() if field_match else "files"
        if data.endswith(b"\r\n"):
            data = data[:-2]
        files.append(
            {
                "field_name": field_name,
                "file_name": file_name,
                "content_type": headers.get("content-type", "application/octet-stream"),
                "data": data,
            }
        )
    return files


def upload_kind_for_file(file_name="", content_type=""):
    mime = str(content_type or "").split(";", 1)[0].strip().lower()
    ext = str(Path(str(file_name or "")).suffix or "").lower()
    if mime.startswith("image/") or ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        return "image"
    if mime.startswith("video/") or ext in {".mp4", ".mov", ".avi", ".webm", ".mkv"}:
        return "video"
    if mime.startswith("audio/") or ext in {".mp3", ".wav", ".ogg", ".m4a", ".flac"}:
        return "audio"
    return "file"


def save_uploaded_input_file(file_info):
    original_name = str(file_info.get("file_name") or "").strip() or f"upload-{uuid.uuid4().hex[:8]}"
    content_type = str(file_info.get("content_type") or "application/octet-stream")
    data = file_info.get("data") or b""
    ext = generated_asset_extension(original_name, content_type, ".bin")
    saved_name = f"ai_ref_{uuid.uuid4().hex[:12]}{ext}"
    target = asset_input_dir() / saved_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    kind = upload_kind_for_file(original_name, content_type)
    return {
        "url": f"/assets/input/{urllib.parse.quote(saved_name)}",
        "name": original_name,
        "filename": saved_name,
        "kind": kind,
        "content_type": content_type,
    }


def handle_ai_upload(raw_body, content_type):
    files = parse_multipart_files(raw_body, content_type)
    if not files:
        raise RuntimeError("上传请求里没有文件")
    return {"ok": True, "files": [save_uploaded_input_file(file_info) for file_info in files]}


def handle_comfy_upload(raw_body, content_type):
    """Forward canvas image uploads to the configured local ComfyUI instance."""
    files = parse_multipart_files(raw_body, content_type)
    if not files:
        raise ApiError(400, "上传请求里没有文件")
    base = comfy_instance_base()
    uploaded = []
    for file_info in files:
        result = request_multipart_json(
            base + "/upload/image",
            fields={"type": "input", "overwrite": "false"},
            files=[
                {
                    "name": "image",
                    "filename": file_info.get("file_name") or "upload.png",
                    "content_type": file_info.get("content_type") or "application/octet-stream",
                    "data": file_info.get("data") or b"",
                }
            ],
            timeout=120,
        )
        if not isinstance(result, dict):
            raise ApiError(502, "ComfyUI 上传接口返回格式异常")
        name = str(result.get("name") or "").strip()
        subfolder = str(result.get("subfolder") or "").strip().strip("/")
        if not name:
            raise ApiError(502, "ComfyUI 未返回上传文件名")
        comfy_name = "/".join(part for part in (subfolder, name) if part)
        uploaded.append({**result, "comfy_name": comfy_name})
    return {"files": uploaded}


def canvas_output_folder_name(canvas_title="", canvas_id=""):
    raw = str(canvas_title or "").strip()
    if not raw:
        raw = f"canvas_{str(canvas_id or '').strip()[:12]}"
    safe = re.sub(r'[\\/:*?"<>|]', '_', raw).strip().strip('.')[:80]
    return safe or f"canvas_{str(canvas_id or '').strip()[:12] or 'default'}"


_RECENT_REMOTE_SAVES = {}
_RECENT_REMOTE_SAVES_LOCK = threading.Lock()
# 任务级本地化锁：防止 run_task 后台线程与 refresh_canvas_task_state（前端轮询触发）
# 同时对同一任务的远程结果做本地落盘（竞态导致同一张图落两份，文件序号各+1）。
_CANVAS_TASK_LOCALIZE_LOCKS = {}
_CANVAS_TASK_LOCALIZE_LOCKS_LOCK = threading.Lock()


def _canvas_task_localize_lock(task_id):
    with _CANVAS_TASK_LOCALIZE_LOCKS_LOCK:
        lock = _CANVAS_TASK_LOCALIZE_LOCKS.get(task_id)
        if lock is None:
            lock = threading.Lock()
            _CANVAS_TASK_LOCALIZE_LOCKS[task_id] = lock
        return lock


def _canvas_task_already_localized(task_id):
    state = get_task_state(task_id)
    return bool(state and state.get("status") == "succeeded" and state.get("localized_at"))


def save_generated_remote_asset(source_url, kind="image", display_name="", canvas_title="", canvas_id="", node_title=""):
    if not display_name:
        display_name = str(node_title or "").strip()
    dedup_key = str(source_url or "").strip()
    if dedup_key and not dedup_key.startswith(("/assets/", "/static/", "/output/", "file://", "data:")):
        with _RECENT_REMOTE_SAVES_LOCK:
            cached = _RECENT_REMOTE_SAVES.get(dedup_key)
            if cached and (time.time() - cached.get("_time", 0)) < 600:
                return {k: v for k, v in cached.items() if k != "_time"}
    raw, file_name, content_type = local_media_source_bytes(source_url)
    media_kind = str(kind or "image").strip().lower() or "image"
    ext = generated_asset_extension(file_name, content_type, ".mp4" if media_kind == "video" else ".mp3" if media_kind == "audio" else ".png")
    canvas_folder = canvas_output_folder_name(canvas_title, canvas_id) if canvas_title or canvas_id else ""
    output_dir = asset_output_media_dir(media_kind, canvas_folder)
    # 保持画布原有的日期序号命名；扩展名只保留一份。
    if display_name:
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', str(display_name).strip())[:80]
        safe_name = re.sub(r'\.(?:png|jpe?g|webp|gif|bmp|mp4|webm|mov|m4a|mp3|wav|aac|ogg|flac)(?:_\d+)?$', '', safe_name, flags=re.IGNORECASE)
        safe_name = safe_name.strip().strip('.') or f"{time.strftime('%m-%d')}-01"
        local_name = f"{safe_name}{ext}"
        # 防重名：追加数字
        target = output_dir / local_name
        counter = 1
        while target.exists():
            date_match = re.match(r'^(\d{2}-\d{2})-(\d{2})$', safe_name)
            next_name = f"{date_match.group(1)}-{counter + 1:02d}" if date_match else f"{safe_name}_{counter}"
            local_name = f"{next_name}{ext}"
            target = output_dir / local_name
            counter += 1
    else:
        date_prefix = time.strftime('%m-%d')
        counter = 1
        local_name = f"{date_prefix}-{counter:02d}{ext}"
        target = output_dir / local_name
        while target.exists():
            counter += 1
            local_name = f"{date_prefix}-{counter:02d}{ext}"
            target = output_dir / local_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    result = {
        "url": asset_output_url(local_name, media_kind, canvas_folder=canvas_folder),
        "name": local_name,
        "kind": media_kind,
        "source_url": str(source_url or ""),
        "local_path": str(target),
    }
    if dedup_key and not dedup_key.startswith(("/assets/", "/static/", "/output/", "file://", "data:")):
        with _RECENT_REMOTE_SAVES_LOCK:
            _RECENT_REMOTE_SAVES[dedup_key] = {**result, "_time": time.time()}
    return result


def fallback_generated_media_item(source, kind="image", error=""):
    if not isinstance(source, dict):
        source = {"url": source}
    url = str(source.get("url") or source.get("path") or source.get("src") or source.get("uri") or "").strip()
    media_kind = str(source.get("kind") or source.get("mediaKind") or kind or "image").strip().lower() or "image"
    parsed_name = os.path.basename(urllib.parse.urlparse(url).path)
    name = str(source.get("name") or source.get("display_name") or parsed_name or f"output_{uuid.uuid4().hex[:8]}").strip()
    fallback = dict(source)
    fallback.update({
        "url": url,
        "name": name,
        "kind": media_kind,
        "source_url": str(source.get("source_url") or source.get("sourceUrl") or url),
        "remote_fallback": True,
    })
    if error:
        fallback["localize_error"] = str(error)
    return fallback


def unique_output_target(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    # 与 save_generated_remote_asset 同规则：只滤文件系统非法字符，保留中文（历史节点名多为中文）
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", Path(str(name or "")).name).strip().strip(".") or f"output_{uuid.uuid4().hex[:8]}"
    target = folder / safe_name
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    for index in range(1, 10000):
        candidate = folder / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    return folder / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"


def canvas_output_folder_from_url(url):
    parsed_path = urllib.parse.urlparse(str(url or "")).path or ""
    prefix = "/assets/output/"
    if not parsed_path.startswith(prefix):
        return ""
    parts = [urllib.parse.unquote(part) for part in parsed_path[len(prefix):].split("/") if part]
    if not parts or parts[0] in {"images", "videos", "history"}:
        return ""
    return canvas_output_folder_name(parts[0], "")


def move_output_asset_to_history(payload):
    url = str((payload or {}).get("url") or "").strip()
    if not url.startswith("/assets/output/"):
        raise ApiError(400, "不是输出素材路径")
    source = resolve_user_asset_path(url)
    if output_asset_kind_for_name(source.name) != "image":
        return {"ok": True, "moved": url, "url": url, "skipped": True}
    parsed_path = urllib.parse.unquote(urllib.parse.urlparse(url).path or "")
    # 任意层级的 history 目录都算已归档（画布同名子目录的 history 也在其中），防止 history/history 套娃
    if "/history/" in parsed_path:
        return {"ok": True, "moved": url, "url": url, "skipped": True}
    asset_root = ASSETS_DIR.resolve()
    canvas_folder = canvas_output_folder_from_url(url)
    target = unique_output_target(asset_output_history_dir("image", canvas_folder), source.name).resolve()
    try:
        target.relative_to(asset_root)
    except Exception as exc:
        raise ApiError(403, "forbidden") from exc
    if source.resolve() != target:
        shutil.move(str(source), str(target))
    moved_url = asset_output_url(target.name, "image", history=True, canvas_folder=canvas_folder)
    return {"ok": True, "moved": moved_url, "url": moved_url, "path": str(target)}


def localize_generated_media_items(items, kind="image", canvas_title="", canvas_id="", node_title=""):
    localized = []
    seen_urls = set()
    for item in items or []:
        source = item if isinstance(item, dict) else {"url": item}
        url = str(source.get("url") or source.get("path") or source.get("src") or source.get("uri") or "").strip()
        if not url:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        if url.startswith("/assets/output/"):
            localized.append({
                "url": url,
                "name": str(source.get("name") or os.path.basename(urllib.parse.urlparse(url).path) or ""),
                "kind": str(source.get("kind") or source.get("mediaKind") or kind or "image"),
            })
            continue
        try:
            saved = save_generated_remote_asset(
                url,
                str(source.get("kind") or source.get("mediaKind") or kind or "image"),
                str(source.get("display_name") or source.get("name") or ""),
                canvas_title,
                canvas_id,
                node_title=node_title,
            )
        except Exception as exc:
            append_log(LOG_FILE, f"generated media localize fallback url={url[:180]} error={exc}")
            localized.append(fallback_generated_media_item(source, kind, exc))
            continue
        if source.get("name"):
            saved["display_name"] = str(source.get("name"))
        localized.append(saved)
    return localized


def runninghub_api_base():
    """RH 平台地址跟随用户在 API 设置里的配置（2026-09-10 解锁）；缺省回退官方域名。"""
    base = "https://www.runninghub.ai"
    try:
        for item in read_api_providers():
            if not isinstance(item, dict):
                continue
            if str(item.get("id") or "").strip() != "runninghub":
                continue
            raw = str(item.get("base_url") or "").strip()
            if not raw:
                break
            if "://" not in raw:
                raw = "https://" + raw
            base = raw.rstrip("/")
            # 用户常把完整接口地址（…/openapi/v2）填进设置里；提交链会再拼一次
            # /openapi/v2/<model>，出现双路径 → RH 返回 1001 Invalid URL。归一化到站点根。
            if base.endswith("/openapi/v2"):
                base = base[: -len("/openapi/v2")]
            break
    except Exception:
        pass
    return base


def runninghub_api_url(path):
    return runninghub_api_base() + path


def runninghub_upload_binary_media(source_url):
    raw, file_name, content_type = local_media_source_bytes(source_url)
    data = request_multipart_json(
        runninghub_api_url("/openapi/v2/media/upload/binary"),
        files=[{"name": "file", "filename": file_name, "content_type": content_type, "data": raw}],
        headers=runninghub_task_auth_headers(),
        timeout=180,
    )
    info = data.get("data") if isinstance(data.get("data"), dict) else data
    public_url = (
        info.get("downloadUrl")
        or info.get("download_url")
        or info.get("url")
        or info.get("viewUrl")
        or ""
    )
    resolved_name = info.get("fileName") or info.get("filename") or file_name
    if not public_url and resolved_name:
        public_url = f"{runninghub_api_base()}/view?filename={urllib.parse.quote(resolved_name)}&type=input&subfolder="
    if not public_url:
        raise RuntimeError(f"RunningHub 二进制上传失败：{data}")
    return {"fileName": resolved_name, "downloadUrl": public_url, "raw": data}


def runninghub_upload_task_asset(source_url):
    raw, file_name, content_type = local_media_source_bytes(source_url)
    data = request_multipart_json(
        runninghub_api_url("/task/openapi/upload"),
        fields={"fileType": "input"},
        files=[{"name": "file", "filename": file_name, "content_type": content_type, "data": raw}],
        headers=runninghub_task_auth_headers(),
        timeout=180,
    )
    info = data.get("data") if isinstance(data.get("data"), dict) else data
    resolved_name = info.get("fileName") or info.get("filename") or info.get("name") or ""
    if not resolved_name:
        raise RuntimeError(f"RunningHub 素材上传失败：{data}")
    public_url = (
        info.get("downloadUrl")
        or info.get("fileUrl")
        or info.get("url")
        or ""
    )
    if not public_url:
        public_url = f"{runninghub_api_base()}/view?filename={urllib.parse.quote(resolved_name)}&type=input&subfolder="
    return {"fileName": resolved_name, "downloadUrl": public_url, "url": public_url, "raw": data}


def volcengine_ark_api_key():
    env = read_env_values()
    for name in ("ARK_API_KEY", "VOLCENGINE_ARK_API_KEY", "API_PROVIDER_VOLCENGINE_KEY"):
        value = str(env.get(name) or os.environ.get(name) or "").strip()
        if value:
            return value
    raise ApiError(400, "缺少火山方舟 API Key")


def volcengine_upload_asset(source_url):
    raw, file_name, content_type = local_media_source_bytes(source_url)
    key = volcengine_ark_api_key()
    data = request_multipart_json(
        "https://ark.cn-beijing.volces.com/api/v3/files",
        fields={"purpose": "user_data"},
        files=[{"name": "file", "filename": file_name, "content_type": content_type, "data": raw}],
        headers={"Authorization": f"Bearer {key}"},
        timeout=180,
    )
    file_id = str(data.get("id") or data.get("file_id") or "").strip()
    file_url = str(data.get("url") or data.get("downloadUrl") or data.get("fileUrl") or "").strip()
    if not file_url and file_id:
        file_url = file_id
    if not file_url:
        raise RuntimeError(f"火山方舟文件上传未返回可用地址：{data}")
    return {"fileName": file_name, "fileId": file_id, "url": file_url, "downloadUrl": file_url, "raw": data}


def upload_cloud_media_bytes_to_litterbox(raw, file_name="upload.bin", content_type="application/octet-stream"):
    safe_name = str(file_name or "upload.bin").strip() or "upload.bin"
    mime = str(content_type or "application/octet-stream").strip() or "application/octet-stream"
    upload_url = os.environ.get("LITTERBOX_UPLOAD_URL", "https://litterbox.catbox.moe/resources/internals/api.php").strip() or "https://litterbox.catbox.moe/resources/internals/api.php"
    time_value = os.environ.get("LITTERBOX_TIME", "72h").strip() or "72h"
    text = request_multipart_text(
        upload_url,
        fields={"reqtype": "fileupload", "time": time_value},
        files=[{"name": "fileToUpload", "filename": safe_name, "content_type": mime, "data": raw or b""}],
        timeout=600,
    )
    url = text.strip().splitlines()[0].strip()
    if not re.match(r"^https?://", url, re.I):
        raise RuntimeError(f"Litterbox 返回了无法识别的链接：{text[:200]}")
    return url


def upload_cloud_media_bytes_to_temp_sh(raw, file_name="upload.bin", content_type="application/octet-stream"):
    safe_name = str(file_name or "upload.bin").strip() or "upload.bin"
    mime = str(content_type or "application/octet-stream").strip() or "application/octet-stream"
    upload_url = os.environ.get("TEMP_SH_UPLOAD_URL", "https://temp.sh/upload").strip() or "https://temp.sh/upload"
    text = request_multipart_text(
        upload_url,
        files=[{"name": "file", "filename": safe_name, "content_type": mime, "data": raw or b""}],
        timeout=600,
    )
    url = ""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            payload = data.get("data") if isinstance(data.get("data"), dict) else data
            url = str(payload.get("url") or payload.get("downloadUrl") or payload.get("fileUrl") or "").strip()
    except Exception:
        url = text.strip()
    if not re.match(r"^https?://", url, re.I):
        raise RuntimeError(f"Temp.sh 返回了无法识别的链接：{text[:200]}")
    return url


def cloud_media_url_downloadable(url, timeout=15):
    text = str(url or "").strip()
    if not re.match(r"^https?://", text, re.I):
        return False
    try:
        req = urllib.request.Request(
            text,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            chunk = resp.read(16)
            return 200 <= status < 400 and bool(chunk)
    except Exception as exc:
        append_log(LOG_FILE, f"cloud media url check failed url={text[:120]}: {exc}")
        return False


def upload_cloud_media_bytes(raw, file_name="upload.bin", content_type="application/octet-stream", service="auto"):
    selected = str(service or os.environ.get("CLOUD_VIDEO_UPLOAD_SERVICE", "auto") or "auto").strip().lower()
    choices = []
    if selected in {"litterbox", "catbox"}:
        choices = [("litterbox", upload_cloud_media_bytes_to_litterbox)]
    elif selected in {"temp", "temp.sh", "tempsh"}:
        choices = [("temp.sh", upload_cloud_media_bytes_to_temp_sh)]
    elif selected in {"volcengine", "volcengine-video", "video-reference"}:
        choices = [
            ("litterbox", upload_cloud_media_bytes_to_litterbox),
            ("temp.sh", upload_cloud_media_bytes_to_temp_sh),
        ]
    else:
        choices = [
            ("temp.sh", upload_cloud_media_bytes_to_temp_sh),
            ("litterbox", upload_cloud_media_bytes_to_litterbox),
        ]
    errors = []
    for name, func in choices:
        try:
            url = func(raw, file_name, content_type)
            if not cloud_media_url_downloadable(url):
                raise RuntimeError(f"上传后链接不可下载：{url[:120]}")
            append_log(LOG_FILE, f"cloud media uploaded service={name} name={str(file_name or '')[:80]} url={url[:120]}")
            return url
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            append_log(LOG_FILE, f"cloud media upload failed service={name} name={str(file_name or '')[:80]}: {exc}")
    raise RuntimeError("云端上传失败：" + "；".join(errors))


def upload_cloud_media_direct(source_url, service="auto"):
    raw, file_name, content_type = local_media_source_bytes(source_url)
    url = upload_cloud_media_bytes(raw, file_name, content_type, service=service)
    return {
        "ok": True,
        "url": url,
        "downloadUrl": url,
        "fileUrl": url,
        "name": file_name,
        "kind": upload_kind_for_file(file_name, content_type),
        "content_type": content_type,
        "expires": "3 days",
        "service": service,
    }


def volcengine_provider_config(provider_id="volcengine"):
    selected = str(provider_id or "volcengine").strip()
    for provider in read_api_providers():
        if not isinstance(provider, dict):
            continue
        provider_id_value = str(provider.get("id") or "").strip()
        provider_protocol = str(provider.get("protocol") or "").strip().lower()
        if provider_id_value == selected or (selected == "volcengine" and provider_protocol == "volcengine"):
            return provider
    if selected == "volcengine":
        return {"id": "volcengine", "protocol": "volcengine", "base_url": "https://ark.cn-beijing.volces.com/api/v3"}
    return {}


def is_volcengine_canvas_video_payload(payload):
    provider_id = str((payload or {}).get("provider_id") or "").strip()
    if provider_id == "volcengine":
        return True
    provider = volcengine_provider_config(provider_id)
    return str(provider.get("protocol") or "").strip().lower() == "volcengine"


def volcengine_normalize_resolution(value):
    text = str(value or "").strip().lower()
    aliases = {
        "": "",
        "480": "480p",
        "480p": "480p",
        "720": "720p",
        "720p": "720p",
        "1080": "1080p",
        "1080p": "1080p",
        "1k": "720p",
        "2k": "1080p",
        "4k": "4k",
    }
    return aliases.get(text, text)


def volcengine_normalize_ratio(value):
    text = str(value or "").strip().lower()
    if text in {"wide", "landscape"}:
        return "16:9"
    if text in {"portrait", "vertical"}:
        return "9:16"
    if text in {"square"}:
        return "1:1"
    return text or "adaptive"


def volcengine_video_media_url(source_url):
    text = str(source_url or "").strip()
    if not text:
        return ""
    if text.startswith("asset://"):
        return text
    public_url = volcengine_public_media_url(text)
    if public_url and not volcengine_video_url_needs_reupload(public_url):
        return public_url
    upload_service = os.environ.get("VOLCENGINE_VIDEO_UPLOAD_SERVICE", "volcengine-video").strip() or "volcengine-video"
    uploaded = upload_cloud_media_direct(text, service=upload_service)
    return str(uploaded.get("url") or "").strip()


def volcengine_image_media_url(source_url, max_bytes=12 * 1024 * 1024):
    text = str(source_url or "").strip()
    if not text:
        return ""
    if text.lower().startswith("data:image/"):
        return text
    if text.startswith("asset://"):
        return text
    public_url = volcengine_public_media_url(text)
    if public_url:
        return public_url
    raw, file_name, content_type = local_media_source_bytes(text)
    mime = str(content_type or mimetypes.guess_type(file_name)[0] or "").strip().lower()
    if not mime.startswith("image/"):
        return ""
    if len(raw) > int(max_bytes):
        raise ApiError(400, f"参考图片过大：{file_name}，请压缩到 12MB 以内。")
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def volcengine_public_media_url(source_url):
    text = str(source_url or "").strip()
    if text.startswith("asset://"):
        return text
    if not re.match(r"^https?://", text, re.I):
        return ""
    parsed = urllib.parse.urlparse(text)
    host = str(parsed.hostname or "").strip().lower()
    if host in {"127.0.0.1", "localhost", "::1"} or host.startswith("192.168.") or host.startswith("10."):
        return ""
    if re.match(r"^172\.(1[6-9]|2[0-9]|3[0-1])\.", host):
        return ""
    return text


def looks_like_video_media_url(source_url):
    text = str(source_url or "").strip().lower()
    if not text:
        return False
    path = urllib.parse.urlparse(text).path or text
    return bool(re.search(r"\.(mp4|mov|m4v|webm|mkv|avi|mpeg|mpg)(?:$|[?#])", path, re.I))


def volcengine_video_url_needs_reupload(source_url):
    try:
        host = str(urllib.parse.urlparse(str(source_url or "")).hostname or "").strip().lower()
    except Exception:
        host = ""
    return host in {"temp.sh", "www.temp.sh"}


def video_reference_to_frame_data_urls(source_url, max_frames=4, max_size=768):
    text = str(source_url or "").strip()
    if not text:
        return []
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        append_log(LOG_FILE, "volcengine video reference frame extraction skipped: ffmpeg not found")
        return []
    work_dir = tempfile.mkdtemp(prefix="myridtv_video_frames_")
    input_path = ""
    try:
        raw, file_name, content_type = local_media_source_bytes(text)
        ext = generated_asset_extension(file_name, content_type, ".mp4")
        input_path = str(Path(work_dir) / f"input{ext}")
        Path(input_path).write_bytes(raw)
        frame_pattern = str(Path(work_dir) / "frame_%02d.jpg")
        vf = f"fps=1,scale={int(max_size)}:-2"
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            input_path,
            "-vf",
            vf,
            "-frames:v",
            str(max(1, int(max_frames))),
            "-q:v",
            "4",
            frame_pattern,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if proc.returncode != 0:
            append_log(LOG_FILE, f"volcengine video frame extraction failed: {proc.stderr[:500]}")
            return []
        frames = sorted(Path(work_dir).glob("frame_*.jpg"))[:max_frames]
        result = []
        for index, frame in enumerate(frames, start=1):
            encoded = base64.b64encode(frame.read_bytes()).decode("ascii")
            result.append(f"data:image/jpeg;base64,{encoded}")
        return result
    except Exception as exc:
        append_log(LOG_FILE, f"volcengine video frame extraction failed url={text[:120]}: {exc}")
        return []
    finally:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass


def volcengine_video_reference_content_items(source_url, max_frames=4, max_size=768, force_frames=False):
    text = str(source_url or "").strip()
    if not text:
        return []
    if not force_frames and text.startswith("asset://"):
        return [{
            "type": "video_url",
            "video_url": {"url": text},
            "role": "reference_video",
        }]
    public_video_url = ""
    if not force_frames:
        try:
            public_video_url = volcengine_video_media_url(text)
        except Exception as exc:
            append_log(LOG_FILE, f"volcengine video reference upload failed, fallback to frames url={text[:120]}: {exc}")
        if public_video_url and looks_like_video_media_url(public_video_url):
            return [{
                "type": "video_url",
                "video_url": {"url": public_video_url},
                "role": "reference_video",
            }]
        if public_video_url:
            append_log(LOG_FILE, f"volcengine video reference uploaded url is not video-like, fallback to frames url={public_video_url[:120]}")
    else:
        append_log(LOG_FILE, f"volcengine video reference forced frame_extract url={text[:120]}")
    frame_urls = video_reference_to_frame_data_urls(text, max_frames=max_frames, max_size=max_size)
    if frame_urls:
        append_log(LOG_FILE, f"volcengine video reference using extracted frames count={len(frame_urls)} url={text[:120]}")
    return [
        {
            "type": "image_url",
            "image_url": {"url": frame_url},
            "role": "reference_image",
        }
        for frame_url in frame_urls
        if frame_url
    ]


def volcengine_image_role(source, index=0, image_count=0):
    raw = str((source or {}).get("role") or "").strip().lower()
    aliases = {
        "first": "first_frame",
        "start": "first_frame",
        "first_frame": "first_frame",
        "last": "last_frame",
        "end": "last_frame",
        "last_frame": "last_frame",
        "reference": "reference_image",
        "reference_image": "reference_image",
        "ref": "reference_image",
        "image": "reference_image",
    }
    if raw in aliases:
        return aliases[raw]
    if image_count <= 1:
        return "first_frame"
    return "reference_image"


def volcengine_video_role(source):
    raw = str((source or {}).get("role") or "").strip().lower()
    if raw in {"reference_video", "video", "reference", "ref"}:
        return "reference_video"
    return "reference_video"


def volcengine_video_content(payload):
    prompt = str((payload or {}).get("prompt") or "").strip()
    if not prompt:
        raise ApiError(400, "缺少视频提示词")
    content = [{"type": "text", "text": prompt}]
    reference_mode = str((payload or {}).get("reference_mode") or "").strip().lower()
    force_video_frames = reference_mode in {"frame_extract", "frames", "extract_frames"}
    images = (payload or {}).get("images") or []
    for index, item in enumerate(images):
        source = item if isinstance(item, dict) else {"url": item}
        media_url = volcengine_image_media_url(source.get("url") or source.get("path") or source.get("src") or "")
        if media_url:
            content.append({
                "type": "image_url",
                "image_url": {"url": media_url},
                "role": volcengine_image_role(source, index, len(images)),
            })
    for item in (payload or {}).get("videos") or []:
        source = item if isinstance(item, dict) else {"url": item}
        raw_video_url = source.get("url") or source.get("path") or source.get("src") or ""
        if not raw_video_url:
            continue
        video_items = volcengine_video_reference_content_items(raw_video_url, force_frames=force_video_frames)
        if not video_items:
            raise ApiError(400, "视频参考处理失败：无法读取视频或抽取关键帧。请确认视频文件存在，或使用素材库 asset:// 视频。")
        content.extend(video_items)
    return content


def volcengine_canvas_video_body(payload):
    model = str((payload or {}).get("model") or "").strip()
    if not model:
        raise ApiError(400, "缺少火山视频模型")
    body = {
        "model": model,
        "content": volcengine_video_content(payload),
    }
    duration = parse_positive_int((payload or {}).get("duration"))
    if duration is not None:
        if "seedance-2-0" in model.lower() or "seedance-1-5" in model.lower():
            duration = max(4, min(15, duration))
        body["duration"] = duration
    ratio = volcengine_normalize_ratio((payload or {}).get("aspect_ratio") or (payload or {}).get("ratio"))
    if ratio:
        body["ratio"] = ratio
    resolution = volcengine_normalize_resolution((payload or {}).get("resolution"))
    if resolution:
        body["resolution"] = resolution
    body["watermark"] = bool((payload or {}).get("watermark"))
    if bool((payload or {}).get("generate_audio")):
        body["generate_audio"] = True
    if bool((payload or {}).get("enhance_prompt")):
        body["enhance_prompt"] = True
    return body


def volcengine_content_debug_summary(content):
    result = []
    for index, item in enumerate(content or []):
        if not isinstance(item, dict):
            result.append({"index": index, "type": type(item).__name__})
            continue
        item_type = str(item.get("type") or "")
        url = ""
        for key in ("image_url", "video_url", "audio_url"):
            value = item.get(key)
            if isinstance(value, dict):
                url = str(value.get("url") or "")
                if url:
                    break
        host = ""
        if url.startswith("asset://"):
            host = "asset"
        elif url:
            try:
                host = urllib.parse.urlparse(url).hostname or ""
            except Exception:
                host = ""
        result.append({
            "index": index,
            "type": item_type,
            "role": item.get("role"),
            "host": host,
            "url_prefix": url[:80],
        })
    return result


def volcengine_base_url(provider):
    return str((provider or {}).get("base_url") or "https://ark.cn-beijing.volces.com/api/v3").strip().rstrip("/")


def volcengine_extract_task_id(data):
    if not isinstance(data, dict):
        return ""
    direct = data.get("id") or data.get("task_id") or data.get("taskId")
    if direct:
        return str(direct).strip()
    nested = data.get("data")
    if isinstance(nested, dict):
        return volcengine_extract_task_id(nested)
    return ""


def volcengine_response_status(data):
    if not isinstance(data, dict):
        return ""
    for key in ("status", "task_status", "taskStatus", "state"):
        value = str(data.get(key) or "").strip().lower()
        if value:
            return value
    nested = data.get("data")
    if isinstance(nested, dict):
        return volcengine_response_status(nested)
    return ""


def volcengine_failure_message(data):
    if not isinstance(data, dict):
        return str(data or "")
    for key in ("error", "message", "detail", "fail_reason", "failReason"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = volcengine_failure_message(value)
            if nested:
                return nested
    nested = data.get("data")
    if isinstance(nested, dict):
        return volcengine_failure_message(nested)
    return ""


def volcengine_user_error_message(error):
    text = str(error or "").strip()
    lower = text.lower()
    if "accountoverdueerror" in lower or "overdue balance" in lower:
        return "火山引擎账户欠费或余额不足，方舟接口返回 403，请在火山控制台充值或结清账单后再生视频。"
    if "authentication" in lower or "unauthorized" in lower or "invalid api key" in lower:
        return "火山引擎 API Key 无效或无权限，请检查方舟 API Key 和模型权限。"
    if "quota" in lower or "insufficient" in lower:
        return "火山引擎额度不足或超过配额，请检查账户额度、并发限制和模型权限。"
    if text.startswith("HTTP 403"):
        return f"火山引擎拒绝请求：{text}"
    return text or "火山引擎请求失败"


def volcengine_collect_video_urls(data):
    urls = []
    seen = set()
    video_keys = {"video_url", "videoUrl", "mp4_url", "mp4Url", "download_url", "downloadUrl", "output_url", "outputUrl"}

    def add(value):
        if isinstance(value, str):
            text = value.strip()
            if text and text not in seen:
                seen.add(text)
                urls.append(text)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, dict):
            walk(value)

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in video_keys:
                    add(child)
                elif isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)
    return urls


def handle_volcengine_canvas_video(payload):
    provider = volcengine_provider_config((payload or {}).get("provider_id") or "volcengine")
    base_url = volcengine_base_url(provider)
    api_key = volcengine_ark_api_key()
    headers = {"Authorization": f"Bearer {api_key}"}
    body = volcengine_canvas_video_body(payload)
    append_log(
        LOG_FILE,
        "volcengine video submit model="
        + str(body.get("model") or "")
        + " content="
        + json.dumps(volcengine_content_debug_summary(body.get("content")), ensure_ascii=False),
    )
    try:
        submit = request_json(f"{base_url}/contents/generations/tasks", "POST", body, headers=headers, timeout=180)
    except Exception as exc:
        raise RuntimeError(volcengine_user_error_message(exc)) from exc
    task_id = volcengine_extract_task_id(submit)
    if not task_id:
        raise RuntimeError(f"火山视频任务提交失败，未返回任务 ID：{submit}")
    query_url = f"{base_url}/contents/generations/tasks/{urllib.parse.quote(task_id)}"
    last = {}
    for _ in range(720):
        time.sleep(2500 / 1000)
        last = request_json(query_url, "GET", headers=headers, timeout=90)
        status = volcengine_response_status(last)
        if status in {"succeeded", "success", "completed", "done"}:
            urls = volcengine_collect_video_urls(last)
            if not urls:
                raise RuntimeError(f"火山视频任务已成功，但未返回 video_url：{last}")
            videos = localize_generated_media_items([{"url": url, "kind": "video"} for url in urls], "video")
            return {"ok": True, "videos": videos, "task_id": task_id, "backend": "volcengine-ark", "raw": {"submit": submit, "result": last}}
        if status in {"failed", "error", "cancelled", "canceled"}:
            detail = volcengine_failure_message(last) or "火山视频任务失败"
            raise RuntimeError(detail)
    raise RuntimeError(f"火山视频任务超时：{task_id}")


def query_volcengine_video_task(provider_id, provider_task_id, localize=False, canvas_title="", canvas_id=""):
    task_id = str(provider_task_id or "").strip()
    if not task_id:
        raise RuntimeError("缺少火山视频任务 ID")
    provider = volcengine_provider_config(provider_id or "volcengine")
    base_url = volcengine_base_url(provider)
    api_key = volcengine_ark_api_key()
    query_url = f"{base_url}/contents/generations/tasks/{urllib.parse.quote(task_id)}"
    try:
        data = request_json(query_url, "GET", headers={"Authorization": f"Bearer {api_key}"}, timeout=90)
    except Exception as exc:
        raise RuntimeError(volcengine_user_error_message(exc)) from exc
    status = volcengine_response_status(data)
    urls = volcengine_collect_video_urls(data)
    if urls and status not in {"failed", "error", "cancelled", "canceled"}:
        videos = [{"url": url, "kind": "video"} for url in urls]
        if localize:
            videos = localize_generated_media_items(videos, "video", canvas_title, canvas_id)
        return {
            "status": "succeeded",
            "result": {"ok": True, "videos": videos, "task_id": task_id, "backend": "volcengine-ark", "raw": {"result": data}},
            "provider_task_id": task_id,
            "raw_status": status,
        }
    if status in {"succeeded", "success", "completed", "done"}:
        raise RuntimeError(f"火山视频任务已成功，但未返回 video_url：{data}")
    if status in {"failed", "error", "cancelled", "canceled"}:
        detail = volcengine_failure_message(data) or "火山视频任务失败"
        return {"status": "failed", "error": detail, "provider_task_id": task_id, "raw": data, "raw_status": status}
    return {"status": "running", "provider_task_id": task_id, "raw": data, "raw_status": status or "running"}


def poll_volcengine_video_task(local_task_id):
    for _ in range(720):
        time.sleep(2500 / 1000)
        if _task_console_is_cancelled(local_task_id):
            return
        state = get_task_state(local_task_id)
        if not state or state.get("status") != "running":
            return
        provider_task_id = state.get("provider_task_id") or state.get("volcengine_task_id")
        try:
            queried = query_volcengine_video_task(state.get("provider_id") or "volcengine", provider_task_id, localize=True, canvas_title=str(state.get("canvas_title") or ""), canvas_id=str(state.get("canvas_id") or ""))
            if queried.get("status") == "succeeded":
                update_task_state(local_task_id, status="succeeded", result=queried.get("result") or {}, completed_at=time.time(), raw_status=queried.get("raw_status") or "")
                append_log(LOG_FILE, f"volcengine video task succeeded local_task_id={local_task_id} provider_task_id={provider_task_id}")
                return
            if queried.get("status") == "failed":
                update_task_state(local_task_id, status="failed", error=queried.get("error") or "火山视频任务失败", completed_at=time.time(), raw=queried.get("raw"), raw_status=queried.get("raw_status") or "")
                append_log(LOG_FILE, f"volcengine video task failed local_task_id={local_task_id} provider_task_id={provider_task_id} error={queried.get('error')}")
                return
            update_task_state(local_task_id, status="running", checked_at=time.time(), raw_status=queried.get("raw_status") or "running")
        except Exception as exc:
            update_task_state(local_task_id, status="running", checked_at=time.time(), last_error=str(exc))
            append_log(LOG_FILE, f"volcengine video task poll failed local_task_id={local_task_id}: {exc}")
    update_task_state(local_task_id, status="failed", error="火山视频任务超时", completed_at=time.time())


def _volcengine_canvas_title_for_output(canvas_id):
    cid = str(canvas_id or "").strip()
    if not cid:
        return ""
    try:
        return str(read_canvas_record(cid).get("title") or "")
    except Exception:
        return ""


def submit_volcengine_canvas_video_task(payload):
    provider_id = (payload or {}).get("provider_id") or "volcengine"
    provider = volcengine_provider_config(provider_id)
    base_url = volcengine_base_url(provider)
    api_key = volcengine_ark_api_key()
    body = volcengine_canvas_video_body(payload)
    append_log(
        LOG_FILE,
        "volcengine video submit model="
        + str(body.get("model") or "")
        + " content="
        + json.dumps(volcengine_content_debug_summary(body.get("content")), ensure_ascii=False),
    )
    try:
        submit = request_json(f"{base_url}/contents/generations/tasks", "POST", body, headers={"Authorization": f"Bearer {api_key}"}, timeout=180)
    except Exception as exc:
        raise RuntimeError(volcengine_user_error_message(exc)) from exc
    provider_task_id = volcengine_extract_task_id(submit)
    if not provider_task_id:
        raise RuntimeError(f"火山视频任务提交失败，未返回任务 ID：{submit}")
    local_task_id = "volc_" + uuid.uuid4().hex
    set_task_state(local_task_id, {
        "status": "running",
        "persistent": True,
        "backend": "volcengine-ark",
        "provider_id": provider_id,
        "provider_task_id": provider_task_id,
        "submit": submit,
        "created_at": time.time(),
        "canvas_id": str((payload or {}).get("canvas_id") or ""),
        "canvas_title": str((payload or {}).get("canvas_title") or _volcengine_canvas_title_for_output((payload or {}).get("canvas_id"))),
        "model": str(body.get("model") or ""),
        "resolution": str((payload or {}).get("resolution") or ""),
        "count": (payload or {}).get("count") or 1,
        "mode": ("i2v" if (isinstance(body.get("content"), list) and body.get("content") and (body["content"][0].get("image_url") or body["content"][0].get("image"))) else "t2v"),
        "node_id": str((payload or {}).get("node_id") or "").strip(),
    }, persistent=True)
    append_log(LOG_FILE, f"volcengine video task submitted local_task_id={local_task_id} provider_task_id={provider_task_id}")
    threading.Thread(target=poll_volcengine_video_task, args=(local_task_id,), daemon=True).start()
    return {"ok": True, "task_id": local_task_id, "provider_task_id": provider_task_id, "status": "running", "backend": "volcengine-ark"}


def refresh_canvas_task_state(task_id):
    state = get_task_state(task_id)
    if not state:
        return {"status": "failed", "error": "任务不存在"}
    if state.get("backend") == "volcengine-ark" and state.get("status") == "running" and (state.get("provider_task_id") or state.get("volcengine_task_id")):
        provider_task_id = state.get("provider_task_id") or state.get("volcengine_task_id")
        try:
            queried = query_volcengine_video_task(state.get("provider_id") or "volcengine", provider_task_id, localize=True, canvas_title=str(state.get("canvas_title") or ""), canvas_id=str(state.get("canvas_id") or ""))
            if queried.get("status") == "succeeded":
                state = update_task_state(task_id, status="succeeded", result=queried.get("result") or {}, completed_at=time.time(), raw_status=queried.get("raw_status") or "")
            elif queried.get("status") == "failed":
                state = update_task_state(task_id, status="failed", error=queried.get("error") or "火山视频任务失败", completed_at=time.time(), raw=queried.get("raw"), raw_status=queried.get("raw_status") or "")
            else:
                state = update_task_state(task_id, status="running", checked_at=time.time(), raw_status=queried.get("raw_status") or "running")
        except Exception as exc:
            state = update_task_state(task_id, status="running", checked_at=time.time(), last_error=str(exc))
    if state.get("backend") == "runninghub-official" and state.get("status") == "running" and state.get("rh_task_id"):
        try:
            queried = runninghub_query_task(state["rh_task_id"])
            status = str(queried.get("status") or "").upper()
            if status == "SUCCESS":
                urls = queried.get("urls") or []
                if urls:
                    with _canvas_task_localize_lock(task_id):
                        if _canvas_task_already_localized(task_id):
                            state = get_task_state(task_id) or state
                        else:
                            raw_result = {
                                "images": urls,
                                "task_id": state["rh_task_id"],
                                "backend": "runninghub-official-proxy",
                                "raw": queried.get("raw") or queried,
                            }
                            # Localize before publishing success so the frontend never sees remote URLs.
                            localized_result = localize_canvas_task_result(raw_result, {
                                "canvas_title": str(state.get("canvas_title") or "").strip(),
                                "canvas_id": str(state.get("canvas_id") or "").strip(),
                                "node_title": str(state.get("node_title") or "").strip(),
                            })
                            state = update_task_state(task_id, status="succeeded", result=localized_result, completed_at=time.time(), raw_status=status, localized_at=time.time())
                else:
                    state = update_task_state(task_id, status="running", checked_at=time.time(), last_error="RunningHub 已完成但结果尚未返回", raw_status=status)
            elif status == "FAILED":
                state = update_task_state(task_id, status="failed", error=queried.get("failReason") or "RunningHub 任务失败", completed_at=time.time(), raw=queried.get("raw"), raw_status=status)
            else:
                state = update_task_state(task_id, status="running", checked_at=time.time(), raw_status=status or "RUNNING")
        except Exception as exc:
            state = update_task_state(task_id, status="running", checked_at=time.time(), last_error=str(exc))
    return state


def runninghub_query_legacy(task_id):
    key = runninghub_task_key()
    status_data = request_json(
        runninghub_api_url("/task/openapi/status"),
        "POST",
        {"apiKey": key, "taskId": task_id},
        timeout=60,
    )
    if isinstance(status_data, dict) and status_data.get("code") not in (None, 0, "0") and not status_data.get("data"):
        message = status_data.get("msg") or status_data.get("message") or status_data.get("errorMessage") or "RunningHub 查询失败"
        return {"status": "FAILED", "failReason": message, "raw": status_data}
    info = status_data.get("data") if isinstance(status_data.get("data"), dict) else status_data
    status = str(info.get("status") or info.get("taskStatus") or "").upper()
    result = {"status": status or "RUNNING", "raw": status_data}
    if result["status"] == "SUCCESS":
        output_data = request_json(
            runninghub_api_url("/task/openapi/outputs"),
            "POST",
            {"apiKey": key, "taskId": task_id},
            timeout=60,
        )
        output_info = output_data.get("data") if isinstance(output_data.get("data"), dict) else output_data
        urls = output_info.get("urls") or output_info.get("images") or []
        if not urls:
            outputs = output_info.get("outputs") or output_info.get("results") or []
            urls = [
                item.get("fileUrl") or item.get("url") or item.get("downloadUrl")
                for item in outputs
                if isinstance(item, dict)
            ]
        result["urls"] = [url for url in urls if isinstance(url, str) and url.strip()]
        result["raw"] = {"status": status_data, "outputs": output_data}
    elif result["status"] == "FAILED":
        result["failReason"] = info.get("failReason") or info.get("message") or ""
    return result


def runninghub_query_v2(task_id):
    data = request_json(
        runninghub_api_url("/openapi/v2/query"),
        "POST",
        {"taskId": task_id},
        headers=runninghub_task_auth_headers(),
        timeout=60,
    )
    if isinstance(data, dict) and str(data.get("errorCode") or "").strip():
        message = data.get("errorMessage") or data.get("message") or "RunningHub 查询失败"
        return {"status": "FAILED", "urls": [], "failReason": message, "raw": data}
    info = data.get("data") if isinstance(data.get("data"), dict) else data
    status = str(info.get("status") or info.get("taskStatus") or "").upper()
    urls = info.get("urls") or []
    if not urls:
        results = info.get("results") or info.get("outputs") or []
        urls = [
            item.get("url") or item.get("fileUrl") or item.get("downloadUrl")
            for item in results
            if isinstance(item, dict)
        ]
    result = {"status": status or "RUNNING", "urls": [url for url in urls if isinstance(url, str) and url.strip()], "raw": data}
    if result["status"] == "FAILED":
        result["failReason"] = info.get("failReason") or info.get("message") or ""
    return result


def runninghub_query_task(task_id):
    errors = []
    for helper in (runninghub_query_v2, runninghub_query_legacy):
        try:
            result = helper(task_id)
            if result.get("status"):
                return result
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError(errors[-1] if errors else "RunningHub 查询失败")


def runninghub_submit_workflow(payload):
    key = runninghub_task_key()
    body = dict(payload or {})
    body["apiKey"] = key
    data = request_json(runninghub_api_url("/task/openapi/create"), "POST", body, timeout=120)
    task_id = data.get("taskId") or (data.get("data") or {}).get("taskId") or ""
    if not task_id:
        raise RuntimeError(f"RunningHub 工作流提交失败：{data}")
    return {"taskId": task_id, "raw": data}


def runninghub_submit_app(payload):
    key = runninghub_task_key()
    body = dict(payload or {})
    body["apiKey"] = key
    data = request_json(runninghub_api_url("/task/openapi/ai-app/run"), "POST", body, timeout=120)
    task_id = data.get("taskId") or (data.get("data") or {}).get("taskId") or ""
    if not task_id:
        raise RuntimeError(f"RunningHub AI 应用提交失败：{data}")
    return {"taskId": task_id, "raw": data}


def runninghub_cached_workflow(workflow_id):
    target_id = str(workflow_id or "").strip()
    if not target_id:
        return None
    for provider in read_api_providers():
        if not isinstance(provider, dict):
            continue
        for item in provider.get("rh_workflows") or []:
            if isinstance(item, dict) and str(item.get("id") or "").strip() == target_id:
                return item
    return None


def runninghub_cached_app_info(app_id):
    target_id = str(app_id or "").strip()
    if not target_id:
        return None
    for provider in read_api_providers():
        if not isinstance(provider, dict):
            continue
        for item in provider.get("rh_apps") or []:
            if isinstance(item, dict) and str(item.get("id") or item.get("appId") or "").strip() == target_id:
                return item
    return None


def runninghub_infer_workflow_field_type(name, value):
    key = str(name or "").strip().lower()
    text = str(value if value is not None else "").strip().lower()
    sample = key + " " + text
    if re.search(r"image|img|mask|photo|picture|png|jpe?g|webp", sample):
        return "IMAGE"
    if re.search(r"video|mp4|webm|mov", sample):
        return "VIDEO"
    if re.search(r"audio|wav|mp3|voice|sound", sample):
        return "AUDIO"
    if isinstance(value, bool) or text in {"true", "false"}:
        return "BOOLEAN"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "NUMBER"
    if text and re.fullmatch(r"-?\d+(\.\d+)?", text):
        return "NUMBER"
    return "TEXT"


def runninghub_workflow_title(workflow_json, workflow_id, fallback_title=""):
    for node in (workflow_json if isinstance(workflow_json, dict) else {}).values():
        if not isinstance(node, dict):
            continue
        title = str(((node.get("_meta") or {}).get("title")) or node.get("class_type") or "").strip()
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        if title and not re.search(r"save|preview|output", title, re.I) and inputs.get("text"):
            return str(fallback_title or title).strip()
    return str(fallback_title or f"工作流 {str(workflow_id)[-6:]}").strip()


def runninghub_fields_from_workflow_json(workflow_json):
    fields = []
    for node_id, node in (workflow_json if isinstance(workflow_json, dict) else {}).items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        if not inputs:
            continue
        title = str(((node.get("_meta") or {}).get("title")) or node.get("class_type") or f"Node {node_id}").strip()
        for field_name, value in inputs.items():
            if isinstance(value, list):
                continue
            if isinstance(value, dict) and "__value__" not in value:
                continue
            field_value = value.get("__value__") if isinstance(value, dict) else value
            field_type = runninghub_infer_workflow_field_type(field_name, field_value)
            field = {
                "id": f"{node_id}::{field_name}",
                "nodeId": str(node_id),
                "fieldName": str(field_name),
                "fieldValue": "" if field_value is None else field_value,
                "fieldType": field_type,
                "label": str(field_name),
                "enabled": False,
                "group": title,
                "note": f"{title} / {field_name}",
            }
            key = str(field_name).lower()
            if field_type == "NUMBER" and ("seed" in key or "noise" in key):
                field["random_enabled"] = True
                field["min"] = 1
                field["max"] = 1000000000000000
                field["step"] = 1
            fields.append(field)
    return fields


def runninghub_default_workflow_fields(workflow_id):
    return [
        {
            "id": "rh-default::prompt",
            "nodeId": "prompt",
            "fieldName": "text",
            "fieldValue": "",
            "fieldType": "TEXT",
            "label": "提示词",
            "enabled": True,
            "sourceFromUpstream": True,
            "group": "基础参数",
            "note": "未能读取 workflow JSON 时的可编辑兜底字段，请按 RunningHub 页面参数手动调整 nodeId/fieldName。",
        },
        {
            "id": "rh-default::seed",
            "nodeId": "seed",
            "fieldName": "seed",
            "fieldValue": "",
            "fieldType": "NUMBER",
            "label": "随机种子",
            "enabled": False,
            "random_enabled": True,
            "min": 1,
            "max": 1000000000000000,
            "step": 1,
            "group": "基础参数",
            "note": f"工作流 {workflow_id} 的兜底随机数参数。",
        },
    ]


def runninghub_fetch_workflow_config(payload):
    workflow_id = str((payload or {}).get("workflowId") or "").strip()
    if not workflow_id:
        raise ApiError(400, "缺少 workflowId")
    title = str((payload or {}).get("title") or f"工作流 {workflow_id[-6:]}").strip()
    description = str((payload or {}).get("description") or "").strip()
    raw = {}
    workflow_json = {}
    fields = []
    source = "fallback"
    fetch_error = ""
    try:
        key = runninghub_task_key()
        raw = request_json(
            runninghub_api_url("/api/openapi/getJsonApiFormat"),
            "POST",
            {"apiKey": key, "workflowId": workflow_id},
            headers={"Authorization": f"Bearer {key}"},
            timeout=120,
        )
        prompt = ((raw.get("data") or {}).get("prompt") if isinstance(raw.get("data"), dict) else None) or raw.get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            workflow_json = json.loads(prompt)
        elif isinstance(prompt, dict):
            workflow_json = prompt
        if isinstance(workflow_json, dict) and workflow_json:
            fields = runninghub_fields_from_workflow_json(workflow_json)
            source = "runninghub-getJsonApiFormat"
    except Exception as exc:
        fetch_error = str(exc)
    if not fields:
        fields = runninghub_default_workflow_fields(workflow_id)
        if fetch_error:
            description = (description + "\n" if description else "") + f"自动拉取 workflow JSON 失败：{fetch_error}"
    return {
        "workflowId": workflow_id,
        "title": runninghub_workflow_title(workflow_json, workflow_id, title),
        "description": description,
        "fields": fields,
        "workflowJson": workflow_json if isinstance(workflow_json, dict) else {},
        "optionalImageMode": "prune-workflow",
        "raw": {"source": source, "fetch_error": fetch_error, "response": raw},
        "updatedAt": int(time.time() * 1000),
    }


def save_runninghub_workflow_config(workflow_id, payload):
    target_id = str(workflow_id or (payload or {}).get("workflowId") or "").strip()
    if not target_id:
        raise ApiError(400, "缺少 workflowId")
    providers = read_api_providers()
    runninghub = next((item for item in providers if isinstance(item, dict) and str(item.get("id") or "") == "runninghub"), None)
    if not runninghub:
        runninghub = {
            "id": "runninghub",
            "name": "RunningHub",
            "base_url": "https://www.runninghub.ai",
            "protocol": "runninghub",
            "enabled": True,
            "image_models": [],
            "chat_models": [],
            "video_models": [],
            "rh_apps": [],
            "rh_workflows": [],
        }
        providers.append(runninghub)
    workflows = runninghub.get("rh_workflows") if isinstance(runninghub.get("rh_workflows"), list) else []
    runninghub["rh_workflows"] = workflows
    existing = next((item for item in workflows if isinstance(item, dict) and str(item.get("id") or item.get("workflowId") or "") == target_id), None)
    if not existing:
        existing = {"id": target_id, "workflowId": target_id, "enabled": True}
        workflows.insert(0, existing)
    safe = payload if isinstance(payload, dict) else {}
    existing.update({
        "id": target_id,
        "workflowId": target_id,
        "title": str(safe.get("title") or existing.get("title") or f"工作流 {target_id[-6:]}").strip(),
        "note": str(safe.get("description") or safe.get("note") or existing.get("note") or "").strip(),
        "fields": safe.get("fields") if isinstance(safe.get("fields"), list) else existing.get("fields", []),
        "workflowJson": safe.get("workflowJson") if isinstance(safe.get("workflowJson"), dict) else existing.get("workflowJson", {}),
        "optionalImageMode": str(safe.get("optionalImageMode") or existing.get("optionalImageMode") or "prune-workflow"),
        "raw": safe.get("raw") if isinstance(safe.get("raw"), dict) else existing.get("raw", {}),
        "updatedAt": int(time.time() * 1000),
        "enabled": safe.get("enabled") is not False,
    })
    saved = write_api_providers(providers)
    for provider in saved:
        if isinstance(provider, dict) and str(provider.get("id") or "") == "runninghub":
            for item in provider.get("rh_workflows") or []:
                if isinstance(item, dict) and str(item.get("id") or item.get("workflowId") or "") == target_id:
                    return item
    return existing


def handle_legacy_generate(payload):
    kind = str((payload or {}).get("type") or "").strip().lower()
    workflow_name = str((payload or {}).get("workflow_json") or "").strip().lower()
    if kind == "workflow-custom" and workflow_name == "krea2参考生成三视图.json":
        # WcsTV's canvas still routes custom nodes through /api/generate.
        # Only this Krea2 workflow is bridged to the local Comfy executor;
        # other legacy generation modes remain unchanged.
        return run_comfy_workflow(str((payload or {}).get("workflow_json") or ""), payload)
    if kind in {"zimage", "klein"} or workflow_name in {"z-image.json", "flux2-klein.json"}:
        compat_payload = resolve_legacy_generate_payload(payload)
        task_id, _submit = submit_official(compat_payload)
        result = poll_result(task_id)
        images = localize_generated_media_items(result.get("images") or [], "image")
        return {
            "images": images,
            "task_id": task_id,
            "backend": "runninghub-official-proxy",
            "raw": result.get("raw") or {},
        }
    raise ApiError(501, "当前版本仅兼容 Z-Image 与 Flux2-Klein 老节点，其他旧 Comfy 工作流尚未迁移。")


def is_runninghub_request(payload):
    protocol = str((payload or {}).get("protocol") or "").strip().lower()
    provider_id = str((payload or {}).get("provider_id") or "").strip().lower()
    base_url = str((payload or {}).get("base_url") or "").strip().lower()
    return protocol == "runninghub" or provider_id == "runninghub" or "runninghub" in base_url


def runninghub_model_catalog(provider_id="", base_url=""):
    selected_id = str(provider_id or "").strip()
    normalized_base = str(base_url or "").strip().lower()
    models = []
    providers = [item for item in read_api_providers() if isinstance(item, dict)]
    for item in providers:
        item_id = str(item.get("id") or "").strip()
        item_protocol = str(item.get("protocol") or "").strip().lower()
        item_base = str(item.get("base_url") or "").strip().lower()
        include = False
        if item_protocol == "runninghub" or item_id == "runninghub":
            include = True
        if selected_id and item_id == selected_id:
            include = True
        if normalized_base and "runninghub" in normalized_base and "runninghub" in item_base:
            include = True
        if not include:
            continue
        models.extend(item for item in (item.get("image_models") or []) if isinstance(item, str))
        models.extend(
            f"app:{entry_id}"
            for entry in (item.get("rh_apps") or [])
            if isinstance(entry, dict)
            and entry.get("enabled", True) is not False
            and entry.get("hidden", False) is not True
            for entry_id in [str(entry.get("appId") or entry.get("webappId") or entry.get("id") or "").strip()]
            if entry_id
        )
        models.extend(
            f"workflow:{entry_id}"
            for entry in (item.get("rh_workflows") or [])
            if isinstance(entry, dict)
            and entry.get("enabled", True) is not False
            and entry.get("hidden", False) is not True
            for entry_id in [str(entry.get("workflowId") or entry.get("id") or "").strip()]
            if entry_id
        )
    all_models = unique_strings(models + RUNNINGHUB_DEFAULT_IMAGE_MODELS)
    return {
        "ok": True,
        "protocol": "runninghub",
        "all": all_models,
        "image_models": all_models,
        "chat_models": [],
        "video_models": [],
        "total": len(all_models),
        "model_count": len(all_models),
    }


def runninghub_probe_payload(payload, action="test"):
    if action != "probe":
        try:
            runninghub_doc_origin(payload.get("base_url"))
        except Exception as exc:
            return {
                "ok": False,
                "protocol": "runninghub",
                "status": 0,
                "status_code": 0,
                "source": "runninghub-address-check",
                "all": [],
                "image_models": [],
                "chat_models": [],
                "video_models": [],
                "total": 0,
                "model_count": 0,
                "message": str(exc),
                "detail": str(exc),
            }
        image_models = unique_strings(RUNNINGHUB_DEFAULT_IMAGE_MODELS)
        result = {
            "ok": True,
            "protocol": "runninghub",
            "source": "runninghub-address-check",
            "all": image_models,
            "image_models": image_models,
            "chat_models": [],
            "video_models": [],
            "total": len(image_models),
            "model_count": len(image_models),
        }
    else:
        result = runninghub_model_catalog(payload.get("provider_id"), payload.get("base_url"))
    result["status"] = 200
    result["status_code"] = 200
    result["raw"] = {
        "provider_id": payload.get("provider_id") or "",
        "base_url": payload.get("base_url") or "",
        "protocol": "runninghub",
        "total": result["total"],
    }
    if action == "probe":
        result["message"] = "RunningHub 协议已识别，模型列表来自内置/手动维护配置。"
    else:
        result["message"] = "RunningHub 地址验证通过，模型列表来自内置/手动维护配置。"
    return result


RUNNINGHUB_DOC_INDEX_PATH = "/runninghub-api-doc-en/llms.txt"
RUNNINGHUB_DOC_URL_RE = re.compile(r"https?://[^)\s]+/runninghub-api-doc-en/api-\d+\.md")
RUNNINGHUB_IMAGE_DOC_RE = re.compile(r"\b(text-to-image|image-to-image|edit)\b", re.IGNORECASE)
RUNNINGHUB_DOC_ROUTE_RE = re.compile(r"/openapi/v2/([a-zA-Z0-9._/-]+):")


def runninghub_doc_origin(base_url):
    raw = str(base_url or "").strip()
    if not raw:
        raise RuntimeError("请先填写 RunningHub 请求地址")
    parsed = urllib.parse.urlparse(raw if "://" in raw else f"https://{raw}")
    host = str(parsed.netloc or parsed.path or "").strip().lower()
    if not host:
        raise RuntimeError("RunningHub 请求地址无效")
    # 2026-09-10 解锁：地址由用户自管，只要求是合法 host（不再限定官方域名）
    if "." not in host and ":" not in host:
        raise RuntimeError("RunningHub 请求地址无效")
    scheme = parsed.scheme or "https"
    return f"{scheme}://{host}"


def request_text(url, timeout=60):
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "text/plain, text/markdown, text/html;q=0.9, */*;q=0.8")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code}: {raw or 'RunningHub 文档请求失败'}")


RUNNINGHUB_DOC_LINE_RE = re.compile(r"^- ([^\[]*)\[([^\]]*)\]\((https?://[^)\s]+/runninghub-api-doc-en/api-\d+\.md)\)")


def runninghub_doc_urls_from_index(index_text):
    urls = []
    for line in str(index_text or "").splitlines():
        if not RUNNINGHUB_IMAGE_DOC_RE.search(line):
            continue
        match = RUNNINGHUB_DOC_LINE_RE.match(line)
        if not match:
            fallback = RUNNINGHUB_DOC_URL_RE.search(line)
            if fallback:
                urls.append(fallback.group(0))
            continue
        if "video" in match.group(1).lower():
            # 面包屑里已含 video：直接跳过，省掉几十次文档请求
            continue
        urls.append(match.group(3))
    return unique_strings(urls)


def runninghub_route_from_doc(doc_text):
    match = RUNNINGHUB_DOC_ROUTE_RE.search(str(doc_text or ""))
    return str(match.group(1) or "").strip() if match else ""


def runninghub_is_image_route(route):
    normalized = str(route or "").strip().lower()
    return bool(normalized) and "video" not in normalized


# 火山「推理计划」plan 端点（.../api/plan/v3）是 OpenAI 兼容对话入口，不提供 /models 列表。
# 这里在后端固化该端点可用的对话模型清单，Agent 模型下拉直接可选，无需手动输入或在线拉取。
VOLCENGINE_PLAN_DEFAULT_CHAT_MODELS = [
    "deepseek-v4-flash",
    "glm-5.3-flash",
    "doubao-seed-2.1-turbo",
    "minimax-m3",
    "glm-5.3",
    "kimi-k2.7-code",
    "deepseek-v4-pro",
    "kimi-k3",
]


def is_volcengine_plan_base(base_url=""):
    return "/api/plan/" in str(base_url or "").strip().lower()


def volcengine_plan_chat_models(extra=None):
    merged = list(VOLCENGINE_PLAN_DEFAULT_CHAT_MODELS)
    for item in (extra or []):
        text = str(item or "").strip()
        if text and text not in merged:
            merged.append(text)
    return merged


def volcengine_fetch_models(payload):
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    api_key = str(payload.get("api_key") or "").strip()
    # Fallback: read from env file if not provided in payload
    if not api_key:
        api_key = volcengine_ark_api_key()
    if not api_key:
        return {"ok": False, "status": 0, "message": "请先填写或保存方舟 API Key", "detail": "缺少 API Key", "all": [], "image_models": [], "video_models": [], "chat_models": [], "model_count": 0, "total": 0}
    # 火山「推理计划」plan 端点是 OpenAI 兼容对话入口，只提供 /chat/completions，不提供 /models。
    # 这类地址用于 Agent 对话，不用于图像/视频任务，因此验证地址按对话端点处理（404 属正常）。
    if "/api/plan/" in base_url:
        plan_models = volcengine_plan_chat_models()
        return {
            "ok": True,
            "protocol": "volcengine",
            "source": "volcengine-plan-chat",
            "all": plan_models,
            "image_models": [],
            "video_models": [],
            "chat_models": plan_models,
            "total": len(plan_models),
            "model_count": len(plan_models),
            "status": 200,
            "message": "方舟推理计划(plan)对话端点可用。该端点不提供模型列表，Agent 模型可直接输入模型名（如 deepseek-v4-flash）。",
        }
    models_url = f"{base_url}/models"
    try:
        data = request_json(models_url, "GET", headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
    except Exception as exc:
        return {"ok": False, "status": 0, "message": f"请求失败: {exc}", "detail": f"请求失败: {exc}", "all": [], "image_models": [], "video_models": [], "chat_models": [], "model_count": 0, "total": 0}
    raw_models = data.get("data") or []
    all_models = unique_strings([str(m.get("id") or "").strip() for m in raw_models if isinstance(m, dict) and str(m.get("id") or "").strip()])
    image_models = [m for m in all_models if re.search(r"seedream|seededit|t2i|i2i|image", m, re.I)]
    video_models = [m for m in all_models if re.search(r"seedance|t2v|i2v|wan2", m, re.I)]
    chat_models = [m for m in all_models if not re.search(r"seedream|seededit|seedance|t2i|i2v|t2v|wan2|seed3d|3d-|embedding", m, re.I)]
    return {
        "ok": True,
        "protocol": "volcengine",
        "source": "volcengine-ark-api",
        "all": all_models,
        "image_models": image_models,
        "video_models": video_models,
        "chat_models": chat_models,
        "total": len(all_models),
        "model_count": len(all_models),
    }


def is_volcengine_request(payload):
    protocol = str((payload or {}).get("protocol") or "").strip().lower()
    provider_id = str((payload or {}).get("provider_id") or "").strip().lower()
    base_url = str((payload or {}).get("base_url") or "").strip().lower()
    return protocol == "volcengine" or provider_id == "volcengine" or "volces.com" in base_url


def openai_probe_payload(payload, action="test"):
    """自定义 OpenAI 兼容平台：本地(:3107)直接探 {base_url}/models，不再转发 :3000 内部服务。"""
    payload = payload if isinstance(payload, dict) else {}
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    provider_id = str(payload.get("provider_id") or "").strip()
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key and provider_id:
        try:
            api_key = read_chat_key(provider_id) or ""
        except Exception:
            api_key = ""
    empty = {"all": [], "image_models": [], "video_models": [], "chat_models": [], "model_count": 0, "total": 0}
    if not base_url:
        return {"ok": False, "protocol": "openai", "status": 0, "status_code": 0,
                "source": "openai-models", "message": "请先填写请求地址", "detail": "缺少请求地址", **empty}
    urls = [f"{base_url}/models"]
    if not base_url.endswith("/v1"):
        urls.append(f"{base_url}/v1/models")
    data = None
    last_error = None
    for url in urls:
        try:
            data = request_json(url, "GET", headers={"Authorization": f"Bearer {api_key}"} if api_key else {}, timeout=30)
            break
        except Exception as exc:
            last_error = exc
    if data is None:
        msg = f"请求失败: {last_error}"
        return {"ok": False, "protocol": "openai", "status": 0, "status_code": 0,
                "source": "openai-models", "message": msg, "detail": msg, **empty}
    raw_models = data.get("data") or []
    all_models = unique_strings([str(m.get("id") or "").strip() for m in raw_models if isinstance(m, dict) and str(m.get("id") or "").strip()])
    image_models = [m for m in all_models if re.search(r"image|seedream|seededit|t2i|i2i|flux|sd3|dalle", m, re.I)]
    video_models = [m for m in all_models if re.search(r"video|seedance|t2v|i2v|kling", m, re.I) and m not in image_models]
    chat_models = [m for m in all_models if m not in image_models and m not in video_models]
    result = {
        "ok": True,
        "protocol": "openai",
        "source": "openai-models",
        "status": 200,
        "status_code": 200,
        "all": all_models,
        "image_models": image_models,
        "video_models": video_models,
        "chat_models": chat_models,
        "total": len(all_models),
        "model_count": len(all_models),
    }
    if api_key:
        result["message"] = f"地址与 API Key 验证通过，共 {len(all_models)} 个模型。"
    else:
        result["message"] = f"地址可达（共 {len(all_models)} 个模型），但未填写 API Key——保存 Key 后才能确认鉴权通过。"
    result["raw"] = {"provider_id": provider_id, "base_url": base_url, "protocol": "openai", "total": len(all_models)}
    return result


def volcengine_probe_payload(payload, action="test"):
    result = volcengine_fetch_models(payload if isinstance(payload, dict) else {})
    result["protocol"] = "volcengine"
    result["source"] = "volcengine-ark-api"
    result["status_code"] = result.get("status") or (200 if result.get("ok") else 0)
    result["raw"] = {
        "provider_id": (payload or {}).get("provider_id") or "",
        "base_url": (payload or {}).get("base_url") or "",
        "protocol": "volcengine",
        "total": result.get("total") or 0,
    }
    if result.get("ok"):
        result["status"] = 200
        result["message"] = result.get("message") or "火山引擎方舟地址验证通过，模型列表已同步。"
    else:
        result["message"] = result.get("message") or result.get("detail") or "火山引擎方舟地址验证失败"
    return result


RUNNINGHUB_CATALOG_CACHE_FILE = USER_DATA_DIR / "data" / "rh_live_model_catalog.json"
RUNNINGHUB_CATALOG_CACHE_TTL_SECONDS = 6 * 3600


def _runninghub_read_catalog_cache():
    try:
        data = json.loads(RUNNINGHUB_CATALOG_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    models = [m for m in (data.get("models") or []) if isinstance(m, str)]
    if not models or time.time() - float(data.get("fetched_at") or 0) > RUNNINGHUB_CATALOG_CACHE_TTL_SECONDS:
        return None
    return models


def _runninghub_write_catalog_cache(models):
    try:
        write_json_file(RUNNINGHUB_CATALOG_CACHE_FILE, {"fetched_at": time.time(), "models": list(models)})
    except Exception:
        pass


def runninghub_crawl_image_routes(origin):
    """抓官方文档索引 -> 并发解析每个图像模型文档的真实 /openapi/v2 路由（约 20-30 秒，结果缓存 6 小时）。"""
    from concurrent.futures import ThreadPoolExecutor
    index_text = request_text(f"{origin}{RUNNINGHUB_DOC_INDEX_PATH}", timeout=30)
    doc_urls = runninghub_doc_urls_from_index(index_text)
    if not doc_urls:
        raise RuntimeError("RunningHub 文档索引未返回任何图像模型条目")

    def route_of(doc_url):
        try:
            return runninghub_route_from_doc(request_text(doc_url, timeout=20))
        except Exception:
            return ""

    with ThreadPoolExecutor(max_workers=10) as executor:
        routes = list(executor.map(route_of, doc_urls))
    models = unique_strings(
        r for r in (str(x or "").strip() for x in routes) if r and "video" not in r.lower()
    )
    if not models:
        raise RuntimeError("未能从 RunningHub 官方文档解析到模型列表")
    return models


def runninghub_live_model_catalog(base_url, force=False):
    models = [] if force else (_runninghub_read_catalog_cache() or [])
    source = "runninghub-docs-cache"
    detail = ""
    if not models:
        source = "runninghub-docs-live"
        try:
            origin = runninghub_doc_origin(base_url)
            models = runninghub_crawl_image_routes(origin)
            _runninghub_write_catalog_cache(models)
        except Exception as exc:
            source = "runninghub-compatibility-fallback"
            detail = str(exc)
    image_models = unique_strings(models + RUNNINGHUB_DEFAULT_IMAGE_MODELS)
    return {
        "ok": True,
        "protocol": "runninghub",
        "source": source,
        "all": image_models,
        "image_models": image_models,
        "chat_models": [],
        "video_models": [],
        "total": len(image_models),
        "model_count": len(image_models),
        **({"detail": detail} if detail else {}),
    }


def runninghub_model_catalog(provider_id="", base_url="", force=False):
    del provider_id
    return runninghub_live_model_catalog(base_url, force=force)


def runninghub_probe_payload(payload, action="test"):
    if action != "probe":
        try:
            runninghub_doc_origin(payload.get("base_url"))
        except Exception as exc:
            return {
                "ok": False,
                "protocol": "runninghub",
                "status": 0,
                "status_code": 0,
                "source": "runninghub-address-check",
                "all": [],
                "image_models": [],
                "chat_models": [],
                "video_models": [],
                "total": 0,
                "model_count": 0,
                "message": str(exc),
                "detail": str(exc),
            }
        image_models = unique_strings(RUNNINGHUB_DEFAULT_IMAGE_MODELS)
        result = {
            "ok": True,
            "protocol": "runninghub",
            "source": "runninghub-address-check",
            "all": image_models,
            "image_models": image_models,
            "chat_models": [],
            "video_models": [],
            "total": len(image_models),
            "model_count": len(image_models),
        }
    else:
        result = runninghub_model_catalog(payload.get("provider_id"), payload.get("base_url"))
    result["status"] = 200
    result["status_code"] = 200
    result["raw"] = {
        "provider_id": payload.get("provider_id") or "",
        "base_url": payload.get("base_url") or "",
        "protocol": "runninghub",
        "total": result["total"],
        "source": result.get("source") or "runninghub-docs-live",
    }
    if action == "probe":
        result["message"] = "RunningHub 协议已识别，模型列表实时解析自官方文档。"
    else:
        if result.get("source") == "runninghub-address-check":
            result["message"] = "RunningHub 地址验证通过，模型列表来自内置/已维护配置。"
        else:
            result["message"] = "RunningHub 地址验证通过，模型列表已实时同步官方文档。"
    return result


def submit_official(payload):
    key = read_env_key()
    if not key:
        raise RuntimeError("未找到 RunningHub API Key，请检查 API/.env")
    refs = payload.get("reference_images") or []
    provider_id = str(payload.get("provider_id") or "runninghub").strip()
    if provider_id == "custom-api-3":
        provider_id = "runninghub"
    model = _agent_select_configured_image_model(provider_id, payload.get("model"), refs)
    endpoint = f"{runninghub_api_base()}/openapi/v2/{model}"
    body = build_official_body(payload, model, refs)
    data = request_json(endpoint, "POST", body, {"Authorization": f"Bearer {key}"}, timeout=120)
    task_id = data.get("taskId") or ""
    if not task_id:
        raise RuntimeError(f"RunningHub 未返回 taskId：{data}")
    return task_id, data


def poll_result(task_id):
    deadline = time.time() + RUNNINGHUB_POLL_TIMEOUT_SECONDS
    last = ""
    while time.time() < deadline:
        if _task_console_is_cancelled(task_id):
            raise _TaskConsoleCancelled()
        try:
            info = runninghub_query_task(task_id)
        except Exception as exc:
            last = str(exc)
            time.sleep(5)
            continue
        last = json.dumps(info, ensure_ascii=False)
        status = str(info.get("status") or "").upper()
        if status == "SUCCESS":
            urls = info.get("urls") or []
            if not urls:
                raise RuntimeError(f"RunningHub 成功但没有返回图片：{info}")
            return {
                "images": urls,
                "task_id": task_id,
                "backend": "runninghub-official-proxy",
                "raw": info.get("raw") or info,
            }
        if status == "FAILED":
            raise RuntimeError(info.get("failReason") or json.dumps(info, ensure_ascii=False))
        time.sleep(3)
    raise RuntimeError(f"RunningHub 查询超时：{last}")


def localize_canvas_task_result(result, payload):
    if not isinstance(result, dict):
        return result
    canvas_title = str((payload or {}).get("canvas_title") or "").strip()
    canvas_id = str((payload or {}).get("canvas_id") or "").strip()
    node_title = str((payload or {}).get("node_title") or "").strip()
    localized = dict(result)
    try:
        if localized.get("images"):
            localized["images"] = localize_generated_media_items(localized.get("images") or [], "image", canvas_title, canvas_id, node_title)
        if localized.get("videos"):
            localized["videos"] = localize_generated_media_items(localized.get("videos") or [], "video", canvas_title, canvas_id, node_title)
        if localized.get("audios"):
            localized["audios"] = localize_generated_media_items(localized.get("audios") or [], "audio", canvas_title, canvas_id, node_title)
    except Exception as exc:
        localized["localize_error"] = str(exc)
        append_log(LOG_FILE, f"canvas task localize failed task={localized.get('task_id')}: {exc}")
    return localized


def localize_canvas_task_result_background(task_id, result, payload):
    try:
        localized = localize_canvas_task_result(result, payload)
        if isinstance(localized, dict) and localized != result:
            current = get_task_state(task_id)
            if current and current.get("status") == "succeeded":
                update_task_state(task_id, result=localized, localized_at=time.time())
                append_log(LOG_FILE, f"canvas task localized in background task={task_id}")
    except Exception as exc:
        append_log(LOG_FILE, f"canvas task background localize failed task={task_id}: {exc}")


def submit_volcengine_agent_task(payload):
    """Agent 生图链路：火山引擎生成（图像/视频统一走 contents/generations/tasks）"""
    provider_id = str((payload or {}).get("provider_id") or "volcengine").strip()
    provider = volcengine_provider_config(provider_id)
    base_url = volcengine_base_url(provider)
    api_key = volcengine_ark_api_key()
    model = str((payload or {}).get("model") or "").strip()
    if not model:
        raise RuntimeError("缺少火山生成模型")
    content = [{"type": "text", "text": str((payload or {}).get("prompt") or "").strip()}]
    refs = (payload or {}).get("reference_images") or []
    if isinstance(refs, list):
        for ref in refs:
            url = str(ref or "").strip()
            if url:
                content.append({"type": "image_url", "image_url": {"url": url}, "role": "reference_image"})
    body = {"model": model, "content": content}
    ratio = volcengine_normalize_ratio((payload or {}).get("aspect_ratio") or (payload or {}).get("ratio"))
    if ratio:
        body["ratio"] = ratio
    resolution = volcengine_normalize_resolution((payload or {}).get("resolution"))
    if resolution:
        body["resolution"] = resolution
    body["watermark"] = False
    try:
        submit = request_json(f"{base_url}/contents/generations/tasks", "POST", body, headers={"Authorization": f"Bearer {api_key}"}, timeout=180)
    except Exception as exc:
        raise RuntimeError(volcengine_user_error_message(exc)) from exc
    provider_task_id = volcengine_extract_task_id(submit)
    if not provider_task_id:
        raise RuntimeError(f"火山生成任务提交失败，未返回任务 ID：{submit}")
    return provider_task_id, submit


def poll_volcengine_agent_task(local_task_id):
    for _ in range(720):
        time.sleep(2500 / 1000)
        state = get_task_state(local_task_id)
        if not state or state.get("status") != "running":
            return
        provider_task_id = state.get("provider_task_id") or state.get("volcengine_task_id")
        try:
            queried = query_volcengine_video_task(state.get("provider_id") or "volcengine", provider_task_id, localize=True, canvas_title=str(state.get("canvas_title") or ""), canvas_id=str(state.get("canvas_id") or ""))
            if queried.get("status") == "succeeded":
                update_task_state(local_task_id, status="succeeded", result=queried.get("result") or {}, completed_at=time.time(), raw_status=queried.get("raw_status") or "")
                append_log(LOG_FILE, f"volcengine agent task succeeded local_task_id={local_task_id} provider_task_id={provider_task_id}")
                return
            if queried.get("status") == "failed":
                update_task_state(local_task_id, status="failed", error=queried.get("error") or "火山生成任务失败", completed_at=time.time(), raw=queried.get("raw"), raw_status=queried.get("raw_status") or "")
                append_log(LOG_FILE, f"volcengine agent task failed local_task_id={local_task_id} provider_task_id={provider_task_id} error={queried.get('error')}")
                return
            update_task_state(local_task_id, status="running", checked_at=time.time(), raw_status=queried.get("raw_status") or "running")
        except Exception as exc:
            update_task_state(local_task_id, status="running", checked_at=time.time(), last_error=str(exc))
            append_log(LOG_FILE, f"volcengine agent task poll failed local_task_id={local_task_id}: {exc}")
    update_task_state(local_task_id, status="failed", error="火山生成任务超时", completed_at=time.time())


def _previz_ratio_size(aspect_ratio):
    text = str(aspect_ratio or "").strip().lower().replace(" ", "")
    mapping = {
        "16:9": (1280, 720), "wide": (1280, 720),
        "9:16": (720, 1280), "story": (720, 1280),
        "1:1": (720, 720), "square": (720, 720),
        "3:2": (1080, 720), "landscape": (1080, 720),
        "2:3": (720, 1080), "portrait": (720, 1080),
        "4:3": (960, 720), "landscape43": (960, 720),
        "3:4": (720, 960), "portrait43": (720, 960),
        "21:9": (1680, 720), "ultrawide": (1680, 720),
        "9:21": (720, 1680), "ultratall": (720, 1680),
    }
    return mapping.get(text, (1280, 720))


def pick_previz_folder():
    """弹出 Windows 文件夹选择框，返回用户选择的路径（取消返回空串）。
    以当前前台窗口为 owner 模态弹出（否则会被前台锁压制显示在应用后面）。"""
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms | Out-Null;"
        "Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public class PrevizWin32 {[DllImport(\"user32.dll\")]public static extern IntPtr GetForegroundWindow();public class PrevizOwner : System.Windows.Forms.IWin32Window {public IntPtr H;public IntPtr Handle {get{return H;}}}}' -ReferencedAssemblies System.Windows.Forms;"
        "$f = New-Object System.Windows.Forms.FolderBrowserDialog;"
        "$f.Description = '选择本地资产文件夹';"
        "$ow = New-Object PrevizWin32+PrevizOwner;"
        "$ow.H = [PrevizWin32]::GetForegroundWindow();"
        "if($f.ShowDialog($ow) -eq [System.Windows.Forms.DialogResult]::OK){ $f.SelectedPath } else { '' }"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=180,
        )
        lines = [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]
        return lines[-1] if lines else ""
    except Exception as exc:
        append_log(LOG_FILE, f"pick folder failed: {exc}")
        return ""


def _strip_llm_fenced_text(text):
    text = str(text or "").strip()
    fence = re.match(r"^```(?:\w+)?\s*([\s\S]*?)\s*```$", text)
    if fence:
        text = fence.group(1).strip()
    return text.strip()


def enhance_previz_prompt_with_llm(prompt, payload):
    """用选定聊天模型把自然语言整理成现有 previz_parse.py 可读的镜头表。
    失败时抛出异常给调用方记录；调用方会回退原提示词，保持旧流程不变。"""
    prompt = str(prompt or "").strip()
    if not prompt:
        return prompt
    llm_provider = str((payload or {}).get("previz_llm_provider") or "").strip()
    llm_model = str((payload or {}).get("previz_llm_model") or "").strip()
    provider_id, model, upstream_base, key = resolve_chat_target({
        "provider": llm_provider,
        "model": llm_model,
        "agent_id": (payload or {}).get("agent_id") or "",
    })
    aspect = str((payload or {}).get("aspectRatio") or "").strip() or "16:9"
    canvas_title = str((payload or {}).get("canvas_title") or "").strip() or "未命名画布"
    system = (
        "你是 MyridTV 无限画布的 3D 预演镜头规划器。"
        "把用户输入整理成可由离线 Blender 预演解析器读取的镜头表，不解释、不写 Markdown。"
        "每行必须使用这个格式：镜号 | 时长 | 景别 | 运镜 | 内容 | 主体 | 相机。\n"
        "镜号用 S01、S02。时长写“3秒”这类格式。"
        "景别只能从 特写、近景、中近景、中景、全景、远景、大远景 中选择。"
        "运镜只能从 固定、推、拉、摇、移、跟、环绕、俯拍、仰拍、升降、甩镜、变焦 或用 + 组合中选择。"
        "主体列用“名称[x,y,z]颜色”或“名称[x,y,z]→[x,y,z]颜色”，多人用空格分隔；"
        "常用颜色：红、蓝、青、橙、灰、冷灰、黑、白。"
        "相机列用“相机[x,y,z]→[x,y,z] 24mm”。"
        "如果用户已经给了竖线镜头表，要保留其意图并补齐缺失主体/相机。"
        "不要输出标题、说明、列表符号或代码块。"
    )
    user = (
        f"画布：{canvas_title}\n"
        f"视频比例：{aspect}\n"
        "请把下面内容整理成 1 到 8 个 Blender 预演镜头行。"
        "镜头要有明确主体位置、主体运动、相机位置、目标点和焦距；"
        "自然语言不明确时使用安全默认：人物在地面，场景中心，24fps，单镜头 4 秒，中景，云台感的平稳运动。\n\n"
        f"{prompt}"
    )
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
    }
    data = request_chat_json_with_retry(
        f"{upstream_base}/chat/completions",
        body,
        {"Authorization": f"Bearer {key}"},
        attempts=2,
        timeout=180,
    )
    choices = data.get("choices") if isinstance(data, dict) else []
    message = (choices[0].get("message") if choices and isinstance(choices[0], dict) else {}) or {}
    text = _strip_llm_fenced_text(message.get("content") or "")
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip().strip("|").strip()
        if not line or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        if re.fullmatch(r"[-:\s|]+", line):
            continue
        if not re.search(r"\d", parts[1] if len(parts) > 1 else ""):
            continue
        if not re.match(r"^(S\d+|镜头\d+|M\d+)", parts[0], re.I):
            continue
        lines.append(" | ".join(parts))
    if not lines:
        raise RuntimeError("LLM 未返回可解析的镜头表")
    enhanced = "\n".join(lines)
    append_log(LOG_FILE, "previz llm enhanced provider={} model={} chars={} lines={}".format(
        provider_id, model, len(enhanced), len(lines)))
    return enhanced


def run_blender_previz(payload):
    """画布 Blender 预演：镜头表文本(prompt) → previz 三件套 → mp4。
    渲染完成后走插件通道(append_blender_assets)自动建节点回填画布。"""
    import sys  # 顶层未导入 sys，这里局部引入
    canvas_id = str((payload or {}).get("canvas_id") or "").strip()
    canvas_title = str((payload or {}).get("canvas_title") or "").strip()
    prompt = str((payload or {}).get("prompt") or "").strip()
    if not prompt:
        raise RuntimeError("Blender 预演缺少镜头表文本（节点 prompt）")
    llm_enabled = bool((payload or {}).get("previz_llm_enabled"))
    if llm_enabled:
        llm_provider = str((payload or {}).get("previz_llm_provider") or "").strip()
        llm_model = str((payload or {}).get("previz_llm_model") or "").strip()
        append_log(LOG_FILE, f"previz llm requested provider={llm_provider or '-'} model={llm_model or '-'} prompt_chars={len(prompt)}")
        try:
            original_prompt = prompt
            prompt = enhance_previz_prompt_with_llm(prompt, payload or {})
            append_log(LOG_FILE, f"previz llm enhanced prompt_chars={len(original_prompt)}->{len(prompt)} changed={prompt != original_prompt}")
        except Exception as exc:
            append_log(LOG_FILE, f"previz llm enhance failed; fallback original prompt: {exc}")
    else:
        append_log(LOG_FILE, "previz llm disabled")
    if not canvas_title:
        canvas_title = "未命名画布"
    if not PREVIZ_DIR.exists():
        raise RuntimeError(f"预演脚本目录不存在: {PREVIZ_DIR}")
    width, height = _previz_ratio_size(payload.get("aspectRatio"))
    run_dir = PREVIZ_DIR / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    tag = time.strftime("%m%d_%H%M%S")
    shots_txt = run_dir / f"shots_{tag}.txt"
    shots_txt.write_text(prompt, encoding="utf-8")
    shots_json = run_dir / f"shots_{tag}.json"
    frames_dir = run_dir / f"frames_{tag}"
    frames_dir.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    def run_cmd(cmd, timeout=2400):
        append_log(LOG_FILE, f"previz cmd: {' '.join(str(c) for c in cmd)}")
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env, cwd=str(PREVIZ_DIR))
        out = (proc.stdout or b"").decode("utf-8", errors="replace")
        err = (proc.stderr or b"").decode("utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(
                f"previz 命令失败: {' '.join(str(c) for c in cmd[:6])}...\n{out[-1000:]}\n{err[-1000:]}"
            )
        return out

    # 1) 解析镜头表文本 → previz JSON（资产目录：前端用户选择可覆盖默认）
    asset_dir = str((payload or {}).get("asset_dir") or (payload or {}).get("asset_path") or "").strip()
    parse_cmd = [py, "-B", str(PREVIZ_DIR / "previz_parse.py"),
                 "--input", str(shots_txt), "--output", str(shots_json),
                 "--width", str(width), "--height", str(height), "--fps", str(PREVIZ_FPS)]
    if asset_dir:
        parse_cmd += ["--assets-dir", asset_dir]
    run_cmd(parse_cmd)
    # 2) Blender Workbench 渲染，同时保存预演工程 .blend
    # 工程统一存 assets/blender_projects/，命名 08-24-01.blender（月-日-当日序号）
    projects_dir = ASSETS_DIR / "blender_projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    seq = len([p for p in projects_dir.glob("*.blender")]) + 1
    blend_path = projects_dir / f"{time.strftime('%m-%d')}-{seq:02d}.blender"
    asset_path = str((payload or {}).get("asset_path") or "").strip()
    blocking_dir = PREVIZ_DIR / "blocking"
    blocking_used = False
    if (payload or {}).get("previz_blocking_core", True) is not False:
        try:
            shot_spec = run_dir / f"blocking_shot_{tag}.py"
            run_cmd([py, "-B", str(PREVIZ_DIR / "blocking_bridge.py"),
                     "--input", str(shots_json), "--output", str(shot_spec)],
                    timeout=120)
            run_cmd([py, "-B", str(blocking_dir / "solve_shot.py"), str(shot_spec)],
                    timeout=180)
            bake_json = shot_spec.with_name("bake.json")
            run_cmd([BLENDER_BIN, "--background", "--python-exit-code", "1", "--python", str(PREVIZ_DIR / "blocking_render.py"), "--",
                     "--input", str(shots_json), "--bake", str(bake_json), "--spec", str(shot_spec),
                     "--core", str(blocking_dir / "previz_core.py"),
                     "--output", str(frames_dir), "--save-blend", str(blend_path)],
                    timeout=3600)
            blocking_used = True
            append_log(LOG_FILE, f"previz blocking core used tag={tag}")
        except Exception as exc:
            append_log(LOG_FILE, f"previz blocking core fallback tag={tag}: {exc}")
            try:
                shutil.rmtree(frames_dir, ignore_errors=True)
                frames_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
    if not blocking_used:
        render_cmd = [BLENDER_BIN, "--background", "--python", str(PREVIZ_DIR / "previz_render.py"), "--",
                      "--input", str(shots_json), "--output", str(frames_dir), "--single-scene",
                      "--save-blend", str(blend_path)]
        if asset_path:
            render_cmd += ["--asset-path", asset_path]
        run_cmd(render_cmd, timeout=3600)
    # 3) ffmpeg 拼接成片
    video_dir = ASSETS_DIR / "output" / canvas_title / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    video_name = f"previz_{tag}.mp4"
    video_path = video_dir / video_name
    run_cmd([py, "-B", str(PREVIZ_DIR / "previz_build.py"),
             "--input", str(frames_dir), "--output", str(video_path)],
            timeout=1200)
    if not video_path.exists():
        raise RuntimeError("预演视频未生成")
    size = video_path.stat().st_size
    url = asset_output_url(video_name, "video", canvas_folder=canvas_title)
    # 读 manifest 拿帧数/时长（拼接脚本写入）
    total_frames = 0
    manifest_file = frames_dir / "manifest.json"
    if manifest_file.exists():
        try:
            mf = json.loads(manifest_file.read_text(encoding="utf-8"))
            total_frames = sum(int(s.get("帧数") or 0) for s in (mf.get("镜头") or []))
        except Exception:
            pass
    duration_seconds = round(total_frames / max(PREVIZ_FPS, 1), 3) if total_frames else 0
    # 自动打开 Blender 工程（GUI）+ 把当前画布 ID 填进 myridtv 插件面板（亮绿灯才能手动推送回传）
    if blend_path.exists():
        try:
            fill_script = PREVIZ_DIR / "open_with_canvas.py"
            subprocess.Popen(
                [BLENDER_BIN, str(blend_path), "--python", str(fill_script), "--",
                 "--canvas-id", canvas_id, "--proxy-url", "http://127.0.0.1:3107"],
                cwd=str(PREVIZ_DIR))
            append_log(LOG_FILE, f"previz opened blend={blend_path.name} canvas={canvas_id}")
        except Exception as exc:
            append_log(LOG_FILE, f"previz open blend failed: {exc}")
    # 画布点生成路径：不 append 建节点（避免与前端写回原节点重复 = 双视频节点 bug）
    # 回填统一由前端 finalizeSmartPendingTask 写回原 3D预演 节点
    # 插件手动推送仍走 append_blender_assets（push-animation 路由）
    append_log(LOG_FILE, f"previz done url={url} size={size} dur={duration_seconds}")
    return {
        "images": [{"url": url, "name": video_name, "kind": "video", "display_name": f"Blender 预演 {tag}"}],
        "backend": "blender-previz",
        "blocking_core": blocking_used,
        "video_url": url,
        "duration_seconds": duration_seconds,
    }


def run_task(task_id, payload):
    try:
        provider_id = str((payload or {}).get("provider_id") or "").strip()
        if provider_id == "blender":
            update_task_state(task_id, status="running", backend="blender-previz", provider_id="blender", checked_at=time.time())
            result = run_blender_previz(payload)
            update_task_state(task_id, status="succeeded", result=result, completed_at=time.time(), localized_at=time.time())
            return
        if provider_id == "volcengine":
            provider_task_id, submit_raw = submit_volcengine_agent_task(payload)
            update_task_state(task_id, status="running", provider_task_id=provider_task_id, submit=submit_raw, checked_at=time.time(), backend="volcengine-ark", provider_id="volcengine")
            threading.Thread(target=poll_volcengine_agent_task, args=(task_id,), daemon=True).start()
            return
        if provider_id == "runninghub":
            workflow_name = str((payload or {}).get("model") or "").strip()
            entry = None
            for provider in read_api_providers():
                if str(provider.get("id") or "") != "runninghub":
                    continue
                for item in provider.get("rh_workflows") or []:
                    if isinstance(item, dict) and str(item.get("title") or item.get("name") or "") == workflow_name:
                        entry = item
                        break
                if entry:
                    break
            if entry:
                workflow_id = str(entry.get("workflowId") or entry.get("id") or "").strip()
                if not workflow_id:
                    raise RuntimeError("RunningHub 云端工作流缺少 workflowId")
                submit = runninghub_submit_workflow({"workflowId": workflow_id, "nodeInfoList": []})
                rh_task_id = str(submit.get("taskId") or "").strip()
                if not rh_task_id:
                    raise RuntimeError("RunningHub 云端工作流提交失败")
                update_task_state(task_id, status="running", rh_task_id=rh_task_id, submit=submit.get("raw") or submit, checked_at=time.time())
                result = poll_result(rh_task_id)
                current = get_task_state(task_id)
                if current.get("status") == "succeeded" and current.get("localized_at"):
                    return
                result = localize_canvas_task_result(result, payload)
                update_task_state(task_id, status="succeeded", result=result, completed_at=time.time(), localized_at=time.time())
                return
        rh_task_id, submit_raw = submit_official(payload)
        update_task_state(task_id, status="running", rh_task_id=rh_task_id, submit=submit_raw, checked_at=time.time())
        result = poll_result(rh_task_id)
        # If refresh_canvas_task_state already localized the result (race condition), skip.
        with _canvas_task_localize_lock(task_id):
            if _canvas_task_already_localized(task_id):
                append_log(LOG_FILE, f"run_task skip localize, already done by refresh task={task_id}")
                return
            # Localize before publishing success so the frontend never localizes the same remote files again.
            result = localize_canvas_task_result(result, payload)
            update_task_state(task_id, status="succeeded", result=result, completed_at=time.time(), localized_at=time.time())
    except Exception as exc:
        if _task_console_is_cancelled(task_id):
            # 控制台手动停止：保持 cancelled 状态，不被轮询异常覆盖
            return
        error = str(exc)
        append_log(LOG_FILE, "[CanvasTaskFailed] task={} provider={} model={} err={}".format(task_id, (payload or {}).get("provider_id"), (payload or {}).get("model"), error[:400]))
        if "RunningHub 查询超时" in error:
            update_task_state(task_id, status="running", checked_at=time.time(), last_error=error, poll_window_expired_at=time.time())
        else:
            update_task_state(task_id, status="failed", error=error, completed_at=time.time())


def handle_localize_generated_media(payload):
    safe_payload = payload if isinstance(payload, dict) else {}
    raw_items = safe_payload.get("items")
    if not isinstance(raw_items, list):
        raw_items = safe_payload.get("images")
    if not isinstance(raw_items, list):
        raw_items = []
    kind = str(safe_payload.get("kind") or "image")
    canvas_title = str(safe_payload.get("canvas_title") or "").strip()
    canvas_id = str(safe_payload.get("canvas_id") or "").strip()
    try:
        node_title = str(safe_payload.get("node_title") or "").strip()
        items = localize_generated_media_items(raw_items, kind, canvas_title, canvas_id, node_title)
        return {
            "ok": True,
            "items": items,
        }
    except Exception as exc:
        append_log(LOG_FILE, f"localize generated media route fallback: {exc}")
        return {
            "ok": True,
            "items": [fallback_generated_media_item(item, kind, exc) for item in raw_items],
            "localize_error": str(exc),
            "fallback": True,
        }


# ====== Canvas MCP Tools (嵌入式) ======
MCP_TOOLS = {
    "canvas_list_canvases": {"description": "列出所有画布", "inputSchema": {"type":"object","properties":{}}},
    "canvas_get_state": {"description": "获取画布状态", "inputSchema": {"type":"object","properties":{"canvas_id":{"type":"string"}}}},
    "canvas_get_selection": {"description": "获取选中节点", "inputSchema": {"type":"object","properties":{"canvas_id":{"type":"string"}}}},
    "canvas_search": {"description": "搜索节点", "inputSchema":{"type":"object","properties":{"query":{"type":"string"},"canvas_id":{"type":"string"}},"required":["query"]}},
    "canvas_create_node": {"description": "创建节点", "inputSchema":{"type":"object","properties":{"type":{"type":"string"},"x":{"type":"number"},"y":{"type":"number"},"width":{"type":"number"},"height":{"type":"number"},"content":{"type":"string"},"label":{"type":"string"},"canvas_id":{"type":"string"}},"required":["type","x","y"]}},
    "canvas_delete_node": {"description": "删除节点", "inputSchema":{"type":"object","properties":{"node_id":{"type":"string"},"canvas_id":{"type":"string"}},"required":["node_id"]}},
    "canvas_update_node": {"description": "更新节点", "inputSchema":{"type":"object","properties":{"node_id":{"type":"string"},"content":{"type":"string"},"x":{"type":"number"},"y":{"type":"number"},"width":{"type":"number"},"height":{"type":"number"},"label":{"type":"string"},"canvas_id":{"type":"string"}},"required":["node_id"]}},
    "canvas_connect_nodes": {"description": "连接节点", "inputSchema":{"type":"object","properties":{"from_id":{"type":"string"},"to_id":{"type":"string"},"label":{"type":"string"},"canvas_id":{"type":"string"}},"required":["from_id","to_id"]}},
    "canvas_snapshot": {"description": "保存快照", "inputSchema":{"type":"object","properties":{"canvas_id":{"type":"string"}}}},
    "canvas_create_text_node": {"description": "创建智能画布原生文本节点(剧本/脚本/方案,type=smart-prompt,内容可见可编辑)", "inputSchema":{"type":"object","properties":{"text":{"type":"string"},"title":{"type":"string"},"x":{"type":"number"},"y":{"type":"number"},"canvas_id":{"type":"string"}},"required":["text"]}},
    "canvas_create_generation_node": {"description": "创建图片生成节点(把提示词同步到画布,type=smart-image,待生成)", "inputSchema":{"type":"object","properties":{"prompt":{"type":"string"},"title":{"type":"string"},"model":{"type":"string"},"size":{"type":"string"},"canvas_id":{"type":"string"}},"required":["prompt"]}},
    "canvas_generate_images": {"description": "提交图片生成任务并回填画布节点(异步)。调用后立即返回 task_id 即提交成功,不要等待、不要轮询;生成完成后图片会自动回填到画布节点,之后用 canvas_get_state 或 canvas_check_generation 查看结果。未给 node_id 会自动建生成节点", "inputSchema":{"type":"object","properties":{"prompt":{"type":"string"},"node_id":{"type":"string"},"model":{"type":"string"},"size":{"type":"string"},"reference_image_urls":{"type":"array","items":{"type":"string"}},"canvas_id":{"type":"string"}},"required":["prompt"]}},
    "canvas_analyze_image": {"description": "分析画布图片内容(看图):OCR文字/版面/语义,返回结构化JSON证据(经 ModLens 视觉引擎)", "inputSchema":{"type":"object","properties":{"image_url":{"type":"string"},"node_id":{"type":"string"},"prompt":{"type":"string"},"canvas_id":{"type":"string"}}}},
    "canvas_list_skills": {"description": "列出已保存的技能", "inputSchema":{"type":"object","properties":{}}},
    "canvas_save_skill": {"description": "把方法/工作流保存为可复用技能(@技能名调用)", "inputSchema":{"type":"object","properties":{"name":{"type":"string"},"content":{"type":"string"}},"required":["name","content"]}},
}
MCP_CACHE = {}
# MCP 画布工具直接调用本代理自身（3107）的 API：APP_BASE 指向 server.port(3000)
# 的旧前端服务，在纯代理部署下已不可达（502/拒绝连接），画布读写会整体失败。
MCP_BASE = str(PROXY_CONFIG.get("base_url") or f"http://127.0.0.1:{PORT}").rstrip("/")

def _mcp_canvas_id(cid=""):
    if cid: return cid
    try:
        r = urllib.request.Request(f"{MCP_BASE}/api/canvases")
        with urllib.request.urlopen(r, timeout=5) as f:
            d = json.loads(f.read())
        cs = d if isinstance(d, list) else d.get("canvases", [])
        if cs: cs.sort(key=lambda c: c.get("last_modified",0), reverse=True); return str(cs[0].get("id",""))
    except: pass
    return ""

def _mcp_fetch(cid=""):
    cid = _mcp_canvas_id(cid)
    if not cid: return {}, False
    try:
        r = urllib.request.Request(f"{MCP_BASE}/api/canvases/{urllib.parse.quote(cid)}")
        with urllib.request.urlopen(r, timeout=5) as f:
            d = json.loads(f.read())
        # 响应形如 {"ok":true,"canvas":{...}}，解包 canvas 字段供 _mcp_handle 使用
        if isinstance(d, dict) and "canvas" in d: d = d.get("canvas") or {}
        MCP_CACHE["id"]=cid; MCP_CACHE["data"]=d
        return d, True
    except: return {}, False

def _mcp_save(cid, data):
    try:
        body = json.dumps(data).encode()
        r = urllib.request.Request(f"{MCP_BASE}/api/canvases/{urllib.parse.quote(cid)}", data=body, method="PUT", headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(r, timeout=5): return True
    except: return False

def _mcp_handle(name, args):
    cid = args.get("canvas_id","") or MCP_CACHE.get("id","")
    if name == "canvas_list_canvases":
        try:
            r = urllib.request.Request(f"{MCP_BASE}/api/canvases")
            with urllib.request.urlopen(r, timeout=5) as f:
                d = json.loads(f.read())
            cs = d if isinstance(d, list) else d.get("canvases",[])
            return {"result":[{"id":c.get("id"),"title":c.get("title",c.get("name","未命名")),"nodes":c.get("node_count",0)} for c in cs]}
        except Exception as e: return {"error":str(e)}
    cv, ok = _mcp_fetch(cid)
    if not ok: return {"error":"画布获取失败"}
    nodes = cv.get("nodes", cv.get("data",{}).get("nodes",[]))
    edges = cv.get("connections", cv.get("edges", cv.get("data",{}).get("edges",[])))
    cid = MCP_CACHE.get("id","")
    if name == "canvas_get_state":
        return {"result":{"canvas_id":cid,"node_count":len(nodes),"edge_count":len(edges),
            "nodes":[{"id":n.get("id"),"type":n.get("type"),"label":n.get("label",n.get("title","")),"x":n.get("x"),"y":n.get("y")} for n in nodes],"edges":edges}}
    if name == "canvas_get_selection":
        sel = cv.get("data",{}).get("selectedIds",[]); sn = [n for n in nodes if n.get("id") in sel]
        return {"result":{"selected_ids":sel,"nodes":sn}}
    if name == "canvas_search":
        q = args.get("query","").lower()
        mt = [n for n in nodes if q in str(n.get("label",n.get("title",""))).lower() or q in str(n.get("content","")).lower()]
        return {"result":{"query":q,"matches":len(mt),"nodes":mt}}
    if name == "canvas_create_node":
        # Phase 3：统一走 _agent_batch_build_* + Artifact Gate，废除 hm_ schema（与 Agent 通道共用单写点）
        node_type = str(args.get("type", "text")).strip().lower()
        params = {
            "canvas_id": cid,
            "type": node_type,
            "title": str(args.get("label") or args.get("title") or "MCP 节点").strip(),
            "text": str(args.get("content") or "").strip(),
            "prompt": str(args.get("content") or "").strip(),
            "x": args.get("x"),
            "y": args.get("y"),
        }
        try:
            if node_type in ("generation", "image", "smart-image", "gen"):
                node, ref_ids = _agent_batch_build_generation_node(cv, params, None)
            else:
                node = _agent_batch_build_text_node(cv, params)
        except ValueError as ve:
            return {"error": "参数不完整: {}".format(ve)}
        if args.get("width"):
            try: node["w"] = int(args["width"])
            except Exception: pass
        if args.get("height"):
            try: node["h"] = int(args["height"])
            except Exception: pass
        ok, nid, save_ok, deduped = _agent_canvas_repo_upsert_node(cid, cv, node, "mcp", args)
        if not ok:
            return {"error": nid}
        return {"result": {"node_id": nid, "type": node["type"], "origin": "mcp", "deduped": deduped}}
    if name == "canvas_delete_node":
        nid = str(args.get("node_id", "") or "").strip()
        d = cv.get("data", cv)
        d["nodes"] = [n for n in d.get("nodes", []) if n.get("id") != nid]
        d["edges"] = [e for e in d.get("edges", []) if e.get("from", e.get("source")) != nid and e.get("to", e.get("target")) != nid]
        if isinstance(d.get("connections"), list):
            d["connections"] = [c for c in d["connections"] if c.get("from") != nid and c.get("to") != nid]
        # Phase 4：与 REST/Agent 通道一致写墓碑
        d["deleted"] = _merge_node_tombstones(d.get("deleted"), [{"id": nid, "at": int(time.time() * 1000), "by": "mcp"}])
        _mcp_save(cid, d)
        return {"result": {"deleted": nid, "tombstoned": True}}
    if name == "canvas_update_node":
        nid = args.get("node_id",""); d = cv.get("data",cv)
        for n in d.get("nodes",[]):
            if n.get("id")==nid:
                for k in ("content","x","y","width","height","label"):
                    if k in args: n[k]=args[k]
                break
        _mcp_save(cid,d); return {"result":{"node_id":nid}}
    if name == "canvas_connect_nodes":
        eid = f"e_{uuid.uuid4().hex[:8]}"; d = cv.get("data",cv)
        el = d.get("edges",[]); el.append({"id":eid,"from":args["from_id"],"to":args["to_id"],"label":args.get("label","")})
        d["edges"]=el; _mcp_save(cid,d); return {"result":{"edge_id":eid}}
    if name == "canvas_snapshot":
        d = cv.get("data",cv); d["snapshot_at"]=time.time(); _mcp_save(cid,d)
        return {"result":{"canvas_id":cid}}
    if name == "canvas_create_text_node":
        return _agent_tool_create_text_node(args)
    if name == "canvas_create_generation_node":
        return _agent_tool_create_generation_node(args, None)
    if name == "canvas_generate_images":
        return _agent_tool_generate_images(args, None)
    if name == "canvas_analyze_image":
        return _agent_tool_analyze_image(args)
    if name == "canvas_list_skills":
        return _agent_tool_list_skills(args)
    if name == "canvas_save_skill":
        return _agent_tool_save_skill(args)
    return {"error":f"unknown tool: {name}"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, raw, "application/json; charset=utf-8")

    def _send_bytes(self, status, raw, content_type="application/json; charset=utf-8"):
        self_content_type = content_type or "application/octet-stream"
        self.send_response(status)
        self.send_header("Content-Type", self_content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,HEAD,POST,DELETE,OPTIONS")
        # 对 HTML/CSS/JS 文件禁止缓存，避免 WebView2 顽固缓存
        if "text/html" in self_content_type or "text/css" in self_content_type or "javascript" in self_content_type:
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _serve_static(self, url_path):
        request_path = urllib.parse.urlparse(str(url_path or "")).path or "/"
        if request_path.startswith("/api/") or request_path.startswith("/assets/"):
            return False

        static_root = (APP_DIR / "_internal" / "static").resolve()
        if request_path.startswith("/static/"):
            relative = urllib.parse.unquote(request_path[len("/static/"):])
            allow_index_fallback = False
        elif request_path in ("", "/"):
            relative = "index.html"
            allow_index_fallback = True
        else:
            relative = urllib.parse.unquote(request_path.lstrip("/"))
            allow_index_fallback = not Path(relative).suffix

        target = (static_root / relative).resolve()
        if static_root not in target.parents and target != static_root:
            self._send(403, {"detail": "forbidden"})
            return True
        if not target.exists() or not target.is_file():
            if not allow_index_fallback:
                self._send(404, {"detail": "static asset not found"})
                return True
            target = static_root / "index.html"
        if not target.exists() or not target.is_file():
            return False
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self._send_bytes(200, target.read_bytes(), content_type)
        return True

    def _serve_user_asset(self, url_path):
        request_path = urllib.parse.urlparse(str(url_path or "")).path or ""
        if not request_path.startswith("/assets/"):
            return False
        try:
            target = resolve_user_asset_path(url_path)
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self._send_bytes(200, Path(target).read_bytes(), content_type)
        except ApiError as exc:
            self._send(exc.status, {"detail": exc.detail, **exc.payload})
        except Exception as exc:
            self._send(404, {"detail": str(exc)})
        return True

    def _serve_remote_output(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query, keep_blank_values=True)
        source_url = str((query.get("url") or [""])[0]).strip()
        parsed = urllib.parse.urlparse(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ApiError(400, "无效的输出地址")
        request = urllib.request.Request(source_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"
        })
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0].strip()
        self._send_bytes(200, raw, content_type or "application/octet-stream")
        return True

    def _forward_upstream(self, method, request_path, body=None):
        target = f"{APP_BASE}{request_path}"
        headers = {}
        content_type = self.headers.get("Content-Type")
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(target, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                raw = response.read()
                self._send_bytes(
                    getattr(response, "status", 200),
                    raw,
                    response.headers.get("Content-Type") or "application/json; charset=utf-8",
                )
                return True
        except urllib.error.HTTPError as exc:
            raw = exc.read() or json.dumps({"detail": str(exc)}, ensure_ascii=False).encode("utf-8")
            self._send_bytes(
                getattr(exc, "code", 502),
                raw,
                exc.headers.get("Content-Type") if exc.headers else "application/json; charset=utf-8",
            )
            return True
        except Exception as exc:
            append_log(LOG_FILE, f"forward {method} {request_path} failed: {exc}")
            self._send(502, {"detail": str(exc)})
            return True

    def do_OPTIONS(self):
        self._send(200, {"ok": True})

    def do_HEAD(self):
        try:
            if self._serve_static(self.path):
                return
            if self._serve_user_asset(self.path):
                return
            self._send(404, {"detail": "not found"})
        except ApiError as exc:
            self._send(exc.status, {"detail": exc.detail, **exc.payload})
        except Exception as exc:
            append_log(LOG_FILE, f"{self.command} {self.path} failed: {exc}\n{traceback.format_exc()}")
            self._send(502, {"detail": str(exc)})

    def do_GET(self):
        try:
            request_path = self.path.split("?", 1)[0]
            canvas_route, canvas_id = parse_canvas_route(request_path)
            workflow_route, workflow_name = parse_workflow_route(request_path)
            if request_path == "/health":
                self._send(200, {
                    "ok": True,
                    "pid": os.getpid(),
                    "version": STATIC_VERSION,
                    "host": str(PROXY_CONFIG.get("host") or "127.0.0.1"),
                    "port": PORT,
                    "app_base": APP_BASE,
                    "config_file": str(CONFIG_FILE),
                    "user_data_dir": str(USER_DATA_DIR),
                    "blender_import_dir": str(BLENDER_IMPORT_DIR),
                    "log_file": str(LOG_FILE),
                    "mcp": True,
                    "agent": {
                        "provider_id": AGENT_CONFIG.get("provider_id"),
                        "model": AGENT_CONFIG.get("model"),
                        "upstream_base_url": AGENT_CONFIG.get("upstream_base_url"),
                    },
                })
                return
            if request_path == "/api/task-console":
                self._send(200, task_console_snapshot())
                return
            if request_path == "/mcp" and self.command == "GET":
                # MCP Streamable HTTP 规范中 GET 是可选的通知通道；本服务只做
                # 纯 POST 无状态模式，返回 405 让 MCP SDK 跳过 SSE 流管理。
                # （旧实现返回 SSE endpoint 后立即断开，会让 SDK 触发重连循环，
                #   长请求（如 ModLens 40-60s）期间 transport 偶发 fetch failed。）
                self.send_response(405)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
                self.send_header("Allow", "POST")
                self.end_headers()
                return
            if request_path == "/app-config":
                safe_config = deep_merge(APP_CONFIG, {
                    "agent": agents_meta_payload(),
                })
                safe_config["agent_storage"] = {
                    "env_file": str(ENV_FILE),
                    "config_file": str(CONFIG_FILE),
                    "models_file": str(USER_DATA_DIR / "data" / "api_providers.json"),
                }
                self._send(200, safe_config)
                return
            if request_path == "/api/canvas-agent-history":
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query or "", keep_blank_values=True)
                canvas_id = (query.get("canvas_id") or [""])[0]
                self._send(200, {"ok": True, "canvas_id": canvas_id, "history": read_canvas_agent_history(canvas_id)})
                return
            if request_path == "/api/canvas-agent-history-index":
                self._send(200, {"ok": True, "entries": read_canvas_agent_history_index()})
                return
            if request_path == "/api/canvas-agent-tasks":
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query or "", keep_blank_values=True)
                canvas_q = str((query.get("canvas_id") or [""])[0] or "").strip()
                conv_q = str((query.get("conversation_id") or query.get("session_id") or [""])[0] or "").strip()
                with TASKS_LOCK:
                    items = [
                        task for task in TASKS.values()
                        if isinstance(task, dict)
                        and (not canvas_q or str(task.get("canvas_id") or "") == canvas_q)
                        and (not conv_q or str(task.get("conversation_id") or "") == conv_q)
                    ]
                self._send(200, {
                    "ok": True,
                    "tasks": [agent_runtime.serialize_task(item) for item in items],
                    "count": len(items),
                })
                return
            if request_path == "/api/canvas-agent-config":
                self._send(200, canvas_agent_config_payload())
                return
            if request_path == "/api/canvas-agent-skill":
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query or "", keep_blank_values=True)
                name = (query.get("name") or [""])[0]
                skill = read_canvas_agent_skill(name)
                self._send(200, {"ok": True, "skill": skill})
                return
            if request_path == "/api/integrations/blender/status":
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query or "", keep_blank_values=True)
                canvas_id = (query.get("canvas_id") or [""])[0]
                self._send(200, blender_connection_status(canvas_id))
                return
            if request_path == "/api/runninghub/query":
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query or "", keep_blank_values=True)
                task_id = (query.get("taskId") or [""])[0]
                if not str(task_id or "").strip():
                    raise ApiError(400, "缺少 taskId")
                self._send(200, {"success": True, "data": runninghub_query_task(task_id)})
                return
            if request_path == "/api/runninghub/app-info":
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query or "", keep_blank_values=True)
                app_id = (query.get("webappId") or [""])[0]
                cached = runninghub_cached_app_info(app_id)
                if cached:
                    self._send(200, {"ok": True, "data": cached})
                    return
                raise ApiError(404, "未找到已缓存的 RunningHub 应用")
            if request_path.startswith("/api/runninghub/workflows/"):
                workflow_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
                cached = runninghub_cached_workflow(workflow_id)
                if cached:
                    self._send(200, {"ok": True, "data": cached})
                    return
                raise ApiError(404, "未找到已缓存的 RunningHub 工作流")
            if request_path == "/api/providers":
                self._send(200, {"ok": True, "providers": read_api_providers()})
                return
            if request_path == "/api/canvas-thumbnail":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query, keep_blank_values=True)
                source_url = (query.get("url") or [""])[0]
                try:
                    size = int((query.get("size") or ["640"])[0])
                except (TypeError, ValueError):
                    size = 640
                thumbnail = canvas_thumbnail_path(source_url, size)
                self._send_bytes(200, thumbnail.read_bytes(), "image/webp")
                return
            if request_path == "/api/canvas-image-info":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query, keep_blank_values=True)
                source_url = (query.get("url") or [""])[0]
                self._send(200, canvas_image_info(source_url))
                return
            if request_path == "/api/download-output":
                self._serve_remote_output()
                return
            if self._serve_static(self.path):
                return
            if self._serve_user_asset(self.path):
                return
            if request_path == "/api/config":
                self._send(200, build_local_config_payload())
                return
            if request_path == "/api/asset-library":
                self._send(200, {"ok": True, "library": read_asset_library()})
                return
            if request_path == "/api/prompt-libraries":
                self._send(200, {"ok": True, "library": read_prompt_libraries()})
                return
            if request_path == "/api/comfyui/instances":
                self._send(200, {"ok": True, "instances": read_comfy_instances()})
                return
            if request_path == "/api/comfyui/object-info":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                types = [t.strip() for t in (query.get("types") or [""])[0].split(",") if t.strip()]
                try:
                    self._send(200, {"ok": True, "object_info": comfy_flow_service.object_info_subset(types or None)})
                except Exception as exc:
                    self._send(502, {"ok": False, "error": f"读取 ComfyUI 节点元数据失败: {str(exc)[:200]}"})
                return
            if request_path.startswith("/api/comfyui/jobs/"):
                job = comfy_flow_service.MANAGER.get(request_path.rsplit("/", 1)[-1])
                if not job:
                    # 后端重启过，内存里的任务记录已丢失，前端应停止轮询而不是一直等
                    self._send(404, {"ok": False, "error": "任务不存在或已过期", "status": "gone"})
                    return
                self._send(200, {"ok": True, **job.to_dict()})
                return
            if request_path == "/api/comfyui/jobs":
                self._send(200, {"ok": True, "jobs": comfy_flow_service.MANAGER.list_jobs()})
                return
            if request_path == "/api/comfyui/recent-outputs":
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                limit = (query.get("limit") or ["6"])[0]
                self._send(200, recent_comfy_outputs({"limit": limit}))
                return
            if workflow_route == "collection":
                self._send(200, {"ok": True, "workflows": list_workflow_records()})
                return
            if workflow_route == "item":
                self._send(200, {"ok": True, **read_workflow_record(workflow_name)})
                return
            if canvas_route == "collection":
                self._send(200, {"ok": True, "canvases": list_canvas_records(include_deleted=False)})
                return
            if canvas_route == "trash":
                self._send(200, {"ok": True, "canvases": list_canvas_records(include_deleted=True)})
                return
            if canvas_route == "item":
                self._send(200, {"ok": True, "canvas": read_canvas_record(canvas_id, include_deleted=True)})
                return
            if canvas_route == "meta":
                canvas = read_canvas_record(canvas_id, include_deleted=True)
                self._send(200, {"ok": True, **canvas_summary(canvas)})
                return
            if canvas_route == "export":
                self._send(200, export_canvas_payload(canvas_id))
                return
            prefix = "/api/canvas-image-tasks/"
            if request_path.startswith(prefix):
                task_id = request_path[len(prefix):]
                self._send(200, refresh_canvas_task_state(task_id))
                return
            if request_path.startswith("/api/"):
                if self._forward_upstream("GET", self.path):
                    return
            self._send(404, {"detail": "not found"})
        except ApiError as exc:
            self._send(exc.status, {"detail": exc.detail, **exc.payload})
        except Exception as exc:
            append_log(LOG_FILE, f"{self.command} {self.path} failed: {exc}\n{traceback.format_exc()}")
            self._send(502, {"detail": str(exc)})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw_body = self.rfile.read(length)
            content_type = str(self.headers.get("Content-Type") or "")
            request_path = self.path.split("?", 1)[0]
            if request_path == "/api/upload" and "multipart/form-data" in content_type.lower():
                # This is the upload path used by the ComfyUI canvas inputs.
                # Handle it before JSON decoding so PNG/JPEG bytes are preserved.
                self._send(200, handle_comfy_upload(raw_body, content_type))
                return
            if request_path == "/api/ai/upload" and "multipart/form-data" in content_type.lower():
                self._send(200, handle_ai_upload(raw_body, content_type))
                return
            payload = json.loads(raw_body.decode("utf-8") or "{}") if raw_body else {}
            canvas_route, canvas_id = parse_canvas_route(request_path)
            workflow_route, workflow_name = parse_workflow_route(request_path)
            if request_path == "/mcp":
                method = payload.get("method", "")
                req_id = payload.get("id")
                params = payload.get("params", {})
                if method == "initialize":
                    self._send(200, {"jsonrpc": "2.0", "id": req_id, "result": {
                        "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                        "serverInfo": {"name": "myridtv-canvas", "version": "0.2.0"},
                    }})
                elif method == "tools/list":
                    tools = [{"name": name, **defn} for name, defn in MCP_TOOLS.items()]
                    self._send(200, {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}})
                elif method == "tools/call":
                    name = params.get("name", "")
                    args = params.get("arguments", {})
                    if name not in MCP_TOOLS:
                        self._send(200, {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Tool not found: {name}"}})
                    else:
                        try:
                            result = _mcp_handle(name, args)
                            if "error" in result:
                                self._send(200, {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": result["error"]}})
                            else:
                                # 兼容两种返回格式：{"result": ...} 或 _agent_tool_* 直接返回的 {ok: ..., ...}
                                payload = result.get("result", result)
                                txt = json.dumps(payload, ensure_ascii=False)
                                self._send(200, {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": txt}]}})
                        except Exception as e:
                            self._send(200, {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(e)}})
                elif method == "notifications/initialized":
                    self._send(200, {})
                else:
                    self._send(200, {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown: {method}"}})
                return
            if request_path == "/api/online-image":
                rh_task_id, _ = submit_official(payload)
                result = poll_result(rh_task_id)
                self._send(200, {
                    "images": result["images"],
                    "timestamp": int(time.time() * 1000),
                    "prompt": payload.get("prompt") or "",
                    "params": payload,
                    "task_id": rh_task_id,
                })
                return
            if request_path == "/api/generate":
                self._send(200, handle_legacy_generate(payload))
                return
            if request_path == "/api/runninghub/upload-asset":
                url = str(payload.get("url") or "").strip()
                if not url:
                    raise ApiError(400, "缺少 url")
                uploaded = runninghub_upload_task_asset(url)
                self._send(200, {"success": True, "data": uploaded})
                return
            if request_path == "/api/runninghub/workflows/fetch":
                workflow = runninghub_fetch_workflow_config(payload)
                self._send(200, {"success": True, "data": workflow})
                return
            if request_path == "/api/volcengine/upload-asset":
                url = str(payload.get("url") or "").strip()
                if not url:
                    raise ApiError(400, "缺少 url")
                uploaded = volcengine_upload_asset(url)
                self._send(200, {"success": True, "data": uploaded})
                return
            if request_path == "/api/cloud-video/upload":
                url = str(payload.get("url") or "").strip()
                if not url:
                    raise ApiError(400, "缺少 url")
                uploaded = upload_cloud_media_direct(url)
                self._send(200, uploaded)
                return
            if request_path == "/api/canvas-video" and is_volcengine_canvas_video_payload(payload):
                self._send(200, submit_volcengine_canvas_video_task(payload))
                return
            if request_path in ("/api/asset-library/items", "/api/asset-library/items/batch"):
                self._send(200, add_asset_library_items(payload))
                return
            if request_path == "/api/asset-library/libraries":
                self._send(200, create_asset_library_record(payload))
                return
            if request_path == "/api/asset-library/categories":
                self._send(200, create_asset_category_record(payload))
                return
            if request_path == "/api/asset-library/items/versions":
                self._send(200, add_asset_library_version(payload))
                return
            if request_path == "/api/asset-library/items/delete":
                self._send(200, delete_asset_items_record(payload))
                return
            if request_path == "/api/asset-library/items/move":
                self._send(200, move_asset_items_record(payload))
                return
            if request_path == "/api/asset-library/items/crop":
                self._send(200, crop_asset_items_record(payload))
                return
            if request_path == "/api/prompt-libraries":
                self._send(200, create_prompt_library_record(payload))
                return
            if request_path == "/api/prompt-libraries/categories":
                self._send(200, create_prompt_category_record(payload))
                return
            if request_path == "/api/prompt-libraries/items":
                self._send(200, create_prompt_item_record(payload))
                return
            if request_path == "/api/prompt-libraries/items/delete":
                self._send(200, delete_prompt_items_record(payload))
                return
            if request_path == "/api/localize-generated-media":
                self._send(200, handle_localize_generated_media(payload))
                return
            if request_path == "/api/move-to-history":
                self._send(200, move_output_asset_to_history(payload))
                return
            if request_path == "/api/runninghub/submit":
                self._send(200, {"success": True, "data": runninghub_submit_app(payload)})
                return
            if request_path == "/api/runninghub/workflow-submit":
                self._send(200, {"success": True, "data": runninghub_submit_workflow(payload)})
                return
            if request_path == "/api/providers/fetch-models":
                if is_runninghub_request(payload):
                    # 用户点「拉取模型」= 显式要最新清单，强制重爬文档（约 25 秒）
                    self._send(200, runninghub_model_catalog(payload.get("provider_id"), payload.get("base_url"), force=True))
                    return
                if str(payload.get("protocol") or "").strip().lower() == "volcengine":
                    self._send(200, volcengine_fetch_models(payload))
                    return
                if str(payload.get("protocol") or "").strip().lower() == "openai":
                    self._send(200, openai_probe_payload(payload, "fetch"))
                    return
            if request_path == "/api/providers/test-connection" and is_runninghub_request(payload):
                self._send(200, runninghub_probe_payload(payload, "test"))
                return
            if request_path == "/api/providers/test-connection" and is_volcengine_request(payload):
                self._send(200, volcengine_probe_payload(payload, "test"))
                return
            if request_path == "/api/providers/test-connection" and str(payload.get("protocol") or "").strip().lower() == "openai":
                self._send(200, openai_probe_payload(payload, "test"))
                return
            if request_path == "/api/providers/probe-async" and str(payload.get("protocol") or "").strip().lower() == "openai":
                self._send(200, openai_probe_payload(payload, "probe"))
                return
            if request_path == "/api/providers/verify-base" and str(payload.get("protocol") or "").strip().lower() == "openai":
                self._send(200, openai_probe_payload(payload, "verify"))
                return
            if request_path == "/api/providers/probe-async" and is_runninghub_request(payload):
                self._send(200, runninghub_probe_payload(payload, "probe"))
                return
            if request_path == "/api/providers/probe-async" and is_volcengine_request(payload):
                self._send(200, volcengine_probe_payload(payload, "probe"))
                return
            if request_path == "/api/providers/verify-base" and is_runninghub_request(payload):
                self._send(200, runninghub_probe_payload(payload, "verify"))
                return
            if request_path == "/api/providers/verify-base" and is_volcengine_request(payload):
                self._send(200, volcengine_probe_payload(payload, "verify"))
                return
            if request_path == "/api/task-console-stop":
                self._send(200, task_console_stop(payload))
                return
            if request_path == "/api/canvas-image-tasks":
                task_id = "rhproxy_" + uuid.uuid4().hex
                set_task_state(task_id, {
                    "status": "running",
                    "persistent": True,
                    "backend": "runninghub-official",
                    "created_at": time.time(),
                    "canvas_title": str(payload.get("canvas_title") or _volcengine_canvas_title_for_output(payload.get("canvas_id"))).strip(),
                    "canvas_id": str(payload.get("canvas_id") or "").strip(),
                    # 控制台明细快照：平台/模型/模式/分辨率/数量
                    "model": str(payload.get("model") or ""),
                    "provider_id": str(payload.get("provider_id") or payload.get("engine") or ""),
                    "resolution": str(payload.get("resolution") or ""),
                    "ratio": str(payload.get("ratio") or payload.get("size") or ""),
                    "quality": str(payload.get("quality") or ""),
                    "count": payload.get("count") or payload.get("n") or 1,
                    "mode": "i2i" if (payload.get("reference_images") or payload.get("reference_image_urls") or payload.get("input_images")) else "t2i",
                    "node_id": str(payload.get("node_id") or "").strip(),
                    "node_title": str(payload.get("node_title") or "").strip(),
                }, persistent=True)
                threading.Thread(target=run_task, args=(task_id, payload), daemon=True).start()
                self._send(200, {"task_id": task_id})
                return
            if request_path == "/api/canvas-llm":
                self._send(200, submit_chat(payload))
                return
            if request_path == "/api/canvas-llm-stop":
                request_id = str(payload.get("request_id") or "").strip()
                self._send(200, {"ok": request_canvas_agent_stop(request_id), "request_id": request_id})
                return
            if request_path == "/api/canvas-agent-interaction":
                session_id = str(payload.get("session_id") or payload.get("agent_session_id") or "").strip()
                self._send(200, get_canvas_agent_interaction(session_id))
                return
            if request_path == "/api/canvas-agent-interaction-receipt":
                self._send(200, submit_canvas_agent_interaction_receipt(payload))
                return
            if request_path == "/api/canvas-agent-undo-batch":
                try:
                    self._send(200, _agent_tool_undo_batch(payload))
                except Exception as exc:
                    self._send(200, {"ok": False, "error": str(exc)[:300]})
                return
            if request_path == "/api/previz/pick-folder":
                self._send(200, {"path": pick_previz_folder()})
                return
            if request_path == "/api/canvas-agent-config":
                if "rules" in payload:
                    write_canvas_agent_rules(payload.get("rules") or "")
                if "vision" in payload and isinstance(payload.get("vision"), dict):
                    save_canvas_agent_vision_config(payload["vision"])
                self._send(200, canvas_agent_config_payload())
                return
            if request_path == "/api/canvas-agent-skill":
                name = str(payload.get("name") or "").strip()
                if bool(payload.get("delete")):
                    result = delete_canvas_agent_skill(name)
                    self._send(200, {"ok": True, **result, "skills": list_canvas_agent_skills()})
                    return
                skill = write_canvas_agent_skill(name, payload.get("content") or "")
                self._send(200, {"ok": True, "skill": skill, "skills": list_canvas_agent_skills()})
                return
            if request_path == "/api/frontend-log":
                try:
                    append_log(LOG_FILE, "frontend-log " + json.dumps(payload, ensure_ascii=False)[:2000])
                except Exception as log_exc:
                    print("frontend-log write failed:", log_exc)
                self._send(200, {"ok": True})
                return
            if request_path == "/api/canvas-agent-history":
                canvas_id = str(payload.get("canvas_id") or "").strip()
                history_list = payload.get("history")
                if not isinstance(history_list, list):
                    raise RuntimeError("历史数据格式错误")
                saved_history = write_canvas_agent_history(canvas_id, history_list)
                sync_canvas_agent_history_index(canvas_id, saved_history, payload.get("canvas_title") or "")
                self._send(200, {"ok": True, "canvas_id": canvas_id, "history": saved_history})
                return
            if request_path == "/api/agent-key":
                key_name = str(payload.get("key_env") or AGENT_CONFIG.get("api_key_env") or "MYRIDTV_AGENT_API_KEY").strip()
                clear_requested = bool(payload.get("clear"))
                key_value = "" if clear_requested else str(payload.get("api_key") or "").strip()
                if not clear_requested and not key_value:
                    raise RuntimeError("请输入 Agent API Key")
                if clear_requested:
                    write_env_values({}, [key_name])
                else:
                    write_env_values({key_name: key_value})
                self._send(200, {"ok": True, "agent": agents_meta_payload()})
                return
            if request_path == "/api/agent-active":
                agent_id = str(payload.get("agent_id") or "").strip()
                section = APP_CONFIG.get("agent") or {}
                agents = section.get("agents") if isinstance(section.get("agents"), dict) else {}
                if agent_id not in agents:
                    raise ApiError(400, "未知 Agent: {}".format(agent_id))
                write_app_config(deep_merge(APP_CONFIG, {"agent": {"active_id": agent_id}}))
                self._send(200, {"ok": True, "agent": agents_meta_payload()})
                return
            if request_path == "/api/agent-models":
                self._send(200, fetch_agent_models(payload))
                return
            if request_path in ("/api/integrations/blender/push-frame", "/api/integrations/blender/push-snapshot"):
                self._send(200, append_blender_frame_to_canvas(payload))
                return
            if request_path == "/api/integrations/blender/push-batch":
                self._send(200, append_blender_batch_to_canvas(payload))
                return
            if request_path == "/api/integrations/blender/push-animation":
                self._send(200, append_blender_animation_to_canvas(payload))
                return
            if request_path == "/app-config":
                saved = write_app_config(payload)
                self._send(200, {"ok": True, "config": saved})
                return
            if workflow_route == "collection":
                created = create_workflow_record(payload.get("name"), payload.get("workflow"))
                self._send(200, {"ok": True, "name": created["name"], **created})
                return
            if workflow_route == "run":
                comfy_payload = dict(payload or {})
                comfy_payload.setdefault("canvas_id", str(canvas_id or "").strip())
                comfy_payload.setdefault("canvas_title", str((payload or {}).get("canvas_title") or _volcengine_canvas_title_for_output(canvas_id)).strip())
                self._send(200, run_comfy_workflow(workflow_name, comfy_payload))
                return
            if request_path == "/api/comfyui/jobs":
                try:
                    record = read_workflow_record(str(payload.get("workflow") or "").strip())
                    job = comfy_flow_service.submit_job(
                        record,
                        payload.get("overrides") if isinstance(payload.get("overrides"), dict) else {},
                        payload.get("modes") if isinstance(payload.get("modes"), dict) else {},
                        payload.get("prefs") if isinstance(payload.get("prefs"), dict) else {},
                        str(payload.get("client_id") or ""),
                    )
                    self._send(200, {"ok": True, **job.to_dict()})
                except ComfyCompileError as exc:
                    self._send(400, {"ok": False, "error": str(exc)})
                except Exception as exc:
                    self._send(500, {"ok": False, "error": "提交失败: {}".format(str(exc)[:200])})
                return
            if request_path.startswith("/api/comfyui/jobs/") and (
                request_path.endswith("/cancel") or request_path.endswith("/interrupt")
            ):
                job = comfy_flow_service.MANAGER.cancel(request_path.split("/")[-2])
                if not job:
                    self._send(404, {"ok": False, "error": "任务不存在或已过期"})
                    return
                self._send(200, {"ok": True, **job.to_dict()})
                return
            if request_path == "/api/comfyui/compile":
                # 只编译不执行：前端用它做节点清单预览与开关调试
                try:
                    record = read_workflow_record(str(payload.get("workflow") or "").strip())
                    workflow = record.get("workflow") if isinstance(record.get("workflow"), dict) else {}
                    object_info = comfy_flow_service.load_object_info()
                    prompt, report = compile_comfy_prompt(
                        workflow,
                        payload.get("overrides") if isinstance(payload.get("overrides"), dict) else {},
                        payload.get("modes") if isinstance(payload.get("modes"), dict) else {},
                        object_info,
                    )
                    nodes = describe_comfy_workflow(
                        workflow,
                        object_info,
                        payload.get("prefs") if isinstance(payload.get("prefs"), dict) else {},
                    )
                    self._send(200, {"ok": True, "prompt": prompt, "report": report, "nodes": nodes})
                except ComfyCompileError as exc:
                    self._send(400, {"ok": False, "error": str(exc)})
                return
            if request_path == "/api/comfyui/instances":
                saved_instances = write_comfy_instances(payload.get("instances"))
                self._send(200, {"ok": True, "instances": saved_instances})
                return
            if canvas_route == "collection":
                created = create_canvas_record(payload)
                self._send(200, {"ok": True, "canvas": created})
                return
            if canvas_route == "import":
                self._send(200, import_canvas_payload(payload))
                return
            if canvas_route == "meta":
                updated = update_canvas_meta(canvas_id, payload)
                self._send(200, {"ok": True, "canvas": updated})
                return
            if canvas_route == "touch":
                touched = touch_canvas_record(canvas_id)
                self._send(200, {"ok": True, "canvas": touched, "updated_at": touched.get("updated_at")})
                return
            if canvas_route == "restore":
                restored = restore_canvas_record(canvas_id)
                self._send(200, {"ok": True, "canvas": restored})
                return
            if request_path == "/api/open-folder":
                url = str(payload.get("url") or "").strip()
                name = str(payload.get("name") or "").strip()
                local_path = str(payload.get("local_path") or payload.get("localPath") or "").strip()
                target = resolve_open_folder_target(url, name, local_path)
                opened = False
                if target.exists() and target.is_file():
                    import subprocess
                    subprocess.Popen(["explorer", "/select,", str(target.resolve())])
                    opened = True
                elif target.exists() and target.is_dir():
                    import subprocess
                    subprocess.Popen(["explorer", str(target.resolve())])
                    opened = True
                elif target.parent.exists():
                    import subprocess
                    subprocess.Popen(["explorer", "/select,", str(target.resolve())])
                    opened = True
                self._send(200, {"ok": True, "opened": opened, "path": str(target)})
                return
            if request_path.startswith("/api/"):
                if self._forward_upstream("POST", self.path, raw_body):
                    return
            self._send(404, {"detail": "not found"})
        except CanvasConflictError as exc:
            self._send(exc.status, {"detail": exc.detail, "canvas": exc.current_canvas})
        except ApiError as exc:
            self._send(exc.status, {"detail": exc.detail, **exc.payload})
        except Exception as exc:
            append_log(LOG_FILE, f"{self.command} {self.path} failed: {exc}\n{traceback.format_exc()}")
            self._send(502, {"detail": str(exc)})

    def do_PATCH(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw_body = self.rfile.read(length)
            payload = json.loads(raw_body.decode("utf-8") or "{}") if raw_body else {}
            request_path = self.path.split("?", 1)[0]
            if request_path.startswith("/api/asset-library/categories/"):
                category_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
                self._send(200, update_asset_category_record(category_id, payload))
                return
            if request_path.startswith("/api/asset-library/items/"):
                item_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
                self._send(200, update_asset_item_record(item_id, payload))
                return
            if request_path.startswith("/api/asset-library/libraries/"):
                library_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
                self._send(200, update_asset_library_record(library_id, payload))
                return
            if request_path.startswith("/api/prompt-libraries/categories/"):
                category_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
                self._send(200, update_prompt_category_record(category_id, payload))
                return
            if request_path.startswith("/api/prompt-libraries/items/"):
                item_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
                self._send(200, update_prompt_item_record(item_id, payload))
                return
            if request_path.startswith("/api/prompt-libraries/"):
                library_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
                self._send(200, update_prompt_library_record(library_id, payload))
                return
            if request_path.startswith("/api/"):
                if self._forward_upstream("PATCH", self.path, raw_body):
                    return
            self._send(404, {"detail": "not found"})
        except ApiError as exc:
            self._send(exc.status, {"detail": exc.detail, **exc.payload})
        except Exception as exc:
            append_log(LOG_FILE, f"{self.command} {self.path} failed: {exc}\n{traceback.format_exc()}")
            self._send(502, {"detail": str(exc)})

    def do_PUT(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw_body = self.rfile.read(length)
            payload = json.loads(raw_body.decode("utf-8") or "{}") if raw_body else {}
            request_path = self.path.split("?", 1)[0]
            canvas_route, canvas_id = parse_canvas_route(request_path)
            workflow_route, workflow_name = parse_workflow_route(request_path)
            if request_path == "/api/providers":
                providers = write_api_providers(payload)
                self._send(200, {"ok": True, "providers": providers})
                return
            if request_path.startswith("/api/runninghub/workflows/"):
                workflow_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
                saved = save_runninghub_workflow_config(workflow_id, payload)
                self._send(200, {"success": True, "workflow": saved})
                return
            if request_path == "/api/comfyui/instances":
                saved_instances = write_comfy_instances(payload.get("instances"))
                self._send(200, {"ok": True, "instances": saved_instances})
                return
            if workflow_route == "config":
                saved = save_workflow_config(workflow_name, payload)
                self._send(200, {"ok": True, **saved})
                return
            if canvas_route == "item":
                saved = save_canvas_record(canvas_id, payload)
                self._send(200, {"ok": True, "canvas": saved})
                return
            if request_path.startswith("/api/"):
                if self._forward_upstream("PUT", self.path, raw_body):
                    return
            self._send(404, {"detail": "not found"})
        except CanvasConflictError as exc:
            self._send(exc.status, {"detail": exc.detail, "canvas": exc.current_canvas})
        except ApiError as exc:
            self._send(exc.status, {"detail": exc.detail, **exc.payload})
        except Exception as exc:
            append_log(LOG_FILE, f"{self.command} {self.path} failed: {exc}\n{traceback.format_exc()}")
            self._send(502, {"detail": str(exc)})

    def do_DELETE(self):
        request_path = self.path.split("?", 1)[0]
        canvas_route, canvas_id = parse_canvas_route(request_path)
        workflow_route, workflow_name = parse_workflow_route(request_path)
        try:
            if request_path.startswith("/api/asset-library/categories/"):
                category_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
                self._send(200, delete_asset_category_record(category_id))
                return
            if request_path.startswith("/api/asset-library/items/"):
                item_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
                self._send(200, delete_asset_item_record(item_id))
                return
            if request_path.startswith("/api/asset-library/libraries/"):
                library_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
                self._send(200, delete_asset_library_record(library_id))
                return
            if request_path.startswith("/api/prompt-libraries/categories/"):
                category_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
                self._send(200, delete_prompt_category_record(category_id))
                return
            if request_path.startswith("/api/prompt-libraries/items/"):
                item_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
                self._send(200, delete_prompt_item_record(item_id))
                return
            if request_path.startswith("/api/prompt-libraries/"):
                library_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
                self._send(200, delete_prompt_library_record(library_id))
                return
            if workflow_route == "item":
                self._send(200, delete_workflow_record(workflow_name))
                return
            if canvas_route == "item":
                deleted = trash_canvas_record(canvas_id)
                self._send(200, {"ok": True, "canvas": deleted})
                return
            if canvas_route == "trashPurgeAll":
                self._send(200, purge_all_trash_records())
                return
            if canvas_route == "purge":
                self._send(200, purge_canvas_record(canvas_id))
                return
            if request_path.startswith("/api/"):
                if self._forward_upstream("DELETE", self.path):
                    return
            self._send(404, {"detail": "not found"})
        except ApiError as exc:
            self._send(exc.status, {"detail": exc.detail, **exc.payload})
        except Exception as exc:
            append_log(LOG_FILE, f"{self.command} {self.path} failed: {exc}")
            self._send(502, {"detail": str(exc)})

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    append_log(LOG_FILE, f"proxy starting pid={os.getpid()} version={STATIC_VERSION} app_base={APP_BASE} port={PORT}")
    patch_static_versions_once()
    threading.Thread(target=patch_static_versions_loop, daemon=True).start()
    # 启动窗口样式自动修复
    _start_window_fix()
    # 启动 Canvas MCP 端点（内置于主服务）
    print(f"[canvas-mcp] embedded at http://127.0.0.1:{PORT}/mcp")
    ThreadingHTTPServer((str(PROXY_CONFIG.get("host") or "127.0.0.1"), PORT), Handler).serve_forever()
