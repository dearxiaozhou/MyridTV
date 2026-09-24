# -*- coding: utf-8 -*-
"""MyridTV 火山引擎视频域（后端拆分第10刀 V1）：provider 配置、分辨率/比例归一、
媒体 URL 解析与重传判定、参考帧抽取、canvas video 请求体构建与调试摘要、任务
提交/查询/轮询、产物标题与本地化收尾。

逐字迁移自 rh_official_proxy.py 连续块 L(volcengine_provider_config)..L(refresh_canvas_
task_state)（27 函数 565 行，SUBS 可逆还原行级 diff=0）。行为零变更。
已拆模块直引（主文件对应名字即薄代理，等价）：myridtv_http.request_json、
myridtv_provider.read_api_providers、myridtv_task_state.set/update/get_task_state、
myridtv_canvas_store.read_canvas_record、myridtv_media_localize 的
generated_asset_extension/local_media_source_bytes/localize_generated_media_items。
configure() 注入留主文件三函数闭包（def 在注入点后，lambda 延迟解析）：
volcengine_ark_api_key / upload_cloud_media_direct / _task_console_is_cancelled，
+ LOG_FILE getter。主文件对块外仍调用的函数留同名薄代理，调用点不改。
"""
import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from myridtv_core import ApiError, append_log, parse_positive_int, unique_strings

import myridtv_http
import myridtv_provider
import myridtv_task_state
import myridtv_canvas_store
import myridtv_media_localize

_log_file = lambda: None
_r_volcengine_ark_api_key = lambda: ""
_r_upload_cloud_media_direct = None
_r_task_console_is_cancelled = lambda task_id: False
_r_read_chat_key = lambda provider_id='', agent_entry=None: ''


def configure(log_file_getter, volcengine_ark_api_key, upload_cloud_media_direct,
              task_console_is_cancelled, read_chat_key):
    global _log_file, _r_volcengine_ark_api_key
    global _r_upload_cloud_media_direct, _r_task_console_is_cancelled
    global _r_read_chat_key
    _log_file = log_file_getter
    _r_volcengine_ark_api_key = volcengine_ark_api_key
    _r_upload_cloud_media_direct = upload_cloud_media_direct
    _r_task_console_is_cancelled = task_console_is_cancelled
    _r_read_chat_key = read_chat_key


def volcengine_provider_config(provider_id="volcengine"):
    selected = str(provider_id or "volcengine").strip()
    for provider in myridtv_provider.read_api_providers():
        if not isinstance(provider, dict):
            continue
        provider_id_value = str(provider.get("id") or "").strip()
        provider_protocol = str(provider.get("protocol") or "").strip().lower()
        if provider_id_value == selected or (selected == "volcengine" and provider_protocol == "volcengine"):
            return provider
    if selected == "volcengine":
        return {"id": "volcengine", "protocol": "volcengine", "base_url": "https://ark.cn-beijing.volces.com/api/v3"}
    return {}


def is_volcengine_canvas_video_payload(payload):
    provider_id = str((payload or {}).get("provider_id") or "").strip()
    if provider_id == "volcengine":
        return True
    provider = volcengine_provider_config(provider_id)
    return str(provider.get("protocol") or "").strip().lower() == "volcengine"


def volcengine_normalize_resolution(value):
    text = str(value or "").strip().lower()
    aliases = {
        "": "",
        "480": "480p",
        "480p": "480p",
        "720": "720p",
        "720p": "720p",
        "1080": "1080p",
        "1080p": "1080p",
        "1k": "720p",
        "2k": "1080p",
        "4k": "4k",
    }
    return aliases.get(text, text)


def volcengine_normalize_ratio(value):
    text = str(value or "").strip().lower()
    if text in {"wide", "landscape"}:
        return "16:9"
    if text in {"portrait", "vertical"}:
        return "9:16"
    if text in {"square"}:
        return "1:1"
    return text or "adaptive"


def volcengine_video_media_url(source_url):
    text = str(source_url or "").strip()
    if not text:
        return ""
    if text.startswith("asset://"):
        return text
    public_url = volcengine_public_media_url(text)
    if public_url and not volcengine_video_url_needs_reupload(public_url):
        return public_url
    upload_service = os.environ.get("VOLCENGINE_VIDEO_UPLOAD_SERVICE", "volcengine-video").strip() or "volcengine-video"
    uploaded = _r_upload_cloud_media_direct(text, service=upload_service)
    return str(uploaded.get("url") or "").strip()


def volcengine_image_media_url(source_url, max_bytes=12 * 1024 * 1024):
    text = str(source_url or "").strip()
    if not text:
        return ""
    if text.lower().startswith("data:image/"):
        return text
    if text.startswith("asset://"):
        return text
    public_url = volcengine_public_media_url(text)
    if public_url:
        return public_url
    raw, file_name, content_type = myridtv_media_localize.local_media_source_bytes(text)
    mime = str(content_type or mimetypes.guess_type(file_name)[0] or "").strip().lower()
    if not mime.startswith("image/"):
        return ""
    if len(raw) > int(max_bytes):
        raise ApiError(400, f"参考图片过大：{file_name}，请压缩到 12MB 以内。")
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def volcengine_public_media_url(source_url):
    text = str(source_url or "").strip()
    if text.startswith("asset://"):
        return text
    if not re.match(r"^https?://", text, re.I):
        return ""
    parsed = urllib.parse.urlparse(text)
    host = str(parsed.hostname or "").strip().lower()
    if host in {"127.0.0.1", "localhost", "::1"} or host.startswith("192.168.") or host.startswith("10."):
        return ""
    if re.match(r"^172\.(1[6-9]|2[0-9]|3[0-1])\.", host):
        return ""
    return text


def looks_like_video_media_url(source_url):
    text = str(source_url or "").strip().lower()
    if not text:
        return False
    path = urllib.parse.urlparse(text).path or text
    return bool(re.search(r"\.(mp4|mov|m4v|webm|mkv|avi|mpeg|mpg)(?:$|[?#])", path, re.I))


def volcengine_video_url_needs_reupload(source_url):
    try:
        host = str(urllib.parse.urlparse(str(source_url or "")).hostname or "").strip().lower()
    except Exception:
        host = ""
    return host in {"temp.sh", "www.temp.sh"}


def video_reference_to_frame_data_urls(source_url, max_frames=4, max_size=768):
    text = str(source_url or "").strip()
    if not text:
        return []
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        append_log(_log_file(), "volcengine video reference frame extraction skipped: ffmpeg not found")
        return []
    work_dir = tempfile.mkdtemp(prefix="myridtv_video_frames_")
    input_path = ""
    try:
        raw, file_name, content_type = myridtv_media_localize.local_media_source_bytes(text)
        ext = myridtv_media_localize.generated_asset_extension(file_name, content_type, ".mp4")
        input_path = str(Path(work_dir) / f"input{ext}")
        Path(input_path).write_bytes(raw)
        frame_pattern = str(Path(work_dir) / "frame_%02d.jpg")
        vf = f"fps=1,scale={int(max_size)}:-2"
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            input_path,
            "-vf",
            vf,
            "-frames:v",
            str(max(1, int(max_frames))),
            "-q:v",
            "4",
            frame_pattern,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if proc.returncode != 0:
            append_log(_log_file(), f"volcengine video frame extraction failed: {proc.stderr[:500]}")
            return []
        frames = sorted(Path(work_dir).glob("frame_*.jpg"))[:max_frames]
        result = []
        for index, frame in enumerate(frames, start=1):
            encoded = base64.b64encode(frame.read_bytes()).decode("ascii")
            result.append(f"data:image/jpeg;base64,{encoded}")
        return result
    except Exception as exc:
        append_log(_log_file(), f"volcengine video frame extraction failed url={text[:120]}: {exc}")
        return []
    finally:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass


def volcengine_video_reference_content_items(source_url, max_frames=4, max_size=768, force_frames=False):
    text = str(source_url or "").strip()
    if not text:
        return []
    if not force_frames and text.startswith("asset://"):
        return [{
            "type": "video_url",
            "video_url": {"url": text},
            "role": "reference_video",
        }]
    public_video_url = ""
    if not force_frames:
        try:
            public_video_url = volcengine_video_media_url(text)
        except Exception as exc:
            append_log(_log_file(), f"volcengine video reference upload failed, fallback to frames url={text[:120]}: {exc}")
        if public_video_url and looks_like_video_media_url(public_video_url):
            return [{
                "type": "video_url",
                "video_url": {"url": public_video_url},
                "role": "reference_video",
            }]
        if public_video_url:
            append_log(_log_file(), f"volcengine video reference uploaded url is not video-like, fallback to frames url={public_video_url[:120]}")
    else:
        append_log(_log_file(), f"volcengine video reference forced frame_extract url={text[:120]}")
    frame_urls = video_reference_to_frame_data_urls(text, max_frames=max_frames, max_size=max_size)
    if frame_urls:
        append_log(_log_file(), f"volcengine video reference using extracted frames count={len(frame_urls)} url={text[:120]}")
    return [
        {
            "type": "image_url",
            "image_url": {"url": frame_url},
            "role": "reference_image",
        }
        for frame_url in frame_urls
        if frame_url
    ]


def volcengine_image_role(source, index=0, image_count=0):
    raw = str((source or {}).get("role") or "").strip().lower()
    aliases = {
        "first": "first_frame",
        "start": "first_frame",
        "first_frame": "first_frame",
        "last": "last_frame",
        "end": "last_frame",
        "last_frame": "last_frame",
        "reference": "reference_image",
        "reference_image": "reference_image",
        "ref": "reference_image",
        "image": "reference_image",
    }
    if raw in aliases:
        return aliases[raw]
    if image_count <= 1:
        return "first_frame"
    return "reference_image"


def volcengine_video_role(source):
    raw = str((source or {}).get("role") or "").strip().lower()
    if raw in {"reference_video", "video", "reference", "ref"}:
        return "reference_video"
    return "reference_video"


def volcengine_video_content(payload):
    prompt = str((payload or {}).get("prompt") or "").strip()
    if not prompt:
        raise ApiError(400, "缺少视频提示词")
    content = [{"type": "text", "text": prompt}]
    reference_mode = str((payload or {}).get("reference_mode") or "").strip().lower()
    force_video_frames = reference_mode in {"frame_extract", "frames", "extract_frames"}
    images = (payload or {}).get("images") or []
    for index, item in enumerate(images):
        source = item if isinstance(item, dict) else {"url": item}
        media_url = volcengine_image_media_url(source.get("url") or source.get("path") or source.get("src") or "")
        if media_url:
            content.append({
                "type": "image_url",
                "image_url": {"url": media_url},
                "role": volcengine_image_role(source, index, len(images)),
            })
    for item in (payload or {}).get("videos") or []:
        source = item if isinstance(item, dict) else {"url": item}
        raw_video_url = source.get("url") or source.get("path") or source.get("src") or ""
        if not raw_video_url:
            continue
        video_items = volcengine_video_reference_content_items(raw_video_url, force_frames=force_video_frames)
        if not video_items:
            raise ApiError(400, "视频参考处理失败：无法读取视频或抽取关键帧。请确认视频文件存在，或使用素材库 asset:// 视频。")
        content.extend(video_items)
    return content


def volcengine_canvas_video_body(payload):
    model = str((payload or {}).get("model") or "").strip()
    if not model:
        raise ApiError(400, "缺少火山视频模型")
    body = {
        "model": model,
        "content": volcengine_video_content(payload),
    }
    duration = parse_positive_int((payload or {}).get("duration"))
    if duration is not None:
        if "seedance-2-0" in model.lower() or "seedance-1-5" in model.lower():
            duration = max(4, min(15, duration))
        body["duration"] = duration
    ratio = volcengine_normalize_ratio((payload or {}).get("aspect_ratio") or (payload or {}).get("ratio"))
    if ratio:
        body["ratio"] = ratio
    resolution = volcengine_normalize_resolution((payload or {}).get("resolution"))
    if resolution:
        body["resolution"] = resolution
    body["watermark"] = bool((payload or {}).get("watermark"))
    if bool((payload or {}).get("generate_audio")):
        body["generate_audio"] = True
    if bool((payload or {}).get("enhance_prompt")):
        body["enhance_prompt"] = True
    return body


def volcengine_content_debug_summary(content):
    result = []
    for index, item in enumerate(content or []):
        if not isinstance(item, dict):
            result.append({"index": index, "type": type(item).__name__})
            continue
        item_type = str(item.get("type") or "")
        url = ""
        for key in ("image_url", "video_url", "audio_url"):
            value = item.get(key)
            if isinstance(value, dict):
                url = str(value.get("url") or "")
                if url:
                    break
        host = ""
        if url.startswith("asset://"):
            host = "asset"
        elif url:
            try:
                host = urllib.parse.urlparse(url).hostname or ""
            except Exception:
                host = ""
        result.append({
            "index": index,
            "type": item_type,
            "role": item.get("role"),
            "host": host,
            "url_prefix": url[:80],
        })
    return result


def volcengine_base_url(provider):
    return str((provider or {}).get("base_url") or "https://ark.cn-beijing.volces.com/api/v3").strip().rstrip("/")


def volcengine_extract_task_id(data):
    if not isinstance(data, dict):
        return ""
    direct = data.get("id") or data.get("task_id") or data.get("taskId")
    if direct:
        return str(direct).strip()
    nested = data.get("data")
    if isinstance(nested, dict):
        return volcengine_extract_task_id(nested)
    return ""


def volcengine_response_status(data):
    if not isinstance(data, dict):
        return ""
    for key in ("status", "task_status", "taskStatus", "state"):
        value = str(data.get(key) or "").strip().lower()
        if value:
            return value
    nested = data.get("data")
    if isinstance(nested, dict):
        return volcengine_response_status(nested)
    return ""


def volcengine_failure_message(data):
    if not isinstance(data, dict):
        return str(data or "")
    for key in ("error", "message", "detail", "fail_reason", "failReason"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = volcengine_failure_message(value)
            if nested:
                return nested
    nested = data.get("data")
    if isinstance(nested, dict):
        return volcengine_failure_message(nested)
    return ""


def volcengine_user_error_message(error):
    text = str(error or "").strip()
    lower = text.lower()
    if "accountoverdueerror" in lower or "overdue balance" in lower:
        return "火山引擎账户欠费或余额不足，方舟接口返回 403，请在火山控制台充值或结清账单后再生视频。"
    if "authentication" in lower or "unauthorized" in lower or "invalid api key" in lower:
        return "火山引擎 API Key 无效或无权限，请检查方舟 API Key 和模型权限。"
    if "quota" in lower or "insufficient" in lower:
        return "火山引擎额度不足或超过配额，请检查账户额度、并发限制和模型权限。"
    if text.startswith("HTTP 403"):
        return f"火山引擎拒绝请求：{text}"
    return text or "火山引擎请求失败"


def volcengine_collect_video_urls(data):
    urls = []
    seen = set()
    video_keys = {"video_url", "videoUrl", "mp4_url", "mp4Url", "download_url", "downloadUrl", "output_url", "outputUrl"}

    def add(value):
        if isinstance(value, str):
            text = value.strip()
            if text and text not in seen:
                seen.add(text)
                urls.append(text)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, dict):
            walk(value)

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in video_keys:
                    add(child)
                elif isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)
    return urls


def handle_volcengine_canvas_video(payload):
    provider = volcengine_provider_config((payload or {}).get("provider_id") or "volcengine")
    base_url = volcengine_base_url(provider)
    api_key = _r_volcengine_ark_api_key()
    headers = {"Authorization": f"Bearer {api_key}"}
    body = volcengine_canvas_video_body(payload)
    append_log(
        _log_file(),
        "volcengine video submit model="
        + str(body.get("model") or "")
        + " content="
        + json.dumps(volcengine_content_debug_summary(body.get("content")), ensure_ascii=False),
    )
    try:
        submit = myridtv_http.request_json(f"{base_url}/contents/generations/tasks", "POST", body, headers=headers, timeout=180)
    except Exception as exc:
        raise RuntimeError(volcengine_user_error_message(exc)) from exc
    task_id = volcengine_extract_task_id(submit)
    if not task_id:
        raise RuntimeError(f"火山视频任务提交失败，未返回任务 ID：{submit}")
    query_url = f"{base_url}/contents/generations/tasks/{urllib.parse.quote(task_id)}"
    last = {}
    for _ in range(720):
        time.sleep(2500 / 1000)
        last = myridtv_http.request_json(query_url, "GET", headers=headers, timeout=90)
        status = volcengine_response_status(last)
        if status in {"succeeded", "success", "completed", "done"}:
            urls = volcengine_collect_video_urls(last)
            if not urls:
                raise RuntimeError(f"火山视频任务已成功，但未返回 video_url：{last}")
            videos = myridtv_media_localize.localize_generated_media_items([{"url": url, "kind": "video"} for url in urls], "video")
            return {"ok": True, "videos": videos, "task_id": task_id, "backend": "volcengine-ark", "raw": {"submit": submit, "result": last}}
        if status in {"failed", "error", "cancelled", "canceled"}:
            detail = volcengine_failure_message(last) or "火山视频任务失败"
            raise RuntimeError(detail)
    raise RuntimeError(f"火山视频任务超时：{task_id}")


def query_volcengine_video_task(provider_id, provider_task_id, localize=False, canvas_title="", canvas_id=""):
    task_id = str(provider_task_id or "").strip()
    if not task_id:
        raise RuntimeError("缺少火山视频任务 ID")
    provider = volcengine_provider_config(provider_id or "volcengine")
    base_url = volcengine_base_url(provider)
    api_key = _r_volcengine_ark_api_key()
    query_url = f"{base_url}/contents/generations/tasks/{urllib.parse.quote(task_id)}"
    try:
        data = myridtv_http.request_json(query_url, "GET", headers={"Authorization": f"Bearer {api_key}"}, timeout=90)
    except Exception as exc:
        raise RuntimeError(volcengine_user_error_message(exc)) from exc
    status = volcengine_response_status(data)
    urls = volcengine_collect_video_urls(data)
    if urls and status not in {"failed", "error", "cancelled", "canceled"}:
        videos = [{"url": url, "kind": "video"} for url in urls]
        if localize:
            videos = myridtv_media_localize.localize_generated_media_items(videos, "video", canvas_title, canvas_id)
        return {
            "status": "succeeded",
            "result": {"ok": True, "videos": videos, "task_id": task_id, "backend": "volcengine-ark", "raw": {"result": data}},
            "provider_task_id": task_id,
            "raw_status": status,
        }
    if status in {"succeeded", "success", "completed", "done"}:
        raise RuntimeError(f"火山视频任务已成功，但未返回 video_url：{data}")
    if status in {"failed", "error", "cancelled", "canceled"}:
        detail = volcengine_failure_message(data) or "火山视频任务失败"
        return {"status": "failed", "error": detail, "provider_task_id": task_id, "raw": data, "raw_status": status}
    return {"status": "running", "provider_task_id": task_id, "raw": data, "raw_status": status or "running"}


def poll_volcengine_video_task(local_task_id):
    for _ in range(720):
        time.sleep(2500 / 1000)
        if _r_task_console_is_cancelled(local_task_id):
            return
        state = myridtv_task_state.get_task_state(local_task_id)
        if not state or state.get("status") != "running":
            return
        provider_task_id = state.get("provider_task_id") or state.get("volcengine_task_id")
        try:
            queried = query_volcengine_video_task(state.get("provider_id") or "volcengine", provider_task_id, localize=True, canvas_title=str(state.get("canvas_title") or ""), canvas_id=str(state.get("canvas_id") or ""))
            if queried.get("status") == "succeeded":
                myridtv_task_state.update_task_state(local_task_id, status="succeeded", result=queried.get("result") or {}, completed_at=time.time(), raw_status=queried.get("raw_status") or "")
                append_log(_log_file(), f"volcengine video task succeeded local_task_id={local_task_id} provider_task_id={provider_task_id}")
                return
            if queried.get("status") == "failed":
                myridtv_task_state.update_task_state(local_task_id, status="failed", error=queried.get("error") or "火山视频任务失败", completed_at=time.time(), raw=queried.get("raw"), raw_status=queried.get("raw_status") or "")
                append_log(_log_file(), f"volcengine video task failed local_task_id={local_task_id} provider_task_id={provider_task_id} error={queried.get('error')}")
                return
            myridtv_task_state.update_task_state(local_task_id, status="running", checked_at=time.time(), raw_status=queried.get("raw_status") or "running")
        except Exception as exc:
            myridtv_task_state.update_task_state(local_task_id, status="running", checked_at=time.time(), last_error=str(exc))
            append_log(_log_file(), f"volcengine video task poll failed local_task_id={local_task_id}: {exc}")
    myridtv_task_state.update_task_state(local_task_id, status="failed", error="火山视频任务超时", completed_at=time.time())


def _volcengine_canvas_title_for_output(canvas_id):
    cid = str(canvas_id or "").strip()
    if not cid:
        return ""
    try:
        return str(myridtv_canvas_store.read_canvas_record(cid).get("title") or "")
    except Exception:
        return ""


def submit_volcengine_canvas_video_task(payload):
    provider_id = (payload or {}).get("provider_id") or "volcengine"
    provider = volcengine_provider_config(provider_id)
    base_url = volcengine_base_url(provider)
    api_key = _r_volcengine_ark_api_key()
    body = volcengine_canvas_video_body(payload)
    append_log(
        _log_file(),
        "volcengine video submit model="
        + str(body.get("model") or "")
        + " content="
        + json.dumps(volcengine_content_debug_summary(body.get("content")), ensure_ascii=False),
    )
    try:
        submit = myridtv_http.request_json(f"{base_url}/contents/generations/tasks", "POST", body, headers={"Authorization": f"Bearer {api_key}"}, timeout=180)
    except Exception as exc:
        raise RuntimeError(volcengine_user_error_message(exc)) from exc
    provider_task_id = volcengine_extract_task_id(submit)
    if not provider_task_id:
        raise RuntimeError(f"火山视频任务提交失败，未返回任务 ID：{submit}")
    local_task_id = "volc_" + uuid.uuid4().hex
    myridtv_task_state.set_task_state(local_task_id, {
        "status": "running",
        "persistent": True,
        "backend": "volcengine-ark",
        "provider_id": provider_id,
        "provider_task_id": provider_task_id,
        "submit": submit,
        "created_at": time.time(),
        "canvas_id": str((payload or {}).get("canvas_id") or ""),
        "canvas_title": str((payload or {}).get("canvas_title") or _volcengine_canvas_title_for_output((payload or {}).get("canvas_id"))),
        "model": str(body.get("model") or ""),
        "resolution": str((payload or {}).get("resolution") or ""),
        "count": (payload or {}).get("count") or 1,
        "mode": ("i2v" if (isinstance(body.get("content"), list) and body.get("content") and (body["content"][0].get("image_url") or body["content"][0].get("image"))) else "t2v"),
        "node_id": str((payload or {}).get("node_id") or "").strip(),
    }, persistent=True)
    append_log(_log_file(), f"volcengine video task submitted local_task_id={local_task_id} provider_task_id={provider_task_id}")
    threading.Thread(target=poll_volcengine_video_task, args=(local_task_id,), daemon=True).start()
    return {"ok": True, "task_id": local_task_id, "provider_task_id": provider_task_id, "status": "running", "backend": "volcengine-ark"}


VOLCENGINE_PLAN_DEFAULT_CHAT_MODELS = [
    "deepseek-v4-flash",
    "glm-5.3-flash",
    "doubao-seed-2.1-turbo",
    "minimax-m3",
    "glm-5.3",
    "kimi-k2.7-code",
    "deepseek-v4-pro",
    "kimi-k3",
]


def is_volcengine_plan_base(base_url=""):
    return "/api/plan/" in str(base_url or "").strip().lower()


def volcengine_plan_chat_models(extra=None):
    merged = list(VOLCENGINE_PLAN_DEFAULT_CHAT_MODELS)
    for item in (extra or []):
        text = str(item or "").strip()
        if text and text not in merged:
            merged.append(text)
    return merged


def volcengine_fetch_models(payload):
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    api_key = str(payload.get("api_key") or "").strip()
    # Fallback: read from env file if not provided in payload
    if not api_key:
        api_key = _r_volcengine_ark_api_key()
    if not api_key:
        return {"ok": False, "status": 0, "message": "请先填写或保存方舟 API Key", "detail": "缺少 API Key", "all": [], "image_models": [], "video_models": [], "chat_models": [], "model_count": 0, "total": 0}
    # 火山「推理计划」plan 端点是 OpenAI 兼容对话入口，只提供 /chat/completions，不提供 /models。
    # 这类地址用于 Agent 对话，不用于图像/视频任务，因此验证地址按对话端点处理（404 属正常）。
    if "/api/plan/" in base_url:
        plan_models = volcengine_plan_chat_models()
        return {
            "ok": True,
            "protocol": "volcengine",
            "source": "volcengine-plan-chat",
            "all": plan_models,
            "image_models": [],
            "video_models": [],
            "chat_models": plan_models,
            "total": len(plan_models),
            "model_count": len(plan_models),
            "status": 200,
            "message": "方舟推理计划(plan)对话端点可用。该端点不提供模型列表，Agent 模型可直接输入模型名（如 deepseek-v4-flash）。",
        }
    models_url = f"{base_url}/models"
    try:
        data = myridtv_http.request_json(models_url, "GET", headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
    except Exception as exc:
        return {"ok": False, "status": 0, "message": f"请求失败: {exc}", "detail": f"请求失败: {exc}", "all": [], "image_models": [], "video_models": [], "chat_models": [], "model_count": 0, "total": 0}
    raw_models = data.get("data") or []
    all_models = unique_strings([str(m.get("id") or "").strip() for m in raw_models if isinstance(m, dict) and str(m.get("id") or "").strip()])
    image_models = [m for m in all_models if re.search(r"seedream|seededit|t2i|i2i|image", m, re.I)]
    video_models = [m for m in all_models if re.search(r"seedance|t2v|i2v|wan2", m, re.I)]
    chat_models = [m for m in all_models if not re.search(r"seedream|seededit|seedance|t2i|i2v|t2v|wan2|seed3d|3d-|embedding", m, re.I)]
    return {
        "ok": True,
        "protocol": "volcengine",
        "source": "volcengine-ark-api",
        "all": all_models,
        "image_models": image_models,
        "video_models": video_models,
        "chat_models": chat_models,
        "total": len(all_models),
        "model_count": len(all_models),
    }


def is_volcengine_request(payload):
    protocol = str((payload or {}).get("protocol") or "").strip().lower()
    provider_id = str((payload or {}).get("provider_id") or "").strip().lower()
    base_url = str((payload or {}).get("base_url") or "").strip().lower()
    return protocol == "volcengine" or provider_id == "volcengine" or "volces.com" in base_url


def openai_probe_payload(payload, action="test"):
    """自定义 OpenAI 兼容平台：本地(:3107)直接探 {base_url}/models，不再转发 :3000 内部服务。"""
    payload = payload if isinstance(payload, dict) else {}
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    provider_id = str(payload.get("provider_id") or "").strip()
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key and provider_id:
        try:
            api_key = _r_read_chat_key(provider_id) or ""
        except Exception:
            api_key = ""
    empty = {"all": [], "image_models": [], "video_models": [], "chat_models": [], "model_count": 0, "total": 0}
    if not base_url:
        return {"ok": False, "protocol": "openai", "status": 0, "status_code": 0,
                "source": "openai-models", "message": "请先填写请求地址", "detail": "缺少请求地址", **empty}
    urls = [f"{base_url}/models"]
    if not base_url.endswith("/v1"):
        urls.append(f"{base_url}/v1/models")
    data = None
    last_error = None
    for url in urls:
        try:
            data = myridtv_http.request_json(url, "GET", headers={"Authorization": f"Bearer {api_key}"} if api_key else {}, timeout=30)
            break
        except Exception as exc:
            last_error = exc
    if data is None:
        msg = f"请求失败: {last_error}"
        return {"ok": False, "protocol": "openai", "status": 0, "status_code": 0,
                "source": "openai-models", "message": msg, "detail": msg, **empty}
    raw_models = data.get("data") or []
    all_models = unique_strings([str(m.get("id") or "").strip() for m in raw_models if isinstance(m, dict) and str(m.get("id") or "").strip()])
    image_models = [m for m in all_models if re.search(r"image|seedream|seededit|t2i|i2i|flux|sd3|dalle", m, re.I)]
    video_models = [m for m in all_models if re.search(r"video|seedance|t2v|i2v|kling", m, re.I) and m not in image_models]
    chat_models = [m for m in all_models if m not in image_models and m not in video_models]
    result = {
        "ok": True,
        "protocol": "openai",
        "source": "openai-models",
        "status": 200,
        "status_code": 200,
        "all": all_models,
        "image_models": image_models,
        "video_models": video_models,
        "chat_models": chat_models,
        "total": len(all_models),
        "model_count": len(all_models),
    }
    if api_key:
        result["message"] = f"地址与 API Key 验证通过，共 {len(all_models)} 个模型。"
    else:
        result["message"] = f"地址可达（共 {len(all_models)} 个模型），但未填写 API Key——保存 Key 后才能确认鉴权通过。"
    result["raw"] = {"provider_id": provider_id, "base_url": base_url, "protocol": "openai", "total": len(all_models)}
    return result


def volcengine_probe_payload(payload, action="test"):
    result = volcengine_fetch_models(payload if isinstance(payload, dict) else {})
    result["protocol"] = "volcengine"
    result["source"] = "volcengine-ark-api"
    result["status_code"] = result.get("status") or (200 if result.get("ok") else 0)
    result["raw"] = {
        "provider_id": (payload or {}).get("provider_id") or "",
        "base_url": (payload or {}).get("base_url") or "",
        "protocol": "volcengine",
        "total": result.get("total") or 0,
    }
    if result.get("ok"):
        result["status"] = 200
        result["message"] = result.get("message") or "火山引擎方舟地址验证通过，模型列表已同步。"
    else:
        result["message"] = result.get("message") or result.get("detail") or "火山引擎方舟地址验证失败"
    return result


def submit_volcengine_agent_task(payload):
    """Agent 生图链路：火山引擎生成（图像/视频统一走 contents/generations/tasks）"""
    provider_id = str((payload or {}).get("provider_id") or "volcengine").strip()
    provider = volcengine_provider_config(provider_id)
    base_url = volcengine_base_url(provider)
    api_key = _r_volcengine_ark_api_key()
    model = str((payload or {}).get("model") or "").strip()
    if not model:
        raise RuntimeError("缺少火山生成模型")
    content = [{"type": "text", "text": str((payload or {}).get("prompt") or "").strip()}]
    refs = (payload or {}).get("reference_images") or []
    if isinstance(refs, list):
        for ref in refs:
            url = str(ref or "").strip()
            if url:
                content.append({"type": "image_url", "image_url": {"url": url}, "role": "reference_image"})
    body = {"model": model, "content": content}
    ratio = volcengine_normalize_ratio((payload or {}).get("aspect_ratio") or (payload or {}).get("ratio"))
    if ratio:
        body["ratio"] = ratio
    resolution = volcengine_normalize_resolution((payload or {}).get("resolution"))
    if resolution:
        body["resolution"] = resolution
    body["watermark"] = False
    try:
        submit = myridtv_http.request_json(f"{base_url}/contents/generations/tasks", "POST", body, headers={"Authorization": f"Bearer {api_key}"}, timeout=180)
    except Exception as exc:
        raise RuntimeError(volcengine_user_error_message(exc)) from exc
    provider_task_id = volcengine_extract_task_id(submit)
    if not provider_task_id:
        raise RuntimeError(f"火山生成任务提交失败，未返回任务 ID：{submit}")
    return provider_task_id, submit


def poll_volcengine_agent_task(local_task_id):
    for _ in range(720):
        time.sleep(2500 / 1000)
        state = myridtv_task_state.get_task_state(local_task_id)
        if not state or state.get("status") != "running":
            return
        provider_task_id = state.get("provider_task_id") or state.get("volcengine_task_id")
        try:
            queried = query_volcengine_video_task(state.get("provider_id") or "volcengine", provider_task_id, localize=True, canvas_title=str(state.get("canvas_title") or ""), canvas_id=str(state.get("canvas_id") or ""))
            if queried.get("status") == "succeeded":
                myridtv_task_state.update_task_state(local_task_id, status="succeeded", result=queried.get("result") or {}, completed_at=time.time(), raw_status=queried.get("raw_status") or "")
                append_log(_log_file(), f"volcengine agent task succeeded local_task_id={local_task_id} provider_task_id={provider_task_id}")
                return
            if queried.get("status") == "failed":
                myridtv_task_state.update_task_state(local_task_id, status="failed", error=queried.get("error") or "火山生成任务失败", completed_at=time.time(), raw=queried.get("raw"), raw_status=queried.get("raw_status") or "")
                append_log(_log_file(), f"volcengine agent task failed local_task_id={local_task_id} provider_task_id={provider_task_id} error={queried.get('error')}")
                return
            myridtv_task_state.update_task_state(local_task_id, status="running", checked_at=time.time(), raw_status=queried.get("raw_status") or "running")
        except Exception as exc:
            myridtv_task_state.update_task_state(local_task_id, status="running", checked_at=time.time(), last_error=str(exc))
            append_log(_log_file(), f"volcengine agent task poll failed local_task_id={local_task_id}: {exc}")
    myridtv_task_state.update_task_state(local_task_id, status="failed", error="火山生成任务超时", completed_at=time.time())
