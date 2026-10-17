# -*- coding: utf-8 -*-
"""MyridTV Agent 画布/Artifact 仓库区（后端拆分第13刀C-X3a）：建节点守卫、
artifactId 去重、节点入画布准备、repo upsert（含阶段守卫与去重回声）、
对话 artifact / sidebar artifact / node-artifact 关联的读写落盘族。

逐字迁移自 rh_official_proxy.py 连续块 L(_agent_should_create_canvas_node)..
L(_agent_batch_build_text_node)（8 函数 356 行，可逆还原行级 diff=0；唯一位移：
AGENT_BATCH_DIR 一行挪进 configure()，脚本单独核账）。行为零变更。
configure() 注入 USER_DATA_DIR（AGENT_BATCH_DIR 派生，import 期不可求值）与
LOG_FILE getter（全文件 74 处引用仍在主搬家，只能延迟读）。
_agent_http 直引 myridtv_agent_state；CANVAS_AGENT_CURRENT_PHASE 与 artifact
ID 族直引 myridtv_canvas_store；append_log 直引 myridtv_core。
主文件对被仍引用函数留同名薄代理；AGENT_BATCH_DIR/AGENT_OP_TYPES 主侧别名。
"""
import re
import time
import urllib.parse
import uuid

from myridtv_core import append_log

import myridtv_agent_state
import myridtv_canvas_store

_cmm = None
AGENT_BATCH_DIR = None
_log_file = lambda: None


def configure(user_data_dir, log_file_getter, cmm):
    global AGENT_BATCH_DIR, _log_file, _cmm
    AGENT_BATCH_DIR = user_data_dir / "data" / "agent_batches"
    _log_file = log_file_getter
    _cmm = cmm


def _agent_should_create_canvas_node(node):
    """Artifact Gate：后端 Agent 自动建节点前的唯一合法性闸门。

    只有具备明确身份且有真实内容的节点才允许进入画布；
    空壳节点（无 id / 无 type / 无 title·text·images 任一内容）一律拦截，
    杜绝“模型说了一段话就变成了空节点”的污染。
    注意：generation 占位节点(images=[]) 凭借 promptDraftText 通过本闸门，
    因为它代表“用户授权的待生成任务”，不等同于空壳。
    """
    if not isinstance(node, dict):
        return False, "node 不是 dict"
    nid = str(node.get("id") or "").strip()
    if not nid:
        return False, "缺少 id"
    ntype = str(node.get("type") or "").strip()
    if not ntype:
        return False, "缺少 type"
    title = str(node.get("title") or "").strip()
    text = str(node.get("text") or node.get("content") or node.get("promptDraftText") or "").strip()
    images = node.get("images") if isinstance(node.get("images"), list) else []
    if not (title or text or images):
        return False, "空壳(无 title/text/images)"
    return True, ""


def _agent_ensure_artifactId(node, args):
    """Artifact 契约：解析/补全 artifactId（结构化产物的唯一幂等键）。

    优先级 node.artifactId > args.artifactId > args.artifact_id > args.intent_id；
    都没有时兜底：生成类用 node.id（不崩，同 id 天然去重），
    文本类基于 title+text 哈希（跨重试/重放稳定去重）。
    """
    aid = str(node.get("artifactId") or (args or {}).get("artifactId") or (args or {}).get("artifact_id") or (args or {}).get("intent_id") or "").strip()
    if aid:
        return aid
    ntype = str(node.get("type") or "")
    is_gen = ntype in ("smart-image", "generation", "image", "gen", "video", "smart-video")
    if is_gen:
        return str(node.get("id") or "agent_" + uuid.uuid4().hex[:12])
    import hashlib
    payload = str(node.get("title") or "") + "|" + str(node.get("text") or node.get("content") or node.get("promptDraftText") or "")
    return "art-" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _agent_prepare_node_for_canvas(cid, canvas, node, origin, args=None):
    """建节点合法性决策单一权威（Artifact 双写归一核心）：

    1) 解析/补全 artifactId
    2) artifactId 去重：同 artifactId 已建节点 -> 复用(deduped=True)，不再建重复节点
    3) Artifact Gate：空壳/无身份拦截
    返回 (ok, node_id_or_error, deduped)
    """
    if not isinstance(node, dict):
        return False, "node 不是 dict", False
    # Only external gateway requests opt into workflow layout; manual/internal paths stay native.
    from myridtv_canvas_gateway import enroll_new_node
    enroll_new_node(cid, canvas, node)
    aid = _agent_ensure_artifactId(node, args)
    node["artifactId"] = aid
    node["__origin"] = origin
    provenance = (args or {}).get("provenance") if isinstance(args, dict) else None
    if isinstance(provenance, dict):
        node["provenance"] = dict(provenance)
        node.setdefault("created_by", "agent")
        node.setdefault("conversation_id", provenance.get("conversation_id") or "")
        node.setdefault("task_id", provenance.get("task_id") or "")
        node.setdefault("step_id", provenance.get("step_id") or "")
        node.setdefault("turn_id", provenance.get("turn_id") or "")
        node.setdefault("tool_call_id", provenance.get("tool_call_id") or "")
    nodes_list = canvas.get("nodes") if isinstance(canvas.get("nodes"), list) else []
    existing = next((n for n in nodes_list if isinstance(n, dict) and str(n.get("artifactId") or "") == aid), None)
    if existing is not None:
        append_log(_log_file(), "[ArtifactDedup] artifactId={} reuse_node={}".format(aid, existing.get("id")))
        return True, existing["id"], True
    ok, reason = _agent_should_create_canvas_node(node)
    if not ok:
        append_log(_log_file(), "[CanvasNodeRejected] origin={} reason={} title={}".format(origin, reason, str(node.get("title"))[:40]))
        return False, "节点被 Artifact Gate 拦截: {}".format(reason), False
    # ---- CanvasMutationManager 收口（#10/#28/#41）----
    # 既有 Artifact Gate 通过后再过一层硬守卫：空 prompt / 非法类型 / 重复 / 阶段守卫，
    # 并写入 Ledger（开发模式 Mutation Timeline 数据源，#39）。模型即使犯错也不可能在
    # Prompt Ready 以前写入垃圾节点。
    if _cmm is not None:
        _mgr_ok, _mgr_reason, _mgr_det = _cmm.validate_asset_node(
            node, phase=myridtv_canvas_store.CANVAS_AGENT_CURRENT_PHASE.get("phase") or "")
        if not _mgr_ok:
            append_log(_log_file(), "[CanvasMutationBlocked] origin={} reason={} title={}".format(
                origin, _mgr_reason, str(node.get("title"))[:40]))
            return False, "节点被 MutationManager 拦截: {}".format(_mgr_reason), False
    return True, node["id"], False


def _agent_canvas_repo_upsert_node(cid, canvas, node, origin, args=None):
    """Canvas Repo：后端唯一受 Artifact Gate 保护的节点落库入口（即时写通道共用）。

    A1 与 MCP 经此落库；A2(含输入连线)与批量通道复用 _agent_prepare_node_for_canvas
    做去重+Gate 决策，仅因需额外连线/整体提交而保留各自 save。
    返回 (ok, node_id_or_error, save_ok, deduped)。
    """
    ok, nid, deduped = _agent_prepare_node_for_canvas(cid, canvas, node, origin, args)
    if not ok:
        return False, nid, False, deduped
    if deduped:
        save = myridtv_agent_state._agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(str(cid))), canvas, timeout=30)
        return True, nid, save.get("ok", save.get("canvas") is not None), True
    nodes_list = canvas.get("nodes") if isinstance(canvas.get("nodes"), list) else []
    canvas["nodes"] = nodes_list
    nodes_list.append(node)
    save = myridtv_agent_state._agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(str(cid))), canvas, timeout=30)
    return True, node["id"], save.get("ok", save.get("canvas") is not None), False


def _agent_upsert_conversation_artifact(cid, canvas, title="", content="", artifact_type="brainstorm",
                                        conversation_id="", conversation_title="",
                                        section_type="", section_title="", item_title="",
                                        item_id="", resource_id="", source_run_id="", source_event_id="",
                                        defer_save=False, metadata=None):
    """Phase 9：Conversation Artifact 容器模式 —— "一轮对话 = 一个整体产物"。

    与旧行为的本质区别：artifact id 由 (canvasId, conversationId, type) 确定性推导，
    所以同一轮头脑风暴产生的 人物/故事/场面/世界观 会合并成同一个 Conversation
    的不同 Section，而不是 4 个平铺的 Sidebar 一级条目（需求第二/六/二十七条）。

    返回 (ok, artifact_id, save_ok)。
    """
    if not cid or not isinstance(canvas, dict) or not str(conversation_id or "").strip():
        return False, "缺少 canvas 或 conversation_id", False

    atype = str(artifact_type or "brainstorm").strip().lower()
    aid = myridtv_canvas_store.conversation_artifact_id(cid, conversation_id, atype)
    now = int(time.time() * 1000)

    arts = canvas.get("artifacts") if isinstance(canvas.get("artifacts"), list) else []
    canvas["artifacts"] = arts
    hit = None
    for a in arts:
        if isinstance(a, dict) and str(a.get("id") or "") == aid:
            hit = a
            break

    if hit is None:
        # 标题优先级：显式 conversation_title > 首个 Section 标题 > 类型标签 > Brainstorm
        seed = str(conversation_title or "").strip() or str(title or "").strip()
        if not seed and atype not in myridtv_canvas_store.CONVERSATION_CONTAINER_TYPES:
            seed = atype[:60]
        hit = {
            "id": aid,
            "canvasId": str(cid),
            "conversationId": str(conversation_id),
            "artifactType": atype,
            "kind": "conversation",
            "title": seed or "Brainstorm",
            "content": "",
            "sections": [],
            "resourceId": str(resource_id or ""),
            "canvasNodeId": "",
            "sourceRunId": str(source_run_id or ""),
            "sourceEventId": str(source_event_id or ""),
            "version": 1,
            "createdAt": now,
            "updatedAt": now,
        }
        arts.append(hit)

    secs = hit.get("sections") if isinstance(hit.get("sections"), list) else []
    hit["sections"] = secs

    # 板块名取值链：显式 section_title > 产物 title > 退化成类型标签
    sec_name = str(section_title or title or "").strip()
    stype = myridtv_canvas_store.infer_section_type(sec_name, section_type)
    stitle = sec_name or myridtv_canvas_store.section_type_label(stype)
    # 去重键：有名字就按名字；连名字都没有才按类型。
    # 不能仅因语义类型相同就合并 —— 「悲剧结局/开放结局/反转结局」都推断成 direction，
    # 但它们明明是三个不同板块。
    if sec_name:
        sid = myridtv_canvas_store.artifact_section_id(conversation_id, "", sec_name)
    else:
        sid = myridtv_canvas_store.artifact_section_id(conversation_id, stype, "")

    sec = None
    for s in secs:
        if isinstance(s, dict) and str(s.get("id") or "") == sid:
            sec = s
            break
    if sec is None:
        sec = {
            "id": sid,
            "type": stype,
            "title": stitle,
            "order": len(secs),
            "items": [],
            "createdAt": now,
            "updatedAt": now,
        }
        secs.append(sec)

    items = sec.get("items") if isinstance(sec.get("items"), list) else []
    sec["items"] = items
    iid = str(item_id or "").strip() or myridtv_canvas_store.artifact_item_id(sid, item_title)
    # 板块从「一整块文本」升级成「具名条目」时，撤掉之前那个匿名占位条目。
    # 否则 核心人物 会同时挂着 "林澜/司徒岳" 旧块 + 林澜 + 司徒岳 三条。
    if str(item_title or "").strip() and len(items) == 1:
        _only = items[0]
        if (isinstance(_only, dict)
                and not str(_only.get("title") or "").strip()
                and str(_only.get("id") or "").endswith("_main")):
            items = []
            sec["items"] = items
    item = None
    for it in items:
        if isinstance(it, dict) and str(it.get("id") or "") == iid:
            item = it
            break
    if item is None:
        item = {
            "id": iid,
            "title": str(item_title or "").strip(),
            "content": "",
            "order": len(items),
            "metadata": dict(metadata or {}),
            "createdAt": now,
            "updatedAt": now,
        }
        items.append(item)
    item["content"] = str(content or "")
    item["updatedAt"] = now
    if metadata:
        item.setdefault("metadata", {})
        try:
            item["metadata"].update(dict(metadata))
        except Exception:
            item["metadata"] = dict(metadata)
    sec["updatedAt"] = now

    secs.sort(key=lambda s: int(s.get("order") or 0))
    for i, s in enumerate(secs):
        s["order"] = i

    hit["updatedAt"] = now
    hit["version"] = int(hit.get("version") or 1) + 1
    # content 保留一份扁平镜像，供旧前端 / 全文检索兜底读取（不作为 Sidebar 分层来源）
    hit["content"] = _flatten_conversation_content(hit)

    if defer_save:
        return True, aid, True
    save = myridtv_agent_state._agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(str(cid))), canvas, timeout=30)
    save_ok = bool(save.get("ok", save.get("canvas") is not None)) if isinstance(save, dict) else False
    if not save_ok:
        return False, "conversation artifact 保存失败", False
    return True, aid, True


def _flatten_conversation_content(art):
    """把 Conversation 的 Section/Item 拍平成 Markdown 文本（仅作镜像，不参与分层导航）。"""
    parts = []
    for sec in (art.get("sections") or []):
        if not isinstance(sec, dict):
            continue
        parts.append("## " + str(sec.get("title") or "").strip())
        for it in (sec.get("items") or []):
            if not isinstance(it, dict):
                continue
            t = str(it.get("title") or "").strip()
            body = str(it.get("content") or "").strip()
            if t:
                parts.append("### " + t)
            if body:
                parts.append(body)
    return "\n\n".join(parts)


def _agent_upsert_sidebar_artifact(cid, canvas, title="", content="", artifact_type="text",
                                   resource_id="", source_run_id="", source_event_id="",
                                   defer_save=False, conversation_id="", conversation_title="",
                                   section_type="", section_title="", item_title="",
                                   item_id="", metadata=None):
    """Phase 8：Sidebar Artifact 落库（与 _agent_canvas_repo_upsert_node 同构）。

    Phase 9：当传入 conversation_id 且类型属于容器型时，改走
    _agent_upsert_conversation_artifact（分层模式）；否则完全保持 Phase 8 旧行为。
    """
    _conv = str(conversation_id or "").strip()
    _atype = str(artifact_type or "text").strip().lower()
    _has_section = bool(str(section_type or "").strip() or str(section_title or "").strip())
    # Phase 9 兜底：会话内的非文档产物（text/note/script/analysis...）一律归入
    # 会话容器，哪怕 LLM 忘了带 section_title —— 用产物 title 退化成板块名，
    # 绝不退回旧的"每次 uuid 新建平铺条目"。只有独立文档型保持一级条目。
    if _conv and (_atype not in myridtv_canvas_store.INDEPENDENT_DOC_TYPES):
        return _agent_upsert_conversation_artifact(
            cid, canvas, title=title, content=content, artifact_type=_atype,
            conversation_id=_conv, conversation_title=conversation_title,
            section_type=section_type, section_title=section_title,
            item_title=item_title, item_id=item_id,
            resource_id=resource_id, source_run_id=source_run_id,
            source_event_id=source_event_id, defer_save=defer_save, metadata=metadata,
        )
    """Phase 8：Sidebar Artifact 落库（与 _agent_canvas_repo_upsert_node 同构）。

    三条保证：
      - 去重：按 artifactId 合并，同 id -> update 不 append（需求第二十二/二十三条）
      - 失败不留痕：保存失败回滚内存态，绝不留下空 artifact（需求第四十一条）
      - 绑定 canvas：写进 canvas["artifacts"]，天然按 canvasId 隔离（需求第八/二十八条）
    返回 (ok, artifact_id, save_ok)。
    """
    if not cid or not isinstance(canvas, dict):
        return False, "缺少 canvas", False
    now = int(time.time() * 1000)
    aid = "artifact_" + uuid.uuid4().hex[:12]
    art = {
        "id": aid,
        "title": str(title or "").strip() or "未命名产物",
        "artifactType": str(artifact_type or "text").strip().lower(),
        "content": str(content or ""),
        "resourceId": str(resource_id or ""),
        "canvasId": str(cid),
        "sourceRunId": str(source_run_id or ""),
        "sourceEventId": str(source_event_id or ""),
        "canvasNodeId": "",
        "version": 1,
        "createdAt": now,
        "updatedAt": now,
    }
    prev_list = canvas.get("artifacts") if isinstance(canvas.get("artifacts"), list) else []
    canvas["artifacts"] = myridtv_canvas_store._merge_artifacts(prev_list, [art])
    if defer_save:
        # 批量通道：只改内存，由调用方末尾统一落盘（避免 N 次 PUT）
        return True, aid, True
    save = myridtv_agent_state._agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(str(cid))), canvas, timeout=30)
    save_ok = bool(save.get("ok", save.get("canvas") is not None)) if isinstance(save, dict) else False
    if not save_ok:
        canvas["artifacts"] = prev_list
        return False, "artifact 保存失败", False
    return True, aid, True


def _agent_link_artifact_node(cid, canvas, artifact_id, node_id):
    """destination=='both'：把 canvasNodeId 回写进 artifact，
    建立 Artifact <-> Canvas Node 双向引用（需求第十四条）。"""
    if not artifact_id or not node_id or not isinstance(canvas, dict):
        return False
    arts = canvas.get("artifacts") if isinstance(canvas.get("artifacts"), list) else []
    hit = None
    for a in arts:
        if isinstance(a, dict) and str(a.get("id") or "") == str(artifact_id):
            hit = a
            break
    if hit is None:
        return False
    hit["canvasNodeId"] = str(node_id)
    hit["updatedAt"] = int(time.time() * 1000)
    save = myridtv_agent_state._agent_http("PUT", "/api/canvases/{}".format(urllib.parse.quote(str(cid))), canvas, timeout=30)
    return bool(save.get("ok", save.get("canvas") is not None)) if isinstance(save, dict) else False


# ============ 统一批量操作协议（对标 operations 契约，所有 Agent 通道共用） ============
AGENT_OP_TYPES = {"add_node", "update_node", "delete_node", "add_link", "delete_link", "set_variable", "layer_operate"}


