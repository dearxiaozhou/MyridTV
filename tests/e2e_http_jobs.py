# -*- coding: utf-8 -*-
"""HTTP 层端到端测试：走 3217 测试实例的完整链路。

1. 从 object_info 拿一张 ComfyUI 里现成的图；
2. POST /api/workflows 创建 LoadImage -> ImageScaleBy -> SaveImage 三节点测试工作流；
3. POST /api/comfyui/jobs 提交，bypass 掉 ImageScaleBy（考验编译器在真实执行里的短路）；
4. 轮询 /api/comfyui/jobs/{id} 到终态；
5. 校验 status/progress/images。
"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:3217"
WF_NAME = "ZZ测试_卡片旁路.json"


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status, json.loads(resp.read().decode())


def call_no_raise(method, path, payload=None):
    # 幂等清理用：404/409 等错误码也吞掉，不抛异常
    import urllib.error
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, None


# 0. 幂等清理：删掉上次运行可能残留的同名测试工作流（409 冲突源）
call_no_raise("DELETE", "/api/workflows/" + urllib.parse.quote(WF_NAME))


# 1. 拿图片名
_, oi = call("GET", "/api/comfyui/object-info?types=LoadImage,ImageScaleBy,SaveImage")
info = oi["object_info"]
image_name = info["LoadImage"]["input"]["required"]["image"][0][0]
print("图片:", image_name)

# 2. 创建工作流
workflow = {
    "1": {"class_type": "LoadImage", "inputs": {"image": image_name}, "_meta": {"title": "载入图片"}},
    "2": {"class_type": "ImageScaleBy", "inputs": {"image": ["1", 0], "upscale_method": "nearest-exact", "scale_by": 1.5}, "_meta": {"title": "缩放"}},
    "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0], "filename_prefix": "MyridTV_CFFLOW"}, "_meta": {"title": "保存"}},
}
_, created = call("POST", "/api/workflows", {"name": WF_NAME, "workflow": workflow})
print("工作流已创建:", created.get("name"))

# 3. 提交 job：bypass 节点 2，SaveImage 应该直接接 LoadImage
_, submitted = call("POST", "/api/comfyui/jobs", {
    "workflow": WF_NAME,
    "overrides": {},
    "modes": {"2": "bypass"},
    "prefs": {},
})
print("提交返回:", submitted.get("ok"), "| job:", submitted.get("job_id"), "| status:", submitted.get("status"))
assert submitted.get("ok"), submitted
job_id = submitted["job_id"]

# 4. 轮询
final = None
for _ in range(90):
    time.sleep(2)
    _, job = call("GET", f"/api/comfyui/jobs/{job_id}")
    final = job
    if job.get("status") not in ("queued", "running"):
        break
    print("  ...", job.get("status"), job.get("current_node_title") or job.get("current_node") or "")

print("终态:", final.get("status"), "| 耗时:", final.get("elapsed"), "s | 进度:", final.get("progress"))
print("错误:", final.get("error"))
print("产物:", [str(u) for u in (final.get("images") or [])])

ok = final.get("status") == "done" and (final.get("images") or [])
print("RESULT:", "PASS" if ok else "FAIL")
