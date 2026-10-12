"""External canvas contract: explicit targets, readable results and reversible writes.

Node construction and mutation still use the established Agent builders and Gate.
Receipts/snapshots live under the configured user-data directory, never the app tree.
"""
import copy
import hashlib
import json
import re
import threading
import time
import uuid
from pathlib import Path

import myridtv_agent_artifact as artifacts
import myridtv_agent_batch as batch
import myridtv_agent_state as state
import myridtv_canvas_store as store
import myridtv_task_state as tasks
from myridtv_core import CanvasConflictError

_target_locks = {}
_locks_guard = threading.Lock()
GLOBAL_TOOLS = {"canvas_list_canvases", "canvas_create", "canvas_list_skills", "canvas_save_skill"}
READ_TOOLS = {"canvas_get_state", "canvas_get_node", "canvas_get_selection", "canvas_search",
              "canvas_check_generation", "canvas_list_snapshots", "canvas_get_snapshot"}


def _target_lock(cid):
    with _locks_guard:
        return _target_locks.setdefault(cid, threading.RLock())


def fail(message, code="invalid_arguments", **extra):
    return {"ok": False, "error": str(message), "error_code": code, **extra}


def _directory(kind):
    return Path(artifacts.AGENT_BATCH_DIR) / ("mcp_" + kind)


def _write_record(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _record_path(kind, record_id):
    if not re.fullmatch(r"(?:batch|snapshot)_[a-f0-9]{12,32}", record_id):
        raise ValueError("无效的记录 ID")
    return _directory(kind) / (record_id + ".json")


def _load_record(kind, record_id, cid):
    path = _record_path(kind, record_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("canvas_id") != cid:
        raise ValueError("记录不属于目标画布")
    return path, data


def _summary(node):
    return {**{k: copy.deepcopy(node[k]) for k in
               ("id", "type", "title", "label", "x", "y", "w", "h", "status",
                "images", "pendingTasks", "runSettings", "inputNodeIds", "flowLayout") if k in node},
            "text_preview": str(next((node[k] for k in
                ("text", "content", "promptDraftText", "runPrompt") if node.get(k)), ""))[:500]}


def _check_revision(args, canvas):
    expected = args.get("expected_updated_at")
    if expected is not None and expected != canvas.get("updated_at"):
        return fail("画布已被修改，请重新读取后重试", "conflict",
                    current_updated_at=canvas.get("updated_at"), retryable=True)


def _restore(canvas, snapshot):
    # Restoration is explicit, revision-checked and includes deleted-node tombstones.
    payload = copy.deepcopy(canvas)
    for key in ("nodes", "connections", "settings", "artifacts", "viewport", "inputMode"):
        if key in snapshot:
            payload[key] = copy.deepcopy(snapshot[key])
    payload["restore_node_ids"] = [n["id"] for n in payload.get("nodes", []) if n.get("id")]
    payload["base_updated_at"] = canvas["updated_at"]
    return store.save_canvas_record(canvas["id"], payload)


def _batch(args):
    cid = args["canvas_id"]
    ops = args["operations"]
    if not 1 <= len(ops) <= 50:
        return fail("operations 需要包含 1–50 项操作，不会静默截断")
    with store._canvas_save_lock:
        canvas = store.read_canvas_record(cid, include_deleted=False)
        conflict = _check_revision(args, canvas)
        if conflict:
            return conflict
        errors = batch._agent_validate_operations(ops, {str(n.get("id")) for n in canvas["nodes"]})
        if errors:
            return fail("批量操作校验失败，未保存任何变更", errors=errors[:10])
        snapshot = copy.deepcopy(canvas)
        results = []
        for op in ops:
            batch._agent_apply_operation(canvas, op, None, results, cid, session_id="mcp")
        if any(r.get("skipped") == "gate" for r in results):
            return fail("节点被 Artifact Gate 拦截，整批未保存", "mutation_rejected", results=results)
        # Keep input connections and node references consistent, as manual wiring does.
        input_ids = {}
        for edge in canvas.get("connections", []):
            if edge.get("kind", "input") == "input":
                input_ids.setdefault(edge.get("to"), []).append(edge.get("from"))
        for node in canvas.get("nodes", []):
            node["inputNodeIds"] = list(dict.fromkeys(input_ids.get(node.get("id"), [])))
        batch_id = "batch_" + uuid.uuid4().hex
        path = _record_path("batches", batch_id)
        record = {"batch_id": batch_id, "canvas_id": cid, "created_at": int(time.time()*1000),
                  "snapshot": snapshot, "operations": ops, "state": "prepared"}
        _write_record(path, record)
        saved = store.save_canvas_record(cid, canvas)
        record.update(state="committed", after_updated_at=saved["updated_at"])
        _write_record(path, record)
        return {"ok": True, "canvas_id": cid, "batch_id": batch_id, "executed": len(results),
                "results": results, "save_ok": True, "updated_at": saved["updated_at"]}


def _undo(args):
    with store._canvas_save_lock:
        path, record = _load_record("batches", args["batch_id"], args["canvas_id"])
        if record.get("state") == "undone":
            return {"ok": True, "batch_id": args["batch_id"], "canvas_id": args["canvas_id"],
                    "already_undone": True, "save_ok": True, "updated_at": record["undo_updated_at"]}
        if record.get("state") != "committed":
            return fail("批次未确认提交，不能撤销", "outcome_unknown")
        canvas = store.read_canvas_record(args["canvas_id"], include_deleted=False)
        if canvas["updated_at"] != record["after_updated_at"]:
            return fail("批次之后画布已有新修改，撤销已阻止以保留这些修改", "conflict",
                        current_updated_at=canvas["updated_at"])
        saved = _restore(canvas, record["snapshot"])
        record.update(state="undone", undo_updated_at=saved["updated_at"])
        _write_record(path, record)
        return {"ok": True, "canvas_id": args["canvas_id"], "batch_id": args["batch_id"],
                "undone_ops": len(record["operations"]), "save_ok": True, "updated_at": saved["updated_at"]}


def _snapshot(name, args):
    cid = args["canvas_id"]
    if name == "canvas_list_snapshots":
        records = []
        for path in _directory("snapshots").glob("snapshot_*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("canvas_id") == cid:
                records.append({k: data[k] for k in ("snapshot_id", "canvas_id", "created_at", "label")})
        records.sort(key=lambda r: r["created_at"], reverse=True)
        return {"canvas_id": cid, "snapshots": records[:args.get("limit", 50)]}
    if name in ("canvas_get_snapshot", "canvas_restore_snapshot"):
        _, record = _load_record("snapshots", args["snapshot_id"], cid)
        if name == "canvas_get_snapshot":
            return record
        with store._canvas_save_lock:
            canvas = store.read_canvas_record(cid, include_deleted=False)
            conflict = _check_revision(args, canvas)
            if conflict:
                return conflict
            saved = _restore(canvas, record["snapshot"])
            return {"ok": True, "canvas_id": cid, "snapshot_id": args["snapshot_id"],
                    "updated_at": saved["updated_at"], "save_ok": True}
    canvas = store.read_canvas_record(cid, include_deleted=False)
    snapshot_id = "snapshot_" + uuid.uuid4().hex
    record = {"snapshot_id": snapshot_id, "canvas_id": cid, "created_at": int(time.time()*1000),
              "label": args.get("label", ""), "snapshot": canvas}
    _write_record(_record_path("snapshots", snapshot_id), record)
    return {"ok": True, **{k: v for k, v in record.items() if k != "snapshot"},
            "updated_at": canvas["updated_at"]}


def _dispatch(name, args, legacy, fetch):
    if name in ('canvas_upsert_flow','canvas_layout_flow'):
        import myridtv_flow_mcp
        return myridtv_flow_mcp.upsert(args)
    if name == "canvas_batch_operations":
        return _batch(args)
    if name == "canvas_undo_batch":
        return _undo(args)
    if name in {"canvas_snapshot", "canvas_list_snapshots", "canvas_get_snapshot", "canvas_restore_snapshot"}:
        return _snapshot(name, args)
    if name in GLOBAL_TOOLS:
        # Skills are independent of the existence of any canvas.
        if name == "canvas_list_skills":
            import myridtv_agent_tools
            return myridtv_agent_tools._agent_tool_list_skills(args)
        if name == "canvas_save_skill":
            import myridtv_agent_tools
            return myridtv_agent_tools._agent_tool_save_skill(args)
        return legacy(name, args)
    canvas = store.read_canvas_record(args["canvas_id"], include_deleted=False)
    nodes = canvas.get("nodes", [])
    if args.get("node_id") and not any(n.get("id") == args["node_id"] for n in nodes):
        return fail("目标画布中不存在该节点", "node_not_found")
    if name == "canvas_get_state":
        limit, offset = args.get("limit", 100), args.get("offset", 0)
        edges = canvas.get("connections", [])
        return {"canvas_id": canvas["id"], "title": canvas["title"], "updated_at": canvas["updated_at"],
                "node_count": len(nodes), "edge_count": len(edges), "nodes": [_summary(n) for n in nodes[offset:offset+limit]],
                "edges": edges, "offset": offset, "has_more": offset+limit < len(nodes)}
    if name == "canvas_get_node":
        return {"canvas_id": canvas["id"], "updated_at": canvas["updated_at"],
                "node": next(n for n in nodes if n.get("id") == args["node_id"])}
    if name == "canvas_search":
        query = args["query"].casefold()
        matches = [n for n in nodes if any(query in str(n.get(k, "")).casefold()
                   for k in ("title", "label", "text", "content", "promptDraftText", "runPrompt"))]
        offset, limit = args.get("offset", 0), args.get("limit", 50)
        return {"canvas_id": canvas["id"], "query": args["query"], "matches": len(matches),
                "nodes": [_summary(n) for n in matches[offset:offset+limit]], "has_more": offset+limit < len(matches)}
    if name == "canvas_get_selection":
        return {"canvas_id": canvas["id"], "available": False, "selected_ids": [], "nodes": [],
                "reason": "界面选择是临时状态，目前没有活动界面会话同步；请明确传入 node_id"}
    if name == "canvas_check_generation":
        task = tasks.get_task_state(args["task_id"])
        if not task:
            return fail("任务不存在或已过期", "task_not_found")
        if task.get("canvas_id") != args["canvas_id"]:
            return fail("任务不属于目标画布", "task_canvas_mismatch")
        if args.get("node_id") and task.get("node_id") != args["node_id"]:
            return fail("任务不属于目标节点", "task_node_mismatch")
        response = state._agent_http("GET", "/api/canvas-image-tasks/" + args["task_id"])
        if response.get("error") and not response.get("status"):
            return fail(response["error"], "task_query_failed", retryable=True)
        # Polling is read-only with respect to canvas nodes; backend task localization stays shared.
        fields = ("status", "images", "videos", "audios", "error", "message", "localized_at", "node_id")
        result = {k: response[k] for k in fields if k in response}
        media = response.get("result") if isinstance(response.get("result"), dict) else {}
        for key in ("images", "videos", "audios"):
            if key in media:
                result[key] = media[key]
        # A successfully queried failed job is data, not a failure of this read tool.
        return {"result": {"canvas_id": args["canvas_id"], "task_id": args["task_id"], **result}}
    conflict = _check_revision(args, canvas)
    if conflict:
        return conflict
    result = legacy(name, args)
    if isinstance(result, dict) and not result.get("error") and result.get("ok") is not False:
        payload = result.get("result", result)
        if payload.get("save_ok") is False:
            return fail("修改未保存，请重新读取画布后重试", "save_failed", retryable=True)
        payload.setdefault("canvas_id", args["canvas_id"])
        payload["updated_at"] = store.read_canvas_record(args["canvas_id"], include_deleted=False)["updated_at"]
    return result


def _validate(args, schema):
    if not isinstance(args, dict):
        return "arguments 必须是对象"
    for key in schema.get("required", []):
        if key not in args or args[key] is None or (isinstance(args[key], str) and not args[key].strip()):
            return key + " 必填"
    for key, value in args.items():
        prop = schema.get("properties", {}).get(key)
        if prop is None:
            return "未知参数: " + key
        kind = prop.get("type")
        valid = {"string": isinstance(value, str), "integer": isinstance(value, int) and not isinstance(value, bool),
                 "number": isinstance(value, (int, float)) and not isinstance(value, bool),
                 "array": isinstance(value, list), "object": isinstance(value, dict), "boolean": isinstance(value, bool)}
        if kind in valid and not valid[kind]:
            return key + " 类型应为 " + kind
        if "enum" in prop and value not in prop["enum"]:
            return key + " 不在允许值内"
        if kind in ("integer", "number") and (value < prop.get("minimum", -float("inf")) or value > prop.get("maximum", float("inf"))):
            return key + " 超出允许范围"
        if kind == "array" and any(not isinstance(v, str) for v in value) and prop.get("items", {}).get("type") == "string":
            return key + " 数组项必须是字符串"


def install(registry, legacy, fetch):
    def add(name, description, properties=None, required=None):
        registry[name] = {"description": description, "inputSchema": {
            "type": "object", "properties": properties or {}, "required": required or []}}
    string = {"type": "string"}
    node_properties = {key:string for key in ('id','type','title','text','content','prompt','parent_id','parentId',
                                            'provider_id','model','size','aspect_ratio','resolution','quality')}
    node_properties.update(width={'type':'number','minimum':28,'maximum':20000},
                           height={'type':'number','minimum':28,'maximum':20000},
                           branch_order={'type':'number'},branchOrder={'type':'number'},locked={'type':'boolean'},
                           depends_on={'type':'array','items':string},images={'type':'array','items':{'type':'object'}},
                           count={'type':'integer','minimum':1},reference_image_urls={'type':'array','items':string})
    flow_properties = {'workflow_id':string,'layout':{'type':'string','enum':['tree_lr']},
                       'nodes':{'type':'array','maxItems':100,'items':{'type':'object','properties':node_properties,'required':['id'],'additionalProperties':False}},
                       'edges':{'type':'array','maxItems':300,'items':{'type':'object','properties':{
                           'from':string,'to':string,'kind':{'type':'string','enum':['input','flow']},'label':string},
                           'required':['from','to'],'additionalProperties':False}}}
    add('canvas_upsert_flow', '按稳定 ID 批量创建/更新工作流并原子保存。layout 默认 tree_lr，自动左到右按真实尺寸布局，禁止 x/y；节点 parent_id/depends_on 或 edges 表达真实多输入 DAG，branch_order 控制分支顺序。锁定节点保留位置，其他工作流不移动。可在 edges 引用画布已有共享资产，无需重复创建。增量调用只需新增/更新节点和连线；省略节点不会删除。生成节点需 prompt，文本节点需 text。尺寸变化保存后自动重排当前工作流。', flow_properties, ['workflow_id','nodes'])
    add('canvas_layout_flow', '重新布局一个已有工作流（例如生成结果尺寸变化后）；保留锁定及无关节点。',
        {'workflow_id':string,'layout':{'type':'string','enum':['tree_lr']}},['workflow_id'])
    add("canvas_get_node", "读取一个节点的完整正文、图片、运行参数和待处理任务", {"node_id": string}, ["node_id"])
    add("canvas_check_generation", "查询生图任务的状态和结果；不存在或不属于指定画布时明确报错。按需查询，避免高频轮询。",
        {"task_id": string, "node_id": string}, ["task_id"])
    # Share the operation descriptions/schema with the built-in Agent.
    import myridtv_agent_tools
    for item in myridtv_agent_tools.CANVAS_AGENT_TOOLS:
        function = item["function"]
        if function["name"] in ("canvas_batch_operations", "canvas_undo_batch"):
            registry[function["name"]] = {"description": function["description"], "inputSchema": copy.deepcopy(function["parameters"])}
    registry["canvas_batch_operations"]["description"] += " 外部 MCP 每批最多50项，失败不保存；撤销只允许在批次之后没有新修改时执行。"
    add("canvas_snapshot", "保存持久快照，返回 snapshot_id；不会修改当前画布", {"label": string})
    add("canvas_list_snapshots", "列出目标画布已保存的快照", {"limit": {"type": "integer", "minimum": 1, "maximum": 200}})
    add("canvas_get_snapshot", "读取快照内容", {"snapshot_id": string}, ["snapshot_id"])
    add("canvas_restore_snapshot", "恢复快照；必须传入刚读取的画布版本，避免覆盖并发修改",
        {"snapshot_id": string}, ["snapshot_id", "expected_updated_at"])
    for name in ("canvas_get_state", "canvas_search"):
        registry[name]["inputSchema"]["properties"].update(
            limit={"type": "integer", "minimum": 1, "maximum": 200}, offset={"type": "integer", "minimum": 0})
    registry["canvas_get_state"]["description"] = "读取画布版本、节点正文摘要、图片、运行参数和任务；完整节点用 canvas_get_node，节点列表支持分页"
    registry["canvas_get_selection"]["description"] = "报告界面选择同步是否可用；目前无活动界面桥接时 available=false，不代表用户未选择节点"
    registry["canvas_create"]["description"] = "新建画布，返回 canvas_id；后续操作必须显式传入此 ID"
    # Expose the generation parameter family consistently across entry points.
    params = registry["canvas_create_node"]["inputSchema"]["properties"]
    for name in ("canvas_generate_images", "canvas_create_generation_node"):
        for key in ("provider_id", "model", "size", "aspect_ratio", "resolution", "quality", "count"):
            registry[name]["inputSchema"]["properties"][key] = copy.deepcopy(params[key])
    for name, definition in registry.items():
        schema = definition["inputSchema"]
        schema["additionalProperties"] = False
        if name not in GLOBAL_TOOLS:
            schema["properties"]["canvas_id"] = string
            schema["required"] = list(dict.fromkeys(schema.get("required", []) + ["canvas_id"]))
        if name not in READ_TOOLS and name not in ("canvas_list_canvases", "canvas_list_skills"):
            schema["properties"]["idempotency_key"] = string
            if name not in GLOBAL_TOOLS:
                schema["properties"]["expected_updated_at"] = {"type": "integer", "minimum": 1}

    def handle(name, args):
        if name not in registry:
            return fail("未知工具: " + name, "tool_not_found")
        error = _validate(args, registry[name]["inputSchema"])
        if error:
            return fail(error)
        args = copy.deepcopy(args)
        try:
            if name in READ_TOOLS:
                return _dispatch(name, args, legacy, fetch)
            with _target_lock(args.get("canvas_id", "global")):
                key = args.get("idempotency_key")
                receipt_path = None
                if key:
                    token = hashlib.sha256((args.get("canvas_id", "global") + "\0" + key).encode()).hexdigest()
                    receipt_path = _directory("receipts") / (token + ".json")
                    fingerprint = hashlib.sha256(json.dumps([name, args], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                    if receipt_path.exists():
                        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                        if receipt["fingerprint"] != fingerprint:
                            return fail("idempotency_key 已用于不同操作，请为新操作使用新键", "idempotency_conflict")
                        if receipt.get("state") == "completed":
                            return receipt["result"]
                        return fail("上次请求结果尚未确认，请读取画布或任务核对，不能自动重复执行", "outcome_unknown")
                    _write_record(receipt_path, {"fingerprint": fingerprint, "state": "pending"})
                result = _dispatch(name, args, legacy, fetch)
                if receipt_path:
                    _write_record(receipt_path, {"fingerprint": fingerprint, "state": "completed", "result": result})
                return result
        except CanvasConflictError as exc:
            return fail(exc.detail, "conflict", retryable=True,
                        current_updated_at=exc.current_canvas.get("updated_at"))
        except (ValueError, KeyError) as exc:
            return fail(str(exc))
        except FileNotFoundError:
            return fail("记录不存在或已过期", "record_not_found")
        except Exception as exc:
            return fail(str(exc), "execution_failed")
    return handle
