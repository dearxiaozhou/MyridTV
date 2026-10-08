# -*- coding: utf-8 -*-
"""MyridTV RunningHub 文档/目录域（后端拆分第9刀）：RH 请求判定、国际站公开模型目录
详情与 API 文档索引爬取（解析图像 route）、live 模型目录（缓存 TTL）、
模型目录聚合与 probe payload 构建。

从 rh_official_proxy.py 迁移 RH 请求判定、文档解析、目录缓存和 probe 逻辑，
并扩展国际站公开模型目录详情同步。configure() 注入 request_text/request_json 闭包、
RUNNINGHUB_DEFAULT_IMAGE_MODELS/USER_DATA_DIR 值、LOG_FILE getter。
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
_r_request_json = None
_DEFAULT_IMAGE_MODELS = []
_USER_DATA_DIR = None
_log_file = lambda: None
RUNNINGHUB_CATALOG_CACHE_FILE = None
RUNNINGHUB_CATALOG_CACHE_TTL_SECONDS = 6 * 3600


def configure(request_text, default_image_models, user_data_dir, log_file_getter, request_json=None):
    global _r_request_text, _r_request_json, _DEFAULT_IMAGE_MODELS, _USER_DATA_DIR, _log_file
    _r_request_text = request_text
    _r_request_json = request_json
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


def _runninghub_catalog_response_data(response, label):
    if not isinstance(response, dict):
        raise RuntimeError(f"RunningHub {label}接口返回格式无效")
    code = response.get("code")
    if code not in (None, 0, "0"):
        message = str(response.get("msg") or response.get("message") or "请求失败").strip()
        raise RuntimeError(f"RunningHub {label}接口失败：{message}")
    data = response.get("data")
    return data if isinstance(data, dict) else {}


def runninghub_catalog_image_routes(origin):
    """从 RunningHub 国际站公开目录读取图像模型，再用详情接口提取真实 API route。"""
    if not callable(_r_request_json):
        return []

    headers = {
        "Origin": origin,
        "Referer": f"{origin}/call-api/search-api/standard-model",
    }
    list_payload = {
        "categoryType": "STANDARD_MODEL",
        "tagIds": [],
        "search": "",
        "categoryTagIds": [],
        "owners": [],
        "isWhitelist": False,
        "isCollected": False,
        "region": "",
        "pageNum": 1,
        "pageSize": 999,
        "sortType": "POPULAR",
    }
    data = _runninghub_catalog_response_data(
        _r_request_json(
            f"{origin}/api/sku/list", method="POST", payload=list_payload,
            headers=headers, timeout=30,
        ),
        "模型目录",
    )
    page = data.get("page") if isinstance(data.get("page"), dict) else {}
    records = list(page.get("records") or [])
    try:
        page_count = int(page.get("pages") or 1)
    except (TypeError, ValueError):
        page_count = 1
    for page_num in range(2, max(1, page_count) + 1):
        list_payload["pageNum"] = page_num
        page_data = _runninghub_catalog_response_data(
            _r_request_json(
                f"{origin}/api/sku/list", method="POST", payload=list_payload,
                headers=headers, timeout=30,
            ),
            "模型目录",
        )
        page_info = page_data.get("page") if isinstance(page_data.get("page"), dict) else {}
        records.extend(page_info.get("records") or [])
    image_records = [
        record for record in records
        if isinstance(record, dict)
        and str(record.get("categoryName") or "").strip().lower() in {"text-to-image", "image-to-image"}
        and str(record.get("id") or "").strip()
    ]
    if not image_records:
        raise RuntimeError("RunningHub 模型目录未返回图像模型条目")

    def route_of(record):
        try:
            detail_response = _r_request_json(
                f"{origin}/api/sku/detail",
                method="POST",
                payload={"id": str(record.get("id") or "")},
                headers=headers,
                timeout=20,
            )
            detail = _runninghub_catalog_response_data(detail_response, "模型详情")
            route = str(detail.get("rhEndpoint") or "").strip()
            if not route:
                return ""
            route = re.sub(r"^https?://[^/]+", "", route, flags=re.IGNORECASE)
            route = route.lstrip("/")
            if route.lower().startswith("openapi/v2/"):
                route = route[len("openapi/v2/"):]
            return route if runninghub_is_image_route(route) else ""
        except Exception:
            return ""

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as executor:
        routes = list(executor.map(route_of, image_records))
    models = unique_strings(route for route in routes if route)
    if not models:
        raise RuntimeError("未能从 RunningHub 模型详情解析到图像 API 路由")
    return models


def _runninghub_crawl_document_image_routes(origin):
    index_text = _r_request_text(f"{origin}{RUNNINGHUB_DOC_INDEX_PATH}", timeout=30)
    doc_urls = runninghub_doc_urls_from_index(index_text)
    if not doc_urls:
        return []

    def route_of(doc_url):
        try:
            return runninghub_route_from_doc(_r_request_text(doc_url, timeout=20))
        except Exception:
            return ""

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=10) as executor:
        routes = list(executor.map(route_of, doc_urls))
    return unique_strings(
        route for route in (str(route or "").strip() for route in routes)
        if route and runninghub_is_image_route(route)
    )


def _runninghub_crawl_image_routes_with_source(origin):
    errors = []
    catalog_models = []
    try:
        catalog_models = runninghub_catalog_image_routes(origin)
    except Exception as exc:
        errors.append(str(exc))

    doc_models = []
    try:
        doc_models = _runninghub_crawl_document_image_routes(origin)
    except Exception as exc:
        errors.append(str(exc))

    models = unique_strings(catalog_models + doc_models)
    if not models:
        detail = "; ".join(error for error in errors if error)
        raise RuntimeError(detail or "未能从 RunningHub 官方目录或文档解析到图像模型")
    source = "runninghub-catalog-live" if catalog_models else "runninghub-docs-live"
    return models, source


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
    """抓公开模型目录及官方文档，解析每个图像模型的真实 API route。"""
    return _runninghub_crawl_image_routes_with_source(origin)[0]


def runninghub_live_model_catalog(base_url, force=False):
    models = [] if force else (_runninghub_read_catalog_cache() or [])
    source = "runninghub-catalog-cache"
    detail = ""
    if not models:
        source = "runninghub-docs-live"
        try:
            origin = runninghub_doc_origin(base_url)
            models, source = _runninghub_crawl_image_routes_with_source(origin)
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
        "source": result.get("source") or "runninghub-catalog-live",
    }
    if action == "probe":
        result["message"] = "RunningHub 协议已识别，模型列表实时同步自官方模型目录和 API 文档。"
    else:
        if result.get("source") == "runninghub-address-check":
            result["message"] = "RunningHub 地址验证通过，模型列表来自内置/已维护配置。"
        else:
            result["message"] = "RunningHub 地址验证通过，模型列表已实时同步官方目录和 API 文档。"
    return result


