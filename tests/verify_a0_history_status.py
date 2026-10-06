# -*- coding: utf-8 -*-
"""A0 判定验证脚本（2026-10-01）——用真实数据验，不靠"跑一个看看"。

A0 修的是**失败路径**，跑一个成功的工作流什么都看不出来。这个脚本直接连 ComfyUI
拉 /history，对每一条真实记录跑 comfy_flow_service.history_failure_reason()，
把「outputs 里有东西、但 status 说失败」的条目揪出来——那正是旧代码会误判成
"完成"、并把预览图当产物回填画布的假成功条目。

用法（ComfyUI 必须在跑，默认 8188）：
    python tests/verify_a0_history_status.py
    python tests/verify_a0_history_status.py --base http://127.0.0.1:8188

不需要重启 MyridTV 后端——本脚本直接 import 后端模块跑判定函数。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, APP_ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import comfy_flow_service  # noqa: E402


def fetch_history(base, timeout=15):
    url = base.rstrip("/") + "/history"
    request = urllib.request.Request(url, headers={"Content-Type": "application/json"}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def count_outputs(history):
    outputs = history.get("outputs") if isinstance(history, dict) else {}
    files = 0
    if isinstance(outputs, dict):
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            for key in ("images", "videos", "gifs"):
                value = node_output.get(key)
                if isinstance(value, list):
                    files += len(value)
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8188")
    args = parser.parse_args()

    try:
        history_all = fetch_history(args.base)
    except Exception as exc:
        print(f"[FAIL] 连不上 ComfyUI（{args.base}）：{exc}")
        print("       先验 ComfyUI 是不是在跑：curl http://127.0.0.1:8188/system_stats")
        return 2

    if not isinstance(history_all, dict) or not history_all:
        print("[WARN] /history 是空的——还没跑过任务，或 history 被清空了。")
        print("       这条路径下脚本验不出东西，请改用「跑一个会失败的任务」来验证。")
        return 0

    total = 0
    fake_success = []   # outputs 有东西，但其实是失败 → 旧代码会误判"完成"
    real_error = []     # 失败且没有产出 → 旧代码也能看出来的
    clean_ok = 0

    for prompt_id, history in history_all.items():
        if not isinstance(history, dict):
            continue
        total += 1
        files = count_outputs(history)
        reason = comfy_flow_service.history_failure_reason(history)
        status = history.get("status") if isinstance(history.get("status"), dict) else {}
        status_str = str(status.get("status_str") or "-")
        completed = status.get("completed")
        if reason:
            entry = (prompt_id, files, status_str, completed, reason)
            if files:
                fake_success.append(entry)
            else:
                real_error.append(entry)
        else:
            clean_ok += 1

    print(f"ComfyUI history 共 {total} 条")
    print(f"  判定成功（会正常收集产出）      : {clean_ok}")
    print(f"  判定失败且没有产出              : {len(real_error)}")
    print(f"  判定失败但 outputs 里有东西     : {len(fake_success)}  <-- 假成功，重点看这里")
    print()

    if fake_success:
        print("=" * 72)
        print("以下条目：ComfyUI 说「失败」，但 outputs 里躺着文件。")
        print("旧代码只看 outputs → 会判成完成，并把这些文件（多半是过程预览图）")
        print("当产物回填进画布。新代码会把它们判成失败，不回填。")
        print("=" * 72)
        for prompt_id, files, status_str, completed, reason in fake_success[:20]:
            print(f"\n  prompt_id : {prompt_id}")
            print(f"  status    : status_str={status_str} completed={completed}")
            print(f"  outputs   : {files} 个文件")
            print(f"  新版判定  : {reason}")
    else:
        print("[OK] 现有 history 里没有「假成功」条目。")
        print("     说明：要么你没跑过会失败的任务，要么 history 已被清理。")
        print("     这不代表修复没生效——要验，需要跑一个**会失败**的任务。")

    print()
    print("=" * 72)
    print("怎么造一个「会失败」的任务来验证（三选一，挑最省事的）：")
    print("=" * 72)
    print("  1. 视频工作流少连一张参考图 → 执行期断粮报错，但前面的预览节点已出图")
    print("  2. 把某个中间节点 Ctrl+B bypass → 下游收到 None（MMH3 的 NoneType 就是这么来的）")
    print("  3. 提交一个参数非法的工作流 → 校验失败，看报错里有没有带节点号")
    print()
    print("验什么（重启后端后）：")
    print("  - 节点显示「失败」而不是「完成」")
    print("  - 报错信息里有具体节点号（如 节点 167），不再只有一句笼统的「执行失败」")
    print("  - 节点上不会被填入预览图")
    return 0


if __name__ == "__main__":
    sys.exit(main())
