# -*- coding: utf-8 -*-
"""
e2e_canvas_node_lifecycle.py
=============================
守护「节点生命周期」交互链路（阶段 1，2026-09-21）：
创建 → 选中 → 拖拽移动 → 删除 → 复制。

真实 UI 交互：
1. 创建：点 #canvasAddToggle → 点 [data-create-type="comfy"|"image"|"prompt"] → 节点出现
2. 选中：点节点 → 节点获得 .selected class
3. 拖拽移动：鼠标拖节点（comfy/image 节点可拖）→ style.left/top 变化
4. 删除：选中后按 Delete 键 → 节点移除
5. 复制：Alt+拖拽依赖完整 canvas 初始化（测试环境 canvas 为 null 会崩），
   故用 page.evaluate 调 duplicateSmartNodeWithConnections 守护复制逻辑本身
   （真实 app 里 canvas 已初始化，Alt+拖拽/右键复制走同一函数）

测试环境初始化：smart-canvas.html 直接打开时 canvas 全局为 null，
复制逻辑依赖 canvas.connections —— 需先补 window.canvas = {connections: []}。

断言锚点（真实 DOM）：
- .image-node 数量
- .image-node.selected 存在性
- 节点 style.left/top（拖拽移动）
- Delete 后节点消失
- 复制后节点数 +1 且位置偏移 (dx,dy)

依赖：隔离测试实例 3217
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
        page.goto(f"{BASE}/smart-canvas.html", wait_until="networkidle")
        page.wait_for_timeout(1500)

        # 测试环境初始化：canvas 全局补最小对象（真实 app 里已初始化）
        page.evaluate("""() => { if (typeof canvas === 'undefined' || canvas === null) {
            window.canvas = { connections: [], nodes: [] };
        } }""")
        action_module = page.evaluate("typeof CanvasNodeActionController === 'object'")
        failures += not check("通用节点动作控制器加载", action_module, "")
        gesture_module = page.evaluate("""typeof CanvasNodeGestureController === 'object'
            && typeof CanvasNodeGestureController.queueDragFrame === 'function'
            && typeof CanvasNodeGestureController.finishDrag === 'function'""")
        failures += not check("节点拖动缩放控制器加载", gesture_module, "")

        def node_count():
            return page.eval_on_selector_all(".image-node", "els => els.length")

        def create_node(create_type, wait=1100):
            page.click("#canvasAddToggle")
            page.wait_for_timeout(300)
            page.click(f'[data-create-type="{create_type}"]')
            page.wait_for_timeout(wait)

        def center_of(sel):
            return page.eval_on_selector(sel, """el => {
                const r = el.getBoundingClientRect();
                return {cx: Math.round(r.x+r.width/2), cy: Math.round(r.y+r.height/2)};
            }""")

        # === 1. 创建 comfy 节点（可拖拽的类型）===
        create_node("comfy")
        cnt1 = node_count()
        failures += not check("创建 comfy 节点后数量=1", cnt1 == 1, str(cnt1))
        sel1 = page.eval_on_selector(".image-node.selected", "el => !!el")
        failures += not check("新节点已选中(.selected)", sel1, "")

        # === 2. 拖拽移动（comfy 节点可拖）===
        before = page.eval_on_selector(".image-node.selected", "el => ({left: el.style.left, top: el.style.top})")
        box = center_of(".image-node.selected")
        page.mouse.move(box["cx"], box["cy"])
        page.mouse.down()
        page.mouse.move(box["cx"]+150, box["cy"]+90, steps=8)
        page.mouse.up()
        page.wait_for_timeout(500)
        after = page.eval_on_selector(".image-node.selected", "el => ({left: el.style.left, top: el.style.top})")
        moved = after["left"] != before["left"] or after["top"] != before["top"]
        failures += not check("拖拽移动后 left/top 变化", moved, f"{before} -> {after}")

        # === 3. 创建第 2 节点（image）===
        create_node("image", 1000)
        cnt2 = node_count()
        failures += not check("创建第 2 节点后数量=2", cnt2 == 2, str(cnt2))

        # === 4. 删除（Delete 键删选中节点）===
        page.keyboard.press("Delete")
        page.wait_for_timeout(800)
        cnt3 = node_count()
        failures += not check("Delete 后节点数减少到 1", cnt3 == 1, f"{cnt2} -> {cnt3}")

        # === 5. 复制（evaluate 驱动复制逻辑，补 canvas 后）===
        nid = page.eval_on_selector(".image-node", "el => el.getAttribute('data-id')")
        pos_before = page.eval_on_selector(".image-node", "el => ({left: parseFloat(el.style.left), top: parseFloat(el.style.top)})")
        page.evaluate("(id) => duplicateSmartNodeWithConnections(id, 48, 36)", nid)
        page.wait_for_timeout(800)
        cnt4 = node_count()
        failures += not check("复制后节点数=2", cnt4 == 2, str(cnt4))

        # === 6. 复制节点位置偏移 (48,36) ===
        pos_after = page.eval_on_selector_all(".image-node", """els => els.map(e=>({
            left: parseFloat(e.style.left), top: parseFloat(e.style.top),
            selected: e.classList.contains('selected')
        }))""")
        # 找非原节点的复制品
        copies = [p for p in pos_after if abs(p["left"]-pos_before["left"])>1 or abs(p["top"]-pos_before["top"])>1]
        offset_ok = len(copies) == 1 and abs(copies[0]["left"]-pos_before["left"]-48) <= 3 \
                    and abs(copies[0]["top"]-pos_before["top"]-36) <= 3
        failures += not check("复制节点位置偏移 (48,36)", offset_ok, str(pos_after))

        # === 7. 节点工具栏删除按钮 ===
        selected = page.locator(".image-node.selected")
        selected.hover()
        selected.locator(".floating-node-actions .node-delete").click()
        page.wait_for_timeout(500)
        cnt5 = node_count()
        failures += not check("点击节点删除按钮可移除节点", cnt5 == 1, str(cnt5))

        # === 8. 节点缩放（通过真实 prompt 节点右下角手柄）===
        create_node("prompt")
        resize_handle = page.locator(".image-node.selected .node-resize-handle")
        handle_visible = resize_handle.count() == 1 and resize_handle.is_visible()
        failures += not check("可缩放节点显示尺寸手柄", handle_visible, "")
        if handle_visible:
            before_size = page.eval_on_selector(".image-node.selected", "el => ({width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height})")
            handle_box = resize_handle.bounding_box()
            page.mouse.move(handle_box["x"] + handle_box["width"] / 2, handle_box["y"] + handle_box["height"] / 2)
            page.mouse.down()
            page.mouse.move(handle_box["x"] + handle_box["width"] / 2 + 90, handle_box["y"] + handle_box["height"] / 2 + 60, steps=8)
            page.mouse.up()
            page.wait_for_timeout(500)
            after_size = page.eval_on_selector(".image-node.selected", "el => ({width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height})")
            resized = abs(after_size["width"] - before_size["width"]) > 2 or abs(after_size["height"] - before_size["height"]) > 2
            failures += not check("拖动尺寸手柄后节点尺寸变化", resized, f"{before_size} -> {after_size}")
        else:
            failures += 1

        # === 9. 节点接收外部素材（URL 拖放）===
        before_drop = node_count()
        page.locator(".image-node.selected").evaluate("""el => {
            const transfer = new DataTransfer();
            transfer.setData('text/uri-list', 'https://example.test/canvas-drop.png');
            const point = el.getBoundingClientRect();
            el.dispatchEvent(new DragEvent('dragover', {bubbles:true, cancelable:true, dataTransfer:transfer}));
            el.dispatchEvent(new DragEvent('drop', {bubbles:true, cancelable:true, dataTransfer:transfer, clientX:point.x+30, clientY:point.y+30}));
        }""")
        page.wait_for_timeout(700)
        after_drop = node_count()
        failures += not check("拖放外部素材后创建图片节点", after_drop == before_drop + 1, f"{before_drop} -> {after_drop}")

        # 无 JS 报错
        real_errors = [e for e in errors if "WebSocket" not in e and "stats" not in e]
        failures += not check("无 JS 报错", len(real_errors) == 0, str(real_errors[:3]))

        browser.close()

    total = 14
    passed = total - failures
    print(f"\nRESULT: {passed}/{total}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
