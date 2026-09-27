# -*- coding: utf-8 -*-
"""MyridTV 媒体本地化域（后端拆分第6刀）：资产输出目录体系、上传解析与落盘、生成物
远程→本地化下载链（save_generated_remote_asset / localize_generated_media_items）、
历史归档移动、打开文件夹目标解析、任务本地化去重锁。

逐字迁移自 rh_official_proxy.py 连续块 L(asset_output_dir)..L(runninghub_api_base) 前
（23 函数 415 行）。行为零变更。
configure() 注入：ASSETS_DIR 值（env 可覆盖但 import 时定、全局零重绑）、LOG_FILE
getter、7 个块外函数 lambda 闭包（comfy_instance_base/get_task_state/
local_media_source_bytes/output_asset_kind_for_name/output_asset_subdir_for_kind/
request_multipart_json/resolve_user_asset_path）。
主文件对块外仍调用的 13 函数留同名薄代理；_canvas_task_localize_lock 缓存归本模块
（其返回的 Lock 对象跨模块同一）。
"""
import json
import mimetypes
import os
import re
import shutil
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import base64

import myridtv_http
import myridtv_env
from myridtv_core import ApiError, append_log

_ASSETS_DIR = None
_USER_DATA_DIR = None
_ROOT = None
_log_file = lambda: None
_r_comfy_instance_base = None
_r_get_task_state = lambda tid: {}
_r_local_media_source_bytes = None
_r_output_asset_kind_for_name = None
_r_output_asset_subdir_for_kind = None
_r_request_multipart_json = None
_r_resolve_user_asset_path = None


def configure(user_data_dir, root, assets_dir, log_file_getter,
              comfy_instance_base, get_task_state, local_media_source_bytes,
              output_asset_kind_for_name, output_asset_subdir_for_kind,
              request_multipart_json, resolve_user_asset_path):
    global _USER_DATA_DIR, _ROOT, _ASSETS_DIR, _log_file
    _USER_DATA_DIR = user_data_dir
    _ROOT = root
    global _r_comfy_instance_base, _r_get_task_state, _r_local_media_source_bytes
    global _r_output_asset_kind_for_name, _r_output_asset_subdir_for_kind
    global _r_request_multipart_json, _r_resolve_user_asset_path
    _ASSETS_DIR = assets_dir
    _log_file = log_file_getter
    _r_comfy_instance_base = comfy_instance_base
    _r_get_task_state = get_task_state
    _r_local_media_source_bytes = local_media_source_bytes
    _r_output_asset_kind_for_name = output_asset_kind_for_name
    _r_output_asset_subdir_for_kind = output_asset_subdir_for_kind
    _r_request_multipart_json = request_multipart_json
    _r_resolve_user_asset_path = resolve_user_asset_path


def asset_output_dir():
    return _ASSETS_DIR / "output"


def asset_output_media_dir(kind="image", canvas_folder=""):
    subdir = _r_output_asset_subdir_for_kind(kind)
    root = asset_output_dir() / str(canvas_folder) if canvas_folder else asset_output_dir()
    result = root / subdir if subdir else root
    result.mkdir(parents=True, exist_ok=True)
    return result


def asset_output_history_dir(kind="image", canvas_folder=""):
    if str(kind or "").strip().lower() == "image":
        return asset_output_media_dir("image", canvas_folder) / "history"
    return (asset_output_dir() / str(canvas_folder) if canvas_folder else asset_output_dir()) / "history"


def asset_output_url(local_name, kind="image", history=False, canvas_folder=""):
    quoted = urllib.parse.quote(str(local_name or ""))
    subdir = _r_output_asset_subdir_for_kind(kind)
    prefix = f"/assets/output/{urllib.parse.quote(str(canvas_folder), safe='')}" if canvas_folder else "/assets/output"
    if history and str(kind or "").strip().lower() == "image":
        return f"{prefix}/images/history/{quoted}"
    if subdir:
        return f"{prefix}/{subdir}/{quoted}"
    return f"{prefix}/{quoted}"


def output_lookup_dirs():
    root = asset_output_dir()
    return (
        root / "images",
        root / "videos",
        root / "images" / "history",
        root / "history",
        root,
    )


def resolve_open_folder_target(url, name="", local_path=""):
    """Resolve canvas image URL/name to a local output file for Explorer /select."""
    text = str(url or "").strip()
    parsed_path = urllib.parse.urlparse(text).path if text else ""
    asset_root = _ASSETS_DIR.resolve()

    local_text = str(local_path or "").strip()
    if local_text:
        try:
            if local_text.lower().startswith("file:"):
                parsed_local = urllib.parse.urlparse(local_text)
                local_target = Path(urllib.request.url2pathname(parsed_local.path)).resolve()
            else:
                local_target = Path(local_text).resolve()
            local_target.relative_to(asset_root)
            return local_target
        except Exception:
            pass

    if parsed_path.startswith("/assets/"):
        try:
            return _r_resolve_user_asset_path(text)
        except ApiError:
            pass

    if parsed_path.startswith("/assets/output/"):
        rel = urllib.parse.unquote(parsed_path[len("/assets/output/"):])
        target = (asset_output_dir() / rel).resolve()
        try:
            target.relative_to(asset_root)
        except Exception:
            return asset_output_dir()
        if target.exists():
            return target
        return target

    clean_name = Path(str(name or "").split("?", 1)[0].split("#", 1)[0]).name
    if clean_name:
        for folder in output_lookup_dirs():
            target = (folder / clean_name).resolve()
            try:
                target.relative_to(asset_root)
            except Exception:
                continue
            if target.exists():
                return target
        return (asset_output_dir() / clean_name).resolve()

    return asset_output_dir()


def asset_input_dir():
    return _ASSETS_DIR / "input"


def generated_asset_extension(file_name="", content_type="", default_ext=".png"):
    for source in (str(file_name or ""), str(content_type or "")):
        if "." in source:
            match = re.search(r"(\.[A-Za-z0-9]{2,8})(?:$|\?)", source)
            if match:
                return match.group(1).lower()
    guessed = mimetypes.guess_extension(str(content_type or "").split(";", 1)[0].strip() or "")
    return (guessed or default_ext or ".png").lower()


def extract_multipart_boundary(content_type=""):
    match = re.search(r'boundary="?([^";]+)"?', str(content_type or ""), re.IGNORECASE)
    return match.group(1) if match else ""


def parse_multipart_files(raw_body, content_type):
    boundary = extract_multipart_boundary(content_type)
    if not boundary:
        raise RuntimeError("上传请求缺少 multipart boundary")
    marker = ("--" + boundary).encode("utf-8")
    files = []
    for part in raw_body.split(marker):
        part = part.strip()
        if not part or part == b"--":
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"--"):
            part = part[:-2]
        header_blob, separator, data = part.partition(b"\r\n\r\n")
        if not separator:
            continue
        header_lines = header_blob.decode("utf-8", "replace").split("\r\n")
        headers = {}
        for line in header_lines:
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
        disposition = headers.get("content-disposition", "")
        filename_match = re.search(r'filename="([^"]*)"', disposition)
        field_match = re.search(r'name="([^"]*)"', disposition)
        if not filename_match:
            continue
        file_name = filename_match.group(1).strip() or f"upload-{uuid.uuid4().hex[:8]}"
        field_name = field_match.group(1).strip() if field_match else "files"
        if data.endswith(b"\r\n"):
            data = data[:-2]
        files.append(
            {
                "field_name": field_name,
                "file_name": file_name,
                "content_type": headers.get("content-type", "application/octet-stream"),
                "data": data,
            }
        )
    return files


def upload_kind_for_file(file_name="", content_type=""):
    mime = str(content_type or "").split(";", 1)[0].strip().lower()
    ext = str(Path(str(file_name or "")).suffix or "").lower()
    if mime.startswith("image/") or ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        return "image"
    if mime.startswith("video/") or ext in {".mp4", ".mov", ".avi", ".webm", ".mkv"}:
        return "video"
    if mime.startswith("audio/") or ext in {".mp3", ".wav", ".ogg", ".m4a", ".flac"}:
        return "audio"
    return "file"


def unique_saved_name(target_dir, saved_name):
    """落盘重名自动避让：xxx.png → xxx-2.png → xxx-3.png …（避免覆盖已有素材）"""
    if not (target_dir / saved_name).exists():
        return saved_name
    # 去掉已有 -N 后缀再递增，避免叠成 xxx-2-2
    stem = re.sub(r"-\d+$", "", Path(saved_name).stem) or Path(saved_name).stem
    suffix = Path(saved_name).suffix
    index = 2
    while index < 1000:
        candidate = f"{stem}-{index}{suffix}"
        if not (target_dir / candidate).exists():
            return candidate
        index += 1
    return f"{stem}-{uuid.uuid4().hex[:6]}{suffix}"


def save_uploaded_file(file_info, target_dir=None, url_prefix=None, kind_subdir=None):
    """通用上传落盘：写进 target_dir，返回以 url_prefix 打头的 URL。

    三个可选参数都由调用方（do_POST 的 scope 分支）给出，用来把上传物归位：
    - target_dir / url_prefix：目标目录与其对外 URL 前缀；
    - kind_subdir：{kind: 子目录名} 映射，按文件实际类型再下一层（图片进 images、
      视频进 videos…），与生成产物的目录约定保持一致。
    三者都缺省时行为与旧版 save_uploaded_input_file 逐字一致（落 assets/input）。
    """
    original_name = str(file_info.get("file_name") or "").strip() or f"upload-{uuid.uuid4().hex[:8]}"
    content_type = str(file_info.get("content_type") or "application/octet-stream")
    data = file_info.get("data") or b""
    ext = generated_asset_extension(original_name, content_type, ".bin")
    kind = upload_kind_for_file(original_name, content_type)
    directory = Path(target_dir) if target_dir else asset_input_dir()
    # 只去首尾多余斜杠再补回前导斜杠：直接 strip("/") 会把 "/assets/..." 的
    # 前导斜杠也吃掉，产出 "assets/xxx" 这种打不开的相对 URL。
    prefix = "/" + str(url_prefix or "").strip().strip("/")
    if str(url_prefix or "").strip() == "":
        try:
            rel = directory.resolve().relative_to(Path(_ASSETS_DIR).resolve())
            prefix = "/assets/" + "/".join(urllib.parse.quote(part) for part in rel.parts)
        except Exception:
            prefix = "/assets/input"
    subdir = ""
    if kind_subdir:
        subdir = str(kind_subdir.get(kind) or kind_subdir.get("*") or "").strip().strip("/")
    if subdir:
        directory = directory / subdir
        prefix = f"{prefix}/{urllib.parse.quote(subdir)}"
    directory.mkdir(parents=True, exist_ok=True)
    saved_name = unique_saved_name(directory, f"ai_ref_{uuid.uuid4().hex[:12]}{ext}")
    (directory / saved_name).write_bytes(data)
    return {
        "url": f"{prefix}/{urllib.parse.quote(saved_name)}",
        "name": original_name,
        "filename": saved_name,
        "kind": kind,
        "content_type": content_type,
    }


def save_uploaded_input_file(file_info):
    """原 input 落盘入口：默认目录即 assets/input，行为逐字不变（保留给未带 scope 的调用方）。"""
    return save_uploaded_file(file_info)


def handle_ai_upload(raw_body, content_type, target_dir=None, url_prefix=None, kind_subdir=None):
    files = parse_multipart_files(raw_body, content_type)
    if not files:
        raise RuntimeError("上传请求里没有文件")
    return {
        "ok": True,
        "files": [
            save_uploaded_file(file_info, target_dir, url_prefix, kind_subdir)
            for file_info in files
        ],
    }


def handle_comfy_upload(raw_body, content_type):
    """Forward canvas image uploads to the configured local ComfyUI instance."""
    files = parse_multipart_files(raw_body, content_type)
    if not files:
        raise ApiError(400, "上传请求里没有文件")
    base = _r_comfy_instance_base()
    uploaded = []
    for file_info in files:
        result = _r_request_multipart_json(
            base + "/upload/image",
            fields={"type": "input", "overwrite": "false"},
            files=[
                {
                    "name": "image",
                    "filename": file_info.get("file_name") or "upload.png",
                    "content_type": file_info.get("content_type") or "application/octet-stream",
                    "data": file_info.get("data") or b"",
                }
            ],
            timeout=120,
        )
        if not isinstance(result, dict):
            raise ApiError(502, "ComfyUI 上传接口返回格式异常")
        name = str(result.get("name") or "").strip()
        subfolder = str(result.get("subfolder") or "").strip().strip("/")
        if not name:
            raise ApiError(502, "ComfyUI 未返回上传文件名")
        comfy_name = "/".join(part for part in (subfolder, name) if part)
        uploaded.append({**result, "comfy_name": comfy_name})
    return {"files": uploaded}


def canvas_output_folder_name(canvas_title="", canvas_id=""):
    """输出素材文件夹名（以画布 ID 为准做唯一锚定，标题仅作可读前缀）。

    返回 ``<清洗后的标题>__<canvas_id>``：标题保留可读、改名仍同步移动；
    ID 后缀保证全局唯一 —— 两个同名画布不再共用同一目录，purge 可精准定位、

    不再需要共享判定。无标题时退回纯 ID 形态 ``c-<id>``（或 ``canvas_default``），

    避免与任何标题撞名。
    """
    cid = str(canvas_id or "").strip()
    raw = str(canvas_title or "").strip()
    if not raw:
        return f"c-{cid}" if cid else "canvas_default"
    safe = re.sub(r'[\\/:*?"<>|]', '_', raw).strip().strip('.')
    if not safe:
        return f"c-{cid}" if cid else "canvas_default"
    safe = safe[:80]
    if cid:
        return f"{safe}__{cid}"
    # 缺 id（极少数历史场景）退回纯标题，保持向后兼容
    return safe


_RECENT_REMOTE_SAVES = {}
_RECENT_REMOTE_SAVES_LOCK = threading.Lock()
# 任务级本地化锁：防止 run_task 后台线程与 refresh_canvas_task_state（前端轮询触发）
# 同时对同一任务的远程结果做本地落盘（竞态导致同一张图落两份，文件序号各+1）。
_CANVAS_TASK_LOCALIZE_LOCKS = {}
_CANVAS_TASK_LOCALIZE_LOCKS_LOCK = threading.Lock()


def _canvas_task_localize_lock(task_id):
    with _CANVAS_TASK_LOCALIZE_LOCKS_LOCK:
        lock = _CANVAS_TASK_LOCALIZE_LOCKS.get(task_id)
        if lock is None:
            lock = threading.Lock()
            _CANVAS_TASK_LOCALIZE_LOCKS[task_id] = lock
        return lock


def _canvas_task_already_localized(task_id):
    state = _r_get_task_state(task_id)
    return bool(state and state.get("status") == "succeeded" and state.get("localized_at"))


def save_generated_remote_asset(source_url, kind="image", display_name="", canvas_title="", canvas_id="", node_title=""):
    if not display_name:
        display_name = str(node_title or "").strip()
    dedup_key = str(source_url or "").strip()
    if dedup_key and not dedup_key.startswith(("/assets/", "/static/", "/output/", "file://", "data:")):
        with _RECENT_REMOTE_SAVES_LOCK:
            cached = _RECENT_REMOTE_SAVES.get(dedup_key)
            if cached and (time.time() - cached.get("_time", 0)) < 600:
                return {k: v for k, v in cached.items() if k != "_time"}
    raw, file_name, content_type = _r_local_media_source_bytes(source_url)
    media_kind = str(kind or "image").strip().lower() or "image"
    ext = generated_asset_extension(file_name, content_type, ".mp4" if media_kind == "video" else ".mp3" if media_kind == "audio" else ".png")
    canvas_folder = canvas_output_folder_name(canvas_title, canvas_id) if canvas_title or canvas_id else ""
    output_dir = asset_output_media_dir(media_kind, canvas_folder)
    # 保持画布原有的日期序号命名；扩展名只保留一份。
    if display_name:
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', str(display_name).strip())[:80]
        safe_name = re.sub(r'\.(?:png|jpe?g|webp|gif|bmp|mp4|webm|mov|m4a|mp3|wav|aac|ogg|flac)(?:_\d+)?$', '', safe_name, flags=re.IGNORECASE)
        safe_name = safe_name.strip().strip('.') or f"{time.strftime('%m-%d')}-01"
        local_name = f"{safe_name}{ext}"
        # 防重名：追加数字
        target = output_dir / local_name
        counter = 1
        while target.exists():
            date_match = re.match(r'^(\d{2}-\d{2})-(\d{2})$', safe_name)
            next_name = f"{date_match.group(1)}-{counter + 1:02d}" if date_match else f"{safe_name}_{counter}"
            local_name = f"{next_name}{ext}"
            target = output_dir / local_name
            counter += 1
    else:
        date_prefix = time.strftime('%m-%d')
        counter = 1
        local_name = f"{date_prefix}-{counter:02d}{ext}"
        target = output_dir / local_name
        while target.exists():
            counter += 1
            local_name = f"{date_prefix}-{counter:02d}{ext}"
            target = output_dir / local_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    result = {
        "url": asset_output_url(local_name, media_kind, canvas_folder=canvas_folder),
        "name": local_name,
        "kind": media_kind,
        "source_url": str(source_url or ""),
        "local_path": str(target),
    }
    if dedup_key and not dedup_key.startswith(("/assets/", "/static/", "/output/", "file://", "data:")):
        with _RECENT_REMOTE_SAVES_LOCK:
            _RECENT_REMOTE_SAVES[dedup_key] = {**result, "_time": time.time()}
    return result


def fallback_generated_media_item(source, kind="image", error=""):
    if not isinstance(source, dict):
        source = {"url": source}
    url = str(source.get("url") or source.get("path") or source.get("src") or source.get("uri") or "").strip()
    media_kind = str(source.get("kind") or source.get("mediaKind") or kind or "image").strip().lower() or "image"
    parsed_name = os.path.basename(urllib.parse.urlparse(url).path)
    name = str(source.get("name") or source.get("display_name") or parsed_name or f"output_{uuid.uuid4().hex[:8]}").strip()
    fallback = dict(source)
    fallback.update({
        "url": url,
        "name": name,
        "kind": media_kind,
        "source_url": str(source.get("source_url") or source.get("sourceUrl") or url),
        "remote_fallback": True,
    })
    if error:
        fallback["localize_error"] = str(error)
    return fallback


def unique_output_target(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    # 与 save_generated_remote_asset 同规则：只滤文件系统非法字符，保留中文（历史节点名多为中文）
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", Path(str(name or "")).name).strip().strip(".") or f"output_{uuid.uuid4().hex[:8]}"
    target = folder / safe_name
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    for index in range(1, 10000):
        candidate = folder / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    return folder / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"


def canvas_output_folder_from_url(url):
    parsed_path = urllib.parse.urlparse(str(url or "")).path or ""
    prefix = "/assets/output/"
    if not parsed_path.startswith(prefix):
        return ""
    parts = [urllib.parse.unquote(part) for part in parsed_path[len(prefix):].split("/") if part]
    if not parts or parts[0] in {"images", "videos", "history"}:
        return ""
    return canvas_output_folder_name(parts[0], "")


def rename_canvas_output_folder(old_title, new_title, canvas_id=""):
    """重命名画布时同步其输出素材文件夹（输出文件夹按画布标题命名）。

    返回 None 表示标题未变 / 无需变更；否则返回
    {"old_folder","new_folder","moved","note"}。
    冲突保护：若目标文件夹已存在（通常是另一同名画布在共享输出目录），
    不移动目录以免覆盖其素材，仅记 note；url 改写仍会把引用指向该共享目录。
    """
    old_folder = canvas_output_folder_name(old_title, canvas_id)
    new_folder = canvas_output_folder_name(new_title, canvas_id)
    if old_folder == new_folder:
        return None
    output_root = asset_output_dir()
    src = output_root / old_folder
    dst = output_root / new_folder
    moved = False
    note = ""
    if src.exists() and src.is_dir():
        if dst.exists():
            note = "target-exists-shared"
        else:
            try:
                src.rename(dst)
                moved = True
            except Exception as exc:  # pragma: no cover - 文件系统异常
                note = "rename-failed:%s" % exc
    return {"old_folder": old_folder, "new_folder": new_folder, "moved": moved, "note": note}


def rewrite_output_urls(obj, old_folder, new_folder):
    """递归改写 obj（画布 dict/list）里所有 /assets/output/<old_folder>/ 形态的 url 为 new_folder。

    同时匹配 quoted 与未 quoted 两种形态（url 实际是 quoted，未 quoted 仅作兜底），
    以便重命名画布后，画布内所有节点/产物/封面引用都指向新文件夹。
    """
    if not old_folder or not new_folder or old_folder == new_folder:
        return obj
    old_q = urllib.parse.quote(old_folder, safe="")
    new_q = urllib.parse.quote(new_folder, safe="")
    if not old_q:
        return obj
    old_raw = urllib.parse.quote(old_folder, safe="/")  # 兜底：极少出现
    prefix_q = "/assets/output/" + old_q
    prefix_raw = "/assets/output/" + old_raw
    new_prefix = "/assets/output/" + new_q

    def walk(o):
        if isinstance(o, str):
            s = o
            if prefix_q in s:
                s = s.replace(prefix_q, new_prefix)
            if prefix_raw in s and prefix_raw != prefix_q:
                s = s.replace(prefix_raw, new_prefix)
            return s
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v) for v in o]
        return o
    return walk(obj)


def move_output_asset_to_history(payload):
    url = str((payload or {}).get("url") or "").strip()
    if not url.startswith("/assets/output/"):
        raise ApiError(400, "不是输出素材路径")
    source = _r_resolve_user_asset_path(url)
    if _r_output_asset_kind_for_name(source.name) != "image":
        return {"ok": True, "moved": url, "url": url, "skipped": True}
    parsed_path = urllib.parse.unquote(urllib.parse.urlparse(url).path or "")
    # 任意层级的 history 目录都算已归档（画布同名子目录的 history 也在其中），防止 history/history 套娃
    if "/history/" in parsed_path:
        return {"ok": True, "moved": url, "url": url, "skipped": True}
    asset_root = _ASSETS_DIR.resolve()
    canvas_folder = canvas_output_folder_from_url(url)
    target = unique_output_target(asset_output_history_dir("image", canvas_folder), source.name).resolve()
    try:
        target.relative_to(asset_root)
    except Exception as exc:
        raise ApiError(403, "forbidden") from exc
    if source.resolve() != target:
        shutil.move(str(source), str(target))
    moved_url = asset_output_url(target.name, "image", history=True, canvas_folder=canvas_folder)
    return {"ok": True, "moved": moved_url, "url": moved_url, "path": str(target)}


def localize_generated_media_items(items, kind="image", canvas_title="", canvas_id="", node_title=""):
    localized = []
    seen_urls = set()
    for item in items or []:
        source = item if isinstance(item, dict) else {"url": item}
        url = str(source.get("url") or source.get("path") or source.get("src") or source.get("uri") or "").strip()
        if not url:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        if url.startswith("/assets/output/"):
            localized.append({
                "url": url,
                "name": str(source.get("name") or os.path.basename(urllib.parse.urlparse(url).path) or ""),
                "kind": str(source.get("kind") or source.get("mediaKind") or kind or "image"),
            })
            continue
        try:
            saved = save_generated_remote_asset(
                url,
                str(source.get("kind") or source.get("mediaKind") or kind or "image"),
                str(source.get("display_name") or source.get("name") or ""),
                canvas_title,
                canvas_id,
                node_title=node_title,
            )
        except Exception as exc:
            append_log(_log_file(), f"generated media localize fallback url={url[:180]} error={exc}")
            localized.append(fallback_generated_media_item(source, kind, exc))
            continue
        if source.get("name"):
            saved["display_name"] = str(source.get("name"))
        localized.append(saved)
    return localized


# ===== 第11刀追加：上传源读取 + 云媒体上传族 =====
def guess_upload_filename(source_url, content_type="application/octet-stream", fallback_prefix="upload"):
    path = urllib.parse.urlparse(str(source_url or "")).path or ""
    name = os.path.basename(path)
    if name:
        return name
    ext = mimetypes.guess_extension(content_type or "application/octet-stream") or ".bin"
    return f"{fallback_prefix}-{uuid.uuid4().hex[:8]}{ext}"


def local_media_source_bytes(source_url):
    text = str(source_url or "").strip()
    if not text:
        raise RuntimeError("缺少素材地址")
    if text.startswith("data:"):
        header, sep, encoded = text.partition(",")
        if not sep:
            raise RuntimeError("data URL 格式错误")
        content_type = header[5:].split(";", 1)[0].strip() or "application/octet-stream"
        if ";base64" in header.lower():
            raw = base64.b64decode(encoded)
        else:
            raw = urllib.parse.unquote_to_bytes(encoded)
        return raw, f"data-{uuid.uuid4().hex[:8]}{generated_asset_extension('', content_type, '.bin')}", content_type
    if text.startswith("/assets/"):
        target = _r_resolve_user_asset_path(text)
        return target.read_bytes(), target.name, mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    if text.startswith("/static/"):
        relative = urllib.parse.urlparse(text).path[len("/static/"):]
        target = (_ROOT / "static" / urllib.parse.unquote(relative)).resolve()
        return target.read_bytes(), target.name, mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    if text.startswith("/output/"):
        relative = urllib.parse.urlparse(text).path[len("/output/"):]
        target = (_USER_DATA_DIR / "output" / urllib.parse.unquote(relative)).resolve()
        return target.read_bytes(), target.name, mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    if text.startswith("file://"):
        parsed = urllib.parse.urlparse(text)
        target = Path(urllib.request.url2pathname(parsed.path))
        return target.read_bytes(), target.name, mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    if re.match(r"^[A-Za-z]:\\", text) and Path(text).exists():
        target = Path(text)
        return target.read_bytes(), target.name, mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    request = urllib.request.Request(
        text,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        raw = response.read()
        content_type = response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0].strip()
    return raw, guess_upload_filename(text, content_type), content_type


def volcengine_ark_api_key():
    env = myridtv_env.read_env_values()
    for name in ("ARK_API_KEY", "VOLCENGINE_ARK_API_KEY", "API_PROVIDER_VOLCENGINE_KEY"):
        value = str(env.get(name) or os.environ.get(name) or "").strip()
        if value:
            return value
    raise ApiError(400, "缺少火山方舟 API Key")


def volcengine_upload_asset(source_url):
    raw, file_name, content_type = local_media_source_bytes(source_url)
    key = volcengine_ark_api_key()
    data = _r_request_multipart_json(
        "https://ark.cn-beijing.volces.com/api/v3/files",
        fields={"purpose": "user_data"},
        files=[{"name": "file", "filename": file_name, "content_type": content_type, "data": raw}],
        headers={"Authorization": f"Bearer {key}"},
        timeout=180,
    )
    file_id = str(data.get("id") or data.get("file_id") or "").strip()
    file_url = str(data.get("url") or data.get("downloadUrl") or data.get("fileUrl") or "").strip()
    if not file_url and file_id:
        file_url = file_id
    if not file_url:
        raise RuntimeError(f"火山方舟文件上传未返回可用地址：{data}")
    return {"fileName": file_name, "fileId": file_id, "url": file_url, "downloadUrl": file_url, "raw": data}


def upload_cloud_media_bytes_to_litterbox(raw, file_name="upload.bin", content_type="application/octet-stream"):
    safe_name = str(file_name or "upload.bin").strip() or "upload.bin"
    mime = str(content_type or "application/octet-stream").strip() or "application/octet-stream"
    upload_url = os.environ.get("LITTERBOX_UPLOAD_URL", "https://litterbox.catbox.moe/resources/internals/api.php").strip() or "https://litterbox.catbox.moe/resources/internals/api.php"
    time_value = os.environ.get("LITTERBOX_TIME", "72h").strip() or "72h"
    text = myridtv_http.request_multipart_text(
        upload_url,
        fields={"reqtype": "fileupload", "time": time_value},
        files=[{"name": "fileToUpload", "filename": safe_name, "content_type": mime, "data": raw or b""}],
        timeout=600,
    )
    url = text.strip().splitlines()[0].strip()
    if not re.match(r"^https?://", url, re.I):
        raise RuntimeError(f"Litterbox 返回了无法识别的链接：{text[:200]}")
    return url


def upload_cloud_media_bytes_to_temp_sh(raw, file_name="upload.bin", content_type="application/octet-stream"):
    safe_name = str(file_name or "upload.bin").strip() or "upload.bin"
    mime = str(content_type or "application/octet-stream").strip() or "application/octet-stream"
    upload_url = os.environ.get("TEMP_SH_UPLOAD_URL", "https://temp.sh/upload").strip() or "https://temp.sh/upload"
    text = myridtv_http.request_multipart_text(
        upload_url,
        files=[{"name": "file", "filename": safe_name, "content_type": mime, "data": raw or b""}],
        timeout=600,
    )
    url = ""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            payload = data.get("data") if isinstance(data.get("data"), dict) else data
            url = str(payload.get("url") or payload.get("downloadUrl") or payload.get("fileUrl") or "").strip()
    except Exception:
        url = text.strip()
    if not re.match(r"^https?://", url, re.I):
        raise RuntimeError(f"Temp.sh 返回了无法识别的链接：{text[:200]}")
    return url


def cloud_media_url_downloadable(url, timeout=15):
    text = str(url or "").strip()
    if not re.match(r"^https?://", text, re.I):
        return False
    try:
        req = urllib.request.Request(
            text,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            chunk = resp.read(16)
            return 200 <= status < 400 and bool(chunk)
    except Exception as exc:
        append_log(_log_file(), f"cloud media url check failed url={text[:120]}: {exc}")
        return False


def upload_cloud_media_bytes(raw, file_name="upload.bin", content_type="application/octet-stream", service="auto"):
    selected = str(service or os.environ.get("CLOUD_VIDEO_UPLOAD_SERVICE", "auto") or "auto").strip().lower()
    choices = []
    if selected in {"litterbox", "catbox"}:
        choices = [("litterbox", upload_cloud_media_bytes_to_litterbox)]
    elif selected in {"temp", "temp.sh", "tempsh"}:
        choices = [("temp.sh", upload_cloud_media_bytes_to_temp_sh)]
    elif selected in {"volcengine", "volcengine-video", "video-reference"}:
        choices = [
            ("litterbox", upload_cloud_media_bytes_to_litterbox),
            ("temp.sh", upload_cloud_media_bytes_to_temp_sh),
        ]
    else:
        choices = [
            ("temp.sh", upload_cloud_media_bytes_to_temp_sh),
            ("litterbox", upload_cloud_media_bytes_to_litterbox),
        ]
    errors = []
    for name, func in choices:
        try:
            url = func(raw, file_name, content_type)
            if not cloud_media_url_downloadable(url):
                raise RuntimeError(f"上传后链接不可下载：{url[:120]}")
            append_log(_log_file(), f"cloud media uploaded service={name} name={str(file_name or '')[:80]} url={url[:120]}")
            return url
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            append_log(_log_file(), f"cloud media upload failed service={name} name={str(file_name or '')[:80]}: {exc}")
    raise RuntimeError("云端上传失败：" + "；".join(errors))


def upload_cloud_media_direct(source_url, service="auto"):
    raw, file_name, content_type = local_media_source_bytes(source_url)
    url = upload_cloud_media_bytes(raw, file_name, content_type, service=service)
    return {
        "ok": True,
        "url": url,
        "downloadUrl": url,
        "fileUrl": url,
        "name": file_name,
        "kind": upload_kind_for_file(file_name, content_type),
        "content_type": content_type,
        "expires": "3 days",
        "service": service,
    }
