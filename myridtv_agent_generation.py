# -*- coding: utf-8 -*-
"""MyridTV Agent 生成工具域（后端拆分第22刀）：生成节点创建、结果图 URL 抽取、
本地化等待/尺寸探测、任务挂起写回节点、结果挂载、提交生成、canvas_generate_images /
canvas_check_generation / canvas_update_node 三个画布工具。

逐字迁移自 rh_official_proxy.py 连续块 L(_agent_tool_create_generation_node)..
L(_agent_prepare_node_for_canvas)（12 函数 364 行，可逆还原行级 diff=0）。
行为零变更。configure() 注入：ASSETS_DIR 值（零重绑）+ LOG_FILE getter +
localize_canvas_task_result 延迟闭包（真身留主，晚于注入点定义）。
其余依赖属性链直引 myridtv_agent_state / myridtv_agent_artifact /
myridtv_volcengine / myridtv_libraries（壳穿透，运行期解析=打桩可穿）。
主文件对被仍引用的 5 函数留同名薄代理。
"""
import os
import time
import urllib.parse
import urllib.request
import uuid

from myridtv_core import append_log, parse_number

import myridtv_agent_artifact
import myridtv_agent_state
import myridtv_libraries
import myridtv_volcengine

_G_ASSETS_DIR = None
_log_file = lambda: None
_r_localize_canvas_task_result = None


def configure(assets_dir, log_file_getter, localize_canvas_task_result):
    global _G_ASSETS_DIR, _log_file, _r_localize_canvas_task_result
    _G_ASSETS_DIR = assets_dir
    _log_file = log_file_getter
    _r_localize_canvas_task_result = localize_canvas_task_result


def _agent_tool_create_generation_node(args, preset=None):
    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        return {"ok": False, "error": "prompt 必填"}
    cid, canvas = myridtv_agent_state._agent_get_canvas(str(args.get("canvas_id") or ""))
    settings = myridtv_agent_state._agent_default_run_settings(args, preset, canvas=canvas, cid=cid)
    node_x, node_y = myridtv_agent_state._agent_find_empty_position(canvas, args.get("x"), args.get("y"), 320, 420, category=myridtv_agent_state._agent_category_from_title(args.get("title")), node_type="smart-image")
    # 引用图片 → 写入节点引用 + 输入连线
    refs = myridtv_agent_state._agent_normalize_reference_items(args.get("reference_image_urls") or args.get("reference_images") or [])
    ref_node_ids = []
    run_refs = []
    for ref in refs:
        url = str((ref or {}).get("url") or "").strip()
        if not url:
            continue
        node_id = str((ref or {}).get("nodeId") or "").strip()
        image_index = int(parse_number((ref or {}).get("imageIndex"), 0) or 0)
        match = next((n for n in (canvas.get("nodes") or [])
                      if any(str(img.get("url") or "") == url for img in (n.get("images") or []) if isinstance(img, dict))
                      or (node_id and str(n.get("id") or "") == node_id)), None)
        if match and not node_id:
            node_id = str(match.get("id") or "")
        run_refs.append({
            "url": url,
            "name": str((ref or {}).get("name") or "图片{}".format(len(run_refs) + 1)).strip() or "图片{}".format(len(run_refs) + 1),
            "sourceName": str((ref or {}).get("sourceName") or match.get("title") or "").strip() if isinstance(match, dict) else str((ref or {}).get("sourceName") or "").strip(),
            "nodeId": node_id,
            "imageIndex": image_index,
            "kind": "image",
        })
        if node_id and node_id != "": 
            ref_node_ids.append(node_id)
    # 提示词里统一使用 @图片1/@图片2…，严格继承当前会话输入链顺序。
    # 如果模型没明确写参考关系，这里至少补成“参考@图片N生成”。
    prompt_with_refs = prompt
    for r in run_refs:
        token = "@" + str(r.get("name") or "").strip()
        if not token:
            continue
        if token not in prompt_with_refs:
            prompt_with_refs += " 参考{}生成".format(token)
        elif "参考{}".format(token) not in prompt_with_refs:
            prompt_with_refs += " 参考{}".format(token)
    node = {
        "id": "agent_" + uuid.uuid4().hex[:12],
        "type": "smart-image",
        "title": str(args.get("title") or "Agent 生成").strip(),
        "promptDraftText": prompt_with_refs,
        "promptDraftHtml": myridtv_agent_state._agent_html_escape(prompt_with_refs),
        "promptDraftTouched": True,
        "runPrompt": prompt_with_refs,
        "runPromptRefs": run_refs,
        "runInputRefs": run_refs,
        "inputNodeIds": list(dict.fromkeys(ref_node_ids)),
        "runSettings": myridtv_agent_state._agent_run_settings_for_storage(settings),
        "images": [],
        "x": node_x, "y": node_y,
        "created_at": int(time.time() * 1000),
        "__origin": "agent_tool_generation",
        "status": "pending",
        "role": "generation",
    }
    ok, nid, deduped = myridtv_agent_artifact._agent_prepare_node_for_canvas(cid, canvas, node, "agent_tool_generation", args)
    if not ok:
        return {"ok": False, "error": nid}
    if not deduped:
        if not isinstance(canvas.get("nodes"), list):
            canvas["nodes"] = []
        canvas["nodes"].append(node)
    if ref_node_ids:
        connections = canvas.get("connections")
        if not isinstance(connections, list):
            connections = []
            canvas["connections"] = connections
        for rid in dict.fromkeys(ref_node_ids):
            if rid != nid and not any(c.get("from") == rid and c.get("to") == nid and c.get("kind") == "input" for c in connections):
                connections.append({"from": rid, "to": nid, "kind": "input"})
    save = myridtv_agent_state._agent_http("PUT", "/api/canvases/{0}".format(urllib.parse.quote(cid)), canvas, timeout=30)
    return {"ok": True, "node_id": nid, "canvas_id": cid, "save_ok": save.get("ok", save.get("canvas") is not None), "deduped": deduped}


def _agent_extract_image_urls(task_state):
    result = task_state.get("result") if isinstance(task_state, dict) else None
    if not isinstance(result, dict):
        return []
    urls = []
    for img in result.get("images") or []:
        if isinstance(img, str):
            urls.append(img)
        elif isinstance(img, dict) and img.get("url"):
            urls.append(img["url"])
    return urls


def record_agent_generation_task_log(task_id, state):
    """Persist an Agent API result even when no canvas tab is polling the task."""
    cid = str(state.get("canvas_id") or "").strip()
    nid = str(state.get("node_id") or "").strip()
    status = str(state.get("status") or "").strip()
    if not cid or not nid or status not in ("succeeded", "failed"):
        return
    outputs = _agent_extract_image_urls(state)
    if status == "succeeded" and not outputs:
        return
    for _ in range(4):
        canvas_response = myridtv_agent_state._agent_http("GET", "/api/canvases/{}".format(urllib.parse.quote(cid)))
        canvas = canvas_response.get("canvas") if isinstance(canvas_response, dict) else None
        if not isinstance(canvas, dict):
            return
        node = next((n for n in (canvas.get("nodes") or []) if isinstance(n, dict) and str(n.get("id") or "") == nid), None)
        if node and node.get("__origin") != "agent_tool_generation":
            return
        if not node and not nid.startswith("agent_"):
            return
        node = node or {}
        logs = canvas.get("logs") if isinstance(canvas.get("logs"), list) else []
        if any(isinstance(log, dict) and (log.get("taskId") == task_id or log.get("id") == "log_" + task_id) for log in logs):
            return
        run_settings = node.get("runSettings") if isinstance(node.get("runSettings"), dict) else {}
        created = float(state.get("created_at") or time.time())
        completed = float(state.get("completed_at") or time.time())
        entry = {
            "id": "log_" + task_id,
            "taskId": task_id,
            "createdAt": int(completed * 1000),
            "status": "success" if status == "succeeded" else "failed",
            "platform": "RH-API" if state.get("provider_id") == "runninghub" else str(state.get("provider_id") or "API"),
            "nodeType": node.get("type") or "smart-image",
            "model": str(state.get("model") or run_settings.get("model") or "API Image"),
            "request": {"task_id": task_id, "provider_id": state.get("provider_id") or run_settings.get("provider_id") or "", "model": state.get("model") or run_settings.get("model") or ""},
            "prompt": node.get("runPrompt") or node.get("promptDraftText") or "",
            "outputs": outputs,
            "refs": node.get("runPromptRefs") or [],
            "runMs": max(0, int((completed - created) * 1000)),
            "error": str(state.get("error") or "") if status == "failed" else "",
        }
        saved = myridtv_agent_state._agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(cid)),
                                              {"logs": [entry] + logs, "base_updated_at": canvas.get("updated_at")}, timeout=30)
        if isinstance(saved, dict) and (saved.get("ok") or isinstance(saved.get("canvas"), dict)):
            return
    append_log(_log_file(), "[CanvasAgentLog] save failed task={}".format(task_id))


def _agent_localize_urls(urls):
    if not urls:
        return
    try:
        myridtv_agent_state._agent_http("POST", "/api/localize-generated-media",
                    {"items": [{"url": u} for u in urls], "kind": "image"}, timeout=120)
    except Exception:
        pass


def _agent_png_size(path):
    try:
        with open(path, "rb") as f:
            head = f.read(26)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return None, None
        import struct
        w, h = struct.unpack(">II", head[16:24])
        return w, h
    except Exception:
        return None, None


def _agent_local_path_for_url(url):
    if not str(url).startswith("/assets/"):
        return ""
    # 画布名可能是中文，url 中是 URL 编码（%E8%B6%85...），必须先 unquote 才能匹配磁盘路径
    rel = urllib.parse.unquote(str(url)[len("/assets/"):])
    return os.path.join(str(_G_ASSETS_DIR), rel.replace("/", os.sep))


def _agent_add_pending_task_to_node(canvas_id, node_id, task_id, kind="image"):
    """把后端任务 ID 写入节点的 pendingTasks，让前端能够按标准流程轮询并回填。"""
    cid = str(canvas_id or "").strip()
    nid = str(node_id or "").strip()
    tid = str(task_id or "").strip()
    if not cid or not nid or not tid:
        return False
    _, canvas = myridtv_agent_state._agent_get_canvas(cid)
    if not isinstance(canvas, dict):
        return False
    node = None
    for n in canvas.get("nodes") or []:
        if isinstance(n, dict) and str(n.get("id")) == nid:
            node = n
            break
    if node is None:
        return False
    pending = node.get("pendingTasks") or []
    if not isinstance(pending, list):
        pending = []
    # 去重
    if not any(str(p.get("taskId") or "") == tid for p in pending if isinstance(p, dict)):
        pending.append({"taskId": tid, "kind": str(kind or "image")})
    node["pendingTasks"] = pending
    node["pending"] = len(pending)
    save = myridtv_agent_state._agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(cid)), canvas, timeout=30)
    return save.get("ok", save.get("canvas") is not None)


def _agent_attach_result_to_node(cid, canvas, node_id, urls, task_id=""):
    node = None
    for n in canvas.get("nodes") or []:
        if isinstance(n, dict) and str(n.get("id")) == str(node_id):
            node = n
            break
    if node is None:
        return False
    images = []
    try:
        existing = node.get("images") or []
        if not isinstance(existing, list):
            existing = []
        seen_urls = {str(img.get("url") or "").strip() for img in existing if isinstance(img, dict)}
        seen_task_ids = {str(img.get("generationTaskId") or "").strip() for img in existing if isinstance(img, dict)}
        for url in urls:
            if str(url).strip() in seen_urls or (task_id and task_id in seen_task_ids):
                continue
            seen_urls.add(str(url).strip())
            w, h = _agent_png_size(_agent_local_path_for_url(url))
            item = {"url": url, "name": str(url).rsplit("/", 1)[-1], "kind": "image", "generatedResult": True}
            if task_id:
                item["generationTaskId"] = task_id
            if w and h:
                item["natural_w"] = w
                item["natural_h"] = h
            images.append(item)
        # 与前端标准流程一致：append 而非覆盖，保留节点已有图片
        node["images"] = existing + images
        node["status"] = "ready"  # 状态机：生成/回填成功 -> ready
        # 补前端重跑归档所需时间戳：nodeHasCompletedGeneration 认 runAt/runFinishedAt，
        # 缺失会让用户下次点"运行"时被判定为首跑、旧图不进历史分组
        _now_ms = int(time.time() * 1000)
        if not node.get("runStartedAt"):
            node["runStartedAt"] = _now_ms
        node["runFinishedAt"] = _now_ms
        node["runElapsedMs"] = max(0, _now_ms - int(node.get("runStartedAt") or _now_ms))
    except Exception as _exc:
        # 状态机：生成或回填异常 -> failed（渲染层红色告警）；promptDraftText 仍保留，供用户显式重跑
        node["status"] = "failed"
        append_log(_log_file(), "[CanvasNodeAttachFailed] node={} reason={}".format(node_id, _exc))
    save = myridtv_agent_state._agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(cid)), canvas, timeout=30)
    return save.get("ok", save.get("canvas") is not None)


def _agent_wait_localized(task_id, attempts=6):
    urls = []
    for _ in range(attempts):
        st = myridtv_agent_state._agent_http("GET", "/api/canvas-image-tasks/{}".format(urllib.parse.quote(task_id)))
        urls = _agent_extract_image_urls(st)
        if urls and all(str(u).startswith("/assets/") for u in urls):
            return urls
        _agent_localize_urls(urls)
        time.sleep(3)
    return urls


def _agent_submit_generation(args, preset=None):
    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        return {"ok": False, "error": "prompt 必填"}
    cid = str(args.get("canvas_id") or "").strip() or myridtv_agent_state._agent_latest_canvas_id()
    nid = str(args.get("node_id") or "").strip()
    node_title = str(args.get("node_title") or "").strip()
    settings = myridtv_agent_state._agent_default_run_settings(args, preset, cid=cid)
    refs = myridtv_agent_state._agent_normalize_reference_items(args.get("reference_image_urls") or args.get("reference_images") or [])
    if str(settings["provider_id"] or "").strip() == "comfy":
        # 本地 ComfyUI 工作流生图：model 即工作流名
        workflow_name = str(settings["model"] or "").strip()
        if not workflow_name:
            return {"ok": False, "error": "未选择 ComfyUI 工作流"}
        try:
            record = myridtv_libraries.read_workflow_record(workflow_name)
        except Exception as exc:
            return {"ok": False, "error": "读取 ComfyUI 工作流失败: {}".format(exc)}
        config = record.get("config") if isinstance(record.get("config"), dict) else {}
        fields = config.get("fields") if isinstance(config.get("fields"), list) else []
        values = {}
        prompt_field = next((f for f in fields if str(f.get("name") or "").strip() in ("提示词", "Prompt") or "prompt" in str(f.get("type") or "").lower()), None)
        if prompt_field and prompt_field.get("id"):
            values[prompt_field["id"]] = prompt
        canvas_title = str(args.get("canvas_title") or myridtv_volcengine._volcengine_canvas_title_for_output(cid)).strip()
        try:
            resp = myridtv_agent_state._agent_http("POST", "/api/workflows/{}/run".format(urllib.parse.quote(workflow_name)),
                               {"config": config, "fields": values, "canvas_id": cid, "canvas_title": canvas_title}, timeout=3700)
        except Exception as exc:
            return {"ok": False, "error": "ComfyUI 工作流执行失败: {}".format(str(exc)[:200])}
        raw_images = [str(u) for u in (resp.get("images") or []) if str(u).strip()]
        if not raw_images:
            return {"ok": False, "error": "ComfyUI 工作流未返回图片: {}".format(str(resp)[:240])}
        # 统一落盘到画布同名文件夹（与 API 分支同一套逻辑）
        localized = _r_localize_canvas_task_result({"images": raw_images}, {
            "canvas_title": canvas_title,
            "canvas_id": cid,
            "node_title": node_title,
        })
        images = [str((img or {}).get("url") or img) for img in (localized.get("images") or [])]
        return {"ok": True, "task_id": "", "images": images, "canvas_id": cid, "comfy": True}
    payload = {
        "prompt": prompt,
        "provider_id": settings["provider_id"],
        "model": settings["model"],
        "size": settings["size"],
        "quality": settings["quality"],
        "n": settings["n"],
        "reference_images": [str((r or {}).get("url") or "").strip() for r in refs if str((r or {}).get("url") or "").strip()],
        "canvas_id": cid,
        "canvas_title": str(args.get("canvas_title") or myridtv_volcengine._volcengine_canvas_title_for_output(cid)),
        "node_id": nid,
        "node_title": node_title,
        "resolution": settings["resolution"],
        "aspectRatio": settings["aspectRatio"],
    }
    resp = myridtv_agent_state._agent_http("POST", "/api/canvas-image-tasks", payload, timeout=30)
    task_id = str(resp.get("task_id") or "").strip()
    if not task_id:
        return {"ok": False, "error": "提交生图失败: {}".format(resp)}
    return {"ok": True, "task_id": task_id, "canvas_id": cid}


def _agent_tool_generate_images(args, preset=None):
    node_id = str(args.get("node_id") or "").strip()
    cid = ""
    if node_id:
        cid, canvas = myridtv_agent_state._agent_get_canvas(str(args.get("canvas_id") or ""))
    else:
        created = _agent_tool_create_generation_node(args, preset)
        if not created.get("ok"):
            return created
        node_id = str(created.get("node_id") or "")
        cid = str(created.get("canvas_id") or "")
    # 优先使用传入的 node_title，否则从节点标题取
    if not str(args.get("node_title") or "").strip() and node_id and cid:
        try:
            _, canvas = myridtv_agent_state._agent_get_canvas(cid)
            node = next((n for n in (canvas.get("nodes") or []) if isinstance(n, dict) and str(n.get("id")) == str(node_id)), None)
            if node and str(node.get("title") or "").strip():
                args = {**args, "node_title": str(node.get("title") or "").strip()}
        except Exception:
            pass
    sub = _agent_submit_generation(args, preset)
    if not sub.get("ok"):
        return sub
    if sub.get("images"):
        # ComfyUI 同步完成：直接回填节点
        attached = False
        if node_id and sub.get("images"):
            try:
                attached = _agent_attach_result_to_node(cid, myridtv_agent_state._agent_get_canvas(cid)[1], node_id, sub["images"])
            except Exception:
                attached = False
        return {"ok": True, "status": "succeeded", "task_id": sub.get("task_id") or "", "node_id": node_id,
                "images": sub["images"], "attached_to_node": attached, "comfy": True}
    task_id = sub["task_id"]
    # 把 task_id 写入 node.pendingTasks，让前端能够按标准流程轮询并自动回填
    if node_id and task_id:
        try:
            _agent_add_pending_task_to_node(cid, node_id, task_id, "image")
        except Exception as exc:
            append_log(_log_file(), f"[CanvasAgent] 无法写入 pendingTasks node={node_id} task={task_id}: {exc}")
    # 异步语义：提交后立即返回，不再在本工具内同步轮询等待（生图常需 1-5 分钟，
    # 同步等待会占住 agent 轮次让用户干等）。生成完成后图片会自动回填画布节点，
    # 需要时用 canvas_check_generation / canvas_get_state 查询。
    return {"ok": True, "status": "running", "task_id": task_id, "node_id": node_id,
            "canvas_id": cid,
            "message": "生图任务已提交,图片生成完成后会自动回填到画布节点。无需轮询等待,可先回复用户已提交。"}


def _agent_tool_check_generation(args):
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        return {"ok": False, "error": "task_id 必填"}
    node_id = str(args.get("node_id") or "").strip()
    cid = str(args.get("canvas_id") or "").strip()
    st = myridtv_agent_state._agent_http("GET", "/api/canvas-image-tasks/{}".format(urllib.parse.quote(task_id)))
    status = st.get("status") or "running"
    if status == "succeeded":
        urls = _agent_wait_localized(task_id)
        attached = False
        if urls and node_id:
            try:
                if not cid:
                    cid = myridtv_agent_state._agent_latest_canvas_id()
                attached = _agent_attach_result_to_node(cid, myridtv_agent_state._agent_get_canvas(cid)[1], node_id, urls, task_id)
            except Exception as exc:
                return {"ok": True, "status": "succeeded", "task_id": task_id, "images": urls,
                        "attached_error": str(exc)}
        return {"ok": True, "status": "succeeded", "task_id": task_id, "node_id": node_id,
                "images": urls, "attached_to_node": attached}
    if status == "failed":
        return {"ok": False, "status": "failed", "task_id": task_id,
                "error": st.get("error") or st.get("message") or "生图失败"}
    return {"ok": True, "status": "running", "task_id": task_id, "node_id": node_id,
            "canvas_id": cid, "message": "任务仍在生成中,请稍后再次调用本工具"}


def _agent_tool_update_node(args):
    node_id = str(args.get("node_id") or "").strip()
    if not node_id:
        return {"ok": False, "error": "node_id 必填"}
    cid, canvas = myridtv_agent_state._agent_get_canvas(str(args.get("canvas_id") or ""))
    node = None
    for n in canvas.get("nodes") or []:
        if isinstance(n, dict) and str(n.get("id")) == str(node_id):
            node = n
            break
    if node is None:
        return {"ok": False, "error": "节点不存在: {}".format(node_id)}
    if "text" in args and args.get("text") is not None:
        node["text"] = str(args.get("text"))
        node["content"] = str(args.get("text"))
    if "title" in args and args.get("title") is not None:
        node["title"] = str(args.get("title"))
    save = myridtv_agent_state._agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(cid)), canvas, timeout=30)
    return {"ok": True, "node_id": node_id, "save_ok": save.get("ok", save.get("canvas") is not None)}


