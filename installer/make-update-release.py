"""Build a signed, content-addressed static update from a staged release.

Output is safe to upload as GitHub Release assets. Unchanged blobs keep the URL
from the preceding signed manifest, so clients fetch only files they lack.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from myridtv_updater import canonical_payload, verify_manifest, version_tuple  # noqa: E402


SUFFIXES = {".html", ".css", ".js"}


def make_release(stage: Path, out: Path, repo: str, key_b64: str, previous: Path | None = None) -> dict:
    version = (stage / "VERSION").read_text(encoding="utf-8-sig").strip()
    version_tuple(version)
    private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(key_b64, validate=True))
    public_key = Path(__file__).resolve().parents[1] / "update-public-key.pub"
    old_by_path = {}
    if previous:
        old = json.loads(previous.read_text(encoding="utf-8"))
        verify_manifest(old, public_key)
        if version_tuple(old["version"]) >= version_tuple(version):
            raise ValueError("release version must increase")
        old_by_path = {item["path"]: item for item in old["files"]}

    out.mkdir(parents=True, exist_ok=True)
    static_root = stage / "_internal" / "static"
    source_root = Path(__file__).resolve().parents[1]
    tracked = set(subprocess.check_output(
        ["git", "ls-files", "-z", "--", "_internal/static"], cwd=source_root
    ).decode("utf-8").strip("\0").split("\0"))
    records = []
    created = set()
    for source in sorted(static_root.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in SUFFIXES:
            continue
        relative = source.relative_to(stage).as_posix()
        if relative not in tracked:
            continue
        if relative == "_internal/static/app_config.json":
            continue
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        previous_item = old_by_path.get(relative)
        if previous_item and previous_item["sha256"] == digest:
            url = previous_item["url"]
        else:
            asset = f"blob-{digest}"
            url = f"https://github.com/{repo}/releases/download/{version}/{asset}"
            if asset not in created:
                (out / asset).write_bytes(raw)
                created.add(asset)
        records.append({"path": relative, "sha256": digest, "size": len(raw), "url": url})

    manifest = {"schema": 1, "version": version, "files": records}
    manifest["signature"] = base64.b64encode(private_key.sign(canonical_payload(manifest))).decode("ascii")
    (out / "update-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    verify_manifest(manifest, public_key)
    return {"version": version, "files": len(records), "new_blobs": len(created), "new_bytes": sum((out / name).stat().st_size for name in created)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repo", default="dearxiaozhou/MyridTV-updates")
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    key = os.environ.get("MYRIDTV_UPDATE_SIGNING_KEY", "")
    if not key:
        raise SystemExit("MYRIDTV_UPDATE_SIGNING_KEY is required")
    print(json.dumps(make_release(args.stage, args.out, args.repo, key, args.previous), ensure_ascii=False))


if __name__ == "__main__":
    main()
