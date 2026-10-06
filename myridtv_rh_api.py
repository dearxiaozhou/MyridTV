# -*- coding: utf-8 -*-
"""RH API 地址与资产上传域（后端拆分第34刀自 rh_official_proxy.py 逐字外移）：
平台地址跟随用户 API 设置（含 /openapi/v2 双路径归一）、URL 拼接、
二进制/任务资产上传（本地媒体→RH asset）。零主文件全局依赖。"""
import time
import socket
import urllib.error
import urllib.parse
import myridtv_http
import myridtv_media_localize
import myridtv_provider
import myridtv_runninghub_build


def runninghub_api_base():
    """RH 平台地址跟随用户在 API 设置里的配置（2026-09-10 解锁）；缺省回退官方域名。"""
    base = "https://www.runninghub.ai"
    try:
        for item in myridtv_provider.read_api_providers():
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


def _rh_upload_multipart_retry(url, fields, files, headers, timeout):
    """RH 素材上传偶发网络写超时（urllib The write operation timed out）。
    最多重试 3 次，仅重试底层网络错误；HTTP 错误已在 request_multipart_json
    内转 RuntimeError 冒泡，不在此重试。2026-09-29 修。"""
    last_exc = None
    for attempt in range(3):
        try:
            return myridtv_http.request_multipart_json(
                url, fields=fields, files=files, headers=headers, timeout=timeout
            )
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(3)
                continue
            raise
    if last_exc is not None:
        raise last_exc


def runninghub_upload_binary_media(source_url):
    raw, file_name, content_type = myridtv_media_localize.local_media_source_bytes(source_url)
    data = _rh_upload_multipart_retry(
        runninghub_api_url("/openapi/v2/media/upload/binary"),
        fields=None,
        files=[{"name": "file", "filename": file_name, "content_type": content_type, "data": raw}],
        headers=myridtv_runninghub_build.runninghub_task_auth_headers(),
        timeout=600,
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
    raw, file_name, content_type = myridtv_media_localize.local_media_source_bytes(source_url)
    data = _rh_upload_multipart_retry(
        runninghub_api_url("/task/openapi/upload"),
        # RH 旧版 /task/openapi/upload 的鉴权要求 apiKey 作为 multipart 表单字段一起提交
        # （官方 curl 示例里 apiKey 是 --form）。只带 Authorization: Bearer 会被拒：
        # {"code":-1,"msg":"apiKey is required"}。2026-09-16 修。
        fields={"fileType": "input", "apiKey": myridtv_runninghub_build.runninghub_task_key()},
        files=[{"name": "file", "filename": file_name, "content_type": content_type, "data": raw}],
        headers=myridtv_runninghub_build.runninghub_task_auth_headers(),
        timeout=600,
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
