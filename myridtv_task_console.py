# -*- coding: utf-8 -*-
"""MyridTV 任务控制台快照域（后端拆分第24刀）：任务分类/媒体类型/平台/模型/
风险/来源标注、Comfy 队列合流、输出拆分、快照 snapshot、取消三件套
（stop/is_cancelled/Cancelled 异常）。

逐字迁移自 rh_official_proxy.py 连续块（9 函数 + 1 类，可逆还原行级
diff=0）。行为零变更。configure() 注入：TASKS/TASKS_LOCK/TASK_STORE 三单例
同对象（权威留主，模块内裸名零改写——第18刀处方）、recover_stale_tasks
延迟闭包（真身留主）、LOG_FILE getter。TASK_CONSOLE_* 三单例与
load_persistent_tasks/persist_tasks_locked 属性链直引 myridtv_task_state，
_agent_task_log 直引 myridtv_agent_tasks（壳穿透=打桩可跑）。
主文件留 snapshot/stop/is_cancelled 薄代理与 _TaskConsoleCancelled 别名。
"""
import re
import threading
import time

import comfy_flow_service

from myridtv_core import append_log, _task_console_ts

import myridtv_agent_tasks
import myridtv_provider
import myridtv_task_state

TASKS = {}
TASKS_LOCK = threading.Lock()
TASK_STORE = None
_log_file = lambda: None
_r_recover_stale_tasks = None


def configure(tasks, tasks_lock, task_store, recover_stale_tasks, log_file_getter):
    global TASKS, TASKS_LOCK, TASK_STORE
    global _log_file, _r_recover_stale_tasks
    TASKS = tasks
    TASKS_LOCK = tasks_lock
    TASK_STORE = task_store
    _log_file = log_file_getter
    _r_recover_stale_tasks = recover_stale_tasks


def _task_console_kind(task_id, state):
    tid = str(task_id or "")
    backend = str(state.get("backend") or "")
    submit = state.get("submit") if isinstance(state.get("submit"), dict) else {}
    if backend == "provider-audio":
        return "语音"
    if state.get("workflow_type") == "video_creation":
        return "智能体任务"
    if backend == "volcengine-ark":
        return "视频"
    if backend == "blender-previz":
        return "视频"
    if backend == "comfyui":
        return "ComfyUI"
    if backend == "runninghub-workflow":
        return "RunningHub 工作流"
    if state.get("rh_task_id") or backend == "runninghub-official":
        model = str(state.get("model") or "")
        if "/image-to-image" in model or state.get("mode") == "i2i":
            return "图生图"
        return "生图"
    if tid.startswith("rhproxy"):
        return "生图"
    if tid.startswith("volc"):
        return "视频"
    # 有 submit payload 但没有明确后端：webappId=RH 会员 API 生图（Agent 建的节点也走这里）
    if submit.get("webappId") or submit.get("prompt") is not None:
        return "生图"
    return "其他"


def _task_media_type(item):
    """任务级媒体归类：所有任务强制二分 image / video，保证明细加和=总数。
    判定源=kind 优先，工作流/未知类看产出条目；智能体任务(短片流水线)按视频计。"""
    workflow_media = str(item.get("workflow_media") or "").strip().lower()
    if workflow_media in ("video", "image", "audio"):
        return workflow_media
    kind = str(item.get("kind") or "")
    if kind == "语音":
        return "audio"
    if kind == "视频":
        return "video"
    if kind in ("生图", "图生图"):
        return "image"
    if kind == "智能体任务":
        return "video"
    if (item.get("output_videos") or 0) > 0:
        return "video"
    return "image"


def _task_console_platform(state):
    backend = str(state.get("backend") or "")
    provider = str(state.get("provider_id") or "")
    if backend in ("provider-openai", "provider-audio"):
        # 通用 OpenAI 兼容平台：rh_task_id 字段只是通用 task_id，绝不能显示成 RunningHub
        try:
            for item in myridtv_provider.read_api_providers() or []:
                if isinstance(item, dict) and str(item.get("id") or "") == provider:
                    return str(item.get("name") or "").strip() or provider
        except Exception:
            pass
        return provider or "API平台"
    if backend == "volcengine-ark" or provider == "volcengine":
        return "火山方舟"
    if backend == "blender-previz" or provider == "blender":
        return "Blender"
    if backend == "comfyui" or provider == "comfyui":
        return "ComfyUI"
    if backend.startswith("runninghub") or provider == "runninghub":
        return "RunningHub"
    if provider:
        return provider
    if state.get("rh_task_id"):
        return "RunningHub"
    return backend or "未知"


def _task_console_model(state):
    for key in ("model",):
        val = str(state.get(key) or "").strip()
        if val:
            return val
    body = state.get("submit") if isinstance(state.get("submit"), dict) else None
    if body:
        val = str(body.get("model") or "").strip()
        if val:
            return val
    return "—"


def _task_console_risks(task_id, state):
    risks = []
    kind = state.get("_kind") or ""
    model = _task_console_model(state)
    resolution = str(state.get("resolution") or (state.get("submit") or {}).get("resolution") if isinstance(state.get("submit"), dict) else state.get("resolution") or "").lower()
    if myridtv_task_state.TASK_CONSOLE_COSTLY_MODEL_PAT.search(model):
        risks.append("高成本模型")
    if "4k" in str(resolution).lower():
        risks.append("4K 分辨率")
    try:
        n = int(state.get("count") or state.get("n") or 1)
    except Exception:
        n = 1
    if n >= 4:
        risks.append("多张并发(%d)" % n)
    if kind == "视频":
        risks.append("视频任务成本高")
    if kind == "RunningHub 工作流":
        risks.append("云端工作流")
    return risks


def _task_console_origin(task_id, state):
    tid = str(task_id or "")
    if tid.startswith("rhproxy"):
        return "画布节点执行"
    if tid.startswith("volc"):
        return "画布节点执行"
    if tid.startswith("task_"):
        return "Myrid-Agent"
    if state.get("source") == "mcp":
        return "MCP 工具"
    if state.get("source") == "agent":
        return "智能体"
    return str(state.get("source") or "画布节点执行")


def _comfy_console_items():
    """把 ComfyUI 独立账本（comfy_flow_service.MANAGER）映射成控制台条目。

    只读合并，不写 TASKS、不改 ComfyJob 存储 —— ComfyUI 与主账本就是两套落盘。
    task_id 前缀 comfy: 供 /api/task-console-stop 反解出 job_id 走 MANAGER.cancel。
    """
    items = []
    try:
        jobs = comfy_flow_service.MANAGER.list_jobs(limit=500)
    except Exception as exc:
        append_log(_log_file(), f"comfy console merge failed: {exc}")
        return items
    status_map = {
        "queued": "queued",
        "running": "running",
        "done": "succeeded",
        "error": "failed",
        "cancelled": "cancelled",
        "gone": "interrupted",
    }
    for job in jobs:
        if not isinstance(job, dict):
            continue
        meta = job.get("meta") if isinstance(job.get("meta"), dict) else {}
        c_img_n, c_vid_n = _task_console_split_outputs(job.get("images") or [], job.get("videos") or [])
        out_count = len(job.get("images") or []) + len(job.get("videos") or [])
        created_ts = _task_console_ts(job.get("created_at"))
        finished_ts = _task_console_ts(job.get("finished_at"))
        duration = None
        if created_ts and finished_ts and finished_ts >= created_ts:
            duration = int(finished_ts - created_ts)
        items.append({
            "task_id": "comfy:" + str(job.get("job_id") or ""),
            "kind": "ComfyUI",
            "status": status_map.get(str(job.get("status") or ""), "unknown"),
            "platform": "ComfyUI",
            "model": str(job.get("workflow_name") or "—"),
            "resolution": "—",
            "count": max(1, out_count) if out_count else 1,
            "origin": str(meta.get("origin") or "ComfyUI 工作流"),
            "canvas_id": str(meta.get("canvas_id") or ""),
            "canvas_title": str(meta.get("canvas_title") or ""),
            "node_id": str(meta.get("node_id") or ""),
            "node_title": str(meta.get("node_title") or ""),
            "mode": str(meta.get("mode") or "comfy"),
            "ratio": "",
            "quality": "",
            "provider_task_id": str(job.get("prompt_id") or ""),
            "created_at": created_ts,
            "completed_at": finished_ts,
            "checked_at": _task_console_ts(job.get("finished_at") or job.get("started_at")),
            "duration": duration,
            "error": str(job.get("error") or "")[:2000],
            "outputs": out_count,
            "output_images": c_img_n,
            "output_videos": c_vid_n,
            "progress": job.get("progress"),
            "current_node": str(job.get("current_node_title") or job.get("current_node") or ""),
            "risks": [],
            "params": {
                "flat": meta.get("params_flat") if isinstance(meta.get("params_flat"), list) else [],
                "modes": meta.get("modes") if isinstance(meta.get("modes"), dict) else {},
                "node_titles": meta.get("node_titles") if isinstance(meta.get("node_titles"), dict) else {},
            },
        })
    return items


def _task_console_split_outputs(images, videos):
    """按条目真实 kind 拆分产出计数（blender/RH 会把视频塞进 images 列表，条目 kind 才可信）。"""
    img_n = vid_n = 0
    for item in list(images or []) + list(videos or []):
        kind = ""
        if isinstance(item, dict):
            kind = str(item.get("kind") or item.get("media_kind") or "").strip().lower()
            if not kind:
                url = str(item.get("url") or "")
                kind = "video" if re.search(r"\.(mp4|mov|webm|avi|mkv)(\?|$)", url, re.I) else ""
        elif isinstance(item, str):
            kind = "video" if re.search(r"\.(mp4|mov|webm|avi|mkv)(\?|$)", item, re.I) else ""
        if kind == "video":
            vid_n += 1
        elif kind != "audio":
            img_n += 1
    return img_n, vid_n


def task_console_snapshot():
    now = time.time()
    items = []
    with TASKS_LOCK:
        raw = {tid: dict(st) for tid, st in TASKS.items() if isinstance(st, dict)}
    for tid, st in raw.items():
        kind = _task_console_kind(tid, st)
        st["_kind"] = kind
        submit = st.get("submit") if isinstance(st.get("submit"), dict) else {}
        resolution = str(st.get("resolution") or submit.get("resolution") or "").strip()
        count = st.get("count") or st.get("n") or 1
        try:
            count = int(count)
        except Exception:
            count = 1
        result = st.get("result") if isinstance(st.get("result"), dict) else {}
        out_images = result.get("images") if isinstance(result.get("images"), list) else []
        out_videos = result.get("videos") if isinstance(result.get("videos"), list) else []
        out_audios = result.get("audios") if isinstance(result.get("audios"), list) else []
        n_img, n_vid = _task_console_split_outputs(out_images, out_videos)
        created_ts = _task_console_ts(st.get("created_at"))
        completed_ts = _task_console_ts(st.get("completed_at"))
        checked_ts = _task_console_ts(st.get("checked_at"))
        duration = None
        if created_ts and completed_ts and completed_ts >= created_ts:
            duration = int(completed_ts - created_ts)
        items.append({
            "task_id": tid,
            "kind": kind,
            "status": str(st.get("status") or "unknown"),
            "platform": _task_console_platform(st),
            "model": _task_console_model(st),
            "resolution": resolution or "—",
            "count": count,
            "origin": _task_console_origin(tid, st),
            "canvas_id": str(st.get("canvas_id") or ""),
            "canvas_title": str(st.get("canvas_title") or ""),
            "node_id": str(st.get("node_id") or ""),
            "node_title": str(st.get("node_title") or ""),
            "mode": str(st.get("mode") or ("i2i" if (st.get("reference_images") or st.get("reference_image_urls")) else "t2i")),
            # 云端工作流身份（2026-10-21）：新增工作流只要在 api_providers 登记就自动带出来
            "workflow_id": str(st.get("workflow_id") or ""),
            "workflow_title": str(st.get("workflow_title") or ""),
            "workflow_media": str(st.get("workflow_media") or ""),
            "ratio": str(st.get("ratio") or submit.get("ratio") or "").strip(),
            "quality": str(st.get("quality") or submit.get("quality") or "").strip(),
            "provider_task_id": str(st.get("provider_task_id") or st.get("rh_task_id") or ""),
            "created_at": created_ts,
            "completed_at": completed_ts,
            "checked_at": checked_ts,
            "duration": duration,
            "error": str(st.get("error") or st.get("last_error") or "")[:2000],
            "can_stop":st.get("can_stop",True),
            "audio_format":str(st.get("audio_format") or ""),
            "outputs": len(out_images) + len(out_videos) + len(out_audios),
            "output_audios":len(out_audios),
            "output_images": n_img,
            "output_videos": n_vid,
            "risks": _task_console_risks(tid, st),
        })
    items.extend(_comfy_console_items())
    items.sort(key=lambda x: _task_console_ts(x.get("created_at")), reverse=True)
    # 统计：今日
    day_start = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, 0))
    today = [it for it in items if _task_console_ts(it.get("created_at")) >= day_start]
    today_ok = [it for it in today if it.get("status") == "succeeded"]
    today_fail = [it for it in today if it.get("status") == "failed"]
    model_calls = {}
    for it in today:
        key = it["platform"] + " / " + it["model"]
        entry = model_calls.setdefault(key, {"calls": 0, "failed": 0, "outputs": 0, "out_images": 0, "out_videos": 0, "out_audios":0})
        entry["calls"] += 1
        if it["status"] == "failed":
            entry["failed"] += 1
        entry["outputs"] += it["outputs"]
        entry["out_images"] += it.get("output_images") or 0
        entry["out_videos"] += it.get("output_videos") or 0
        entry["out_audios"] += it.get("output_audios") or 0
    running_items = [it for it in items if it["status"] == "running"]

    def _media_split(group):
        out = {"image": 0, "video": 0, "audio":0}
        for it in group:
            out[_task_media_type(it)] += 1
        return out

    def _media_failure_rate(group):
        out = {}
        for media in ("image", "video", "audio"):
            sub_total = [it for it in group if _task_media_type(it) == media]
            sub_fail = [it for it in sub_total if it["status"] == "failed"]
            out[media] = round(len(sub_fail) * 100.0 / len(sub_total), 1) if sub_total else 0.0
        return out

    stats = {
        "today_total": len(today),
        "today_total_media": _media_split(today),
        "today_success": len(today_ok),
        "today_success_media": _media_split(today_ok),
        "today_failed": len(today_fail),
        "today_failed_media": _media_split(today_fail),
        "today_failure_rate": round(len(today_fail) * 100.0 / len(today), 1) if today else 0.0,
        "today_failure_rate_media": _media_failure_rate(today),
        "today_outputs": sum(it["outputs"] for it in today_ok),
        "today_output_images": sum(it.get("output_images") or 0 for it in today_ok),
        "today_output_videos": sum(it.get("output_videos") or 0 for it in today_ok),
        "today_output_audios":sum(it.get("output_audios") or 0 for it in today_ok),
        "running": len(running_items),
        "running_media": _media_split(running_items),
        "models": [
            {"key": k, **v, "failure_rate": round(v["failed"] * 100.0 / v["calls"], 1) if v["calls"] else 0.0}
            for k, v in sorted(model_calls.items(), key=lambda kv: -kv[1]["calls"])
        ],
    }
    return {"ok": True, "tasks": items, "stats": stats, "now": now}


class _TaskConsoleCancelled(RuntimeError):
    pass


def task_console_stop(payload):
    task_ids = payload.get("task_ids") if isinstance(payload.get("task_ids"), list) else []
    if not task_ids and payload.get("task_id"):
        task_ids = [payload.get("task_id")]
    stopped, missing = [], []
    # ComfyUI 任务（comfy:<job_id>）走独立账本的 cancel，不查 TASKS
    comfy_ids = [str(t or "").strip() for t in task_ids if str(t or "").startswith("comfy:")]
    for cid in comfy_ids:
        job_id = cid.split(":", 1)[1]
        try:
            job = comfy_flow_service.MANAGER.cancel(job_id)
        except Exception:
            job = None
        if job:
            stopped.append(cid)
        else:
            missing.append(cid)
    task_ids = [t for t in task_ids if not str(t or "").startswith("comfy:")]
    with TASKS_LOCK:
        for tid in task_ids:
            tid = str(tid or "").strip()
            if not tid:
                continue
            st = TASKS.get(tid)
            if not isinstance(st, dict):
                missing.append(tid)
                continue
            if st.get("can_stop") is False:
                missing.append(tid)
                continue
            if str(st.get("status")) == "running":
                with myridtv_task_state.TASK_CONSOLE_CANCELLED_LOCK:
                    myridtv_task_state.TASK_CONSOLE_CANCELLED.add(tid)
                # 立刻标记取消；轮询线程检测到后不再覆盖状态
                st["status"] = "cancelled"
                st["error"] = "用户手动停止"
                st["completed_at"] = time.time()
                if st.get("persistent"):
                    myridtv_task_state.persist_tasks_locked()
                stopped.append(tid)
            else:
                missing.append(tid)
    return {"ok": True, "stopped": stopped, "skipped": missing}


def _task_console_is_cancelled(task_id):
    with myridtv_task_state.TASK_CONSOLE_CANCELLED_LOCK:
        return str(task_id or "") in myridtv_task_state.TASK_CONSOLE_CANCELLED


