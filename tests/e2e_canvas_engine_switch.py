# -*- coding: utf-8 -*-
"""
e2e_canvas_engine_switch.py
============================
守护「生成引擎切换」交互链路（阶段 1，2026-09-21）。

背景：用户工作流分本地（ComfyUI）+ 云端（RunningHub/火山引擎）两套并行，
引擎切换必须可靠。切换入口在 comfy 节点 composer 的「合并 pill」（平台+工作流合并），
引擎下拉收进该 pill 的弹层（自研深色弹层，非原生 select）。

交互链路（真实 UI）：
1. 创建 comfy 节点 → composer 变 comfy-layout
2. 点 .workflow-control .smart-pill → 弹出合并弹层
3. 弹层「生成引擎」分组里点 .direct-option（RunningHub/火山引擎/ComfyUI生成）
4. 断言 .composer 布局类 + #engineSelect 值 联动变化

断言锚点（真实 DOM）：
- .composer 布局类：comfy-layout / api-single-row（api）/ rh-single-row（RH 或单行）
- #engineSelect 值：comfy / api / volcengine
- 合并 pill 文字变化（"SeedVR2图片放大" ↔ "RunningHub · ..."）

依赖：隔离测试实例 3217（tests/launch_test_instance.py）
"""
import json, sys
from playwright.sync_api import sync_playwright

import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")


def check(label, ok, detail=""):
    sym = "PASS" if ok else "FAIL"
    print(f"{sym} - {label} | {detail}")
    return 1 if ok else 0


def main():
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
            headless=True,
            args=["--no-sandbox"],
        )
        ctx = browser.new_context(viewport={"width": 1680, "height": 980})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        def rc(route):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"proxy": {"base_url": BASE}}))

        page.route("**/static/app_config.json*", rc)
        VID = {"99": {"class_type": "VHS_VideoCombine"}, "88": {"class_type": "MiniMaxH3ReferenceToVideo"}}
        IMG = {"50": {"class_type": "SaveImage"}, "47": {"class_type": "KSamplerAdvanced"}}
        def prov_route(route):
            body = {"providers": [
                {"id": "p_img", "name": "图片平台A", "enabled": True, "image_models": ["flux-dev"], "video_models": []},
                {"id": "runninghub", "name": "RH-API", "enabled": True, "protocol": "runninghub",
                 "image_models": [],
                 "rh_workflows": [{"id": "wvid", "title": "Mock视频流", "enabled": True, "workflowJson": VID},
                                   {"id": "wimg", "title": "Mock图片流", "enabled": True, "workflowJson": IMG}],
                 "rh_apps": []}]}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
        page.route("**/api/providers**", prov_route)
        page.goto(f"{BASE}/smart-canvas.html", wait_until="networkidle")
        page.wait_for_timeout(1500)

        # 创建 comfy 节点
        page.click("#canvasAddToggle")
        page.wait_for_timeout(300)
        page.click('[data-create-type="comfy"]')
        page.wait_for_timeout(1200)

        def composer_cls():
            return page.eval_on_selector(".composer", "el => el.className")

        def engine_val():
            return page.evaluate("() => settings.engine")

        def pill_text():
            return page.eval_on_selector(".unified-picker-pill", "el => el.innerText")

        def pick_unified(title_kw):
            """打开统一面板，点标题含关键字的条目"""
            page.click(".unified-picker-pill")
            page.wait_for_timeout(400)
            page.click(f".unified-option:has-text('{title_kw}')")
            page.wait_for_timeout(900)

        # === 初始态：comfy 布局 ===
        c0 = composer_cls()
        v0 = engine_val()
        failures += not check("初始 composer 为 comfy-layout", "comfy-layout" in c0, c0)
        failures += not check("初始 engine=comfy", v0 == "comfy", v0)
        failures += not check("引擎下拉已隐藏",
                              page.evaluate("() => getComputedStyle(document.getElementById('engineSelect')).display") == "none")

        # === 切换 1：comfy → RunningHub 图片工作流（mock 或真实条目）===
        pick_unified("Mock图片流") if page.locator(".unified-option:has-text('Mock图片流')").count() else pick_unified("Krea2")
        c1 = composer_cls()
        v1 = engine_val()
        failures += not check("选 RH 条目后 engine=runninghub", v1 == "runninghub", v1)
        failures += not check("选 RH 条目后 composer 含 rh 布局", "rh-single-row" in c1, c1)
        api_pill = page.evaluate("() => CanvasUnifiedPicker.renderPill ? document.querySelector('.unified-picker-pill').innerText : ''")
        # 2026-09-25 拍板：pill 只显示条目名（不拼平台标题）
        failures += not check("统一 pill 只显示条目名(无平台前缀)", api_pill.strip() == "Mock图片流", api_pill[:80])

        # === 切换 2：→ ComfyUI 条目（Krea 图流）===
        pick_unified("Krea")
        v2 = engine_val()
        failures += not check("选 Comfy 条目后 engine=comfy", v2 == "comfy", v2)
        # === 切换 3：→ 图片平台A 的模型 ===
        pick_unified("flux-dev")
        v3 = engine_val()
        c3 = composer_cls()
        failures += not check("选 API 条目后 engine=api", v3 == "api", v3)
        failures += not check("api 布局含 api-single-row", "api-single-row" in c3, c3)

        # 无 JS 报错
        real_errors = [e for e in errors if "WebSocket" not in e and "stats" not in e]
        failures += not check("无 JS 报错", len(real_errors) == 0, str(real_errors[:3]))

        browser.close()

    total = 12
    passed = total - failures
    print(f"\nRESULT: {passed}/{total}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
