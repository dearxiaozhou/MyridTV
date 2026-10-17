#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动打开预演工程时：把当前画布 ID / 代理地址填入 myridtv 插件面板并保存。
用法: blender.exe file.blend --python open_with_canvas.py -- --canvas-id XXX --proxy-url http://127.0.0.1:3113 --task-id rhproxy_xxx
"""
import bpy
import sys
import time

args = {}
raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
for i in range(0, len(raw) - 1, 2):
    args[raw[i]] = raw[i + 1]

CANVAS_ID = args.get("--canvas-id", "").strip()
PROXY_URL = args.get("--proxy-url", "http://127.0.0.1:3107").strip()
TASK_ID = args.get("--task-id", "").strip()

_fill_done = {"ok": False, "err": ""}


def _fill():
    s = bpy.context.scene
    try:
        if hasattr(s, "wcstv_bridge"):
            s.wcstv_bridge.canvas_id = CANVAS_ID
            s.wcstv_bridge.proxy_url = PROXY_URL
            # 任务 ID（回传完全依赖插件：推送时带回，视频才落回原节点）；老插件无该属性时跳过
            if TASK_ID:
                try:
                    s.wcstv_bridge.task_id = TASK_ID
                    print("[wcstv] task_id filled:", TASK_ID)
                except Exception as e:
                    print("[wcstv] task_id fill skipped:", e)
            # 保存文件，保证下次打开面板仍有画布 ID
            try:
                bpy.ops.wm.save_mainfile()
            except Exception as e:
                print("[wcstv] save failed:", e)
            _fill_done["ok"] = True
            print("[wcstv] canvas_id filled:", CANVAS_ID, "saved")
        else:
            _fill_done["err"] = "wcstv_bridge 属性未注册（插件未启用？）"
            print("[wcstv] wcstv_bridge missing")
    except Exception as e:
        _fill_done["err"] = str(e)
        print("[wcstv] fill failed:", e)
    return None


# 插件加载完成后再设置（延迟 3 秒）
bpy.app.timers.register(_fill, first_interval=3.0)
print("[wcstv] scheduled fill in 3s", CANVAS_ID)
