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
MAX_MANIFEST_BYTES = 2_000_000
MAX_FILE_BYTES = 100_000_000
VERSION_RE = re.compile(r"^V(\d+)\.(\d+)\.(\d+)$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


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


def get_bytes(url: str, limit: int, allow_local: bool = False) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" and not (allow_local and parsed.scheme in {"http", "file"}):
        raise ValueError("update source must use HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "MyridTV-Updater/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("update download exceeds size limit")
    return data


def safe_static_path(app_dir: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.startswith("_internal/static/"):
        raise ValueError("update path outside static directory")
    parts = relative.split("/")
    if any(part in {"", ".", ".."} or ":" in part or "\\" in part for part in parts):
        raise ValueError("unsafe update path")
    if relative == "_internal/static/app_config.json" or relative.startswith("_internal/static/images/styles/generated/"):
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


def check_once(app_dir: Path, feed: str, public_key_file: Path, allow_local: bool = False) -> dict:
    raw = get_bytes(feed, MAX_MANIFEST_BYTES, allow_local=allow_local)
    manifest = json.loads(raw)
    if not isinstance(manifest, dict):
        raise ValueError("invalid update manifest")
    verify_manifest(manifest, public_key_file)
    return apply_manifest(app_dir, manifest, allow_local=allow_local)


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
    recover_incomplete_update(args.app_dir)
    while True:
        try:
            result = check_once(args.app_dir, args.feed, args.public_key, args.allow_local_feed)
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(f"update check failed: {exc}", file=sys.stderr, flush=True)
            if not args.watch:
                return 1
        if not args.watch:
            return 0
        time.sleep(1800)


if __name__ == "__main__":
    raise SystemExit(main())
