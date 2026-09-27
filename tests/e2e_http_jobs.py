# -*- coding: utf-8 -*-
"""Live HTTP + real ComfyUI integration test. Requires explicit opt-in because it generates an image."""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

if os.environ.get("MYRIDTV_RUN_LIVE_INTEGRATION") != "1":
    print("SKIP: live ComfyUI generation is opt-in; use run_regression.ps1 -IncludeLiveIntegration")
    sys.exit(0)

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
WF_NAME = f"MyridTV_E2E_{uuid.uuid4().hex[:12]}.json"


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status, json.loads(resp.read().decode())


def call_no_raise(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, None


def main():
    workflow_path = "/api/workflows/" + urllib.parse.quote(WF_NAME)
    try:
        # 1. 拿 ComfyUI 里现成的一张图片；这是 live 集成测试，需要可用的本机 ComfyUI。
        _, oi = call("GET", "/api/comfyui/object-info?types=LoadImage,ImageScaleBy,SaveImage")
        info = oi["object_info"]
        image_name = info["LoadImage"]["input"]["required"]["image"][0][0]
        print("图片:", image_name)

        # 2. 临时创建一个工作流：LoadImage -> ImageScaleBy -> SaveImage。
        workflow = {
            "1": {"class_type": "LoadImage", "inputs": {"image": image_name}, "_meta": {"title": "载入图片"}},
            "2": {"class_type": "ImageScaleBy", "inputs": {"image": ["1", 0], "upscale_method": "nearest-exact", "scale_by": 1.5}, "_meta": {"title": "缩放"}},
            "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0], "filename_prefix": "MyridTV_E2E"}, "_meta": {"title": "保存"}},
        }
        _, created = call("POST", "/api/workflows", {"name": WF_NAME, "workflow": workflow})
        print("工作流已创建:", created.get("name"))

        # 3. 提交真实生成任务，bypass 节点 2，检查完整作业生命周期。
        _, submitted = call("POST", "/api/comfyui/jobs", {
            "workflow": WF_NAME,
            "overrides": {},
            "modes": {"2": "bypass"},
            "prefs": {},
        })
        print("提交返回:", submitted.get("ok"), "| job:", submitted.get("job_id"), "| status:", submitted.get("status"))
        assert submitted.get("ok"), submitted
        job_id = submitted["job_id"]

        final = None
        for _ in range(90):
            time.sleep(2)
            _, final = call("GET", f"/api/comfyui/jobs/{job_id}")
            if final.get("status") not in ("queued", "running"):
                break
            print("  ...", final.get("status"), final.get("current_node_title") or final.get("current_node") or "")

        print("终态:", final.get("status"), "| 耗时:", final.get("elapsed"), "s | 进度:", final.get("progress"))
        print("错误:", final.get("error"))
        print("产物:", [str(url) for url in (final.get("images") or [])])
        ok = final.get("status") == "done" and bool(final.get("images"))
        print("RESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        # 随机名称确保只清理本次测试创建的记录，失败路径也执行。
        status, _ = call_no_raise("DELETE", workflow_path)
        if status in (200, 404):
            print("临时工作流已清理")
        else:
            print("WARN: 临时工作流清理返回", status)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("LIVE INTEGRATION ERROR:", repr(exc))
        sys.exit(1)
