# -*- coding: utf-8 -*-
"""workflow 记录 + blender 资产落盘域（第31刀自 rh_official_proxy.py 逐字外移）：
workflow 记录创建/保存/删除、路由解析、素材名/类型工具、
blender payload 解码落盘。LOG_FILE 走 getter；ROOT/ASSETS_DIR 统一 getter 处方。"""
from pathlib import Path
import json
import re
import time
import difflib
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
_G_USER_DATA_DIR = lambda: None


def configure(getters):
    global _G_LOG_FILE, _G_ROOT, _G_ASSETS_DIR, _G_CANVAS_DIR, _G_USER_DATA_DIR
    _G_LOG_FILE = getters['LOG_FILE']
    _G_ROOT = getters['ROOT']
    _G_ASSETS_DIR = getters['ASSETS_DIR']
    # 重命名工作流时要连带改写画布里的引用，故需知道画布目录（旧调用无此键则安全降级）
    _G_CANVAS_DIR = getters.get('CANVAS_DIR', lambda: None)
    # 记「源文件都放在哪些目录」用（旧调用无此键则安全降级：不记目录）
    _G_USER_DATA_DIR = getters.get('USER_DATA_DIR', lambda: None)


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


def _source_dirs_file():
    """「源文件都放在哪些目录」的记账本（user_data/data/comfy_source_dirs.json）。

    老王 2026-10-26：真源头是他**上传时选的那个目录**，浏览器死活不给路径，
    所以只能「你指一次，我记一辈子」——之后所有工作流都先去这些目录里找。
    """
    base = _G_USER_DATA_DIR()
    if not base:
        return None
    return Path(base) / "data" / "comfy_source_dirs.json"


def known_source_dirs():
    path = _source_dirs_file()
    if not path or not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = raw.get("dirs") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in out and Path(text).is_dir():
            out.append(text)
    return out[:8]


def remember_source_dir(file_path):
    """把「这次源文件所在的目录」记进账本（最近用过的排前面，最多 8 个）。"""
    path = _source_dirs_file()
    if not path:
        return []
    folder = str(Path(str(file_path or "")).parent).strip()
    if not folder or not Path(folder).is_dir():
        return known_source_dirs()
    dirs = [d for d in known_source_dirs() if d.lower() != folder.lower()]
    dirs.insert(0, folder)
    dirs = dirs[:8]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"dirs": dirs}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass
    return dirs


def _best_match_in_dir(folder, file_name):
    """在一个目录（含一层子目录）里找跟 file_name 最像的那个 json。

    老王嫌填全路径烦：填个目录就行，剩下的我来认名字（前缀/空格/emoji 一律忽略）。
    """
    def norm(text):
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(text or "").lower())
    target = norm(re.sub(r"\.json$", "", str(file_name or ""), flags=re.I))
    if not target:
        return ""
    root = Path(folder)
    if not root.is_dir():
        return ""
    best, best_score = "", 0.0
    try:
        for pattern in ("*.json", "*/*.json"):
            for path in root.glob(pattern):
                if path.name.lower().endswith(".config.json"):
                    continue
                other = norm(re.sub(r"\.json$", "", path.name, flags=re.I))
                if not other:
                    continue
                score = difflib.SequenceMatcher(None, target, other).ratio()
                if target in other or other in target:
                    score = max(score, 0.8)
                if score > best_score:
                    best, best_score = str(path), score
    except Exception:
        return ""
    return best if best_score >= 0.42 else ""


def candidate_source_files(file_name, limit=8):
    """没记过源时，去本机常见的 ComfyUI 工作流目录里找同名/近名文件。

    老王最烦「每个工作流都要手填一次绝对路径」：导入时浏览器根本不给路径，
    第一次重载必然没源。这里按文件名相似度扫几个常见目录给出候选，点一下即可。
    只扫顶层 ComfyUI* 目录下的 workflows，成本低、不会全盘遍历。
    """
    # 老王的真源文件叫「AI代码侠土豆-Qwen Image 2.1 文生图.json」，app 里叫「Qwen-2.1-文生图.json」：
    # 前缀、空格、标点、emoji 全不一样 → 只能归一化后按包含/相似度匹配，不能按全名相等。
    def norm(text):
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(text or "").lower())
    target = norm(re.sub(r"\.json$", "", str(file_name or ""), flags=re.I))
    if not target:
        return []
    roots = []
    # 老王指过的目录优先（那才是真源头）
    for folder in known_source_dirs():
        roots.append(Path(folder))
    for drive in ("C:", "D:", "E:", "F:"):
        try:
            base_dir = Path(drive + "\\")
            if not base_dir.exists():
                continue
            for entry in base_dir.glob("ComfyUI*"):
                if not entry.is_dir():
                    continue
                for sub in ("", "user/default/workflows", "workflows", "ComfyUI/user/default/workflows"):
                    candidate_root = entry if not sub else entry / sub
                    if candidate_root.is_dir():
                        roots.append(candidate_root)
        except Exception:
            continue
    seen = set()
    hits = []
    for root in roots:
        try:
            # 只有真·工作流目录才往下钻一层（子目录分门别类是常态）；
            # 其余目录只扫顶层，免得把 ComfyUI 的 python/ 之类大目录翻一遍。
            lowered = str(root.name).lower()
            deep = "workflow" in lowered or "工作流" in lowered
            patterns = ("*.json", "*/*.json") if deep else ("*.json",)
            for pattern in patterns:
                for path in root.glob(pattern):
                    key = str(path).lower()
                    if key in seen or key.endswith(".config.json"):
                        continue
                    seen.add(key)
                    other = norm(re.sub(r"\.json$", "", path.name, flags=re.I))
                    if not other:
                        continue
                    score = difflib.SequenceMatcher(None, target, other).ratio()
                    if target in other or other in target:
                        score = max(score, 0.8)
                    if score < 0.42:
                        continue
                    hits.append((score, str(path)))
        except Exception:
            continue
    hits.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
    return [path for _score, path in hits[:limit]]


def _pack_member_index(file_name, config):
    """pack（多管线集合）成员名形如 <base>-2.json → 返回 2；非 pack 返回 0。"""
    if not (config or {}).get("group"):
        return 0
    match = re.search(r"-(\d+)\.json$", str(file_name or ""), flags=re.I)
    return int(match.group(1)) if match else 1


def reload_workflow_from_source(name, source_path=None, workflow=None):
    """从「源文件」重新拉一份工作流，覆盖 app 自己目录下的副本。

    老王 2026-10-26：改的是 ComfyUI 侧导出的源文件，app 只重读 `workflows/custom/`
    下那份副本，等于原地打转。所以「重载」= 去源路径读新版本 → 覆盖副本。
      - 传了 workflow（前端直接选文件内容）→ 用它；
      - 否则用 source_path，没传就用 config 里记住的 source_path；
      - 记住的也没有 / 源文件已被删或改名 → 返回 need_source，前端弹窗让老王手动指定；
      - 指定成功就把路径写进 config，下次一键重载。
    """
    file_name, workflow_path, config_path, builtin = myridtv_libraries.find_workflow_files(name)
    if builtin:
        raise ApiError(403, "内置工作流不支持从源文件重载")
    if not workflow_path.exists():
        raise ApiError(404, f"Workflow not found: {file_name}")
    config = myridtv_core.read_json_file(config_path, {}) or {}
    if not isinstance(config, dict):
        config = {}
    remembered = str(config.get("source_path") or "").strip()

    src = str(source_path or "").strip()
    raw = workflow if isinstance(workflow, dict) else None
    if raw is None:
        if not src:
            src = remembered
        if not src:
            return {"ok": False, "need_source": True, "reason": "unset", "name": file_name,
                    "last_source": "", "candidates": candidate_source_files(file_name),
                    "source_dirs": known_source_dirs()}
        source_file = Path(src)
        # 填的是目录也认：按名字在目录里挑最像的那个（省得手敲完整路径）
        if source_file.is_dir():
            picked = _best_match_in_dir(source_file, file_name)
            if not picked:
                return {"ok": False, "need_source": True, "reason": "dir-empty", "name": file_name,
                        "last_source": src, "candidates": candidate_source_files(file_name),
                        "source_dirs": known_source_dirs()}
            src = picked
            source_file = Path(src)
        if not source_file.exists() or not source_file.is_file():
            return {"ok": False, "need_source": True, "reason": "missing", "name": file_name,
                    "last_source": src, "candidates": candidate_source_files(file_name),
                    "source_dirs": known_source_dirs()}
        try:
            raw = json.loads(source_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ApiError(400, f"源文件不是合法 JSON：{str(exc)[:120]}")
    if not isinstance(raw, dict) or not raw:
        raise ApiError(400, "源文件内容不是工作流对象")
    # ComfyUI 的「界面格式」导出（nodes/links 列表）不是可提交图，直接挡掉，
    # 免得把好好的副本覆盖成一张废图。
    if isinstance(raw.get("nodes"), list) and not any(
        isinstance(value, dict) and value.get("class_type") for value in raw.values()
    ):
        raise ApiError(400, "这是 ComfyUI 的界面格式导出，请在 ComfyUI 里用「导出(API 格式)」后再重载")

    clusters, _dropped = myridtv_comfy.comfy_workflow_split_clusters(raw)
    if clusters:
        if not config.get("group"):
            raise ApiError(400, "源文件含多条独立管线，请用「上传」重新导入，别用重载覆盖单条")
        index = _pack_member_index(file_name, config)
        if index < 1 or index > len(clusters):
            raise ApiError(400, f"源文件管线数（{len(clusters)}）与当前成员序号（{index}）对不上")
        raw = clusters[index - 1]["nodes"]

    # 覆盖前留一份 .bak（老王最烦不可逆）；.bak 不匹配 *.json，不会混进列表
    try:
        if workflow_path.exists():
            workflow_path.with_name(workflow_path.name + ".bak").write_text(
                workflow_path.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass
    myridtv_core.write_json_file(workflow_path, raw)

    # 源目录里若躺着同名 .config.json（参数暴露配置）→ 一并覆盖；
    # 没有就保留本地 config（那是 MyridTV 侧的暴露配置，ComfyUI 导出里没有）。
    if src:
        try:
            stem = re.sub(r"\.json$", "", Path(src).name, flags=re.I)
            sidecar = Path(src).with_name(stem + ".config.json")
            if sidecar.exists():
                side_config = json.loads(sidecar.read_text(encoding="utf-8"))
                if isinstance(side_config, dict):
                    config = side_config
        except Exception:
            pass
    config.setdefault("title", myridtv_libraries.workflow_title_from_name(file_name))
    config.setdefault("fields", [])
    config.setdefault("mini_cards", {})
    if src:
        config["source_path"] = src
        try:
            stat = Path(src).stat()
            config["source_mtime"] = int(stat.st_mtime * 1000)
            config["source_size"] = int(stat.st_size)
        except Exception:
            pass
        config["source_synced_at"] = int(time.time() * 1000)
    myridtv_core.write_json_file(config_path, config)

    if src:
        remember_source_dir(src)  # 记下「源文件都放这个目录」，下次别的流也能直接找到
    myridtv_core.append_log(_G_LOG_FILE(), f"comfy workflow reloaded from source {file_name} <- {src or '(inline)'}")
    return {
        "ok": True,
        "name": file_name,
        "source_path": src,
        "config": config,
        "record": myridtv_libraries.read_workflow_record(file_name),
    }


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
        ("/reload-source", "reload-source"),
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

