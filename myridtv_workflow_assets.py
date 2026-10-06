# -*- coding: utf-8 -*-
"""workflow 记录 + blender 资产落盘域（第31刀自 rh_official_proxy.py 逐字外移）：
workflow 记录创建/保存/删除、路由解析、素材名/类型工具、
blender payload 解码落盘。LOG_FILE 走 getter；ROOT/ASSETS_DIR 统一 getter 处方。"""
from pathlib import Path
import json
import re
import time
import base64
import mimetypes
import urllib.parse
import uuid
import myridtv_canvas_store
import myridtv_comfy
import myridtv_core
import myridtv_libraries
import myridtv_media_localize
from myridtv_core import ApiError

_G_LOG_FILE = lambda: None
_G_ROOT = lambda: None
_G_ASSETS_DIR = lambda: None
_G_CANVAS_DIR = lambda: None


def configure(getters):
    global _G_LOG_FILE, _G_ROOT, _G_ASSETS_DIR, _G_CANVAS_DIR
    _G_LOG_FILE = getters['LOG_FILE']
    _G_ROOT = getters['ROOT']
    _G_ASSETS_DIR = getters['ASSETS_DIR']
    # 重命名工作流时要连带改写画布里的引用，故需知道画布目录（旧调用无此键则安全降级）
    _G_CANVAS_DIR = getters.get('CANVAS_DIR', lambda: None)


def create_workflow_record(name, workflow):
    file_name, _ = myridtv_libraries.workflow_file_candidates(name)
    workflow_path = _G_ROOT() / "workflows" / "custom" / file_name
    if workflow_path.exists():
        raise ApiError(409, f"工作流已存在: {file_name}")

    # 多管线集合导入：一个 json 文件里装了几条互不重叠的生成管线时，
    # 自动拆成 N 个独立工作流注册成同一组（组名 = 导入名），画布端按组折叠显示。
    clusters, dropped = myridtv_comfy.comfy_workflow_split_clusters(workflow)
    if clusters:
        base_title = myridtv_libraries.workflow_title_from_name(file_name)
        group = {"id": re.sub(r"\.json$", "", file_name), "title": base_title}
        for index, cluster in enumerate(clusters, start=1):
            member_name = f"{base_title}-{index}.json" if len(clusters) > 1 else file_name
            member_path = _G_ROOT() / "workflows" / "custom" / member_name
            if member_path.exists():
                raise ApiError(409, f"工作流已存在: {member_name}")
            myridtv_core.write_json_file(member_path, cluster["nodes"])
            config_path = member_path.with_suffix(".config.json")
            if not config_path.exists():
                myridtv_core.write_json_file(config_path, {
                    "title": f"{base_title}-{index}",
                    "fields": [],
                    "mini_cards": {},
                    "group": group,
                    "imported_from": file_name,
                })
        myridtv_core.append_log(_G_LOG_FILE(), f"comfy workflow pack imported {file_name} -> {len(clusters)} members, dropped={len(dropped)} nodes")
        first = myridtv_libraries.read_workflow_record(f"{base_title}-1.json" if len(clusters) > 1 else file_name)
        first["pack"] = {
            "id": group["id"],
            "title": base_title,
            "members": [{"name": f"{base_title}-{i}.json", "title": f"{base_title}-{i}"} for i in range(1, len(clusters) + 1)],
        }
        return first

    myridtv_core.write_json_file(workflow_path, workflow if isinstance(workflow, dict) else {})
    config_path = workflow_path.with_suffix(".config.json")
    if not config_path.exists():
        myridtv_core.write_json_file(config_path, {"title": myridtv_libraries.workflow_title_from_name(file_name), "fields": [], "mini_cards": {}})
    return myridtv_libraries.read_workflow_record(file_name)


def save_workflow_config(name, config):
    file_name, workflow_path, config_path, _builtin = myridtv_libraries.find_workflow_files(name)
    if not workflow_path.exists():
        raise ApiError(404, f"Workflow not found: {file_name}")
    safe = config if isinstance(config, dict) else {}
    safe.setdefault("title", myridtv_libraries.workflow_title_from_name(file_name))
    safe.setdefault("fields", [])
    safe.setdefault("mini_cards", {})
    myridtv_core.write_json_file(config_path, safe)
    return myridtv_libraries.read_workflow_record(file_name)


def rename_workflow_record(name, new_name):
    """重命名自定义工作流文件（改名 = 文件名与显示名统一）。

    老王诉求：不要「前端叫 MMH3-文戏、后端文件叫 MMH3.json」两套名字。
    这里把 .json 与 .config.json 一起改名，并**递归改写所有画布里对该文件名的
    引用**（节点 runSettings.comfyWorkflow、settings.comfyWorkflow、以及其它
    以文件名做键/值的缓存），否则改名后引用旧名的节点会直接失效。
    """
    old_file, workflow_path, config_path, builtin = myridtv_libraries.find_workflow_files(name)
    if builtin:
        raise ApiError(403, "内置工作流不能重命名")
    base = re.sub(r"\.json$", "", str(new_name or "").strip(), flags=re.I).strip()
    if not base or base in (".", "..") or re.search(r'[\\/:*?"<>|]', base):
        raise ApiError(400, "工作流名称非法（不能包含 \\ / : * ? \" < > |）")
    new_file = base + ".json"
    if new_file == old_file:
        return {"ok": True, "name": new_file, "renamed": False, "updated_canvases": 0}

    new_workflow_path = workflow_path.parent / new_file
    if new_workflow_path.exists():
        raise ApiError(409, f"工作流已存在: {new_file}")

    workflow_path.rename(new_workflow_path)
    new_config_path = new_workflow_path.with_suffix(".config.json")
    config = None
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            config = None
        config_path.rename(new_config_path)
    # 显示名同步为新文件名（用户就是要两者统一）
    if isinstance(config, dict):
        config["title"] = base
        try:
            myridtv_core.write_json_file(new_config_path, config)
        except Exception:
            pass

    updated = _rewrite_canvas_workflow_refs(old_file, new_file)
    myridtv_core.append_log(_G_LOG_FILE(), f"comfy workflow renamed {old_file} -> {new_file}, canvases updated={updated}")
    return {"ok": True, "name": new_file, "renamed": True, "updated_canvases": updated}


def _rewrite_canvas_workflow_refs(old_file, new_file):
    """把所有画布里等于旧文件名的字符串（键与值）改写成新文件名。"""
    canvas_dir = None
    try:
        canvas_dir = _G_CANVAS_DIR()
    except Exception:
        canvas_dir = None
    if not canvas_dir:
        return 0
    root = Path(canvas_dir)
    if not root.exists():
        return 0
    updated = 0

    def walk_container(node):
        nonlocal updated
        if isinstance(node, dict):
            for key in list(node.keys()):
                value = node[key]
                if isinstance(value, str) and value == old_file:
                    node[key] = new_file
                    updated += 1
                elif isinstance(key, str) and key == old_file:
                    node[new_file] = node.pop(key)
                    updated += 1
                walk_container(value)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                if isinstance(item, str) and item == old_file:
                    node[index] = new_file
                    updated += 1
                else:
                    walk_container(item)

    for canvas_path in root.glob("*.json"):
        try:
            data = json.loads(canvas_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        before = updated
        walk_container(data)
        if updated > before:
            try:
                myridtv_core.write_json_file(canvas_path, data)
            except Exception as exc:
                myridtv_core.append_log(_G_LOG_FILE(), f"rename ref write failed {canvas_path.name}: {exc}")
    return updated


def delete_workflow_record(name):
    file_name, workflow_path, config_path, builtin = myridtv_libraries.find_workflow_files(name)
    if builtin:
        raise ApiError(403, "内置工作流不能删除")
    if workflow_path.exists():
        workflow_path.unlink()
    if config_path.exists():
        config_path.unlink()
    return {"ok": True, "name": file_name}


def parse_workflow_route(request_path):
    prefix = "/api/workflows"
    if request_path == prefix:
        return ("collection", "")
    if not request_path.startswith(prefix + "/"):
        return (None, "")
    tail = request_path[len(prefix) + 1:]
    for suffix, route_name in (
        ("/config", "config"),
        ("/run", "run"),
        ("/rename", "rename"),
    ):
        if tail.endswith(suffix):
            return (route_name, urllib.parse.unquote(tail[:-len(suffix)]))
    return ("item", urllib.parse.unquote(tail))


def guess_kind_from_name(name, mime_type=""):
    mime_text = str(mime_type or "").lower()
    if mime_text.startswith("video/"):
        return "video"
    if mime_text.startswith("audio/"):
        return "audio"
    text = str(name or "").lower()
    if re.search(r"\.(mp4|webm|mov|m4v|avi|mkv)$", text):
        return "video"
    if re.search(r"\.(mp3|wav|m4a|aac|ogg|flac)$", text):
        return "audio"
    return "image"


def sanitize_file_name(name, mime_type="", fallback="blender-frame.png"):
    raw = str(name or fallback).strip() or fallback
    raw = raw.replace("\\", "_").replace("/", "_")
    raw = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._") or fallback
    if "." not in Path(raw).name:
        ext = mimetypes.guess_extension(str(mime_type or "").strip(), strict=False) or ".png"
        if ext == ".jpe":
            ext = ".jpg"
        raw += ext
    return raw[:180]


def decode_blender_payload_asset(payload):
    mime_type = str(payload.get("mime_type") or "image/png").strip() or "image/png"
    file_name = sanitize_file_name(payload.get("file_name") or payload.get("name") or "blender-frame.png", mime_type=mime_type)
    encoded = str(payload.get("file_base64") or payload.get("image_base64") or "").strip()
    if not encoded:
        raise RuntimeError("缺少 file_base64 或 image_base64")
    if "," in encoded and encoded.lower().startswith("data:"):
        header, encoded = encoded.split(",", 1)
        detected_mime = header.split(";", 1)[0].split(":", 1)[-1].strip()
        if detected_mime and not payload.get("mime_type"):
            mime_type = detected_mime
    encoded = re.sub(r"\s+", "", encoded)
    try:
        data = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise RuntimeError("file_base64 无法解码") from exc
    return {
        "file_name": file_name,
        "mime_type": mime_type,
        "data": data,
    }


def save_blender_payload_asset(payload):
    decoded = decode_blender_payload_asset(payload)
    file_name = decoded["file_name"]
    mime_type = decoded["mime_type"]
    data = decoded["data"]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    unique_name = f"{stamp}_{uuid.uuid4().hex[:8]}_{file_name}"
    # 插件回传（视频/截图）统一走画布输出目录 assets/output/<画布名>/{videos,images}/
    is_video = str(mime_type or "").startswith("video")
    if is_video:
        sub = "videos"
    else:
        sub = "images"
    canvas_title = ""
    try:
        cid = str(payload.get("canvas_id") or "").strip()
        if cid:
            cpath = myridtv_canvas_store.smart_canvas_path(cid)
            if cpath.exists():
                canvas_title = str((myridtv_core.read_json_file(cpath, {}) or {}).get("title") or "").strip()
    except Exception:
        canvas_title = ""
    folder = myridtv_media_localize.canvas_output_folder_name(canvas_title, cid)
    target_dir = _G_ASSETS_DIR() / "output" / folder / sub
    url = f"/assets/output/{urllib.parse.quote(folder)}/{sub}/{urllib.parse.quote(unique_name)}"
    target = target_dir / unique_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {
        "name": file_name,
        "url": url,
        "local_path": str(target),
        "mime_type": mime_type,
        "kind": guess_kind_from_name(file_name, mime_type),
        "size_bytes": len(data),
    }

