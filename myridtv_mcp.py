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
import myridtv_media_localize


def configure(mcp_base):
    global MCP_BASE
    MCP_BASE = mcp_base

# ====== Canvas MCP Tools (嵌入式) ======
MCP_TOOLS = {
    "canvas_list_canvases": {"description": "列出所有画布", "inputSchema": {"type":"object","properties":{}}},
    "canvas_create": {"description": "新建画布（与界面人工新建走同一条 POST /api/canvases 链路，title 可空自动命名），返回 canvas_id 并自动成为当前画布", "inputSchema": {"type":"object","properties":{"title":{"type":"string"},"kind":{"type":"string"},"icon":{"type":"string"},"color":{"type":"string"},"owner":{"type":"string"}}}},
    "canvas_get_state": {"description": "获取画布状态", "inputSchema": {"type":"object","properties":{"canvas_id":{"type":"string"}}}},
    "canvas_get_selection": {"description": "获取选中节点", "inputSchema": {"type":"object","properties":{"canvas_id":{"type":"string"}}}},
    "canvas_search": {"description": "搜索节点", "inputSchema":{"type":"object","properties":{"query":{"type":"string"},"canvas_id":{"type":"string"}},"required":["query"]}},
    "canvas_create_node": {"description": "创建节点（与画布 Agent/人工同一落库链路）。type 取 text(文本/剧本，内容字段 text 或 content) | generation(图片生成节点，内容字段 prompt 或 content)；x/y 可不传=自动空位排列（按类别分列不重叠）。generation 可带生图参数族：provider_id/model/size/aspect_ratio(16:9、1:1、9:16、3:4、4:3、2:3、3:2、21:9)/resolution(1k/2k/4k)/quality(low/medium/high)/count(张数)/reference_image_urls(参考图url数组)", "inputSchema":{"type":"object","properties":{"type":{"type":"string","enum":["text","generation"]},"text":{"type":"string"},"prompt":{"type":"string"},"content":{"type":"string"},"title":{"type":"string"},"label":{"type":"string"},"x":{"type":"number"},"y":{"type":"number"},"width":{"type":"number"},"height":{"type":"number"},"provider_id":{"type":"string"},"model":{"type":"string"},"size":{"type":"string"},"aspect_ratio":{"type":"string"},"resolution":{"type":"string"},"quality":{"type":"string"},"count":{"type":"integer"},"reference_image_urls":{"type":"array","items":{"type":"string"}},"canvas_id":{"type":"string"}},"required":["type"]}},
    "canvas_delete_node": {"description": "删除节点", "inputSchema":{"type":"object","properties":{"node_id":{"type":"string"},"canvas_id":{"type":"string"}},"required":["node_id"]}},
    "canvas_update_node": {"description": "更新节点（与人工编辑同字段族：text/content/prompt 任一即改正文，同步 promptDraft/runPrompt；尺寸 w/h）。生成节点可改运行参数（只覆盖传入的键）：provider_id/model/size/aspect_ratio(16:9、1:1、9:16、3:4、4:3、2:3、3:2、21:9)/resolution(1k/2k/4k)/quality(low/medium/high)/count(张数)。挂图：images=url数组(替换节点全部图) 或 add_images=url数组(追加)；来源支持 /assets/ 本服务路径、data:URI、http(s)、file://、Windows盘符路径——后两类自动落盘成画布素材", "inputSchema":{"type":"object","properties":{"node_id":{"type":"string"},"text":{"type":"string"},"content":{"type":"string"},"prompt":{"type":"string"},"title":{"type":"string"},"label":{"type":"string"},"x":{"type":"number"},"y":{"type":"number"},"w":{"type":"number"},"h":{"type":"number"},"provider_id":{"type":"string"},"model":{"type":"string"},"size":{"type":"string"},"aspect_ratio":{"type":"string"},"resolution":{"type":"string"},"quality":{"type":"string"},"count":{"type":"integer"},"images":{"type":"array","items":{"type":"string"}},"add_images":{"type":"array","items":{"type":"string"}},"canvas_id":{"type":"string"}},"required":["node_id"]}},
    "canvas_connect_nodes": {"description": "连接节点（写入画布 connections，与人工/Agent 连线同一字段族）。kind 默认 input（接参考图/输入，同步目标节点 inputNodeIds）；可选 flow（普通流程线）。两端节点必须已存在，重复连线自动去重", "inputSchema":{"type":"object","properties":{"from_id":{"type":"string"},"to_id":{"type":"string"},"kind":{"type":"string","enum":["input","flow"]},"label":{"type":"string"},"canvas_id":{"type":"string"}},"required":["from_id","to_id"]}},
    "canvas_disconnect_nodes": {"description": "断开节点连线（canvas_connect_nodes 的逆操作：从画布 connections 摘除连线，kind=input 的同步回收目标节点 inputNodeIds）。from_id+to_id 都给=只拆这一条；只给 from_id=拆该节点全部出边，只给 to_id=拆全部入边（要拆某节点全部连线就两端各调一次）；kind 省略=不限类型全拆，kind=input/flow 只拆该类。没有匹配连线时幂等返回 count=0（不报错）", "inputSchema": {"type":"object","properties":{"from_id":{"type":"string"},"to_id":{"type":"string"},"kind":{"type":"string","enum":["input","flow"]},"canvas_id":{"type":"string"}}}},
    "canvas_snapshot": {"description": "保存快照", "inputSchema":{"type":"object","properties":{"canvas_id":{"type":"string"}}}},
    "canvas_create_text_node": {"description": "创建智能画布原生文本节点(剧本/脚本/方案,type=smart-prompt,内容可见可编辑)。x/y 可省=自动空位", "inputSchema":{"type":"object","properties":{"text":{"type":"string"},"title":{"type":"string"},"x":{"type":"number"},"y":{"type":"number"},"canvas_id":{"type":"string"}},"required":["text"]}},
    "canvas_create_generation_node": {"description": "创建图片生成节点(把提示词同步到画布,type=smart-image,待生成)。x/y 可省=自动空位。可选生图参数族：provider_id/model/size/aspect_ratio(16:9、1:1、9:16、3:4、4:3、2:3、3:2、21:9)/resolution(1k/2k/4k)/quality(low/medium/high)/count(张数)/reference_image_urls(参考图url数组，自动建输入连线)", "inputSchema":{"type":"object","properties":{"prompt":{"type":"string"},"title":{"type":"string"},"model":{"type":"string"},"size":{"type":"string"},"aspect_ratio":{"type":"string"},"resolution":{"type":"string"},"quality":{"type":"string"},"count":{"type":"integer"},"reference_image_urls":{"type":"array","items":{"type":"string"}},"x":{"type":"number"},"y":{"type":"number"},"canvas_id":{"type":"string"}},"required":["prompt"]}},
    "canvas_create_video_node": {"description": "创建视频生成节点(把提示词同步到画布,type=smart-image,outputKind=video,待生成/可并行提交)。x/y 可省=自动空位。可选视频参数族：model(火山视频模型,如 seedance-1-5-pro)/duration(秒,4-15)/video_aspect(16:9、9:16、1:1、21:9)/video_resolution(480p/720p/1080p/4k)/generate_audio(生成配音)/watermark/enhance_prompt/reference_image_urls(参考图)/reference_videos(参考视频)。submit=true 时创建后立即并行提交视频生成任务(异步返回 task_id,结果自动回填节点)", "inputSchema":{"type":"object","properties":{"prompt":{"type":"string"},"title":{"type":"string"},"model":{"type":"string"},"video_model":{"type":"string"},"provider_id":{"type":"string"},"duration":{"type":"integer"},"video_aspect":{"type":"string"},"video_resolution":{"type":"string"},"generate_audio":{"type":"boolean"},"watermark":{"type":"boolean"},"enhance_prompt":{"type":"boolean"},"count":{"type":"integer"},"reference_image_urls":{"type":"array","items":{"type":"string"}},"reference_videos":{"type":"array","items":{"type":"string"}},"submit":{"type":"boolean"},"x":{"type":"number"},"y":{"type":"number"},"canvas_id":{"type":"string"}},"required":["prompt"]}},
    "canvas_generate_images": {"description": "提交图片生成任务并回填画布节点(异步)。调用后立即返回 task_id 即提交成功,不要等待、不要轮询;生成完成后图片会自动回填到画布节点,之后用 canvas_get_state 或 canvas_check_generation 查看结果。未给 node_id 会自动建生成节点", "inputSchema":{"type":"object","properties":{"prompt":{"type":"string"},"node_id":{"type":"string"},"model":{"type":"string"},"size":{"type":"string"},"reference_image_urls":{"type":"array","items":{"type":"string"}},"canvas_id":{"type":"string"}},"required":["prompt"]}},
    "canvas_analyze_image": {"description": "分析画布图片内容(看图):OCR文字/版面/语义,返回结构化JSON证据(经 ModLens 视觉引擎)", "inputSchema":{"type":"object","properties":{"image_url":{"type":"string"},"node_id":{"type":"string"},"prompt":{"type":"string"},"canvas_id":{"type":"string"}}}},
    "canvas_list_skills": {"description": "列出已保存的技能", "inputSchema":{"type":"object","properties":{}}},
    "canvas_save_skill": {"description": "把方法/工作流保存为可复用技能(@技能名调用)", "inputSchema":{"type":"object","properties":{"name":{"type":"string"},"content":{"type":"string"}},"required":["name","content"]}},
}
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
        if cs: cs.sort(key=lambda c: c.get("updated_at", c.get("last_modified", 0)), reverse=True); return str(cs[0].get("id",""))
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
        from myridtv_canvas_gateway import enroll_existing
        enroll_existing(cid,d)
        # Target identity stays local to this request.
        return d, True
    except: return {}, False

def _mcp_save(cid, data):
    try:
        body = json.dumps(data).encode()
        r = urllib.request.Request(f"{MCP_BASE}/api/canvases/{urllib.parse.quote(cid)}", data=body, method="PUT", headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(r, timeout=5): return True
    except: return False

# ====== 挂图（2026-10-09）：混合来源图片引用 → 画布规范 img 对象 ======
# 本服务路径(/assets/ /static/ /output/)直接引用；data:URI / http(s) / file:// /
# Windows 盘符路径 → save_generated_remote_asset 落盘成画布素材（与人工上传同目录同命名口径）。
_MCP_ATTACH_LOCAL_PREFIXES = ("/assets/", "/static/", "/output/")

def _mcp_attach_image_items(urls, cid="", canvas_title=""):
    items = []
    for u in (urls or []):
        u = str(u or "").strip()
        if not u: continue
        if u.startswith(_MCP_ATTACH_LOCAL_PREFIXES):
            name = urllib.parse.unquote(u.split("?")[0].rstrip("/").rsplit("/", 1)[-1]) or "image"
            items.append({"url": u, "name": name})
            continue
        try:
            saved = myridtv_media_localize.save_generated_remote_asset(u, "image", canvas_title=canvas_title, canvas_id=cid)
        except Exception:
            continue
        if saved and saved.get("url"):
            items.append({"url": str(saved["url"]), "name": str(saved.get("name") or "")})
    return items

def _mcp_handle(name, args):
    cid = str(args.get("canvas_id", "") or "").strip()
    if name == "canvas_list_canvases":
        try:
            r = urllib.request.Request(f"{MCP_BASE}/api/canvases")
            with urllib.request.urlopen(r, timeout=5) as f:
                d = json.loads(f.read())
            cs = d if isinstance(d, list) else d.get("canvases",[])
            return {"result":[{"id":c.get("id"),"title":c.get("title",c.get("name","未命名")),"nodes":c.get("node_count",0)} for c in cs]}
        except Exception as e: return {"error":str(e)}
    if name == "canvas_create":
        # 与界面人工新建同链路：POST /api/canvases -> create_canvas_record（字段规范化、id 生成、kind 默认全部后端把关）
        body = json.dumps({
            "title": str(args.get("title") or "").strip(),
            "kind": str(args.get("kind") or "").strip() or "smart",
            "icon": str(args.get("icon") or "").strip(),
            "color": str(args.get("color") or "").strip(),
            "owner": str(args.get("owner") or "").strip(),
        }).encode()
        try:
            r = urllib.request.Request(f"{MCP_BASE}/api/canvases", data=body, method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=10) as f:
                d = json.loads(f.read())
            canvas = d.get("canvas") or {}
            new_id = str(canvas.get("id") or "").strip()
            # Return an explicit target; never change another caller's context.
            return {"result": {"canvas_id": new_id, "title": canvas.get("title", ""), "kind": canvas.get("kind", "")}}
        except Exception as e:
            return {"error": str(e)}
    cv, ok = _mcp_fetch(cid)
    if not ok: return {"error":"画布获取失败"}

    if args.get("expected_updated_at") is not None and args["expected_updated_at"] != cv.get("updated_at"):
        return {"error": "画布已被修改，请重新读取后重试", "error_code": "conflict", "current_updated_at": cv.get("updated_at")}
    nodes = cv.get("nodes", cv.get("data",{}).get("nodes",[]))
    edges = cv.get("connections", cv.get("edges", cv.get("data",{}).get("edges",[])))
    cid = str(cv.get("id") or cid)
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
        # 内容字段互为别名：content/text/prompt 任一即可（与人工逻辑同字段族）
        body_text = str(args.get("text") or args.get("content") or args.get("prompt") or "").strip()
        params = {
            "canvas_id": cid,
            "type": node_type,
            "title": str(args.get("label") or args.get("title") or "MCP 节点").strip(),
            "text": body_text,
            "prompt": body_text,
            "x": args.get("x"),
            "y": args.get("y"),
            "provider_id": str(args.get("provider_id") or "").strip(),
            "model": str(args.get("model") or "").strip(),
            "size": str(args.get("size") or "").strip(),
            # 2026-10-09 放行：内部链路 _agent_default_run_settings 本就支持这五个参数，
            # 此前 MCP 入口白名单漏放，传了被静默丢弃
            "aspect_ratio": str(args.get("aspect_ratio") or args.get("aspectRatio") or "").strip(),
            "resolution": str(args.get("resolution") or "").strip(),
            "quality": str(args.get("quality") or "").strip(),
            "count": args.get("count"),
            "reference_image_urls": args.get("reference_image_urls") or args.get("reference_images") or [],
        }
        try:
            if node_type in ("generation", "image", "smart-image", "gen"):
                node, ref_ids = myridtv_agent_batch._agent_batch_build_generation_node(cv, params, None)
            elif node_type in ("text", "smart-prompt", "prompt", "script"):
                node = myridtv_agent_batch._agent_batch_build_text_node(cv, params)
            else:
                return {"error": "type 仅支持 text 或 generation（收到: {}）".format(node_type)}
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
        if not save_ok:
            return {"error": "画布保存失败或发生并发冲突，请重新读取后重试"}
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
        if not _mcp_save(cid, d):
            return {"error": "删除未保存：画布保存失败或发生并发冲突"}
        return {"result": {"deleted": nid, "tombstoned": True}}
    if name == "canvas_update_node":
        nid = str(args.get("node_id","")).strip(); d = cv.get("data",cv)
        hit = next((n for n in d.get("nodes",[]) if isinstance(n,dict) and n.get("id")==nid), None)
        if not hit: return {"error":"节点不存在: {}".format(nid)}
        # 与人工编辑同一字段族：文本节点前端读 text/promptDraftText/promptDraftHtml，
        # 生成节点读 runPrompt/promptDraftText；尺寸键是 w/h（不是 width/height）。
        body = next((args[k] for k in ("text", "content", "prompt") if k in args), None)
        if body is not None:
            body = str(body)
            hit["text"]=body; hit["content"]=body
            hit["promptDraftText"]=body
            hit["promptDraftHtml"]=myridtv_agent_state._agent_html_escape(body)
            hit["promptDraftTouched"]=True
            if str(hit.get("type") or "")=="smart-image": hit["runPrompt"]=body
        title = args.get("title") or args.get("label")
        if title: hit["title"]=str(title).strip()
        if "x" in args: hit["x"]=args["x"]
        if "y" in args: hit["y"]=args["y"]
        wv = args.get("w") if "w" in args else args.get("width")
        hv = args.get("h") if "h" in args else args.get("height")
        if wv is not None:
            try: hit["w"]=int(wv)
            except Exception: pass
        if hv is not None:
            try: hit["h"]=int(hv)
            except Exception: pass
        # 运行参数族（2026-10-09）：只 patch 传入的键，字段名对齐 _agent_run_settings_for_storage
        # （前端 settingsForStorage 同构：ratio 是枚举键、count 是张数），未传的键原样保留
        _RS_KEYS = ("provider_id", "model", "size", "aspect_ratio", "aspectRatio", "resolution", "quality", "count")
        if any(args.get(k) is not None for k in _RS_KEYS):
            rs = hit.get("runSettings") if isinstance(hit.get("runSettings"), dict) else None
            if rs is None:
                rs = myridtv_agent_state._agent_run_settings_for_storage({})
                hit["runSettings"] = rs
            if args.get("provider_id"): rs["provider_id"] = str(args["provider_id"]).strip()
            if args.get("model"): rs["model"] = str(args["model"]).strip()
            if args.get("size"): rs["size"] = str(args["size"]).strip()
            _ar = str(args.get("aspect_ratio") or args.get("aspectRatio") or "").strip()
            if _ar: rs["ratio"] = myridtv_agent_state._agent_ratio_key(_ar)
            if args.get("resolution"): rs["resolution"] = str(args["resolution"]).strip()
            if args.get("quality"): rs["quality"] = str(args["quality"]).strip()
            if args.get("count") is not None:
                try: rs["count"] = max(1, int(args["count"]))
                except Exception: pass
        # 挂图（2026-10-09）：images=替换整组，add_images=追加；本地/远程来源统一规范化
        if isinstance(args.get("images"), list) or isinstance(args.get("add_images"), list):
            _cv_title = str(d.get("title") or cv.get("title") or "").strip()
            _items = []
            if isinstance(args.get("images"), list):
                _items = _mcp_attach_image_items(args.get("images"), cid, _cv_title)
            if isinstance(args.get("add_images"), list):
                _cur = hit.get("images") if isinstance(hit.get("images"), list) else []
                _items = _cur + _mcp_attach_image_items(args.get("add_images"), cid, _cv_title)
            # 单图节点规则（2026-10-19 老王定案，见 AGENTS.md「Single-image Nodes」）：
            # 一个节点最多一张图，多出来的图各自落成独立节点。
            if len(_items) > 1:
                hit["images"] = _items[:1]
                myridtv_agent_generation.spawn_single_image_nodes(cid, d, hit, _items[1:], origin="mcp_image_split")
            else:
                hit["images"] = _items
        ok, _nid, save_ok, _dd = myridtv_agent_artifact._agent_canvas_repo_upsert_node(cid, cv, hit, "mcp_update", args)
        if not ok: return {"error": _nid}
        if not save_ok: return {"error": "更新未保存：画布保存失败或发生并发冲突"}
        return {"result":{"node_id":nid,"updated":True,"save_ok":save_ok}}
    if name == "canvas_connect_nodes":
        # 2026-10-09 修：此前写 d["edges"]，而画布真实连线字段是 connections -> 落盘即被
        # save_canvas_record 丢弃（前端/normalize 都不认 edges），却谎报 edge_id 成功。
        # 对齐前端 addConnection/connectInputNode 与 Agent 通道口径：connections 追加
        # {from,to,kind}，kind=input（默认，接参考图给生成用）时同步 to.inputNodeIds。
        fid = str(args.get("from_id","")).strip(); tid = str(args.get("to_id","")).strip()
        if not fid or not tid: return {"error":"from_id/to_id 必填"}
        if fid == tid: return {"error":"不能连接节点自身"}
        d = cv.get("data", cv)
        node_ids = {str(n.get("id") or "") for n in (d.get("nodes") or []) if isinstance(n, dict)}
        missing = [x for x in (fid, tid) if x not in node_ids]
        if missing: return {"error":"节点不存在: {}".format(",".join(missing))}
        kind = str(args.get("kind") or "input").strip() or "input"
        conns = d.get("connections") if isinstance(d.get("connections"), list) else []
        if any(c.get("from") == fid and c.get("to") == tid and (c.get("kind") or "flow") == kind for c in conns):
            return {"result":{"edge_id":"{}->{}:{}".format(fid, tid, kind), "from":fid, "to":tid, "kind":kind, "deduped":True}}
        entry = {"from":fid, "to":tid, "kind":kind}
        label = str(args.get("label") or "").strip()
        if label: entry["label"] = label
        conns.append(entry); d["connections"] = conns
        if kind == "input":
            to_node = next((n for n in (d.get("nodes") or []) if isinstance(n, dict) and n.get("id") == tid), None)
            if to_node is not None:
                ins = to_node.get("inputNodeIds") if isinstance(to_node.get("inputNodeIds"), list) else []
                if fid not in ins: ins.append(fid)
                to_node["inputNodeIds"] = ins
        if not _mcp_save(cid, d): return {"error":"画布保存失败"}
        return {"result":{"edge_id":"{}->{}:{}".format(fid, tid, kind), "from":fid, "to":tid, "kind":kind, "deduped":False}}
    if name == "canvas_disconnect_nodes":
        # 2026-10-10 新增：此前只有 connect，Agent 想拆连线只能删节点重建。
        # 与 canvas_connect_nodes 严格对称：字段族是 connections（不是 edges，edges 落盘会被
        # save_canvas_record 丢弃），kind=input 的连线同步回收目标节点 inputNodeIds。
        fid = str(args.get("from_id","")).strip(); tid = str(args.get("to_id","")).strip()
        if not fid and not tid: return {"error":"from_id / to_id 至少给一个"}
        d = cv.get("data", cv)
        node_ids = {str(n.get("id") or "") for n in (d.get("nodes") or []) if isinstance(n, dict)}
        missing = [x for x in (fid, tid) if x and x not in node_ids]
        if missing: return {"error":"节点不存在: {}".format(",".join(missing))}
        kind = str(args.get("kind") or "").strip()
        conns = d.get("connections") if isinstance(d.get("connections"), list) else []
        keep, removed = [], []
        for c in conns:
            if not isinstance(c, dict): continue
            cf = str(c.get("from") or ""); ct = str(c.get("to") or ""); ck = str(c.get("kind") or "flow")
            hit = (not fid or cf == fid) and (not tid or ct == tid) and (not kind or ck == kind)
            if hit: removed.append((cf, ct, ck))
            else: keep.append(c)
        if not removed:
            return {"result":{"removed":[], "count":0, "already_absent":True, "from":fid, "to":tid}}
        d["connections"] = keep
        # 回收 inputNodeIds：被拆掉的 kind=input 连线，其 from 应从 to 节点的输入列表里摘掉
        touched = set()
        for cf, ct, ck in removed:
            if ck != "input": continue
            tn = next((n for n in (d.get("nodes") or []) if isinstance(n, dict) and str(n.get("id") or "") == ct), None)
            if tn is None: continue
            ins = tn.get("inputNodeIds") if isinstance(tn.get("inputNodeIds"), list) else []
            if cf in ins:
                tn["inputNodeIds"] = [x for x in ins if x != cf]
                touched.add(ct)
        if not _mcp_save(cid, d): return {"error":"断连未保存：画布保存失败或发生并发冲突"}
        return {"result":{"removed":["{}->{}:{}".format(f,t,k) for f,t,k in removed], "count":len(removed), \
                          "from":fid, "to":tid, "kind":kind or "*", "input_node_ids_updated":sorted(touched)}}
    if name == "canvas_snapshot":
        d = cv.get("data",cv); d["snapshot_at"]=time.time()
        if not _mcp_save(cid,d): return {"error":"快照未保存：画布保存失败或发生并发冲突"}
        return {"result":{"canvas_id":cid}}
    if name == "canvas_create_text_node":
        return myridtv_agent_state._agent_tool_create_text_node(args)
    if name == "canvas_create_generation_node":
        return myridtv_agent_generation._agent_tool_create_generation_node(args, None)
    if name == "canvas_create_video_node":
        return myridtv_agent_generation._agent_tool_create_video_node(args, None)

    if name == "canvas_generate_images":
        return myridtv_agent_generation._agent_tool_generate_images(args, None)
    if name == "canvas_analyze_image":
        return myridtv_agent_tools._agent_tool_analyze_image(args)
    if name == "canvas_list_skills":
        return myridtv_agent_tools._agent_tool_list_skills(args)
    if name == "canvas_save_skill":
        return myridtv_agent_tools._agent_tool_save_skill(args)
    return {"error":f"unknown tool: {name}"}


# Preserve established node builders/Gate, with one external-agent contract.
from myridtv_mcp_contract import install as _install_mcp_contract
_mcp_handle = _install_mcp_contract(MCP_TOOLS, _mcp_handle, _mcp_fetch)
