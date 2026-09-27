# -*- coding: utf-8 -*-
"""MyridTV 嵌入式 Canvas MCP 域（后端拆分第26刀）：工具 schema 表、画布
缓存/基址、_mcp_canvas_id/_mcp_fetch/_mcp_save 读写器与 _mcp_handle 工具
分发（16 动作：读状态/搜索/建节点走 Artifact Gate 单写点/删除写墓碑/
连接/快照/文本/生成/技能）。

逐字迁移自 rh_official_proxy.py 连续区（3 顶层 + 4 函数，可逆还原行级
diff=0）。行为零变更。MCP_BASE 维持 import 期定值语义（write_app_config
改 PORT 不会传导——与迁移前一致），由主文件算好后 configure 值传。
_agent_batch_build_*/_agent_canvas_repo_upsert_node/_merge_node_tombstones/
_agent_tool_* 属性链直引属主模块（壳穿透）。主文件留 MCP_TOOLS 引用别名与
_mcp_handle 薄代理（Handler 消费点）。
"""
import json
import time
import urllib.parse
import urllib.request
import uuid

import myridtv_agent_artifact
import myridtv_agent_batch
import myridtv_agent_generation
import myridtv_agent_state
import myridtv_agent_tools
import myridtv_canvas_store

MCP_CACHE: dict = {}


def configure(mcp_base):
    global MCP_BASE
    MCP_BASE = mcp_base

# ====== Canvas MCP Tools (嵌入式) ======
MCP_TOOLS = {
    "canvas_list_canvases": {"description": "列出所有画布", "inputSchema": {"type":"object","properties":{}}},
    "canvas_get_state": {"description": "获取画布状态", "inputSchema": {"type":"object","properties":{"canvas_id":{"type":"string"}}}},
    "canvas_get_selection": {"description": "获取选中节点", "inputSchema": {"type":"object","properties":{"canvas_id":{"type":"string"}}}},
    "canvas_search": {"description": "搜索节点", "inputSchema":{"type":"object","properties":{"query":{"type":"string"},"canvas_id":{"type":"string"}},"required":["query"]}},
    "canvas_create_node": {"description": "创建节点", "inputSchema":{"type":"object","properties":{"type":{"type":"string"},"x":{"type":"number"},"y":{"type":"number"},"width":{"type":"number"},"height":{"type":"number"},"content":{"type":"string"},"label":{"type":"string"},"canvas_id":{"type":"string"}},"required":["type","x","y"]}},
    "canvas_delete_node": {"description": "删除节点", "inputSchema":{"type":"object","properties":{"node_id":{"type":"string"},"canvas_id":{"type":"string"}},"required":["node_id"]}},
    "canvas_update_node": {"description": "更新节点", "inputSchema":{"type":"object","properties":{"node_id":{"type":"string"},"content":{"type":"string"},"x":{"type":"number"},"y":{"type":"number"},"width":{"type":"number"},"height":{"type":"number"},"label":{"type":"string"},"canvas_id":{"type":"string"}},"required":["node_id"]}},
    "canvas_connect_nodes": {"description": "连接节点", "inputSchema":{"type":"object","properties":{"from_id":{"type":"string"},"to_id":{"type":"string"},"label":{"type":"string"},"canvas_id":{"type":"string"}},"required":["from_id","to_id"]}},
    "canvas_snapshot": {"description": "保存快照", "inputSchema":{"type":"object","properties":{"canvas_id":{"type":"string"}}}},
    "canvas_create_text_node": {"description": "创建智能画布原生文本节点(剧本/脚本/方案,type=smart-prompt,内容可见可编辑)", "inputSchema":{"type":"object","properties":{"text":{"type":"string"},"title":{"type":"string"},"x":{"type":"number"},"y":{"type":"number"},"canvas_id":{"type":"string"}},"required":["text"]}},
    "canvas_create_generation_node": {"description": "创建图片生成节点(把提示词同步到画布,type=smart-image,待生成)", "inputSchema":{"type":"object","properties":{"prompt":{"type":"string"},"title":{"type":"string"},"model":{"type":"string"},"size":{"type":"string"},"canvas_id":{"type":"string"}},"required":["prompt"]}},
    "canvas_generate_images": {"description": "提交图片生成任务并回填画布节点(异步)。调用后立即返回 task_id 即提交成功,不要等待、不要轮询;生成完成后图片会自动回填到画布节点,之后用 canvas_get_state 或 canvas_check_generation 查看结果。未给 node_id 会自动建生成节点", "inputSchema":{"type":"object","properties":{"prompt":{"type":"string"},"node_id":{"type":"string"},"model":{"type":"string"},"size":{"type":"string"},"reference_image_urls":{"type":"array","items":{"type":"string"}},"canvas_id":{"type":"string"}},"required":["prompt"]}},
    "canvas_analyze_image": {"description": "分析画布图片内容(看图):OCR文字/版面/语义,返回结构化JSON证据(经 ModLens 视觉引擎)", "inputSchema":{"type":"object","properties":{"image_url":{"type":"string"},"node_id":{"type":"string"},"prompt":{"type":"string"},"canvas_id":{"type":"string"}}}},
    "canvas_list_skills": {"description": "列出已保存的技能", "inputSchema":{"type":"object","properties":{}}},
    "canvas_save_skill": {"description": "把方法/工作流保存为可复用技能(@技能名调用)", "inputSchema":{"type":"object","properties":{"name":{"type":"string"},"content":{"type":"string"}},"required":["name","content"]}},
}
MCP_CACHE = {}
# MCP 画布工具直接调用本代理自身（3107）的 API：APP_BASE 指向 proxy.port(3107)
# 的旧前端服务，在纯代理部署下已不可达（502/拒绝连接），画布读写会整体失败。
# MCP_BASE 定义留主文件（值来自 PROXY_CONFIG/PORT，configure 值传）

def _mcp_canvas_id(cid=""):
    if cid: return cid
    try:
        r = urllib.request.Request(f"{MCP_BASE}/api/canvases")
        with urllib.request.urlopen(r, timeout=5) as f:
            d = json.loads(f.read())
        cs = d if isinstance(d, list) else d.get("canvases", [])
        if cs: cs.sort(key=lambda c: c.get("last_modified",0), reverse=True); return str(cs[0].get("id",""))
    except: pass
    return ""

def _mcp_fetch(cid=""):
    cid = _mcp_canvas_id(cid)
    if not cid: return {}, False
    try:
        r = urllib.request.Request(f"{MCP_BASE}/api/canvases/{urllib.parse.quote(cid)}")
        with urllib.request.urlopen(r, timeout=5) as f:
            d = json.loads(f.read())
        # 响应形如 {"ok":true,"canvas":{...}}，解包 canvas 字段供 _mcp_handle 使用
        if isinstance(d, dict) and "canvas" in d: d = d.get("canvas") or {}
        MCP_CACHE["id"]=cid; MCP_CACHE["data"]=d
        return d, True
    except: return {}, False

def _mcp_save(cid, data):
    try:
        body = json.dumps(data).encode()
        r = urllib.request.Request(f"{MCP_BASE}/api/canvases/{urllib.parse.quote(cid)}", data=body, method="PUT", headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(r, timeout=5): return True
    except: return False

def _mcp_handle(name, args):
    cid = args.get("canvas_id","") or MCP_CACHE.get("id","")
    if name == "canvas_list_canvases":
        try:
            r = urllib.request.Request(f"{MCP_BASE}/api/canvases")
            with urllib.request.urlopen(r, timeout=5) as f:
                d = json.loads(f.read())
            cs = d if isinstance(d, list) else d.get("canvases",[])
            return {"result":[{"id":c.get("id"),"title":c.get("title",c.get("name","未命名")),"nodes":c.get("node_count",0)} for c in cs]}
        except Exception as e: return {"error":str(e)}
    cv, ok = _mcp_fetch(cid)
    if not ok: return {"error":"画布获取失败"}
    nodes = cv.get("nodes", cv.get("data",{}).get("nodes",[]))
    edges = cv.get("connections", cv.get("edges", cv.get("data",{}).get("edges",[])))
    cid = MCP_CACHE.get("id","")
    if name == "canvas_get_state":
        return {"result":{"canvas_id":cid,"node_count":len(nodes),"edge_count":len(edges),
            "nodes":[{"id":n.get("id"),"type":n.get("type"),"label":n.get("label",n.get("title","")),"x":n.get("x"),"y":n.get("y")} for n in nodes],"edges":edges}}
    if name == "canvas_get_selection":
        sel = cv.get("data",{}).get("selectedIds",[]); sn = [n for n in nodes if n.get("id") in sel]
        return {"result":{"selected_ids":sel,"nodes":sn}}
    if name == "canvas_search":
        q = args.get("query","").lower()
        mt = [n for n in nodes if q in str(n.get("label",n.get("title",""))).lower() or q in str(n.get("content","")).lower()]
        return {"result":{"query":q,"matches":len(mt),"nodes":mt}}
    if name == "canvas_create_node":
        # Phase 3：统一走 _agent_batch_build_* + Artifact Gate，废除 hm_ schema（与 Agent 通道共用单写点）
        node_type = str(args.get("type", "text")).strip().lower()
        params = {
            "canvas_id": cid,
            "type": node_type,
            "title": str(args.get("label") or args.get("title") or "MCP 节点").strip(),
            "text": str(args.get("content") or "").strip(),
            "prompt": str(args.get("content") or "").strip(),
            "x": args.get("x"),
            "y": args.get("y"),
        }
        try:
            if node_type in ("generation", "image", "smart-image", "gen"):
                node, ref_ids = myridtv_agent_batch._agent_batch_build_generation_node(cv, params, None)
            else:
                node = myridtv_agent_batch._agent_batch_build_text_node(cv, params)
        except ValueError as ve:
            return {"error": "参数不完整: {}".format(ve)}
        if args.get("width"):
            try: node["w"] = int(args["width"])
            except Exception: pass
        if args.get("height"):
            try: node["h"] = int(args["height"])
            except Exception: pass
        ok, nid, save_ok, deduped = myridtv_agent_artifact._agent_canvas_repo_upsert_node(cid, cv, node, "mcp", args)
        if not ok:
            return {"error": nid}
        return {"result": {"node_id": nid, "type": node["type"], "origin": "mcp", "deduped": deduped}}
    if name == "canvas_delete_node":
        nid = str(args.get("node_id", "") or "").strip()
        d = cv.get("data", cv)
        d["nodes"] = [n for n in d.get("nodes", []) if n.get("id") != nid]
        d["edges"] = [e for e in d.get("edges", []) if e.get("from", e.get("source")) != nid and e.get("to", e.get("target")) != nid]
        if isinstance(d.get("connections"), list):
            d["connections"] = [c for c in d["connections"] if c.get("from") != nid and c.get("to") != nid]
        # Phase 4：与 REST/Agent 通道一致写墓碑
        d["deleted"] = myridtv_canvas_store._merge_node_tombstones(d.get("deleted"), [{"id": nid, "at": int(time.time() * 1000), "by": "mcp"}])
        _mcp_save(cid, d)
        return {"result": {"deleted": nid, "tombstoned": True}}
    if name == "canvas_update_node":
        nid = args.get("node_id",""); d = cv.get("data",cv)
        for n in d.get("nodes",[]):
            if n.get("id")==nid:
                for k in ("content","x","y","width","height","label"):
                    if k in args: n[k]=args[k]
                break
        _mcp_save(cid,d); return {"result":{"node_id":nid}}
    if name == "canvas_connect_nodes":
        eid = f"e_{uuid.uuid4().hex[:8]}"; d = cv.get("data",cv)
        el = d.get("edges",[]); el.append({"id":eid,"from":args["from_id"],"to":args["to_id"],"label":args.get("label","")})
        d["edges"]=el; _mcp_save(cid,d); return {"result":{"edge_id":eid}}
    if name == "canvas_snapshot":
        d = cv.get("data",cv); d["snapshot_at"]=time.time(); _mcp_save(cid,d)
        return {"result":{"canvas_id":cid}}
    if name == "canvas_create_text_node":
        return myridtv_agent_state._agent_tool_create_text_node(args)
    if name == "canvas_create_generation_node":
        return myridtv_agent_generation._agent_tool_create_generation_node(args, None)
    if name == "canvas_generate_images":
        return myridtv_agent_generation._agent_tool_generate_images(args, None)
    if name == "canvas_analyze_image":
        return myridtv_agent_tools._agent_tool_analyze_image(args)
    if name == "canvas_list_skills":
        return myridtv_agent_tools._agent_tool_list_skills(args)
    if name == "canvas_save_skill":
        return myridtv_agent_tools._agent_tool_save_skill(args)
    return {"error":f"unknown tool: {name}"}
