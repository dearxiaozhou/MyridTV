"""comfy_flow_service 冒烟测试：真的连一次本地 ComfyUI 跑一个最小工作流。

跑法：
    python tests/smoke_comfy_flow_service.py

会做三件事：
1. 验证最小 WebSocket 客户端能连上 ComfyUI 并收到 status 事件；
2. 拉取 /object_info（首次约 8MB，会缓存到 tests/_oi_cache.json）；
3. 用 LoadImage -> SaveImage 的最小图跑一次端到端任务，验证
   提交 -> ws 进度 -> history -> 下载产物 全链路。

需要先启动本地 ComfyUI（127.0.0.1:8188）。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, APP_ROOT)

import comfy_flow_service as service  # noqa: E402
from comfy_flow_service import MiniWebSocket, _ws_endpoint  # noqa: E402

DOWNLOAD_DIR = os.path.join(HERE, "_smoke_assets")


def fake_asset_saver(base, item, prompt_id, kind="image"):
    """代替宿主的 comfy_output_asset_url：把产物抓到本地目录。"""
    import urllib.parse
    import urllib.request

    filename = str(item.get("filename") or "").strip()
    if not filename:
        return ""
    params = {
        "filename": filename,
        "type": str(item.get("type") or "output"),
        "subfolder": str(item.get("subfolder") or ""),
    }
    url = base + "/view?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as response:
        raw = response.read()
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    import re
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", filename)
    target = os.path.join(DOWNLOAD_DIR, f"smoke_{prompt_id}_{safe}")
    with open(target, "wb") as handle:
        handle.write(raw)
    return target


def check_ws():
    print("[1/3] WebSocket 客户端")
    messages = []
    host, port = _ws_endpoint()
    ws = MiniWebSocket(host, port, "/ws?clientId=smoke_" + str(int(time.time())), messages.append, timeout=5)
    try:
        ws.connect()
        time.sleep(2.0)
    finally:
        ws.close()
    kinds = sorted({str(m.get("type")) for m in messages if isinstance(m, dict)})
    print("      连接", f"{host}:{port}", "收到消息", len(messages), "条，类型:", kinds)
    if not messages:
        print("      [警告] 没收到任何 ws 消息，节点级进度会降级（任务本身不受影响）")
        return False
    return True


def check_object_info():
    print("[2/3] /object_info")
    service.configure(
        base_provider=lambda: "http://127.0.0.1:8188",
        asset_saver=fake_asset_saver,
        cache_path=os.path.join(HERE, "_oi_cache.json"),
    )
    started = time.time()
    data = service.load_object_info()
    print(f"      节点类型 {len(data)} 个，耗时 {time.time() - started:.1f}s")
    subset = service.object_info_subset(["LoadImage", "SaveImage"])
    print("      切片 LoadImage/SaveImage ->", list(subset.keys()))
    return data


def check_end_to_end(object_info):
    print("[3/3] 端到端最小任务")
    load_options = (object_info.get("LoadImage") or {}).get("input", {}).get("required", {}).get("image")
    if not isinstance(load_options, list) or not load_options or not isinstance(load_options[0], list):
        print("      [跳过] 无法从 object_info 取到可用图片名")
        return None
    image_name = load_options[0][0]
    print("      使用图片:", image_name)

    workflow = {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}, "_meta": {"title": "载入图片"}},
        "2": {
            "class_type": "SaveImage",
            "inputs": {"images": ["1", 0], "filename_prefix": "MyridTV_SMOKE"},
            "_meta": {"title": "保存图片"},
        },
    }
    job = service.submit_job({"name": "smoke", "workflow": workflow}, {}, {}, {})
    print("      已提交 job_id =", job.id)

    deadline = time.time() + 120
    last = ""
    while time.time() < deadline:
        current = f"{job.status}/{job.progress}%/node={job.current_node}"
        if current != last:
            print("      ", current)
            last = current
        if job.status in (service.STATUS_DONE, service.STATUS_ERROR, service.STATUS_CANCELLED):
            break
        time.sleep(1)

    print("      终态:", job.status, "| 图片:", job.images, "| 错误:", job.error or "无")
    return job


def main():
    try:
        service._request_json("/system_stats", timeout=10)
    except Exception as exc:
        print("连不上本地 ComfyUI（127.0.0.1:8188）：", exc)
        return 1

    check_ws()
    object_info = check_object_info()
    job = check_end_to_end(object_info)

    ok = bool(job and job.status == service.STATUS_DONE and job.images)
    print()
    print("结果:", "通过" if ok else "未通过")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
