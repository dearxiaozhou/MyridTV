# -*- coding: utf-8 -*-
"""资产解析/缩略图域（后端拆分第29刀自 rh_official_proxy.py 逐字外移）：
输出资产名→类型/子目录/回退路径、/assets/ URL→磁盘路径（含防穿越）、
画布缩略图生成缓存、图片信息读取。值型全局走 getter 注入。"""
from pathlib import Path
import urllib.parse
import mimetypes
import shutil
import hashlib
import io
import uuid
from myridtv_core import ApiError

_G_ASSETS_DIR = lambda: None
_G_USER_DATA_DIR = lambda: None
_G_OUTPUT_IMAGE_EXTS = lambda: None
_G_OUTPUT_VIDEO_EXTS = lambda: None


def configure(getters):
    global _G_ASSETS_DIR, _G_USER_DATA_DIR, _G_OUTPUT_IMAGE_EXTS, _G_OUTPUT_VIDEO_EXTS
    _G_ASSETS_DIR = getters['ASSETS_DIR']
    _G_USER_DATA_DIR = getters['USER_DATA_DIR']
    _G_OUTPUT_IMAGE_EXTS = getters['OUTPUT_IMAGE_EXTS']
    _G_OUTPUT_VIDEO_EXTS = getters['OUTPUT_VIDEO_EXTS']


def output_asset_kind_for_name(name=""):
    ext = str(Path(str(name or "")).suffix or "").lower()
    if ext in {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}:
        return "audio"
    if ext in _G_OUTPUT_VIDEO_EXTS():
        return "video"
    if ext in _G_OUTPUT_IMAGE_EXTS():
        return "image"
    return ""


def output_asset_subdir_for_kind(kind="image"):
    text = str(kind or "").strip().lower()
    if text == "audio":
        return "audios"
    if text == "video":
        return "videos"
    if text == "image":
        return "images"
    return ""


def output_asset_fallback_paths(decoded):
    text = str(decoded or "").replace("\\", "/")
    if not text.startswith("output/"):
        return []
    name = Path(text).name
    if not name:
        return []
    root = _G_ASSETS_DIR() / "output"
    kind = output_asset_kind_for_name(name)
    candidates = []
    if text.startswith("output/history/"):
        candidates.append(root / "images" / "history" / name)
        return [path.resolve() for path in candidates]
    if text.startswith("output/images/history/"):
        candidates.append(root / "history" / name)
    elif text.startswith("output/images/"):
        candidates.extend([root / "images" / "history" / name, root / "history" / name])
    elif text.startswith("output/videos/"):
        candidates.append(root / name)
    else:
        if kind == "video":
            candidates.append(root / "videos" / name)
        else:
            candidates.extend([root / "images" / name, root / "images" / "history" / name, root / "history" / name])
    return [path.resolve() for path in candidates]


def resolve_user_asset_path(url_path):
    raw = urllib.parse.urlparse(str(url_path or "")).path or ""
    if not raw.startswith("/assets/"):
        raise ApiError(404, "asset not found")
    relative = raw[len("/assets/"):]
    if not relative:
        raise ApiError(404, "asset not found")
    decoded = urllib.parse.unquote(relative)
    target = (_G_ASSETS_DIR() / decoded).resolve()
    asset_root = _G_ASSETS_DIR().resolve()
    try:
        target.relative_to(asset_root)
    except Exception as exc:
        raise ApiError(403, "forbidden") from exc
    if not target.exists() or not target.is_file():
        if decoded.startswith("output/"):
            for fallback in output_asset_fallback_paths(decoded):
                try:
                    fallback.relative_to(asset_root)
                except Exception as exc:
                    raise ApiError(403, "forbidden") from exc
                if fallback.exists() and fallback.is_file():
                    return fallback
        raise ApiError(404, "asset not found")
    return target


def canvas_thumbnail_path(source_url, max_edge=640):
    raw_url = str(source_url or "")
    parsed_path = urllib.parse.urlparse(raw_url).path or ""
    if not parsed_path.startswith("/assets/"):
        raise ApiError(404, "asset not found")
    source = resolve_user_asset_path(parsed_path)
    mime_type = mimetypes.guess_type(source.name)[0] or ""
    if not mime_type.startswith("image/"):
        raise ApiError(415, "thumbnail source must be an image")

    edge = max(160, min(2048, int(max_edge or 640)))
    stat = source.stat()
    cache_key = hashlib.sha256(
        f"{source}|{stat.st_mtime_ns}|{stat.st_size}|{edge}".encode("utf-8")
    ).hexdigest()
    cache_dir = _G_USER_DATA_DIR() / "cache" / "canvas_thumbnails"
    target = cache_dir / f"{cache_key}.webp"
    if target.exists() and target.is_file():
        return target

    try:
        from PIL import Image, ImageOps
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            image.thumbnail((edge, edge), Image.Resampling.LANCZOS)
            payload = io.BytesIO()
            image.save(payload, "WEBP", quality=76, method=4)
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(422, "unable to create canvas thumbnail") from exc

    cache_dir.mkdir(parents=True, exist_ok=True)
    temporary = cache_dir / f".{cache_key}.{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_bytes(payload.getvalue())
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
    return target


def canvas_image_info(source_url):
    raw_url = str(source_url or "")
    parsed_path = urllib.parse.urlparse(raw_url).path or ""
    if not parsed_path.startswith("/assets/"):
        raise ApiError(404, "asset not found")
    source = resolve_user_asset_path(parsed_path)
    mime_type = mimetypes.guess_type(source.name)[0] or ""
    if not mime_type.startswith("image/"):
        raise ApiError(415, "source must be an image")
    try:
        from PIL import Image, ImageOps
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            width, height = image.size
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(422, "unable to read image info") from exc
    stat = source.stat()
    return {
        "ok": True,
        "width": int(width),
        "height": int(height),
        "mime": mime_type,
        "size": int(stat.st_size),
    }

def migrate_legacy_assets(user_data_dir, assets_dir):
    """把旧版 %APPDATA%\\MyridTV\\assets 整体迁移到安装目录（直接覆盖；用户已备份 C 盘目录）。"""
    try:
        legacy = user_data_dir / "assets"
        marker = assets_dir / ".legacy_migrated"
        if not legacy.exists() or marker.exists():
            return
        assets_dir.mkdir(parents=True, exist_ok=True)
        for item in legacy.iterdir():
            dest = assets_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            elif item.is_file():
                shutil.copy2(item, dest)
        marker.write_text("1", encoding="utf-8")
    except Exception as exc:
        try:
            print("assets migration failed:", exc)
        except Exception:
            pass

def _portable_user_data_dir(app_dir):
    """便携模式（仿 ComfyUI 的 user 目录）：安装目录下存在 user_data\\ 或 .portable 标记时，
    这份安装就用自己的数据目录，多份安装互不干扰；默认仍走 %APPDATA%\\MyridTV（现有安装行为不变）。"""
    try:
        if (app_dir / ".portable").exists():
            return app_dir / "user_data"
        candidate = app_dir / "user_data"
        if candidate.is_dir():
            return candidate
    except Exception:
        pass
    return None
