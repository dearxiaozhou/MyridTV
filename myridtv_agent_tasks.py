# -*- coding: utf-8 -*-
"""MyridTV Agent 任务记账域（后端拆分第18刀）：任务日志行追加、失败标记
（含用户可见日志与落盘）、按 payload 定位任务、任务表保存、运行时结果挂载。

逐字迁移自 rh_official_proxy.py 连续块 L(_agent_task_log)..L(positive_env_int)
（5 函数 49 行，可逆还原行级 diff=0）。行为零变更。
TASKS/TASKS_LOCK 两单例定义留主文件（历史上是全局权威，多处跨域读写），
configure() 同对象引用注入——模块内裸名零改写（第5刀 task_state 同款处方）。
_agent_latest_user_text 直引 myridtv_agent_short_drama、persist_tasks_locked
直引 myridtv_task_state（壳穿透）；LOG_FILE×2 走 getter。
主文件对被仍引用的 5 函数留同名薄代理。
"""
import time

import agent_task_runtime as agent_runtime
from myridtv_core import append_log

import myridtv_agent_short_drama
import myridtv_task_state

# 原块内防御式写法 `"_agent_latest_user_text" in globals()` 决定取用户文本
# 还是 fallback——别名按原语义入模块 globals，行为零变更。
_agent_latest_user_text = myridtv_agent_short_drama._agent_latest_user_text

TASKS = None
TASKS_LOCK = None
_log_file = lambda: None


def configure(tasks, tasks_lock, log_file_getter):
    global TASKS, TASKS_LOCK, _log_file
    TASKS = tasks
    TASKS_LOCK = tasks_lock
    _log_file = log_file_getter


def _agent_task_log(category, message):
    append_log(_log_file(), "[{}] {}".format(category, message))


def _agent_mark_task_failed(task, turn, exc):
    """上游/配置异常时收尾任务：置 failed + 记原因。

    背景：submit_chat 抛异常时任务从不收尾，任务表里会永久留一条假 running
    （今天已踩两次：401 Invalid API-key、key 串平台）。
    """
    reason = str(exc or "").strip()[:300]
    now_ms = int(time.time() * 1000)
    try:
        if isinstance(task, dict):
            if str(task.get("status") or "") in {"pending", "running", "waiting_user", "paused"}:
                task["status"] = "failed"
            task["error"] = reason
            task["failed_at"] = now_ms
            task["updated_at"] = now_ms
        if isinstance(turn, dict):
            turn["status"] = "failed"
            turn["error"] = reason
            turn["updated_at"] = now_ms
        _agent_save_tasks()
        _agent_task_log("AgentTask", "task={} status=failed error={}".format(
            (task or {}).get("task_id") if isinstance(task, dict) else "", reason[:160]))
    except Exception as _e:
        append_log(_log_file(), "agent mark-task-failed error: {}".format(_e))


def _agent_task_for_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    conversation_id = str(payload.get("agent_session_id") or payload.get("session_id") or "").strip()
    canvas_id = str(payload.get("canvas_id") or "").strip()
    task_id = str(payload.get("task_id") or payload.get("agent_task_id") or "").strip()
    user_text = _agent_latest_user_text(payload) if "_agent_latest_user_text" in globals() else str(payload.get("message") or "")
    with TASKS_LOCK:
        task = agent_runtime.ensure_task(TASKS, conversation_id, canvas_id, user_text, task_id)
        myridtv_task_state.persist_tasks_locked()
    _agent_task_log("AgentTask", "task={} workflow={} step={} status={}".format(
        task.get("task_id"), task.get("workflow_type"), task.get("current_step_id"), task.get("status")))
    return task


def _agent_save_tasks():
    with TASKS_LOCK:
        return myridtv_task_state.persist_tasks_locked()


def _agent_attach_runtime_result(result, task, turn=None, validation=None):
    if not isinstance(result, dict):
        result = {"text": str(result or "")}
    task_payload = agent_runtime.serialize_task(task)
    step_payload = agent_runtime.serialize_step(task)
    progress = (task or {}).get("progress") if isinstance(task, dict) else {}
    result["task"] = task_payload
    result["step"] = step_payload
    result["progress"] = progress
    if validation is not None:
        result["workflow_validation"] = validation
    agent_result = result.get("agent_result")
    if isinstance(agent_result, dict):
        agent_result["task"] = task_payload
        agent_result["step"] = step_payload
        agent_result["progress"] = progress
        if validation is not None:
            agent_result["workflow_validation"] = validation
    return result


