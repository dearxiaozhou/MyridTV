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
STATIC_VERSION = "2026.09.23.previzcomposition43"
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
    ROOT / "static" / "smart-canvas.html": ["/static/css/smart-canvas.css", "/static/js/smart-canvas.js", "/static/js/canvas-node-registry.js", "/static/js/canvas-draft-store.js", "/static/js/canvas-overlay-registry.js", "/static/js/canvas-viewport-engine.js", "/static/js/canvas-render-scheduler.js", "/static/js/canvas-comfy-job-engine.js", "/static/js/canvas-agent-history-store.js", "/static/js/canvas-artifact-model.js", "/static/js/canvas-artifact-view.js", "/static/js/canvas-agent-message-render.js", "/static/js/canvas-rh-controls.js", "/static/js/canvas-comfy-controls.js", "/static/js/canvas-param-controls.js", "/static/js/canvas-prompt-library-picker.js", "/static/js/canvas-unified-picker.js", "/static/js/canvas-spec-controls.js", "/static/js/canvas-interaction-observer.js", "/static/js/canvas-interaction-machine.js", "/static/js/i18n.js"],
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
import myridtv_chat
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
import myridtv_agent_generation
import myridtv_runninghub_build
import myridtv_task_console
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



myridtv_codex.configure(
    ASSETS_DIR, CODEX_LOCAL_IMAGE_CACHE_DIR, lambda: LOG_FILE,
    lambda cid, nid: _agent_canvas_node_image_by_id(cid, nid),
    lambda msgs: _agent_sanitize_messages(msgs),
    {
        'USER_DATA_DIR': USER_DATA_DIR,
        'CODEX_APP_SERVER_BRIDGE': myridtv_codex.CODEX_APP_SERVER_BRIDGE,
        'CODEX_APP_SERVER_PORT_FILE': CODEX_APP_SERVER_PORT_FILE,
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



def task_console_snapshot():
    return myridtv_task_console.task_console_snapshot()

def task_console_stop(payload):
    return myridtv_task_console.task_console_stop(payload)

def _task_console_is_cancelled(task_id):
    return myridtv_task_console._task_console_is_cancelled(task_id)


# 24刀：Cancelled 类归 task_console，主侧 raise 点薄别名同对象
_TaskConsoleCancelled = myridtv_task_console._TaskConsoleCancelled

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


def _agent_canvas_node_image_by_id(node_id, image_index=0):
    return myridtv_chat._agent_canvas_node_image_by_id(node_id, image_index)

def normalize_chat_messages(payload):
    return myridtv_chat.normalize_chat_messages(payload)

def resolve_codex_executable():
    return myridtv_chat.resolve_codex_executable()

def payload_prefers_codex_local(payload):
    return myridtv_chat.payload_prefers_codex_local(payload)

def resolve_chat_target(payload):
    return myridtv_chat.resolve_chat_target(payload)

def fetch_agent_models(payload=None):
    return myridtv_chat.fetch_agent_models(payload)

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
    return myridtv_agent_generation._agent_tool_create_generation_node(args, preset)

def _agent_local_path_for_url(url):
    return myridtv_agent_generation._agent_local_path_for_url(url)

def _agent_tool_generate_images(args, preset=None):
    return myridtv_agent_generation._agent_tool_generate_images(args, preset)

def _agent_tool_check_generation(args):
    return myridtv_agent_generation._agent_tool_check_generation(args)

def _agent_tool_update_node(args):
    return myridtv_agent_generation._agent_tool_update_node(args)


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

myridtv_agent_generation.configure(
    ASSETS_DIR,
    lambda: LOG_FILE,
    lambda *a, **k: localize_canvas_task_result(*a, **k),
)

myridtv_runninghub_build.configure(
    lambda *a, **k: runninghub_upload_binary_media(*a, **k),
    RUNNINGHUB_ALLOWED_RESOLUTIONS,
    RUNNINGHUB_DEFAULT_IMAGE_MODELS,
)

myridtv_task_console.configure(
    TASKS, TASKS_LOCK, TASK_STORE,
    lambda *a, **k: recover_stale_tasks(*a, **k),
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

myridtv_chat.configure(
    {
        'USER_DATA_DIR': lambda: USER_DATA_DIR,
        'ASSETS_DIR': lambda: ASSETS_DIR,
        'LOG_FILE': lambda: LOG_FILE,
        'CODEX_LOCAL_UPSTREAMS': lambda: CODEX_LOCAL_UPSTREAMS,
        'CODEX_LOCAL_DEFAULT_MODEL': lambda: CODEX_LOCAL_DEFAULT_MODEL,
    },
    {
        'read_chat_key': lambda *a, **k: read_chat_key(*a, **k),
        'resolve_agent_entry': lambda *a, **k: resolve_agent_entry(*a, **k),
    },
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


def normalize_model(model, refs):
    return myridtv_runninghub_build.normalize_model(model, refs)

def build_official_body(payload, model, refs):
    return myridtv_runninghub_build.build_official_body(payload, model, refs)

def resolve_legacy_generate_payload(payload, providers=None):
    return myridtv_runninghub_build.resolve_legacy_generate_payload(payload, providers)

def runninghub_task_key():
    return myridtv_runninghub_build.runninghub_task_key()

def runninghub_task_auth_headers():
    return myridtv_runninghub_build.runninghub_task_auth_headers()


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

import myridtv_mcp

# 26刀：MCP 域住 myridtv_mcp；Handler 消费的表与分发器走引用别名。
# MCP_BASE 维持 import 期定值语义（迁移前后一致）。
MCP_BASE = str(PROXY_CONFIG.get("base_url") or f"http://127.0.0.1:{PORT}").rstrip("/")
myridtv_mcp.configure(MCP_BASE)
MCP_TOOLS = myridtv_mcp.MCP_TOOLS
def _mcp_handle(name, args):
    return myridtv_mcp._mcp_handle(name, args)


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

    def _get_health(self):
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

    def _get_api_task_console(self):
        self._send(200, task_console_snapshot())
        return

    def _get_app_config(self):
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

    def _get_api_canvas_agent_history(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query or "", keep_blank_values=True)
        canvas_id = (query.get("canvas_id") or [""])[0]
        self._send(200, {"ok": True, "canvas_id": canvas_id, "history": read_canvas_agent_history(canvas_id)})
        return

    def _get_api_canvas_agent_history_index(self):
        self._send(200, {"ok": True, "entries": read_canvas_agent_history_index()})
        return

    def _get_api_canvas_agent_tasks(self):
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

    def _get_api_canvas_agent_config(self):
        self._send(200, canvas_agent_config_payload())
        return

    def _get_api_canvas_agent_skill(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query or "", keep_blank_values=True)
        name = (query.get("name") or [""])[0]
        skill = read_canvas_agent_skill(name)
        self._send(200, {"ok": True, "skill": skill})
        return

    def _get_api_integrations_blender_status(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query or "", keep_blank_values=True)
        canvas_id = (query.get("canvas_id") or [""])[0]
        self._send(200, blender_connection_status(canvas_id))
        return

    def _get_api_runninghub_query(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query or "", keep_blank_values=True)
        task_id = (query.get("taskId") or [""])[0]
        if not str(task_id or "").strip():
            raise ApiError(400, "缺少 taskId")
        _queried = runninghub_query_task(task_id)
        _rh_sync_task_console_state(task_id, _queried)
        self._send(200, {"success": True, "data": _queried})
        return

    def _get_api_runninghub_app_info(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query or "", keep_blank_values=True)
        app_id = (query.get("webappId") or [""])[0]
        cached = runninghub_cached_app_info(app_id)
        if cached:
            self._send(200, {"ok": True, "data": cached})
            return
        raise ApiError(404, "未找到已缓存的 RunningHub 应用")

    def _get_api_providers(self):
        self._send(200, {"ok": True, "providers": read_api_providers()})
        return

    def _get_api_canvas_thumbnail(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query, keep_blank_values=True)
        source_url = (query.get("url") or [""])[0]
        try:
            size = int((query.get("size") or ["640"])[0])
        except (TypeError, ValueError):
            size = 640
        thumbnail = canvas_thumbnail_path(source_url, size)
        self._send_bytes(200, thumbnail.read_bytes(), "image/webp")
        return

    def _get_api_canvas_image_info(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query, keep_blank_values=True)
        source_url = (query.get("url") or [""])[0]
        self._send(200, canvas_image_info(source_url))
        return

    def _get_api_download_output(self):
        self._serve_remote_output()
        return

    def _get_api_config(self):
        self._send(200, build_local_config_payload())
        return

    def _get_api_asset_library(self):
        self._send(200, {"ok": True, "library": read_asset_library()})
        return

    def _get_api_prompt_libraries(self):
        self._send(200, {"ok": True, "library": read_prompt_libraries()})
        return

    def _get_api_comfyui_instances(self):
        self._send(200, {"ok": True, "instances": read_comfy_instances()})
        return

    def _get_api_comfyui_object_info(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        types = [t.strip() for t in (query.get("types") or [""])[0].split(",") if t.strip()]
        try:
            self._send(200, {"ok": True, "object_info": comfy_flow_service.object_info_subset(types or None)})
        except Exception as exc:
            self._send(502, {"ok": False, "error": f"读取 ComfyUI 节点元数据失败: {str(exc)[:200]}"})
        return

    def _get_api_comfyui_queue(self):
        # 排队视图：正在跑的 + 还在排的（含位次），供前端显示「排队中 · 第 N 位」
        self._send(200, comfy_flow_service.MANAGER.queue_snapshot())
        return

    def _get_api_comfyui_jobs(self):
        self._send(200, {"ok": True, "jobs": comfy_flow_service.MANAGER.list_jobs()})
        return

    def _get_api_comfyui_recent_outputs(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        limit = (query.get("limit") or ["6"])[0]
        self._send(200, recent_comfy_outputs({"limit": limit}))
        return
    def do_GET(self):
        try:
            request_path = self.path.split("?", 1)[0]
            canvas_route, canvas_id = parse_canvas_route(request_path)
            workflow_route, workflow_name = parse_workflow_route(request_path)
            _GET_ROUTES = {
                '/health': '_get_health',
                '/api/task-console': '_get_api_task_console',
                '/app-config': '_get_app_config',
                '/api/canvas-agent-history': '_get_api_canvas_agent_history',
                '/api/canvas-agent-history-index': '_get_api_canvas_agent_history_index',
                '/api/canvas-agent-tasks': '_get_api_canvas_agent_tasks',
                '/api/canvas-agent-config': '_get_api_canvas_agent_config',
                '/api/canvas-agent-skill': '_get_api_canvas_agent_skill',
                '/api/integrations/blender/status': '_get_api_integrations_blender_status',
                '/api/runninghub/query': '_get_api_runninghub_query',
                '/api/runninghub/app-info': '_get_api_runninghub_app_info',
                '/api/providers': '_get_api_providers',
                '/api/canvas-thumbnail': '_get_api_canvas_thumbnail',
                '/api/canvas-image-info': '_get_api_canvas_image_info',
                '/api/download-output': '_get_api_download_output',
                '/api/config': '_get_api_config',
                '/api/asset-library': '_get_api_asset_library',
                '/api/prompt-libraries': '_get_api_prompt_libraries',
                '/api/comfyui/instances': '_get_api_comfyui_instances',
                '/api/comfyui/object-info': '_get_api_comfyui_object_info',
                '/api/comfyui/queue': '_get_api_comfyui_queue',
                '/api/comfyui/jobs': '_get_api_comfyui_jobs',
                '/api/comfyui/recent-outputs': '_get_api_comfyui_recent_outputs',
            }
            _get_fn = _GET_ROUTES.get(request_path)
            if _get_fn:
                getattr(self, _get_fn)()
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
            if request_path.startswith("/api/runninghub/workflows/"):
                workflow_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
                cached = runninghub_cached_workflow(workflow_id)
                if cached:
                    # "workflow" 与 "data" 并存：旧前端读 data.workflow，新前端读 data.data。
                    # 只给 data 会让旧前端拿不到配置→回云端重抓→把用户勾好的暴露字段清成 enabled:false。
                    self._send(200, {"ok": True, "data": cached, "workflow": cached})
                    return
                raise ApiError(404, "未找到已缓存的 RunningHub 工作流")
            if self._serve_static(self.path):
                return
            if self._serve_user_asset(self.path):
                return
            if request_path.startswith("/api/comfyui/jobs/"):
                job = comfy_flow_service.MANAGER.get(request_path.rsplit("/", 1)[-1])
                if not job:
                    # 后端重启过，内存里的任务记录已丢失，前端应停止轮询而不是一直等
                    self._send(404, {"ok": False, "error": "任务不存在或已过期", "status": "gone"})
                    return
                self._send(200, {"ok": True, **job.to_dict()})
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

    def _post_api_asset_library_libraries(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/asset-library/libraries 机械表化（体逐字）"""
        self._send(200, create_asset_library_record(payload))
        return

    def _post_api_asset_library_categories(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/asset-library/categories 机械表化（体逐字）"""
        self._send(200, create_asset_category_record(payload))
        return

    def _post_api_asset_library_items_versions(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/asset-library/items/versions 机械表化（体逐字）"""
        self._send(200, add_asset_library_version(payload))
        return

    def _post_api_asset_library_items_delete(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/asset-library/items/delete 机械表化（体逐字）"""
        self._send(200, delete_asset_items_record(payload))
        return

    def _post_api_asset_library_items_move(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/asset-library/items/move 机械表化（体逐字）"""
        self._send(200, move_asset_items_record(payload))
        return

    def _post_api_asset_library_items_crop(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/asset-library/items/crop 机械表化（体逐字）"""
        self._send(200, crop_asset_items_record(payload))
        return

    def _post_api_prompt_libraries(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/prompt-libraries 机械表化（体逐字）"""
        self._send(200, create_prompt_library_record(payload))
        return

    def _post_api_prompt_libraries_categories(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/prompt-libraries/categories 机械表化（体逐字）"""
        self._send(200, create_prompt_category_record(payload))
        return

    def _post_api_prompt_libraries_items(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/prompt-libraries/items 机械表化（体逐字）"""
        self._send(200, create_prompt_item_record(payload))
        return

    def _post_api_prompt_libraries_items_delete(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/prompt-libraries/items/delete 机械表化（体逐字）"""
        self._send(200, delete_prompt_items_record(payload))
        return

    def _post_api_localize_generated_media(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/localize-generated-media 机械表化（体逐字）"""
        self._send(200, handle_localize_generated_media(payload))
        return

    def _post_api_move_to_history(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/move-to-history 机械表化（体逐字）"""
        self._send(200, move_output_asset_to_history(payload))
        return

    def _post_api_task_console_stop(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/task-console-stop 机械表化（体逐字）"""
        self._send(200, task_console_stop(payload))
        return

    def _post_api_canvas_llm(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/canvas-llm 机械表化（体逐字）"""
        self._send(200, submit_chat(payload))
        return

    def _post_api_agent_models(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/agent-models 机械表化（体逐字）"""
        self._send(200, fetch_agent_models(payload))
        return

    _POST_ROUTES_B1 = {
        "/api/asset-library/libraries": "_post_api_asset_library_libraries",
        "/api/asset-library/categories": "_post_api_asset_library_categories",
        "/api/asset-library/items/versions": "_post_api_asset_library_items_versions",
        "/api/asset-library/items/delete": "_post_api_asset_library_items_delete",
        "/api/asset-library/items/move": "_post_api_asset_library_items_move",
        "/api/asset-library/items/crop": "_post_api_asset_library_items_crop",
        "/api/prompt-libraries": "_post_api_prompt_libraries",
        "/api/prompt-libraries/categories": "_post_api_prompt_libraries_categories",
        "/api/prompt-libraries/items": "_post_api_prompt_libraries_items",
        "/api/prompt-libraries/items/delete": "_post_api_prompt_libraries_items_delete",
        "/api/localize-generated-media": "_post_api_localize_generated_media",
        "/api/move-to-history": "_post_api_move_to_history",
        "/api/task-console-stop": "_post_api_task_console_stop",
        "/api/canvas-llm": "_post_api_canvas_llm",
        "/api/agent-models": "_post_api_agent_models",
    }

    def _post2_api_online_image(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/online-image 机械表化（体逐字）"""
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

    def _post2_api_generate(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/generate 机械表化（体逐字）"""
        self._send(200, handle_legacy_generate(payload))
        return

    def _post2_api_runninghub_upload_asset(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/runninghub/upload-asset 机械表化（体逐字）"""
        url = str(payload.get("url") or "").strip()
        if not url:
            raise ApiError(400, "缺少 url")
        uploaded = runninghub_upload_task_asset(url)
        self._send(200, {"success": True, "data": uploaded})
        return

    def _post2_api_runninghub_workflows_fetch(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/runninghub/workflows/fetch 机械表化（体逐字）"""
        workflow = runninghub_fetch_workflow_config(payload)
        self._send(200, {"success": True, "data": workflow})
        return

    def _post2_api_volcengine_upload_asset(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/volcengine/upload-asset 机械表化（体逐字）"""
        url = str(payload.get("url") or "").strip()
        if not url:
            raise ApiError(400, "缺少 url")
        uploaded = volcengine_upload_asset(url)
        self._send(200, {"success": True, "data": uploaded})
        return

    def _post2_api_cloud_video_upload(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/cloud-video/upload 机械表化（体逐字）"""
        url = str(payload.get("url") or "").strip()
        if not url:
            raise ApiError(400, "缺少 url")
        uploaded = upload_cloud_media_direct(url)
        self._send(200, uploaded)
        return

    def _post2_api_runninghub_submit(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/runninghub/submit 机械表化（体逐字）"""
        self._send(200, {"success": True, "data": runninghub_submit_app(payload)})
        return

    def _post2_api_runninghub_workflow_submit(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/runninghub/workflow-submit 机械表化（体逐字）"""
        self._send(200, {"success": True, "data": runninghub_submit_workflow(payload)})
        return

    def _post2_api_providers_fetch_models(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/providers/fetch-models 机械表化（体逐字）"""
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

    def _post2_api_canvas_image_tasks(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/canvas-image-tasks 机械表化（体逐字）"""
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

    def _post2_api_canvas_llm_stop(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/canvas-llm-stop 机械表化（体逐字）"""
        request_id = str(payload.get("request_id") or "").strip()
        self._send(200, {"ok": request_canvas_agent_stop(request_id), "request_id": request_id})
        return

    def _post2_api_canvas_agent_interaction(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/canvas-agent-interaction 机械表化（体逐字）"""
        session_id = str(payload.get("session_id") or payload.get("agent_session_id") or "").strip()
        self._send(200, get_canvas_agent_interaction(session_id))
        return

    def _post2_api_canvas_agent_interaction_receipt(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/canvas-agent-interaction-receipt 机械表化（体逐字）"""
        self._send(200, submit_canvas_agent_interaction_receipt(payload))
        return

    def _post2_api_canvas_agent_undo_batch(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/canvas-agent-undo-batch 机械表化（体逐字）"""
        try:
            self._send(200, _agent_tool_undo_batch(payload))
        except Exception as exc:
            self._send(200, {"ok": False, "error": str(exc)[:300]})
        return

    def _post2_api_canvas_agent_config(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/canvas-agent-config 机械表化（体逐字）"""
        if "rules" in payload:
            write_canvas_agent_rules(payload.get("rules") or "")
        self._send(200, canvas_agent_config_payload())
        return

    def _post2_api_canvas_agent_skill(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/canvas-agent-skill 机械表化（体逐字）"""
        name = str(payload.get("name") or "").strip()
        if bool(payload.get("delete")):
            result = delete_canvas_agent_skill(name)
            self._send(200, {"ok": True, **result, "skills": list_canvas_agent_skills()})
            return
        skill = write_canvas_agent_skill(name, payload.get("content") or "")
        self._send(200, {"ok": True, "skill": skill, "skills": list_canvas_agent_skills()})
        return

    def _post2_api_frontend_log(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/frontend-log 机械表化（体逐字）"""
        try:
            append_log(LOG_FILE, "frontend-log " + json.dumps(payload, ensure_ascii=False)[:2000])
        except Exception as log_exc:
            print("frontend-log write failed:", log_exc)
        self._send(200, {"ok": True})
        return

    def _post2_api_canvas_agent_history(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/canvas-agent-history 机械表化（体逐字）"""
        canvas_id = str(payload.get("canvas_id") or "").strip()
        history_list = payload.get("history")
        if not isinstance(history_list, list):
            raise RuntimeError("历史数据格式错误")
        saved_history = write_canvas_agent_history(canvas_id, history_list)
        sync_canvas_agent_history_index(canvas_id, saved_history, payload.get("canvas_title") or "")
        self._send(200, {"ok": True, "canvas_id": canvas_id, "history": saved_history})
        return

    def _post2_api_agent_key(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/agent-key 机械表化（体逐字）"""
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

    def _post2_api_agent_active(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/agent-active 机械表化（体逐字）"""
        agent_id = str(payload.get("agent_id") or "").strip()
        section = APP_CONFIG.get("agent") or {}
        agents = section.get("agents") if isinstance(section.get("agents"), dict) else {}
        if agent_id not in agents:
            raise ApiError(400, "未知 Agent: {}".format(agent_id))
        write_app_config(deep_merge(APP_CONFIG, {"agent": {"active_id": agent_id}}))
        self._send(200, {"ok": True, "agent": agents_meta_payload()})
        return

    def _post2_api_integrations_blender_push_batch(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/integrations/blender/push-batch 机械表化（体逐字）"""
        self._send(200, append_blender_batch_to_canvas(payload))
        return

    def _post2_api_integrations_blender_push_animation(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/integrations/blender/push-animation 机械表化（体逐字）"""
        self._send(200, append_blender_animation_to_canvas(payload))
        return

    def _post2_app_config(self, payload):
        """do_POST 路由表 handler：原精确分支 /app-config 机械表化（体逐字）"""
        saved = write_app_config(payload)
        self._send(200, {"ok": True, "config": saved})
        return

    def _post2_api_comfyui_jobs(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/comfyui/jobs 机械表化（体逐字）"""
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

    def _post2_api_comfyui_compile(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/comfyui/compile 机械表化（体逐字）"""
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

    def _post2_api_comfyui_instances(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/comfyui/instances 机械表化（体逐字）"""
        saved_instances = write_comfy_instances(payload.get("instances"))
        self._send(200, {"ok": True, "instances": saved_instances})
        return

    def _post2_api_open_folder(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/open-folder 机械表化（体逐字）"""
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

    _POST_ROUTES_B2 = {
        "/api/online-image": "_post2_api_online_image",
        "/api/generate": "_post2_api_generate",
        "/api/runninghub/upload-asset": "_post2_api_runninghub_upload_asset",
        "/api/runninghub/workflows/fetch": "_post2_api_runninghub_workflows_fetch",
        "/api/volcengine/upload-asset": "_post2_api_volcengine_upload_asset",
        "/api/cloud-video/upload": "_post2_api_cloud_video_upload",
        "/api/runninghub/submit": "_post2_api_runninghub_submit",
        "/api/runninghub/workflow-submit": "_post2_api_runninghub_workflow_submit",
        "/api/providers/fetch-models": "_post2_api_providers_fetch_models",
        "/api/canvas-image-tasks": "_post2_api_canvas_image_tasks",
        "/api/canvas-llm-stop": "_post2_api_canvas_llm_stop",
        "/api/canvas-agent-interaction": "_post2_api_canvas_agent_interaction",
        "/api/canvas-agent-interaction-receipt": "_post2_api_canvas_agent_interaction_receipt",
        "/api/canvas-agent-undo-batch": "_post2_api_canvas_agent_undo_batch",
        "/api/canvas-agent-config": "_post2_api_canvas_agent_config",
        "/api/canvas-agent-skill": "_post2_api_canvas_agent_skill",
        "/api/frontend-log": "_post2_api_frontend_log",
        "/api/canvas-agent-history": "_post2_api_canvas_agent_history",
        "/api/agent-key": "_post2_api_agent_key",
        "/api/agent-active": "_post2_api_agent_active",
        "/api/integrations/blender/push-batch": "_post2_api_integrations_blender_push_batch",
        "/api/integrations/blender/push-animation": "_post2_api_integrations_blender_push_animation",
        "/app-config": "_post2_app_config",
        "/api/comfyui/jobs": "_post2_api_comfyui_jobs",
        "/api/comfyui/compile": "_post2_api_comfyui_compile",
        "/api/comfyui/instances": "_post2_api_comfyui_instances",
        "/api/open-folder": "_post2_api_open_folder",
    }

    def _postc_00(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #0：原分支条件逐字（request_path == "/api/canvas-video" and is_volcengine_can...）"""
        if request_path == "/api/canvas-video" and is_volcengine_canvas_video_payload(payload):
            self._send(200, submit_volcengine_canvas_video_task(payload))
            return True
        return False

    def _postc_01(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #1：原分支条件逐字（request_path in ("/api/asset-library/items", "/api/asset-...）"""
        if request_path in ("/api/asset-library/items", "/api/asset-library/items/batch"):
            self._send(200, add_asset_library_items(payload))
            return True
        return False

    def _postc_02(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #2：原分支条件逐字（request_path == "/api/providers/test-connection" and is_r...）"""
        if request_path == "/api/providers/test-connection" and is_runninghub_request(payload):
            self._send(200, runninghub_probe_payload(payload, "test"))
            return True
        return False

    def _postc_03(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #3：原分支条件逐字（request_path == "/api/providers/test-connection" and is_v...）"""
        if request_path == "/api/providers/test-connection" and is_volcengine_request(payload):
            self._send(200, volcengine_probe_payload(payload, "test"))
            return True
        return False

    def _postc_04(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #4：原分支条件逐字（request_path == "/api/providers/test-connection" and str(...）"""
        if request_path == "/api/providers/test-connection" and str(payload.get("protocol") or "").strip().lower() == "openai":
            self._send(200, openai_probe_payload(payload, "test"))
            return True
        return False

    def _postc_05(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #5：原分支条件逐字（request_path == "/api/providers/probe-async" and str(payl...）"""
        if request_path == "/api/providers/probe-async" and str(payload.get("protocol") or "").strip().lower() == "openai":
            self._send(200, openai_probe_payload(payload, "probe"))
            return True
        return False

    def _postc_06(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #6：原分支条件逐字（request_path == "/api/providers/verify-base" and str(payl...）"""
        if request_path == "/api/providers/verify-base" and str(payload.get("protocol") or "").strip().lower() == "openai":
            self._send(200, openai_probe_payload(payload, "verify"))
            return True
        return False

    def _postc_07(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #7：原分支条件逐字（request_path == "/api/providers/probe-async" and is_runni...）"""
        if request_path == "/api/providers/probe-async" and is_runninghub_request(payload):
            self._send(200, runninghub_probe_payload(payload, "probe"))
            return True
        return False

    def _postc_08(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #8：原分支条件逐字（request_path == "/api/providers/probe-async" and is_volce...）"""
        if request_path == "/api/providers/probe-async" and is_volcengine_request(payload):
            self._send(200, volcengine_probe_payload(payload, "probe"))
            return True
        return False

    def _postc_09(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #9：原分支条件逐字（request_path == "/api/providers/verify-base" and is_runni...）"""
        if request_path == "/api/providers/verify-base" and is_runninghub_request(payload):
            self._send(200, runninghub_probe_payload(payload, "verify"))
            return True
        return False

    def _postc_10(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #10：原分支条件逐字（request_path == "/api/providers/verify-base" and is_volce...）"""
        if request_path == "/api/providers/verify-base" and is_volcengine_request(payload):
            self._send(200, volcengine_probe_payload(payload, "verify"))
            return True
        return False

    def _postc_11(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #11：原分支条件逐字（request_path in ("/api/integrations/blender/push-frame", ...）"""
        if request_path in ("/api/integrations/blender/push-frame", "/api/integrations/blender/push-snapshot"):
            self._send(200, append_blender_frame_to_canvas(payload))
            return True
        return False

    def _postc_12(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #12：原分支条件逐字（workflow_route == "collection":...）"""
        if workflow_route == "collection":
            created = create_workflow_record(payload.get("name"), payload.get("workflow"))
            self._send(200, {"ok": True, "name": created["name"], **created})
            return True
        return False

    def _postc_13(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #13：原分支条件逐字（workflow_route == "run":...）"""
        if workflow_route == "run":
            comfy_payload = dict(payload or {})
            comfy_payload.setdefault("canvas_id", str(canvas_id or "").strip())
            comfy_payload.setdefault("canvas_title", str((payload or {}).get("canvas_title") or _volcengine_canvas_title_for_output(canvas_id)).strip())
            self._send(200, run_comfy_workflow(workflow_name, comfy_payload))
            return True
        return False

    def _postc_14(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #14：原分支条件逐字（request_path.startswith("/api/comfyui/jobs/") and (...）"""
        if request_path.startswith("/api/comfyui/jobs/") and (
            request_path.endswith("/cancel") or request_path.endswith("/interrupt")
        ):
            job = comfy_flow_service.MANAGER.cancel(request_path.split("/")[-2])
            if not job:
                self._send(404, {"ok": False, "error": "任务不存在或已过期"})
                return True
            self._send(200, {"ok": True, **job.to_dict()})
            return True
        return False

    def _postc_15(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #15：原分支条件逐字（canvas_route == "collection":...）"""
        if canvas_route == "collection":
            created = create_canvas_record(payload)
            self._send(200, {"ok": True, "canvas": created})
            return True
        return False

    def _postc_16(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #16：原分支条件逐字（canvas_route == "import":...）"""
        if canvas_route == "import":
            self._send(200, import_canvas_payload(payload))
            return True
        return False

    def _postc_17(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #17：原分支条件逐字（canvas_route == "meta":...）"""
        if canvas_route == "meta":
            updated = update_canvas_meta(canvas_id, payload)
            self._send(200, {"ok": True, "canvas": updated})
            return True
        return False

    def _postc_18(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #18：原分支条件逐字（canvas_route == "touch":...）"""
        if canvas_route == "touch":
            touched = touch_canvas_record(canvas_id)
            self._send(200, {"ok": True, "canvas": touched, "updated_at": touched.get("updated_at")})
            return True
        return False

    def _postc_19(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #19：原分支条件逐字（canvas_route == "restore":...）"""
        if canvas_route == "restore":
            restored = restore_canvas_record(canvas_id)
            self._send(200, {"ok": True, "canvas": restored})
            return True
        return False

    _POST_CONDS = [
        "_postc_00",
        "_postc_01",
        "_postc_02",
        "_postc_03",
        "_postc_04",
        "_postc_05",
        "_postc_06",
        "_postc_07",
        "_postc_08",
        "_postc_09",
        "_postc_10",
        "_postc_11",
        "_postc_12",
        "_postc_13",
        "_postc_14",
        "_postc_15",
        "_postc_16",
        "_postc_17",
        "_postc_18",
        "_postc_19",
    ]

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
            _rm = Handler._POST_ROUTES_B1.get(request_path)
            if _rm is not None:
                getattr(self, _rm)(payload)
                return
            _rm2 = Handler._POST_ROUTES_B2.get(request_path)
            if _rm2 is not None:
                getattr(self, _rm2)(payload)
                return
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
            for _cm in Handler._POST_CONDS:
                if getattr(self, _cm)(request_path, payload, canvas_route, canvas_id,
                                      workflow_route, workflow_name):
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

    def _put_api_providers(self, payload, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_PUT 路由表 handler：原分支 exact /api/providers 机械表化（体逐字）"""
        providers = write_api_providers(payload)
        self._send(200, {"ok": True, "providers": providers})
        return

    def _put_api_runninghub_workflows(self, payload, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_PUT 路由表 handler：原分支 prefix /api/runninghub/workflows/ 机械表化（体逐字）"""
        workflow_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
        saved = save_runninghub_workflow_config(workflow_id, payload)
        self._send(200, {"success": True, "workflow": saved})
        return

    def _put_api_comfyui_instances(self, payload, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_PUT 路由表 handler：原分支 exact /api/comfyui/instances 机械表化（体逐字）"""
        saved_instances = write_comfy_instances(payload.get("instances"))
        self._send(200, {"ok": True, "instances": saved_instances})
        return

    def _put_workflow_config(self, payload, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_PUT 路由表 handler：原分支 route ('workflow', 'config') 机械表化（体逐字）"""
        saved = save_workflow_config(workflow_name, payload)
        self._send(200, {"ok": True, **saved})
        return

    def _put_canvas_item(self, payload, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_PUT 路由表 handler：原分支 route ('canvas', 'item') 机械表化（体逐字）"""
        saved = save_canvas_record(canvas_id, payload)
        self._send(200, {"ok": True, "canvas": saved})
        return

    _PUT_ROUTES = [
        ('exact', '/api/providers', "_put_api_providers"),
        ('prefix', '/api/runninghub/workflows/', "_put_api_runninghub_workflows"),
        ('exact', '/api/comfyui/instances', "_put_api_comfyui_instances"),
        ('route', ('workflow', 'config'), "_put_workflow_config"),
        ('route', ('canvas', 'item'), "_put_canvas_item"),
    ]

    def do_PUT(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw_body = self.rfile.read(length)
            payload = json.loads(raw_body.decode("utf-8") or "{}") if raw_body else {}
            request_path = self.path.split("?", 1)[0]
            canvas_route, canvas_id = parse_canvas_route(request_path)
            workflow_route, workflow_name = parse_workflow_route(request_path)
            for _k, _key, _m in Handler._PUT_ROUTES:
                if (_k == "exact" and request_path == _key) \
                    or (_k == "prefix" and request_path.startswith(_key)) \
                    or (_k == "route" and (
                        (_key[0] == "workflow" and workflow_route == _key[1])
                        or (_key[0] == "canvas" and canvas_route == _key[1]))):
                    getattr(self, _m)(payload, request_path, canvas_route, canvas_id, workflow_route, workflow_name)
                    break
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

    def _del_api_asset_library_categories(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_DELETE 路由表 handler：原分支 prefix /api/asset-library/categories/ 机械表化（体逐字）"""
        category_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
        self._send(200, delete_asset_category_record(category_id))
        return

    def _del_api_asset_library_items(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_DELETE 路由表 handler：原分支 prefix /api/asset-library/items/ 机械表化（体逐字）"""
        item_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
        self._send(200, delete_asset_item_record(item_id))
        return

    def _del_api_asset_library_libraries(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_DELETE 路由表 handler：原分支 prefix /api/asset-library/libraries/ 机械表化（体逐字）"""
        library_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
        self._send(200, delete_asset_library_record(library_id))
        return

    def _del_api_prompt_libraries_categories(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_DELETE 路由表 handler：原分支 prefix /api/prompt-libraries/categories/ 机械表化（体逐字）"""
        category_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
        self._send(200, delete_prompt_category_record(category_id))
        return

    def _del_api_prompt_libraries_items(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_DELETE 路由表 handler：原分支 prefix /api/prompt-libraries/items/ 机械表化（体逐字）"""
        item_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
        self._send(200, delete_prompt_item_record(item_id))
        return

    def _del_api_prompt_libraries(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_DELETE 路由表 handler：原分支 prefix /api/prompt-libraries/ 机械表化（体逐字）"""
        library_id = urllib.parse.unquote(request_path.rsplit("/", 1)[-1])
        self._send(200, delete_prompt_library_record(library_id))
        return

    def _del_workflow_item(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_DELETE 路由表 handler：原分支 route ('workflow', 'item') 机械表化（体逐字）"""
        self._send(200, delete_workflow_record(workflow_name))
        return

    def _del_canvas_item(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_DELETE 路由表 handler：原分支 route ('canvas', 'item') 机械表化（体逐字）"""
        deleted = trash_canvas_record(canvas_id)
        self._send(200, {"ok": True, "canvas": deleted})
        return

    def _del_canvas_trashPurgeAll(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_DELETE 路由表 handler：原分支 route ('canvas', 'trashPurgeAll') 机械表化（体逐字）"""
        self._send(200, purge_all_trash_records())
        return

    def _del_canvas_purge(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_DELETE 路由表 handler：原分支 route ('canvas', 'purge') 机械表化（体逐字）"""
        self._send(200, purge_canvas_record(canvas_id))
        return

    _DELETE_ROUTES = [
        ('prefix', '/api/asset-library/categories/', "_del_api_asset_library_categories"),
        ('prefix', '/api/asset-library/items/', "_del_api_asset_library_items"),
        ('prefix', '/api/asset-library/libraries/', "_del_api_asset_library_libraries"),
        ('prefix', '/api/prompt-libraries/categories/', "_del_api_prompt_libraries_categories"),
        ('prefix', '/api/prompt-libraries/items/', "_del_api_prompt_libraries_items"),
        ('prefix', '/api/prompt-libraries/', "_del_api_prompt_libraries"),
        ('route', ('workflow', 'item'), "_del_workflow_item"),
        ('route', ('canvas', 'item'), "_del_canvas_item"),
        ('route', ('canvas', 'trashPurgeAll'), "_del_canvas_trashPurgeAll"),
        ('route', ('canvas', 'purge'), "_del_canvas_purge"),
    ]

    def do_DELETE(self):
        request_path = self.path.split("?", 1)[0]
        canvas_route, canvas_id = parse_canvas_route(request_path)
        workflow_route, workflow_name = parse_workflow_route(request_path)
        try:
            for _k, _key, _m in Handler._DELETE_ROUTES:
                if (_k == "exact" and request_path == _key) \
                    or (_k == "prefix" and request_path.startswith(_key)) \
                    or (_k == "route" and (
                        (_key[0] == "workflow" and workflow_route == _key[1])
                        or (_key[0] == "canvas" and canvas_route == _key[1]))):
                    getattr(self, _m)(request_path, canvas_route, canvas_id, workflow_route, workflow_name)
                    break
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
