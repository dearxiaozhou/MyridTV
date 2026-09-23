# -*- coding: utf-8 -*-
"""MyridTV RunningHub 平台域·上（后端拆分第8刀）：任务查询（legacy/v2/query_task）、
进度与 wss 抽取、任务控制台注册与状态同步、workflow/app 提交、workflow 配置缓存
（缓存文件/字段推断/标题/默认字段/拉取/保存）。

逐字迁移自 rh_official_proxy.py 连续块 L(runninghub_query_legacy)..L(handle_legacy_generate)
（17 函数 445 行，可逆还原行级 diff=0）。行为零变更。
已拆模块直引：myridtv_http（重试底座）、myridtv_provider（平台配置读写）、
myridtv_task_state（任务账本读写 API）。configure() 注入：TASKS/TASKS_LOCK 同对象
（与主文件/task_state 三方同一对象，块内只读遍历）、LOG_FILE getter、
3 个 RH helper 闭包（runninghub_api_url/runninghub_task_key/runninghub_task_auth_headers，
仍留主文件）。主文件对块外仍调用的 11 函数留同名薄代理，调用点不改。
"""
import json
import re
import time
import uuid

import myridtv_http
import myridtv_provider
import myridtv_task_state
from myridtv_core import ApiError, append_log

_TASKS = {}
_TASKS_LOCK = None
_log_file = lambda: None
_r_runninghub_api_url = None
_r_runninghub_task_key = None
_r_runninghub_task_auth_headers = None


def configure(tasks, tasks_lock, log_file_getter,
              runninghub_api_url, runninghub_task_key, runninghub_task_auth_headers):
    global _TASKS, _TASKS_LOCK, _log_file
    global _r_runninghub_api_url, _r_runninghub_task_key, _r_runninghub_task_auth_headers
    _TASKS = tasks
    _TASKS_LOCK = tasks_lock
    _log_file = log_file_getter
    _r_runninghub_api_url = runninghub_api_url
    _r_runninghub_task_key = runninghub_task_key
    _r_runninghub_task_auth_headers = runninghub_task_auth_headers


def runninghub_query_legacy(task_id):
    key = _r_runninghub_task_key()
    status_data = myridtv_http._rh_request_with_retry(
        _r_runninghub_api_url("/task/openapi/status"),
        "POST",
        {"apiKey": key, "taskId": task_id},
        timeout=60,
    )
    if isinstance(status_data, dict) and status_data.get("code") not in (None, 0, "0") and not status_data.get("data"):
        message = status_data.get("msg") or status_data.get("message") or status_data.get("errorMessage") or "RunningHub 查询失败"
        return {"status": "FAILED", "failReason": message, "raw": status_data}
    info = status_data.get("data") if isinstance(status_data.get("data"), dict) else status_data
    status = str(info.get("status") or info.get("taskStatus") or "").upper()
    result = {"status": status or "RUNNING", "raw": status_data}
    progress = _extract_rh_progress(result.get("raw"))
    if progress is not None:
        result["progress"] = progress
    wss_url = _extract_rh_wss(result.get("raw"))
    if wss_url:
        result["wss_url"] = wss_url
    if result["status"] == "SUCCESS":
        output_data = myridtv_http._rh_request_with_retry(
            _r_runninghub_api_url("/task/openapi/outputs"),
            "POST",
            {"apiKey": key, "taskId": task_id},
            timeout=60,
        )
        output_info = output_data.get("data") if isinstance(output_data.get("data"), dict) else output_data
        urls = output_info.get("urls") or output_info.get("images") or []
        if not urls:
            outputs = output_info.get("outputs") or output_info.get("results") or []
            urls = [
                item.get("fileUrl") or item.get("url") or item.get("downloadUrl")
                for item in outputs
                if isinstance(item, dict)
            ]
        result["urls"] = [url for url in urls if isinstance(url, str) and url.strip()]
        result["raw"] = {"status": status_data, "outputs": output_data}
    elif result["status"] == "FAILED":
        result["failReason"] = info.get("failReason") or info.get("message") or ""
    return result


def runninghub_query_v2(task_id):
    data = myridtv_http._rh_request_with_retry(
        _r_runninghub_api_url("/openapi/v2/query"),
        "POST",
        {"taskId": task_id},
        headers=_r_runninghub_task_auth_headers(),
        timeout=60,
    )
    if isinstance(data, dict) and str(data.get("errorCode") or "").strip():
        message = data.get("errorMessage") or data.get("message") or "RunningHub 查询失败"
        return {"status": "FAILED", "urls": [], "failReason": message, "raw": data}
    info = data.get("data") if isinstance(data.get("data"), dict) else data
    status = str(info.get("status") or info.get("taskStatus") or "").upper()
    urls = info.get("urls") or []
    if not urls:
        results = info.get("results") or info.get("outputs") or []
        urls = [
            item.get("url") or item.get("fileUrl") or item.get("downloadUrl")
            for item in results
            if isinstance(item, dict)
        ]
    result = {"status": status or "RUNNING", "urls": [url for url in urls if isinstance(url, str) and url.strip()], "raw": data}
    progress = _extract_rh_progress(result.get("raw"))
    if progress is not None:
        result["progress"] = progress
    wss_url = _extract_rh_wss(result.get("raw"))
    if wss_url:
        result["wss_url"] = wss_url
    if result["status"] == "FAILED":
        result["failReason"] = info.get("failReason") or info.get("message") or ""
    return result


def _extract_rh_progress(raw):
    """从 RunningHub query 原始返回中提取进度百分比（0-100）。

    RH 官方 query 不保证返回进度字段；若返回里存在 progress/percent 等字段则透传，
    否则返回 None（调用方回退到 indeterminate 流光，不改变现有行为）。
    """
    if not isinstance(raw, dict):
        return None
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    for key in ("progress", "percent", "progressValue", "progress_percent"):
        val = data.get(key)
        if val is None:
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        if val < 0 or val > 100:
            continue
        return val
    return None


def _extract_rh_wss(raw):
    """从 RunningHub query 原始返回中提取实时进度 WSS 链接。

    官方进度示例（doc-8287471）在任务 RUNNING 态轮询返回 netWssUrl，连上后
    收 {"type":"progress","node":..,"value":..,"max":..} 实时消息。工作流任务
    若返回该字段则透传，否则返回 None（不改变现有轮询行为）。
    """
    if not isinstance(raw, dict):
        return None
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    for key in ("netWssUrl", "wssUrl", "wss_url", "progressWssUrl"):
        val = data.get(key)
        if isinstance(val, str) and val.startswith("wss://"):
            return val
    return None


def runninghub_query_task(task_id):
    errors = []
    for helper in (runninghub_query_v2, runninghub_query_legacy):
        try:
            result = helper(task_id)
            if result.get("status"):
                return result
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError(errors[-1] if errors else "RunningHub 查询失败")


def _rh_sync_task_console_state(rh_task_id, queried):
    """把 RH 轮询结果回写任务控制台（running->succeeded/failed）。"""
    if not rh_task_id or not isinstance(queried, dict):
        return
    try:
        status = str(queried.get("status") or "").upper()
        if status not in ("SUCCESS", "FAILED", "RUNNING"):
            return
        with _TASKS_LOCK:
            local_id = None
            for tid, st in _TASKS.items():
                if isinstance(st, dict) and str(st.get("rh_task_id") or "") == str(rh_task_id):
                    local_id = tid
                    break
        if not local_id:
            return
        if status == "SUCCESS":
            urls = queried.get("urls") or []
            myridtv_task_state.update_task_state(local_id, status="succeeded", result={"images": [{"url": u} for u in urls]},
                              completed_at=time.time(), checked_at=time.time(), raw_status="SUCCESS")
        elif status == "FAILED":
            myridtv_task_state.update_task_state(local_id, status="failed", error=queried.get("failReason") or "RunningHub 任务失败",
                              completed_at=time.time(), checked_at=time.time(), raw_status="FAILED")
        else:
            myridtv_task_state.update_task_state(local_id, status="running", checked_at=time.time(), raw_status="RUNNING")
    except Exception as exc:
        append_log(_log_file(), f"rh task console sync failed: {exc}")


def _rh_task_console_register(rh_task_id, payload, data, backend, mode):
    """RunningHub 提交成功后注册到任务控制台（running 态，持久化）。

    智能画布走 /api/runninghub/submit 与 /api/runninghub/workflow-submit 是透传
    （此前不写 TASKS，控制台永远只显示旧画布/Agent 的任务）。这里补注册，让
    新任务从提交起就出现在控制台，随后由 /api/runninghub/query 轮询回写状态。
    """
    try:
        local_id = "rhproxy_" + uuid.uuid4().hex
        # 元数据优先取 payload 显式字段；前端未传时从 nodeInfoList 兜底解析模型
        model = str(payload.get("model") or "").strip()
        if not model:
            for item in (payload.get("nodeInfoList") or []):
                if not isinstance(item, dict):
                    continue
                fv = str(item.get("fieldValue") or "").strip()
                if fv and ("/" in fv) and not fv.startswith("http"):
                    model = fv
                    break
        myridtv_task_state.set_task_state(local_id, {
            "status": "running",
            "persistent": True,
            "backend": backend,
            "created_at": time.time(),
            "canvas_title": str(payload.get("canvas_title") or ""),
            "canvas_id": str(payload.get("canvas_id") or ""),
            "model": model,
            "provider_id": "runninghub",
            "mode": mode,
            "node_id": str(payload.get("node_id") or ""),
            "node_title": str(payload.get("node_title") or ""),
            "rh_task_id": str(rh_task_id or ""),
            "submit": data,
            "checked_at": time.time(),
            "raw_status": "QUEUED",
        })
    except Exception as exc:
        append_log(_log_file(), f"rh task console register failed: {exc}")


def runninghub_submit_workflow(payload):
    key = _r_runninghub_task_key()
    body = dict(payload or {})
    body["apiKey"] = key
    # RH 的 /task/openapi/create 只接受 workflow 为 JSON 字符串（官方文档：Custom full workflow in
    # JSON string format）。传对象会返回 {"code":404,"msg":"NOT_FOUND"}（2026-09-16 实测复现），
    # 这里兜底转换，避免任何前端版本漏转。
    if isinstance(body.get("workflow"), (dict, list)):
        body["workflow"] = json.dumps(body["workflow"], ensure_ascii=False)
    data = myridtv_http._rh_request_with_retry(_r_runninghub_api_url("/task/openapi/create"), "POST", body, timeout=120)
    task_id = data.get("taskId") or (data.get("data") or {}).get("taskId") or ""
    if not task_id:
        raise RuntimeError(f"RunningHub 工作流提交失败：{data}")
    _rh_task_console_register(task_id, payload, data, "runninghub-workflow", "workflow")
    return {"taskId": task_id, "raw": data}


def runninghub_submit_app(payload):
    key = _r_runninghub_task_key()
    body = dict(payload or {})
    body["apiKey"] = key
    data = myridtv_http._rh_request_with_retry(_r_runninghub_api_url("/task/openapi/ai-app/run"), "POST", body, timeout=120)
    task_id = data.get("taskId") or (data.get("data") or {}).get("taskId") or ""
    if not task_id:
        raise RuntimeError(f"RunningHub AI 应用提交失败：{data}")
    _rh_task_console_register(task_id, payload, data, "runninghub-official", "i2i")
    return {"taskId": task_id, "raw": data}


def runninghub_cached_workflow(workflow_id):
    target_id = str(workflow_id or "").strip()
    if not target_id:
        return None
    for provider in myridtv_provider.read_api_providers():
        if not isinstance(provider, dict):
            continue
        for item in provider.get("rh_workflows") or []:
            if isinstance(item, dict) and str(item.get("id") or "").strip() == target_id:
                return item
    return None


def runninghub_cached_app_info(app_id):
    target_id = str(app_id or "").strip()
    if not target_id:
        return None
    for provider in myridtv_provider.read_api_providers():
        if not isinstance(provider, dict):
            continue
        for item in provider.get("rh_apps") or []:
            if isinstance(item, dict) and str(item.get("id") or item.get("appId") or "").strip() == target_id:
                return item
    return None


def runninghub_infer_workflow_field_type(name, value):
    key = str(name or "").strip().lower()
    text = str(value if value is not None else "").strip().lower()
    sample = key + " " + text
    if re.search(r"image|img|mask|photo|picture|png|jpe?g|webp", sample):
        return "IMAGE"
    if re.search(r"video|mp4|webm|mov", sample):
        return "VIDEO"
    if re.search(r"audio|wav|mp3|voice|sound", sample):
        return "AUDIO"
    if isinstance(value, bool) or text in {"true", "false"}:
        return "BOOLEAN"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "NUMBER"
    if text and re.fullmatch(r"-?\d+(\.\d+)?", text):
        return "NUMBER"
    return "TEXT"


def runninghub_workflow_title(workflow_json, workflow_id, fallback_title=""):
    for node in (workflow_json if isinstance(workflow_json, dict) else {}).values():
        if not isinstance(node, dict):
            continue
        title = str(((node.get("_meta") or {}).get("title")) or node.get("class_type") or "").strip()
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        if title and not re.search(r"save|preview|output", title, re.I) and inputs.get("text"):
            return str(fallback_title or title).strip()
    return str(fallback_title or f"工作流 {str(workflow_id)[-6:]}").strip()


def runninghub_fields_from_workflow_json(workflow_json):
    fields = []
    for node_id, node in (workflow_json if isinstance(workflow_json, dict) else {}).items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        if not inputs:
            continue
        title = str(((node.get("_meta") or {}).get("title")) or node.get("class_type") or f"Node {node_id}").strip()
        for field_name, value in inputs.items():
            if isinstance(value, list):
                continue
            if isinstance(value, dict) and "__value__" not in value:
                continue
            field_value = value.get("__value__") if isinstance(value, dict) else value
            field_type = runninghub_infer_workflow_field_type(field_name, field_value)
            field = {
                "id": f"{node_id}::{field_name}",
                "nodeId": str(node_id),
                "fieldName": str(field_name),
                "fieldValue": "" if field_value is None else field_value,
                "fieldType": field_type,
                "label": str(field_name),
                "enabled": False,
                "group": title,
                "note": f"{title} / {field_name}",
            }
            key = str(field_name).lower()
            if field_type == "NUMBER" and ("seed" in key or "noise" in key):
                field["random_enabled"] = True
                field["min"] = 1
                field["max"] = 1000000000000000
                field["step"] = 1
            fields.append(field)
    return fields


def runninghub_default_workflow_fields(workflow_id):
    return [
        {
            "id": "rh-default::prompt",
            "nodeId": "prompt",
            "fieldName": "text",
            "fieldValue": "",
            "fieldType": "TEXT",
            "label": "提示词",
            "enabled": True,
            "sourceFromUpstream": True,
            "group": "基础参数",
            "note": "未能读取 workflow JSON 时的可编辑兜底字段，请按 RunningHub 页面参数手动调整 nodeId/fieldName。",
        },
        {
            "id": "rh-default::seed",
            "nodeId": "seed",
            "fieldName": "seed",
            "fieldValue": "",
            "fieldType": "NUMBER",
            "label": "随机种子",
            "enabled": False,
            "random_enabled": True,
            "min": 1,
            "max": 1000000000000000,
            "step": 1,
            "group": "基础参数",
            "note": f"工作流 {workflow_id} 的兜底随机数参数。",
        },
    ]


def runninghub_fetch_workflow_config(payload):
    workflow_id = str((payload or {}).get("workflowId") or "").strip()
    if not workflow_id:
        raise ApiError(400, "缺少 workflowId")
    title = str((payload or {}).get("title") or f"工作流 {workflow_id[-6:]}").strip()
    description = str((payload or {}).get("description") or "").strip()
    raw = {}
    workflow_json = {}
    fields = []
    source = "fallback"
    fetch_error = ""
    try:
        key = _r_runninghub_task_key()
        raw = myridtv_http._rh_request_with_retry(
            _r_runninghub_api_url("/api/openapi/getJsonApiFormat"),
            "POST",
            {"apiKey": key, "workflowId": workflow_id},
            headers={"Authorization": f"Bearer {key}"},
            timeout=120,
        )
        prompt = ((raw.get("data") or {}).get("prompt") if isinstance(raw.get("data"), dict) else None) or raw.get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            workflow_json = json.loads(prompt)
        elif isinstance(prompt, dict):
            workflow_json = prompt
        if isinstance(workflow_json, dict) and workflow_json:
            fields = runninghub_fields_from_workflow_json(workflow_json)
            source = "runninghub-getJsonApiFormat"
    except Exception as exc:
        fetch_error = str(exc)
    if not fields:
        fields = runninghub_default_workflow_fields(workflow_id)
        if fetch_error:
            description = (description + "\n" if description else "") + f"自动拉取 workflow JSON 失败：{fetch_error}"
    return {
        "workflowId": workflow_id,
        "title": runninghub_workflow_title(workflow_json, workflow_id, title),
        "description": description,
        "fields": fields,
        "workflowJson": workflow_json if isinstance(workflow_json, dict) else {},
        "optionalImageMode": "prune-workflow",
        "raw": {"source": source, "fetch_error": fetch_error, "response": raw},
        "updatedAt": int(time.time() * 1000),
    }


def save_runninghub_workflow_config(workflow_id, payload):
    target_id = str(workflow_id or (payload or {}).get("workflowId") or "").strip()
    if not target_id:
        raise ApiError(400, "缺少 workflowId")
    providers = myridtv_provider.read_api_providers()
    runninghub = next((item for item in providers if isinstance(item, dict) and str(item.get("id") or "") == "runninghub"), None)
    if not runninghub:
        runninghub = {
            "id": "runninghub",
            "name": "RunningHub",
            "base_url": "https://www.runninghub.ai",
            "protocol": "runninghub",
            "enabled": True,
            "image_models": [],
            "chat_models": [],
            "video_models": [],
            "rh_apps": [],
            "rh_workflows": [],
        }
        providers.append(runninghub)
    workflows = runninghub.get("rh_workflows") if isinstance(runninghub.get("rh_workflows"), list) else []
    runninghub["rh_workflows"] = workflows
    existing = next((item for item in workflows if isinstance(item, dict) and str(item.get("id") or item.get("workflowId") or "") == target_id), None)
    if not existing:
        existing = {"id": target_id, "workflowId": target_id, "enabled": True}
        workflows.insert(0, existing)
    safe = payload if isinstance(payload, dict) else {}
    existing.update({
        "id": target_id,
        "workflowId": target_id,
        "title": str(safe.get("title") or existing.get("title") or f"工作流 {target_id[-6:]}").strip(),
        "note": str(safe.get("description") or safe.get("note") or existing.get("note") or "").strip(),
        "fields": safe.get("fields") if isinstance(safe.get("fields"), list) else existing.get("fields", []),
        "workflowJson": safe.get("workflowJson") if isinstance(safe.get("workflowJson"), dict) else existing.get("workflowJson", {}),
        "optionalImageMode": str(safe.get("optionalImageMode") or existing.get("optionalImageMode") or "prune-workflow"),
        "raw": safe.get("raw") if isinstance(safe.get("raw"), dict) else existing.get("raw", {}),
        "updatedAt": int(time.time() * 1000),
        "enabled": safe.get("enabled") is not False,
    })
    saved = myridtv_provider.write_api_providers(providers)
    for provider in saved:
        if isinstance(provider, dict) and str(provider.get("id") or "") == "runninghub":
            for item in provider.get("rh_workflows") or []:
                if isinstance(item, dict) and str(item.get("id") or item.get("workflowId") or "") == target_id:
                    return item
    return existing


