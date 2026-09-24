# -*- coding: utf-8 -*-
"""MyridTV Blender 预演节点域（后端拆分第20刀）：previz 节点布局、媒体项/节点
构建、payload 归一、资产/帧/批次/动画入画布、Blender 连接状态查询。

逐字迁移自 rh_official_proxy.py 连续块 L(next_blender_node_position)..
L(canvas_source_url_for_media_url)（10 函数 286 行，可逆还原行级 diff=0）。
行为零变更。configure() 注入：save_blender_payload_asset 延迟解析闭包（真身
留主，晚于注入点定义）+ APP_BASE getter（write_app_config 会 global 重绑）。
normalize_canvas_structure/smart_canvas_path 属性链直引 myridtv_canvas_store。
主文件对被仍引用的 4 函数留同名薄代理。
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from myridtv_core import (append_log, parse_number, parse_positive_int,
                     read_json_file, write_json_file)

import myridtv_canvas_store
import myridtv_media_localize
import myridtv_media_localize

_r_save_blender_payload_asset = None
_log_file = lambda: None
_app_base_getter = lambda: ""


_G_ASSETS_DIR = None
_G_BLENDER_BIN = None
_G_PREVIZ_DIR = None
_G_PREVIZ_FPS = None
_r_previz_ratio_size = None
_r_strip_llm_fenced_text = None
_r_request_chat_json_with_retry = None
_r_resolve_chat_target = None

def configure(save_blender_payload_asset, app_base_getter, log_file_getter,
              previz_ratio_size, strip_llm_fenced_text,
              request_chat_json_with_retry, resolve_chat_target,
              assets_dir, blender_bin, previz_dir, previz_fps):
    global _r_save_blender_payload_asset, _app_base_getter, _log_file
    _log_file = log_file_getter
    global _G_ASSETS_DIR, _G_BLENDER_BIN, _G_PREVIZ_DIR, _G_PREVIZ_FPS
    global _r_previz_ratio_size
    global _r_strip_llm_fenced_text
    global _r_request_chat_json_with_retry
    global _r_resolve_chat_target
    _r_save_blender_payload_asset = save_blender_payload_asset
    _app_base_getter = app_base_getter
    _r_previz_ratio_size = previz_ratio_size
    _r_strip_llm_fenced_text = strip_llm_fenced_text
    _r_request_chat_json_with_retry = request_chat_json_with_retry
    _r_resolve_chat_target = resolve_chat_target
    _G_ASSETS_DIR = assets_dir
    _G_BLENDER_BIN = blender_bin
    _G_PREVIZ_DIR = previz_dir
    _G_PREVIZ_FPS = previz_fps


def next_blender_node_position(canvas, node_type=None, node_title=None):
    nodes = canvas.get("nodes") or []
    # 排版规则：四区域固定布局
    # 1. 文本列（普通文本/剧本/大纲）：x=0，y 递增（竖排），间距 320px
    # 2. 人物列（角色卡/人物设定）：x=420，y 递增（竖排），间距 320px
    # 3. 资产行（图片生成节点/参考素材）：y=0，x 从 840 递增（横排），间距 420px
    # 4. 视频区（镜头/分镜/视频预览）：x=840，y 从 360 递增，间距 320px

    def is_text_node(node):
        # 普通文本节点：type=smart-prompt 或无类型（兼容旧节点），非人物
        t = node.get("type")
        title = str(node.get("title") or "").lower()
        return (t in ("smart-prompt", None, "")) and not any(k in title for k in ["角色", "人物", "主角", "配角"])

    def is_character_node(node):
        # 人物角色节点：type=smart-prompt 或无类型，标题含角色相关词
        t = node.get("type")
        title = str(node.get("title") or "").lower()
        return (t in ("smart-prompt", None, "")) and any(k in title for k in ["角色", "人物", "主角", "配角"])

    def is_asset_node(node):
        # 资产节点：type=smart-image 或空（图片生成/参考素材）
        t = node.get("type")
        return t in ("smart-image", "", None)

    def is_video_node(node):
        # 视频/镜头节点：标题含视频/镜头/分镜，放在x840 y360开始
        title = str(node.get("title") or "").lower()
        return any(k in title for k in ["视频", "镜头", "分镜", "动画"])

    def node_height(node):
        explicit_h = parse_number(node.get("h"), 0) or 0
        scale = parse_number(node.get("scale"), 2) or 2
        base = explicit_h if explicit_h > 24 else 210 * max(scale, 1)
        return max(base, 210) + 320  # + 间距

    def node_width(node):
        explicit_w = parse_number(node.get("w"), 0) or 0
        scale = parse_number(node.get("scale"), 2) or 2
        base = explicit_w if explicit_w > 24 else 280 * max(scale, 1)
        return max(base, 280) + 420  # + 间距

    # 统计各区域最大位置
    # 文本区域统计
    text_nodes = [n for n in nodes if is_text_node(n)]
    max_y_text = 0
    if text_nodes:
        max_y_text = max((parse_number(n.get("y"), 0) or 0) + node_height(n) for n in text_nodes)

    # 人物区域统计
    char_nodes = [n for n in nodes if is_character_node(n)]
    max_y_char = 0
    if char_nodes:
        max_y_char = max((parse_number(n.get("y"), 0) or 0) + node_height(n) for n in char_nodes)

    # 资产区域统计（不含视频）
    asset_nodes = [n for n in nodes if is_asset_node(n) and not is_video_node(n)]
    max_x_asset = 840 - 420  # 第一个资产从840开始，所以初始是 840 - 间距
    if asset_nodes:
        max_x_asset = max((parse_number(n.get("x"), 0) or 0) + node_width(n) for n in asset_nodes)

    # 视频区域统计
    video_nodes = [n for n in nodes if is_video_node(n)]
    max_y_video = 360 - 320  # 第一个视频从360开始
    if video_nodes:
        max_y_video = max((parse_number(n.get("y"), 0) or 0) + node_height(n) for n in video_nodes)

    # 根据当前节点类型选择位置
    node_t = node_type
    if node_t is None:
        node_t = "smart-image"  # 默认资产
    title_lower = str(node_title).lower()

    if (node_t == "smart-prompt" and not any(k in title_lower for k in ["角色", "人物", "主角", "配角"])):
        # 普通文本：左列 x=0，y递增
        return {"x": 0, "y": round(max_y_text, 3)}
    elif (node_t == "smart-prompt" and any(k in title_lower for k in ["角色", "人物", "主角", "配角"])):
        # 人物角色：中列 x=420，y递增
        return {"x": 420, "y": round(max_y_char, 3)}
    elif (node_t in ("smart-image", "", None) and any(k in title_lower for k in ["视频", "镜头", "分镜", "动画"])):
        # 视频镜头：右列下区 x=840，y从360递增
        return {"x": 840, "y": round(max_y_video, 3)}
    else:
        # 资产/参考图片：右上横排 y=0，x从840递增
        return {"x": round(max_x_asset, 3), "y": 0}

    # 兜底：原逻辑
    image_nodes = [node for node in nodes if isinstance(node, dict) and (node.get("type") in ("smart-image", "", None))]
    anchor = max(
        image_nodes,
        key=lambda node: (
            (parse_number(node.get("x"), 0) or 0) + node_width(node),
            (parse_number(node.get("y"), 0) or 0),
            parse_number(node.get("created_at"), 0) or 0,
        ),
    )
    return {
        "x": round((parse_number(anchor.get("x"), 0) or 0) + node_width(anchor) + 96, 3),
        "y": round((parse_number(anchor.get("y"), 0) or 0), 3),
    }


def build_blender_media_item(saved_asset, payload):
    camera_name = str(payload.get("camera_name") or "").strip()
    title_name = str(payload.get("node_title") or payload.get("title") or "").strip()
    display_name = camera_name or title_name or "Viewport"
    item = {
        "url": saved_asset["url"],
        "name": display_name,
        "kind": saved_asset["kind"],
        "source": "blender",
        "source_file_name": saved_asset["name"],
        "local_path": saved_asset.get("local_path") or "",
    }
    width = parse_positive_int(payload.get("width"))
    height = parse_positive_int(payload.get("height"))
    if width:
        item["natural_w"] = width
    if height:
        item["natural_h"] = height
    return item


def default_blender_node_title(items_payloads, saved_assets, payload):
    custom_title = str(payload.get("batch_title") or payload.get("node_title") or payload.get("title") or "").strip()
    if custom_title:
        return custom_title
    kinds = {str(asset.get("kind") or "image") for asset in saved_assets}
    names = []
    for item in items_payloads:
        name = str(item.get("camera_name") or item.get("node_title") or item.get("title") or "").strip()
        if name and name not in names:
            names.append(name)
    if len(saved_assets) == 1:
        if names:
            return names[0]
        return "动画参考" if "video" in kinds else "Viewport"
    if kinds == {"video"}:
        return "动画组"
    if kinds == {"image"}:
        return "机位组"
    return "媒体组"


def build_blender_node(saved_assets, items_payloads, payload, position):
    now_ms = int(time.time() * 1000)
    primary_item = items_payloads[0] if items_payloads else {}
    camera_names = [str(item.get("camera_name") or "").strip() for item in items_payloads]
    camera_names = [name for name in camera_names if name]
    title = default_blender_node_title(items_payloads, saved_assets, payload)
    meta = {
        "source": "blender",
        "camera_name": camera_names[0] if len(camera_names) == 1 else "",
        "camera_names": camera_names if len(camera_names) > 1 else [],
        "blend_file": str(payload.get("blend_file") or "").strip(),
        "scene_name": str(payload.get("scene_name") or "").strip(),
        "view_layer": str(payload.get("view_layer") or "").strip(),
        "batch_size": len(saved_assets),
        "media_kind": saved_assets[0]["kind"] if len(saved_assets) == 1 else "group",
    }
    frame_value = parse_positive_int(primary_item.get("frame"))
    start_frame = parse_positive_int(primary_item.get("start_frame"))
    end_frame = parse_positive_int(primary_item.get("end_frame"))
    duration_seconds = parse_number(primary_item.get("duration_seconds"))
    if frame_value is not None:
        meta["frame"] = frame_value
    if start_frame is not None:
        meta["start_frame"] = start_frame
    if end_frame is not None:
        meta["end_frame"] = end_frame
    if duration_seconds is not None:
        meta["duration_seconds"] = duration_seconds
    meta = {key: value for key, value in meta.items() if value not in ("", None)}
    images = [build_blender_media_item(saved_asset, item_payload) for saved_asset, item_payload in zip(saved_assets, items_payloads)]
    first_kind = images[0]["kind"] if images else "image"
    scale = 1.4 if len(images) > 1 else 2
    return {
        "id": f"smart_{uuid.uuid4().hex[:12]}",
        "type": "smart-image",
        "x": parse_number(position.get("x"), 180) or 180,
        "y": parse_number(position.get("y"), 180) or 180,
        "title": title,
        "images": images,
        "created_at": now_ms,
        "scale": scale,
        "outputKind": first_kind if len({img.get('kind') for img in images}) == 1 else "image",
        "blender": meta,
    }


def normalize_blender_payload_items(payload):
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return [payload]
    merged_items = []
    for index, raw_item in enumerate(raw_items, 1):
        if not isinstance(raw_item, dict):
            raise RuntimeError(f"items[{index - 1}] 不是对象")
        merged = dict(payload)
        merged.pop("items", None)
        merged.update(raw_item)
        merged_items.append(merged)
    return merged_items


def append_blender_assets_to_canvas(payload):
    canvas_id = str(payload.get("canvas_id") or "").strip()
    path = myridtv_canvas_store.smart_canvas_path(canvas_id)
    if not path.exists():
        raise RuntimeError(f"目标画布不存在: {canvas_id}")
    canvas = myridtv_canvas_store.normalize_canvas_structure(canvas_id, read_json_file(path, {}))
    if canvas.get("deleted_at"):
        raise RuntimeError("目标画布已在回收站中，不能导入")
    items_payloads = normalize_blender_payload_items(payload)
    saved_assets = [_r_save_blender_payload_asset(item_payload) for item_payload in items_payloads]
    # 传递节点类型和标题给位置计算函数
    node_type = payload.get("type")
    node_title = payload.get("title") or payload.get("prompt")
    next_position = next_blender_node_position(canvas, node_type, node_title)
    position = {
        "x": parse_number(payload.get("x"), next_position["x"]),
        "y": parse_number(payload.get("y"), next_position["y"]),
    }
    node = build_blender_node(saved_assets, items_payloads, payload, position)
    canvas["nodes"] = list(canvas.get("nodes") or [])
    canvas["nodes"].append(node)
    canvas["updated_at"] = int(time.time() * 1000)
    write_json_file(path, canvas)
    return {
        "ok": True,
        "canvas_id": canvas_id,
        "canvas_path": str(path),
        "updated_at": canvas["updated_at"],
        "node_id": node["id"],
        "node": node,
        "asset": ({
            **saved_assets[0],
            "app_url": f"{_app_base_getter()}{saved_assets[0]['url']}",
        } if len(saved_assets) == 1 else None),
        "assets": [
            {
                **saved_asset,
                "app_url": f"{_app_base_getter()}{saved_asset['url']}",
            }
            for saved_asset in saved_assets
        ],
    }


def append_blender_frame_to_canvas(payload):
    return append_blender_assets_to_canvas(payload)


def append_blender_batch_to_canvas(payload):
    return append_blender_assets_to_canvas(payload)


def append_blender_animation_to_canvas(payload):
    return append_blender_assets_to_canvas(payload)


def blender_connection_status(canvas_id=""):
    safe_canvas_id = str(canvas_id or "").strip()
    if not safe_canvas_id:
        return {"ok": False, "connected": False, "reason": "missing_canvas_id", "message": "未填写画布 ID"}
    try:
        canvas_path = myridtv_canvas_store.smart_canvas_path(safe_canvas_id)
    except Exception as exc:
        return {"ok": False, "connected": False, "reason": "invalid_canvas_id", "message": str(exc)}
    if not canvas_path.exists():
        return {"ok": False, "connected": False, "reason": "canvas_missing", "message": "目标画布不存在"}
    canvas_data = myridtv_canvas_store.normalize_canvas_structure(safe_canvas_id, read_json_file(canvas_path, {}))
    if canvas_data.get("deleted_at"):
        return {"ok": False, "connected": False, "reason": "canvas_deleted", "message": "目标画布已在回收站"}
    # 连接检查：本服务（3107）能响应请求即视为连接正常（push-animation 由本服务处理）
    # 不再依赖 3000 端口画布 app（用户环境通常只跑 3107 后端 + 桌面应用）
    return {
        "ok": True,
        "connected": True,
        "reason": "connected",
        "message": "连接正常",
        "canvas_id": safe_canvas_id,
        "canvas_title": str(canvas_data.get("title") or "").strip(),
    }

# ===== 第21刀追加：previz LLM 增强与 Blender 执行域 =====
def enhance_previz_prompt_with_llm(prompt, payload):
    """用选定聊天模型把自然语言整理成现有 previz_parse.py 可读的镜头表。
    失败时抛出异常给调用方记录；调用方会回退原提示词，保持旧流程不变。"""
    prompt = str(prompt or "").strip()
    if not prompt:
        return prompt
    llm_provider = str((payload or {}).get("previz_llm_provider") or "").strip()
    llm_model = str((payload or {}).get("previz_llm_model") or "").strip()
    provider_id, model, upstream_base, key = _r_resolve_chat_target({
        "provider": llm_provider,
        "model": llm_model,
        "agent_id": (payload or {}).get("agent_id") or "",
    })
    aspect = str((payload or {}).get("aspectRatio") or "").strip() or "16:9"
    canvas_title = str((payload or {}).get("canvas_title") or "").strip() or "未命名画布"
    system = (
        "你是 MyridTV 的 Blender 3D 预演镜头规划 Agent。"
        "把用户提供的剧情、分镜、参考图描述整理为可执行的 3D 预演数据。"
        "不要解释，不要输出视频生成提示词、参考图提示词、Markdown 表格或代码块；"
        "只按以下顺序输出：\n"
        "3D预演场景资产\n"
        "3D预演镜头表\n"
        "【坐标规则】"
        "Blender 地面为 z=0。x 轴：东(+)/西(-)；y 轴：北(+)/南(-)；z 轴：上(+)。"
        "资产位置是落地中心点；人物位置是脚底点。人物、资产、相机必须处在同一个可见空间内。"
        "全部坐标与尺寸均为米。人物默认身高约 1.7 米；电驱车约 1.9×0.7×1.1 米；普通门洞净高至少 2.1 米；"
        "早餐铺等小型棚架约 3×2×2.5 米；路边立杆设备高度约 2 至 4 米。"
        "只创建镜头看得见、会遮挡、承托人物、形成构图层次或影响走位的资产；画外和相机背后不创建。"
        "普通物体一件只用一个 box；地面由系统创建，无需输出。"
        "镜头看得见的墙面、窗墙、门墙可用 box；门洞用门洞框，棚架用棚架，车辆用电驱车，路边设备用立杆设备。"
        "【资产输出格式】资产 | 名称 | 类型 | [x,y,z] | [宽,深,高] | 颜色 | 镜头用途。"
        "类型只能使用：box、cylinder、sphere、门洞框、棚架、电驱车、立杆设备。"
        "【街道尺度规则】只要镜头可见街道、车辆行驶或人物沿街奔跑，就必须输出一条可见路面资产："
        "资产 | 单向车道 | box | [x,y,0] | [可见长度,3.5,0.04] | 深灰 | Sxx人物走位与车辆行驶承托。"
        "单向机动车道宽固定 3.5 米；道路沿 y 轴时写 [3.5,可见长度,0.04]。"
        "车、人、路边资产都必须落在道路或人行区域内：电驱车宽约 0.7 米，车身中心距车道边至少 0.5 米；"
        "人物横向站位不能与车身重叠。"
        "镜头用途必须写对应镜号及空间职责，例如：S01可见背景墙、S01人物承托、S01前景遮挡、S01前景掠过、S01收束主体。"
        "【前景掠过硬规则】当镜头内容出现“某资产前景掠过”时，该资产用途必须严格写为：Sxx前景掠过。"
        "例如：资产 | 早餐铺棚架 | 棚架 | [3.5,1.0,0] | [2.5,1.5,2.4] | 棕 | S01前景掠过。"
        "这代表它是静止的前景构图资产：系统会在该镜头横移的中段，把它放入相机与主角之间的构图带，由相机经过它产生视差。"
        "不要把它写成背景，不要把它当作移动物体，也不要用“中段：前景掠过与街道纵深”这类文学备注替代用途字段。"
        "【镜头输出格式】镜头 | 镜号 | 时长 | 景别 | 运镜 | 内容 | 人物 | 相机。"
        "镜号固定为 S01、S02……。景别只能使用：特写、近景、中近景、中景、全景、远景、大远景。"
        "人物格式：静止 名称[x,y,z]颜色姿态=站；移动 名称[x,y,z]→[x,y,z]颜色姿态=站；多人用空格分隔。"
        "姿态只能使用：站、坐、躺。坐在有动作车辆上的人物仍只写车辆最终停位的地面坐标，例如 周烬[2.0,0.5,0]红姿态=坐；"
        "不得手填座位高度或绑定字段。只要内容写“跨坐车上/坐在车上/骑在车上”且该车有车辆动作，后端会自动绑定人物并放到座垫锚点。"
        "相机格式：相机[x,y,z]→[目标x,目标y,目标z] 焦距mm。"
        "相机目标必须是主角头部、动作关键点或关键道具；禁止指向场景原点、空墙或无关背景。"
        "主体有走位且镜头有跟拍时，相机目标必须锁定该主体，而不是静止配角。"
        "【构图与镜头节奏】同一连续动作优先设计为一镜到底，用镜头节拍表达动作的起承转合；只有明确的视点或场景变化才切镜。"
        "构图服务动作与情绪：人物朝向或移动方向预留引导空间，给头顶与画面边缘留安全余量；主体可落在三分线附近，不要所有镜头都机械居中。"
        "用户给出“构图起落幅”时，必须原样保留该字段及起幅/落幅方括号内容；不得把两端合并成单一构图描述。"
        "起幅负责交代空间、主体初始落点和初始景别；落幅负责说明结尾停留景别、主体画面位置、视线留白或头顶空间。"
        "多人镜头明确主次与视线关系；连续镜头保持动作方向一致，除非剧情明确要求越轴。运镜平滑且有动机，避免同一镜头堆叠互相冲突的运动。"
        "【运镜与时间规则】保留用户指定的中文运镜名称，不得改写或删减。"
        "内容列末尾必须写镜头节拍：镜头节拍：动作[开始秒-结束秒]；动作[开始秒-结束秒]。"
        "动作只能使用：跟拍、横移、横移加速、横移减速、下压、上升、慢推、环绕、变焦、冲击变焦、固定。"
        "第一段从 0 秒开始，最后一段必须在镜头结束秒结束。"
        "用户输入了百分比节拍模板时，按该镜头时长换算为秒数并保留动作顺序和重叠区间，不可省略。"
        "输出包含构图起落幅时，写成：构图起落幅：起幅[环境建立全景，主体左三分，右侧留白]；落幅[近景，主体右三分，视线左侧留白，头顶留白]。"
        "人物有终点且存在跟拍时，人物从跟拍开始移动，在跟拍结束时到达终点。"
        "【速度与避碰硬规则】坐标单位按米规划。人物写“奔跑/冲出/全力跑”时，走位距离应约为每秒 3 至 5 米；"
        "若镜头先跟拍跑者、后段发生车辆事件，跑者须在车辆动作开始前抵达终点。"
        "写“高速驶入/飞驰/甩尾急停/漂移”的车辆动作时，车辆路径应约为每秒 5 至 8 米，且至少 5.5 米；"
        "车辆从镜头外快速进入时，起点可置于画外，终点仍是镜头内的车辆资产位置。"
        "人物的行走或跑动终点不可落在车辆、墙体、桌子等资产包围盒内；人物在车辆旁收步时，须与车身边缘至少留出 0.8 米。"
        "前景掠过通常与横移时间重叠；例如横移[1-3秒]，系统会在约 2 秒时使前景资产进入画面。"
        "后段冲击变焦、下压或变焦只改变相机，不得让已到终点的人物继续移动。"
        "【空间关系规则】从门洞出来的人物起点必须位于门洞开口范围内。"
        "人物停在车辆、桌子、门前时，人物终点与目标资产的平面距离不超过 1 米。"
        "同一动作相关的角色、车辆、道具必须放在同一区域，不能一个在 y=0、另一个在 y=-3.5。"
        "多人物镜头：主角是相机目标；配角只能作为同画面关系、前景肩部、反应对象或对话对象出现。"
        "车辆有甩尾急停、驶入或漂移时，在内容列镜头节拍后追加："
        "车辆动作：资产名从[x,y,z]→[x,y,z]，朝向=东→南，甩尾急停[开始秒-结束秒]。"
        "车辆动作终点必须等于车辆资产位置；坐车人物必须写在车辆终点附近。车辆的起始朝向必须与从起点到终点的主要移动方向一致；"
        "甩尾急停时结束朝向可与移动方向不同。"
        "【输出示例】\n"
        "3D预演场景资产\n"
        "资产 | 居民楼门洞 | 门洞框 | [-3.0,0.5,0] | [3.0,0.6,2.4] | 灰 | S01起点通道\n"
        "资产 | 早餐铺棚架 | 棚架 | [3.5,1.0,0] | [2.5,1.5,2.4] | 棕 | S01前景掠过\n"
        "资产 | 电驱车 | 电驱车 | [2.0,0.5,0] | [1.9,0.7,1.1] | 深灰 | S01收束主体\n"
        "3D预演镜头表\n"
        "镜头 | S01 | 4秒 | 中景 | 中景跟拍+横移+冲击变焦 | 林野从门洞冲出；早餐铺棚架在前景掠过；林野跑至电驱车旁停住，镜头冲击变焦收在林野。镜头节拍：跟拍[0-3秒]；横移[1-3秒]；冲击变焦[3-4秒]。 | 林野[-2.8,0.5,0]→[1.35,0.5,0]蓝姿态=站 | 相机[-4.5,-1.2,1.0]→[-2.8,0.5,1.5] 35mm\n"
        "不要输出说明、列表符号或代码块。"
    )
    user = (
        f"画布：{canvas_title}\n"
        f"视频比例：{aspect}\n"
        "请把下面内容整理成 1 到 8 个 Blender 预演镜头行。"
        "镜头要有明确主体位置、主体运动、相机位置、目标点和焦距；"
        "自然语言不明确时使用安全默认：人物在地面，场景中心，24fps，单镜头 4 秒，中景，云台感的平稳运动。\n\n"
        f"{prompt}"
    )
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
    }
    data = _r_request_chat_json_with_retry(
        f"{upstream_base}/chat/completions",
        body,
        {"Authorization": f"Bearer {key}"},
        attempts=2,
        timeout=180,
    )
    choices = data.get("choices") if isinstance(data, dict) else []
    message = (choices[0].get("message") if choices and isinstance(choices[0], dict) else {}) or {}
    text = _r_strip_llm_fenced_text(message.get("content") or "")
    lines = []
    shot_count = 0
    for raw_line in text.splitlines():
        line = raw_line.strip().strip()
        if not line or "|" not in line:
            if line.replace(" ", "").rstrip("：:") in {"3D预演场景资产", "3D预演镜头表"}:
                lines.append(line.rstrip("：:"))
            continue
        line = line.strip("|").strip()
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        if re.fullmatch(r"[-:\s|]+", line):
            continue
        if not re.search(r"\d", parts[1] if len(parts) > 1 else ""):
            continue
        is_asset = re.match(r"^资产$", parts[0]) and len(parts) >= 6
        is_shot = re.match(r"^镜头$", parts[0]) and len(parts) >= 7
        is_plain_shot = re.match(r"^(S\d+|镜头\d+|M\d+)", parts[0], re.I)
        if is_asset or is_shot or is_plain_shot:
            lines.append(" | ".join(parts))
            shot_count += 1 if (is_shot or is_plain_shot) else 0
    if not lines or not shot_count:
        raise RuntimeError("LLM 未返回可解析的镜头表")
    enhanced = "\n".join(lines)
    append_log(_log_file(), "previz llm enhanced provider={} model={} chars={} lines={}".format(
        provider_id, model, len(enhanced), len(lines)))
    return enhanced


def run_blender_previz(payload):
    """画布 Blender 预演：镜头表文本(prompt) → previz 三件套 → mp4。
    渲染完成后走插件通道(append_blender_assets)自动建节点回填画布。"""
    import sys  # 顶层未导入 sys，这里局部引入
    canvas_id = str((payload or {}).get("canvas_id") or "").strip()
    canvas_title = str((payload or {}).get("canvas_title") or "").strip()
    prompt = str((payload or {}).get("prompt") or "").strip()
    if not prompt:
        raise RuntimeError("Blender 预演缺少镜头表文本（节点 prompt）")
    llm_enabled = bool((payload or {}).get("previz_llm_enabled"))
    if llm_enabled:
        llm_provider = str((payload or {}).get("previz_llm_provider") or "").strip()
        llm_model = str((payload or {}).get("previz_llm_model") or "").strip()
        append_log(_log_file(), f"previz llm requested provider={llm_provider or '-'} model={llm_model or '-'} prompt_chars={len(prompt)}")
        try:
            original_prompt = prompt
            prompt = enhance_previz_prompt_with_llm(prompt, payload or {})
            append_log(_log_file(), f"previz llm enhanced prompt_chars={len(original_prompt)}->{len(prompt)} changed={prompt != original_prompt}")
        except Exception as exc:
            append_log(_log_file(), f"previz llm enhance failed; fallback original prompt: {exc}")
    else:
        append_log(_log_file(), "previz llm disabled")
    if not canvas_title:
        canvas_title = "未命名画布"
    if not _G_PREVIZ_DIR.exists():
        raise RuntimeError(f"预演脚本目录不存在: {_G_PREVIZ_DIR}")
    width, height = _r_previz_ratio_size(payload.get("aspectRatio"))
    tag = time.strftime("%m%d_%H%M%S")
    # All temporary parse/render data lives outside the asset library and is
    # deleted after a successful task.  Canvas deliverables live together in
    # assets/output/<canvas>/ only.
    work_dir = Path(tempfile.mkdtemp(prefix=f"myridtv_previz_{tag}_"))
    shots_txt = work_dir / "shots.txt"
    shots_txt.write_text(prompt, encoding="utf-8")
    shots_json = work_dir / "shots.json"
    frames_dir = work_dir / "render"
    frames_dir.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    def run_cmd(cmd, timeout=2400):
        append_log(_log_file(), f"previz cmd: {' '.join(str(c) for c in cmd)}")
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env, cwd=str(_G_PREVIZ_DIR))
        out = (proc.stdout or b"").decode("utf-8", errors="replace")
        err = (proc.stderr or b"").decode("utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(
                f"previz 命令失败: {' '.join(str(c) for c in cmd[:6])}...\n{out[-1000:]}\n{err[-1000:]}"
            )
        return out

    # 1) 解析镜头表文本 → previz JSON（不传资产目录 = 基础风格）
    parse_cmd = [py, "-B", str(_G_PREVIZ_DIR / "previz_parse.py"),
                 "--input", str(shots_txt), "--output", str(shots_json),
                 "--width", str(width), "--height", str(height), "--fps", str(_G_PREVIZ_FPS)]
    run_cmd(parse_cmd)
    # 2) Blender Workbench 渲染；最终视频和 .blend 都归档到当前画布资产目录。
    canvas_output_dir = _G_ASSETS_DIR / "output" / canvas_title
    video_dir = canvas_output_dir / "videos"
    blend_dir = canvas_output_dir / "blender"
    video_dir.mkdir(parents=True, exist_ok=True)
    blend_dir.mkdir(parents=True, exist_ok=True)
    data_dir = canvas_output_dir / "previs_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    blend_path = blend_dir / f"previz_{tag}.blend"
    # 预演仅保留正式 Blender 渲染链路：场景资产、中文相机和镜头目标空物体
    # 全部由 previz_render.py 生成。旧 seedance-blocking 解算链路已移除。
    render_cmd = [_G_BLENDER_BIN, "--background", "--python", str(_G_PREVIZ_DIR / "previz_render.py"), "--",
                  "--input", str(shots_json), "--output", str(frames_dir), "--single-scene",
                  "--video-dir", str(frames_dir / "clips"),
                  "--save-blend", str(blend_path)]
    run_cmd(render_cmd, timeout=3600)
    # 3) ffmpeg 拼接成片
    video_name = f"previz_{tag}.mp4"
    video_path = video_dir / video_name
    run_cmd([py, "-B", str(_G_PREVIZ_DIR / "previz_build.py"),
             "--input", str(frames_dir), "--output", str(video_path)],
            timeout=1200)
    if not video_path.exists():
        raise RuntimeError("预演视频未生成")
    size = video_path.stat().st_size
    url = myridtv_media_localize.asset_output_url(video_name, "video", canvas_folder=canvas_title)
    # 镜头表 JSON 是整个链路的唯一事实来源：与可编辑 .blend / MP4 一起归档，
    # 再从同一 JSON 生成 AI 视频提示词，绝不反向从自然语言重新猜镜头。
    data_json_path = data_dir / f"previz_{tag}_镜头数据.json"
    prompt_path = data_dir / f"previz_{tag}_视频提示词.txt"
    validation_path = data_dir / f"previz_{tag}_验镜结果.json"
    shutil.copy2(shots_json, data_json_path)
    run_cmd([py, "-B", str(_G_PREVIZ_DIR / "previz_prompt.py"),
             "--input", str(shots_json), "--output", str(prompt_path)])
    # 读 manifest 拿帧数/时长与验镜结果（Blender 写入）。
    total_frames = 0
    validation = {}
    manifest_file = frames_dir / "manifest.json"
    if manifest_file.exists():
        try:
            mf = json.loads(manifest_file.read_text(encoding="utf-8"))
            total_frames = sum(int(s.get("帧数") or 0) for s in (mf.get("镜头") or []))
            validation = mf.get("验镜") or {}
        except Exception:
            pass
    validation_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    # The final MP4 and editable .blend are the deliverables.  Blender now
    # writes temporary per-shot MP4s directly (not PNG frames); remove them
    # after a successful build so the run directory cannot accumulate renders.
    try:
        shutil.rmtree(work_dir, ignore_errors=True)
    except Exception:
        pass
    duration_seconds = round(total_frames / max(_G_PREVIZ_FPS, 1), 3) if total_frames else 0
    # 自动打开 Blender 工程（GUI）+ 把当前画布 ID 填进 myridtv 插件面板（亮绿灯才能手动推送回传）
    if blend_path.exists():
        try:
            fill_script = _G_PREVIZ_DIR / "open_with_canvas.py"
            subprocess.Popen(
                [_G_BLENDER_BIN, str(blend_path), "--python", str(fill_script), "--",
                 "--canvas-id", canvas_id, "--proxy-url", "http://127.0.0.1:3107"],
                cwd=str(_G_PREVIZ_DIR))
            append_log(_log_file(), f"previz opened blend={blend_path.name} canvas={canvas_id}")
        except Exception as exc:
            append_log(_log_file(), f"previz open blend failed: {exc}")
    # 画布点生成路径：不 append 建节点（避免与前端写回原节点重复 = 双视频节点 bug）
    # 回填统一由前端 finalizeSmartPendingTask 写回原 3D预演 节点
    # 插件手动推送仍走 append_blender_assets（push-animation 路由）
    append_log(_log_file(), f"previz done url={url} size={size} dur={duration_seconds}")
    return {
        "images": [{"url": url, "name": video_name, "kind": "video", "display_name": f"Blender 预演 {tag}"}],
        "backend": "blender-previz",
        "video_url": url,
        "duration_seconds": duration_seconds,
        "previs_data_url": myridtv_media_localize.asset_output_url(data_json_path.name, "file", canvas_folder=f"{canvas_title}/previs_data"),
        "video_prompt_url": myridtv_media_localize.asset_output_url(prompt_path.name, "file", canvas_folder=f"{canvas_title}/previs_data"),
        "validation_url": myridtv_media_localize.asset_output_url(validation_path.name, "file", canvas_folder=f"{canvas_title}/previs_data"),
        "validation": validation,
    }
