# -*- coding: utf-8 -*-
"""MyridTV RunningHub 生成请求构建族（后端拆分第23刀）：参考图上传、模型名
归一、尺寸解析/分辨率与画幅推导、官方请求体构建、provider 模型表/首选模型、
legacy 生图载荷解析、任务 key/auth headers。

逐字迁移自 rh_official_proxy.py 连续块 L(upload_reference)..
L(local_media_source_bytes)（13 函数 + 2 常量 191 行，可逆还原行级
diff=0）。行为零变更。configure() 注入：runninghub_upload_binary_media 延迟
闭包（真身留主）+ 两个零重绑常量值传。read_api_providers/read_env_key 属性
链直引 myridtv_provider / myridtv_env（壳穿透）。
主文件对被仍引用的 5 函数留同名薄代理。
"""
import math
import re
import threading
import time

from myridtv_core import unique_strings, parse_positive_int

import myridtv_env
import myridtv_provider

_r_runninghub_upload_binary_media = None
_G_RUNNINGHUB_ALLOWED_RESOLUTIONS = None
_G_RUNNINGHUB_DEFAULT_IMAGE_MODELS = None


def configure(runninghub_upload_binary_media, runninghub_allowed_resolutions,
              runninghub_default_image_models):
    global _r_runninghub_upload_binary_media
    global _G_RUNNINGHUB_ALLOWED_RESOLUTIONS
    global _G_RUNNINGHUB_DEFAULT_IMAGE_MODELS
    _r_runninghub_upload_binary_media = runninghub_upload_binary_media
    _G_RUNNINGHUB_ALLOWED_RESOLUTIONS = runninghub_allowed_resolutions
    _G_RUNNINGHUB_DEFAULT_IMAGE_MODELS = runninghub_default_image_models


_REFERENCE_UPLOAD_TTL_SEC = 900.0
_REFERENCE_UPLOAD_CACHE_MAX = 256
_REFERENCE_UPLOAD_WAIT_SEC = 180.0
_reference_upload_lock = threading.Lock()
_reference_upload_cache = {}        # 源 url -> (过期时间戳, downloadUrl)
_reference_upload_inflight = {}     # 源 url -> {"event": Event, "value": downloadUrl}


def upload_reference(ref):
    url = ref.get("url") if isinstance(ref, dict) else str(ref or "")
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return _upload_reference_shared(url)


def _upload_reference_shared(url):
    """带结果缓存 + 单飞（single-flight）的参考图上传。

    背景：批量/多张节点一次提交会把同一张参考图随每个并发任务各传一遍
    （2026-10-27 实测 8 并发 = 同一张图传 8 次），既慢又容易把 RH 侧的
    请求频率顶上去。key 就是本地/相对 URL 字符串本身：
      ① 命中缓存直接复用 downloadUrl（默认 TTL 15 分钟）；
      ② 同一时刻只放行一个上传线程，其余并发请求等它的结果而不是各自重传；
      ③ 领队失败时跟随者自己兜底再传一次（不把领队的失败扩散给整批）。
    """
    now = time.time()
    with _reference_upload_lock:
        hit = _reference_upload_cache.get(url)
        if hit and hit[0] > now and hit[1]:
            return hit[1]
        waiter = _reference_upload_inflight.get(url)
        leader = waiter is None
        if leader:
            waiter = {"event": threading.Event(), "value": ""}
            _reference_upload_inflight[url] = waiter
    if not leader:
        waiter["event"].wait(timeout=_REFERENCE_UPLOAD_WAIT_SEC)
        if waiter["value"]:
            return waiter["value"]
        return _upload_reference_once(url)
    value = ""
    try:
        value = _upload_reference_once(url)
    finally:
        with _reference_upload_lock:
            waiter["value"] = value
            if value:
                if len(_reference_upload_cache) >= _REFERENCE_UPLOAD_CACHE_MAX:
                    _reference_upload_cache.pop(next(iter(_reference_upload_cache)), None)
                _reference_upload_cache[url] = (time.time() + _REFERENCE_UPLOAD_TTL_SEC, value)
            _reference_upload_inflight.pop(url, None)
            waiter["event"].set()
    return value


def _upload_reference_once(url):
    uploaded = _r_runninghub_upload_binary_media(url) or {}
    return uploaded.get("downloadUrl") or ""


def reset_reference_upload_cache():
    """清掉参考图上传缓存（测试用）。生产路径不需要调用。"""
    with _reference_upload_lock:
        _reference_upload_cache.clear()
        inflight = list(_reference_upload_inflight.values())
        _reference_upload_inflight.clear()
    for waiter in inflight:
        waiter["event"].set()


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
    if resolution not in _G_RUNNINGHUB_ALLOWED_RESOLUTIONS:
        size_value = str(payload.get("size") or "").strip()
        size_lower = size_value.lower()
        resolution = size_lower if size_lower in _G_RUNNINGHUB_ALLOWED_RESOLUTIONS else derive_resolution_from_size(size_value) or "1k"
    aspect_ratio = str(payload.get("aspectRatio") or "").strip() or derive_aspect_ratio_from_size(payload.get("size")) or "16:9"
    aspect_ratio = _normalize_rh_aspect_ratio(aspect_ratio, payload.get("size"))
    body = {
        "prompt": payload.get("prompt") or "",
        "aspectRatio": aspect_ratio,
    }
    # N 系（nano-banana 家族，rhart-image-n-*）：官方文档只接受 prompt/aspectRatio(+imageUrls)，
    # 传 resolution 会被拒（实测 "2K/4K image size is not supported" / "Invalid parameters"）。
    if not str(model or "").startswith("rhart-image-n-"):
        body["resolution"] = resolution
    if model.startswith("rhart-image-g-2-official/"):
        body["quality"] = payload.get("quality") or "medium"
    if refs:
        body["imageUrls"] = [upload_reference(ref) for ref in refs]
    return body


def runninghub_provider_models(providers=None):
    items = providers if isinstance(providers, list) else myridtv_provider.read_api_providers()
    models = []
    for provider in items or []:
        if not isinstance(provider, dict):
            continue
        protocol = str(provider.get("protocol") or "").strip().lower()
        provider_id = str(provider.get("id") or "").strip().lower()
        base_url = str(provider.get("base_url") or "").strip().lower()
        if protocol == "runninghub" or provider_id == "runninghub" or "runninghub" in base_url or provider_id == "custom-api-3":
            models.extend(item for item in (provider.get("image_models") or []) if isinstance(item, str))
    return unique_strings(models or _G_RUNNINGHUB_DEFAULT_IMAGE_MODELS)


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
    key = myridtv_env.read_env_key()
    if not key:
        raise RuntimeError("未找到 RunningHub API Key，请检查 API/.env")
    return key


def runninghub_task_auth_headers():
    return {"Authorization": f"Bearer {runninghub_task_key()}"}


