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
import ssl
import subprocess
import sys
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
def _portable_user_data_dir(app_dir):
    """便携模式（仿 ComfyUI 的 user 目录）：安装目录下存在 user_data\\ 或 .portable 标记时，
    这份安装就用自己的数据目录，多份安装互不干扰；默认仍走 %APPDATA%\\MyridTV（现有安装行为不变）。"""
    try:
        if (app_dir / ".portable").exists():
            return app_dir / "user_data"
        candidate = app_dir / "user_data"
        if candidate.is_dir():
            return candidate
    except Exception:
        pass
    return None

_user_data_env = os.environ.get("MYRIDTV_USER_DATA_DIR")
_portable_user_data = None if _user_data_env else _portable_user_data_dir(APP_DIR)
if _user_data_env:
    USER_DATA_DIR = Path(_user_data_env)
elif _portable_user_data:
    USER_DATA_DIR = _portable_user_data
else:
    USER_DATA_DIR = Path(os.environ.get("APPDATA", str(APP_DIR))) / "MyridTV"
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
BLENDER_BIN = os.environ.get("MYRIDTV_BLENDER_BIN") or r"D:\blender\blender-5.0.0-windows-x64\blender.exe"
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


def write_static_app_config(raw):
    """把生效配置镜像到 _internal/static/app_config.json —— 前端启动时读的就是这一份。

    安装脚本首次只把 app_config.template.json 复制过去，里面的 proxy 端口写死 3107；
    若本安装因端口冲突换到了别的端口（多份安装共存），不镜像就会让前端把请求发去
    3107 上的另一个实例（表现为看到别的安装的 Agent 设置 / 对话历史 / 控制台记录）。
    """
    try:
        static_config = ROOT / "static" / "app_config.json"
        static_config.parent.mkdir(parents=True, exist_ok=True)
        static_config.write_text(raw + "\n", encoding="utf-8")
    except Exception as exc:
        try:
            append_log(LOG_FILE, f"static app_config sync failed: {exc}")
        except Exception:
            pass


def write_app_config(config):
    global APP_CONFIG, SERVER_CONFIG, PROXY_CONFIG, AGENT_CONFIG, RUNNINGHUB_CONFIG, PATHS_CONFIG, ENV_FILE, APP_BASE, PORT, LOG_FILE
    merged = deep_merge(DEFAULT_CONFIG, config if isinstance(config, dict) else {})
    merged["agent"] = normalize_agent_section(merged.get("agent"))
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(merged, ensure_ascii=False, indent=2)
    CONFIG_FILE.write_text(raw + "\n", encoding="utf-8")
    write_static_app_config(raw)
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
# 启动时把生效配置镜像到 _internal/static/app_config.json（前端读这份定 API 基址，
# 端口冲突换端口后必须同步，否则前端会打到 3107 上的另一个实例）——见 write_static_app_config
write_static_app_config(json.dumps(APP_CONFIG, ensure_ascii=False, indent=2))
TASKS = {}
TASKS_LOCK = threading.Lock()
PERSISTENT_TASKS_FILE = USER_DATA_DIR / "data" / "canvas_tasks.json"
STATIC_VERSION = "2026.09.23.previzcomposition31"
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
    return myridtv_agent_tasks._agent_task_log(category, message)

def _agent_mark_task_failed(task, turn, exc):
    return myridtv_agent_tasks._agent_mark_task_failed(task, turn, exc)

def _agent_task_for_payload(payload):
    return myridtv_agent_tasks._agent_task_for_payload(payload)

def _agent_save_tasks():
    return myridtv_agent_tasks._agent_save_tasks()

def _agent_attach_runtime_result(result, task, turn=None, validation=None):
    return myridtv_agent_tasks._agent_attach_runtime_result(result, task, turn, validation)


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
    ROOT / "static" / "smart-canvas.html": ["/static/css/smart-canvas.css", "/static/js/smart-canvas.js", "/static/js/canvas-node-registry.js", "/static/js/canvas-draft-store.js", "/static/js/canvas-overlay-registry.js", "/static/js/canvas-viewport-engine.js", "/static/js/canvas-render-scheduler.js", "/static/js/canvas-comfy-job-engine.js", "/static/js/canvas-agent-history-store.js", "/static/js/canvas-artifact-model.js", "/static/js/canvas-artifact-view.js", "/static/js/canvas-agent-message-render.js", "/static/js/canvas-rh-controls.js", "/static/js/canvas-comfy-controls.js", "/static/js/canvas-param-controls.js", "/static/js/canvas-spec-controls.js", "/static/js/canvas-interaction-observer.js", "/static/js/canvas-interaction-machine.js", "/static/js/i18n.js"],
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
                # 兼容两种 URL 形态：/x.css?v= 与 /x.css?cb=xxx&v= （后者曾导致版本号永远刷不到）
                pattern = re.compile(rf"({re.escape(url)}\?(?:[^\"'<>\s]*&)?v=)[^\"'<>\s]+")
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
    return myridtv_env.read_env_values()


def write_env_values(updates=None, removals=None):
    return myridtv_env.write_env_values(updates=updates, removals=removals)


def read_env_balance_key():
    return myridtv_env.read_env_balance_key()


def read_env_key():
    return myridtv_env.read_env_key()


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
    return myridtv_env.provider_key_env_name(provider_id)


def provider_wallet_key_env_name(provider_id):
    return myridtv_env.provider_wallet_key_env_name(provider_id)


def read_api_providers():
    return myridtv_provider.read_api_providers()

def write_api_providers(providers):
    return myridtv_provider.write_api_providers(providers)

def write_canvas_agent_rules(content):
    return myridtv_agent.write_canvas_agent_rules(content)

def list_canvas_agent_skills():
    return myridtv_agent.list_canvas_agent_skills()

def read_canvas_agent_skill(name):
    return myridtv_agent.read_canvas_agent_skill(name)

def write_canvas_agent_skill(name, content):
    return myridtv_agent.write_canvas_agent_skill(name, content)

def delete_canvas_agent_skill(name):
    return myridtv_agent.delete_canvas_agent_skill(name)

def _agent_has_flow_skill(payload):
    return myridtv_agent._agent_has_flow_skill(payload)

def canvas_agent_augmented_system_prompt(payload):
    return myridtv_agent.canvas_agent_augmented_system_prompt(payload)

def canvas_agent_config_payload(include_rules=True):
    return myridtv_agent.canvas_agent_config_payload(include_rules)

def read_canvas_agent_history(canvas_id=""):
    return myridtv_agent.read_canvas_agent_history(canvas_id)

def write_canvas_agent_history(canvas_id="", history_list=None):
    return myridtv_agent.write_canvas_agent_history(canvas_id, history_list)

def prune_canvas_agent_history_files(canvas_id):
    return myridtv_agent.prune_canvas_agent_history_files(canvas_id)

def read_canvas_agent_history_index():
    return myridtv_agent.read_canvas_agent_history_index()

def sync_canvas_agent_history_index(canvas_id="", history_list=None, canvas_title=""):
    return myridtv_agent.sync_canvas_agent_history_index(canvas_id, history_list, canvas_title)

_RH_TLS_CTX_CACHE = {}


import myridtv_http
import myridtv_env
import myridtv_provider
import myridtv_agent
import myridtv_canvas_store
import myridtv_task_state
import myridtv_media_localize
import myridtv_libraries
import myridtv_codex
import myridtv_agent_tools
import myridtv_agent_state
import myridtv_agent_guard
import myridtv_agent_artifact
import myridtv_agent_batch
import myridtv_agent_short_drama
import myridtv_agent_stop
import myridtv_agent_guidance
import myridtv_agent_tasks
import myridtv_agent_submit
import myridtv_blender_previz
import myridtv_comfy
import myridtv_runninghub
import myridtv_rh_catalog
import myridtv_volcengine

myridtv_http.configure(lambda: runninghub_api_base())

myridtv_env.configure(lambda: ENV_FILE, lambda: RUNNINGHUB_CONFIG, lambda: AGENT_CONFIG)

myridtv_provider.configure(
    ROOT, USER_DATA_DIR,
    myridtv_env.read_env_values, myridtv_env.write_env_values,
    myridtv_env.provider_key_env_name, myridtv_env.provider_wallet_key_env_name,
    lambda b: is_volcengine_plan_base(b), lambda: volcengine_plan_chat_models(),
)

myridtv_agent.configure(
    CANVAS_AGENT_HISTORY_DIR, CANVAS_AGENT_HISTORY_INDEX_FILE,
    CANVAS_AGENT_RULES_FILE, CANVAS_AGENT_SKILLS_DIR,
    CANVAS_AGENT_MAX_INVOKED_SKILLS, CANVAS_AGENT_RULES_MAX_CHARS,
    CANVAS_AGENT_SKILL_MAX_CHARS, USER_DATA_DIR,
    lambda: LOG_FILE, lambda: agents_meta_payload(),
)

myridtv_canvas_store.configure(
    USER_DATA_DIR, APP_DIR, lambda: LOG_FILE,
    lambda canvas: resolve_canvas_asset_versions(canvas),
    lambda url_path: resolve_user_asset_path(url_path),
    lambda canvas_id: prune_canvas_agent_history_files(canvas_id),
)

myridtv_task_state.configure(
    TASKS, TASKS_LOCK, TASK_STORE, _agent_task_log,
)

myridtv_media_localize.configure(
    USER_DATA_DIR, ROOT, ASSETS_DIR, lambda: LOG_FILE,
    lambda: comfy_instance_base(),
    lambda tid: get_task_state(tid),
    lambda url: local_media_source_bytes(url),
    lambda name: output_asset_kind_for_name(name),
    lambda kind: output_asset_subdir_for_kind(kind),
    lambda *a, **k: request_multipart_json(*a, **k),
    lambda url_path: resolve_user_asset_path(url_path),
)

myridtv_comfy.configure(
    USER_DATA_DIR, COMFY_WORKFLOW_POLL_TIMEOUT_SECONDS, lambda: LOG_FILE,
    lambda: comfy_instances_file_path(),
    lambda: read_comfy_instances(),
    lambda instances: normalize_comfy_instances(instances),
    lambda kind='image', canvas_folder='': asset_output_media_dir(kind, canvas_folder),
    lambda local_name, kind='image', history=False, canvas_folder='': asset_output_url(local_name, kind, history, canvas_folder),
    lambda canvas_title='', canvas_id='': canvas_output_folder_name(canvas_title, canvas_id),
    lambda name: read_workflow_record(name),
)

myridtv_runninghub.configure(
    TASKS, TASKS_LOCK, lambda: LOG_FILE,
    lambda path: runninghub_api_url(path),
    lambda: runninghub_task_key(),
    lambda: runninghub_task_auth_headers(),
)

myridtv_rh_catalog.configure(
    lambda url: request_text(url),
    RUNNINGHUB_DEFAULT_IMAGE_MODELS,
    USER_DATA_DIR, lambda: LOG_FILE,
)

myridtv_volcengine.configure(
    lambda: LOG_FILE,
    lambda: volcengine_ark_api_key(),
    lambda source_url, service='auto': upload_cloud_media_direct(source_url, service=service),
    lambda task_id: _task_console_is_cancelled(task_id),
    lambda provider_id='', agent_entry=None: read_chat_key(provider_id, agent_entry),
)

myridtv_libraries.configure(
    USER_DATA_DIR, ROOT, lambda: LOG_FILE,
)


_cmm = myridtv_canvas_store._cmm  # 第4刀：try/except 定义随块入模块，块外守卫处用同一对象


def _rh_forced_tls_context(url=""):
    return myridtv_http._rh_forced_tls_context(url)


def request_json(url, method="GET", payload=None, headers=None, timeout=120):
    return myridtv_http.request_json(url, method=method, payload=payload, headers=headers, timeout=timeout)


def _rh_request_with_retry(url, method="GET", payload=None, headers=None, timeout=120, attempts=3):
    return myridtv_http._rh_request_with_retry(url, method=method, payload=payload, headers=headers, timeout=timeout, attempts=attempts)


def _is_transient_network_error(msg):
    return myridtv_http._is_transient_network_error(msg)


def request_multipart_json(url, fields=None, files=None, headers=None, timeout=120):
    return myridtv_http.request_multipart_json(url, fields=fields, files=files, headers=headers, timeout=timeout)


def request_multipart_text(url, fields=None, files=None, headers=None, timeout=180):
    return myridtv_http.request_multipart_text(url, fields=fields, files=files, headers=headers, timeout=timeout)

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

myridtv_codex.configure(
    ASSETS_DIR, CODEX_LOCAL_IMAGE_CACHE_DIR, lambda: LOG_FILE,
    lambda cid, nid: _agent_canvas_node_image_by_id(cid, nid),
    lambda msgs: _agent_sanitize_messages(msgs),
    {
        'USER_DATA_DIR': USER_DATA_DIR,
        'CODEX_APP_SERVER_BRIDGE': CODEX_APP_SERVER_BRIDGE,
        'CODEX_LOCAL_DEFAULT_MODEL': CODEX_LOCAL_DEFAULT_MODEL,
        'CODEX_LOCAL_DEFAULT_RUNTIME_MODEL': CODEX_LOCAL_DEFAULT_RUNTIME_MODEL,
        'CODEX_LOCAL_REPLY_DIR': CODEX_LOCAL_REPLY_DIR,
        'CODEX_LOCAL_WORKSPACE': CODEX_LOCAL_WORKSPACE,
        'CODEX_LOCAL_PERSIST_SESSIONS': CODEX_LOCAL_PERSIST_SESSIONS,
    },
    lambda: resolve_codex_executable(),
)


def persist_tasks_locked(task_id=None):
    return myridtv_task_state.persist_tasks_locked(task_id)

def set_task_state(task_id, state, persistent=False):
    return myridtv_task_state.set_task_state(task_id, state, persistent)

def update_task_state(task_id, **updates):
    return myridtv_task_state.update_task_state(task_id, **updates)

def get_task_state(task_id):
    return myridtv_task_state.get_task_state(task_id)

def load_persistent_tasks():
    return myridtv_task_state.load_persistent_tasks()

def recover_stale_tasks(source="MyridTV 后端重启"):
    return myridtv_task_state.recover_stale_tasks(source)

TASK_CONSOLE_CANCELLED = myridtv_task_state.TASK_CONSOLE_CANCELLED
TASK_CONSOLE_CANCELLED_LOCK = myridtv_task_state.TASK_CONSOLE_CANCELLED_LOCK
TASK_CONSOLE_COSTLY_MODEL_PAT = myridtv_task_state.TASK_CONSOLE_COSTLY_MODEL_PAT


def _task_console_kind(task_id, state):
    tid = str(task_id or "")
    backend = str(state.get("backend") or "")
    submit = state.get("submit") if isinstance(state.get("submit"), dict) else {}
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
    if state.get("rh_task_id") or backend == "runninghub-official":
        model = str(state.get("model") or "")
        if "/image-to-image" in model or state.get("mode") == "i2i":
            return "图生图"
        return "生图"
    if tid.startswith("rhproxy"):
        return "生图"
    if tid.startswith("volc"):
        return "视频"
    # 有 submit payload 但没有明确后端：webappId=RH 会员 API 生图（Agent 建的节点也走这里）
    if submit.get("webappId") or submit.get("prompt") is not None:
        return "生图"
    return "其他"


def _task_media_type(item):
    """任务级媒体归类：所有任务强制二分 image / video，保证明细加和=总数。
    判定源=kind 优先，工作流/未知类看产出条目；智能体任务(短片流水线)按视频计。"""
    kind = str(item.get("kind") or "")
    if kind == "视频":
        return "video"
    if kind in ("生图", "图生图"):
        return "image"
    if kind == "智能体任务":
        return "video"
    if (item.get("output_videos") or 0) > 0:
        return "video"
    return "image"


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


def _comfy_console_items():
    """把 ComfyUI 独立账本（comfy_flow_service.MANAGER）映射成控制台条目。

    只读合并，不写 TASKS、不改 ComfyJob 存储 —— ComfyUI 与主账本就是两套落盘。
    task_id 前缀 comfy: 供 /api/task-console-stop 反解出 job_id 走 MANAGER.cancel。
    """
    items = []
    try:
        jobs = comfy_flow_service.MANAGER.list_jobs(limit=500)
    except Exception as exc:
        append_log(LOG_FILE, f"comfy console merge failed: {exc}")
        return items
    status_map = {
        "queued": "queued",
        "running": "running",
        "done": "succeeded",
        "error": "failed",
        "cancelled": "cancelled",
        "gone": "interrupted",
    }
    for job in jobs:
        if not isinstance(job, dict):
            continue
        meta = job.get("meta") if isinstance(job.get("meta"), dict) else {}
        c_img_n, c_vid_n = _task_console_split_outputs(job.get("images") or [], job.get("videos") or [])
        out_count = len(job.get("images") or []) + len(job.get("videos") or [])
        created_ts = _task_console_ts(job.get("created_at"))
        finished_ts = _task_console_ts(job.get("finished_at"))
        duration = None
        if created_ts and finished_ts and finished_ts >= created_ts:
            duration = int(finished_ts - created_ts)
        items.append({
            "task_id": "comfy:" + str(job.get("job_id") or ""),
            "kind": "ComfyUI",
            "status": status_map.get(str(job.get("status") or ""), "unknown"),
            "platform": "ComfyUI",
            "model": str(job.get("workflow_name") or "—"),
            "resolution": "—",
            "count": max(1, out_count) if out_count else 1,
            "origin": str(meta.get("origin") or "ComfyUI 工作流"),
            "canvas_id": str(meta.get("canvas_id") or ""),
            "canvas_title": str(meta.get("canvas_title") or ""),
            "node_id": str(meta.get("node_id") or ""),
            "node_title": str(meta.get("node_title") or ""),
            "mode": str(meta.get("mode") or "comfy"),
            "ratio": "",
            "quality": "",
            "provider_task_id": str(job.get("prompt_id") or ""),
            "created_at": created_ts,
            "completed_at": finished_ts,
            "checked_at": _task_console_ts(job.get("finished_at") or job.get("started_at")),
            "duration": duration,
            "error": str(job.get("error") or "")[:2000],
            "outputs": out_count,
            "output_images": c_img_n,
            "output_videos": c_vid_n,
            "progress": job.get("progress"),
            "current_node": str(job.get("current_node_title") or job.get("current_node") or ""),
            "risks": [],
            "params": {
                "flat": meta.get("params_flat") if isinstance(meta.get("params_flat"), list) else [],
                "modes": meta.get("modes") if isinstance(meta.get("modes"), dict) else {},
                "node_titles": meta.get("node_titles") if isinstance(meta.get("node_titles"), dict) else {},
            },
        })
    return items


def _task_console_split_outputs(images, videos):
    """按条目真实 kind 拆分产出计数（blender/RH 会把视频塞进 images 列表，条目 kind 才可信）。"""
    img_n = vid_n = 0
    for item in list(images or []) + list(videos or []):
        kind = ""
        if isinstance(item, dict):
            kind = str(item.get("kind") or item.get("media_kind") or "").strip().lower()
            if not kind:
                url = str(item.get("url") or "")
                kind = "video" if re.search(r"\.(mp4|mov|webm|avi|mkv)(\?|$)", url, re.I) else ""
        elif isinstance(item, str):
            kind = "video" if re.search(r"\.(mp4|mov|webm|avi|mkv)(\?|$)", item, re.I) else ""
        if kind == "video":
            vid_n += 1
        else:
            img_n += 1
    return img_n, vid_n


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
        n_img, n_vid = _task_console_split_outputs(out_images, out_videos)
        created_ts = _task_console_ts(st.get("created_at"))
        completed_ts = _task_console_ts(st.get("completed_at"))
        checked_ts = _task_console_ts(st.get("checked_at"))
        duration = None
        if created_ts and completed_ts and completed_ts >= created_ts:
            duration = int(completed_ts - created_ts)
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
            "node_title": str(st.get("node_title") or ""),
            "mode": str(st.get("mode") or ("i2i" if (st.get("reference_images") or st.get("reference_image_urls")) else "t2i")),
            "ratio": str(st.get("ratio") or submit.get("ratio") or "").strip(),
            "quality": str(st.get("quality") or submit.get("quality") or "").strip(),
            "provider_task_id": str(st.get("provider_task_id") or st.get("rh_task_id") or ""),
            "created_at": created_ts,
            "completed_at": completed_ts,
            "checked_at": checked_ts,
            "duration": duration,
            "error": str(st.get("error") or st.get("last_error") or "")[:2000],
            "outputs": len(out_images) + len(out_videos),
            "output_images": n_img,
            "output_videos": n_vid,
            "risks": _task_console_risks(tid, st),
        })
    items.extend(_comfy_console_items())
    items.sort(key=lambda x: _task_console_ts(x.get("created_at")), reverse=True)
    # 统计：今日
    day_start = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, 0))
    today = [it for it in items if _task_console_ts(it.get("created_at")) >= day_start]
    today_ok = [it for it in today if it.get("status") == "succeeded"]
    today_fail = [it for it in today if it.get("status") == "failed"]
    model_calls = {}
    for it in today:
        key = it["platform"] + " / " + it["model"]
        entry = model_calls.setdefault(key, {"calls": 0, "failed": 0, "outputs": 0, "out_images": 0, "out_videos": 0})
        entry["calls"] += 1
        if it["status"] == "failed":
            entry["failed"] += 1
        entry["outputs"] += it["outputs"]
        entry["out_images"] += it.get("output_images") or 0
        entry["out_videos"] += it.get("output_videos") or 0
    running_items = [it for it in items if it["status"] == "running"]

    def _media_split(group):
        out = {"image": 0, "video": 0}
        for it in group:
            out[_task_media_type(it)] += 1
        return out

    def _media_failure_rate(group):
        out = {}
        for media in ("image", "video"):
            sub_total = [it for it in group if _task_media_type(it) == media]
            sub_fail = [it for it in sub_total if it["status"] == "failed"]
            out[media] = round(len(sub_fail) * 100.0 / len(sub_total), 1) if sub_total else 0.0
        return out

    stats = {
        "today_total": len(today),
        "today_total_media": _media_split(today),
        "today_success": len(today_ok),
        "today_success_media": _media_split(today_ok),
        "today_failed": len(today_fail),
        "today_failed_media": _media_split(today_fail),
        "today_failure_rate": round(len(today_fail) * 100.0 / len(today), 1) if today else 0.0,
        "today_failure_rate_media": _media_failure_rate(today),
        "today_outputs": sum(it["outputs"] for it in today_ok),
        "today_output_images": sum(it.get("output_images") or 0 for it in today_ok),
        "today_output_videos": sum(it.get("output_videos") or 0 for it in today_ok),
        "running": len(running_items),
        "running_media": _media_split(running_items),
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
    # ComfyUI 任务（comfy:<job_id>）走独立账本的 cancel，不查 TASKS
    comfy_ids = [str(t or "").strip() for t in task_ids if str(t or "").startswith("comfy:")]
    for cid in comfy_ids:
        job_id = cid.split(":", 1)[1]
        try:
            job = comfy_flow_service.MANAGER.cancel(job_id)
        except Exception:
            job = None
        if job:
            stopped.append(cid)
        else:
            missing.append(cid)
    task_ids = [t for t in task_ids if not str(t or "").startswith("comfy:")]
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


def comfy_instances_file_path():
    return myridtv_libraries.comfy_instances_file_path()

def workflow_file_candidates(name):
    return myridtv_libraries.workflow_file_candidates(name)

def workflow_title_from_name(name):
    return myridtv_libraries.workflow_title_from_name(name)

def read_asset_library():
    return myridtv_libraries.read_asset_library()

def add_asset_library_version(payload):
    return myridtv_libraries.add_asset_library_version(payload)

def resolve_canvas_asset_versions(canvas):
    return myridtv_libraries.resolve_canvas_asset_versions(canvas)

def add_asset_library_items(payload):
    return myridtv_libraries.add_asset_library_items(payload)

def create_asset_library_record(payload):
    return myridtv_libraries.create_asset_library_record(payload)

def update_asset_library_record(library_id, payload):
    return myridtv_libraries.update_asset_library_record(library_id, payload)

def delete_asset_library_record(library_id):
    return myridtv_libraries.delete_asset_library_record(library_id)

def create_asset_category_record(payload):
    return myridtv_libraries.create_asset_category_record(payload)

def update_asset_category_record(category_id, payload):
    return myridtv_libraries.update_asset_category_record(category_id, payload)

def delete_asset_category_record(category_id):
    return myridtv_libraries.delete_asset_category_record(category_id)

def update_asset_item_record(item_id, payload):
    return myridtv_libraries.update_asset_item_record(item_id, payload)

def delete_asset_item_record(item_id):
    return myridtv_libraries.delete_asset_item_record(item_id)

def delete_asset_items_record(payload):
    return myridtv_libraries.delete_asset_items_record(payload)

def move_asset_items_record(payload):
    return myridtv_libraries.move_asset_items_record(payload)

def crop_asset_items_record(payload):
    return myridtv_libraries.crop_asset_items_record(payload)

def read_prompt_libraries():
    return myridtv_libraries.read_prompt_libraries()

def create_prompt_library_record(payload):
    return myridtv_libraries.create_prompt_library_record(payload)

def update_prompt_library_record(library_id, payload):
    return myridtv_libraries.update_prompt_library_record(library_id, payload)

def delete_prompt_library_record(library_id):
    return myridtv_libraries.delete_prompt_library_record(library_id)

def create_prompt_category_record(payload):
    return myridtv_libraries.create_prompt_category_record(payload)

def update_prompt_category_record(category_id, payload):
    return myridtv_libraries.update_prompt_category_record(category_id, payload)

def delete_prompt_category_record(category_id):
    return myridtv_libraries.delete_prompt_category_record(category_id)

def create_prompt_item_record(payload):
    return myridtv_libraries.create_prompt_item_record(payload)

def update_prompt_item_record(item_id, payload):
    return myridtv_libraries.update_prompt_item_record(item_id, payload)

def delete_prompt_item_record(item_id):
    return myridtv_libraries.delete_prompt_item_record(item_id)

def delete_prompt_items_record(payload):
    return myridtv_libraries.delete_prompt_items_record(payload)

def read_comfy_instances():
    return myridtv_libraries.read_comfy_instances()

def normalize_comfy_instances(instances):
    return myridtv_libraries.normalize_comfy_instances(instances)

def list_workflow_records():
    return myridtv_libraries.list_workflow_records()

def find_workflow_files(name):
    return myridtv_libraries.find_workflow_files(name)

def read_workflow_record(name):
    return myridtv_libraries.read_workflow_record(name)

def build_local_config_payload():
    return myridtv_libraries.build_local_config_payload()

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

    edge = max(160, min(2048, int(max_edge or 640)))
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


def write_comfy_instances(instances):
    return myridtv_comfy.write_comfy_instances(instances)

def comfy_instance_base():
    return myridtv_comfy.comfy_instance_base()

def run_comfy_workflow(name, payload):
    return myridtv_comfy.run_comfy_workflow(name, payload)

def recent_comfy_outputs(payload=None):
    return myridtv_comfy.recent_comfy_outputs(payload)

def comfy_workflow_split_clusters(workflow):
    return myridtv_comfy.comfy_workflow_split_clusters(workflow)

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


def smart_canvas_path(canvas_id):
    return myridtv_canvas_store.smart_canvas_path(canvas_id)

def normalize_canvas_structure(canvas_id, data):
    return myridtv_canvas_store.normalize_canvas_structure(canvas_id, data)

def conversation_artifact_id(canvas_id, conversation_id, artifact_type="brainstorm"):
    return myridtv_canvas_store.conversation_artifact_id(canvas_id, conversation_id, artifact_type)

def artifact_section_id(conversation_id, section_type, section_title):
    return myridtv_canvas_store.artifact_section_id(conversation_id, section_type, section_title)

def artifact_item_id(section_id, item_title):
    return myridtv_canvas_store.artifact_item_id(section_id, item_title)

def infer_section_type(title="", explicit=""):
    return myridtv_canvas_store.infer_section_type(title, explicit)

def section_type_label(stype):
    return myridtv_canvas_store.section_type_label(stype)

def _merge_artifacts(*sources):
    return myridtv_canvas_store._merge_artifacts(*sources)

def route_artifact(artifact_type=None, role=None, tool_name=None, user_text=None, existing=None):
    return myridtv_canvas_store.route_artifact(artifact_type, role, tool_name, user_text, existing)

def _merge_node_tombstones(*sources):
    return myridtv_canvas_store._merge_node_tombstones(*sources)

def canvas_summary(canvas):
    return myridtv_canvas_store.canvas_summary(canvas)

def read_canvas_record(canvas_id, include_deleted=True):
    return myridtv_canvas_store.read_canvas_record(canvas_id, include_deleted)

def list_canvas_records(include_deleted=False):
    return myridtv_canvas_store.list_canvas_records(include_deleted)

def create_canvas_record(payload=None):
    return myridtv_canvas_store.create_canvas_record(payload)

def save_canvas_record(canvas_id, payload=None):
    return myridtv_canvas_store.save_canvas_record(canvas_id, payload)

def update_canvas_meta(canvas_id, patch=None):
    return myridtv_canvas_store.update_canvas_meta(canvas_id, patch)

def touch_canvas_record(canvas_id):
    return myridtv_canvas_store.touch_canvas_record(canvas_id)

def trash_canvas_record(canvas_id):
    return myridtv_canvas_store.trash_canvas_record(canvas_id)

def restore_canvas_record(canvas_id):
    return myridtv_canvas_store.restore_canvas_record(canvas_id)

def purge_canvas_record(canvas_id):
    return myridtv_canvas_store.purge_canvas_record(canvas_id)

def purge_all_trash_records():
    return myridtv_canvas_store.purge_all_trash_records()

def export_canvas_payload(canvas_id):
    return myridtv_canvas_store.export_canvas_payload(canvas_id)

def import_canvas_payload(payload):
    return myridtv_canvas_store.import_canvas_payload(payload)

def parse_canvas_route(request_path):
    return myridtv_canvas_store.parse_canvas_route(request_path)

CANVAS_AGENT_ROUTE_CONTEXT = myridtv_canvas_store.CANVAS_AGENT_ROUTE_CONTEXT
CANVAS_AGENT_CURRENT_PHASE = myridtv_canvas_store.CANVAS_AGENT_CURRENT_PHASE
CONVERSATION_CONTAINER_TYPES = myridtv_canvas_store.CONVERSATION_CONTAINER_TYPES
INDEPENDENT_DOC_TYPES = myridtv_canvas_store.INDEPENDENT_DOC_TYPES


def append_blender_frame_to_canvas(payload):
    return myridtv_blender_previz.append_blender_frame_to_canvas(payload)

def append_blender_batch_to_canvas(payload):
    return myridtv_blender_previz.append_blender_batch_to_canvas(payload)

def append_blender_animation_to_canvas(payload):
    return myridtv_blender_previz.append_blender_animation_to_canvas(payload)

def blender_connection_status(canvas_id=""):
    return myridtv_blender_previz.blender_connection_status(canvas_id)


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
            assets_root = ASSETS_DIR.resolve()
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


def _agent_select_configured_image_model(provider_id, requested_model="", refs=None):
    return myridtv_agent_state._agent_select_configured_image_model(provider_id, requested_model, refs)

def _agent_html_escape(text):
    return myridtv_agent_state._agent_html_escape(text)

def _agent_http(method, path, payload=None, timeout=30):
    return myridtv_agent_state._agent_http(method, path, payload, timeout)

def _agent_latest_canvas_id():
    return myridtv_agent_state._agent_latest_canvas_id()

def _agent_get_canvas(canvas_id=""):
    return myridtv_agent_state._agent_get_canvas(canvas_id)

def _agent_tool_get_state(args):
    return myridtv_agent_state._agent_tool_get_state(args)

def _agent_tool_search_nodes(args):
    return myridtv_agent_state._agent_tool_search_nodes(args)


def _agent_category_from_title(title):
    return myridtv_agent_state._agent_category_from_title(title)

def _agent_find_empty_position(canvas, x, y, w, h, step=36, category=None, node_type=None, text_len=0):
    return myridtv_agent_state._agent_find_empty_position(canvas, x, y, w, h, step, category, node_type, text_len)

def _agent_tool_create_text_node(args, session_id=""):
    return myridtv_agent_state._agent_tool_create_text_node(args, session_id)

def _agent_default_run_settings(args, preset=None):
    return myridtv_agent_state._agent_default_run_settings(args, preset)

def _agent_normalize_reference_items(refs):
    return myridtv_agent_state._agent_normalize_reference_items(refs)

def _agent_merge_payload_refs_into_tool_args(name, args, payload):
    return myridtv_agent_state._agent_merge_payload_refs_into_tool_args(name, args, payload)

def _agent_run_settings_for_storage(settings):
    return myridtv_agent_state._agent_run_settings_for_storage(settings)


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


def _agent_prepare_node_for_canvas(cid, canvas, node, origin, args=None):
    return myridtv_agent_artifact._agent_prepare_node_for_canvas(cid, canvas, node, origin, args)

def _agent_canvas_repo_upsert_node(cid, canvas, node, origin, args=None):
    return myridtv_agent_artifact._agent_canvas_repo_upsert_node(cid, canvas, node, origin, args)

def _agent_upsert_sidebar_artifact(cid, canvas, title="", content="", artifact_type="text",                                resource_id="", source_run_id="", source_event_id="",                                defer_save=False, conversation_id="", conversation_title="",                                section_type="", section_title="", item_title="",                                item_id="", metadata=None):
    return myridtv_agent_artifact._agent_upsert_sidebar_artifact(cid, canvas, title, content, artifact_type, resource_id, source_run_id, source_event_id, defer_save, conversation_id, conversation_title, section_type, section_title, item_title, item_id, metadata)

def _agent_link_artifact_node(cid, canvas, artifact_id, node_id):
    return myridtv_agent_artifact._agent_link_artifact_node(cid, canvas, artifact_id, node_id)


def _agent_batch_build_text_node(canvas, params):
    return myridtv_agent_batch._agent_batch_build_text_node(canvas, params)

def _agent_batch_build_generation_node(canvas, params, preset):
    return myridtv_agent_batch._agent_batch_build_generation_node(canvas, params, preset)

def _agent_tool_batch_operations(args, preset=None, session_id=""):
    return myridtv_agent_batch._agent_tool_batch_operations(args, preset, session_id)

def _agent_tool_undo_batch(args):
    return myridtv_agent_batch._agent_tool_undo_batch(args)

def _agent_tool_add_link(args):
    return myridtv_agent_batch._agent_tool_add_link(args)

def _agent_tool_delete_node(args):
    return myridtv_agent_batch._agent_tool_delete_node(args)


MODLENS_CACHE = {}
MODLENS_CACHE_DIR = USER_DATA_DIR / "data" / "modlens_cache"
MODLENS_CACHE_KEY_MAX = 64


myridtv_agent_tools.configure(
    MODLENS_CACHE, MODLENS_CACHE_DIR, MODLENS_CACHE_KEY_MAX,
    lambda canvas_id='': _agent_get_canvas(canvas_id),
    lambda url: _agent_local_path_for_url(url),
)

myridtv_agent_state.configure(
    CANVAS_AGENT_DEFAULT_PROVIDER,
    lambda: PORT,
    lambda model, refs=None: normalize_model(model, refs),
    lambda node_id, image_index=0: _agent_canvas_node_image_by_id(node_id, image_index),
    lambda *a, **k: _agent_canvas_repo_upsert_node(*a, **k),
    lambda *a, **k: _agent_link_artifact_node(*a, **k),
    lambda *a, **k: _agent_upsert_sidebar_artifact(*a, **k),
)

myridtv_agent_guard.configure(
    lambda tool_log: _agent_result_created_nodes(tool_log),
    lambda session_id="": _agent_take_pending_interaction(session_id),
)

myridtv_agent_artifact.configure(
    USER_DATA_DIR,
    lambda: LOG_FILE,
    _cmm,
)

myridtv_agent_batch.configure(
    lambda: LOG_FILE,
    lambda model, refs=None: normalize_model(model, refs),
    lambda url: _agent_local_path_for_url(url),
    lambda node_id, image_index=0: _agent_canvas_node_image_by_id(node_id, image_index),
)

myridtv_agent_short_drama.configure(
    lambda: LOG_FILE,
)
CANVAS_AGENT_ALLOW_TEXT_FALLBACK_NODES = myridtv_agent_short_drama.CANVAS_AGENT_ALLOW_TEXT_FALLBACK_NODES
AGENT_BATCH_DIR = myridtv_agent_artifact.AGENT_BATCH_DIR
AGENT_OP_TYPES = myridtv_agent_artifact.AGENT_OP_TYPES

def _agent_tool_analyze_image(args):
    return myridtv_agent_tools._agent_tool_analyze_image(args)

def _agent_tool_save_skill(args):
    return myridtv_agent_tools._agent_tool_save_skill(args)

def _agent_tool_list_skills(args):
    return myridtv_agent_tools._agent_tool_list_skills(args)

def _agent_tool_present_interaction(args, session_id=None):
    return myridtv_agent_tools._agent_tool_present_interaction(args, session_id)

def _agent_take_pending_interaction(session_id=""):
    return myridtv_agent_tools._agent_take_pending_interaction(session_id)

CANVAS_AGENT_INTERACTIONS = myridtv_agent_tools.CANVAS_AGENT_INTERACTIONS
CANVAS_AGENT_INTERACTIONS_LOCK = myridtv_agent_tools.CANVAS_AGENT_INTERACTIONS_LOCK
CANVAS_AGENT_CURRENT_SESSION = myridtv_agent_tools.CANVAS_AGENT_CURRENT_SESSION
CANVAS_AGENT_LOADED_SKILLS = myridtv_agent_tools.CANVAS_AGENT_LOADED_SKILLS
CANVAS_AGENT_TOOLS = myridtv_agent_tools.CANVAS_AGENT_TOOLS




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

myridtv_agent_stop.configure(
    CANVAS_AGENT_RECEIPTS,
    CANVAS_AGENT_RECEIPTS_LOCK,
)

myridtv_agent_submit.configure(
    lambda: LOG_FILE,
    {
        'request_chat_json_with_retry': lambda *a, **k: request_chat_json_with_retry(*a, **k),
        'resolve_chat_target': lambda *a, **k: resolve_chat_target(*a, **k),
        'payload_prefers_codex_local': lambda *a, **k: payload_prefers_codex_local(*a, **k),
        'normalize_chat_messages': lambda *a, **k: normalize_chat_messages(*a, **k),
        'canvas_agent_execute_tool': lambda *a, **k: canvas_agent_execute_tool(*a, **k),
        'canvas_agent_tools_schema': lambda *a, **k: canvas_agent_tools_schema(*a, **k),
        '_codex_bridge_session_record': lambda *a, **k: _codex_bridge_session_record(*a, **k),
        '_codex_bridge_store_session_record': lambda *a, **k: _codex_bridge_store_session_record(*a, **k),
        '_codex_bridge_clear_session_record': lambda *a, **k: _codex_bridge_clear_session_record(*a, **k),
    },
    {
        'CODEX_LOCAL_DEFAULT_MODEL': CODEX_LOCAL_DEFAULT_MODEL,
        'CODEX_LOCAL_PERSIST_SESSIONS': CODEX_LOCAL_PERSIST_SESSIONS,
        'CANVAS_AGENT_MAX_TOOL_TURNS': CANVAS_AGENT_MAX_TOOL_TURNS,
        'CANVAS_AGENT_MAX_INTERACTION_RETRIES': CANVAS_AGENT_MAX_INTERACTION_RETRIES,
        'CANVAS_AGENT_REASONING_EFFORT': CANVAS_AGENT_REASONING_EFFORT,
        '_canvas_agent_reasoning_effort': _canvas_agent_reasoning_effort,
    },
)

myridtv_blender_previz.configure(
    lambda *a, **k: save_blender_payload_asset(*a, **k),
    lambda: APP_BASE,
    lambda: LOG_FILE,
    lambda *a, **k: _previz_ratio_size(*a, **k),
    lambda *a, **k: _strip_llm_fenced_text(*a, **k),
    lambda *a, **k: request_chat_json_with_retry(*a, **k),
    lambda *a, **k: resolve_chat_target(*a, **k),
    ASSETS_DIR, BLENDER_BIN, PREVIZ_DIR, PREVIZ_FPS,
)

myridtv_agent_tasks.configure(
    TASKS, TASKS_LOCK,
    lambda: LOG_FILE,
)


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
    return myridtv_agent_guidance._agent_sanitize_messages(messages)

def _agent_inject_tool_guidance(messages, preset=None):
    return myridtv_agent_guidance._agent_inject_tool_guidance(messages, preset)

def _agent_append_system(messages, text):
    return myridtv_agent_guidance._agent_append_system(messages, text)

def _agent_reply_rules():
    return myridtv_agent_guidance._agent_reply_rules()

def _agent_brainstorm_guidance(brainstorm):
    return myridtv_agent_guidance._agent_brainstorm_guidance(brainstorm)

def _agent_candidate_interaction_guidance():
    return myridtv_agent_guidance._agent_candidate_interaction_guidance()


def _codex_bridge_attachment_files(payload):
    return myridtv_codex._codex_bridge_attachment_files(payload)

def _codex_bridge_prompt_text(payload, messages):
    return myridtv_codex._codex_bridge_prompt_text(payload, messages)

def _codex_bridge_compact_messages(messages, max_history=4, max_chars=700):
    return myridtv_codex._codex_bridge_compact_messages(messages, max_history, max_chars)

def _codex_bridge_protocol_instruction(tools, preset=None):
    return myridtv_codex._codex_bridge_protocol_instruction(tools, preset)

def _codex_bridge_extract_json(text):
    return myridtv_codex._codex_bridge_extract_json(text)

def _codex_bridge_normalize_tool_calls(payload):
    return myridtv_codex._codex_bridge_normalize_tool_calls(payload)

def _codex_bridge_request_wants_canvas_nodes(payload):
    return myridtv_codex._codex_bridge_request_wants_canvas_nodes(payload)

def _codex_bridge_default_generation_nodes(text, fallback_prompt=""):
    return myridtv_codex._codex_bridge_default_generation_nodes(text, fallback_prompt)

def _codex_bridge_extract_generation_nodes(text, fallback_prompt=""):
    return myridtv_codex._codex_bridge_extract_generation_nodes(text, fallback_prompt)

def _agent_result_created_nodes(tool_log):
    return myridtv_codex._agent_result_created_nodes(tool_log)

def _codex_bridge_cleanup_fallback_text(text):
    return myridtv_codex._codex_bridge_cleanup_fallback_text(text)

def _codex_bridge_should_reset_session(error_text, had_session=False):
    return myridtv_codex._codex_bridge_should_reset_session(error_text, had_session)



def _agent_has_present_interaction(tool_log):
    return myridtv_agent_guard._agent_has_present_interaction(tool_log)

def _agent_detect_interaction_violation(text):
    return myridtv_agent_guard._agent_detect_interaction_violation(text)

def _agent_interaction_correction_prompt(violation):
    return myridtv_agent_guard._agent_interaction_correction_prompt(violation)

def _agent_detected_batch_violation(messages, tool_log):
    return myridtv_agent_guard._agent_detected_batch_violation(messages, tool_log)

def _agent_batch_correction_prompt(violation):
    return myridtv_agent_guard._agent_batch_correction_prompt(violation)

def _build_canvas_agent_result(text, tool_log=None, raw=None, output_mode="", extra=None, session_id=""):
    return myridtv_agent_guard._build_canvas_agent_result(text, tool_log, raw, output_mode, extra, session_id)


def _run_codex_bridge_exec(prompt_text, model, attachment_files, session_id=""):
    return myridtv_codex._run_codex_bridge_exec(prompt_text, model, attachment_files, session_id)

def _run_codex_bridge_persistent(prompt_text, model, attachment_files, session_id=""):
    return myridtv_codex._run_codex_bridge_persistent(prompt_text, model, attachment_files, session_id)


def _agent_short_drama_mode_card_result(payload):
    return myridtv_agent_short_drama._agent_short_drama_mode_card_result(payload)

def _agent_latest_user_text(payload):
    return myridtv_agent_short_drama._agent_latest_user_text(payload)

def _agent_short_drama_param_card_result(payload):
    return myridtv_agent_short_drama._agent_short_drama_param_card_result(payload)

def _agent_short_drama_script_param_card_result(payload):
    return myridtv_agent_short_drama._agent_short_drama_script_param_card_result(payload)

def _agent_short_drama_script_board_result(payload):
    return myridtv_agent_short_drama._agent_short_drama_script_board_result(payload)

def _agent_short_drama_board_result(payload):
    return myridtv_agent_short_drama._agent_short_drama_board_result(payload)


def request_canvas_agent_stop(request_id):
    return myridtv_agent_stop.request_canvas_agent_stop(request_id)

def _canvas_agent_stop_requested(request_id):
    return myridtv_agent_stop._canvas_agent_stop_requested(request_id)

def _agent_detect_premature_creation(tool_calls, messages, tool_log):
    return myridtv_agent_stop._agent_detect_premature_creation(tool_calls, messages, tool_log)

def _agent_premature_creation_correction():
    return myridtv_agent_stop._agent_premature_creation_correction()


# 第16刀：STOP 单例归 myridtv_agent_stop，主侧写点走同对象别名
CANVAS_AGENT_STOP_REQUESTS = myridtv_agent_stop.CANVAS_AGENT_STOP_REQUESTS
CANVAS_AGENT_STOP_LOCK = myridtv_agent_stop.CANVAS_AGENT_STOP_LOCK

def submit_chat(payload):
    return myridtv_agent_submit.submit_chat(payload)


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
    # 精确约分（如 3840x2160 -> 16:9）；若结果不在 RH 白名单（如 2480x3312 -> 155:207），
    # 按宽高比误差最小匹配白名单比例，避免 size 非标准倍数时静默兜底成 16:9。
    divisor = math.gcd(width, height) or 1
    exact = f"{width // divisor}:{height // divisor}"
    if exact in RH_ALLOWED_ASPECT_RATIOS:
        return exact
    if width <= 0 or height <= 0:
        return ""
    ratio = width / height
    best = "16:9"
    best_err = float("inf")
    for cand in RH_ALLOWED_ASPECT_RATIOS:
        try:
            w, h = (int(p) for p in cand.split(":"))
        except ValueError:
            continue
        if w <= 0 or h <= 0:
            continue
        cand_ratio = w / h
        err = abs(cand_ratio - ratio)
        if err < best_err:
            best_err = err
            best = cand
    return best


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


def local_media_source_bytes(source_url):
    return myridtv_media_localize.local_media_source_bytes(source_url)

def asset_output_media_dir(kind="image", canvas_folder=""):
    return myridtv_media_localize.asset_output_media_dir(kind, canvas_folder)

def asset_output_url(local_name, kind="image", history=False, canvas_folder=""):
    return myridtv_media_localize.asset_output_url(local_name, kind, history, canvas_folder)

def resolve_open_folder_target(url, name="", local_path=""):
    return myridtv_media_localize.resolve_open_folder_target(url, name, local_path)

def generated_asset_extension(file_name="", content_type="", default_ext=".png"):
    return myridtv_media_localize.generated_asset_extension(file_name, content_type, default_ext)

def upload_kind_for_file(file_name="", content_type=""):
    return myridtv_media_localize.upload_kind_for_file(file_name, content_type)

def handle_ai_upload(raw_body, content_type):
    return myridtv_media_localize.handle_ai_upload(raw_body, content_type)

def handle_comfy_upload(raw_body, content_type):
    return myridtv_media_localize.handle_comfy_upload(raw_body, content_type)

def canvas_output_folder_name(canvas_title="", canvas_id=""):
    return myridtv_media_localize.canvas_output_folder_name(canvas_title, canvas_id)

def _canvas_task_localize_lock(task_id):
    return myridtv_media_localize._canvas_task_localize_lock(task_id)

def _canvas_task_already_localized(task_id):
    return myridtv_media_localize._canvas_task_already_localized(task_id)

def fallback_generated_media_item(source, kind="image", error=""):
    return myridtv_media_localize.fallback_generated_media_item(source, kind, error)

def move_output_asset_to_history(payload):
    return myridtv_media_localize.move_output_asset_to_history(payload)

def localize_generated_media_items(items, kind="image", canvas_title="", canvas_id="", node_title=""):
    return myridtv_media_localize.localize_generated_media_items(items, kind, canvas_title, canvas_id, node_title)

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
        # RH 旧版 /task/openapi/upload 的鉴权要求 apiKey 作为 multipart 表单字段一起提交
        # （官方 curl 示例里 apiKey 是 --form）。只带 Authorization: Bearer 会被拒：
        # {"code":-1,"msg":"apiKey is required"}。2026-09-16 修。
        fields={"fileType": "input", "apiKey": runninghub_task_key()},
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
    return myridtv_media_localize.volcengine_ark_api_key()

def volcengine_upload_asset(source_url):
    return myridtv_media_localize.volcengine_upload_asset(source_url)

def upload_cloud_media_direct(source_url, service="auto"):
    return myridtv_media_localize.upload_cloud_media_direct(source_url, service)

def volcengine_provider_config(provider_id="volcengine"):
    return myridtv_volcengine.volcengine_provider_config(provider_id)

def is_volcengine_canvas_video_payload(payload):
    return myridtv_volcengine.is_volcengine_canvas_video_payload(payload)

def volcengine_normalize_resolution(value):
    return myridtv_volcengine.volcengine_normalize_resolution(value)

def volcengine_normalize_ratio(value):
    return myridtv_volcengine.volcengine_normalize_ratio(value)

def volcengine_base_url(provider):
    return myridtv_volcengine.volcengine_base_url(provider)

def volcengine_extract_task_id(data):
    return myridtv_volcengine.volcengine_extract_task_id(data)

def volcengine_user_error_message(error):
    return myridtv_volcengine.volcengine_user_error_message(error)

def query_volcengine_video_task(provider_id, provider_task_id, localize=False, canvas_title="", canvas_id=""):
    return myridtv_volcengine.query_volcengine_video_task(provider_id, provider_task_id, localize, canvas_title, canvas_id)

def _volcengine_canvas_title_for_output(canvas_id):
    return myridtv_volcengine._volcengine_canvas_title_for_output(canvas_id)

def submit_volcengine_canvas_video_task(payload):
    return myridtv_volcengine.submit_volcengine_canvas_video_task(payload)

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
                progress = queried.get("progress")
                if progress is not None:
                    state = update_task_state(task_id, status="running", checked_at=time.time(), raw_status=status or "RUNNING", progress=progress)
                else:
                    state = update_task_state(task_id, status="running", checked_at=time.time(), raw_status=status or "RUNNING")
        except Exception as exc:
            state = update_task_state(task_id, status="running", checked_at=time.time(), last_error=str(exc))
    return state


def runninghub_query_task(task_id):
    return myridtv_runninghub.runninghub_query_task(task_id)

def _rh_sync_task_console_state(rh_task_id, queried):
    return myridtv_runninghub._rh_sync_task_console_state(rh_task_id, queried)

def runninghub_submit_workflow(payload):
    return myridtv_runninghub.runninghub_submit_workflow(payload)

def runninghub_submit_app(payload):
    return myridtv_runninghub.runninghub_submit_app(payload)

def runninghub_cached_workflow(workflow_id):
    return myridtv_runninghub.runninghub_cached_workflow(workflow_id)

def runninghub_cached_app_info(app_id):
    return myridtv_runninghub.runninghub_cached_app_info(app_id)

def runninghub_fetch_workflow_config(payload):
    return myridtv_runninghub.runninghub_fetch_workflow_config(payload)

def save_runninghub_workflow_config(workflow_id, payload):
    return myridtv_runninghub.save_runninghub_workflow_config(workflow_id, payload)

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
    return myridtv_rh_catalog.is_runninghub_request(payload)

def runninghub_model_catalog(provider_id="", base_url="", force=False):
    return myridtv_rh_catalog.runninghub_model_catalog(provider_id, base_url, force)

def runninghub_probe_payload(payload, action="test"):
    return myridtv_rh_catalog.runninghub_probe_payload(payload, action)

RUNNINGHUB_DEFAULT_IMAGE_MODELS = myridtv_rh_catalog._DEFAULT_IMAGE_MODELS  # 第9刀：列表仍被块外引用，别名同对象


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


# 火山「推理计划」plan 端点（.../api/plan/v3）是 OpenAI 兼容对话入口，不提供 /models 列表。
# 这里在后端固化该端点可用的对话模型清单，Agent 模型下拉直接可选，无需手动输入或在线拉取。
def is_volcengine_plan_base(base_url=""):
    return myridtv_volcengine.is_volcengine_plan_base(base_url)

def volcengine_plan_chat_models(extra=None):
    return myridtv_volcengine.volcengine_plan_chat_models(extra)

def volcengine_fetch_models(payload):
    return myridtv_volcengine.volcengine_fetch_models(payload)

def is_volcengine_request(payload):
    return myridtv_volcengine.is_volcengine_request(payload)

def openai_probe_payload(payload, action="test"):
    return myridtv_volcengine.openai_probe_payload(payload, action)

def volcengine_probe_payload(payload, action="test"):
    return myridtv_volcengine.volcengine_probe_payload(payload, action)

def submit_official(payload):
    key = read_env_balance_key()
    if not key:
        raise RuntimeError("未找到 RunningHub API Key，请在 API 设置填写「账户余额 API Key」（标准模型需企业级 Key）")
    refs = payload.get("reference_images") or []
    provider_id = str(payload.get("provider_id") or "runninghub").strip()
    if provider_id == "custom-api-3":
        provider_id = "runninghub"
    model = _agent_select_configured_image_model(provider_id, payload.get("model"), refs)
    endpoint = f"{runninghub_api_base()}/openapi/v2/{model}"
    body = build_official_body(payload, model, refs)
    data = _rh_request_with_retry(endpoint, "POST", body, {"Authorization": f"Bearer {key}"}, timeout=120)
    task_id = data.get("taskId") or ""
    if not task_id:
        if str(data.get("errorCode") or "") == "1014":
            raise RuntimeError(
                "标准模型 API 需要企业级 Key：请在 API 设置把企业级 Key 填入「账户余额 API Key」"
                f"（当前错误：{str(data.get('errorMessage') or '')[:80]}）")
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
    return myridtv_volcengine.submit_volcengine_agent_task(payload)

def poll_volcengine_agent_task(local_task_id):
    return myridtv_volcengine.poll_volcengine_agent_task(local_task_id)

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


def _strip_llm_fenced_text(text):
    text = str(text or "").strip()
    fence = re.match(r"^```(?:\w+)?\s*([\s\S]*?)\s*```$", text)
    if fence:
        text = fence.group(1).strip()
    return text.strip()


def run_blender_previz(payload):
    return myridtv_blender_previz.run_blender_previz(payload)


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
            raw = Path(target).read_bytes()
            range_header = self.headers.get("Range", "")
            if range_header.startswith("bytes=") and "," not in range_header:
                start_text, sep, end_text = range_header[6:].strip().partition("-")
                if sep:
                    try:
                        if start_text:
                            start = int(start_text)
                            end = int(end_text) if end_text else len(raw) - 1
                        else:
                            suffix = int(end_text)
                            start, end = max(0, len(raw) - suffix), len(raw) - 1
                        if start < 0 or start >= len(raw) or end < start:
                            self.send_response(416)
                            self.send_header("Content-Range", f"bytes */{len(raw)}")
                            self.send_header("Accept-Ranges", "bytes")
                            self.send_header("Content-Length", "0")
                            self.end_headers()
                            return True
                        end = min(end, len(raw) - 1)
                        chunk = raw[start:end + 1]
                        self.send_response(206)
                        self.send_header("Content-Type", content_type)
                        self.send_header("Content-Range", f"bytes {start}-{end}/{len(raw)}")
                        self.send_header("Accept-Ranges", "bytes")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.send_header("Content-Length", str(len(chunk)))
                        self.end_headers()
                        if self.command != "HEAD":
                            self.wfile.write(chunk)
                        return True
                    except ValueError:
                        pass
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(raw)
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
                _queried = runninghub_query_task(task_id)
                _rh_sync_task_console_state(task_id, _queried)
                self._send(200, {"success": True, "data": _queried})
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
                    # "workflow" 与 "data" 并存：旧前端读 data.workflow，新前端读 data.data。
                    # 只给 data 会让旧前端拿不到配置→回云端重抓→把用户勾好的暴露字段清成 enabled:false。
                    self._send(200, {"ok": True, "data": cached, "workflow": cached})
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
            if request_path == "/api/comfyui/queue":
                # 排队视图：正在跑的 + 还在排的（含位次），供前端显示「排队中 · 第 N 位」
                self._send(200, comfy_flow_service.MANAGER.queue_snapshot())
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
            if request_path == "/api/canvas-agent-config":
                if "rules" in payload:
                    write_canvas_agent_rules(payload.get("rules") or "")
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
                        meta={
                            "canvas_id": str(payload.get("canvas_id") or "").strip(),
                            "canvas_title": str(payload.get("canvas_title") or "").strip(),
                            "node_id": str(payload.get("node_id") or "").strip(),
                            "node_title": str(payload.get("node_title") or "").strip(),
                            "origin": str(payload.get("origin") or "comfyui").strip(),
                        },
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
