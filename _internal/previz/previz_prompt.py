#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从预演镜头数据包生成 AI 视频提示词；只读取结构化 JSON，不重写镜头意图。"""
import argparse
import json
from pathlib import Path


def subject_text(subjects):
    items = []
    for subject in subjects or []:
        name = str(subject.get("名称") or "主体")
        pos = subject.get("位置") or [0, 0, 0]
        item = f"{name}位于[{','.join(str(v) for v in pos)}]"
        if subject.get("终点"):
            item += f"，移动至[{','.join(str(v) for v in subject['终点'])}]"
        items.append(item)
    return "；".join(items) or "无人物入画"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    out = ["# 视频生成提示词（由 3D预演镜头数据生成）", ""]
    for shot in data.get("镜头") or []:
        sid = shot.get("镜号", "镜头")
        duration = shot.get("时长秒", 4)
        scale = shot.get("景别", "中景")
        # 优先保留用户/LLM 写入的完整中文镜头语言；没有时才用物理运镜字段。
        motion = " + ".join(shot.get("镜头语言") or []) or shot.get("运镜", "固定")
        note = str(shot.get("备注") or "").strip()
        out.append(f"{sid}（{duration}秒）：{note}；{scale}，{motion}；主体：{subject_text(shot.get('主体'))}。保持镜头目标对准主体或关键道具，稳定电影感构图。")
        out.append("")
    Path(args.output).write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
