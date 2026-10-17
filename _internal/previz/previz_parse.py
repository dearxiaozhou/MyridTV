#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
画布镜头表文本 → previz 镜头表 JSON
=====================================
从画布 smart-prompt 镜头表节点提取的文本，解析成 previz_render.py 用的 JSON。

用法:
  python previz_parse.py --input 画布镜头表.txt --output 镜头表.json \
      [--width 1280] [--height 720] [--fps 24]

行格式（竖线分隔，7 列，后两列可省略）:
  镜号 | 时长 | 景别 | 运镜 | 内容 | 主体 | 相机

主体（空格分隔多个，颜色词可省略）:
  名称[位置]颜色            → 苏焰[0.6,-8.5,0]红
  名称[位置]→[终点]颜色     → 林野[-2.5,-6,0]→[2.5,-6,0]冷灰

相机（省略则按景别自动）:
  相机[位置]→[目标] 焦距mm  → 相机[0,-1.5,0.8]→[0,-8,1.0] 24mm
"""
import argparse
import json
import re
import sys
from pathlib import Path
from camera_language import extract_camera_languages, support_assets_for_languages

COLOR_MAP = {
    "红": [0.66, 0.16, 0.16], "绿": [0.29, 0.81, 0.50],
    "灰": [0.45, 0.45, 0.48], "冷灰": [0.23, 0.24, 0.26],
    "深灰": [0.30, 0.30, 0.33], "蓝": [0.25, 0.38, 0.55],
    "橙": [1.0, 0.62, 0.12], "白": [0.85, 0.85, 0.85],
    "黑": [0.12, 0.12, 0.14], "青": [0.20, 0.70, 0.75],
    "紫": [0.55, 0.35, 0.70], "棕": [0.40, 0.28, 0.18],
}

SUBJ_RE = re.compile(
    r"^(?P<name>[^\[\]]+?)\[(?P<pos>[-\d.,]+)\](?:→\[(?P<end>[-\d.,]+)\])?(?P<color>[^\s\[\]]*)$"
)
POSE_RE = re.compile(r"姿态\s*[=:：]\s*(躺|躺卧|仰卧|坐|坐姿|站|站姿)")
BIND_RE = re.compile(r"(?:绑定|载具绑定)\s*[=:：]\s*([^\s\[\]]+)")
CAM_RE = re.compile(
    r"^相机\[(?P<pos>[-\d.,]+)\]→\[(?P<tar>[-\d.,]+)\](?:\s*(?P<focal>\d+)\s*mm)?$"
)

# 预演人物资产目录（用户提供：man.obj/woman.obj，后续逐步增加）
_ASSETS = {}

ASSET_DIR = None  # 默认不扫描资产（不写资产路径=基础风格，绝不沿用上次资产）；--assets-dir 显式指定才加载


def scan_assets():
    """扫描资产目录：{文件名去扩展名: 绝对路径}，支持 obj/glb/fbx。
    未指定资产目录（ASSET_DIR=None）时返回空 = 基础风格。"""
    assets = {}
    if ASSET_DIR and Path(ASSET_DIR).exists():
        for ext in (".obj", ".glb", ".gltf", ".fbx"):
            for f in ASSET_DIR.rglob(f"*{ext}"):
                assets[f.stem.lower()] = str(f)
    return assets


MOVE_WORDS = ["奔跑", "行走", "前进", "走来", "走向", "移动", "巡逻", "走", "跑", "冲", "逼近", "上前", "离去", "撤退", "撤离", "行驶", "驾驶", "骑", "骑着", "飞驰", "疾驰", "高速", "极速"]


def detect_move(text):
    """从提示词检测资产移动：返回 (轴方向, 距离) 或 None。纯轴位移动画。"""
    if not any(w in text for w in MOVE_WORDS):
        return None
    dist = 14.0 if any(w in text for w in ["高速", "极速", "飞驰", "疾驰", "摩托", "骑车", "行驶"]) else (6.0 if any(w in text for w in ["奔跑", "跑", "冲"]) else 4.0)
    if any(w in text for w in ["向左", "左边", "左侧"]):
        return (1.0, 0.0), dist
    if any(w in text for w in ["向右", "右边", "右侧"]):
        return (-1.0, 0.0), dist
    if any(w in text for w in ["向前", "前方", "走来", "逼近", "冲", "走向"]):
        return (0.0, 1.0), dist
    return (0.0, -1.0), dist


WAYPOINT_RE = re.compile(
    r"(?:走位|位移|移动)\s*[：:]\s*从\s*\[(?P<from>[-\d.,]+)\]\s*(?:跑|走|冲|移|奔|前进|移动|到|至|向|→|->)\s*(?:到|至|向|→|->)?\s*\[(?P<to>[-\d.,]+)\]"
)
WAYPOINT_RE2 = re.compile(
    r"从\s*\[(?P<from>[-\d.,]+)\]\s*(?:跑|走|冲|移|奔|前进|移动|到|至|向|→|->)\s*(?:到|至|向|→|->)?\s*\[(?P<to>[-\d.,]+)\]"
)
CAMERA_BEAT_RE = re.compile(
    r"(?:镜头节拍|运镜节拍)\s*[：:]\s*(?P<body>[^\n]+?)(?=\s*(?:车辆动作|载具动作)\s*[：:]|$)", re.I
)
CAMERA_BEAT_ITEM_RE = re.compile(
    r"(?P<name>[^；;\[\]]+?)\s*\[\s*(?P<start>\d+(?:\.\d+)?)\s*(?P<start_pct>%)?\s*[-~至到]\s*"
    r"(?P<end>\d+(?:\.\d+)?)\s*(?P<end_pct>%)?\s*秒?\s*\]"
)
COMPOSITION_BEATS_RE = re.compile(
    r"(?:构图起落幅|起落幅构图)\s*[：:]\s*起幅\s*\[([^\]]+)\]\s*[；;，,]\s*落幅\s*\[([^\]]+)\]"
)
VEHICLE_ACTION_RE = re.compile(
    r"(?:车辆动作|载具动作)\s*[：:]\s*"
    r"(?P<name>[^从，,；;]+?)\s*从\s*\[(?P<start>[-\d.,]+)\]\s*"
    r"(?:→|->)\s*\[(?P<end>[-\d.,]+)\]\s*[，,；;\s]*"
    r"朝向\s*[=:：]\s*(?P<facing_from>东|南|西|北)\s*(?:→|->)\s*(?P<facing_to>东|南|西|北)\s*[，,；;\s]*"
    r"(?P<action>甩尾急停|漂移急停|急停)\s*\[(?P<t0>\d+(?:\.\d+)?)\s*[-~至到]\s*(?P<t1>\d+(?:\.\d+)?)\s*秒?\s*\]"
)


def extract_waypoint(text):
    """从备注文本提取走位坐标：返回 (起点, 终点) 或 None。

    兼容 H3 镜头表写法「走位：从 [x,y,z] 跑到 [x,y,z]」以及
    「从 [x,y,z] 到 [x,y,z]」两种格式。走位优先给主体做位移关键帧。
    """
    if not text:
        return None
    m = WAYPOINT_RE.search(text) or WAYPOINT_RE2.search(text)
    if not m:
        return None
    try:
        frm = [float(x) for x in m.group("from").split(",")]
        to = [float(x) for x in m.group("to").split(",")]
    except Exception:
        return None
    if len(frm) != 3 or len(to) != 3:
        return None
    return frm, to


def extract_camera_beats(text, duration=4.0):
    """解析秒数或按镜头时长缩放的百分比节拍。"""
    m = CAMERA_BEAT_RE.search(str(text or ""))
    if not m:
        return []
    duration = max(float(duration or 4.0), 1e-3)
    beats = []
    for item in CAMERA_BEAT_ITEM_RE.finditer(m.group("body")):
        start, end = float(item.group("start")), float(item.group("end"))
        if item.group("start_pct"):
            start = duration * max(0.0, min(100.0, start)) / 100.0
        if item.group("end_pct"):
            end = duration * max(0.0, min(100.0, end)) / 100.0
        start = max(0.0, min(duration, start))
        end = max(0.0, min(duration, end))
        if end > start:
            beats.append({"动作": item.group("name").strip(), "开始秒": start, "结束秒": end})
    return beats


def extract_composition_beats(text):
    """解析一个镜头的起幅、落幅构图提示。"""
    match = COMPOSITION_BEATS_RE.search(str(text or ""))
    if not match:
        return None
    return {"起幅": match.group(1).strip(), "落幅": match.group(2).strip()}


def infer_camera_beats(text, duration=4.0):
    """从常见自然语言运镜词自动规划平滑节拍，作为 LLM 不可用时的本地回退。"""
    text = str(text or "")
    duration = max(float(duration or 4.0), 1e-3)
    cues = [
        ("跟拍", r"跟拍|跟随|跟着(?:人物|主角|镜头)?|跟踪拍摄", 0.0, 0.82),
        ("横移", r"横移|侧移|平移|侧向移(?:动)?", 0.30, 0.80),
        ("环绕", r"环绕|绕着?(?:人物|主角|主体)(?:转|移动)?|绕(?:半圈|一圈)", 0.0, 1.0),
        ("慢推", r"慢推|慢慢推进|缓慢推进|推近|推进到(?:近景|特写)", 0.68, 1.0),
        ("冲击变焦", r"冲击变焦|突然变焦|快速变焦", 0.68, 1.0),
        ("变焦", r"变焦", 0.0, 1.0),
        ("上升", r"吊臂上升|镜头上升|向上升起", 0.0, 1.0),
        ("下压", r"下压镜头|镜头下压|向下俯拍", 0.0, 1.0),
    ]
    found = []
    for action, pattern, start_ratio, end_ratio in cues:
        match = re.search(pattern, text)
        if match:
            found.append((match.start(), action, start_ratio, end_ratio))
    # “冲击变焦”也会命中“变焦”，保留更具体的动作。
    found = [item for item in found if not (item[1] == "变焦" and "冲击变焦" in text)]
    found.sort(key=lambda item: item[0])
    if not found:
        return []
    moving = len(found) > 1
    beats = []
    for _, action, start_ratio, end_ratio in found:
        if not moving:
            start_ratio, end_ratio = 0.0, 1.0
        start = duration * start_ratio
        end = duration * end_ratio
        if end > start:
            beats.append({"动作": action, "开始秒": start, "结束秒": end})
    return beats


def extract_vehicle_action(text):
    """解析有明确空间、方向和时间的低模车辆动作。"""
    m = VEHICLE_ACTION_RE.search(str(text or ""))
    if not m:
        return None
    try:
        start = [float(x) for x in m.group("start").split(",")]
        end = [float(x) for x in m.group("end").split(",")]
        t0, t1 = float(m.group("t0")), float(m.group("t1"))
    except Exception:
        return None
    if len(start) != 3 or len(end) != 3 or t1 <= t0:
        return None
    return {
        "名称": m.group("name").strip(), "起点": start, "终点": end,
        "起始朝向": m.group("facing_from"), "结束朝向": m.group("facing_to"),
        "动作": m.group("action"), "开始秒": t0, "结束秒": t1,
    }


def match_asset(subject, assets):
    """主体名匹配资产：精确/包含匹配 > 女男机怪前缀规范 > 英文兜底。"""
    name = str(subject.get("名称") or "")
    low = name.lower()
    if low in assets:
        return assets[low]
    for key, path in assets.items():
        if key in low or low in key:
            return path
    prefix_candidates = []
    if "女" in name:
        prefix_candidates += ["女", "woman", "girl"]
    if "男" in name or "骑手" in name:
        prefix_candidates += ["男", "man", "boy"]
    if "机" in name or "机器人" in name or "机械" in name:
        prefix_candidates += ["机", "robot", "mech"]
    if "怪" in name or "怪物" in name:
        prefix_candidates += ["怪", "monster", "creature"]
    for prefix in prefix_candidates:
        for key, path in assets.items():
            if key.startswith(prefix) or prefix in key:
                return path
    return None


def match_vehicle_asset(text, assets):
    text_low = str(text or "").lower()
    for key in sorted(assets.keys(), key=len, reverse=True):
        if key and key in text_low and (key.startswith("机") or any(w in key for w in ["moto", "motor", "bike", "车"])):
            return assets[key]
    for key, path in assets.items():
        if key.startswith("机") or any(w in key for w in ["moto", "motor", "bike", "摩托"]):
            return path
    return None


def apply_vehicle_hint(shot, text):
    if not any(w in str(text or "") for w in ["摩托", "机车", "骑车", "骑着"]):
        return
    shot["载具"] = "摩托"
    model = match_vehicle_asset(text, _ASSETS)
    if model:
        shot["载具模型"] = model


# 不再注入与当前故事无关的默认舞台。场景资产只来自智能体输出的资产表。
DEFAULT_PROPS = []


def parse_pos(s):
    try:
        return [float(x) for x in s.split(",")]
    except Exception:
        return None


def parse_subject(token):
    raw = token.strip()
    pose_match = POSE_RE.search(raw)
    bind_match = BIND_RE.search(raw)
    # 姿态是主体元数据，不是颜色的一部分；先剥离再走原有坐标/颜色解析。
    clean = BIND_RE.sub("", POSE_RE.sub("", raw))
    m = SUBJ_RE.match(clean)
    if not m:
        return None
    pos = parse_pos(m.group("pos"))
    if not pos:
        return None
    subj = {"名称": m.group("name"), "位置": pos}
    end = m.group("end")
    if end:
        subj["终点"] = parse_pos(end)
    color = COLOR_MAP.get(m.group("color"))
    if color:
        subj["颜色"] = color
    if pose_match:
        pose_map = {"躺": "lying", "躺卧": "lying", "仰卧": "lying", "坐": "sitting", "坐姿": "sitting", "站": "standing", "站姿": "standing"}
        subj["姿态"] = pose_map.get(pose_match.group(1), "standing")
    if bind_match:
        subj["载具绑定"] = bind_match.group(1).strip()
    model = match_asset(subj, _ASSETS)
    if model:
        subj["模型"] = model
    return subj


def parse_camera(token):
    m = CAM_RE.match(token.strip())
    if not m:
        return None
    cam = {"位置": parse_pos(m.group("pos")), "目标": parse_pos(m.group("tar"))}
    if m.group("focal"):
        cam["焦距"] = int(m.group("focal"))
    return cam


# 基础体适合普通家具；镜头会穿越/掠过的结构必须保留最小可读轮廓，
# 不能把门洞、棚架、车辆又压回一块实心 box。
ASSET_TYPES = {"box", "cylinder", "sphere", "门洞框", "棚架", "电驱车", "立杆设备"}


# 预演全部使用米制。这里不是把美术资产强行做成同一大小，而是给镜头
# 最常用、且直接决定人物避碰和景别的街道类基础物体加安全边界。
# 保留作者在区间内给出的尺寸；只有明显失真时才回正。
REAL_WORLD_DIMENSIONS = {
    "电驱车": ((1.7, 2.3), (0.60, 0.90), (0.90, 1.40)),
    "门洞框": ((1.8, 5.0), (0.12, 0.80), (2.10, 3.50)),
    "棚架": ((2.5, 6.0), (1.80, 4.0), (2.30, 3.20)),
    "立杆设备": ((0.20, 0.80), (0.20, 0.80), (2.00, 4.50)),
}


def _clamp(value, low, high):
    return max(low, min(high, float(value)))


def normalize_real_world_scales(props):
    """将结构性街景资产限制在可信米制区间，并补齐可见单向车道宽度。"""
    for prop in props:
        kind = str(prop.get("类型") or "box")
        name = str(prop.get("名称") or "")
        size = list(prop.get("尺寸") or [])
        if len(size) != 3:
            continue
        bounds = REAL_WORLD_DIMENSIONS.get(kind)
        if bounds:
            original = list(size)
            size = [_clamp(size[i], *bounds[i]) for i in range(3)]
            if size != original:
                print("[previz-parse] 米制尺度校正 %s: %s -> %s" % (name, original, size))
            prop["尺寸"] = size
            continue
        # 路面仅在作者明确建了可见车道时校正。单向机动车道按 3.5m
        # 处理，长度仍完全尊重镜头所需可见范围；短边判断让横/竖道路都可用。
        if kind == "box" and any(word in name for word in ("单向车道", "机动车道", "行车道")):
            road_axis = 0 if size[0] >= size[1] else 1
            cross_axis = 1 - road_axis
            original = list(size)
            size[cross_axis] = 3.5
            size[2] = _clamp(size[2], 0.02, 0.12)
            if size != original:
                print("[previz-parse] 单向车道宽度校正 %s: %s -> %s" % (name, original, size))
            prop["尺寸"] = size


def parse_asset_line(line):
    """Parse: 名称 | 类型 | [x,y,z] | [宽,深,高] | 颜色.

    位置 is a ground anchor: z=0 means the bottom rests on the ground.
    """
    parts = [p.strip().rstrip("\\\\") for p in line.split("|")]
    if len(parts) < 4 or parts[1].lower() not in ASSET_TYPES:
        return None
    pos_text = parts[2].strip().strip("[]")
    size_text = parts[3].strip().strip("[]")
    pos, size = parse_pos(pos_text), parse_pos(size_text)
    if not pos or len(pos) != 3 or not size:
        return None
    asset_type = parts[1].lower()
    asset = {"名称": parts[0], "类型": asset_type, "位置": pos}
    if asset_type == "cylinder":
        asset["半径"] = float(size[0])
        asset["高度"] = float(size[2] if len(size) >= 3 else size[-1])
    elif asset_type == "sphere":
        asset["半径"] = float(size[0])
    else:
        if len(size) != 3:
            return None
        asset["尺寸"] = size
    color = COLOR_MAP.get(parts[4]) if len(parts) > 4 else None
    if color:
        asset["颜色"] = color
    if len(parts) > 5 and parts[5]:
        # 资产表是镜头唯一事实源的一部分：用途明确说明此资产为何需要，
        # 不能在后续渲染阶段因为正文没有复述名字而丢失。
        asset["镜头用途"] = parts[5]
    # Optional authoring constraint, e.g. “朝向=北” or “朝向=东”.
    for extra in parts[5:]:
        m = re.search(r"朝向\s*[=:：]\s*(北|南|东|西)", extra)
        if m:
            asset["朝向"] = m.group(1)
            break
    return asset


def extract_structured_blocks(text):
    """Read only explicit preview sections from a mixed agent answer.

    This prevents explanatory prose and video prompts from becoming accidental shots.
    """
    # Some agents collapse all records onto one physical line.  The record tag
    # remains unambiguous, so restore one-record-per-line before parsing.
    # 负向后顾：只有当“资产/镜头”前不是汉字时才拆行——保护运镜名以
    # “镜头”结尾（如“超现实镜头 | 档案库…”）不被拦腰切断成幽灵镜头。
    # 富文本画布粘贴时，标题后的换行偶尔会被浏览器吞掉，形成
    # “3D预演镜头表镜头 | S01 | ...”。先把这个明确的标题+记录
    # 边界复原；它不能依赖下面的“前一字符不是汉字”规则，因为“表”
    # 本身就是汉字。
    text = re.sub(
        r"(3D\s*预演(?:场景)?资产(?:表)?|3D\s*场景资产表|3D\s*预演镜头表|3D\s*预演镜头|3D\s*预演数据(?:包)?)\s*(?=(?:资产|镜头)\s*\|)",
        r"\1\n",
        text,
    )
    text = re.sub(r"(?<![一-龥])(?=(?:资产|镜头)\s*\|)", "\n", text)
    shot_lines, asset_lines = [], []
    mode = ""
    for raw in text.splitlines():
        line = raw.strip().lstrip("-• ").strip()
        line = re.sub(r"^#{1,6}\s*", "", line)  # Markdown headings are valid input.
        heading = re.sub(r"[：:]$", "", line).replace(" ", "")
        if heading in {"3D预演镜头表", "3D预演镜头"}:
            mode = "shots"
            continue
        if heading in {"3D预演场景资产", "3D预演资产表", "3D场景资产表"}:
            mode = "assets"
            continue
        if heading in {"3D预演数据", "3D预演数据包"}:
            mode = "data"
            continue
        if re.match(r"^(参考图镜头资产站位|视频生成提示词)(?:[：:]|$)", line):
            mode = ""
            continue
        # Canvas and LLM output often collapse headings onto the first record
        # (e.g. “3D预演数据资产 | 床 | ...”).  Record prefixes remain
        # reliable, so parse them even when the heading was lost or merged.
        asset_match = re.search(r"(?:^|3D预演数据|3D预演场景资产|3D预演资产表|3D场景资产表)资产\s*\|(.+)$", line)
        if asset_match:
            asset_lines.append(asset_match.group(1).rstrip("\\\\").strip())
            continue
        shot_match = re.search(r"(?:^|3D预演数据|3D预演镜头表|3D预演镜头)镜头\s*\|(.+)$", line)
        if shot_match:
            shot_lines.append(shot_match.group(1).rstrip("\\\\").strip())
            continue
        if mode == "shots" and re.match(r"^镜头\s*\|", line):
            # 镜头表常用“镜头 | S01 | ...”；解析器内部需要从 S01 开始。
            shot_lines.append(re.sub(r"^镜头\s*\|", "", line, count=1).rstrip("\\\\").strip())
        elif mode == "shots" and re.match(r"^(?:S|M)\d+[A-Za-z]*\s*\|", line, re.I):
            shot_lines.append(line.rstrip("\\\\").strip())
        elif mode == "assets" and re.match(r"^资产\s*\|", line):
            # 同理，资产表的记录前缀不是资产名称，必须剥离。
            asset_lines.append(re.sub(r"^资产\s*\|", "", line, count=1).rstrip("\\\\").strip())
        elif mode == "data" and re.match(r"^资产\s*\|", line):
            asset_lines.append(re.sub(r"^资产\s*\|", "", line, count=1).rstrip("\\\\").strip())
        elif mode == "data" and re.match(r"^镜头\s*\|", line):
            shot_lines.append(re.sub(r"^镜头\s*\|", "", line, count=1).rstrip("\\\\").strip())
    return shot_lines, asset_lines


def parse_line(line, idx=0, default_lens=""):
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 4:
        # —— 自然语言宽松解析（画布上直接写描述也能出预演）——
        text = line.strip()
        if not text:
            return None
        sid = ""
        m = re.match(r"^([sS]\d+|M\d+|镜头\d+)[\s,，、:：]*", text)
        if m:
            sid = m.group(1).upper()
            text = text[m.end():]
        dur = 4.0
        m = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:秒|s)(?![a-zA-Z0-9])", text, re.IGNORECASE)
        if m:
            dur = float(m.group(1))
        scale_match = re.search(r"特写|近景|中近景|中景|全景|大远景|远景", text)
        scale = scale_match.group(0) if scale_match else ""
        language_text = text
        languages = extract_camera_languages(text)
        if not languages and default_lens:
            languages = [default_lens]
        for language in languages:
            language_text = language_text.replace(language, "")
        moves = []
        for kw in ["环绕", "升降", "俯拍", "仰拍", "甩镜", "变焦", "推", "拉", "摇", "移", "跟"]:
            if kw in language_text and kw not in moves:
                moves.append(kw)
        move = "+".join(moves) if moves else "固定"
        if not sid:
            sid = "M%02d" % (idx + 1)
        shot = {
            "镜号": sid,
            "时长秒": dur,
            "景别": scale or "中景",
            "运镜": move or "固定",
            "备注": text,
            "原始提示词": text,
        }
        if languages:
            shot["镜头语言"] = languages
            shot["镜头辅助资产"] = support_assets_for_languages(languages)
        beats = extract_camera_beats(text, dur)
        if not beats:
            beats = infer_camera_beats(text, dur)
        if beats:
            shot["镜头节拍"] = beats
        composition = extract_composition_beats(text)
        if composition:
            shot["构图起落幅"] = composition
            if not beats:
                shot["镜头节拍"] = [{"动作": "构图过渡", "开始秒": 0.0, "结束秒": dur}]
        # 自然语言主体 → 用资产人物模型当主体；覆盖男孩/女孩和骑车类描述。
        text_low = text.lower()
        explicit_asset = next((key for key in sorted(_ASSETS.keys(), key=len, reverse=True) if key and key in text_low), "")
        sname = explicit_asset or ("女孩" if any(w in text for w in ["女孩", "女童", "少女", "女人", "女子", "女性"]) else ("男孩" if any(w in text for w in ["男孩", "男童", "少年", "男人", "男子", "男性", "士兵", "战士"]) else ("骑手" if any(w in text for w in ["摩托", "骑车", "骑着"]) else "")))
        if sname:
            subj = {"名称": sname, "位置": [0, -3.0, 0], "颜色": [0.62, 0.45, 0.30]}
            model = match_asset(subj, _ASSETS)
            if model:
                subj["模型"] = model
            # 移动动词 → 纯轴位移动画（终点沿方向平移）
            mv = detect_move(text)
            if mv:
                (dx, dy), md = mv
                subj["终点"] = [round(subj["位置"][0] + dx * md, 2),
                                round(subj["位置"][1] + dy * md, 2), 0]
            shot["主体"] = [subj]
        apply_vehicle_hint(shot, text)
        return shot
    shot = {
        "镜号": parts[0],
        "时长秒": float(re.search(r"[\d.]+", parts[1]).group()) if re.search(r"[\d.]+", parts[1]) else 4.0,
        "景别": parts[2],
        "运镜": parts[3],
        "备注": parts[4] if len(parts) > 4 else "",
        "原始提示词": line.strip(),
    }
    languages = extract_camera_languages(" ".join(str(part) for part in parts[3:5]))
    if not languages and default_lens:
        languages = [default_lens]
    if languages:
        shot["镜头语言"] = languages
        shot["镜头辅助资产"] = support_assets_for_languages(languages)
    if len(parts) > 5 and parts[5]:
        subjects = []
        for token in re.split(r"\s+", parts[5].strip()):
            s = parse_subject(token)
            if s:
                subjects.append(s)
        if subjects:
            shot["主体"] = subjects
            # 备注走位 → 第一个主体位移关键帧（H3 镜头表把走位写在备注：
            # 「走位：从 [x,y,z] 跑到 [x,y,z]」，不写进主体列）
            note_text = parts[4] if len(parts) > 4 else ""
            # 车辆动作同样含“从[...]→[...]”，但那是车辆路径，绝不能
            # 被误套到主体列表第一人（会把车上乘员变成独立移动人物）。
            waypoint = None if re.search(r"(?:车辆动作|载具动作)\s*[：:]", note_text) else extract_waypoint(note_text)
            # 备注走位只是一种兼容兜底。只要主体列里已经有任意明确的
            # “→终点”，就不能把备注中的主角路径强加给列表第一个配角。
            if waypoint and not any(subject.get("终点") for subject in shot["主体"]):
                frm, to = waypoint
                shot["主体"][0]["位置"] = frm
                shot["主体"][0]["终点"] = to
    if len(parts) > 6 and parts[6]:
        cam = parse_camera(parts[6])
        if cam:
            shot["摄像机"] = cam
    beats = extract_camera_beats(shot.get("备注", ""), shot.get("时长秒", 4.0))
    if beats:
        shot["镜头节拍"] = beats
    composition = extract_composition_beats(shot.get("备注", ""))
    if composition:
        shot["构图起落幅"] = composition
        if not beats:
            shot["镜头节拍"] = [{"动作": "构图过渡", "开始秒": 0.0, "结束秒": float(shot.get("时长秒") or 4.0)}]
    vehicle_action = extract_vehicle_action(shot.get("备注", ""))
    if vehicle_action:
        shot["载具动作"] = vehicle_action
    apply_vehicle_hint(shot, shot.get("备注", ""))
    return shot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="画布镜头表文本文件")
    ap.add_argument("--output", required=True, help="输出 previz JSON")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--assets-dir", default="", help="自定义资产文件夹（用户选择），为空用默认")
    a = ap.parse_args()

    global _ASSETS, ASSET_DIR
    if getattr(a, "assets_dir", ""):
        ASSET_DIR = Path(a.assets_dir)
    else:
        ASSET_DIR = None
    _ASSETS = scan_assets()
    print("[previz-parse] 资产:", list(_ASSETS.keys()))

    with open(a.input, "r", encoding="utf-8") as f:
        text = f.read()

    structured_shots, structured_assets = extract_structured_blocks(text)
    # If the answer contains an explicit 3D section, it is authoritative.  Keep
    # legacy plain-text support only for direct hand-authored shot lists.
    source_lines = structured_shots or text.splitlines()
    props = [asset for asset in (parse_asset_line(line) for line in structured_assets) if asset]
    shots = []
    for idx, line in enumerate(source_lines):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        shot = parse_line(line, idx, default_lens="")
        if shot:
            shots.append(shot)
        else:
            print("[warn] 无法解析行: %s" % line, file=sys.stderr)

    # 车辆动作不是可选的文学描述，而是后端要执行的资产动画合同。某些
    # 画布/LLM 回写会错误漏掉资产表行；此时必须从动作终点补回车辆，
    # 否则乘员没有可绑定的座垫枢轴、车辆动作也会静默失效。
    prop_names = {str(prop.get("名称") or "") for prop in props}
    for shot in shots:
        action = shot.get("载具动作") or {}
        vehicle_name = str(action.get("名称") or "").strip()
        end = action.get("终点")
        if not vehicle_name or vehicle_name in prop_names or not isinstance(end, list) or len(end) != 3:
            continue
        props.append({
            "名称": vehicle_name, "类型": "电驱车", "位置": end,
            "尺寸": [1.9, 0.7, 1.1], "颜色": COLOR_MAP["深灰"],
            "镜头用途": f"{shot.get('镜号', 'S01')}车辆动作自动补全",
        })
        prop_names.add(vehicle_name)
        print("[previz-parse] 从车辆动作补全资产:", vehicle_name)

    normalize_real_world_scales(props)

    data = {
        "项目": "画布镜头表预演",
        "fps": a.fps,
        "分辨率": [a.width, a.height],
        "背景颜色": [0.05, 0.06, 0.09],
        "地面颜色": [0.16, 0.16, 0.18],
        "地面大小": 80,
        "场景": {"道具": props or DEFAULT_PROPS},
        "镜头": shots,
    }
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("[previz-parse] %d 个镜头 -> %s" % (len(shots), a.output))


if __name__ == "__main__":
    main()
