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

import myridtv_env

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

def _start_window_fix():
    """32刀：窗口补丁域住 myridtv_window_fix；延迟转发保块原位可用。"""
    return myridtv_window_fix._start_window_fix()

SCRIPT_PATH = Path(__file__).resolve()
APP_DIR = SCRIPT_PATH.parent if (SCRIPT_PATH.parent / "_internal").exists() else SCRIPT_PATH.parent.parent
ROOT = APP_DIR / "_internal" if (APP_DIR / "_internal").exists() else SCRIPT_PATH.parent
CONFIG_FILE = ROOT / "data" / "app_config.json"
import myridtv_asset_resolver

_user_data_env = os.environ.get("MYRIDTV_USER_DATA_DIR")
_portable_user_data = None if _user_data_env else myridtv_asset_resolver._portable_user_data_dir(APP_DIR)
if _user_data_env:
    USER_DATA_DIR = Path(_user_data_env)
elif _portable_user_data:
    USER_DATA_DIR = _portable_user_data
else:
    USER_DATA_DIR = Path(os.environ.get("APPDATA", str(APP_DIR))) / "MyridTV"
# 资产与输出默认放在软件安装目录下（用户要求 2026-08-16）。
# 2026-10-15 起可由用户自定义（Blender 插件那套：不改就用系统指定的）：
#   优先级 env MYRIDTV_ASSETS_DIR > app_config.paths.assets_dir（安装器/设置页写入）> <安装目录>/assets。
# 覆盖安装/在线升级只覆盖程序文件（installer [Files] 不删除未知目录），assets 子目录会保留。
# 注意：改了目录要重启应用才生效——ASSETS_DIR 在 import 期就被若干子模块定值注入了。
ASSETS_DIR = myridtv_asset_resolver.resolve_assets_root(APP_DIR, CONFIG_FILE)
ASSETS_DIR_SOURCE = myridtv_asset_resolver.assets_dir_source(APP_DIR, CONFIG_FILE)


def _migrate_legacy_assets():
    myridtv_asset_resolver.migrate_legacy_assets(USER_DATA_DIR, ASSETS_DIR)
_migrate_legacy_assets()
# 资产主路径下的标准子目录骨架（output/images|videos|audios|history、input、library、blender…）
myridtv_asset_resolver.ensure_assets_layout(ASSETS_DIR)
BLENDER_IMPORT_DIR = ASSETS_DIR / "blender_imports"
# —— Blender 预演（画布 → Blender → 画布）——
# previz 三件套是程序脚本、不是资产：随程序走（_internal/previz），升级会跟着更新。
# 兼容老安装：程序目录里没有时才回退到资产目录下的旧副本（早期脚本曾被放进 assets）。
PREVIZ_SHIPPED_DIR = APP_DIR / "_internal" / "previz"
PREVIZ_LEGACY_DIR = ASSETS_DIR / "blender" / "previz"
PREVIZ_DIR = PREVIZ_SHIPPED_DIR if (PREVIZ_SHIPPED_DIR / "previz_render.py").exists() else PREVIZ_LEGACY_DIR
def _resolve_blender_bin():
    r"""定位 blender.exe：环境变量 > PATH > 常见安装根扫描 > 裸命令兜底。

    历史坑（2026-10-17）：以前只认 PATH 上的裸 "blender"，Blender 安装目录
    不在 PATH 时 blender --background 直接 FileNotFoundError [WinError 2]，
    3D 预演 2 秒即败。扫描根：C:\Program Files\Blender Foundation 与
    <各固定盘>:\blender；优先最高 4.x——MyridTV 桥接插件（wcstv_blender_bridge_45，
    bl_info 声明 4.5.0）只装在 4.5 用户配置里，GUI 自动开箱后的手动推送回传依赖它；
    机器上没有 4.x 时才取最高版本（渲染脚本 --background 各版本通用）。
    """
    env_bin = (os.environ.get("MYRIDTV_BLENDER_BIN") or "").strip()
    if env_bin and Path(env_bin).exists():
        return env_bin
    on_path = shutil.which("blender")
    if on_path:
        return on_path
    roots = [Path(r"C:\Program Files\Blender Foundation")]
    for drive in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        roots.append(Path("%s:/blender" % drive))
    candidates = []
    for root in roots:
        try:
            if not root.is_dir():
                continue
            for exe in root.glob("*/blender.exe"):
                candidates.append(exe)
            direct = root / "blender.exe"
            if direct.is_file():
                candidates.append(direct)
        except OSError:
            continue
    if not candidates:
        return "blender"

    def _version_key(exe):
        match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", exe.parent.name)
        if not match:
            return (0, 0, 0)
        return (int(match.group(1)), int(match.group(2)), int(match.group(3) or 0))

    four_x = [exe for exe in candidates if _version_key(exe)[0] == 4]
    pool = four_x or candidates
    return str(max(pool, key=_version_key))


BLENDER_BIN = _resolve_blender_bin()
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
    "proxy": {"host": "127.0.0.1", "port": 3107, "base_url": "http://127.0.0.1:3107"},
    "agent": {
        "active_id": "codex",
        "agents": DEFAULT_AGENTS,
    },
    "runninghub": {"api_key_envs": ["RUNNINGHUB_COIN_API_KEY", "RUNNINGHUB_API_KEY"]},
    "paths": {
        "env_file": "API/.env",
        "logs_dir": "data/logs",
        "proxy_log": "data/logs/rh_official_proxy.log",
        "startup_log": "data/logs/startup.log",
        # 资产主路径（assets 根目录）。空 = 用系统默认 <安装目录>/assets；
        # 由安装器首装页或设置页写入绝对路径，改完需重启应用。
        "assets_dir": "",
    },
    "runtime": {"python_exe": "", "python_env": "MYRIDTV_PYTHON_EXE"},
    "user_data": {"root_env": "MYRIDTV_USER_DATA_DIR", "default_dir": "%APPDATA%\\MyridTV", "mode": "junction"},
    "setup": {"completed": False, "completed_at": "", "dismissed_at": ""},
}


def normalize_agent_section(section):
    return myridtv_env.normalize_agent_section(section)


def active_agent_entry(config=None):
    return myridtv_env.active_agent_entry(config)


def resolve_agent_entry(agent_id=None, config=None):
    return myridtv_env.resolve_agent_entry(agent_id, config)

myridtv_env.configure(lambda: ENV_FILE, lambda: RUNNINGHUB_CONFIG, lambda: AGENT_CONFIG,
                       lambda: APP_CONFIG,
                       lambda: volcengine_ark_api_key(),
                       lambda agent_id=None, config=None: resolve_agent_entry(agent_id, config),
                       lambda: DEFAULT_AGENTS,
                       {'CONFIG_FILE': CONFIG_FILE, 'DEFAULT_CONFIG': DEFAULT_CONFIG,
                        'ROOT': ROOT, 'log_file_getter': lambda: LOG_FILE})





def load_app_config():
    return myridtv_env.load_app_config()


def describe_update_error(exc):
    """把更新检查的网络异常翻成人话，供界面提示用。"""
    text = str(exc)
    lowered = text.lower()
    if "urlopen" in lowered or "timed out" in lowered or "10060" in text:
        return "连不上更新服务器，请检查网络或代理设置"
    if "10053" in text or "aborted" in lowered or "reset" in lowered:
        return "连接被中断，请检查网络后重试"
    if "ssl" in lowered or "certificate" in lowered:
        return "安全证书校验失败，请检查系统时间或网络代理"
    if "resolve" in lowered or "getaddrinfo" in lowered:
        return "域名解析失败，请检查 DNS 或网络设置"
    return text or "未知错误"


def root_path(value, fallback):
    return myridtv_env.root_path(value, fallback)


def write_static_app_config(raw):
    return myridtv_env.write_static_app_config(raw)


def apply_app_config(merged):
    """boot 与 write_app_config 共用：把 merged 应用回主模块 globals（派生绑定单点）。"""
    global APP_CONFIG, PROXY_CONFIG, AGENT_CONFIG, RUNNINGHUB_CONFIG, PATHS_CONFIG, ENV_FILE, APP_BASE, PORT, LOG_FILE
    APP_CONFIG = merged
    PROXY_CONFIG = APP_CONFIG.get("proxy") or {}
    AGENT_CONFIG = active_agent_entry(APP_CONFIG)
    RUNNINGHUB_CONFIG = APP_CONFIG.get("runninghub") or {}
    PATHS_CONFIG = APP_CONFIG.get("paths") or {}
    ENV_FILE = root_path(PATHS_CONFIG.get("env_file"), "API/.env")
    LOG_FILE = root_path(PATHS_CONFIG.get("proxy_log"), "data/logs/rh_official_proxy.log")
    # app_base = 本代理自身地址（原为已废弃的 server(3000) 内部服务；该服务 2026-09 已不存在）
    APP_BASE = str(PROXY_CONFIG.get("base_url") or f"http://{PROXY_CONFIG.get('host', '127.0.0.1')}:{PROXY_CONFIG.get('port', 3107)}").rstrip("/")
    PORT = int(PROXY_CONFIG.get("port") or 3107)


def write_app_config(config):
    merged = deep_merge(DEFAULT_CONFIG, config if isinstance(config, dict) else {})
    merged["agent"] = normalize_agent_section(merged.get("agent"))
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(merged, ensure_ascii=False, indent=2)
    CONFIG_FILE.write_text(raw + "\n", encoding="utf-8")
    write_static_app_config(raw)
    apply_app_config(merged)
    append_log(LOG_FILE, f"app-config saved agent_active={APP_CONFIG['agent'].get('active_id')} agents={','.join(APP_CONFIG['agent'].get('agents', {}).keys())}")
    return merged


apply_app_config(load_app_config())
# 启动时把生效配置镜像到 _internal/static/app_config.json（前端读这份定 API 基址，
# 端口冲突换端口后必须同步，否则前端会打到 3107 上的另一个实例）——见 write_static_app_config
write_static_app_config(json.dumps(APP_CONFIG, ensure_ascii=False, indent=2))
TASKS = {}
TASKS_LOCK = threading.Lock()
PERSISTENT_TASKS_FILE = USER_DATA_DIR / "data" / "canvas_tasks.json"
STATIC_VERSION = "2026.10.23.e2efix1"
OUTPUT_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
# Windows 版 Python 的 mimetypes 不带 webp，猜不出来会回落成
# application/octet-stream，浏览器按未知类型拒绝渲染（风格缩略图会全变空白）。
mimetypes.add_type("image/webp", ".webp")
OUTPUT_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
RUNNINGHUB_ALLOWED_RESOLUTIONS = ("1k", "2k", "4k")
RUNNINGHUB_POLL_TIMEOUT_SECONDS = 1800
CODEX_LOCAL_UPSTREAMS = {"codex://local", "codex://cli", "codex://bridge"}
CODEX_LOCAL_DEFAULT_MODEL = "codex-default"
CODEX_LOCAL_DEFAULT_RUNTIME_MODEL = "gpt-5.5"
CODEX_LOCAL_WORKSPACE = Path(os.environ.get("MYRIDTV_CODEX_WORKSPACE") or APP_DIR)
CODEX_LOCAL_ATTACHMENTS_DIR = USER_DATA_DIR / "data" / "codex_bridge"
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


import myridtv_static_delivery


def positive_env_int(name, default, minimum=1, maximum=None):
    return myridtv_static_delivery.positive_env_int(name, default, minimum, maximum)


COMFY_WORKFLOW_POLL_TIMEOUT_SECONDS = myridtv_static_delivery.COMFY_WORKFLOW_POLL_TIMEOUT_SECONDS
RUNNINGHUB_DEFAULT_IMAGE_MODELS = myridtv_static_delivery.RUNNINGHUB_DEFAULT_IMAGE_MODELS


def patch_static_versions_once():
    myridtv_static_delivery.patch_static_versions_once()


myridtv_static_delivery.configure(ROOT, lambda: STATIC_VERSION)




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
    return myridtv_env.read_chat_key(provider_id, agent_entry)


def agents_meta_payload():
    return myridtv_env.agents_meta_payload()




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
import myridtv_provider
import myridtv_provider_audio
import myridtv_agent
import myridtv_canvas_store
import myridtv_task_state
import myridtv_media_localize
import myridtv_video_codec
import myridtv_libraries
import myridtv_codex
import myridtv_chat
import myridtv_rh_taskflow
import myridtv_provider_image
import myridtv_workflow_assets
import myridtv_window_fix
import myridtv_agent_receipt
import myridtv_rh_api
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
import myridtv_offline_previs
import myridtv_comfy
import myridtv_runninghub
import myridtv_rh_catalog
import myridtv_volcengine

myridtv_http.configure(lambda: runninghub_api_base())


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

myridtv_video_codec.configure({
    "LOG_FILE": lambda: LOG_FILE,
})

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
    lambda name, config: myridtv_workflow_assets.save_workflow_config(name, config),
)

myridtv_runninghub.configure(
    TASKS, TASKS_LOCK, lambda: LOG_FILE,
    lambda path: runninghub_api_url(path),
    lambda: runninghub_task_key(),
    lambda: runninghub_task_auth_headers(),
)

myridtv_rh_catalog.configure(
    lambda url, timeout=60: request_text(url, timeout),
    RUNNINGHUB_DEFAULT_IMAGE_MODELS,
    USER_DATA_DIR, lambda: LOG_FILE,
    lambda url, method="GET", payload=None, headers=None, timeout=120: myridtv_http.request_json(
        url, method=method, payload=payload, headers=headers, timeout=timeout
    ),
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

def request_chat_json_with_retry(url, body, headers, attempts=3, timeout=120):
    return myridtv_chat.request_chat_json_with_retry(url, body, headers, attempts, timeout)




def _codex_bridge_read_session_cache():
    return myridtv_codex._codex_bridge_read_session_cache()


def _codex_bridge_write_session_cache():
    return myridtv_codex._codex_bridge_write_session_cache()


def _codex_bridge_session_key(payload, model):
    return myridtv_codex._codex_bridge_session_key(payload, model)


def _codex_bridge_session_record(payload, model):
    return myridtv_codex._codex_bridge_session_record(payload, model)


def _codex_bridge_store_session_record(key, thread_id, model):
    return myridtv_codex._codex_bridge_store_session_record(key, thread_id, model)


def _codex_bridge_clear_session_record(key):
    return myridtv_codex._codex_bridge_clear_session_record(key)


# 35刀：会话缓存单例归 myridtv_codex，主留同对象别名（零重绑实证）。
CODEX_LOCAL_SESSION_LOCK = myridtv_codex.CODEX_LOCAL_SESSION_LOCK
CODEX_LOCAL_SESSION_CACHE = myridtv_codex.CODEX_LOCAL_SESSION_CACHE



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


def _probe_recovering_remote_tasks():
    """常驻对账：本地在飞/待核实的云端任务，由后端周期性向 RunningHub 核实并落终态。

    2026-10-23 老王（真因）：收片此前完全依赖前端那条轮询连接。页面一刷新或切画布，
    连接就断（后端日志里是 WinError 10053），于是任务永远停在 running、节点一直
    「生成中」、控制台不收片 —— 用户既拿不到结果，也没法重跑，还不报错。
    收片不能依赖「页面还活着」，所以这里放一个常驻后台线程兜底：
    凡是「非终态 + 有云端任务号」的任务，每 15 秒核一次：
      SUCCESS -> succeeded（产物地址写回任务）
      FAILED  -> failed（带云端原因）
      其它    -> 记一笔 checked_at，继续等下一轮
    兼容重启恢复：recover_stale_tasks 挂起的 recovering 也在扫描范围内。
    """
    import threading
    import time as _time

    non_terminal = ("recovering", "running", "submitted", "queued", "pending")

    def _run():
        _time.sleep(8)          # 等后端端口就绪，避免自连失败
        while True:
            try:
                pending = []
                for tid, st in list(myridtv_task_state.TASKS.items()):
                    if not isinstance(st, dict):
                        continue
                    if str(st.get("status") or "").strip().lower() not in non_terminal:
                        continue
                    remote_id = str(
                        st.get("recover_remote_id") or st.get("provider_task_id") or st.get("rh_task_id") or ""
                    ).strip()
                    if remote_id:
                        pending.append((tid, remote_id))
                for tid, remote_id in pending:
                    try:
                        q = runninghub_query_task(remote_id)
                    except Exception as exc:
                        append_log(LOG_FILE, f"reconcile probe error task={tid} remote={remote_id}: {exc}")
                        continue
                    status = str((q or {}).get("status") or "").upper()
                    if status == "SUCCESS":
                        urls = [u for u in (q.get("urls") or []) if u]
                        myridtv_task_state.update_task_state(
                            tid, status="succeeded", error="", completed_at=_time.time(),
                            checked_at=_time.time(), raw_status="SUCCESS",
                            result={"images": [{"url": u} for u in urls]},
                            reconciled_from_remote=True,
                        )
                        append_log(LOG_FILE, f"reconcile task={tid} remote={remote_id} -> succeeded urls={len(urls)}")
                    elif status == "FAILED":
                        myridtv_task_state.update_task_state(
                            tid, status="failed", error=(q.get("failReason") or "云端任务失败"),
                            completed_at=_time.time(), checked_at=_time.time(), raw_status="FAILED",
                        )
                        append_log(LOG_FILE, f"reconcile task={tid} remote={remote_id} -> failed")
                    else:
                        myridtv_task_state.update_task_state(
                            tid, checked_at=_time.time(), raw_status=status or "RUNNING")
            except Exception as exc:
                try:
                    append_log(LOG_FILE, f"reconcile loop error: {exc}")
                except Exception:
                    pass
            _time.sleep(15)

    t = threading.Thread(target=_run, name="reconcile-remote-tasks", daemon=True)
    t.start()


# 延迟到本模块全部加载完再拉线程（runninghub_query_task 在文件后段定义，
# 线程体里第一次用到时才会解析，但启动太早容易碰到端口未就绪）。
def _bootstrap_probe_recovering():
    try:
        _probe_recovering_remote_tasks()
    except Exception as _exc:  # 恢复失败绝不能拖垮启动
        try:
            append_log(LOG_FILE, f"recover probe bootstrap failed: {_exc}")
        except Exception:
            pass
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
    return myridtv_asset_resolver.output_asset_kind_for_name(name)


def output_asset_subdir_for_kind(kind="image"):
    return myridtv_asset_resolver.output_asset_subdir_for_kind(kind)


def output_asset_fallback_paths(decoded):
    return myridtv_asset_resolver.output_asset_fallback_paths(decoded)


def resolve_user_asset_path(url_path):
    return myridtv_asset_resolver.resolve_user_asset_path(url_path)


def canvas_thumbnail_path(source_url, max_edge=640):
    return myridtv_asset_resolver.canvas_thumbnail_path(source_url, max_edge)


def canvas_image_info(source_url):
    return myridtv_asset_resolver.canvas_image_info(source_url)

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
    return myridtv_workflow_assets.create_workflow_record(name, workflow)


def save_workflow_config(name, config):
    return myridtv_workflow_assets.save_workflow_config(name, config)


def delete_workflow_record(name):
    return myridtv_workflow_assets.delete_workflow_record(name)


def rename_workflow_record(name, new_name):
    return myridtv_workflow_assets.rename_workflow_record(name, new_name)


def parse_workflow_route(request_path):
    return myridtv_workflow_assets.parse_workflow_route(request_path)


def save_blender_payload_asset(payload):
    return myridtv_workflow_assets.save_blender_payload_asset(payload)
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

def _agent_default_run_settings(args, preset=None, canvas=None, cid=""):
    return myridtv_agent_state._agent_default_run_settings(args, preset, canvas=canvas, cid=cid)

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
    return myridtv_agent_tools.canvas_agent_execute_tool(name, args, preset, session_id)


# 交互回执：session_id -> {card_id, selection, submitted_at, resolved}
CANVAS_AGENT_RECEIPTS = {}
CANVAS_AGENT_RECEIPTS_LOCK = threading.Lock()

myridtv_agent_stop.configure(
    CANVAS_AGENT_RECEIPTS,
    CANVAS_AGENT_RECEIPTS_LOCK,
)

myridtv_workflow_assets.configure(
    {
        'LOG_FILE': lambda: LOG_FILE,
        'ROOT': lambda: ROOT,
        'ASSETS_DIR': lambda: ASSETS_DIR,
        # 重命名工作流时需连带改写画布里的引用
        'CANVAS_DIR': lambda: USER_DATA_DIR / "data" / "canvases",
    },
)

myridtv_provider_image.configure(
    lambda: LOG_FILE,
    lambda: RUNNINGHUB_POLL_TIMEOUT_SECONDS,
    {
        'prepare_reference': lambda source_url: upload_cloud_media_direct(source_url).get("downloadUrl") or "",
        'is_cancelled': lambda local_task_id: _task_console_is_cancelled(local_task_id),
    },
)

myridtv_rh_taskflow.configure(
    lambda: LOG_FILE,
    {
        'runninghub_api_base': lambda *a, **k: runninghub_api_base(*a, **k),
        'submit_generic_image': lambda *a, **k: myridtv_provider_image.submit_generic_image(*a, **k),
        'poll_generic_result': lambda *a, **k: myridtv_provider_image.poll_generic_result(*a, **k),
        'query_generic_image': lambda *a, **k: myridtv_provider_image.query_generic_image(*a, **k),
    },
    lambda: RUNNINGHUB_POLL_TIMEOUT_SECONDS,
)

myridtv_asset_resolver.configure(
    {
        'ASSETS_DIR': lambda: ASSETS_DIR,
        'USER_DATA_DIR': lambda: USER_DATA_DIR,
        'OUTPUT_IMAGE_EXTS': lambda: OUTPUT_IMAGE_EXTS,
        'OUTPUT_VIDEO_EXTS': lambda: OUTPUT_VIDEO_EXTS,
    },
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
append_log(LOG_FILE, f"blender bin resolved: {BLENDER_BIN}")

myridtv_agent_tasks.configure(
    TASKS, TASKS_LOCK,
    lambda: LOG_FILE,
)


def submit_canvas_agent_interaction_receipt(payload):
    return myridtv_agent_receipt.submit_canvas_agent_interaction_receipt(payload)


def get_canvas_agent_interaction(session_id=""):
    return myridtv_agent_receipt.get_canvas_agent_interaction(session_id)


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

def _upload_target_for_scope(request_path=""):
    """按 /api/ai/upload 的 query 决定上传物落盘位置（返回 target_dir, url_prefix, kind_subdir）。

    scope=canvas&canvas_id=xxx
        画布类动作（上传 / 导入 / 粘贴拖入 / 裁剪外扩 / Agent 附件 / 封面）→
        assets/output/<画布目录>/<images|videos|audios|files>/
        这样上传物随画布改名一起搬移、随画布彻底删除一起清理（此前一律进
        assets/input，与画布无关联，删画布后成为孤儿）。
    scope=library
        素材库（跨画布、不随任何画布删除）→ assets/library/
        该目录历史上就用于存放素材库文件（现存 lib_* 旧文件），后因上传被统一到
        /api/ai/upload 而失去写入方，这里恢复。
    缺省
        assets/input/——旧行为，兼容未带 scope 的调用方（如设置页工作流预览）。
    """
    query = request_path.split("?", 1)[1] if "?" in str(request_path or "") else ""
    params = urllib.parse.parse_qs(query)
    scope = str((params.get("scope") or [""])[0]).strip().lower()
    if scope == "library":
        return str(ASSETS_DIR / "library"), "/assets/library", None
    if scope == "canvas":
        canvas_id = str((params.get("canvas_id") or [""])[0]).strip()
        if not canvas_id:
            return "", "", None
        title = ""
        try:
            title = str(read_canvas_record(canvas_id, include_deleted=True).get("title") or "").strip()
        except Exception:
            title = ""
        folder = canvas_output_folder_name(title, canvas_id)
        if not folder:
            return "", "", None
        return (
            str(ASSETS_DIR / "output" / folder),
            "/assets/output/" + urllib.parse.quote(str(folder), safe=""),
            {
                "image": output_asset_subdir_for_kind("image") or "images",
                "video": output_asset_subdir_for_kind("video") or "videos",
                "audio": output_asset_subdir_for_kind("audio") or "audios",
                "*": "files",
            },
        )
    return "", "", None


def handle_ai_upload(raw_body, content_type, target_dir=None, url_prefix=None, kind_subdir=None):
    return myridtv_media_localize.handle_ai_upload(
        raw_body, content_type, target_dir, url_prefix, kind_subdir)

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
    return myridtv_rh_api.runninghub_api_base()


def runninghub_api_url(path):
    return myridtv_rh_api.runninghub_api_url(path)


def runninghub_upload_binary_media(source_url):
    return myridtv_rh_api.runninghub_upload_binary_media(source_url)


def runninghub_upload_task_asset(source_url):
    return myridtv_rh_api.runninghub_upload_task_asset(source_url)


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
    return myridtv_rh_taskflow.refresh_canvas_task_state(task_id)


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
    return myridtv_rh_taskflow.handle_legacy_generate(payload)




def is_runninghub_request(payload):
    return myridtv_rh_catalog.is_runninghub_request(payload)

def runninghub_model_catalog(provider_id="", base_url="", force=False):
    return myridtv_rh_catalog.runninghub_model_catalog(provider_id, base_url, force)

def runninghub_probe_payload(payload, action="test"):
    return myridtv_rh_catalog.runninghub_probe_payload(payload, action)

RUNNINGHUB_DEFAULT_IMAGE_MODELS = myridtv_rh_catalog._DEFAULT_IMAGE_MODELS  # 第9刀：列表仍被块外引用，别名同对象


def request_text(url, timeout=60):
    return myridtv_http.request_text(url, timeout)


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
    return myridtv_rh_taskflow.submit_official(payload)


def submit_and_poll_official(payload):
    return myridtv_rh_taskflow.submit_and_poll_official(payload)


def poll_result(task_id):
    return myridtv_rh_taskflow.poll_result(task_id)


def localize_canvas_task_result(result, payload):
    return myridtv_rh_taskflow.localize_canvas_task_result(result, payload)


def _previz_ratio_size(aspect_ratio):
    return myridtv_rh_taskflow._previz_ratio_size(aspect_ratio)


def _strip_llm_fenced_text(text):
    return myridtv_rh_taskflow._strip_llm_fenced_text(text)


def run_task(task_id, payload):
    return myridtv_rh_taskflow.run_task(task_id, payload)


def handle_localize_generated_media(payload):
    return myridtv_rh_taskflow.handle_localize_generated_media(payload)
import myridtv_mcp

# 26刀：MCP 域住 myridtv_mcp；Handler 消费的表与分发器走引用别名。
# MCP_BASE 维持 import 期定值语义（迁移前后一致）。
MCP_BASE = str(PROXY_CONFIG.get("base_url") or f"http://127.0.0.1:{PORT}").rstrip("/")
myridtv_mcp.configure(MCP_BASE)
MCP_TOOLS = myridtv_mcp.MCP_TOOLS
def _mcp_handle(name, args):
    return myridtv_mcp._mcp_handle(name, args)


class Handler(BaseHTTPRequestHandler):
    # 2026-10-15: HTTP/1.1 + keep-alive。冷启动打开画布要拉 130+ 个静态文件，
    # HTTP/1.0 下每个文件一条短连接，慢机(CI runner)上并发握手容易丢连接
    # (trace 里 js 请求 status=-1, 耗时 600~1000ms)。升 1.1 后浏览器用 ~6 条
    # 长连接复用到全部文件，连接数从 130+ 降到个位数。所有响应都带 Content-Length。
    protocol_version = 'HTTP/1.1'
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
        request = urllib.request.Request(myridtv_media_localize.iri_to_uri(source_url), headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"
        })
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0].strip()
        self._send_bytes(200, raw, content_type or "application/octet-stream")
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
            "software_version": (APP_DIR / "VERSION").read_text(encoding="utf-8").strip(),
            "mcp_api_version": "0.3.0",
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

    def _get_update_status(self):
        import myridtv_updater
        state_file = myridtv_updater.state_path(APP_DIR)
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                state = {}
        except (OSError, ValueError):
            state = {}
        self._send(200, {"ok": True, "static_version": state.get("static_version", ""), "status": state.get("status", "current")})
        return

    def _post_api_update_check(self, payload):
        """版本号按钮触发：同步跑一次更新检查，完成后回写状态文件。"""
        import myridtv_updater
        public_key = Path(APP_DIR) / "update-public-key.pub"
        if not public_key.is_file():
            self._send(200, {"ok": False, "status": "unsupported", "detail": "缺少更新公钥"})
            return
        try:
            result = myridtv_updater.check_now(Path(APP_DIR), public_key)
        except Exception as exc:
            append_log(LOG_FILE, f"update check failed: {exc}\n")
            self._send(200, {"ok": False, "status": "error", "detail": describe_update_error(exc)})
            return
        self._send(200, {"ok": True, **result})
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

    def _get_api_assets_root(self):
        """资产主路径（assets 根目录）当前状态：给设置页读。"""
        self._send(200, myridtv_asset_resolver.assets_root_payload(
            ASSETS_DIR, APP_DIR, USER_DATA_DIR, CONFIG_FILE, ASSETS_DIR_SOURCE))
        return

    def _get_api_home_bg_list(self):
        """主页背景素材目录清单：assets/home-bg/ 下用户自放的图片/视频。
        目录不存在则自动创建，方便用户直接往里放文件。"""
        import os as _os
        folder = ASSETS_DIR / "home-bg"
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        files = []
        if folder.is_dir():
            _IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif", ".svg"}
            _VID_EXT = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v"}
            try:
                entries = sorted(folder.iterdir(), key=lambda p: p.name)
            except Exception:
                entries = []
            for entry in entries:
                if not entry.is_file():
                    continue
                ext = entry.suffix.lower()
                kind = "image" if ext in _IMG_EXT else ("video" if ext in _VID_EXT else "")
                if not kind:
                    continue
                try:
                    stat = entry.stat()
                except Exception:
                    continue
                files.append({
                    "name": entry.name,
                    "url": "/assets/home-bg/" + urllib.parse.quote(entry.name, safe=""),
                    "type": kind,
                    "size": stat.st_size,
                    "mtime": int(stat.st_mtime),
                })
        self._send(200, {"ok": True, "dir": str(folder), "files": files})
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
    def _getc_00(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_GET 谓词链 #0：原分支条件逐字（workflow_route == "collection"）"""
        if workflow_route == "collection":
            self._send(200, {"ok": True, "workflows": list_workflow_records()})
            return True
        return False

    def _getc_01(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_GET 谓词链 #1：原分支条件逐字（workflow_route == "item"）"""
        if workflow_route == "item":
            self._send(200, {"ok": True, **read_workflow_record(workflow_name)})
            return True
        return False

    def _getc_02(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_GET 谓词链 #2：原分支条件逐字（canvas_route == "collection"）"""
        if canvas_route == "collection":
            self._send(200, {"ok": True, "canvases": list_canvas_records(include_deleted=False)})
            return True
        return False

    def _getc_03(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_GET 谓词链 #3：原分支条件逐字（canvas_route == "trash"）"""
        if canvas_route == "trash":
            self._send(200, {"ok": True, "canvases": list_canvas_records(include_deleted=True)})
            return True
        return False

    def _getc_04(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_GET 谓词链 #4：原分支条件逐字（canvas_route == "item"）"""
        if canvas_route == "item":
            self._send(200, {"ok": True, "canvas": read_canvas_record(canvas_id, include_deleted=True)})
            return True
        return False

    def _getc_05(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_GET 谓词链 #5：原分支条件逐字（canvas_route == "meta"）"""
        if canvas_route == "meta":
            canvas = read_canvas_record(canvas_id, include_deleted=True)
            self._send(200, {"ok": True, **canvas_summary(canvas)})
            return True
        return False

    def _getc_06(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_GET 谓词链 #6：原分支条件逐字（canvas_route == "export"）"""
        if canvas_route == "export":
            self._send(200, export_canvas_payload(canvas_id))
            return True
        return False

    def _getc_07(self, request_path, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_GET 谓词链 #7：原分支条件逐字（request_path.startswith(prefix)）"""
        prefix = "/api/canvas-image-tasks/"
        if request_path.startswith(prefix):
            task_id = request_path[len(prefix):]
            self._send(200, refresh_canvas_task_state(task_id))
            return True
        return False


    _GET_CONDS = [
        "_getc_00",
        "_getc_01",
        "_getc_02",
        "_getc_03",
        "_getc_04",
        "_getc_05",
        "_getc_06",
        "_getc_07",
    ]


    def do_GET(self):
        try:
            request_path = self.path.split("?", 1)[0]
            canvas_route, canvas_id = parse_canvas_route(request_path)
            workflow_route, workflow_name = parse_workflow_route(request_path)
            if request_path == "/api/plugins/offline-previs":
                self._send(200, myridtv_offline_previs.plugin().metadata())
                return
            if request_path.startswith("/api/plugins/offline-previs/web/"):
                raw, content_type = myridtv_offline_previs.plugin().web_asset(request_path.rsplit("/", 1)[-1])
                self._send_bytes(200, raw, content_type)
                return
            _GET_ROUTES = {
                '/health': '_get_health',
                '/api/update-status': '_get_update_status',
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
                '/api/assets-root': '_get_api_assets_root',
                '/api/home-bg/list': '_get_api_home_bg_list',
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
                self.send_header("Content-Length", "0")
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
            for _cm in Handler._GET_CONDS:
                if getattr(self, _cm)(request_path, canvas_route, canvas_id,
                                      workflow_route, workflow_name):
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
        """提示词节点 LLM 运行 / 连通性测试专用：强制纯聊天，不注入任何画布变更工具。"""
        payload = dict(payload) if isinstance(payload, dict) else {}
        payload["pure_chat"] = True
        self._send(200, submit_chat(payload))
        return

    def _post_api_agent_models(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/agent-models 机械表化（体逐字）"""
        self._send(200, fetch_agent_models(payload))
        return

    _POST_ROUTES_B1 = {
        "/api/update-check": "_post_api_update_check",
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
        "/api/assets-root": "_post2_api_assets_root",
        "/api/assets-root/migrate": "_post2_api_assets_root_migrate",
        "/api/localize-generated-media": "_post_api_localize_generated_media",
        "/api/move-to-history": "_post_api_move_to_history",
        "/api/task-console-stop": "_post_api_task_console_stop",
        "/api/canvas-llm": "_post_api_canvas_llm",
        "/api/agent-models": "_post_api_agent_models",
        "/api/comfyui/auto-expose-media": "_post2_api_comfyui_auto_expose_media",
    }

    def _post2_api_assets_root(self, payload):
        """设置资产主路径（assets 根目录）。assets_dir 留空或 use_default=true = 回到系统默认 <安装目录>/assets。"""
        raw = str(payload.get("assets_dir") or "").strip()
        use_default = bool(payload.get("use_default")) or not raw
        if use_default:
            target_value = ""
            target = Path(APP_DIR) / "assets"
        else:
            ok, message, candidate = myridtv_asset_resolver.validate_assets_target(raw, APP_DIR, USER_DATA_DIR)
            if not ok:
                raise ApiError(400, message)
            target = candidate
            target_value = str(candidate)
        created = myridtv_asset_resolver.ensure_assets_layout(target)
        merged = write_app_config(deep_merge(APP_CONFIG, {"paths": {"assets_dir": target_value}}))
        try:
            append_log(LOG_FILE, f"assets-root saved: {target} (source={'custom' if target_value else 'default'})")
        except Exception:
            pass
        self._send(200, {
            "ok": True,
            "assets_dir": str(target),
            "assets_dir_setting": target_value,
            "source": "custom" if target_value else "default",
            "created": created,
            # ASSETS_DIR 在 import 期就被若干子模块定值注入，热切不可靠 → 改完必须重启应用
            "requires_restart": True,
            "config": merged,
        })
        return

    def _post2_api_assets_root_migrate(self, payload):
        """把旧资产目录内容复制到当前资产目录（复制而非移动：源目录原地保留，零丢失）。"""
        source = str(payload.get("source") or payload.get("from") or "").strip() or str(Path(APP_DIR) / "assets")
        target = str(payload.get("target") or payload.get("to") or "").strip() or str(ASSETS_DIR)
        src = Path(source)
        dst = Path(target)
        if not src.exists() or not src.is_dir():
            raise ApiError(400, "源目录不存在：%s" % src)
        try:
            same = src.resolve() == dst.resolve()
        except Exception as exc:
            raise ApiError(400, "路径无法解析：%s" % exc)
        if same:
            raise ApiError(400, "源目录和目标目录是同一个，不用搬")
        dst.mkdir(parents=True, exist_ok=True)
        state = myridtv_asset_resolver.start_assets_migration(str(src), str(dst))
        try:
            append_log(LOG_FILE, f"assets migration started: {src} -> {dst}")
        except Exception:
            pass
        self._send(200, {"ok": True, "source": str(src), "target": str(dst), "migration": state})
        return

    def _post2_api_online_image(self, payload):
        """do_POST 路由表 handler：原精确分支 /api/online-image 机械表化（体逐字）"""
        result = submit_and_poll_official(payload)
        self._send(200, {
            "images": result["images"],
            "timestamp": int(time.time() * 1000),
            "prompt": payload.get("prompt") or "",
            "params": payload,
            "task_id": result["task_id"],
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
        if myridtv_provider_audio.is_mimo(payload):
            self._send(200, myridtv_provider_audio.probe(payload))
            return
        if is_runninghub_request(payload):
            # 用户点「拉取模型」= 显式要最新清单，强制同步官方目录和文档路由
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
        """do_POST 路由表 handler：原精确分支 /api/integrations/blender/push-animation 机械表化（体逐字）
        2026-10-17：回传完全依赖插件——推送带 task_id 且命中等待中的预演任务时，
        直接交付给该任务的 worker（合并进结果后由前端写回原节点），不再 append 新节点；
        未命中（手动推送/任务已结算）维持原行为 append 新节点。"""
        task_id = str((payload or {}).get("task_id") or "").strip()
        if task_id and myridtv_blender_previz.deliver_previz_push(task_id, payload):
            self._send(200, {"ok": True, "delivered_to_task": task_id})
            return
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

    def _post2_api_comfyui_auto_expose_media(self, payload):
        """导入/加载工作流时自动暴露素材槽：把未暴露的 LoadImage/LoadAudio 追加进 config。"""
        name = str(payload.get("name") or "").strip()
        if not name:
            self._send(200, {"ok": False, "added": 0, "error": "name 为空"})
            return
        result = myridtv_comfy.auto_expose_media_fields(name)
        self._send(200, result)
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

    def _post2_api_canvas_audio(self, payload):
        client_id = str(payload.get("client_task_id") or "")
        task_id = client_id if re.fullmatch(r"speech_[0-9a-f]{32}", client_id) else "speech_" + uuid.uuid4().hex
        now = time.time()
        state = {"backend":"provider-audio", "status":"running", "created_at":now,
                 "checked_at":now, "can_stop":False, "provider_id":str(payload.get("provider_id") or ""),
                 "model":str(payload.get("model") or myridtv_provider_audio.MODELS[0]), "mode":dict(zip(myridtv_provider_audio.MODELS,("音色设计","预置音色","音色复刻"))).get(payload.get("model") or myridtv_provider_audio.MODELS[0],"语音"),
                 "canvas_id":str(payload.get("canvas_id") or ""), "canvas_title":str(payload.get("canvas_title") or ""),
                 "node_id":str(payload.get("node_id") or ""), "node_title":str(payload.get("node_title") or "语音生成"),
                 "audio_format":str(payload.get("format") or "wav"), "source":"画布节点执行", "persistent":True}
        with TASKS_LOCK:
            if task_id in TASKS:
                self._send(409, {"ok":False,"detail":"这次语音任务已经提交，请等待完成或重新点击生成"})
                return
            TASKS[task_id] = state
            myridtv_task_state.persist_tasks_locked(task_id)
        append_log(LOG_FILE, "speech started task=" + task_id + " node=" + state["node_id"] + " model=" + state["model"])
        try:
            result = myridtv_provider_audio.generate(payload)
            update_task_state(task_id,status="succeeded",completed_at=time.time(),checked_at=time.time(),
                              result={"audios":result.get("items") or []},localized_at=time.time())
            append_log(LOG_FILE, "speech generated task=" + task_id + " node=" + state["node_id"] + " model=" + state["model"])
            self._send(200, {**result,"task_id":task_id})
        except myridtv_provider_audio.AudioError as exc:
            update_task_state(task_id,status="failed",completed_at=time.time(),checked_at=time.time(),error=exc.detail)
            append_log(LOG_FILE, "speech failed task=" + task_id + " node=" + state["node_id"] + " model=" + state["model"] + " status=" + str(exc.status) + " detail=" + exc.detail)
            self._send(exc.status, {"ok":False,"detail":exc.detail,"task_id":task_id})
        except Exception:
            detail = "语音生成发生异常，请稍后重新生成"
            update_task_state(task_id,status="failed",completed_at=time.time(),checked_at=time.time(),error=detail)
            append_log(LOG_FILE, "speech failed task=" + task_id + " node=" + state["node_id"] + " detail=" + detail)
            self._send(500,{"ok":False,"detail":detail,"task_id":task_id})

    _POST_ROUTES_B2 = {
        "/api/canvas-audio": "_post2_api_canvas_audio",
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
        if request_path == "/api/providers/test-connection" and myridtv_provider_audio.is_mimo(payload):
            self._send(200, myridtv_provider_audio.probe(payload))
            return True
        if request_path == "/api/providers/test-connection" and str(payload.get("protocol") or "").strip().lower() == "openai":
            self._send(200, openai_probe_payload(payload, "test"))
            return True
        return False

    def _postc_05(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #5：原分支条件逐字（request_path == "/api/providers/probe-async" and str(payl...）"""
        if request_path == "/api/providers/probe-async" and myridtv_provider_audio.is_mimo(payload):
            self._send(200, myridtv_provider_audio.probe(payload))
            return True
        if request_path == "/api/providers/probe-async" and str(payload.get("protocol") or "").strip().lower() == "openai":
            self._send(200, openai_probe_payload(payload, "probe"))
            return True
        return False

    def _postc_06(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #6：原分支条件逐字（request_path == "/api/providers/verify-base" and str(payl...）"""
        if request_path == "/api/providers/verify-base" and myridtv_provider_audio.is_mimo(payload):
            self._send(200, myridtv_provider_audio.probe(payload))
            return True
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

    def _postc_20(self, request_path, payload, canvas_route, canvas_id, workflow_route, workflow_name):
        """do_POST 谓词链 #20：工作流重命名（workflow_route == "rename"）。

        把 .json 与 .config.json 一起改名，并连带改写所有画布里对该文件名的引用，
        使「前端显示名」与「后端文件名」统一为同一个名字。
        """
        if workflow_route == "rename":
            result = rename_workflow_record(workflow_name, (payload or {}).get("name"))
            self._send(200, result)
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
        "_postc_20",
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
                _dir, _prefix, _subdir = _upload_target_for_scope(self.path)
                self._send(200, handle_ai_upload(raw_body, content_type, _dir, _prefix, _subdir))
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
                        "serverInfo": {"name": "myridtv-canvas", "version": (APP_DIR / "VERSION").read_text(encoding="utf-8").strip().lstrip("V")},
                    }})
                elif method == "tools/list":
                    tools = [{"name": name, **defn} for name, defn in MCP_TOOLS.items()]
                    self._send(200, {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}})
                elif method == "tools/call":
                    name = params.get("name", "")
                    args = params.get("arguments", {})
                    if name not in MCP_TOOLS:
                        self._send(200, {"jsonrpc": "2.0", "id": req_id, "result": {"isError": True, "content": [{"type":"text", "text":json.dumps({"ok":False,"error_code":"entrypoint_changed","error":"旧工具已撤下，请刷新 MCP 工具列表并调用 canvas_execute","entrypoint":"canvas_execute","action":name.removeprefix('canvas_')},ensure_ascii=False)}]}})
                    else:
                        try:
                            result = _mcp_handle(name, args)
                            if result.get("error") or result.get("ok") is False:
                                self._send(200, {"jsonrpc": "2.0", "id": req_id, "result": {
                                    "isError": True, "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}})
                            else:
                                # 兼容两种返回格式：{"result": ...} 或 _agent_tool_* 直接返回的 {ok: ..., ...}
                                payload = result.get("result", result)
                                txt = json.dumps(payload, ensure_ascii=False)
                                self._send(200, {"jsonrpc": "2.0", "id": req_id, "result": {"isError": False, "content": [{"type": "text", "text": txt}]}})
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
        """do_PUT 路由表 handler：原分支 route ('canvas', 'item') 机械表化（体逐字）
        + 重命名联动：标题变化时同步输出素材文件夹并重写画布内所有引用 url。"""
        payload = payload if isinstance(payload, dict) else {}
        current = read_canvas_record(canvas_id, include_deleted=True)
        renamed = None
        new_title = payload.get("title")
        old_title = current.get("title")
        if new_title is not None and str(new_title).strip() != str(old_title or "").strip():
            info = myridtv_media_localize.rename_canvas_output_folder(old_title, new_title, canvas_id)
            if info:
                # 改写既有画布数据里的引用（payload 可能只带了 title，未带 nodes）
                rewritten = myridtv_media_localize.rewrite_output_urls(current, info["old_folder"], info["new_folder"])
                if isinstance(rewritten, dict):
                    if "nodes" in rewritten:
                        payload["nodes"] = rewritten.get("nodes")
                    if "artifacts" in rewritten:
                        payload["artifacts"] = rewritten.get("artifacts")
                    if "cover" in rewritten:
                        payload["cover"] = rewritten.get("cover")
                renamed = info
        saved = save_canvas_record(canvas_id, payload)
        resp = {"ok": True, "canvas": saved}
        if renamed:
            resp["renamed"] = renamed
        self._send(200, resp)
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
            self._send(404, {"detail": "not found"})
        except ApiError as exc:
            self._send(exc.status, {"detail": exc.detail, **exc.payload})
        except Exception as exc:
            append_log(LOG_FILE, f"{self.command} {self.path} failed: {exc}")
            self._send(502, {"detail": str(exc)})

    def log_message(self, fmt, *args):
        return


class CanvasProxyServer(ThreadingHTTPServer):
    # A cold canvas page pulls 130+ static files over HTTP/1.0, so every asset opens
    # its own connection. The socketserver default backlog of 5 drops the overflow,
    # which surfaced as random "CanvasXxxController is not defined" on slower machines
    # (GitHub runners): the script never arrived, the entry script aborted mid-file and
    # every later `let` stayed in its temporal dead zone.
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128


if __name__ == "__main__":
    append_log(LOG_FILE, f"proxy starting pid={os.getpid()} version={STATIC_VERSION} app_base={APP_BASE} port={PORT}")
    patch_static_versions_once()
    threading.Thread(target=patch_static_versions_loop, daemon=True).start()
    # 启动窗口样式自动修复
    _start_window_fix()
    # 启动 Canvas MCP 端点（内置于主服务）
    print(f"[canvas-mcp] embedded at http://127.0.0.1:{PORT}/mcp")
    # 重启后把挂起等核实的云端任务问清楚（进程重启 ≠ 云端失败）
    _bootstrap_probe_recovering()
    CanvasProxyServer((str(PROXY_CONFIG.get("host") or "127.0.0.1"), PORT), Handler).serve_forever()
