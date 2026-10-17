# -*- coding: utf-8 -*-
"""Shared camera-language vocabulary for MyridTV previz.

The public authoring contract is the exact Chinese names in CAMERA_LANGUAGE_NAMES.
Coordinates remain an implementation detail of the renderer.
"""

# 用户定稿的 30 条镜头语言（画布「镜头语言」下拉的 option 值 = 这里的原文）。
# 兼容旧 prompt：旧名（慢推进/转移焦点/180度环绕）也保留，两列都能被子串匹配命中。
CAMERA_LANGUAGE_NAMES = (
    "慢镜头感", "推进 / 慢推", "摇镜", "背景虚化", "低机位", "高机位", "浅景深",
    "中景跟拍", "穿梭镜头", "超现实镜头", "希区柯克变焦", "转移焦点 / 拉焦",
    "蒙太奇", "慢速拉出", "冲击变焦", "上摇镜头", "下摇镜头", "水平摇镜",
    "横移", "渐进变速横移", "吊臂上升", "吊臂下降", "正反打", "鱼眼镜头",
    "第一人称行走", "遮挡物揭示", "穿飞镜头", "前景遮挡转场", "缝隙窥视推进", "180° 环绕",
    # 历史别名（老 prompt 兼容）
    "慢推进", "转移焦点", "180度环绕",
)

# This mapping deliberately reduces authored language to physical camera operations.
# Composition and optical presets are handled separately by the Blender renderer.
MOTION_BY_LANGUAGE = {
    "推进 / 慢推": "推", "摇镜": "摇", "中景跟拍": "跟", "穿梭镜头": "推",
    "超现实镜头": "环绕", "希区柯克变焦": ("推", "变焦"), "慢速拉出": "拉",
    "冲击变焦": "变焦", "上摇镜头": "仰拍", "下摇镜头": "俯拍",
    "水平摇镜": "摇", "横移": "移", "渐进变速横移": "移",
    "吊臂上升": "升降", "吊臂下降": "升降", "第一人称行走": "跟",
    "遮挡物揭示": "移", "穿飞镜头": "推", "缝隙窥视推进": "推",
    "180° 环绕": "环绕",
    # 历史别名
    "慢推进": "推", "转移焦点": "", "180度环绕": "环绕",
}


def extract_camera_languages(text):
    """Return exact, de-duplicated vocabulary matches in authoring order."""
    text = str(text or "")
    return [name for name in CAMERA_LANGUAGE_NAMES if name in text]


def shot_languages(shot):
    values = shot.get("镜头语言") if isinstance(shot, dict) else None
    if isinstance(values, list):
        return [name for name in values if name in CAMERA_LANGUAGE_NAMES]
    text = " ".join(str(shot.get(key) or "") for key in ("运镜", "备注")) if isinstance(shot, dict) else ""
    return extract_camera_languages(text)


def effective_moves(shot):
    """Map exact preset names to renderer operations, then retain legacy operations."""
    result = []
    for name in shot_languages(shot):
        moves = MOTION_BY_LANGUAGE.get(name)
        if isinstance(moves, str):
            moves = (moves,)
        for move in moves or ():
            if move and move not in result:
                result.append(move)
    legacy = str(shot.get("运镜") or "固定") if isinstance(shot, dict) else "固定"
    for move in legacy.split("+"):
        move = move.strip()
        if move in {"推", "拉", "摇", "移", "跟", "环绕", "俯仰", "俯拍", "仰拍", "升降", "甩镜", "变焦", "手持"} and move not in result:
            result.append(move)
    return result or ["固定"]


def support_assets_for_languages(languages):
    """Return deterministic, editable Blender helper assets for a shot language set."""
    languages = set(languages or ())
    plan = []
    if "遮挡物揭示" in languages:
        plan.append({"类型": "遮挡柱", "规则": "镜头与主体之间"})
    if "前景遮挡转场" in languages:
        plan.append({"类型": "转场遮挡", "规则": "镜头前方", "切点": "遮满画面时"})
    if "缝隙窥视推进" in languages:
        plan.append({"类型": "缝隙框", "规则": "镜头前方"})
    if "穿飞镜头" in languages:
        plan.append({"类型": "门框", "规则": "路径中段"})
    if "正反打" in languages:
        plan.append({"类型": "对话站位", "规则": "主体两侧", "说明": "需要两个主体以生成完整正反打"})
    if "蒙太奇" in languages:
        plan.append({"类型": "剪辑标记", "规则": "镜头内部", "说明": "在时间线拆分为多段镜头"})
    return plan
