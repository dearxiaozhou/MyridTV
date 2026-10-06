# -*- coding: utf-8 -*-
"""通用生图平台通道（2026-09-28）：OpenAI 兼容协议的自定义 API 平台按自身配置出图。

背景：旧版把 provider_id=custom-api-3 硬编码成 RunningHub 别名，导致用户新配的
API 平台（如土豆网关）请求被发去 RunningHub 烧企业余额。本模块改为「按配置路由」：
凡 protocol=openai 且 base_url 不含 runninghub 的平台，一律走自己的 base_url +
平台 Key（API_PROVIDER_<ID>_KEY），与 RunningHub 彻底解绑。

协议（对 aitudou.net 网关实测，2026-09-28）：
- 提交 POST {base}/image/generations（平台 image_generation_endpoint 可覆盖路径），
  body={model, prompt, size(ratio 写法), metadata:{resolution}, images:[参考图URL]}；
  成功返回 {task_id}。部分网关忽略 size 里的 W*H 而吃 "WxH"，失败时自动降级重试。
- 轮询 GET {base}/image/generations/{task_id}，兼容两种返回形态：
  {status, images|data.images|result_url|data.content.image_url|data.output.*}
  与 {code, data:{status, result_url, data:{content:{image_url}}, fail_reason}}。
- 结果 URL 24h 内必须下载：本地化沿用画布任务通用 localize 链。
"""
import json
import math as _math
import re
import time
import urllib.parse
import urllib.request

import myridtv_core
import myridtv_env
import myridtv_http
import myridtv_provider

# 与 ComfyUI-TDNodes 一致：部分网关对 Python 默认 UA 有拦截。
_PROVIDER_IMAGE_UA = "ComfyUI-TDNodes"
# 提交时保留的通用字段；网关报错「size must be one of」等会点名正确字段，
# 因此这里宁多勿少，未识别字段一般被上游忽略。
_SUBMIT_ALLOWED_KEYS = (
    "model", "prompt", "size", "aspect_ratio", "resolution",
    "n", "metadata", "images", "seed", "quality", "response_format",
)
_SUCCESS_STATUSES = {"SUCCESS", "SUCCEEDED", "COMPLETED", "DONE", "FINISHED"}
_FAILURE_STATUSES = {"FAILED", "FAILURE", "FAIL", "ERROR", "CANCELED", "CANCELLED", "REJECTED", "TIMEOUT"}
_TRANSIENT_MARKERS = ("SEC_E_MESSAGE_ALTERED", "SSL", "ssl", "EOF", "Connection", "reset", "timed out", "Timeout")
# 提交被上游以参数错拒绝时允许自动降级的字段
_RETRY_STRIP_FIELDS = ("size", "metadata", "n")

_LOG_GETTER = lambda: None
_POLL_TIMEOUT_GETTER = lambda: 1800
_closures = {}
_cancel_check = lambda local_task_id: False


class ProviderTaskCancelled(Exception):
    """用户在任务控制台点了停止。"""


def configure(log_file_getter, poll_timeout_getter, closures=None):
    global _LOG_GETTER, _POLL_TIMEOUT_GETTER, _closures, _cancel_check
    _LOG_GETTER = log_file_getter
    _POLL_TIMEOUT_GETTER = poll_timeout_getter
    _closures = dict(closures or {})
    _cancel_check = _closures.get("is_cancelled") or (lambda local_task_id: False)


def is_generic_image_provider(provider):
    """协议=openai 且不是 RunningHub 系（id/base_url 任一带 runninghub 都算 RH）。"""
    if not isinstance(provider, dict):
        return False
    protocol = str(provider.get("protocol") or "").strip().lower()
    provider_id = str(provider.get("id") or "").strip().lower()
    base_url = str(provider.get("base_url") or "").strip().lower()
    if "runninghub" in provider_id or "runninghub" in base_url:
        return False
    return protocol == "openai" and bool(base_url)


def resolve_generic_image_provider(provider_id):
    """命中返回 provider dict；未命中返回 None。runninghub 平台永远返回 None（走 RH 原链）。"""
    provider_id = str(provider_id or "").strip()
    if not provider_id:
        return None
    # runninghub 永远走原 RH 链（工作流/RH币/会员 key 选择链不得触碰）
    if provider_id == "runninghub":
        return None
    for provider in myridtv_provider.read_api_providers() or []:
        if not isinstance(provider, dict):
            continue
        if str(provider.get("id") or "").strip() != provider_id:
            continue
        if provider.get("enabled") is False:
            return None
        return provider if is_generic_image_provider(provider) else None
    return None


def generic_image_base_url(provider):
    base = str(provider.get("base_url") or "").strip().rstrip("/")
    if not base:
        raise RuntimeError(f"生图平台 {provider.get('id')} 缺少 base_url")
    return base


def generic_image_endpoint(provider):
    """提交端点：平台 image_generation_endpoint 覆盖优先（相对路径拼到 base_url）。"""
    base = generic_image_base_url(provider)
    override = str(provider.get("image_generation_endpoint") or "").strip()
    if override:
        if override.startswith("http://") or override.startswith("https://"):
            return override
        path = override if override.startswith("/") else "/" + override
        return base + path
    return base + "/image/generations"


def generic_image_key(provider_id):
    env_name = myridtv_env.provider_key_env_name(provider_id)
    values = myridtv_env.read_env_values()
    value = str(values.get(env_name) or "").strip()
    if not value:
        raise RuntimeError(f"生图平台 {provider_id} 未配置 API Key（{env_name}）")
    return value


def _generic_headers(provider_id):
    return {
        "Authorization": "Bearer " + generic_image_key(provider_id),
        "Content-Type": "application/json",
        "User-Agent": _PROVIDER_IMAGE_UA,
    }


def _generic_request(url, method, payload, headers, timeout, provider_id, api_error_prefix):
    last_exc = None
    for attempt in range(1, 4):
        try:
            return myridtv_http.request_json(url, method=method, payload=payload, headers=headers, timeout=timeout)
        except RuntimeError as exc:
            last_exc = exc
            if any(marker in str(exc) for marker in _TRANSIENT_MARKERS):
                time.sleep(min(2 ** attempt, 4))
                continue
            raise RuntimeError(f"{api_error_prefix} 请求失败：{exc}") from exc
        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            if any(marker in msg for marker in _TRANSIENT_MARKERS):
                time.sleep(min(2 ** attempt, 4))
                continue
            raise RuntimeError(f"{api_error_prefix} 请求失败：{msg}") from exc
    raise RuntimeError(f"{api_error_prefix} 重试后仍失败：{last_exc}")


def _ref_to_public_url(ref):
    """参考图转公网 URL：http(s) 直传；本地素材走闭包注入的公共上传（网关要能拉到）。"""
    url = ref.get("url") if isinstance(ref, dict) else str(ref or "")
    url = str(url or "").strip()
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    prepare = _closures.get("prepare_reference")
    if not prepare:
        raise RuntimeError(f"参考图 {url[:60]} 需要先上传公网，但未注入上传通道")
    return str(prepare(url) or "")


def _ref_is_fetchable(url):
    """参考图 URL 必须公网直接可下载（文档要求）；探一次 Range GET。"""
    try:
        req = urllib.request.Request(str(url), headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36",
            "Range": "bytes=0-0",
        })
        with urllib.request.urlopen(req, timeout=12) as r:
            r.read(1)
            return int(getattr(r, "status", 200) or 200) < 400
    except Exception:
        return False


def _upload_to_provider_files(provider_id, provider, raw_bytes, file_name, content_type):
    """平台自带素材上传（Tudou: POST {base}/files/upload，免费、24h 直链）。失败返回 ''。"""
    url = generic_image_base_url(provider) + "/files/upload"
    last_exc = None
    for attempt in range(3):
        try:
            data = myridtv_http.request_multipart_json(
                url,
                files=[{"name": "file", "filename": file_name, "content_type": content_type or "application/octet-stream", "data": raw_bytes}],
                headers={"Authorization": "Bearer " + generic_image_key(provider_id)},
                timeout=300,
            )
            if isinstance(data, dict):
                u = str(data.get("url") or (data.get("data") or {}).get("url") or "").strip()
                if u.startswith("http"):
                    myridtv_core.append_log(_LOG_GETTER(), f"[ProviderImage] ref rehosted via provider upload provider={provider_id} url={u[:100]}")
                    return u
        except Exception as exc:
            last_exc = exc
            time.sleep(2 * (attempt + 1))
    myridtv_core.append_log(_LOG_GETTER(), f"[ProviderImage] provider files/upload failed provider={provider_id}: {str(last_exc)[:150]}")
    return ""


def _rehost_reference(source, provider_id, provider):
    """把不可达/本地素材换成公网直链：平台 files/upload 优先，公共图床兜底。"""
    import myridtv_media_localize
    raw_bytes, file_name, content_type = myridtv_media_localize.local_media_source_bytes(source)
    u = _upload_to_provider_files(provider_id, provider, raw_bytes, file_name, content_type)
    if u:
        return u
    errors = []
    for service in ("litterbox", "temp"):
        try:
            u = myridtv_media_localize.upload_cloud_media_bytes(raw_bytes, file_name, content_type, service=service)
            myridtv_core.append_log(_LOG_GETTER(), f"[ProviderImage] ref rehosted via cloud({service}) url={str(u)[:100]}")
            return u
        except Exception as exc:
            errors.append(f"{service}: {str(exc)[:80]}")
    raise RuntimeError("参考图换链失败：" + "；".join(errors))


def generic_prepare_references(refs, provider_id, provider=None):
    urls = []
    if provider is None:
        provider = resolve_generic_image_provider(provider_id) or {}
    for ref in refs or []:
        url = str(ref.get("url") if isinstance(ref, dict) else ref or "").strip()
        if not url:
            continue
        if url.startswith("http://") or url.startswith("https://"):
            if _ref_is_fetchable(url):
                if url not in urls:
                    urls.append(url)
                continue
            # 不可达（典型：结果图 CDN 对爬虫 403，上游会异步报"settings not supported"）→ 自动换链
            myridtv_core.append_log(_LOG_GETTER(), f"[ProviderImage] ref not fetchable, rehosting url={url[:100]}")
            try:
                fresh = _rehost_reference(url, provider_id, provider)
            except Exception as exc:
                raise RuntimeError(f"参考图换链失败（原链接不可下载）：{url[:80]}｜{exc}") from exc
            if fresh and fresh not in urls:
                urls.append(fresh)
            continue
        # 本地素材（/assets/... 等）：同样走平台上传优先
        try:
            fresh = _rehost_reference(url, provider_id, provider)
        except Exception as exc:
            prepare = _closures.get("prepare_reference")
            if not prepare:
                raise RuntimeError(f"参考图 {url[:60]} 需要先上传公网，但未注入上传通道") from exc
            fresh = str(prepare(url) or "")
        if fresh and fresh not in urls:
            urls.append(fresh)
    return urls


def _build_submit_body(model, prompt, refs, payload):
    resolution = str(payload.get("resolution") or "").strip().lower()
    if resolution not in {"1k", "2k", "4k"}:
        size_text = str(payload.get("size") or "").strip().lower()
        resolution = size_text if size_text in {"1k", "2k", "4k"} else ""
        if not resolution:
            match = re.match(r"^\s*(\d+)\s*[xX*]\s*(\d+)\s*$", size_text)
            if match:
                longest = max(int(match.group(1)), int(match.group(2)))
                resolution = "1k" if longest <= 1024 else ("2k" if longest <= 2048 else "4k")
    ratio = str(payload.get("aspectRatio") or payload.get("ratio") or "").strip()
    if not ratio:
        ratio = str(payload.get("size") or "").strip()
    # WxH 像素写法先约分成比例：g2.5 系只吃 ratio，提交时不报错但排队后异步 FAILURE（"settings not supported"），
    # 降级链拦不住这种"提交成功、运行失败"，必须提交前就折好。qwen 类只吃 W*H，会 HTTP400 走降级链处理。
    folded = _pixel_size_to_ratio(ratio) or ratio
    body = {"model": model, "prompt": prompt}
    if folded:
        body["size"] = folded
        body["aspect_ratio"] = folded
    if resolution:
        body["metadata"] = {"resolution": resolution}
    count = payload.get("count") or payload.get("n")
    if isinstance(count, int) and count > 1:
        body["n"] = count
    if refs:
        body["images"] = refs
    return {k: v for k, v in body.items() if k in _SUBMIT_ALLOWED_KEYS and v is not None}


def _pixel_size_to_ratio(value):
    dims = re.match(r"^\s*(\d+)\s*[xX*]\s*(\d+)\s*$", str(value or ""))
    if not dims:
        return ""
    width, height = int(dims.group(1)), int(dims.group(2))
    if width <= 0 or height <= 0:
        return ""
    divisor = _math.gcd(width, height) or 1
    return f"{width // divisor}:{height // divisor}"


def _strip_retryable(body, message):
    """上游以 size/参数非法拒绝（含 HTTP 4xx）：按优先级生成降级变体，逐一试错。"""
    msg = str(message or "").lower()
    if "size" not in msg and "aspect" not in msg and "resolution" not in msg and "metadata" not in msg:
        return None
    variants = []
    size = body.get("size")
    if isinstance(size, str) and size:
        ratio = _pixel_size_to_ratio(size)
        if ratio:  # 像素写法 -> 约分成比例写法（部分网关只吃 ratio）
            variants.append({**body, "size": ratio})
        swapped = size.replace("*", "x") if "*" in size else (size.replace("x", "*") if "x" in size else size)
        if swapped != size:
            variants.append({**body, "size": swapped})
        variants.append({k: v for k, v in body.items() if k != "size"})  # 省略让上游 auto
        variants.append({k: v for k, v in body.items() if k not in ("size", "aspect_ratio")})
    if "resolution" in msg or "metadata" in msg:
        variants.append({k: v for k, v in body.items() if k != "metadata"})
    for variant in variants:
        if variant != body:
            return variant
    return None


def _task_id_from(data):
    for key in ("task_id", "taskId", "id"):
        value = str(data.get(key) or "").strip()
        if value:
            return value
    nested = data.get("data")
    if isinstance(nested, dict):
        return _task_id_from(nested)
    return ""


def _error_message_from(data):
    for key in ("message", "error", "fail_reason", "failReason", "detail"):
        value = data.get(key)
        if isinstance(value, dict):
            value = value.get("message") or json.dumps(value, ensure_ascii=False)
        text = str(value or "").strip()
        if text:
            return text[:300]
    nested = data.get("data")
    if isinstance(nested, dict):
        return _error_message_from(nested)
    return ""


def submit_generic_image(provider_id, model, prompt, refs, payload):
    provider = resolve_generic_image_provider(provider_id)
    if not provider:
        raise RuntimeError(f"生图平台 {provider_id} 不存在或未启用")
    endpoint = generic_image_endpoint(provider)
    headers = _generic_headers(provider_id)
    body = _build_submit_body(model, prompt, generic_prepare_references(refs, provider_id, provider), payload or {})
    api_error_prefix = str(provider.get("name") or provider_id)
    last_error = ""
    for _ in range(5):  # 最多 5 次降级（variants 链）：HTTP 4xx 业务错误同样尝试修参重试
        try:
            data = _generic_request(endpoint, "POST", body, headers, 120, provider_id, api_error_prefix)
            # 同步返回型（OpenAI 标准 images/generations 直接吐图）：无 task_id 但有图 = 即时成功
            inline = []
            _collect_image_urls(data, inline)
            if not _task_id_from(data) and inline:
                myridtv_core.append_log(_LOG_GETTER(), f"[ProviderImage] submitted(sync) provider={provider_id} model={model} images={len(inline)}")
                return "inline-" + str(int(time.time() * 1000)), {"inline_images": inline, "raw": data}
            task_id = _task_id_from(data)
            if task_id:
                myridtv_core.append_log(_LOG_GETTER(), "[ProviderImage] submitted provider={} model={} task={} size={}".format(
                    provider_id, model, task_id, body.get("size") or "-"))
                return task_id, data
            last_error = _error_message_from(data) or json.dumps(data, ensure_ascii=False)[:300]
        except RuntimeError as exc:
            msg = str(exc)
            if "HTTP 4" not in msg:
                raise
            last_error = msg
        variant = _strip_retryable(body, last_error)
        if variant is None:
            break
        myridtv_core.append_log(_LOG_GETTER(), f"[ProviderImage] submit retry-stripped provider={provider_id} err={last_error[:120]}")
        body = variant
    raise RuntimeError(f"{api_error_prefix} 提交失败：{last_error}")


def _collect_image_urls(node, out):
    if isinstance(node, str):
        if node.startswith("http://") or node.startswith("https://"):
            if node not in out:
                out.append(node)
        return
    if isinstance(node, dict):
        for key in ("url", "image_url", "imageUrl", "image", "result_url", "resultUrl", "signed_url"):
            value = node.get(key)
            if isinstance(value, str) and (value.startswith("http://") or value.startswith("https://")):
                if value not in out:
                    out.append(value)
            elif isinstance(value, dict):
                _collect_image_urls(value.get("url") or value, out)
        for key in ("images", "data", "content", "output", "results", "result"):
            if key in node:
                _collect_image_urls(node[key], out)


def query_generic_image(provider_id, task_id):
    provider = resolve_generic_image_provider(provider_id)
    if not provider:
        raise RuntimeError(f"生图平台 {provider_id} 不存在或未启用")
    url = generic_image_endpoint(provider) + "/" + urllib.parse.quote(str(task_id))
    headers = _generic_headers(provider_id)
    data = _generic_request(url, "GET", None, headers, 60, provider_id, str(provider.get("name") or provider_id))
    body = data.get("data") if isinstance(data.get("data"), dict) else data
    status = str(body.get("status") or body.get("state") or body.get("task_status") or data.get("status") or "").upper().replace("-", "_")
    urls = []
    _collect_image_urls(body, urls)
    # qwen 等返回 data.content.image_url 在 data 层
    if isinstance(data.get("data"), dict):
        _collect_image_urls(data["data"], urls)
    result = {"status": status, "urls": urls, "raw": data}
    if status in _FAILURE_STATUSES:
        result["failReason"] = _error_message_from(body) or _error_message_from(data) or "生图平台任务失败"
    return result


def poll_generic_result(provider_id, task_id, deadline=None, local_task_id=""):
    """轮询到终态。超时抛「查询超时」，调用方转成 running 态由刷新路由续轮询。
    local_task_id=画布任务 id：用户点停止后必须立刻退出，不得再覆盖 cancelled 态。"""
    end = deadline or (time.time() + _POLL_TIMEOUT_GETTER())
    last = ""
    while time.time() < end:
        if local_task_id and _cancel_check(local_task_id):
            raise ProviderTaskCancelled("用户手动停止")
        try:
            info = query_generic_image(provider_id, task_id)
        except Exception as exc:
            last = str(exc)
            time.sleep(5)
            continue
        last = json.dumps(info.get("raw") or {}, ensure_ascii=False)[:300]
        status = info.get("status")
        if status in _SUCCESS_STATUSES:
            urls = info.get("urls") or []
            if urls:
                myridtv_core.append_log(_LOG_GETTER(), "[ProviderImage] succeeded provider={} task={} images={}".format(provider_id, task_id, len(urls)))
                # images 用字符串 URL 列表，与 poll_result（RH 官方链）同构
                return {"images": list(urls), "task_id": task_id, "backend": "provider-openai", "raw": info.get("raw"), "provider_id": provider_id}
            time.sleep(3)
            continue
        if status in _FAILURE_STATUSES:
            reason = info.get("failReason") or last
            myridtv_core.append_log(_LOG_GETTER(), "[ProviderImage] task-failed provider={} task={} reason={}".format(provider_id, task_id, str(reason)[:200]))
            raise RuntimeError(reason)
        time.sleep(3)
    raise RuntimeError(f"生图平台查询超时：{last}")


def poll_generic_result_checked(provider_id, task_id, local_task_id, deadline=None):
    """run_task 用：带取消检查的包装，取消异常原样上抛由 run_task 保持 cancelled 态。"""
    return poll_generic_result(provider_id, task_id, deadline=deadline, local_task_id=local_task_id)
