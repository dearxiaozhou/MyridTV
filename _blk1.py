# ====== 任务运行控制台（task-console）======
TASK_CONSOLE_CANCELLED = set()
TASK_CONSOLE_CANCELLED_LOCK = threading.Lock()
# 高成本模型关键词（官方贵档/4K档）
TASK_CONSOLE_COSTLY_MODEL_PAT = re.compile(r"official|g-2-official|4k|seedance|premium", re.I)


def _task_console_kind(task_id, state):
    tid = str(task_id or "")
    backend = str(state.get("backend") or "")
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
    submit = state.get("submit") if isinstance(state.get("submit"), dict) else {}
    if state.get("rh_task_id") or backend == "runninghub-official":
        model = str(state.get("model") or "")
        if "/image-to-image" in model or state.get("mode") == "i2i":
            return "图生图"
        return "生图"
    if tid.startswith("rhproxy"):
        return "生图"
    if tid.startswith("volc"):
        return "视频"
    return "其他"


def _task_console_platform(state):
    backend = str(state.get("backend") or "")
    provider = str(state.get("provider_id") or "")
    if backend == "volcengine-ark" or provider == "volcengine":
        return "火山方舟"
    if backend == "blender-previz" or provider == "blender":
        return "Blender"
    if backend == "comfyui" or provider == "comfyui":
        return "ComfyUI"
    if backend.startswith("runninghub") or provider == "runninghub":
        return "RunningHub"
    if state.get("rh_task_id"):
        return "RunningHub"
    if provider:
        return provider
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
    if TASK_CONSOLE_COSTLY_MODEL_PAT.search(model):
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
            "mode": str(st.get("mode") or ("i2i" if (st.get("reference_images") or st.get("reference_image_urls")) else "t2i")),
            "provider_task_id": str(st.get("provider_task_id") or st.get("rh_task_id") or ""),
            "created_at": st.get("created_at") or 0,
            "completed_at": st.get("completed_at") or 0,
            "error": str(st.get("error") or st.get("last_error") or "")[:300],
            "outputs": len(out_images) + len(out_videos),
            "risks": _task_console_risks(tid, st),
        })
    items.sort(key=lambda x: x.get("created_at") or 0, reverse=True)
    # 统计：今日
    day_start = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, 0))
    today = [it for it in items if (it.get("created_at") or 0) >= day_start]
    today_ok = [it for it in today if it.get("status") == "succeeded"]
    today_fail = [it for it in today if it.get("status") == "failed"]
    model_calls = {}
    for it in today:
        key = it["platform"] + " / " + it["model"]
        entry = model_calls.setdefault(key, {"calls": 0, "failed": 0, "outputs": 0})
        entry["calls"] += 1
        if it["status"] == "failed":
            entry["failed"] += 1
        entry["outputs"] += it["outputs"]
    stats = {
        "today_total": len(today),
        "today_success": len(today_ok),
        "today_failed": len(today_fail),
        "today_failure_rate": round(len(today_fail) * 100.0 / len(today), 1) if today else 0.0,
        "today_outputs": sum(it["outputs"] for it in today_ok),
        "running": sum(1 for it in items if it["status"] == "running"),
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
    with TASKS_LOCK:
        for tid in task_ids:
            tid = str(tid or "").strip()
            if not tid:
                continue
            st = TASKS.get(tid)
            if not isinstance(st, dict):
                missing.append(tid)
                continue
            if str(st.get("status")) == "running":
                with TASK_CONSOLE_CANCELLED_LOCK:
                    TASK_CONSOLE_CANCELLED.add(tid)
                # 立刻标记取消；轮询线程检测到后不再覆盖状态
                st["status"] = "cancelled"
                st["error"] = "用户手动停止"
                st["completed_at"] = time.time()
                if st.get("persistent"):
                    persist_tasks_locked()
                stopped.append(tid)
            else:
                missing.append(tid)
    return {"ok": True, "stopped": stopped, "skipped": missing}


def _task_console_is_cancelled(task_id):
    with TASK_CONSOLE_CANCELLED_LOCK:
        return str(task_id or "") in TASK_CONSOLE_CANCELLED
