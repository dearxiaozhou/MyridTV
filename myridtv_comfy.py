# -*- coding: utf-8 -*-
"""MyridTV ComfyUI 平台域（后端拆分第7刀）：实例配置写回、实例基址解析、Comfy HTTP、
workflow 字段注入、输出节点挑选/构建提交/轮询、产物 URL 映射、最近输出与簇拆分。

逐字迁移自 rh_official_proxy.py 连续块 L(write_comfy_instances)..L(create_workflow_record)
（11 函数 316 行，可逆还原行级 diff=0）。行为零变更。
configure() 注入：COMFY_WORKFLOW_POLL_TIMEOUT_SECONDS 值（import 时定、零重绑）、
LOG_FILE getter、7 个块外函数 lambda 闭包（instances 读写族 / media_localize 产物路径族 /
read_workflow_record）。core 直用 ApiError/append_log/write_json_file。
主文件对块外仍调用的 6 函数留同名薄代理，调用点不改。
"""
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import comfy_flow_service
from comfy_flow_compiler import compile_prompt as compile_comfy_prompt

from myridtv_core import ApiError, append_log, write_json_file

_POLL_TIMEOUT = 600
_log_file = lambda: None
_USER_DATA_DIR = None
_r_comfy_instances_file_path = None
_r_read_comfy_instances = None
_r_normalize_comfy_instances = None
_r_asset_output_media_dir = None
_r_asset_output_url = None
_r_canvas_output_folder_name = None
_r_read_workflow_record = None


def configure(user_data_dir, poll_timeout, log_file_getter,
              comfy_instances_file_path, read_comfy_instances, normalize_comfy_instances,
              asset_output_media_dir, asset_output_url, canvas_output_folder_name,
              read_workflow_record):
    global _USER_DATA_DIR, _POLL_TIMEOUT, _log_file
    _USER_DATA_DIR = user_data_dir
    global _r_comfy_instances_file_path, _r_read_comfy_instances, _r_normalize_comfy_instances
    global _r_asset_output_media_dir, _r_asset_output_url, _r_canvas_output_folder_name
    global _r_read_workflow_record
    _POLL_TIMEOUT = poll_timeout
    _log_file = log_file_getter
    _r_comfy_instances_file_path = comfy_instances_file_path
    _r_read_comfy_instances = read_comfy_instances
    _r_normalize_comfy_instances = normalize_comfy_instances
    _r_asset_output_media_dir = asset_output_media_dir
    _r_asset_output_url = asset_output_url
    _r_canvas_output_folder_name = canvas_output_folder_name
    _r_read_workflow_record = read_workflow_record

    # 服务层注入（原块顶层 comfy_flow_service.configure，依赖注入值故挪到此处）
    comfy_flow_service.configure(
        base_provider=comfy_instance_base,
        asset_saver=comfy_output_asset_url,
        cache_path=_USER_DATA_DIR / "cache" / "comfy_object_info.json",
        job_store_path=_USER_DATA_DIR / "data" / "comfy_jobs.json",
    )


def write_comfy_instances(instances):
    safe = _r_normalize_comfy_instances(instances)
    write_json_file(_r_comfy_instances_file_path(), {"instances": safe})
    return safe


def comfy_instance_base():
    instances = _r_read_comfy_instances()
    raw = instances[0] if instances else "127.0.0.1:8188"
    base = str(raw or "").strip()
    if not base:
        base = "127.0.0.1:8188"
    if not re.match(r"^https?://", base, re.I):
        base = "http://" + base
    return base.rstrip("/")


def comfy_request_json(base, path, method="GET", payload=None, timeout=120):
    raw = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(base + path, data=raw, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    return json.loads(body.decode("utf-8") or "{}")


def apply_comfy_workflow_fields(workflow, config, fields):
    result = json.loads(json.dumps(workflow if isinstance(workflow, dict) else {}))
    safe_config = config if isinstance(config, dict) else {}
    safe_fields = fields if isinstance(fields, dict) else {}
    applied_media = []
    for field in safe_config.get("fields") or []:
        if not isinstance(field, dict):
            continue
        node_id = str(field.get("node") or "").strip()
        input_key = str(field.get("input") or "").strip()
        if not node_id or not input_key or node_id not in result:
            continue
        supplied = field.get("id") in safe_fields
        value = safe_fields.get(field.get("id"), field.get("default"))
        field_type = str(field.get("type") or "").lower()
        field_id = field.get("id")
        if field_type in ("number", "slider"):
            try:
                value = float(value)
                if value.is_integer():
                    value = int(value)
            except Exception:
                pass
        elif field_type == "boolean":
            value = bool(value)
        result.setdefault(node_id, {}).setdefault("inputs", {})[input_key] = value
        if field_type in {"image", "video", "audio"}:
            applied_media.append({
                "id": str(field_id or ""),
                "type": field_type,
                "node": node_id,
                "input": input_key,
                "value": str(value or "")[:240],
                "supplied": supplied,
            })
    if applied_media:
        append_log(_log_file(), "comfy workflow media fields applied " + json.dumps(applied_media, ensure_ascii=False))
    return result


def comfy_output_asset_url(base, item, prompt_id, kind="image", canvas_title="", canvas_id=""):
    filename = str(item.get("filename") or "").strip()
    if not filename:
        return ""
    params = {
        "filename": filename,
        "type": str(item.get("type") or "output"),
        "subfolder": str(item.get("subfolder") or ""),
    }
    url = base + "/view?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=120) as response:
        raw = response.read()
    media_kind = str(kind or "image").strip().lower() or "image"
    canvas_folder = _r_canvas_output_folder_name(canvas_title, canvas_id) if canvas_title or canvas_id else ""
    output_dir = _r_asset_output_media_dir(media_kind, canvas_folder)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^0-9A-Za-z._-]+", "_", filename)
    target = output_dir / f"comfy_{prompt_id}_{safe_name}"
    target.write_bytes(raw)
    return _r_asset_output_url(target.name, media_kind, canvas_folder=canvas_folder)


# 工作流卡片节点依赖的服务层：节点元数据缓存与异步任务队列。
# 宿主能力在这里注入，服务层不反向 import 本模块。


def select_comfy_output_nodes(history):
    outputs = history.get("outputs") if isinstance(history, dict) else {}
    if not isinstance(outputs, dict):
        return []
    image_nodes = []
    video_nodes = []
    for node_id, node_output in outputs.items():
        if not isinstance(node_output, dict):
            continue
        if node_output.get("images"):
            image_nodes.append((str(node_id), node_output))
        elif node_output.get("videos") or node_output.get("gifs") or node_output.get("video"):
            video_nodes.append((str(node_id), node_output))
    if len(image_nodes) > 1:
        return [image_nodes[-1]]
    if image_nodes:
        return image_nodes
    if len(video_nodes) > 1:
        return [video_nodes[-1]]
    return video_nodes


def build_comfy_workflow_prompt(name, payload):
    """按 payload 构造最终要提交给 ComfyUI 的 prompt（字段覆盖 / 节点开关编译都在这里）。"""
    record = _r_read_workflow_record(name)
    config = payload.get("config") if isinstance(payload.get("config"), dict) else record.get("config")
    modes = payload.get("modes") if isinstance(payload.get("modes"), dict) else None
    if modes:
        # 画布生成节点传来的节点开关（bypass / mute），交给编译器改写整张图。
        # 这一步是必需的：ComfyUI 的 /prompt 不认识 mode 字段，bypass 得自己算。
        # 先应用暴露字段（提示词/参数），再叠加节点开关，两者可同时生效。
        base_prompt = apply_comfy_workflow_fields(
            record.get("workflow") if isinstance(record.get("workflow"), dict) else {},
            config,
            payload.get("fields"),
        )
        if isinstance(payload.get("params"), dict) and payload.get("params"):
            base_prompt = json.loads(json.dumps(base_prompt or {}))
            for node_id, overrides in payload.get("params", {}).items():
                if not isinstance(overrides, dict) or str(node_id) not in base_prompt:
                    continue
                base_prompt[str(node_id)].setdefault("inputs", {}).update(overrides)
        prompt, _report = compile_comfy_prompt(
            base_prompt or {},
            {},
            modes,
            comfy_flow_service.load_object_info(),
        )
    elif isinstance(payload.get("params"), dict):
        # Canvas custom-Comfy calls already provide node/input overrides.
        # Keep this path local to Comfy workflow execution; legacy API modes
        # continue to use their existing compatibility handler.
        prompt = json.loads(json.dumps(record.get("workflow") if isinstance(record.get("workflow"), dict) else {}))
        for node_id, overrides in payload.get("params", {}).items():
            if not isinstance(overrides, dict) or str(node_id) not in prompt:
                continue
            prompt[str(node_id)].setdefault("inputs", {}).update(overrides)
    else:
        prompt = apply_comfy_workflow_fields(record.get("workflow"), config, payload.get("fields"))
    if not prompt:
        raise ApiError(400, "工作流为空")
    return prompt


def submit_comfy_workflow_job(name, payload, prompt=None):
    """走全局 FIFO 队列提交一条工作流，立即返回 job（HTTP 不阻塞）。

    以前这里是直接 POST /prompt 再 while 轮询 /history，会把 HTTP 请求一直挂到
    工作流跑完（上限 3600 秒），而且绕开队列、可能和画布节点抢显存。
    """
    payload = payload if isinstance(payload, dict) else {}
    if prompt is None:
        prompt = build_comfy_workflow_prompt(name, payload)
    client_id = str(payload.get("client_id") or uuid.uuid4().hex)
    meta = {
        "source": "workflow_run",
        "workflow": str(name or ""),
        "canvas_id": str(payload.get("canvas_id") or "").strip(),
        "canvas_title": str(payload.get("canvas_title") or "").strip(),
    }
    job = comfy_flow_service.MANAGER.submit(str(name or ""), prompt, client_id, meta=meta)
    append_log(_log_file(), f"comfy workflow queued name={name} job_id={job.id} position={job.queue_position}")
    return job


def run_comfy_workflow(name, payload):
    """同步执行一条工作流：底层走统一 FIFO 队列，外层等结果。

    payload['async'] = True 时只入队并立即返回 job_id，HTTP 不再挂到跑完
    （设置页试跑走这条，免得一个请求卡一小时）。
    """
    payload = payload if isinstance(payload, dict) else {}
    prompt = build_comfy_workflow_prompt(name, payload)
    job = submit_comfy_workflow_job(name, payload, prompt=prompt)
    if payload.get("async") is True or payload.get("wait") is False:
        return {
            "ok": True,
            "async": True,
            "job_id": job.id,
            "status": job.status,
            "queue_position": job.queue_position,
        }
    finished = comfy_flow_service.MANAGER.wait(job.id, timeout=_POLL_TIMEOUT)
    if finished is None:
        raise ApiError(504, "任务记录已丢失，后端可能重启过")
    if finished.status == comfy_flow_service.STATUS_ERROR:
        raise ApiError(502, finished.error or "ComfyUI 执行失败")
    if finished.status == comfy_flow_service.STATUS_CANCELLED:
        raise ApiError(409, "任务已取消")
    if finished.status != comfy_flow_service.STATUS_DONE:
        elapsed = int(time.time() - (job.created_at or time.time()))
        append_log(_log_file(), f"comfy workflow timeout name={name} job_id={job.id} elapsed={elapsed}s")
        raise ApiError(504, f"ComfyUI 执行超时：已等待 {elapsed} 秒，工作流可能仍在后台运行。")
    append_log(_log_file(), f"comfy workflow succeeded name={name} prompt_id={finished.prompt_id} job_id={finished.id} images={len(finished.images)} videos={len(finished.videos)}")
    return {
        "ok": True,
        "prompt_id": finished.prompt_id,
        "images": finished.images,
        "videos": finished.videos,
        "job_id": finished.id,
    }


def recent_comfy_outputs(payload=None):
    payload = payload if isinstance(payload, dict) else {}
    limit = max(1, min(20, int(payload.get("limit") or 6)))
    base = comfy_instance_base()
    history_all = comfy_request_json(base, "/history", "GET", timeout=30)
    # 只归档 MyridTV 自己提交的任务：外部（含 ComfyUI 网页手动跑）的 prompt 不落盘，
    # 防止窗口 focus 时把别人的图拷进 assets/output/images/history。
    known_ids = set()
    try:
        for job in comfy_flow_service.MANAGER.list_jobs(limit=100):
            pid = str(job.get("prompt_id") or "").strip()
            if pid:
                known_ids.add(pid)
    except Exception:
        pass
    rows = []
    if isinstance(history_all, dict):
        for prompt_id, history in history_all.items():
            if str(prompt_id) not in known_ids:
                continue
            if not isinstance(history, dict):
                continue
            order = 0
            prompt_info = history.get("prompt")
            if isinstance(prompt_info, list) and prompt_info:
                try:
                    order = int(prompt_info[0])
                except Exception:
                    order = 0
            images = []
            videos = []
            for _node_id, node_output in select_comfy_output_nodes(history):
                if not isinstance(node_output, dict):
                    continue
                for item in node_output.get("images") or []:
                    url = comfy_output_asset_url(base, item, str(prompt_id), "image")
                    if url:
                        images.append(url)
                for item in (node_output.get("videos") or []) + (node_output.get("gifs") or []):
                    url = comfy_output_asset_url(base, item, str(prompt_id), "video")
                    if url:
                        videos.append(url)
            if images or videos:
                rows.append({"prompt_id": str(prompt_id), "order": order, "images": images, "videos": videos})
    rows.sort(key=lambda item: int(item.get("order") or 0), reverse=True)
    return {"ok": True, "outputs": rows[:limit]}


def comfy_workflow_split_clusters(workflow):
    """多管线集合检测：按输出节点沿上游回溯聚簇。

    返回 (clusters, dropped)：
    - clusters: [{"nodes": {id: node}, "save_id": 输出节点id}, ...]，按簇规模降序
    - dropped: 未归属任何簇的节点 id 集合（悬空预览、未连线节点、多余原图 SaveImage）
    只有聚出 >=2 个互不重叠的簇才视为集合；单输出或交叠图（同一链上双 SaveImage）返回 ([], set())。
    """
    if not isinstance(workflow, dict) or not workflow:
        return [], set()

    def upstream(nid):
        seen = set()
        stack = [nid]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            node = workflow.get(cur)
            if not isinstance(node, dict):
                continue
            for value in (node.get("inputs") or {}).values():
                if isinstance(value, list) and len(value) == 2 and str(value[0]) in workflow:
                    stack.append(str(value[0]))
        return seen

    save_ids = [str(nid) for nid, node in workflow.items()
                if isinstance(node, dict) and str(node.get("class_type") or "").lower() in ("saveimage", "vhs_videocombine")]
    if len(save_ids) < 2:
        return [], set()
    clusters = []
    claimed = set()
    for sid in sorted(save_ids, key=lambda x: -len(upstream(x))):
        nodes = upstream(sid)
        if not nodes or (nodes & claimed):
            continue  # 与更大簇共享节点（同一链上的双 SaveImage）→ 不独立成簇
        claimed |= nodes
        clusters.append({"nodes": {nid: workflow[nid] for nid in nodes}, "save_id": sid})
    if len(clusters) < 2:
        return [], set()
    clusters.sort(key=lambda c: -len(c["nodes"]))
    dropped = {str(nid) for nid in workflow if nid not in claimed}
    return clusters, dropped


