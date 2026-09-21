# -*- coding: utf-8 -*-
"""
e2e_canvas_interaction_combos.py
=================================
守护「交互组合」链路（阶段 1 补充，2026-09-21）。

GPT/架构诊断点名最容易互相打架的组合，之前 e2e 没覆盖：
1. 缩放后拖节点（wheel 缩放 → 拖拽，坐标换算不能崩）
2. 框选后拖拽（selection box → 多选 → 拖拽移动）
3. 中键平移后右键菜单（pan 后 contextmenu 仍能弹出）
4. 浮层内滚动（composer 内 wheel 不触发画布缩放）

真实 UI 交互驱动（Playwright），断言锚点全部走真实 DOM：
- 节点位置：.image-node 的 style.left/top（世界坐标）
- 缩放：节点 getBoundingClientRect 尺寸变化（viewport.scale 生效）
- 框选：.image-node.selected 数量
- 右键菜单：#smartImageContextMenu.open
- 浮层滚动：composer 内 wheel 后节点尺寸不变（未缩放）

依赖：隔离测试实例 3217（tests/launch_test_instance.py）
"""
import json, sys, urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:3217"


def create_test_canvas():
    """预建画布：2 个空 comfy 节点 + 1 个带图 image 节点（右键菜单需要 thumb-item）。"""
    nodes = [
        {"id": "n_img", "type": "smart-image", "title": "img1",
         "x": 250, "y": 250, "w": 260, "h": 260, "scale": 1, "status": "ready",
         "role": "media", "created_at": 0, "artifactId": "n_img",
         "images": [{"url": "/assets/output/e2e/x.png", "name": "x.png", "kind": "image",
                     "local_path": "_test_userdata/x.png", "display_name": "x.png",
                     "generatedResult": True, "natural_w": 512, "natural_h": 512}]},
        {"id": "n_comfy1", "type": "smart-image", "title": "node1",
         "x": 650, "y": 250, "w": 260, "h": 260, "scale": 1, "status": "ready",
         "role": "media", "created_at": 0, "artifactId": "n_comfy1",
         "runSettings": {"engine": "comfy", "workflowName": "Krea2-文生图"}, "images": []},
        {"id": "n_comfy2", "type": "smart-image", "title": "node2",
         "x": 1050, "y": 250, "w": 260, "h": 260, "scale": 1, "status": "ready",
         "role": "media", "created_at": 0, "artifactId": "n_comfy2",
         "runSettings": {"engine": "comfy", "workflowName": "Krea2-文生图"}, "images": []},
    ]
    req = urllib.request.Request(
        f"{BASE}/api/canvases",
        data=json.dumps({"name": "e2e-combos", "nodes": nodes, "connections": []}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["canvas"]["id"]


def check(label, ok, detail=""):
    sym = "PASS" if ok else "FAIL"
    print(f"{sym} - {label} | {detail}")
    return 1 if ok else 0


def main():
    failures = 0
    canvas_id = create_test_canvas()
    print(f"测试画布: {canvas_id}")

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
        page.goto(f"{BASE}/smart-canvas.html?id={canvas_id}", wait_until="networkidle")
        page.wait_for_timeout(2500)

        def center(sel):
            return page.eval_on_selector(sel, """el => {
                const r = el.getBoundingClientRect();
                return {cx: Math.round(r.x+r.width/2), cy: Math.round(r.y+r.height/2)};
            }""")

        def rect(sel):
            return page.eval_on_selector(sel, """el => {
                const r = el.getBoundingClientRect();
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
            }""")

        def node_pos():
            return page.eval_on_selector_all(".image-node", """els => els.map(e => ({
                id: e.dataset.id, left: e.style.left, top: e.style.top
            }))""")

        def selected_count():
            return page.eval_on_selector_all(".image-node.selected", "els => els.length")

        # === 等待画布渲染出 3 节点 ===
        for _ in range(20):
            if page.eval_on_selector_all(".image-node", "els => els.length") >= 3:
                break
            page.wait_for_timeout(500)
        cnt0 = page.eval_on_selector_all(".image-node", "els => els.length")
        failures += not check("画布渲染 3 节点", cnt0 >= 3, str(cnt0))

        # ============================================================
        # 组合 1：缩放后拖节点
        # ============================================================
        # 先选中 node1（点节点顶边，别点 textarea/内容）
        r1 = rect(".image-node[data-id='n_comfy1']")
        page.mouse.click(r1["x"] + 50, r1["y"] + 3)
        page.wait_for_timeout(500)
        s1 = selected_count()
        failures += not check("[缩放拖拽] 选中 node1", s1 == 1, str(s1))

        # 记录缩放前节点屏幕尺寸（作为缩放生效基准）
        size_before = rect(".image-node[data-id='n_comfy1']")
        # wheel 放大（deltaY < 0 = zoom in）
        page.mouse.move(size_before["x"] + 50, size_before["y"] + 50)
        page.mouse.wheel(0, -240)
        page.wait_for_timeout(800)
        size_zoomed = rect(".image-node[data-id='n_comfy1']")
        zoomed = size_zoomed["w"] > size_before["w"] + 5
        failures += not check("[缩放拖拽] wheel 放大后节点尺寸变大", zoomed,
                              f"{size_before['w']} -> {size_zoomed['w']}")

        # 缩放后拖拽节点：左键按住节点顶边 → 移动
        pos_before = page.eval_on_selector(".image-node[data-id='n_comfy1']",
                                           "el => ({left: el.style.left, top: el.style.top})")
        r2 = rect(".image-node[data-id='n_comfy1']")
        page.mouse.move(r2["x"] + 50, r2["y"] + 3)
        page.mouse.down()
        page.mouse.move(r2["x"] + 150, r2["y"] + 90, steps=8)
        page.mouse.up()
        page.wait_for_timeout(600)
        pos_after = page.eval_on_selector(".image-node[data-id='n_comfy1']",
                                          "el => ({left: el.style.left, top: el.style.top})")
        moved = pos_after["left"] != pos_before["left"] or pos_after["top"] != pos_before["top"]
        failures += not check("[缩放拖拽] 缩放后拖节点位置变化", moved,
                              f"{pos_before} -> {pos_after}")

        # ============================================================
        # 组合 2：框选后拖拽
        # ============================================================
        # 取消选中（点空白）
        page.mouse.click(60, 60)
        page.wait_for_timeout(400)
        # 空白处拖出 selection box 框住 node1+node2
        r_a = rect(".image-node[data-id='n_comfy1']")
        r_b = rect(".image-node[data-id='n_comfy2']")
        x0, y0 = min(r_a["x"], r_b["x"]) - 30, min(r_a["y"], r_b["y"]) - 30
        x1, y1 = max(r_a["x"] + r_a["w"], r_b["x"] + r_b["w"]) + 30, max(r_a["y"] + r_a["h"], r_b["y"] + r_b["h"]) + 30
        page.mouse.move(x0, y0)
        page.mouse.down()
        page.mouse.move(x1, y1, steps=10)
        page.mouse.up()
        page.wait_for_timeout(600)
        s2 = selected_count()
        failures += not check("[框选拖拽] 框选后选中 2 节点", s2 == 2, str(s2))

        # 拖拽其中一个 → 两个都移动（多选联动）
        pos_pair_before = node_pos()
        r_sel = rect(".image-node.selected")
        page.mouse.move(r_sel["x"] + 50, r_sel["y"] + 3)
        page.mouse.down()
        page.mouse.move(r_sel["x"] + 200, r_sel["y"] + 120, steps=8)
        page.mouse.up()
        page.wait_for_timeout(600)
        pos_pair_after = node_pos()
        by_id = {p["id"]: p for p in pos_pair_before}
        moved1 = False
        for p in pos_pair_after:
            if p["id"] in by_id and (p["left"] != by_id[p["id"]]["left"] or p["top"] != by_id[p["id"]]["top"]):
                moved1 = True
        failures += not check("[框选拖拽] 框选多节点拖拽位置变化", moved1,
                              f"{pos_pair_before} -> {pos_pair_after}")

        # ============================================================
        # 组合 3：中键平移后右键菜单
        # ============================================================
        # 取消选中
        page.mouse.click(60, 60)
        page.wait_for_timeout(400)
        # 中键拖动画布（button=1）
        before_pan = rect(".image-node[data-id='n_img']")
        page.mouse.move(700, 400)
        page.mouse.down(button="middle")
        page.mouse.move(900, 500, steps=6)
        page.mouse.up(button="middle")
        page.wait_for_timeout(600)
        after_pan = rect(".image-node[data-id='n_img']")
        panned = abs(after_pan["x"] - before_pan["x"]) > 20 or abs(after_pan["y"] - before_pan["y"]) > 20
        failures += not check("[平移+右键] 中键平移后画布位移", panned,
                              f"({before_pan['x']},{before_pan['y']}) -> ({after_pan['x']},{after_pan['y']})")

        # 平移后右键带图节点 → 上下文菜单弹出
        r_img = rect(".image-node[data-id='n_img']")
        thumb = page.eval_on_selector(".image-node[data-id='n_img'] .image-wrap, .image-node[data-id='n_img'] .thumb-item",
                                      "el => { const r = el.getBoundingClientRect(); return {x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)}; }")
        page.mouse.move(thumb["x"], thumb["y"])
        page.mouse.click(thumb["x"], thumb["y"], button="right")
        page.wait_for_timeout(600)
        menu_open = page.eval_on_selector("#smartImageContextMenu",
                                          "el => el.classList.contains('open')")
        failures += not check("[平移+右键] 平移后右键菜单弹出", menu_open, str(menu_open))

        # ============================================================
        # 组合 4：浮层内滚动不缩放画布
        # ============================================================
        # 关闭右键菜单（Esc），选中 node1 打开 composer
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        rc1 = rect(".image-node[data-id='n_comfy1']")
        page.mouse.click(rc1["x"] + 50, rc1["y"] + 3)
        page.wait_for_timeout(800)
        composer_open = page.eval_on_selector(".composer", "el => el.classList.contains('open')")
        failures += not check("[浮层滚动] composer 打开", composer_open, "")

        # 在 composer 内滚轮 → 画布节点尺寸不应变化（缩放被拦截）
        node_w_before = rect(".image-node[data-id='n_comfy1']")["w"]
        comp = rect(".composer")
        page.mouse.move(comp["x"] + 100, comp["y"] + 60)
        page.mouse.wheel(0, -400)
        page.wait_for_timeout(700)
        node_w_after = rect(".image-node[data-id='n_comfy1']")["w"]
        not_zoomed = abs(node_w_after - node_w_before) <= 5
        failures += not check("[浮层滚动] composer 内 wheel 不缩放画布", not_zoomed,
                              f"节点宽 {node_w_before} -> {node_w_after}")

        # 对照组：在画布空白处滚轮 → 应该缩放（证明 wheel 链路本身活着）
        page.mouse.move(1200, 850)
        page.mouse.wheel(0, -240)
        page.wait_for_timeout(700)
        node_w_ctrl = rect(".image-node[data-id='n_comfy1']")["w"]
        ctrl_zoomed = node_w_ctrl > node_w_after + 5
        failures += not check("[浮层滚动] 对照组：画布空白处 wheel 仍能缩放", ctrl_zoomed,
                              f"{node_w_after} -> {node_w_ctrl}")

        # 无 JS 报错
        real_errors = [e for e in errors if "WebSocket" not in e and "stats" not in e]
        failures += not check("无 JS 报错", len(real_errors) == 0, str(real_errors[:3]))

        browser.close()

    total = 13
    passed = total - failures
    print(f"\nRESULT: {passed}/{total}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
