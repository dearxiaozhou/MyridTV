# -*- coding: utf-8 -*-
"""MyridTV Agent 批量操作域（后端拆分第13刀C-X3b）：批文本/生成节点构建、
operations 校验、单 op 应用器、canvas_batch_operations / undo_batch /
add_link / delete_node 四个批工具（批快照落 AGENT_BATCH_DIR）。

逐字迁移自 rh_official_proxy.py 连续块 L(_agent_batch_build_text_node)..
L(_agent_tool_analyze_image)（8 函数 396 行，可逆还原行级 diff=0）。行为零变更。
configure() 注入：LOG_FILE getter + normalize_model/_agent_local_path_for_url/
_agent_canvas_node_image_by_id 三闭包（留主文件）。其余依赖属性链直引
myridtv_agent_state / myridtv_agent_artifact / myridtv_agent_tools /
myridtv_codex / myridtv_canvas_store（运行期解析，测试 monkeypatch 可穿透）。
主文件对被仍引用的 6 函数留同名薄代理。
"""
import json
import time
import urllib.parse
import uuid

from myridtv_core import append_log, parse_number

import myridtv_agent_state
import myridtv_agent_artifact
import myridtv_agent_tools
import myridtv_codex
import myridtv_canvas_store

_log_file = lambda: None
_r_normalize_model = None
_r_local_path_for_url = None
_r_canvas_node_image_by_id = None


def configure(log_file_getter, normalize_model, local_path_for_url,
              canvas_node_image_by_id):
    global _log_file, _r_normalize_model, _r_local_path_for_url
    global _r_canvas_node_image_by_id
    _log_file = log_file_getter
    _r_normalize_model = normalize_model
    _r_local_path_for_url = local_path_for_url
    _r_canvas_node_image_by_id = canvas_node_image_by_id


def _agent_batch_build_text_node(canvas, params):
    text = str(params.get("text") or params.get("content") or "").strip()
    if not text:
        raise ValueError("add_node(text) 缺少 text")
    node_x, node_y = myridtv_agent_state._agent_find_empty_position(canvas, params.get("x"), params.get("y"), 316, 194, category=myridtv_agent_state._agent_category_from_title(params.get("title")), node_type="smart-prompt", text_len=len(text))
    return {
        "id": "agent_" + uuid.uuid4().hex[:12],
        "type": "smart-prompt",
        "title": str(params.get("title") or "Agent 笔记").strip(),
        "kind": "script",
        "text": text, "content": text,
        "promptDraftText": text,
        "promptDraftHtml": myridtv_agent_state._agent_html_escape(text),
        "promptDraftTouched": True,
        "llmEnabled": False, "llmSystemEnabled": False,
        "llmSystemPrompt": "You are a helpful prompt assistant.",
        "llmInstruction": "",
        "x": node_x, "y": node_y, "w": 316, "h": 194,
        "created_at": int(time.time() * 1000),
        "status": "ready",
        "role": "text",
    }


def _agent_batch_build_generation_node(canvas, params, preset):
    prompt = str(params.get("prompt") or params.get("text") or "").strip()
    if not prompt:
        raise ValueError("add_node(generation) 缺少 prompt")
    settings = myridtv_agent_state._agent_default_run_settings(params, preset, canvas=canvas)
    node_x, node_y = myridtv_agent_state._agent_find_empty_position(canvas, params.get("x"), params.get("y"), 320, 420, category=myridtv_agent_state._agent_category_from_title(params.get("title")), node_type="smart-image")
    refs = myridtv_agent_state._agent_normalize_reference_items(params.get("reference_image_urls") or params.get("reference_images") or [])
    ref_node_ids, run_refs = [], []
    for ref in refs:
        url = str((ref or {}).get("url") or "").strip()
        if not url:
            continue
        node_id = str((ref or {}).get("nodeId") or "").strip()
        match = next((n for n in (canvas.get("nodes") or [])
                      if any(str(img.get("url") or "") == url for img in (n.get("images") or []) if isinstance(img, dict))
                      or (node_id and str(n.get("id") or "") == node_id)), None)
        if match and not node_id:
            node_id = str(match.get("id") or "")
        run_refs.append({
            "url": url,
            "name": str((ref or {}).get("name") or "图片{}".format(len(run_refs) + 1)).strip() or "图片{}".format(len(run_refs) + 1),
            "sourceName": str((ref or {}).get("sourceName") or (match.get("title") if isinstance(match, dict) else "") or "").strip(),
            "nodeId": node_id,
            "imageIndex": int(parse_number((ref or {}).get("imageIndex"), 0) or 0),
            "kind": "image",
        })
        if node_id:
            ref_node_ids.append(node_id)
    prompt_with_refs = prompt
    for r in run_refs:
        token = "@" + str(r.get("name") or "").strip()
        if token and token not in prompt_with_refs:
            prompt_with_refs += " 参考{}生成".format(token)
    return {
        "id": "agent_" + uuid.uuid4().hex[:12],
        "type": "smart-image",
        "title": str(params.get("title") or "Agent 生成").strip(),
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
        "status": "pending",
        "role": "generation",
    }, list(dict.fromkeys(ref_node_ids))


def _agent_validate_operations(ops, node_ids):
    """执行前统一校验：op_type 合法性 + target 存在性。返回错误列表。"""
    errors = []
    pending_ids = set(node_ids)
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            errors.append("operations[{}]: 不是对象".format(i))
            continue
        t = str(op.get("op_type") or "").strip()
        if t not in myridtv_agent_artifact.AGENT_OP_TYPES:
            errors.append("operations[{}]: 非法 op_type '{}',只允许 {}".format(i, t, "/".join(sorted(myridtv_agent_artifact.AGENT_OP_TYPES))))
            continue
        params = op.get("params") if isinstance(op.get("params"), dict) else {}
        target = str(op.get("target_id") or params.get("node_id") or params.get("id") or "").strip()
        if t == "update_node":
            if not target:
                errors.append("operations[{}]: update_node 缺少 target_id".format(i))
            elif target not in pending_ids:
                errors.append("operations[{}]: 节点不存在: {}".format(i, target))
        elif t == "delete_node":
            if not target:
                errors.append("operations[{}]: delete_node 缺少 target_id".format(i))
            elif target not in pending_ids:
                errors.append("operations[{}]: 节点不存在: {}".format(i, target))
            else:
                pending_ids.discard(target)
        elif t == "add_link":
            f = str(params.get("from_id") or op.get("from_id") or "").strip()
            to = str(params.get("to_id") or op.get("to_id") or "").strip()
            if not f or not to:
                errors.append("operations[{}]: add_link 缺少 from_id/to_id".format(i))
            else:
                if f not in pending_ids:
                    errors.append("operations[{}]: add_link from 节点不存在: {}".format(i, f))
                if to not in pending_ids:
                    errors.append("operations[{}]: add_link to 节点不存在: {}".format(i, to))
        elif t == "delete_link":
            if not (str(params.get("from_id") or "") or str(params.get("to_id") or "")):
                errors.append("operations[{}]: delete_link 需要 from_id/to_id(至少其一)".format(i))
        elif t == "set_variable":
            if not str(params.get("name") or "").strip():
                errors.append("operations[{}]: set_variable 缺少 name".format(i))
        elif t == "layer_operate":
            if not target:
                errors.append("operations[{}]: layer_operate 缺少 target_id".format(i))
            elif target not in pending_ids:
                errors.append("operations[{}]: 节点不存在: {}".format(i, target))
    return errors


def _agent_apply_operation(canvas, op, preset, results, cid=None, session_id=""):
    t = str(op.get("op_type") or "").strip()
    params = op.get("params") if isinstance(op.get("params"), dict) else {}
    provenance = op.get("provenance") if isinstance(op.get("provenance"), dict) else params.get("provenance")
    target = str(op.get("target_id") or params.get("node_id") or params.get("id") or "").strip()
    nodes_list = canvas.get("nodes") if isinstance(canvas.get("nodes"), list) else []
    connections = canvas.get("connections")
    if not isinstance(connections, list):
        connections = []
        canvas["connections"] = connections
    if t == "add_node":
        node_type = str(params.get("node_type") or params.get("type") or "text").strip().lower()
        # Phase 5：artifactId 作为严格幂等键（intent_id/dedup_key 向后兼容映射）
        artifact_id = str(params.get("artifact_id") or params.get("artifactId") or params.get("intent_id") or params.get("dedup_key") or "").strip()
        if node_type in ("generation", "image", "smart-image", "gen"):
            node, ref_ids = _agent_batch_build_generation_node(canvas, params, preset)
            node["__origin"] = "agent_batch"
            ok, nid, deduped = myridtv_agent_artifact._agent_prepare_node_for_canvas(None, canvas, node, "agent_batch", {"artifactId": artifact_id, "intent_id": artifact_id, "provenance": provenance})
            if not ok:
                append_log(_log_file(), "[CanvasNodeRejected] origin=agent_batch reason={} title={}".format(nid, str(node.get("title"))[:40]))
                results.append({"op": "add_node", "skipped": "gate", "reason": nid, "title": node.get("title")})
            else:
                if not deduped:
                    nodes_list.append(node)
                    for rid in ref_ids:
                        if rid != node["id"] and not any(c.get("from") == rid and c.get("to") == node["id"] and c.get("kind") == "input" for c in connections):
                            connections.append({"from": rid, "to": node["id"], "kind": "input"})
                results.append({"op": "add_node", "node_id": nid, "title": node.get("title"), "type": "smart-image", "artifactId": artifact_id, "deduped": deduped})
        else:
            # Phase 8：批量文本节点同样过 Router。只有 destination=='canvas' 才继续建节点，
            # 因此不会与既有 Artifact Gate 形成两条建节点路径（需求第三十三条）。
            _btype = str(params.get("artifact_type") or params.get("artifactType") or "").strip().lower() or "text"
            _broute = myridtv_canvas_store.route_artifact(
                artifact_type=_btype,
                role="text",
                tool_name="canvas_batch_operations",
                user_text=str(myridtv_canvas_store.CANVAS_AGENT_ROUTE_CONTEXT.get("user_text") or ""),
            )
            if str(_broute.get("destination") or "canvas") == "sidebar" and cid:
                _bok, _bid, _ = myridtv_agent_artifact._agent_upsert_sidebar_artifact(
                    cid, canvas,
                    title=str(params.get("title") or "Agent 笔记").strip(),
                    content=str(params.get("text") or params.get("content") or ""),
                    artifact_type=_btype,
                    defer_save=True,
                    # Phase 9：一轮 Agent 会话 = 一个 Conversation Artifact
                    conversation_id=str(session_id or myridtv_agent_tools.CANVAS_AGENT_CURRENT_SESSION.get("session_id") or ""),
                    conversation_title=str(myridtv_canvas_store.CANVAS_AGENT_ROUTE_CONTEXT.get("user_text") or "")[:40],
                    section_type=str(params.get("section_type") or params.get("sectionType") or "").strip(),
                    section_title=str(params.get("section_title") or params.get("sectionTitle") or params.get("section") or "").strip(),
                    item_title=str(params.get("item_title") or params.get("itemTitle") or "").strip(),
                )
                if _bok:
                    results.append({"op": "add_node", "node_id": None, "artifact_id": _bid,
                                    "title": params.get("title"), "type": "sidebar-artifact",
                                    "destination": "sidebar", "reason": _broute.get("reason")})
                    return
            node = _agent_batch_build_text_node(canvas, params)
            node["__origin"] = "agent_batch"
            ok, nid, deduped = myridtv_agent_artifact._agent_prepare_node_for_canvas(None, canvas, node, "agent_batch", {"artifactId": artifact_id, "intent_id": artifact_id, "provenance": provenance})
            if not ok:
                append_log(_log_file(), "[CanvasNodeRejected] origin=agent_batch reason={} title={}".format(nid, str(node.get("title"))[:40]))
                results.append({"op": "add_node", "skipped": "gate", "reason": nid, "title": node.get("title")})
            else:
                if not deduped:
                    nodes_list.append(node)
                results.append({"op": "add_node", "node_id": nid, "title": node.get("title"), "type": "smart-prompt", "artifactId": artifact_id, "deduped": deduped})
    elif t == "update_node":
        node = next((n for n in nodes_list if str(n.get("id")) == target), None)
        if node is None:
            raise ValueError("节点不存在: {}".format(target))
        for key in ("text", "title"):
            if params.get(key) is not None:
                node[key] = str(params[key])
                if key == "text":
                    node["content"] = str(params[key])
                    if node.get("type") == "smart-prompt":
                        node["promptDraftText"] = str(params[key])
                        node["promptDraftHtml"] = myridtv_agent_state._agent_html_escape(str(params[key]))
                        node["promptDraftTouched"] = True
        if params.get("x") is not None or params.get("y") is not None:
            if params.get("x") is not None:
                node["x"] = float(params["x"])
            if params.get("y") is not None:
                node["y"] = float(params["y"])
        if params.get("prompt") is not None and node.get("type") == "smart-image":
            node["promptDraftText"] = str(params["prompt"])
            node["promptDraftHtml"] = myridtv_agent_state._agent_html_escape(str(params["prompt"]))
            node["runPrompt"] = str(params["prompt"])
        results.append({"op": "update_node", "node_id": target})
    elif t == "delete_node":
        before = len(nodes_list)
        canvas["nodes"] = [n for n in nodes_list if str(n.get("id")) != target]
        canvas["connections"] = [c for c in connections if c.get("from") != target and c.get("to") != target]
        # Phase 4：写墓碑，防止前端合并时复活
        canvas["deleted"] = myridtv_canvas_store._merge_node_tombstones(
            canvas.get("deleted"), [{"id": target, "at": int(time.time() * 1000), "by": "agent"}]
        )
        results.append({"op": "delete_node", "node_id": target, "removed": before - len(canvas["nodes"]), "tombstoned": True})
    elif t == "add_link":
        f = str(params.get("from_id") or "").strip()
        to = str(params.get("to_id") or "").strip()
        kind = str(params.get("kind") or "input").strip() or "input"
        if f == to:
            raise ValueError("add_link: 不能连接节点到自身")
        if any(c.get("from") == f and c.get("to") == to and c.get("kind") == kind for c in connections):
            results.append({"op": "add_link", "from": f, "to": to, "skipped": "已存在"})
        else:
            connections.append({"from": f, "to": to, "kind": kind})
            results.append({"op": "add_link", "from": f, "to": to})
    elif t == "delete_link":
        f = str(params.get("from_id") or "").strip()
        to = str(params.get("to_id") or "").strip()
        before = len(connections)
        canvas["connections"] = [c for c in connections
                                 if not ((not f or c.get("from") == f) and (not to or c.get("to") == to))]
        results.append({"op": "delete_link", "from": f, "to": to, "removed": before - len(canvas["connections"])})
    elif t == "set_variable":
        settings = canvas.get("settings")
        if not isinstance(settings, dict):
            settings = {}
            canvas["settings"] = settings
        variables = settings.get("agent_variables")
        if not isinstance(variables, dict):
            variables = {}
            settings["agent_variables"] = variables
        name = str(params.get("name") or "").strip()
        value = params.get("value")
        variables[name] = value
        results.append({"op": "set_variable", "name": name, "value": value})
    elif t == "layer_operate":
        node = next((n for n in nodes_list if str(n.get("id")) == target), None)
        if node is None:
            raise ValueError("节点不存在: {}".format(target))
        action = str(params.get("action") or "").strip().lower()
        if action in ("hide", "visible_off"):
            node["visible"] = False
        elif action in ("show", "visible_on"):
            node["visible"] = True
        elif action == "front":
            nodes_list.remove(node)
            nodes_list.append(node)
        elif action == "back":
            nodes_list.remove(node)
            nodes_list.insert(0, node)
        else:
            raise ValueError("layer_operate: 非法 action '{}',只允许 show/hide/front/back".format(action))
        results.append({"op": "layer_operate", "node_id": target, "action": action})


def _agent_tool_batch_operations(args, preset=None, session_id=""):
    ops = args.get("operations")
    if not isinstance(ops, list):
        return {"ok": False, "error": "operations 数组必填"}
    ops = [op for op in ops if isinstance(op, dict) and str(op.get("op_type") or "").strip()][:50]
    if not ops:
        return {"ok": True, "batch_id": "", "results": [], "note": "空操作数组,未做任何变更"}
    cid, canvas = myridtv_agent_state._agent_get_canvas(str(args.get("canvas_id") or ""))
    node_ids = {str(n.get("id")) for n in (canvas.get("nodes") or []) if isinstance(n, dict)}
    errors = _agent_validate_operations(ops, node_ids)
    if errors:
        return {"ok": False, "error": "操作校验失败,未执行任何变更", "errors": errors[:10]}
    snapshot = json.dumps(canvas, ensure_ascii=False)
    results = []
    batch_provenance = args.get("provenance") if isinstance(args.get("provenance"), dict) else None
    try:
        for op in ops:
            if batch_provenance and isinstance(op, dict):
                op = dict(op)
                params = op.get("params") if isinstance(op.get("params"), dict) else {}
                params = dict(params)
                params.setdefault("provenance", batch_provenance)
                op["params"] = params
                op.setdefault("provenance", batch_provenance)
            _agent_apply_operation(canvas, op, preset, results, cid, session_id=session_id)
    except Exception as exc:
        restored = json.loads(snapshot)
        canvas.clear()
        canvas.update(restored)
        myridtv_agent_state._agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(cid)), canvas, timeout=30)
        return {"ok": False, "error": "执行失败已回滚: {}".format(exc), "rolled_back": True}
    save = myridtv_agent_state._agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(cid)), canvas, timeout=30)
    created = [r for r in results if isinstance(r, dict) and r.get("op") == "add_node"]
    if created:
        append_log(_log_file(), "[CanvasBatchCreate] origin=agent_batch canvas={} count={} ids={}".format(
            cid, len(created), ",".join(str(r.get("node_id")) for r in created[:12])))
    batch_id = "batch_" + uuid.uuid4().hex[:12]
    try:
        myridtv_agent_artifact.AGENT_BATCH_DIR.mkdir(parents=True, exist_ok=True)
        (myridtv_agent_artifact.AGENT_BATCH_DIR / (batch_id + ".json")).write_text(json.dumps({
            "batch_id": batch_id, "canvas_id": cid, "created_at": int(time.time() * 1000),
            "snapshot": json.loads(snapshot), "operations": ops,
        }, ensure_ascii=False), encoding="utf-8")
    except Exception:
        batch_id = ""
    return {"ok": True, "batch_id": batch_id, "canvas_id": cid, "executed": len(results),
            "results": results, "save_ok": save.get("ok", save.get("canvas") is not None)}


def _agent_tool_undo_batch(args):
    batch_id = str(args.get("batch_id") or "").strip()
    if not batch_id:
        return {"ok": False, "error": "batch_id 必填"}
    path = myridtv_agent_artifact.AGENT_BATCH_DIR / (batch_id + ".json")
    if not path.exists():
        return {"ok": False, "error": "批次不存在或已过期: {}".format(batch_id)}
    data = json.loads(path.read_text(encoding="utf-8"))
    cid = str(data.get("canvas_id") or "")
    snapshot = data.get("snapshot")
    if not cid or not isinstance(snapshot, dict):
        return {"ok": False, "error": "批次快照损坏"}
    cur_cid, canvas = myridtv_agent_state._agent_get_canvas(cid)
    canvas["nodes"] = snapshot.get("nodes") or []
    canvas["connections"] = snapshot.get("connections") or []
    if isinstance(snapshot.get("settings"), dict):
        canvas["settings"] = snapshot["settings"]
    save = myridtv_agent_state._agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(cid)), canvas, timeout=30)
    return {"ok": True, "batch_id": batch_id, "canvas_id": cid,
            "undone_ops": len(data.get("operations") or []),
            "save_ok": save.get("ok", save.get("canvas") is not None)}


def _agent_tool_add_link(args):
    return _agent_tool_batch_operations({"operations": [{
        "op_type": "add_link",
        "params": {"from_id": args.get("from_id"), "to_id": args.get("to_id"), "kind": args.get("kind") or "input"},
    }, ], "canvas_id": args.get("canvas_id")})


def _agent_tool_delete_node(args):
    return _agent_tool_batch_operations({"operations": [{
        "op_type": "delete_node", "target_id": args.get("node_id"),
    }], "canvas_id": args.get("canvas_id")})


