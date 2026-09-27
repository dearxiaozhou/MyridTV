# -*- coding: utf-8 -*-
"""MyridTV 素材/提示词/工作流仓库域（后端拆分第12刀）：asset_library 与 prompt_libraries
两级（库/类目/条目）CRUD、版本追加与索引缓存、workflow 记录读写与文件定位、
comfy_instances 存储路径、本地配置载荷装配。

逐字迁移自 rh_official_proxy.py 连续块 L(asset_library_file_path)..L(output_asset_kind_for_name)
（56 函数 819 行，可逆还原行级 diff=0）。行为零变更。
configure() 注入：USER_DATA_DIR/ROOT 值（import 时定、零重绑）+ LOG_FILE getter；
read_api_providers 直引 myridtv_provider。ASSET_VERSION_INDEX_CACHE 单例与
PROMPT_BUILTIN_CATEGORY_IDS 常量随块入本模块。主文件对块外仍引用的 35 函数留
同名薄代理，调用点不改（comfy 域 lambda 闭包经主代理回指本模块，链不断）。
"""
import time
import urllib.parse
import uuid
from pathlib import Path

import myridtv_provider
from myridtv_core import (
    ApiError,
    append_log,
    clean_asset_name,
    clean_prompt_name,
    default_asset_library,
    default_prompt_library,
    read_json_file,
    write_json_file,
)

_USER_DATA_DIR = None
_ROOT = None
_log_file = lambda: None


def configure(user_data_dir, root, log_file_getter):
    global _USER_DATA_DIR, _ROOT, _log_file
    _USER_DATA_DIR = user_data_dir
    _ROOT = root
    _log_file = log_file_getter


def asset_library_file_path():
    return _USER_DATA_DIR / "data" / "asset_library.json"


def prompt_library_file_path():
    return _USER_DATA_DIR / "data" / "prompt_libraries.json"


def comfy_instances_file_path():
    return _USER_DATA_DIR / "data" / "comfyui_instances.json"


def workflow_search_roots():
    return [
        (_ROOT / "workflows" / "custom", False),
        (_ROOT / "workflows", True),
    ]


def workflow_file_candidates(name):
    safe_name = str(name or "").strip()
    if not safe_name:
        raise ApiError(400, "缺少工作流名称")
    if "/" in safe_name or "\\" in safe_name or ".." in safe_name:
        raise ApiError(400, "工作流名称非法")
    file_name = safe_name if safe_name.lower().endswith(".json") else f"{safe_name}.json"
    config_name = file_name[:-5] + ".config.json"
    candidates = []
    for root, builtin in workflow_search_roots():
        candidates.append((root / file_name, root / config_name, builtin))
    return file_name, candidates


def workflow_title_from_name(name):
    return str(name or "").replace(".json", "").strip() or "未命名工作流"


def workflow_field_count(config):
    if not isinstance(config, dict):
        return 0
    fields = config.get("fields")
    return len(fields) if isinstance(fields, list) else 0


def read_asset_library():
    data = read_json_file(asset_library_file_path(), default_asset_library())
    return data if isinstance(data, dict) else default_asset_library()


def write_asset_library(library):
    safe = library if isinstance(library, dict) else default_asset_library()
    safe["updated_at"] = int(time.time() * 1000)
    write_json_file(asset_library_file_path(), safe)
    return safe


def asset_library_payload(library, **extra):
    return {"ok": True, "library": write_asset_library(library), **extra}


def asset_libraries_list(library):
    libs = library.get("libraries") if isinstance(library, dict) else []
    if not isinstance(libs, list) or not libs:
        defaults = default_asset_library()
        library.clear()
        library.update(defaults)
        libs = library.get("libraries") or []
    return libs


def find_asset_library_record(library, library_id="", required=True):
    libs = asset_libraries_list(library)
    wanted = str(library_id or library.get("active_library_id") or "default").strip()
    lib = next((item for item in libs if str(item.get("id") or "") == wanted), None)
    if lib is None and not wanted:
        lib = libs[0] if libs else None
    if lib is None and required:
        raise ApiError(404, "资产库不存在")
    if lib is not None and not isinstance(lib.get("categories"), list):
        lib["categories"] = []
    return lib


def find_asset_category_record(library, category_id="", library_id="", required=True):
    wanted = str(category_id or "").strip()
    libs = [find_asset_library_record(library, library_id)] if str(library_id or "").strip() else asset_libraries_list(library)
    for lib in libs:
        if not lib:
            continue
        cats = lib.get("categories")
        if not isinstance(cats, list):
            cats = []
            lib["categories"] = cats
        for cat in cats:
            if str(cat.get("id") or "") == wanted:
                if not isinstance(cat.get("items"), list):
                    cat["items"] = []
                return lib, cat
    if required:
        raise ApiError(404, "资产分组不存在")
    return None, None


def find_asset_item_record(library, item_id="", library_id="", required=True):
    wanted = str(item_id or "").strip()
    libs = [find_asset_library_record(library, library_id)] if str(library_id or "").strip() else asset_libraries_list(library)
    for lib in libs:
        if not lib:
            continue
        cats = lib.get("categories")
        if not isinstance(cats, list):
            cats = []
            lib["categories"] = cats
        for cat in cats:
            items = cat.get("items")
            if not isinstance(items, list):
                items = []
                cat["items"] = items
            for item in items:
                if str(item.get("id") or "") == wanted:
                    return lib, cat, item
    if required:
        raise ApiError(404, "素材不存在")
    return None, None, None


def find_asset_category(library, library_id="", category_id=""):
    libs = library.get("libraries") if isinstance(library, dict) else []
    if not isinstance(libs, list) or not libs:
        library.update(default_asset_library())
        libs = library.get("libraries") or []
    lib = next((item for item in libs if str(item.get("id") or "") == str(library_id or "")), None)
    if lib is None:
        lib = libs[0]
    cats = lib.get("categories") if isinstance(lib.get("categories"), list) else []
    image_cats = [cat for cat in cats if str(cat.get("type") or "image") == "image"]
    cat = next((item for item in image_cats if str(item.get("id") or "") == str(category_id or "")), None)
    if cat is None:
        if image_cats:
            cat = image_cats[0]
        else:
            cat = {"id": "images", "name": "图片", "type": "image", "items": []}
            cats.append(cat)
            lib["categories"] = cats
    if not isinstance(cat.get("items"), list):
        cat["items"] = []
    return lib, cat


# ====== 资产版本链：同一素材的 v1/v2/... + 引用可"跟最新"或"钉旧版" ======
# 条目结构（向后兼容：老的 url/name 仍是"当前版本指针"）：
#   item = { id, url, name, kind, created_at, updated_at,
#            versions:[{version_id, url, name, kind, created_at, note?}], current_version_id }
# 画布节点里引用资产时带：
#   image = { url, name, assetId, assetVersionMode:"latest"|"pinned", assetVersionId? }
#   - latest：读画布时解析到条目当前版本（源素材重跑出新版，引用处自动跟）
#   - pinned：解析到 assetVersionId 指定的那一版（已出片的镜头钉住不动）

ASSET_VERSION_INDEX_CACHE = {"mtime": None, "index": {}}


def asset_item_versions(item):
    """返回条目的版本链；老条目（没有 versions）自动把自身当作 v1 补齐。"""
    if not isinstance(item, dict):
        return []
    versions = item.get("versions")
    if not isinstance(versions, list) or not versions:
        url = str(item.get("url") or "").strip()
        if not url:
            return []
        head = {
            "version_id": str(item.get("current_version_id") or ("v1_" + str(item.get("id") or uuid.uuid4().hex[:8]))),
            "url": url,
            "name": str(item.get("name") or ""),
            "kind": str(item.get("kind") or "image"),
            "created_at": int(item.get("created_at") or 0),
        }
        item["versions"] = [head]
        item["current_version_id"] = head["version_id"]
        return item["versions"]
    return versions


def append_asset_version(item, url, name="", kind="", note=""):
    """给条目追加一个新版本。返回 (version_entry, created?)；同一地址不重复登记。"""
    versions = asset_item_versions(item)
    target_url = str(url or "").strip()
    if not target_url:
        raise ApiError(400, "新版本缺少素材地址")
    for existing in versions:
        if str(existing.get("url") or "") == target_url:
            return existing, False
    now_ms = int(time.time() * 1000)
    entry = {
        "version_id": "v{}_{}".format(len(versions) + 1, uuid.uuid4().hex[:8]),
        "url": target_url,
        "name": str(name or item.get("name") or "").strip(),
        "kind": str(kind or item.get("kind") or "image").strip(),
        "created_at": now_ms,
    }
    if note:
        entry["note"] = str(note)[:200]
    versions.append(entry)
    item["versions"] = versions
    item["current_version_id"] = entry["version_id"]
    # 当前版本指针（老代码读 url/name/kind 依然正确）
    item["url"] = target_url
    if entry["name"]:
        item["name"] = entry["name"]
    if entry["kind"]:
        item["kind"] = entry["kind"]
    item["updated_at"] = now_ms
    return entry, True


def asset_version_index():
    """{item_id: item} 索引，按资产库文件 mtime 缓存，避免每次读画布都解析大文件。"""
    try:
        path = asset_library_file_path()
        mtime = path.stat().st_mtime
    except Exception:
        return {}
    cache = ASSET_VERSION_INDEX_CACHE
    if cache.get("mtime") == mtime:
        return cache.get("index") or {}
    index = {}
    try:
        library = read_asset_library()
        for lib in library.get("libraries") or []:
            for cat in lib.get("categories") or []:
                for item in cat.get("items") or []:
                    if isinstance(item, dict) and item.get("id"):
                        index[str(item["id"])] = item
    except Exception:
        index = {}
    ASSET_VERSION_INDEX_CACHE["mtime"] = mtime
    ASSET_VERSION_INDEX_CACHE["index"] = index
    return index


def add_asset_library_version(payload):
    """把一张图登记为某个已有素材的新版本。payload: {item_id, url, name?, kind?, note?}"""
    payload = payload if isinstance(payload, dict) else {}
    item_id = str(payload.get("item_id") or payload.get("assetId") or "").strip()
    url = str(payload.get("url") or "").strip()
    if not item_id:
        raise ApiError(400, "缺少 item_id（要更新哪个素材）")
    if not url:
        raise ApiError(400, "缺少 url（新版本的素材地址）")
    library = read_asset_library()
    _lib, _cat, item = find_asset_item_record(library, item_id, payload.get("library_id") or "")
    entry, created = append_asset_version(
        item, url,
        name=str(payload.get("name") or ""),
        kind=str(payload.get("kind") or payload.get("mediaKind") or ""),
        note=str(payload.get("note") or ""))
    saved = write_asset_library(library)
    ASSET_VERSION_INDEX_CACHE["mtime"] = None
    append_log(_log_file(), "[AssetVersion] item={} version={} created={}".format(item_id, entry.get("version_id"), created))
    return {
        "ok": True,
        "library": saved,
        "item": item,
        "version": entry,
        "created": created,
        "versionCount": len(item.get("versions") or []),
    }


def resolve_canvas_asset_versions(canvas):
    """按引用策略把画布里的资产引用解析到目标版本（就地改 canvas，返回解析条数）。

    - mode=latest：解析到条目当前版本 → 素材重跑出新版，引用处自动跟
    - mode=pinned：解析到 assetVersionId 指定那版 → 钉住不动
    只处理带 assetId 的引用；老的纯 url 引用一律不碰。
    """
    if not isinstance(canvas, dict):
        return 0
    refs = []
    for node in canvas.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        for image in node.get("images") or []:
            if isinstance(image, dict) and str(image.get("assetId") or "").strip():
                refs.append(image)
    if not refs:
        return 0
    index = asset_version_index()
    if not index:
        return 0
    resolved = 0
    for image in refs:
        item = index.get(str(image.get("assetId") or "").strip())
        if not item:
            continue
        versions = asset_item_versions(item)
        if not versions:
            continue
        mode = str(image.get("assetVersionMode") or "latest").strip().lower()
        target = None
        if mode == "pinned":
            want = str(image.get("assetVersionId") or "").strip()
            target = next((v for v in versions if str(v.get("version_id")) == want), None)
        if target is None:
            want = str(item.get("current_version_id") or "").strip()
            target = next((v for v in versions if str(v.get("version_id")) == want), versions[-1])
        url = str(target.get("url") or "").strip()
        if not url or url == str(image.get("url") or ""):
            continue
        image["url"] = url
        # 只同步地址与类型，不改用户给这条引用起的名字
        if target.get("kind"):
            image["kind"] = str(target.get("kind"))
        image["assetVersionId"] = str(target.get("version_id") or "")
        resolved += 1
    return resolved


def add_asset_library_items(payload):
    payload = payload if isinstance(payload, dict) else {}
    library = read_asset_library()
    library_id = str(payload.get("library_id") or library.get("active_library_id") or "default")
    category_id = str(payload.get("category_id") or "")
    lib, cat = find_asset_category(library, library_id, category_id)
    raw_items = payload.get("items") if isinstance(payload.get("items"), list) else [payload]
    created = []
    now_ms = int(time.time() * 1000)
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url") or "").strip()
        if not url:
            continue
        item = {
            "id": str(raw.get("id") or f"asset_{uuid.uuid4().hex[:10]}"),
            "url": url,
            "name": str(raw.get("name") or Path(urllib.parse.urlparse(url).path).name or "asset"),
            "kind": str(raw.get("kind") or raw.get("mediaKind") or "image"),
            "created_at": now_ms,
            "updated_at": now_ms,
        }
        cat["items"].append(item)
        created.append(item)
    saved = write_asset_library(library)
    return {"ok": True, "library": saved, "item": created[0] if created else None, "items": created}


def create_asset_library_record(payload):
    library = read_asset_library()
    name = clean_asset_name(payload.get("name"), "资产库名称")
    lib = {
        "id": f"asset_lib_{uuid.uuid4().hex[:10]}",
        "name": name,
        "type": "asset",
        "categories": [],
        "created_at": int(time.time() * 1000),
    }
    asset_libraries_list(library).append(lib)
    library["active_library_id"] = lib["id"]
    return asset_library_payload(library, asset_library=lib)


def update_asset_library_record(library_id, payload):
    library = read_asset_library()
    lib = find_asset_library_record(library, library_id)
    lib["name"] = clean_asset_name(payload.get("name"), "资产库名称")
    lib["updated_at"] = int(time.time() * 1000)
    return asset_library_payload(library, asset_library=lib)


def delete_asset_library_record(library_id):
    library = read_asset_library()
    wanted = str(library_id or "").strip()
    libs = asset_libraries_list(library)
    if len(libs) <= 1:
        raise ApiError(400, "至少保留一个资产库")
    before = len(libs)
    library["libraries"] = [lib for lib in libs if str(lib.get("id") or "") != wanted]
    if len(library["libraries"]) == before:
        raise ApiError(404, "资产库不存在")
    if str(library.get("active_library_id") or "") == wanted:
        library["active_library_id"] = library["libraries"][0].get("id") if library["libraries"] else ""
    return asset_library_payload(library)


def create_asset_category_record(payload):
    library = read_asset_library()
    lib = find_asset_library_record(library, payload.get("library_id") or "")
    name = clean_asset_name(payload.get("name"), "分组名称")
    category_type = str(payload.get("type") or "image").strip() or "image"
    cat = {
        "id": f"asset_cat_{uuid.uuid4().hex[:10]}",
        "name": name,
        "type": category_type,
        "items": [],
        "created_at": int(time.time() * 1000),
    }
    cats = lib.get("categories")
    if not isinstance(cats, list):
        cats = []
        lib["categories"] = cats
    cats.append(cat)
    return asset_library_payload(library, category=cat)


def update_asset_category_record(category_id, payload):
    library = read_asset_library()
    _lib, cat = find_asset_category_record(library, category_id, payload.get("library_id") or "")
    cat["name"] = clean_asset_name(payload.get("name"), "分组名称")
    if "type" in payload:
        cat["type"] = str(payload.get("type") or cat.get("type") or "image").strip() or "image"
    cat["updated_at"] = int(time.time() * 1000)
    return asset_library_payload(library, category=cat)


def delete_asset_category_record(category_id):
    library = read_asset_library()
    lib, _cat = find_asset_category_record(library, category_id)
    lib["categories"] = [cat for cat in lib.get("categories", []) if str(cat.get("id") or "") != str(category_id or "")]
    return asset_library_payload(library)


def update_asset_item_record(item_id, payload):
    library = read_asset_library()
    _lib, _cat, item = find_asset_item_record(library, item_id, payload.get("library_id") or "")
    item["name"] = clean_asset_name(payload.get("name"), "素材名称")
    item["updated_at"] = int(time.time() * 1000)
    return asset_library_payload(library, item=item)


def delete_asset_item_record(item_id):
    library = read_asset_library()
    _lib, cat, _item = find_asset_item_record(library, item_id)
    cat["items"] = [item for item in cat.get("items", []) if str(item.get("id") or "") != str(item_id or "")]
    return asset_library_payload(library)


def delete_asset_items_record(payload):
    ids = {str(item or "").strip() for item in (payload.get("ids") if isinstance(payload, dict) else []) or []}
    ids.discard("")
    library = read_asset_library()
    removed = 0
    for lib in asset_libraries_list(library):
        for cat in lib.get("categories", []) if isinstance(lib.get("categories"), list) else []:
            if not isinstance(cat.get("items"), list):
                cat["items"] = []
                continue
            before = len(cat["items"])
            cat["items"] = [item for item in cat["items"] if str(item.get("id") or "") not in ids]
            removed += before - len(cat["items"])
    return asset_library_payload(library, removed=removed)


def move_asset_items_record(payload):
    payload = payload if isinstance(payload, dict) else {}
    ids = {str(item or "").strip() for item in payload.get("ids") or []}
    ids.discard("")
    library = read_asset_library()
    target_library_id = str(payload.get("target_library_id") or payload.get("library_id") or "").strip()
    target_category_id = str(payload.get("target_category_id") or payload.get("category_id") or "").strip()
    _target_lib, target_cat = find_asset_category_record(library, target_category_id, target_library_id)
    moved_items = []
    for lib in asset_libraries_list(library):
        for cat in lib.get("categories", []) if isinstance(lib.get("categories"), list) else []:
            items = cat.get("items")
            if not isinstance(items, list):
                cat["items"] = []
                continue
            remaining = []
            for item in items:
                if str(item.get("id") or "") in ids:
                    moved_items.append(item)
                else:
                    remaining.append(item)
            cat["items"] = remaining
    now_ms = int(time.time() * 1000)
    for item in moved_items:
        item["updated_at"] = now_ms
        target_cat.setdefault("items", []).append(item)
    return asset_library_payload(library, moved=len(moved_items), items=moved_items)


def crop_asset_items_record(payload):
    payload = payload if isinstance(payload, dict) else {}
    ids = {str(item or "").strip() for item in payload.get("ids") or []}
    ids.discard("")
    library = read_asset_library()
    target_library_id = str(payload.get("target_library_id") or payload.get("library_id") or "").strip()
    target_category_id = str(payload.get("target_category_id") or payload.get("category_id") or "").strip()
    if target_category_id:
        _target_lib, target_cat = find_asset_category_record(library, target_category_id, target_library_id)
    else:
        _target_lib, target_cat, _item = find_asset_item_record(library, next(iter(ids), ""), target_library_id)
    added = []
    now_ms = int(time.time() * 1000)
    for item_id in ids:
        _lib, _cat, item = find_asset_item_record(library, item_id, payload.get("library_id") or "", required=False)
        if not item:
            continue
        clone = dict(item)
        clone["id"] = f"asset_{uuid.uuid4().hex[:10]}"
        clone["name"] = f"{str(item.get('name') or 'asset')} 裁剪"
        clone["created_at"] = now_ms
        clone["updated_at"] = now_ms
        target_cat.setdefault("items", []).append(clone)
        added.append(clone)
    return asset_library_payload(library, added=len(added), items=added)

def read_prompt_libraries():
    data = read_json_file(prompt_library_file_path(), default_prompt_library())
    return data if isinstance(data, dict) else default_prompt_library()


PROMPT_BUILTIN_CATEGORY_IDS = {"view", "storyboard", "character", "product", "lighting", "custom"}


def write_prompt_libraries(library):
    safe = library if isinstance(library, dict) else default_prompt_library()
    if not isinstance(safe.get("libraries"), list) or not safe.get("libraries"):
        safe = default_prompt_library()
    safe["updated_at"] = int(time.time() * 1000)
    write_json_file(prompt_library_file_path(), safe)
    return safe


def prompt_library_payload(library, **extra):
    return {"ok": True, "library": write_prompt_libraries(library), **extra}


def prompt_libraries_list(library):
    libs = library.get("libraries") if isinstance(library, dict) else []
    if not isinstance(libs, list) or not libs:
        defaults = default_prompt_library()
        library.clear()
        library.update(defaults)
        libs = library.get("libraries") or []
    return libs


def find_prompt_library_record(library, library_id="", required=True):
    libs = prompt_libraries_list(library)
    wanted = str(library_id or library.get("active_library_id") or "system").strip()
    lib = next((item for item in libs if str(item.get("id") or "") == wanted), None)
    if lib is None and not wanted:
        lib = libs[0] if libs else None
    if lib is None and required:
        raise ApiError(404, "提示词库不存在")
    if lib is not None:
        lib.setdefault("items", [])
        lib.setdefault("categories", [])
    return lib


def find_prompt_category_record(library, category_id="", required=True):
    wanted = str(category_id or "").strip()
    for lib in prompt_libraries_list(library):
        cats = lib.get("categories")
        if not isinstance(cats, list):
            cats = []
            lib["categories"] = cats
        for cat in cats:
            if str(cat.get("id") or "") == wanted:
                return lib, cat
    if required:
        raise ApiError(404, "提示词分组不存在")
    return None, None


def find_prompt_item_record(library, item_id="", library_id="", required=True):
    wanted = str(item_id or "").strip()
    libs = [find_prompt_library_record(library, library_id)] if library_id else prompt_libraries_list(library)
    for lib in libs:
        items = lib.get("items")
        if not isinstance(items, list):
            items = []
            lib["items"] = items
        for item in items:
            if str(item.get("id") or "") == wanted:
                return lib, item
    if required:
        raise ApiError(404, "提示词不存在")
    return None, None


def create_prompt_library_record(payload):
    library = read_prompt_libraries()
    name = clean_prompt_name(payload.get("name"), "提示词库名称")
    lib = {
        "id": f"prompt_lib_{uuid.uuid4().hex[:10]}",
        "name": name,
        "type": "prompt",
        "readonly": False,
        "categories": [],
        "items": [],
        "created_at": int(time.time() * 1000),
    }
    prompt_libraries_list(library).append(lib)
    library["active_library_id"] = lib["id"]
    return prompt_library_payload(library, prompt_library=lib)


def update_prompt_library_record(library_id, payload):
    library = read_prompt_libraries()
    lib = find_prompt_library_record(library, library_id)
    lib["name"] = clean_prompt_name(payload.get("name"), "提示词库名称")
    return prompt_library_payload(library, prompt_library=lib)


def delete_prompt_library_record(library_id):
    library = read_prompt_libraries()
    wanted = str(library_id or "").strip()
    if wanted == "system":
        raise ApiError(400, "系统提示词库不能删除")
    libs = prompt_libraries_list(library)
    before = len(libs)
    library["libraries"] = [lib for lib in libs if str(lib.get("id") or "") != wanted]
    if len(library["libraries"]) == before:
        raise ApiError(404, "提示词库不存在")
    library["active_library_id"] = "system" if any(lib.get("id") == "system" for lib in library["libraries"]) else (library["libraries"][0].get("id") if library["libraries"] else "")
    return prompt_library_payload(library)


def create_prompt_category_record(payload):
    library = read_prompt_libraries()
    lib = find_prompt_library_record(library, payload.get("library_id") or "system")
    name = clean_prompt_name(payload.get("name"), "分组名称")
    cat = {"id": f"prompt_cat_{uuid.uuid4().hex[:10]}", "name": name}
    cats = lib.get("categories")
    if not isinstance(cats, list):
        cats = []
        lib["categories"] = cats
    cats.append(cat)
    return prompt_library_payload(library, category=cat)


def update_prompt_category_record(category_id, payload):
    wanted = str(category_id or "").strip()
    if wanted in PROMPT_BUILTIN_CATEGORY_IDS:
        raise ApiError(400, "内置分组不能编辑")
    library = read_prompt_libraries()
    _lib, cat = find_prompt_category_record(library, wanted)
    cat["name"] = clean_prompt_name(payload.get("name"), "分组名称")
    return prompt_library_payload(library, category=cat)


def delete_prompt_category_record(category_id):
    wanted = str(category_id or "").strip()
    if wanted in PROMPT_BUILTIN_CATEGORY_IDS:
        raise ApiError(400, "内置分组不能删除")
    library = read_prompt_libraries()
    lib, _cat = find_prompt_category_record(library, wanted)
    lib["categories"] = [cat for cat in lib.get("categories", []) if str(cat.get("id") or "") != wanted]
    for item in lib.get("items", []) if isinstance(lib.get("items"), list) else []:
        if str(item.get("category") or "") == wanted:
            item["category"] = "custom"
    return prompt_library_payload(library)


def prompt_item_from_payload(payload, existing=None):
    now_ms = int(time.time() * 1000)
    item = dict(existing or {})
    item["id"] = str(item.get("id") or payload.get("id") or f"prompt_{uuid.uuid4().hex[:10]}")
    item["name"] = clean_prompt_name(payload.get("name"), "提示词名称")
    item["scene"] = str(payload.get("scene") or "").strip()
    item["positive"] = clean_prompt_name(payload.get("positive"), "正向提示词")
    item["negative"] = str(payload.get("negative") or "").strip()
    item["category"] = str(payload.get("category") or item.get("category") or "custom").strip() or "custom"
    item.setdefault("created_at", now_ms)
    item["updated_at"] = now_ms
    return item


def create_prompt_item_record(payload):
    library = read_prompt_libraries()
    lib = find_prompt_library_record(library, payload.get("library_id") or "system")
    item = prompt_item_from_payload(payload)
    items = lib.get("items")
    if not isinstance(items, list):
        items = []
        lib["items"] = items
    items.append(item)
    return prompt_library_payload(library, item=item)


def update_prompt_item_record(item_id, payload):
    library = read_prompt_libraries()
    lib, item = find_prompt_item_record(library, item_id, payload.get("library_id") or "")
    updated = prompt_item_from_payload(payload, existing=item)
    items = lib.get("items") if isinstance(lib.get("items"), list) else []
    for index, current in enumerate(items):
        if str(current.get("id") or "") == str(item_id or ""):
            items[index] = updated
            break
    return prompt_library_payload(library, item=updated)


def delete_prompt_item_record(item_id):
    library = read_prompt_libraries()
    lib, _item = find_prompt_item_record(library, item_id)
    lib["items"] = [item for item in lib.get("items", []) if str(item.get("id") or "") != str(item_id or "")]
    return prompt_library_payload(library)


def delete_prompt_items_record(payload):
    ids = {str(item or "").strip() for item in (payload.get("ids") if isinstance(payload, dict) else []) or []}
    ids.discard("")
    library = read_prompt_libraries()
    for lib in prompt_libraries_list(library):
        if isinstance(lib.get("items"), list):
            lib["items"] = [item for item in lib["items"] if str(item.get("id") or "") not in ids]
    return prompt_library_payload(library)


def read_comfy_instances():
    data = read_json_file(comfy_instances_file_path(), {"instances": []})
    if isinstance(data, dict):
        items = data.get("instances")
        return normalize_comfy_instances(items)
    if isinstance(data, list):
        return normalize_comfy_instances(data)
    return []


def normalize_comfy_instances(instances):
    safe = []
    seen = set()
    for item in instances if isinstance(instances, list) else []:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        safe.append(text)
    return safe


def list_workflow_records():
    seen = set()
    records = []
    for root, builtin in workflow_search_roots():
        try:
            files = sorted(root.glob("*.json"))
        except Exception:
            files = []
        for path in files:
            if path.name.endswith(".config.json"):
                continue
            normalized_name = path.name
            if normalized_name in seen:
                continue
            seen.add(normalized_name)
            config_path = path.with_suffix(".config.json")
            config = read_json_file(config_path, {})
            record = {
                "name": normalized_name,
                "title": str(config.get("title") or workflow_title_from_name(normalized_name)).strip() or workflow_title_from_name(normalized_name),
                "field_count": workflow_field_count(config),
                "builtin": bool(builtin),
                "path": str(path),
            }
            group = config.get("group") if isinstance(config.get("group"), dict) else None
            if group and str(group.get("id") or "").strip():
                record["group"] = {"id": str(group.get("id")), "title": str(group.get("title") or group.get("id"))}
            records.append(record)
    records.sort(key=lambda item: (not bool(item.get("builtin")), str(item.get("title") or "").lower(), str(item.get("name") or "").lower()))
    return records


def find_workflow_files(name):
    file_name, candidates = workflow_file_candidates(name)
    for workflow_path, config_path, builtin in candidates:
        if workflow_path.exists():
            return file_name, workflow_path, config_path, builtin
    raise ApiError(404, f"Workflow not found: {file_name}")


def read_workflow_record(name):
    file_name, workflow_path, config_path, builtin = find_workflow_files(name)
    workflow = read_json_file(workflow_path, None)
    if not isinstance(workflow, dict):
        raise ApiError(500, f"工作流文件损坏: {file_name}")
    config = read_json_file(config_path, {})
    if not isinstance(config, dict):
        config = {}
    config.setdefault("title", workflow_title_from_name(file_name))
    config.setdefault("fields", [])
    config.setdefault("mini_cards", {})
    return {
        "name": file_name,
        "workflow": workflow,
        "config": config,
        "builtin": bool(builtin),
    }


def build_local_config_payload():
    providers = myridtv_provider.read_api_providers()
    image_models = []
    chat_models = []
    video_models = []
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        image_models.extend([item for item in (provider.get("image_models") or []) if isinstance(item, str) and item.strip()])
        chat_models.extend([item for item in (provider.get("chat_models") or []) if isinstance(item, str) and item.strip()])
        video_models.extend([item for item in (provider.get("video_models") or []) if isinstance(item, str) and item.strip()])
    return {
        "image_models": sorted(set(image_models)),
        "chat_models": sorted(set(chat_models)),
        "video_models": sorted(set(video_models)),
        "api_providers": providers,
        "comfy_instances": read_comfy_instances(),
        "image_model": (sorted(set(image_models))[0] if image_models else ""),
    }


