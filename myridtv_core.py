"""MyridTV 基础层（从 rh_official_proxy.py 拆出的第一批零耦合工具）。

②B 模块化第一刀：这些函数是"叶子"——只互相调用 + 标准库，不碰任何全局状态，
所以可以安全外移；后端改成 from myridtv_core import ... 后，所有调用点名字不变。
新增同类工具请加到本模块，不要再往 rh_official_proxy.py 里堆。
"""

from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path


def read_json_file(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def write_json_file(path, data):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_log(path, message):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as log:
            log.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def parse_number(value, default=None):
    try:
        number = float(value)
    except Exception:
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def parse_positive_int(value):
    number = parse_number(value)
    if number is None:
        return None
    number = int(round(number))
    return number if number > 0 else None


class ApiError(RuntimeError):
    def __init__(self, status, detail, payload=None):
        super().__init__(detail)
        self.status = int(status)
        self.detail = str(detail)
        self.payload = payload or {}


class CanvasConflictError(ApiError):
    def __init__(self, current_canvas):
        super().__init__(409, "画布已被其他窗口更新，请先刷新后再保存", {"canvas": current_canvas})
        self.current_canvas = current_canvas


def deep_merge(base, override):
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def unique_strings(items):
    seen = set()
    result = []
    for item in items or []:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def mask_secret(value):
    text = str(value or "").strip()
    if not text:
        return ""
    tail = text[-4:] if len(text) >= 4 else text
    return f"••••••••{tail}"


def clean_asset_name(value, label="名称"):
    text = str(value or "").strip()
    if not text:
        raise ApiError(400, f"{label}不能为空")
    return text


def clean_prompt_name(value, label="名称"):
    text = str(value or "").strip()
    if not text:
        raise ApiError(400, f"{label}不能为空")
    return text


def safe_agent_skill_name(name):
    text = str(name or "").strip()
    if text.lower().endswith(".md"):
        text = text[:-3]
    text = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", text).strip(" .")
    if not text or text in (".", ".."):
        return ""
    return text[:80]


def default_asset_library():
    return {
        "active_library_id": "default",
        "libraries": [
            {
                "id": "default",
                "name": "默认资产库",
                "type": "asset",
                "categories": [
                    {"id": "characters", "name": "角色", "type": "image", "items": []},
                    {"id": "scenes", "name": "场景", "type": "image", "items": []},
                    {"id": "workflows", "name": "工作流", "type": "workflow", "items": []},
                ],
            }
        ],
    }


def default_prompt_library():
    return {
        "active_library_id": "system",
        "libraries": [
            {
                "id": "system",
                "name": "系统提示词库",
                "type": "prompt",
                "readonly": False,
                "system": True,
                "categories": [
                    {"id": "view", "name": "视角"},
                    {"id": "storyboard", "name": "分镜"},
                    {"id": "character", "name": "角色"},
                    {"id": "product", "name": "产品"},
                    {"id": "lighting", "name": "光影"},
                    {"id": "custom", "name": "我的"},
                ],
                "items": [],
            }
        ],
    }


def _task_console_ts(value):
    """任务时间戳统一归一到「秒」。

    Agent 任务（agent_task_runtime.now_ms）写毫秒，生图/生视频任务写秒。混用会让
    Agent 任务永远排在最前、时间显示成乱值（09-08 的任务显示成 10:44），
    还会被误算进「今日任务」统计。
    """
    try:
        v = float(value)
    except Exception:
        return 0.0
    if v > 1e11:  # 毫秒量级（秒级要到公元 5138 年才可能这么大）
        v = v / 1000.0
    return v
