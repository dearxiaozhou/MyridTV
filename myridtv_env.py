# -*- coding: utf-8 -*-
"""MyridTV env 密钥域（后端拆分第2刀2a）：API/.env 读写 + RH 双通道 Key 槽命名。

逐字迁移自 rh_official_proxy.py（read_env_values/write_env_values/read_env_balance_key/
read_env_key/provider_key_env_name/provider_wallet_key_env_name），行为零变更。
ENV_FILE 与 RUNNINGHUB_CONFIG 由主文件 configure() 注入（主文件 import 时求值一次，
注入闭包同样每次读取主文件当前值，语义一致）。主文件保留同名薄代理，调用点不改。
"""
import os
import re

_env_file = None
_rh_config_getter = lambda: {}
_agent_config_getter = lambda: {}


def configure(env_file_getter, rh_config_getter, agent_config_getter):
    global _env_file, _rh_config_getter, _agent_config_getter
    _env_file = env_file_getter
    _rh_config_getter = rh_config_getter
    _agent_config_getter = agent_config_getter


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

    keys = _rh_config_getter().get("api_key_envs") or ("API_PROVIDER_CUSTOM_API_3_KEY", "RUNNINGHUB_API_KEY")

    values = read_env_values()

    for key in keys:

        if values.get(key):

            return values[key]

    return ""




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

    if provider_id == str(_agent_config_getter().get("provider_id") or "").strip():

        return str(_agent_config_getter().get("api_key_env") or "MYRIDTV_AGENT_API_KEY").strip() or "MYRIDTV_AGENT_API_KEY"

    return "API_PROVIDER_CUSTOM_API_KEY"




def provider_wallet_key_env_name(provider_id):

    provider_id = str(provider_id or "").strip()

    if provider_id == "runninghub":

        return "RUNNINGHUB_API_KEY"

    safe = re.sub(r"[^A-Za-z0-9]+", "_", provider_id).strip("_").upper()

    return f"API_PROVIDER_{safe}_WALLET_KEY" if safe else "API_PROVIDER_WALLET_KEY"





__all__ = [
    "read_env_values",
    "write_env_values",
    "read_env_balance_key",
    "read_env_key",
    "provider_key_env_name",
    "provider_wallet_key_env_name",
    "configure",
]
