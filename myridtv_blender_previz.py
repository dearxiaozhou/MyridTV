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
import time
import uuid

from myridtv_core import parse_number, parse_positive_int, read_json_file, write_json_file

import myridtv_canvas_store

_r_save_blender_payload_asset = None
_app_base_getter = lambda: ""


def configure(save_blender_payload_asset, app_base_getter):
    global _r_save_blender_payload_asset, _app_base_getter
    _r_save_blender_payload_asset = save_blender_payload_asset
    _app_base_getter = app_base_getter


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


