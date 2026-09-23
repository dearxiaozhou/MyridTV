# -*- coding: utf-8 -*-
"""MyridTV RunningHub 文档/目录域（后端拆分第9刀）：RH 请求判定、官方 API 文档索引
爬取（llms.txt → 逐文档 route 抽取 → 生图 route 过滤）、live 模型目录（缓存 TTL）、
模型目录聚合与 probe payload 构建。

逐字迁移自 rh_official_proxy.py 三片连续区段（P1 判定+文档常量带 / P2 文档解析族 /
P3 catalog 缓存+目录+probe，可逆还原行级 diff=0）。行为零变更。
configure() 注入：request_text 闭包（HTTP 拉文档仍走主文件底座）、
RUNNINGHUB_DEFAULT_IMAGE_MODELS/USER_DATA_DIR 值（零重绑）、LOG_FILE getter。
主文件留 is_runninghub_request/runninghub_model_catalog/runninghub_probe_payload
三个薄代理 + RUNNINGHUB_DEFAULT_IMAGE_MODELS 别名。catalog 缓存常量
（依赖 USER_DATA_DIR）在 configure() 时求值。
"""
import json
import re
import time
import urllib.parse

from myridtv_core import unique_strings, write_json_file

_r_request_text = None
_DEFAULT_IMAGE_MODELS = []
_USER_DATA_DIR = None
_log_file = lambda: None
RUNNINGHUB_CATALOG_CACHE_FILE = None
RUNNINGHUB_CATALOG_CACHE_TTL_SECONDS = 6 * 3600


def configure(request_text, default_image_models, user_data_dir, log_file_getter):
    global _r_request_text, _DEFAULT_IMAGE_MODELS, _USER_DATA_DIR, _log_file
    _r_request_text = request_text
    _DEFAULT_IMAGE_MODELS = default_image_models
    _USER_DATA_DIR = user_data_dir
    _log_file = log_file_getter

    # catalog 路径常量（原块顶层，依赖注入值 USER_DATA_DIR → 挪入本函数，第7刀配方）
    global RUNNINGHUB_CATALOG_CACHE_FILE
    RUNNINGHUB_CATALOG_CACHE_FILE = _USER_DATA_DIR / "data" / "rh_live_model_catalog.json"


def is_runninghub_request(payload):
    protocol = str((payload or {}).get("protocol") or "").strip().lower()
    provider_id = str((payload or {}).get("provider_id") or "").strip().lower()
    base_url = str((payload or {}).get("base_url") or "").strip().lower()
    return protocol == "runninghub" or provider_id == "runninghub" or "runninghub" in base_url


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
    index_text = _r_request_text(f"{origin}{RUNNINGHUB_DOC_INDEX_PATH}", timeout=30)
    doc_urls = runninghub_doc_urls_from_index(index_text)
    if not doc_urls:
        raise RuntimeError("RunningHub 文档索引未返回任何图像模型条目")

    def route_of(doc_url):
        try:
            return runninghub_route_from_doc(_r_request_text(doc_url, timeout=20))
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
    image_models = unique_strings(models + _DEFAULT_IMAGE_MODELS)
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
        image_models = unique_strings(_DEFAULT_IMAGE_MODELS)
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


