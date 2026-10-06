# -*- coding: utf-8 -*-
"""MyridTV env 密钥域（后端拆分第2刀2a）：API/.env 读写 + RH 双通道 Key 槽命名。

逐字迁移自 rh_official_proxy.py（read_env_values/write_env_values/read_env_balance_key/
read_env_key/provider_key_env_name/provider_wallet_key_env_name），行为零变更。
ENV_FILE 与 RUNNINGHUB_CONFIG 由主文件 configure() 注入（主文件 import 时求值一次，
注入闭包同样每次读取主文件当前值，语义一致）。主文件保留同名薄代理，调用点不改。
"""
import json
import os
import re
from pathlib import Path

import myridtv_core

_env_file = None
_rh_config_getter = lambda: {}
_agent_config_getter = lambda: {}
_app_config_getter = lambda: {}
_ark_key_getter = lambda: ""
_resolve_agent_entry = lambda agent_id: (None, {})
_default_agents_getter = lambda: {}
_G_CONFIG_FILE = None
_G_DEFAULT_CONFIG = {}
_G_ROOT = None
_log_file = lambda: None


def configure(env_file_getter, rh_config_getter, agent_config_getter,
              app_config_getter=None, ark_key_getter=None, resolve_agent_entry=None,
              default_agents_getter=None, config_globals=None):
    global _env_file, _rh_config_getter, _agent_config_getter
    global _app_config_getter, _ark_key_getter, _resolve_agent_entry
    global _default_agents_getter
    global _G_CONFIG_FILE, _G_DEFAULT_CONFIG, _G_ROOT, _log_file
    _env_file = env_file_getter
    _rh_config_getter = rh_config_getter
    _agent_config_getter = agent_config_getter
    if app_config_getter is not None:
        _app_config_getter = app_config_getter
    if ark_key_getter is not None:
        _ark_key_getter = ark_key_getter
    if resolve_agent_entry is not None:
        _resolve_agent_entry = resolve_agent_entry
    if default_agents_getter is not None:
        _default_agents_getter = default_agents_getter
    if config_globals is not None:
        _G_CONFIG_FILE = config_globals['CONFIG_FILE']
        _G_DEFAULT_CONFIG = config_globals['DEFAULT_CONFIG']
        _G_ROOT = config_globals['ROOT']
        _log_file = config_globals['log_file_getter']


def load_app_config():
    try:
        data = json.loads(_G_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    merged = myridtv_core.deep_merge(_G_DEFAULT_CONFIG, data if isinstance(data, dict) else {})
    merged["agent"] = normalize_agent_section(merged.get("agent"))
    return merged


def root_path(value, fallback):
    text = str(value or fallback or "").strip()
    path = Path(text)
    return path if path.is_absolute() else _G_ROOT / path


def write_static_app_config(raw):
    """把生效配置镜像到 _internal/static/app_config.json —— 前端启动时读的就是这一份。

    安装脚本首次只把 app_config.template.json 复制过去，里面的 proxy 端口写死 3107；
    若本安装因端口冲突换到了别的端口（多份安装共存），不镜像就会让前端把请求发去
    3107 上的另一个实例（表现为看到别的安装的 Agent 设置 / 对话历史 / 控制台记录）。
    """
    try:
        static_config = _G_ROOT / "static" / "app_config.json"
        static_config.parent.mkdir(parents=True, exist_ok=True)
        static_config.write_text(raw + "\n", encoding="utf-8")
    except Exception as exc:
        try:
            myridtv_core.append_log(_log_file(), f"static app_config sync failed: {exc}")
        except Exception:
            pass


def read_env_values():

    try:

        lines = _env_file().read_text(encoding="utf-8").splitlines()

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

        lines = _env_file().read_text(encoding="utf-8").splitlines()

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

    _env_file().parent.mkdir(parents=True, exist_ok=True)

    _env_file().write_text("\n".join(result_lines).rstrip() + "\n", encoding="utf-8")

    return read_env_values()




def read_env_balance_key():

    """标准模型 API（flare 等第三方模型）只认企业级 Key：优先「账户余额 API Key」槽。



    与 read_env_key()（RH币工作流通道=会员 Key 优先）分刀；余额槽为空时回退

    币槽，兼容只配一把 Key 的老配置。"""

    values = read_env_values()

    wallet = str(values.get("RUNNINGHUB_API_KEY") or "").strip()

    return wallet or read_env_key()




def read_env_key():

    keys = _rh_config_getter().get("api_key_envs") or ("RUNNINGHUB_COIN_API_KEY", "RUNNINGHUB_API_KEY")

    values = read_env_values()

    for key in keys:

        if values.get(key):

            return values[key]

    return ""




def provider_key_env_name(provider_id):

    provider_id = str(provider_id or "").strip()

    if provider_id == "volcengine":

        return "ARK_API_KEY"

    if provider_id == "runninghub":

        # RH币/会员 key 独立槽位：不再与自定义平台 custom-api-3 共用变量（2026-09-28 解耦）

        return "RUNNINGHUB_COIN_API_KEY"

    if provider_id == "custom-api":

        return "API_PROVIDER_CUSTOM_API_KEY"

    # 平台 Key 优先按 API_PROVIDER_<ID>_KEY 推导（custom-api-2 → API_PROVIDER_CUSTOM_API_2_KEY）。

    # 注意：不能因为「该平台就是 Agent 当前平台」就返回 Agent 自己的 Key 变量——

    # Agent 切平台后那个变量通常不存在，会一路掉到兜底 Key（串平台 → 401）。

    safe = re.sub(r"[^A-Za-z0-9]+", "_", provider_id).strip("_").upper()

    if safe:

        return f"API_PROVIDER_{safe}_KEY"

    if provider_id == str(_agent_config_getter().get("provider_id") or "").strip():

        return str(_agent_config_getter().get("api_key_env") or "MYRIDTV_AGENT_API_KEY").strip() or "MYRIDTV_AGENT_API_KEY"

    return "API_PROVIDER_CUSTOM_API_KEY"




def provider_wallet_key_env_name(provider_id):

    provider_id = str(provider_id or "").strip()

    if provider_id == "runninghub":

        return "RUNNINGHUB_API_KEY"

    safe = re.sub(r"[^A-Za-z0-9]+", "_", provider_id).strip("_").upper()

    return f"API_PROVIDER_{safe}_WALLET_KEY" if safe else "API_PROVIDER_WALLET_KEY"







def read_chat_key(provider_id="", agent_entry=None):
    entry = agent_entry if isinstance(agent_entry, dict) else _agent_config_getter()
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
            ark_key = _ark_key_getter()
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
        _, entry = _resolve_agent_entry(agent_id)
    else:
        entry = _agent_config_getter()
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
    section = _app_config_getter().get("agent") or {}
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
            base = dict(_default_agents_getter().get(aid, {}))
            for key, value in entry.items():
                if value is not None and value != "":
                    base[key] = value
            if not base.get("name"):
                base["name"] = _default_agents_getter().get(aid, {}).get("name") or aid
            agents[aid] = base
    if legacy:
        base = dict(_default_agents_getter()["codex"])
        base.update(legacy)
        base["name"] = "Myrid-Agent"
        agents["codex"] = base
    for aid, defaults in _default_agents_getter().items():
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
    config = config if isinstance(config, dict) else _app_config_getter()
    section = config.get("agent") or {}
    agents = section.get("agents") if isinstance(section.get("agents"), dict) else {}
    if not agents:
        agents = dict(_default_agents_getter())
    active_id = str(section.get("active_id") or "codex")
    entry = agents.get(active_id)
    if entry is None:
        entry = next(iter(agents.values()), dict(_default_agents_getter()["codex"]))
    return entry


def resolve_agent_entry(agent_id=None, config=None):
    """按 agent_id 解析 Agent 配置条目；未指定或不存在时回退到激活 Agent。

    返回 (agent_id, entry)。
    """
    config = config if isinstance(config, dict) else _app_config_getter()
    section = config.get("agent") or {}
    agents = section.get("agents") if isinstance(section.get("agents"), dict) else {}
    if not agents:
        agents = dict(_default_agents_getter())
    requested = str(agent_id or "").strip() or str(section.get("active_id") or "codex")
    if requested not in agents:
        requested = "codex" if "codex" in agents else next(iter(agents))
    return requested, agents[requested]


__all__ = [
    "read_env_values",
    "write_env_values",
    "read_env_balance_key",
    "read_env_key",
    "provider_key_env_name",
    "provider_wallet_key_env_name",
    "configure",
    "read_chat_key",
    "agent_key_meta",
    "agents_meta_payload",
    "normalize_agent_section",
    "active_agent_entry",
    "resolve_agent_entry",
    "load_app_config",
    "root_path",
    "write_static_app_config",
]
