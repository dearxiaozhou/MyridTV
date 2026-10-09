#!/usr/bin/env python3
"""Mirror a MyridTV signed update release from GitHub to Gitee as a file tree.

Gitee 免费版 release 附件上传 API 不可达（404），所以不走 release，而是把
manifest + blob 推到 Gitee 仓库文件树，用 raw 链接访问（国内裸连稳定）：
  https://gitee.com/myridtv/myrid-tv-updates/raw/master/<tag>/<file>
  https://gitee.com/myridtv/myrid-tv-updates/raw/master/update-manifest.json  (最新版)

myridtv_updater.py 的 remap_to_gitee 会把 GitHub release URL 重写成上面这种
Gitee raw URL，因此已装用户检查更新时 GitHub 抖动会自动走 Gitee。

PREREQUISITES:
  * 公开仓库 myridtv/myrid-tv-updates（默认分支 master）
  * GITEE_TOKEN 个人访问令牌（repo 权限）
  * 本机 git（在 PATH 中）
USAGE:
  set GITEE_TOKEN=xxxx
  python installer/mirror_to_gitee.py --tag V0.10.9
      [--cache-dir <dir>]   # 复用已下载的 manifest + blob，跳过重新下载
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

GITHUB_OWNER = "dearxiaozhou"
GITHUB_REPO = "MyridTV-updates"
GITEE_OWNER = "myridtv"
GITEE_REPO = "myrid-tv-updates"
GITEE_BRANCH = "master"


def gh_get(url: str, *, proxy, timeout=20, retries=6) -> bytes:
    """Download from GitHub with retries. Each attempt tries the proxy first,
    then a direct connection (proxy cleared) — the 127.0.0.1:7897 proxy is
    flaky for github.com (intermittent SSL EOF), so alternating paths maximises
    the chance one is healthy on any given try.
    """
    last: Exception | None = None
    for attempt in range(retries):
        for p in ([proxy, None] if proxy else [None]):
            handlers = [urllib.request.ProxyHandler({"http": p, "https": p})] if p else []
            opener = urllib.request.build_opener(*handlers)
            req = urllib.request.Request(url, headers={"User-Agent": "MyridTV-Updater/1"})
            try:
                with opener.open(req, timeout=timeout) as r:
                    return r.read()
            except Exception as exc:  # noqa: BLE001 - tried below / re-raised after retries
                last = exc
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    raise last if last else RuntimeError("gh_get failed")


def _blob_name(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--github-proxy", default="http://127.0.0.1:7897",
                    help="proxy for downloading from GitHub (set '' to disable)")
    ap.add_argument("--cache-dir", default=None,
                    help="reuse a directory that already holds update-manifest.json + the blobs")
    args = ap.parse_args()
    token = os.environ.get("GITEE_TOKEN")
    if not token:
        sys.exit("set GITEE_TOKEN environment variable first")

    # 1) 下载 / 复用 manifest + blobs
    tmp = Path(args.cache_dir) if args.cache_dir else Path(tempfile.mkdtemp(prefix="myrid-mirror-"))
    tmp.mkdir(parents=True, exist_ok=True)
    manifest_url = (f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
                    f"/releases/download/{args.tag}/update-manifest.json")
    manifest_path = tmp / "update-manifest.json"
    manifest = None
    if manifest_path.exists():
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            need = [_blob_name(f["url"]) for f in m["files"]]
            if need and all((tmp / n).exists() for n in need):
                manifest = m
                print(f"reusing cached manifest + {len(need)} blobs in {tmp}")
        except Exception:
            manifest = None
    if manifest is None:
        print(f"download manifest from GitHub: {manifest_url}")
        manifest = json.loads(gh_get(manifest_url, proxy=args.github_proxy or None))
        assert manifest["version"] == args.tag, f"manifest version {manifest['version']} != tag {args.tag}"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    files = [(tmp / _blob_name(f["url"]), f["url"]) for f in manifest["files"]]
    print(f"downloading {len(files)} blobs from GitHub (resume-supported) ...")
    for i, (local, url) in enumerate(files, 1):
        # 断点续传：已存在且非空的文件跳过，避免慢网下反复从头下
        if local.exists() and local.stat().st_size > 0:
            print(f"  skip cached [{i}/{len(files)}] {local.name}")
            continue
        local.write_bytes(gh_get(url, proxy=args.github_proxy or None))
        if i % 20 == 0:
            print(f"  {i}/{len(files)}")

    # 2) 准备 Gitee 仓库工作区（clone；空仓库则 init）
    repo_dir = Path(tempfile.mkdtemp(prefix="myrid-gitee-"))
    clone_url = f"https://oauth2:{token}@gitee.com/{GITEE_OWNER}/{GITEE_REPO}.git"
    print("cloning Gitee repo ...")
    rc = subprocess.run(["git", "clone", clone_url, str(repo_dir)],
                        capture_output=True, text=True)
    if rc.returncode != 0:
        print("clone failed (empty repo?), initializing instead ...")
        repo_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(repo_dir)], check=True)
        subprocess.run(["git", "-C", str(repo_dir), "remote", "add", "origin", clone_url], check=True)

    # 3) 写文件树：根目录放最新版 manifest，<tag>/ 放该版完整文件
    tag_dir = repo_dir / args.tag
    tag_dir.mkdir(parents=True, exist_ok=True)
    manifest_text = json.dumps(manifest, ensure_ascii=False)
    (repo_dir / "update-manifest.json").write_text(manifest_text, encoding="utf-8")
    (tag_dir / "update-manifest.json").write_text(manifest_text, encoding="utf-8")
    for f in manifest["files"]:
        name = _blob_name(f["url"])
        src = tmp / name
        if src.exists():
            (tag_dir / name).write_bytes(src.read_bytes())
        else:
            print(f"  WARN missing cached blob {name}, downloading ...")
            (tag_dir / name).write_bytes(gh_get(f["url"], proxy=args.github_proxy or None))
    print(f"committing {len(manifest['files']) + 1} files ...")
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "updater@myridtv.local"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "MyridTV Updater"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "add", "-A"], check=True)
    # commit 可能因无变化而失败（重跑同版本），忽略
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-q", "-m", f"mirror {args.tag}"],
                   capture_output=True, text=True)
    # 推 Gitee 走 HTTPS 代理时常因 postBuffer 太小报 "unable to rewind rpc post data"
    subprocess.run(["git", "-C", str(repo_dir), "config", "http.postBuffer", "524288000"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "http.version", "HTTP/1.1"], check=True)
    print(f"pushing to Gitee {GITEE_OWNER}/{GITEE_REPO} ({GITEE_BRANCH}) ...")
    subprocess.run(["git", "-C", str(repo_dir), "push", "origin", GITEE_BRANCH], check=True)
    print("done. verify:")
    print(f"  https://gitee.com/{GITEE_OWNER}/{GITEE_REPO}/raw/master/{args.tag}/update-manifest.json")
    print(f"  https://gitee.com/{GITEE_OWNER}/{GITEE_REPO}/raw/master/update-manifest.json")


if __name__ == "__main__":
    main()
