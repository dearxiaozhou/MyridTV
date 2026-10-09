"""Signed, file-level updates for the MyridTV web UI.

The updater intentionally touches only shipped static files. Runtime configuration,
user assets, Python code, and desktop binaries have separate lifecycles.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import msvcrt
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from ecdsa import BadSignatureError, Ed25519, VerifyingKey


APP_DIR = Path(__file__).resolve().parent
DEFAULT_FEED = "https://github.com/dearxiaozhou/MyridTV-updates/releases/latest/download/update-manifest.json"
# 镜像回退（GitHub 不可达时）：用 Gitee 公开仓库的 raw 文件树当备胎。
# Gitee 免费账户的 release 附件上传 API 不可达（404），所以不走 release，
# 而是把文件推到仓库文件树、用 raw 链接访问（国内裸连稳定）。
# URL 结构重写（非简单换 host）：
#   https://github.com/dearxiaozhou/MyridTV-updates/releases/download/<tag>/<file>
#     -> https://gitee.com/myridtv/myrid-tv-updates/raw/master/<tag>/<file>
#   https://github.com/dearxiaozhou/MyridTV-updates/releases/latest/download/update-manifest.json
#     -> https://gitee.com/myridtv/myrid-tv-updates/raw/master/update-manifest.json
# （Gitee 个人空间 path 是 myridtv，显示名 Xiaozhou；默认分支 master。）
GITHUB_RELEASE_RE = re.compile(
    r"^https://github\.com/dearxiaozhou/MyridTV-updates/releases/download/([^/]+)/(.+)$")
GITHUB_LATEST_RE = re.compile(
    r"^https://github\.com/dearxiaozhou/MyridTV-updates/releases/latest/download/update-manifest\.json$")
GITEE_RAW_BASE = "https://gitee.com/myridtv/myrid-tv-updates/raw/master"


def remap_to_gitee(url: str) -> str | None:
    """把 GitHub release 下载 URL 重写成 Gitee raw 文件树 URL；非 GitHub 源返回 None。"""
    m = GITHUB_RELEASE_RE.match(url)
    if m:
        return f"{GITEE_RAW_BASE}/{m.group(1)}/{m.group(2)}"
    if GITHUB_LATEST_RE.match(url):
        return f"{GITEE_RAW_BASE}/update-manifest.json"
    return None
MAX_MANIFEST_BYTES = 2_000_000
MAX_FILE_BYTES = 100_000_000
VERSION_RE = re.compile(r"^V(\d+)\.(\d+)\.(\d+)$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _env_mirrors() -> list[tuple[str, str]]:
    """MYRIDTV_UPDATE_MIRRORS 覆盖：分号分隔的 src=dst 前缀对（可选自定义镜像）。"""
    raw = os.environ.get("MYRIDTV_UPDATE_MIRRORS", "").strip()
    if not raw:
        return []
    pairs: list[tuple[str, str]] = []
    for part in re.split(r"[;\s]+", raw):
        if "=" in part:
            src, dst = part.split("=", 1)
            if src and dst:
                pairs.append((src, dst))
    return pairs


def mirror_candidates(url: str, extra: list[tuple[str, str]] | None = None) -> list[str]:
    """返回含主源在内的候选 URL 列表：默认 GitHub→Gitee raw 重写，再加可选自定义前缀镜像。"""
    out = [url]
    g = remap_to_gitee(url)
    if g:
        out.append(g)
    for src, dst in (extra or _env_mirrors()):
        if src in url and dst not in url:
            out.append(url.replace(src, dst, 1))
    return out


def user_data_root(app_dir: Path) -> Path:
    override = os.environ.get("MYRIDTV_USER_DATA_DIR")
    if override:
        return Path(override).resolve()
    if (app_dir / ".portable").exists() or (app_dir / "user_data").is_dir():
        return app_dir / "user_data"
    return Path(os.environ.get("APPDATA", str(app_dir))) / "MyridTV"


def state_path(app_dir: Path) -> Path:
    return update_dir(app_dir) / "state.json"


def journal_path(app_dir: Path) -> Path:
    return update_dir(app_dir) / "journal.json"


def update_dir(app_dir: Path) -> Path:
    install_id = hashlib.sha256(str(app_dir.resolve()).casefold().encode("utf-8")).hexdigest()[:16]
    return user_data_root(app_dir) / "data" / "updates" / install_id


def read_state(app_dir: Path) -> dict:
    try:
        value = json.loads(state_path(app_dir).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(app_dir: Path, value: dict) -> None:
    write_json_atomic(state_path(app_dir), value)


def write_json_atomic(target: Path, value: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="update-state-", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def version_tuple(value: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(str(value))
    if not match:
        raise ValueError("invalid update version")
    return tuple(map(int, match.groups()))


def current_version(app_dir: Path) -> str:
    installed = (app_dir / "VERSION").read_text(encoding="utf-8-sig").strip()
    version_tuple(installed)
    state_version = read_state(app_dir).get("static_version")
    if state_version:
        version_tuple(state_version)
        return state_version if version_tuple(state_version) > version_tuple(installed) else installed
    return installed


def canonical_payload(manifest: dict) -> bytes:
    payload = {key: value for key, value in manifest.items() if key != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify_manifest(manifest: dict, public_key_file: Path) -> None:
    if manifest.get("schema") != 1 or not isinstance(manifest.get("files"), list):
        raise ValueError("unsupported update manifest")
    version_tuple(manifest.get("version", ""))
    key = base64.b64decode(public_key_file.read_text(encoding="ascii").strip(), validate=True)
    signature = base64.b64decode(manifest.get("signature", ""), validate=True)
    try:
        VerifyingKey.from_string(key, curve=Ed25519).verify(signature, canonical_payload(manifest))
    except BadSignatureError as exc:
        raise ValueError("update manifest signature is invalid") from exc


def get_bytes(url: str, limit: int, allow_local: bool = False, fast: bool = False,
              mirror_hosts: list[tuple[str, str]] | None = None) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" and not (allow_local and parsed.scheme in {"http", "file"}):
        raise ValueError("update source must use HTTPS")
    candidates = mirror_candidates(url, extra=mirror_hosts)
    last: Exception | None = None
    # 每个候选源各重试若干次：CDN / release 下载常掉连接，退避重试能挡掉瞬时抖动。
    # fast=True（界面「立即检查」）：每个候选只试 1 次，主源失败立刻切镜像源再试
    # 一次，仍失败才报错——既快速失败又能在 GitHub 抖动时白嫖镜像源。后台 --watch
    # 用完整重试（每候选 4 次）。
    per_candidate = 1 if fast else 4
    timeout = 8 if fast else 30
    for cand in candidates:
        request = urllib.request.Request(cand, headers={"User-Agent": "MyridTV-Updater/1"})
        for attempt in range(per_candidate):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    data = response.read(limit + 1)
                if len(data) > limit:
                    raise ValueError("update download exceeds size limit")
                return data
            except Exception as exc:  # noqa: BLE001 - retried below, re-raised if all fail
                last = exc
                if attempt < per_candidate - 1:
                    time.sleep(1.5 * (attempt + 1))
    raise last if last else ValueError("update download failed")


def safe_static_path(app_dir: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.startswith("_internal/static/"):
        raise ValueError("update path outside static directory")
    parts = relative.split("/")
    if any(part in {"", ".", ".."} or ":" in part or "\\" in part for part in parts):
        raise ValueError("unsafe update path")
    if relative == "_internal/static/app_config.json":
        raise ValueError("runtime file excluded from update")
    # 风格缩略图（generated/）：只下发 .webp。缩略图已从 PNG 换成 WebP，
    # 但老版本安装目录里留的是 .png；让更新通道带 .webp 下去，前端引用即可
    # 换成 webp，同时不必把 .png 也重复推一遍。
    if relative.startswith("_internal/static/images/styles/generated/") and not relative.endswith(".webp"):
        raise ValueError("runtime file excluded from update")
    target = app_dir.joinpath(*parts)
    static_root = app_dir / "_internal" / "static"
    if not target.resolve(strict=False).is_relative_to(static_root.resolve()):
        raise ValueError("update path escapes static directory")
    return target


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def recover_incomplete_update(app_dir: Path) -> bool:
    journal_file = journal_path(app_dir)
    if not journal_file.exists():
        return False
    journal = json.loads(journal_file.read_text(encoding="utf-8"))
    backup_root = update_dir(app_dir) / "backups" / journal["previous_version"]
    for item in reversed(journal["files"]):
        target = safe_static_path(app_dir, item["path"])
        backup = backup_root / item["path"]
        if item["existed"]:
            if not backup.is_file():
                raise RuntimeError(f"update backup missing: {item['path']}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
        else:
            target.unlink(missing_ok=True)
    previous_state = journal.get("previous_state") or {}
    if previous_state:
        write_state(app_dir, previous_state)
    else:
        state_path(app_dir).unlink(missing_ok=True)
    journal_file.unlink()
    return True


def apply_manifest(app_dir: Path, manifest: dict, allow_local: bool = False) -> dict:
    recover_incomplete_update(app_dir)
    previous_state = read_state(app_dir)
    old_version = current_version(app_dir)
    target_version = manifest["version"]
    if version_tuple(target_version) <= version_tuple(old_version):
        return {"status": "current", "version": old_version, "downloaded_files": 0}

    entries: list[tuple[Path, bytes]] = []
    seen: set[str] = set()
    for item in manifest["files"]:
        if not isinstance(item, dict):
            raise ValueError("invalid file entry")
        relative = item.get("path", "")
        target = safe_static_path(app_dir, relative)
        if relative in seen:
            raise ValueError("duplicate file entry")
        seen.add(relative)
        expected = item.get("sha256", "")
        size = item.get("size")
        if not SHA_RE.fullmatch(str(expected)) or not isinstance(size, int) or size < 0 or size > MAX_FILE_BYTES:
            raise ValueError("invalid file digest or size")
        if target.is_file() and target.stat().st_size == size and sha256(target.read_bytes()) == expected:
            continue
        raw = get_bytes(item.get("url", ""), min(size, MAX_FILE_BYTES), allow_local=allow_local)
        if len(raw) != size or sha256(raw) != expected:
            raise ValueError(f"update file checksum failed: {relative}")
        entries.append((target, raw))

    # All downloads are verified before touching the installed program.
    backup_dir = update_dir(app_dir) / "backups" / old_version
    journal_files = []
    try:
        for target, raw in entries:
            target.parent.mkdir(parents=True, exist_ok=True)
            relative = target.relative_to(app_dir).as_posix()
            backup = backup_dir / relative
            if target.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
            journal_files.append({"path": relative, "existed": target.exists()})
        if journal_files:
            journal = {
                "previous_version": old_version,
                "previous_state": previous_state,
                "files": journal_files,
            }
            write_json_atomic(journal_path(app_dir), journal)
        for target, raw in entries:
            fd, temp_name = tempfile.mkstemp(prefix=".myrid-update-", dir=target.parent)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, target)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
        result = {
            "status": "refresh_available",
            "static_version": target_version,
            "previous_version": old_version,
            "downloaded_files": len(entries),
            "updated_at": int(time.time()),
        }
        write_state(app_dir, result)
        journal_path(app_dir).unlink(missing_ok=True)
        return result
    except Exception:
        if journal_path(app_dir).exists():
            recover_incomplete_update(app_dir)
        raise


def check_once(app_dir: Path, feed: str, public_key_file: Path, allow_local: bool = False, fast: bool = False) -> dict:
    raw = get_bytes(feed, MAX_MANIFEST_BYTES, allow_local=allow_local, fast=fast)
    manifest = json.loads(raw)
    if not isinstance(manifest, dict):
        raise ValueError("invalid update manifest")
    verify_manifest(manifest, public_key_file)
    return apply_manifest(app_dir, manifest, allow_local=allow_local)


def resolve_feeds() -> list[str]:
    """更新源列表。MYRIDTV_UPDATE_FEED_URL（分号分隔）优先，否则用默认 GitHub
    源；主源不可达时的 Gitee raw 文件树镜像回退由 get_bytes 内部 remap_to_gitee 处理。"""
    raw = os.environ.get("MYRIDTV_UPDATE_FEED_URL", "").strip()
    if raw:
        feeds = [f.strip() for f in raw.split(";") if f.strip()]
        if feeds:
            return feeds
    return [DEFAULT_FEED]


def humanize_error(exc: BaseException | None) -> str:
    """把网络/系统级异常翻译成用户能读的中文原因。"""
    if exc is None:
        return "未知错误"
    s = str(exc)
    if "10060" in s or "timed out" in s or "Connection timed out" in s:
        return "网络连接超时：请检查网络或代理设置后重试"
    if "UNEXPECTED_EOF" in s or "SSLEOF" in s or "SSL" in s or "CERT" in s:
        return "安全连接被中断：请检查代理或网络稳定性后重试"
    if "Name or service" in s or "getaddrinfo" in s or "Name resolution" in s:
        return "无法解析更新服务器地址：请检查 DNS 或网络后重试"
    if "404" in s or "Not Found" in s:
        return "未找到更新清单：可能尚未发布对应版本"
    return f"更新检查失败：{s[:120]}"


def check_now(app_dir: Path, public_key_file: Path, allow_local: bool = False) -> dict:
    """界面「检查更新」按钮调用。依次尝试各更新源（默认仅 GitHub，不可达时
    get_bytes 自动回退 Gitee 镜像），全部失败时将可读的中文原因写入 state。"""
    last: Exception | None = None
    for feed in resolve_feeds():
        try:
            return check_once(app_dir, feed, public_key_file, allow_local=allow_local, fast=True)
        except Exception as exc:  # noqa: BLE001 - 尝试下一个源
            last = exc
    state = read_state(app_dir)
    msg = humanize_error(last)
    state.update({"status": "error", "error": msg, "raw_error": str(last), "checked_at": int(time.time())})
    write_state(app_dir, state)
    raise RuntimeError(msg) from last


def acquire_watcher_lock(app_dir: Path):
    lock_path = update_dir(app_dir) / "watcher.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    handle.seek(0)
    if not handle.read(1):
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return None
    return handle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", type=Path, default=APP_DIR)
    parser.add_argument("--feed", default=os.environ.get("MYRIDTV_UPDATE_FEED_URL", DEFAULT_FEED))
    parser.add_argument("--public-key", type=Path, default=APP_DIR / "update-public-key.pub")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--allow-local-feed", action="store_true", help="for isolated tests only")
    args = parser.parse_args()
    if args.watch and (args.app_dir / ".git").exists():
        print("update watcher disabled in source checkout")
        return 0
    lock = acquire_watcher_lock(args.app_dir) if args.watch else None
    if args.watch and lock is None:
        print("update watcher already running")
        return 0
    feeds = [f.strip() for f in args.feed.split(";") if f.strip()] or resolve_feeds()
    recover_incomplete_update(args.app_dir)
    while True:
        last: Exception | None = None
        for feed in feeds:
            try:
                result = check_once(args.app_dir, feed, args.public_key, args.allow_local_feed)
                print(json.dumps(result, ensure_ascii=False), flush=True)
                last = None
                break
            except Exception as exc:  # noqa: BLE001
                last = exc
        if last is not None:
            print(f"update check failed: {humanize_error(last)}", file=sys.stderr, flush=True)
            if not args.watch:
                return 1
        if not args.watch:
            return 0
        time.sleep(1800)


if __name__ == "__main__":
    raise SystemExit(main())
