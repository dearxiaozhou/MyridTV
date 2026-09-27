# -*- coding: utf-8 -*-
"""MyridTV provider 域（后端拆分第2刀2b）：api_providers.json 读写、记录净化、内置表合并、
Key 槽回填（enrich/persist）、用户模型偏好 prefs。

逐字迁移自 rh_official_proxy.py 五块（行级可逆机械核对）。行为零变更。
configure() 注入：ROOT/USER_DATA_DIR 路径 + myridtv_env 四函数 + 主文件 volc 套餐判定两个。
主文件对剩余代码仍引用的名字保留同名薄代理/常量再导出，调用点不改。
"""
import json
import re

from myridtv_core import read_json_file, write_json_file, mask_secret

_ROOT = None
_USER_DATA_DIR = None
_env_read_env_values = None
_env_write_env_values = None
_env_provider_key_env_name = None
_env_provider_wallet_key_env_name = None
_x_is_volcengine_plan_base = None
_x_volcengine_plan_chat_models = None


def configure(root, user_data_dir, read_env_values, write_env_values,
              provider_key_env_name, provider_wallet_key_env_name,
              is_volcengine_plan_base, volcengine_plan_chat_models):
    global _ROOT, _USER_DATA_DIR, _env_read_env_values, _env_write_env_values
    global _env_provider_key_env_name, _env_provider_wallet_key_env_name
    global _x_is_volcengine_plan_base, _x_volcengine_plan_chat_models
    _ROOT = root
    _USER_DATA_DIR = user_data_dir
    _env_read_env_values = read_env_values
    _env_write_env_values = write_env_values
    _env_provider_key_env_name = provider_key_env_name
    _env_provider_wallet_key_env_name = provider_wallet_key_env_name
    _x_is_volcengine_plan_base = is_volcengine_plan_base
    _x_volcengine_plan_chat_models = volcengine_plan_chat_models


def enrich_api_provider_key_meta(providers):
    values = _env_read_env_values()
    result = []
    for provider in providers if isinstance(providers, list) else []:
        if not isinstance(provider, dict):
            continue
        item = dict(provider)
        key_env = _env_provider_key_env_name(item.get("id"))
        key_value = values.get(key_env, "")
        item["key_env"] = key_env
        item["has_key"] = bool(key_value)
        item["key_preview"] = mask_secret(key_value)
        # 火山推理计划 plan 端点不提供模型列表；仅在用户没有保存任何对话模型时用内置清单引导，
        # 已保存的以用户配置为准（删掉的模型不再复活）。
        if _x_is_volcengine_plan_base(item.get("base_url")) and not (item.get("chat_models") or []):
            item["chat_models"] = _x_volcengine_plan_chat_models(item.get("chat_models"))
        if str(item.get("id") or "").strip() == "runninghub":
            wallet_env = _env_provider_wallet_key_env_name(item.get("id"))
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
        key_env = _env_provider_key_env_name(provider_id)
        wallet_env = _env_provider_wallet_key_env_name(provider_id)
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
        _env_write_env_values(updates, removals)


def providers_file_path():
    return _USER_DATA_DIR / "data" / "api_providers.json"


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
    fallback = _ROOT / "static" / "runninghub" / "api_providers.json"
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
    "model_protocols",
}
API_PROVIDER_LIST_KEYS = {"image_models", "chat_models", "video_models", "rh_apps", "rh_workflows"}
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


def user_model_prefs_path():
    return _USER_DATA_DIR / "data" / "user_model_prefs.json"


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


