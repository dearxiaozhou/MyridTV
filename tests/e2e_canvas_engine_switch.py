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

BASE = "http://127.0.0.1:3217"


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

        page.route("**/static/app_config.json", rc)
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
            return page.eval_on_selector("#engineSelect", "el => el.value")

        def pill_text():
            return page.eval_on_selector(".workflow-control .smart-pill", "el => el.innerText")

        # === 初始态：comfy 布局 ===
        c0 = composer_cls()
        v0 = engine_val()
        failures += not check("初始 composer 为 comfy-layout", "comfy-layout" in c0, c0)
        failures += not check("初始 engineSelect=comfy", v0 == "comfy", v0)

        # === 切换 1：comfy → api（RunningHub）===
        page.click(".workflow-control .smart-pill")
        page.wait_for_timeout(400)
        # 弹层「生成引擎」分组选 RunningHub
        page.click(".direct-option:has-text('RunningHub')")
        page.wait_for_timeout(800)
        c1 = composer_cls()
        v1 = engine_val()
        failures += not check("切 api 后 composer 含 api 布局", "api" in c1 and "comfy-layout" not in c1, c1)
        failures += not check("切 api 后 engineSelect=api", v1 == "api", v1)
        # api 布局的合并 pill 显示引擎名
        api_pill = page.eval_on_selector_all(".composer .smart-pill",
            "els => els.filter(e=>e.offsetWidth>0).map(e=>e.innerText)")
        failures += not check("api 布局合并 pill 含 RunningHub",
                              any("RunningHub" in t for t in api_pill), str(api_pill))

        # === 切换 2：api → volcengine（火山引擎）===
        # api 布局下点合并 pill（第一个 smart-pill 是引擎+模型）
        page.click(".composer .smart-pill >> nth=0")
        page.wait_for_timeout(400)
        page.click(".direct-option:has-text('火山引擎')")
        page.wait_for_timeout(800)
        v2 = engine_val()
        c2 = composer_cls()
        failures += not check("切火山后 engineSelect=volcengine", v2 == "volcengine", v2)

        # === 切换 3：volcengine → comfy（ComfyUI生成）===
        # 点合并 pill 切回 comfy
        page.click(".composer .smart-pill >> nth=0")
        page.wait_for_timeout(400)
        page.click(".direct-option:has-text('ComfyUI生成')")
        page.wait_for_timeout(800)
        v3 = engine_val()
        c3 = composer_cls()
        failures += not check("切回 comfy 后 engineSelect=comfy", v3 == "comfy", v3)
        failures += not check("切回 comfy 后 composer 回 comfy-layout", "comfy-layout" in c3, c3)
        # comfy 布局恢复合并 pill（工作流名）
        pill3 = pill_text() if page.eval_on_selector(".workflow-control .smart-pill",
                       "el => !!el") else "(无 workflow-control)"
        failures += not check("comfy 布局恢复 workflow pill", "SeedVR2" in pill3 or "Krea" in pill3 or "MM" in pill3, pill3)

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
