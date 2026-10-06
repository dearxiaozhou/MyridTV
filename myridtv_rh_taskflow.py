# -*- coding: utf-8 -*-
"""RH 任务执行域（后端拆分第30刀自 rh_official_proxy.py 逐字外移）：
官方生图任务提交/轮询、画布任务结果本地化（含后台本地化）、
火山 Agent 任务、Blender 预演执行、run_task 主循环、本地化路由入口。
LOG_FILE 走 getter（write_app_config 重绑）；主留函数 closure 延迟解析。"""
import re
import json
import time
import threading
import myridtv_agent_state
import myridtv_blender_previz
import myridtv_core
import myridtv_env
import myridtv_http
import myridtv_comfy
import myridtv_media_localize
import myridtv_provider
import myridtv_provider_image
import myridtv_runninghub
import myridtv_runninghub_build
import myridtv_task_console
import myridtv_task_state
import myridtv_volcengine

_G_LOG_FILE = lambda: None
_r_runninghub_api_base = lambda *a, **k: None
_G_POLL_TIMEOUT = lambda: 1800

def configure(log_file_getter, closures, poll_timeout_getter):
    global _G_LOG_FILE, _G_POLL_TIMEOUT
    _G_LOG_FILE = log_file_getter
    _G_POLL_TIMEOUT = poll_timeout_getter
    global _r_runninghub_api_base
    _r_runninghub_api_base = closures['runninghub_api_base']


def submit_official(payload):
    refs = payload.get("reference_images") or []
    provider_id = str(payload.get("provider_id") or "runninghub").strip()
    if myridtv_provider_image.resolve_generic_image_provider(provider_id):
        # 通用 OpenAI 兼容平台：按平台自身 base_url + 平台 Key 出图，不碰 RunningHub
        model = myridtv_agent_state._agent_select_configured_image_model(provider_id, payload.get("model"), refs)
        task_id, data = myridtv_provider_image.submit_generic_image(
            provider_id, model, payload.get("prompt") or "", refs, payload)
        return task_id, data
    key = myridtv_env.read_env_balance_key()
    if not key:
        raise RuntimeError("未找到 RunningHub API Key，请在 API 设置填写「账户余额 API Key」（标准模型需企业级 Key）")
    model = myridtv_agent_state._agent_select_configured_image_model(provider_id, payload.get("model"), refs)
    endpoint = f"{_r_runninghub_api_base()}/openapi/v2/{model}"
    body = myridtv_runninghub_build.build_official_body(payload, model, refs)
    data = myridtv_http._rh_request_with_retry(endpoint, "POST", body, {"Authorization": f"Bearer {key}"}, timeout=120)
    task_id = data.get("taskId") or ""
    if not task_id:
        if str(data.get("errorCode") or "") == "1014":
            raise RuntimeError(
                "标准模型 API 需要企业级 Key：请在 API 设置把企业级 Key 填入「账户余额 API Key」"
                f"（当前错误：{str(data.get('errorMessage') or '')[:80]}）")
        raise RuntimeError(f"RunningHub 未返回 taskId：{data}")
    return task_id, data


def submit_and_poll_official(payload):
    """同步出图路由（online-image 等）：按平台分叉轮询链。"""
    provider_id = str((payload or {}).get("provider_id") or "").strip()
    task_id, submit_raw = submit_official(payload)
    if myridtv_provider_image.resolve_generic_image_provider(provider_id):
        if isinstance(submit_raw, dict) and submit_raw.get("inline_images"):
            return {"images": list(submit_raw["inline_images"]), "task_id": task_id, "backend": "provider-openai", "raw": submit_raw.get("raw") or submit_raw}
        return myridtv_provider_image.poll_generic_result(provider_id, task_id)
    return poll_result(task_id)


def poll_result(task_id):
    deadline = time.time() + _G_POLL_TIMEOUT()
    last = ""
    while time.time() < deadline:
        if myridtv_task_console._task_console_is_cancelled(task_id):
            raise myridtv_task_console._TaskConsoleCancelled()
        try:
            info = myridtv_runninghub.runninghub_query_task(task_id)
        except Exception as exc:
            last = str(exc)
            time.sleep(5)
            continue
        last = json.dumps(info, ensure_ascii=False)
        status = str(info.get("status") or "").upper()
        if status == "SUCCESS":
            urls = info.get("urls") or []
            if not urls:
                raise RuntimeError(f"RunningHub 成功但没有返回图片：{info}")
            return {
                "images": urls,
                "task_id": task_id,
                "backend": "runninghub-official-proxy",
                "raw": info.get("raw") or info,
            }
        if status == "FAILED":
            raise RuntimeError(info.get("failReason") or json.dumps(info, ensure_ascii=False))
        time.sleep(3)
    raise RuntimeError(f"RunningHub 查询超时：{last}")


def localize_canvas_task_result(result, payload):
    if not isinstance(result, dict):
        return result
    canvas_title = str((payload or {}).get("canvas_title") or "").strip()
    canvas_id = str((payload or {}).get("canvas_id") or "").strip()
    node_title = str((payload or {}).get("node_title") or "").strip()
    localized = dict(result)
    try:
        if localized.get("images"):
            localized["images"] = myridtv_media_localize.localize_generated_media_items(localized.get("images") or [], "image", canvas_title, canvas_id, node_title)
        if localized.get("videos"):
            localized["videos"] = myridtv_media_localize.localize_generated_media_items(localized.get("videos") or [], "video", canvas_title, canvas_id, node_title)
        if localized.get("audios"):
            localized["audios"] = myridtv_media_localize.localize_generated_media_items(localized.get("audios") or [], "audio", canvas_title, canvas_id, node_title)
    except Exception as exc:
        localized["localize_error"] = str(exc)
        myridtv_core.append_log(_G_LOG_FILE(), f"canvas task localize failed task={localized.get('task_id')}: {exc}")
    return localized


def localize_canvas_task_result_background(task_id, result, payload):
    try:
        localized = localize_canvas_task_result(result, payload)
        if isinstance(localized, dict) and localized != result:
            current = myridtv_task_state.get_task_state(task_id)
            if current and current.get("status") == "succeeded":
                myridtv_task_state.update_task_state(task_id, result=localized, localized_at=time.time())
                myridtv_core.append_log(_G_LOG_FILE(), f"canvas task localized in background task={task_id}")
    except Exception as exc:
        myridtv_core.append_log(_G_LOG_FILE(), f"canvas task background localize failed task={task_id}: {exc}")


def submit_volcengine_agent_task(payload):
    return myridtv_volcengine.submit_volcengine_agent_task(payload)

def poll_volcengine_agent_task(local_task_id):
    return myridtv_volcengine.poll_volcengine_agent_task(local_task_id)

def _previz_ratio_size(aspect_ratio):
    text = str(aspect_ratio or "").strip().lower().replace(" ", "")
    mapping = {
        "16:9": (1280, 720), "wide": (1280, 720),
        "9:16": (720, 1280), "story": (720, 1280),
        "1:1": (720, 720), "square": (720, 720),
        "3:2": (1080, 720), "landscape": (1080, 720),
        "2:3": (720, 1080), "portrait": (720, 1080),
        "4:3": (960, 720), "landscape43": (960, 720),
        "3:4": (720, 960), "portrait43": (720, 960),
        "21:9": (1680, 720), "ultrawide": (1680, 720),
        "9:21": (720, 1680), "ultratall": (720, 1680),
    }
    return mapping.get(text, (1280, 720))


def _strip_llm_fenced_text(text):
    text = str(text or "").strip()
    fence = re.match(r"^```(?:\w+)?\s*([\s\S]*?)\s*```$", text)
    if fence:
        text = fence.group(1).strip()
    return text.strip()


def run_blender_previz(payload):
    return myridtv_blender_previz.run_blender_previz(payload)


def run_task(task_id, payload):
    try:
        provider_id = str((payload or {}).get("provider_id") or "").strip()
        if provider_id == "blender":
            myridtv_task_state.update_task_state(task_id, status="running", backend="blender-previz", provider_id="blender", checked_at=time.time())
            result = run_blender_previz(payload)
            myridtv_task_state.update_task_state(task_id, status="succeeded", result=result, completed_at=time.time(), localized_at=time.time())
            return
        if provider_id == "volcengine":
            provider_task_id, submit_raw = submit_volcengine_agent_task(payload)
            myridtv_task_state.update_task_state(task_id, status="running", provider_task_id=provider_task_id, submit=submit_raw, checked_at=time.time(), backend="volcengine-ark", provider_id="volcengine")
            threading.Thread(target=poll_volcengine_agent_task, args=(task_id,), daemon=True).start()
            return
        if provider_id == "runninghub":
            workflow_name = str((payload or {}).get("model") or "").strip()
            entry = None
            for provider in myridtv_provider.read_api_providers():
                if str(provider.get("id") or "") != "runninghub":
                    continue
                for item in provider.get("rh_workflows") or []:
                    if isinstance(item, dict) and str(item.get("title") or item.get("name") or "") == workflow_name:
                        entry = item
                        break
                if entry:
                    break
            if entry:
                workflow_id = str(entry.get("workflowId") or entry.get("id") or "").strip()
                if not workflow_id:
                    raise RuntimeError("RunningHub 云端工作流缺少 workflowId")
                submit = myridtv_runninghub.runninghub_submit_workflow({"workflowId": workflow_id, "nodeInfoList": []})
                rh_task_id = str(submit.get("taskId") or "").strip()
                if not rh_task_id:
                    raise RuntimeError("RunningHub 云端工作流提交失败")
                myridtv_task_state.update_task_state(task_id, status="running", rh_task_id=rh_task_id, submit=submit.get("raw") or submit, checked_at=time.time())
                result = poll_result(rh_task_id)
                current = myridtv_task_state.get_task_state(task_id)
                if current.get("status") == "succeeded" and current.get("localized_at"):
                    return
                result = localize_canvas_task_result(result, payload)
                myridtv_task_state.update_task_state(task_id, status="succeeded", result=result, completed_at=time.time(), localized_at=time.time())
                return
        is_generic = bool(myridtv_provider_image.resolve_generic_image_provider(provider_id))
        rh_task_id, submit_raw = submit_official(payload)
        myridtv_task_state.update_task_state(
            task_id, status="running", rh_task_id=rh_task_id, submit=submit_raw, checked_at=time.time(),
            backend=("provider-openai" if is_generic else "runninghub-official"), provider_id=provider_id)
        if is_generic:
            if isinstance(submit_raw, dict) and submit_raw.get("inline_images"):
                result = {"images": list(submit_raw["inline_images"]), "task_id": rh_task_id, "backend": "provider-openai", "raw": submit_raw.get("raw") or submit_raw}
            else:
                result = myridtv_provider_image.poll_generic_result(provider_id, rh_task_id, local_task_id=task_id)
        else:
            result = poll_result(rh_task_id)
        # 用户已点停止：轮询窗口尾部竞态下不得把 cancelled 覆盖回 succeeded
        if myridtv_task_console._task_console_is_cancelled(task_id):
            myridtv_core.append_log(_G_LOG_FILE(), f"[ProviderImage] discard late result (cancelled) task={task_id} provider={provider_id}")
            return
        # If refresh_canvas_task_state already localized the result (race condition), skip.
        with myridtv_media_localize._canvas_task_localize_lock(task_id):
            if myridtv_media_localize._canvas_task_already_localized(task_id):
                myridtv_core.append_log(_G_LOG_FILE(), f"run_task skip localize, already done by refresh task={task_id}")
                return
            # Localize before publishing success so the frontend never localizes the same remote files again.
            result = localize_canvas_task_result(result, payload)
            myridtv_task_state.update_task_state(task_id, status="succeeded", result=result, completed_at=time.time(), localized_at=time.time())
        if is_generic:
            myridtv_core.append_log(_G_LOG_FILE(), f"[ProviderImage] canvas task done task={task_id} provider={provider_id} model={payload.get('model')}")
    except Exception as exc:
        if myridtv_task_console._task_console_is_cancelled(task_id):
            # 控制台手动停止：保持 cancelled 状态，不被轮询异常覆盖
            myridtv_core.append_log(_G_LOG_FILE(), "[CanvasTaskCancelled] task={} provider={} model={}".format(task_id, (payload or {}).get("provider_id"), (payload or {}).get("model")))
            return
        error = str(exc)
        myridtv_core.append_log(_G_LOG_FILE(), "[CanvasTaskFailed] task={} provider={} model={} err={}".format(task_id, (payload or {}).get("provider_id"), (payload or {}).get("model"), error[:400]))
        if "查询超时" in error:
            myridtv_task_state.update_task_state(task_id, status="running", checked_at=time.time(), last_error=error, poll_window_expired_at=time.time())
        else:
            myridtv_task_state.update_task_state(task_id, status="failed", error=error, completed_at=time.time())


def handle_localize_generated_media(payload):
    safe_payload = payload if isinstance(payload, dict) else {}
    raw_items = safe_payload.get("items")
    if not isinstance(raw_items, list):
        raw_items = safe_payload.get("images")
    if not isinstance(raw_items, list):
        raw_items = []
    kind = str(safe_payload.get("kind") or "image")
    canvas_title = str(safe_payload.get("canvas_title") or "").strip()
    canvas_id = str(safe_payload.get("canvas_id") or "").strip()
    try:
        node_title = str(safe_payload.get("node_title") or "").strip()
        items = myridtv_media_localize.localize_generated_media_items(raw_items, kind, canvas_title, canvas_id, node_title)
        return {
            "ok": True,
            "items": items,
        }
    except Exception as exc:
        myridtv_core.append_log(_G_LOG_FILE(), f"localize generated media route fallback: {exc}")
        return {
            "ok": True,
            "items": [myridtv_media_localize.fallback_generated_media_item(item, kind, exc) for item in raw_items],
            "localize_error": str(exc),
            "fallback": True,
        }

def refresh_canvas_task_state(task_id):
    state = myridtv_task_state.get_task_state(task_id)
    if not state:
        return {"status": "failed", "error": "任务不存在"}
    if state.get("backend") == "volcengine-ark" and state.get("status") == "running" and (state.get("provider_task_id") or state.get("volcengine_task_id")):
        provider_task_id = state.get("provider_task_id") or state.get("volcengine_task_id")
        try:
            queried = myridtv_volcengine.query_volcengine_video_task(state.get("provider_id") or "volcengine", provider_task_id, localize=True, canvas_title=str(state.get("canvas_title") or ""), canvas_id=str(state.get("canvas_id") or ""))
            if queried.get("status") == "succeeded":
                state = myridtv_task_state.update_task_state(task_id, status="succeeded", result=queried.get("result") or {}, completed_at=time.time(), raw_status=queried.get("raw_status") or "")
            elif queried.get("status") == "failed":
                state = myridtv_task_state.update_task_state(task_id, status="failed", error=queried.get("error") or "火山视频任务失败", completed_at=time.time(), raw=queried.get("raw"), raw_status=queried.get("raw_status") or "")
            else:
                state = myridtv_task_state.update_task_state(task_id, status="running", checked_at=time.time(), raw_status=queried.get("raw_status") or "running")
        except Exception as exc:
            state = myridtv_task_state.update_task_state(task_id, status="running", checked_at=time.time(), last_error=str(exc))
    if state.get("backend") == "provider-openai" and state.get("status") == "running" and state.get("rh_task_id"):
        if myridtv_task_console._task_console_is_cancelled(task_id):
            return state
        try:
            queried = myridtv_provider_image.query_generic_image(str(state.get("provider_id") or ""), state["rh_task_id"])
            raw_status = str(queried.get("status") or "").upper().replace("-", "_")
            urls = queried.get("urls") or []
            if raw_status in myridtv_provider_image._SUCCESS_STATUSES and not urls:
                status = "RUNNING"
            elif raw_status in myridtv_provider_image._SUCCESS_STATUSES:
                status = "SUCCESS"
            elif raw_status in myridtv_provider_image._FAILURE_STATUSES:
                status = "FAILED"
            else:
                status = raw_status or "RUNNING"
            if status == "SUCCESS":
                if urls:
                    with myridtv_media_localize._canvas_task_localize_lock(task_id):
                        if not myridtv_media_localize._canvas_task_already_localized(task_id):
                            raw_result = {
                                "images": list(urls),
                                "task_id": state["rh_task_id"],
                                "backend": "provider-openai",
                                "raw": queried.get("raw") or queried,
                            }
                            localized_result = localize_canvas_task_result(raw_result, {
                                "canvas_title": str(state.get("canvas_title") or "").strip(),
                                "canvas_id": str(state.get("canvas_id") or "").strip(),
                                "node_title": str(state.get("node_title") or "").strip(),
                            })
                            state = myridtv_task_state.update_task_state(task_id, status="succeeded", result=localized_result, completed_at=time.time(), raw_status=raw_status, localized_at=time.time())
                else:
                    state = myridtv_task_state.update_task_state(task_id, status="running", checked_at=time.time(), last_error="生图平台已完成但结果尚未返回", raw_status=status)
            elif status == "FAILED":
                state = myridtv_task_state.update_task_state(task_id, status="failed", error=queried.get("failReason") or "生图平台任务失败", completed_at=time.time(), raw=queried.get("raw"), raw_status=raw_status)
            else:
                state = myridtv_task_state.update_task_state(task_id, status="running", checked_at=time.time(), raw_status=status or "RUNNING")
        except Exception as exc:
            state = myridtv_task_state.update_task_state(task_id, status="running", checked_at=time.time(), last_error=str(exc))
    if state.get("backend") == "runninghub-official" and state.get("status") == "running" and state.get("rh_task_id"):
        try:
            queried = myridtv_runninghub.runninghub_query_task(state["rh_task_id"])
            status = str(queried.get("status") or "").upper()
            if status == "SUCCESS":
                urls = queried.get("urls") or []
                if urls:
                    with myridtv_media_localize._canvas_task_localize_lock(task_id):
                        if myridtv_media_localize._canvas_task_already_localized(task_id):
                            state = myridtv_task_state.get_task_state(task_id) or state
                        else:
                            raw_result = {
                                "images": urls,
                                "task_id": state["rh_task_id"],
                                "backend": "runninghub-official-proxy",
                                "raw": queried.get("raw") or queried,
                            }
                            # Localize before publishing success so the frontend never sees remote URLs.
                            localized_result = localize_canvas_task_result(raw_result, {
                                "canvas_title": str(state.get("canvas_title") or "").strip(),
                                "canvas_id": str(state.get("canvas_id") or "").strip(),
                                "node_title": str(state.get("node_title") or "").strip(),
                            })
                            state = myridtv_task_state.update_task_state(task_id, status="succeeded", result=localized_result, completed_at=time.time(), raw_status=status, localized_at=time.time())
                else:
                    state = myridtv_task_state.update_task_state(task_id, status="running", checked_at=time.time(), last_error="RunningHub 已完成但结果尚未返回", raw_status=status)
            elif status == "FAILED":
                state = myridtv_task_state.update_task_state(task_id, status="failed", error=queried.get("failReason") or "RunningHub 任务失败", completed_at=time.time(), raw=queried.get("raw"), raw_status=status)
            else:
                progress = queried.get("progress")
                if progress is not None:
                    state = myridtv_task_state.update_task_state(task_id, status="running", checked_at=time.time(), raw_status=status or "RUNNING", progress=progress)
                else:
                    state = myridtv_task_state.update_task_state(task_id, status="running", checked_at=time.time(), raw_status=status or "RUNNING")
        except Exception as exc:
            state = myridtv_task_state.update_task_state(task_id, status="running", checked_at=time.time(), last_error=str(exc))
    return state


def handle_legacy_generate(payload):
    kind = str((payload or {}).get("type") or "").strip().lower()
    workflow_name = str((payload or {}).get("workflow_json") or "").strip().lower()
    if kind == "workflow-custom" and workflow_name == "krea2参考生成三视图.json":
        # WcsTV's canvas still routes custom nodes through /api/generate.
        # Only this Krea2 workflow is bridged to the local Comfy executor;
        # other legacy generation modes remain unchanged.
        return myridtv_comfy.run_comfy_workflow(str((payload or {}).get("workflow_json") or ""), payload)
    if kind in {"zimage", "klein"} or workflow_name in {"z-image.json", "flux2-klein.json"}:
        compat_payload = myridtv_runninghub_build.resolve_legacy_generate_payload(payload)
        task_id, _submit = submit_official(compat_payload)
        result = poll_result(task_id)
        images = myridtv_media_localize.localize_generated_media_items(result.get("images") or [], "image")
        return {
            "images": images,
            "task_id": task_id,
            "backend": "runninghub-official-proxy",
            "raw": result.get("raw") or {},
        }
    raise myridtv_core.ApiError(501, "当前版本仅兼容 Z-Image 与 Flux2-Klein 老节点，其他旧 Comfy 工作流尚未迁移。")
