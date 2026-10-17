# -*- coding: utf-8 -*-
"""资产解析/缩略图域（后端拆分第29刀自 rh_official_proxy.py 逐字外移）：
输出资产名→类型/子目录/回退路径、/assets/ URL→磁盘路径（含防穿越）、
画布缩略图生成缓存、图片信息读取。值型全局走 getter 注入。"""
import json
import os
import threading
import time
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


# ============================================================
# 资产根目录可配置（2026-10-15 / V0.11.19）
# 优先级：环境变量 MYRIDTV_ASSETS_DIR > app_config.paths.assets_dir（用户自定义）
#          > <安装目录>/assets（系统默认：不改就是这个）
# 说明：改完要重启应用才生效——ASSETS_DIR 在 import 期就被多个子模块定值注入了。
# ============================================================

ASSETS_LAYOUT_SUBDIRS = (
    "output",
    "output/images",
    "output/videos",
    "output/audios",
    "output/history",
    "input",
    "library",
    "blender",
    "blender_imports",
)

_MIGRATION = {
    "running": False,
    "status": "idle",
    "source": "",
    "target": "",
    "copied": 0,
    "skipped": 0,
    "failed": 0,
    "total": 0,
    "error": "",
    "started_at": 0.0,
    "finished_at": 0.0,
}
_MIGRATION_LOCK = threading.Lock()


def _config_assets_dir(config_file):
    """读 app_config.json 的 paths.assets_dir（用户自定义值，空=没设过）。"""
    try:
        raw = json.loads(Path(config_file).read_text(encoding="utf-8"))
    except Exception:
        return ""
    paths = raw.get("paths") if isinstance(raw, dict) else None
    return str((paths or {}).get("assets_dir") or "").strip()


def _installer_preset_assets_dir(app_dir):
    """安装器首装页写下的预设（_internal/data/assets_root.ini）。

    安装器把非 ASCII 字符统一转成 \\uXXXX 再写入，文件恒为纯 ASCII，
    所以这里按 utf-8 读就是安全的；配置段缺失/解析失败一律当没设过。
    """
    ini_path = Path(app_dir) / "_internal" / "data" / "assets_root.ini"
    if not ini_path.exists():
        return ""
    try:
        import configparser
        parser = configparser.ConfigParser()
        parser.read_string(ini_path.read_text(encoding="utf-8", errors="ignore"))
        raw = str(parser.get("assets", "root", fallback="") or "").strip()
    except Exception:
        return ""
    if not raw:
        return ""
    try:
        return str(json.loads('"%s"' % raw))
    except Exception:
        return raw


def assets_dir_source(app_dir, config_file):
    """当前资产根目录从哪来的：env（环境变量）/ custom（设置页自定义）
    / installer（安装器首装页）/ default（系统默认）。"""
    if str(os.environ.get("MYRIDTV_ASSETS_DIR") or "").strip():
        return "env"
    if _config_assets_dir(config_file):
        return "custom"
    if _installer_preset_assets_dir(app_dir):
        return "installer"
    return "default"


def resolve_assets_root(app_dir, config_file):
    env_dir = str(os.environ.get("MYRIDTV_ASSETS_DIR") or "").strip()
    if env_dir:
        return Path(env_dir)
    custom = _config_assets_dir(config_file)
    if custom:
        return Path(custom)
    preset = _installer_preset_assets_dir(app_dir)
    if preset:
        return Path(preset)
    return Path(app_dir) / "assets"


def ensure_assets_layout(assets_dir):
    """确保资产主路径下的标准子目录骨架存在（已存在的原样不动）。返回本次新建的目录列表。"""
    created = []
    for rel in ASSETS_LAYOUT_SUBDIRS:
        try:
            target = Path(assets_dir) / rel
            if not target.exists():
                target.mkdir(parents=True, exist_ok=True)
                created.append(rel)
        except Exception:
            continue
    return created


def _writable(path):
    """目录可写判定：不存在的目录只测其最近的存在祖先，不为探测而创建目录。"""
    try:
        candidate = Path(path)
        probe_root = candidate
        while not probe_root.exists() and probe_root.parent != probe_root:
            probe_root = probe_root.parent
        if not probe_root.exists():
            return False
        if not probe_root.is_dir():
            return False
        probe = probe_root / ".myridtv_probe.tmp"
        probe.write_text("1", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _free_bytes(path):
    try:
        return int(shutil.disk_usage(str(path)).free)
    except Exception:
        return 0


def _count_entries(path):
    try:
        return len([item for item in Path(path).iterdir()])
    except Exception:
        return 0


def _forbidden_target(candidate, app_dir, user_data_dir):
    """防呆：不许把资产目录指到程序目录/数据目录/盘符根/系统目录（互相污染）。"""
    try:
        resolved = candidate.resolve()
    except Exception:
        return ""
    for base in (Path(app_dir), Path(user_data_dir)):
        try:
            if resolved == base.resolve():
                return "不能把资产目录设成 %s（会跟程序或数据目录混在一起）" % base
        except Exception:
            continue
    drive = resolved.drive or ""
    if drive:
        try:
            if resolved == Path(drive + "\\"):
                return "不能把资产目录直接设在盘符根目录 %s" % (drive + "\\")
        except Exception:
            pass
    for env_name in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        raw = str(os.environ.get(env_name) or "").strip()
        if not raw:
            continue
        try:
            root = Path(raw).resolve()
        except Exception:
            continue
        try:
            if resolved == root or root in resolved.parents:
                return "不能把资产目录设在系统/程序目录内：%s" % root
        except Exception:
            continue
    return ""


def validate_assets_target(raw_path, app_dir, user_data_dir):
    """校验用户填写的资产目录。返回 (ok, message, path)。"""
    text = str(raw_path or "").strip().strip('"').strip("'")
    if not text:
        return False, "资产目录不能为空", None
    try:
        candidate = Path(os.path.expandvars(text)).expanduser()
    except Exception as exc:
        return False, "路径无法解析：%s" % exc, None
    if not candidate.is_absolute():
        return False, "资产目录必须填绝对路径（例如 D:\\MyridAssets）", None
    reason = _forbidden_target(candidate, app_dir, user_data_dir)
    if reason:
        return False, reason, None
    if not _writable(candidate):
        return False, "目录无法创建或不可写入：%s" % candidate, None
    return True, "", candidate


def _same_path(a, b):
    try:
        return Path(a).resolve() == Path(b).resolve()
    except Exception:
        return str(a) == str(b)


def configured_assets_dir(config_file):
    """app_config.json 里已保存的资产目录（空=没自定义过）。"""
    return _config_assets_dir(config_file)


def assets_root_payload(assets_dir, app_dir, user_data_dir, config_file, source=None, migration=None):
    """设置页要的资产主路径状态。

    assets_dir = 进程内正在用的目录；saved_dir = app_config 里已保存的目录；
    两者不等 = 改过但还没重启应用（pending_restart=True）。
    """
    current = Path(assets_dir)
    default_dir = Path(app_dir) / "assets"
    saved = _config_assets_dir(config_file)
    src = source or assets_dir_source(app_dir, config_file)
    saved_dir = Path(saved) if saved else default_dir
    same_as_default = _same_path(default_dir, current)
    missing = [rel for rel in ASSETS_LAYOUT_SUBDIRS if not (current / rel).exists()]
    return {
        "ok": True,
        "assets_dir": str(current),
        "saved_dir": str(saved_dir),
        "default_dir": str(default_dir),
        "source": src,
        "configured": src in ("custom", "installer"),
        "exists": current.exists(),
        "writable": _writable(current),
        "free_bytes": _free_bytes(current),
        "layout_missing": missing,
        "legacy_dir": str(default_dir),
        "legacy_has_content": (not same_as_default) and default_dir.exists() and _count_entries(default_dir) > 0,
        "legacy_entries": 0 if same_as_default else _count_entries(default_dir),
        "pending_restart": bool(saved) and not _same_path(saved_dir, current),
        "migration": migration or assets_migration_state(),
    }


def assets_migration_state():
    with _MIGRATION_LOCK:
        return dict(_MIGRATION)


def _count_files(root):
    """统计目录下的文件总数（只数文件，用于搬迁进度分母）。"""
    count = 0
    try:
        for _cur, _dirs, files in os.walk(root):
            count += len(files)
    except Exception:
        return count
    return count


def _migrate_worker(source, target):
    """递归合并式搬迁：目录递归进入（不再整棵跳过），目标已存在的同名文件跳过、绝不覆盖。

    注意：资产目录切换后目标下已被 ensure_assets_layout 建好骨架（output/input/library...），
    与源目录顶层同名，因此必须逐层递归合并，不能在顶层判 exists 就 continue。
    """
    copied = 0
    skipped = 0
    failed = 0
    total = 0
    status = "done"
    error = ""

    def bump(force=False):
        with _MIGRATION_LOCK:
            _MIGRATION["copied"] = copied
            _MIGRATION["skipped"] = skipped
            _MIGRATION["failed"] = failed
            if force or total:
                _MIGRATION["total"] = total

    try:
        src = Path(source)
        dst = Path(target)
        dst.mkdir(parents=True, exist_ok=True)
        total = _count_files(str(src))
        with _MIGRATION_LOCK:
            _MIGRATION["total"] = total

        stack = [(src, dst)]
        while stack:
            cur_src, cur_dst = stack.pop()
            try:
                entries = list(cur_src.iterdir())
            except Exception:
                failed += 1
                continue
            for item in entries:
                dest = cur_dst / item.name
                try:
                    if item.is_dir():
                        # 目录：目标已有就进去合并，绝不整棵跳过
                        dest.mkdir(parents=True, exist_ok=True)
                        stack.append((item, dest))
                    elif item.is_file():
                        if dest.exists():
                            # 同名文件已存在：跳过，绝不覆盖、绝不删源
                            skipped += 1
                            continue
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest)
                        copied += 1
                    else:
                        skipped += 1
                except Exception:
                    failed += 1
                if (copied + skipped + failed) % 50 == 0:
                    bump()
        bump(force=True)
        if failed:
            status = "done_with_errors"
    except Exception as exc:
        status = "failed"
        error = str(exc)
    with _MIGRATION_LOCK:
        _MIGRATION.update({
            "running": False,
            "status": status,
            "copied": copied,
            "skipped": skipped,
            "failed": failed,
            "total": total,
            "error": error,
            "finished_at": time.time(),
        })


def start_assets_migration(source, target):
    """把旧资产目录内容复制到当前资产目录（复制而非移动：源目录原地保留，零丢失）。"""
    with _MIGRATION_LOCK:
        if _MIGRATION["running"]:
            return dict(_MIGRATION)
        _MIGRATION.update({
            "running": True,
            "status": "running",
            "source": str(source),
            "target": str(target),
            "copied": 0,
            "skipped": 0,
            "failed": 0,
            "total": 0,
            "error": "",
            "started_at": time.time(),
            "finished_at": 0.0,
        })
    threading.Thread(target=_migrate_worker, args=(str(source), str(target)), daemon=True).start()
    return assets_migration_state()
