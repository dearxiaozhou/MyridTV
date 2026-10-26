# -*- coding: utf-8 -*-
"""MyridTV HTTP 底座（后端拆分第1刀）：TLS 兼容层 + JSON/multipart 请求 + 瞬时错误重试。

逐字迁移自 rh_official_proxy.py（区段 _RH_TLS_CTX_CACHE..request_multipart_text），
行为零变更。唯一外部依赖 runninghub_api_base 由主文件 configure() 注入
（未注入时回退 RH 官方域名，与主文件缺省一致）。主文件保留同名薄代理，调用点不改。
"""
import json
import random
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

_RH_TLS_CTX_CACHE = {}
_rh_api_base_getter = lambda: "https://www.runninghub.ai"


def configure(rh_api_base_getter):
    """主文件启动时注入 runninghub_api_base 的读取闭包。"""
    global _rh_api_base_getter
    _rh_api_base_getter = rh_api_base_getter


def _rh_forced_tls_context(url=""):
    """RunningHub 网关（OpenResty）与部分 OpenSSL 版本（如 3.0.x）的 TLS 1.3 记录层
    存在兼容缺陷，表现为 SSLV3_ALERT_BAD_RECORD_MAC（同机同网 TLS 1.2 实测 100% 通、
    TLS 1.3 约半数失败）。对 RH 域名请求强制 TLS 1.2，证书验证保持完整（实测 8/8）。

    2026-09-22 根治画布 Flare 出图「直接报错」。仅匹配 RH 主机名，其它上游不受影响。"""
    try:
        host = urllib.parse.urlparse(str(url or "")).hostname or ""
    except Exception:
        return None
    base = _rh_api_base_getter()
    rh_host = ""
    try:
        rh_host = urllib.parse.urlparse(base).hostname or "runninghub.ai"
    except Exception:
        rh_host = "runninghub.ai"
    if not host or (host != rh_host and not host.endswith(".runninghub.ai") and "runninghub" not in host):
        return None
    key = (sys.version_info[:2], ssl.OPENSSL_VERSION)
    ctx = _RH_TLS_CTX_CACHE.get(key)
    if ctx is not None:
        return ctx
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_default_certs()
        ctx.load_verify_locations(cafile=ssl.get_default_verify_paths().openssl_cafile)
    except Exception:
        try:
            ctx = ssl._create_default_https_context()
            ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        except Exception:
            ctx = None
    _RH_TLS_CTX_CACHE[key] = ctx
    return ctx


def _rh_urlopen(url, req, timeout, ssl_ctx):
    """RH 主机直连、其它主机维持默认（含环境变量代理）。

    2026-10-27 真事故：本机用户级环境变量设了 https_proxy=http://127.0.0.1:7897，
    而该端口只做明文 HTTP 转发、不接 HTTPS 的 CONNECT 隧道。urllib 的 urlopen 默认
    把环境变量代理套进来，于是 App 进程里对 RunningHub 的所有 HTTPS 请求在 TLS 握手
    阶段就被掐断 —— URLError(SSLEOFError(8,'[SSL: UNEXPECTED_EOF_WHILE_READING]'))，
    后台一条任务记录都没有（请求压根没到 RH）。实测复现：直连 5/5 HTTP 200、
    http_proxy 走同一端口 5/5 200、https_proxy 走同一端口 3/3 EOF。

    ProxyHandler({}) 显式空代理即可绕过；只作用于 RH 主机，LLM 供应商 / 火山 / 本地
    ComfyUI 这些可能确实需要代理出海的调用保持原行为不动。
    """
    if not _is_rh_host(url):
        return urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl_ctx),
    )
    return opener.open(req, timeout=timeout)


def _is_rh_host(url=""):
    try:
        host = (urllib.parse.urlparse(str(url or "")).hostname or "").strip().lower()
    except Exception:
        return False
    if not host:
        return False
    if host == "runninghub.ai" or host.endswith(".runninghub.ai") or "runninghub" in host:
        return True
    try:
        rh_host = (urllib.parse.urlparse(_rh_api_base_getter()).hostname or "").strip().lower()
    except Exception:
        rh_host = ""
    return bool(rh_host) and (host == rh_host or host.endswith("." + rh_host))


def request_json(url, method="GET", payload=None, headers=None, timeout=120):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36")
    req.add_header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    ssl_ctx = _rh_forced_tls_context(url)
    try:
        with _rh_urlopen(url, req, timeout, ssl_ctx) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            detail = json.loads(raw)
        except Exception:
            detail = raw
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def _rh_request_with_retry(url, method="GET", payload=None, headers=None, timeout=120, attempts=5):
    """RunningHub API 请求带网络抖动重试。

    只用于 RH 提交/查询链路。RH 官方网关偶发 SSL/连接层瞬时错误
    （SSLV3_ALERT_BAD_RECORD_MAC / 502 / EOF），这类抖动重试即可成功；
    业务错误（HTTP 4xx / 明确的 RH code）不重试，直接抛。

    2026-10-27：旧策略「3 次 + 封顶 4s」太密——同一批并发任务会在同一秒集体重试，
    RH 侧把这种同步重试判为频率异常并直接断 TLS（客户端只看到 SSL EOF）。
    改为 5 次 + 指数退避封顶 15s + 随机抖动：既给上游恢复窗口，又把重试点打散
    （累计等待上限约 29s + 抖动）。
    """
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return request_json(url, method=method, payload=payload, headers=headers, timeout=timeout)
        except RuntimeError as exc:
            # HTTP 业务错误：4xx 不重试（参数错/权限错），5xx 重试
            msg = str(exc)
            is_server_err = any(marker in msg for marker in ("HTTP 5", "HTTP 502", "HTTP 503", "HTTP 504"))
            if not is_server_err and not _is_transient_network_error(msg):
                raise
            last_exc = exc
        except Exception as exc:
            last_exc = exc
            if not _is_transient_network_error(str(exc)):
                raise
        if attempt < attempts:
            time.sleep(_rh_retry_delay(attempt))
    raise RuntimeError(f"RunningHub 请求重试 {attempts} 次仍失败：{last_exc}") from last_exc


_RH_RETRY_BASE_DELAY = 2.0
_RH_RETRY_MAX_DELAY = 15.0


def _rh_retry_delay(attempt):
    """第 attempt 次失败后的等待秒数：2→4→8→15s 封顶的指数退避 + 随机抖动。

    抖动（0 ~ min(1.5s, 30%)）用于打散同步重试风暴：没有它时同一瞬间提交的
    N 个任务会在完全相同的时间点重试第二次、第三次……
    """
    index = max(0, int(attempt or 1) - 1)
    base = min(_RH_RETRY_MAX_DELAY, _RH_RETRY_BASE_DELAY * (2 ** index))
    return base + random.uniform(0.0, min(1.5, base * 0.3))


def _is_transient_network_error(msg):
    """判断是否网络瞬时错误（值得重试）。"""
    msg = str(msg or "")
    markers = (
        "SSLV3_ALERT_BAD_RECORD_MAC",
        "ssl", "SSL",
        "EOF occurred",
        "Connection reset",
        "ConnectionReset",
        "timed out",
        "Timeout",
        "Temporary failure",
        "RemoteDisconnected",
        "Bad Gateway",
        "502",
        "503",
        "504",
        "unexpected EOF",
    )
    return any(m in msg for m in markers)


def request_multipart_json(url, fields=None, files=None, headers=None, timeout=120):
    boundary = "----MyridTV" + uuid.uuid4().hex
    body = bytearray()
    for name, value in (fields or {}).items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value or "").encode("utf-8"))
        body.extend(b"\r\n")
    for file_info in files or []:
        field_name = str(file_info.get("name") or "file")
        file_name = str(file_info.get("filename") or "upload.bin")
        content_type = str(file_info.get("content_type") or "application/octet-stream")
        raw = file_info.get("data") or b""
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{file_name}"\r\n'.encode("utf-8")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(raw)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    req = urllib.request.Request(url, data=bytes(body), method="POST")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36")
    req.add_header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    ssl_ctx = _rh_forced_tls_context(url)
    try:
        with _rh_urlopen(url, req, timeout, ssl_ctx) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            detail = json.loads(raw)
        except Exception:
            detail = raw
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def request_multipart_text(url, fields=None, files=None, headers=None, timeout=180):
    boundary = "----MyridTV" + uuid.uuid4().hex
    body = bytearray()
    for name, value in (fields or {}).items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value or "").encode("utf-8"))
        body.extend(b"\r\n")
    for file_info in files or []:
        field_name = str(file_info.get("name") or "file")
        file_name = str(file_info.get("filename") or "upload.bin")
        content_type = str(file_info.get("content_type") or "application/octet-stream")
        raw = file_info.get("data") or b""
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{file_name}"\r\n'.encode("utf-8")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(raw)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    req = urllib.request.Request(url, data=bytes(body), method="POST")
    req.add_header("Accept", "text/plain, application/json;q=0.9, */*;q=0.8")
    req.add_header("User-Agent", "MyridTV/1.0")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    ssl_ctx = _rh_forced_tls_context(url)
    try:
        with _rh_urlopen(url, req, timeout, ssl_ctx) as resp:
            return resp.read().decode("utf-8", "replace").strip()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code}: {raw}") from exc



__all__ = [
    "_RH_TLS_CTX_CACHE",
    "_rh_forced_tls_context",
    "request_json",
    "_rh_request_with_retry",
    "_rh_retry_delay",
    "_is_transient_network_error",
    "request_multipart_json",
    "request_multipart_text",
    "configure",
]


def request_text(url, timeout=60):
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "text/plain, text/markdown, text/html;q=0.9, */*;q=0.8")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36")
    ssl_ctx = _rh_forced_tls_context(url)
    try:
        with _rh_urlopen(url, req, timeout, ssl_ctx) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code}: {raw or 'RunningHub 文档请求失败'}")
