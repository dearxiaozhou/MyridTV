# -*- coding: utf-8 -*-
"""MyridTV 任务状态域（后端拆分第5刀）：裸 TASKS 账本的读写 API（set/update/get/持久化/
启动自愈）+ 控制台取消集合与昂贵模型正则、僵尸态白名单。

逐字迁移自 rh_official_proxy.py 块 L(persistent_task_payload)..L(_task_console_kind) 前
（7 函数 + 5 常量，零改写——SUBS 为空）。行为零变更。
configure() 绑定共享对象（非复制）：TASKS/TASKS_LOCK/TASK_STORE 初始化后全局零重绑，
已机械验证，传引用与主文件消费方同一对象；_agent_task_log 为日志回调。
TASK_CONSOLE_CANCELLED / TASK_CONSOLE_CANCELLED_LOCK / TASK_CONSOLE_COSTLY_MODEL_PAT
可变单例归本模块定义，主文件别名再导出（同对象，取消集合跨模块互见）。
主文件对块外仍调用的函数留同名薄代理，调用点不改。
"""
import json
import re
import threading
import time

TASKS = {}
TASKS_LOCK = None
TASK_STORE = None
_agent_task_log = lambda category, message: None


def configure(tasks, tasks_lock, task_store, agent_task_log):
    global TASKS, TASKS_LOCK, TASK_STORE, _agent_task_log
    TASKS = tasks
    TASKS_LOCK = tasks_lock
    TASK_STORE = task_store
    _agent_task_log = agent_task_log


def persistent_task_payload(state):
    if not isinstance(state, dict):
        return {}
    safe = {}
    for key, value in state.items():
        if key.startswith("_"):
            continue
        try:
            json.dumps(value, ensure_ascii=False)
        except Exception:
            continue
        safe[key] = value
    safe["persistent"] = True
    return safe


def persist_tasks_locked(task_id=None):
    """写任务表：给了 task_id 只写这一行（热路径），否则整表同步一次事务。

    注意：本函数自身不加锁，必须在 TASKS_LOCK 内调用。
    """
    if task_id is not None:
        safe_id = str(task_id)
        state = TASKS.get(safe_id)
        if isinstance(state, dict) and state.get("persistent"):
            TASK_STORE.upsert(safe_id, persistent_task_payload(state))
        return
    TASK_STORE.upsert_many({
        task_id: persistent_task_payload(state)
        for task_id, state in TASKS.items()
        if isinstance(state, dict) and state.get("persistent")
    })


def set_task_state(task_id, state, persistent=False):
    safe_id = str(task_id or "").strip()
    if not safe_id:
        return {}
    safe_state = dict(state or {})
    if persistent or safe_state.get("persistent"):
        safe_state["persistent"] = True
    with TASKS_LOCK:
        TASKS[safe_id] = safe_state
        if safe_state.get("persistent"):
            persist_tasks_locked(safe_id)
    return safe_state


def update_task_state(task_id, **updates):
    safe_id = str(task_id or "").strip()
    if not safe_id:
        return {}
    with TASKS_LOCK:
        current = dict(TASKS.get(safe_id) or {})
        current.update(updates)
        TASKS[safe_id] = current
        if current.get("persistent"):
            persist_tasks_locked(safe_id)
    if current.get("status") in ("succeeded", "failed") and current.get("canvas_id") and current.get("node_id"):
        if current.get("status") == "failed" or current.get("localized_at"):
            try:
                import myridtv_agent_generation
                myridtv_agent_generation.record_agent_generation_task_log(safe_id, current)
            except Exception as exc:
                _agent_task_log("CanvasAgentLog", "task={} log failed: {}".format(safe_id, exc))
    return current


def get_task_state(task_id):
    safe_id = str(task_id or "").strip()
    if not safe_id:
        return {}
    with TASKS_LOCK:
        return dict(TASKS.get(safe_id) or {})


def load_persistent_tasks():
    data = TASK_STORE.load_all()
    if not isinstance(data, dict):
        return
    with TASKS_LOCK:
        for task_id, state in data.items():
            if isinstance(state, dict) and task_id:
                TASKS[str(task_id)] = persistent_task_payload(state)


# ====== 启动自愈：上一次进程遗留的僵尸任务 ======
# 进程退出/崩溃时，任务表会永久残留 in-flight 状态：前端一直转圈、任务再也无法重新提交。
# 只有真正的僵尸态才收尾；waiting_user / paused 是健康的「等用户 / 已暂停」休息态，绝不动。
STALE_AGENT_TASK_STATUSES = {"pending", "running"}
STALE_MEDIA_TASK_STATUSES = {"pending", "running", "queued", "processing", "submitting"}


def recover_stale_tasks(source="MyridTV 后端重启"):
    """启动时把上一次进程遗留的 in-flight 任务收尾为 failed，并写明中断原因。

    Agent 任务里未收尾的 turn 一并置 failed，避免前端停在「思考中」。
    返回被收尾的 task_id 列表。
    """
    now = int(time.time() * 1000)
    reason = "{}，任务已中断并标记为失败，可重新提交".format(source)
    recovered = []
    with TASKS_LOCK:
        for task_id, state in TASKS.items():
            if not isinstance(state, dict):
                continue
            status = str(state.get("status") or "").strip().lower()
            is_agent = isinstance(state.get("turns"), list) or bool(state.get("workflow_type"))
            allowed = STALE_AGENT_TASK_STATUSES if is_agent else STALE_MEDIA_TASK_STATUSES
            if status not in allowed:
                continue
            tid = str(task_id or state.get("task_id") or "")
            # 2026-10-23 老王：云端任务（有 provider_task_id）不能因为「本地进程重启」就判死。
            # 进程重启 ≠ 云端任务失败：RH 那边还在跑、甚至已经出片了（实测：本地标 failed，
            # 云端其实 SUCCESS，26 币已扣，产物躺在 COS 上没人取）。
            # 这里先挂起等云端核实（由后台 probe 收尾），不要直接写死 failed。
            remote_id = str(state.get("provider_task_id") or state.get("rh_task_id") or "").strip()
            if remote_id:
                state["status"] = "recovering"
                state["error"] = ""
                state["recover_remote_id"] = remote_id
                state["recover_probe_at"] = now
                state["updated_at"] = now
                recovered.append(tid)
                continue
            state["status"] = "failed"
            state["error"] = reason
            state["failed_at"] = now
            state["updated_at"] = now
            if is_agent:
                for turn in reversed(state.get("turns") or []):
                    if isinstance(turn, dict) and str(turn.get("status") or "").strip().lower() in STALE_AGENT_TASK_STATUSES:
                        turn["status"] = "failed"
                        turn["error"] = reason
                        turn["updated_at"] = now
                        break
            recovered.append(tid)
        if recovered:
            persist_tasks_locked()
    for tid in recovered:
        _agent_task_log("StartupRecovery", "task={} -> failed ({})".format(tid, reason))
    if recovered:
        _agent_task_log("StartupRecovery", "已收尾 {} 个僵尸任务".format(len(recovered)))
    return recovered


# ====== 任务运行控制台（task-console）======
TASK_CONSOLE_CANCELLED = set()
TASK_CONSOLE_CANCELLED_LOCK = threading.Lock()
# 高成本模型关键词（官方贵档/4K档）
TASK_CONSOLE_COSTLY_MODEL_PAT = re.compile(r"official|g-2-official|4k|seedance|premium", re.I)


