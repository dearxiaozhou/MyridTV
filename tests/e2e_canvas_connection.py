# -*- coding: utf-8 -*-
"""
e2e_canvas_connection.py
=========================
守护「节点连线」交互链路（阶段 1，2026-09-21）：
端口拖拽连线 → canvas.connections 数据建立 → 连线路径渲染 → 断线。

真实 UI 交互：
1. 用 ?id=<画布id> 加载真实画布（canvas 全局初始化，连线逻辑依赖 canvas.connections）
2. 创建 2 个 comfy 节点
3. 取消选中（点空白）→ 逐个拖开节点（避免重叠：重叠时端口被覆盖无法命中）
4. 从一个节点 port-out 拖到另一个节点 port-in → 连线建立
5. 断言 canvas.connections 新增 {from,to,kind:'input'} + connection-layer path 渲染
6. 断线：悬停连线出现剪刀按钮并点击 → canvas.connections 移除

关键教训（2026-09-21 探测）：
- 测试不能裸开 smart-canvas.html——canvas 是模块级闭包变量（let canvas = null），
  由 loadCanvas() 从后端 /api/canvases/{id} 加载。裸开时 canvas 为 null，
  连线 addConnection 读 canvas.connections 直接崩。必须 ?id= 加载真实画布。
- 节点重叠时端口被覆盖（elementFromPoint 命中 node-drop/world 层而非端口），
  必须先取消选中再分别拖开节点到干净位置。
- 端口坐标：读 .node-port 的 getBoundingClientRect 中心点。

依赖：隔离测试实例 3217
"""
import json, sys, urllib.request
from playwright.sync_api import sync_playwright

import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")


def create_test_canvas():
    """通过后端 API 创建一个空画布，返回 id"""
    req = urllib.request.Request(
        f"{BASE}/api/canvases",
        data=json.dumps({"name": "e2e-conn", "nodes": [], "connections": []}).encode(),
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

        page.route("**/static/app_config.json*", rc)
        page.goto(f"{BASE}/smart-canvas.html?id={canvas_id}", wait_until="networkidle")
        page.wait_for_timeout(2500)
        port_module = page.evaluate("typeof CanvasPortGestureController === 'object'")
        failures += not check("端口手势模块加载", port_module, "")

        def create_node(ct, wait=1200):
            page.click("#canvasAddToggle")
            page.wait_for_timeout(300)
            page.click(f'[data-create-type="{ct}"]')
            page.wait_for_timeout(wait)

        def center(sel):
            return page.eval_on_selector(sel, """el => {
                const r = el.getBoundingClientRect();
                return {cx: Math.round(r.x+r.width/2), cy: Math.round(r.y+r.height/2)};
            }""")

        def node_count():
            return page.eval_on_selector_all(".image-node", "els => els.length")

        def connections():
            return page.evaluate("() => (typeof canvas !== 'undefined' && canvas && canvas.connections) || []")

        # === 1. 创建 2 节点 ===
        create_node("comfy")
        create_node("comfy")
        cnt = node_count()
        failures += not check("创建 2 节点", cnt == 2, str(cnt))

        # === 2. 取消选中 + 拖开 node1（左移）===
        page.mouse.click(150, 150)
        page.wait_for_timeout(400)
        b1 = center(".image-node >> nth=1")
        page.mouse.move(b1["cx"], b1["cy"])
        page.mouse.down()
        page.mouse.move(b1["cx"]-260, b1["cy"]+40, steps=8)
        page.mouse.up()
        page.wait_for_timeout(600)

        # === 3. 取消选中 + 拖开 node0（右移）===
        page.mouse.click(150, 150)
        page.wait_for_timeout(300)
        b0 = center(".image-node >> nth=0")
        page.mouse.move(b0["cx"], b0["cy"])
        page.mouse.down()
        page.mouse.move(b0["cx"]+300, b0["cy"]+60, steps=8)
        page.mouse.up()
        page.wait_for_timeout(600)

        # === 4. 读端口（取左右分离的 src out / dst in）===
        ports = page.eval_on_selector_all(".node-port", """els => els.map(e => {
            const r = e.getBoundingClientRect();
            return {cls: e.className, cx: Math.round(r.x+r.width/2), cy: Math.round(r.y+r.height/2)};
        })""")
        src = max([x for x in ports if "port-out" in x["cls"]], key=lambda x: x["cx"])
        dst = min([x for x in ports if "port-in" in x["cls"]], key=lambda x: x["cx"])
        # 确认 src 和 dst 不在同一节点（cx 差距大）
        failures += not check("src/dst 端口分离", dst["cx"] < src["cx"] - 100, f"src={src['cx']} dst={dst['cx']}")

        # === 5. 连线拖拽 ===
        page.mouse.move(src["cx"], src["cy"])
        page.mouse.down()
        page.wait_for_timeout(200)
        md = page.evaluate("() => portDragState ? {fromPort:portDragState.fromPort} : 'null'")
        failures += not check("mousedown 建立 portDragState", isinstance(md, dict) and md.get("fromPort") == "out", str(md))
        page.mouse.move(dst["cx"], dst["cy"], steps=15)
        page.wait_for_timeout(250)
        hov = page.evaluate("() => portDragState ? {hoverTargetId:portDragState.hoverTargetId, hoverPort:portDragState.hoverPort} : null")
        failures += not check("hover 命中目标 in", bool(hov and hov["hoverPort"] == "in"), str(hov))
        page.mouse.up()
        page.wait_for_timeout(800)

        # === 6. 断言连线建立 ===
        conns = connections()
        failures += not check("canvas.connections 新增 input 连线", len(conns) >= 1 and conns[-1]["kind"] == "input", json.dumps(conns, ensure_ascii=False))
        paths = page.eval_on_selector_all(".connection-layer path", "els => els.length")
        failures += not check("connection-layer 渲染连线路径", paths >= 4, str(paths))

        # === 7. 断线：用当前界面上的剪刀按钮删除连线 ===
        # 找断线入口，便于诊断接线情况。
        cut_ok = page.evaluate("""() => {
            // 尝试常见的断线入口
            if (typeof disconnectNodes === 'function') { return 'disconnectNodes'; }
            if (typeof removeConnection === 'function') { return 'removeConnection'; }
            if (typeof cutConnection === 'function') { return 'cutConnection'; }
            if (typeof startConnectionCutGesture === 'function') { return 'startConnectionCutGesture'; }
            return 'none';
        }""")
        print(f"  断线函数探测: {cut_ok}")

        # 2026-10-18：剪刀在节点/端口/composer 命中区内一律不弹（10-17 有意防误剪）。
        # UI 拖拽摆位后连线常整段压在端口命中区上，先用 API 把两节点拉成一条水平长线
        # 并重载，保证连线中段是大片可命中的空白。
        try:
            with urllib.request.urlopen(f"{BASE}/api/canvases/{canvas_id}", timeout=15) as resp:
                cur = json.loads(resp.read().decode("utf-8"))["canvas"]
            ns = cur.get("nodes") or []
            if len(ns) >= 2:
                ns[0]["x"], ns[0]["y"] = 200, 300
                ns[1]["x"], ns[1]["y"] = 1200, 300
                req = urllib.request.Request(
                    f"{BASE}/api/canvases/{canvas_id}",
                    data=json.dumps({"nodes": ns, "base_updated_at": cur.get("updated_at")}).encode(),
                    headers={"Content-Type": "application/json"}, method="PUT")
                urllib.request.urlopen(req, timeout=15).read()
                page.reload(wait_until="domcontentloaded")
                page.locator("#canvasAddToggle").wait_for(state="visible", timeout=30000)
                page.wait_for_function("() => (canvas?.connections || []).length >= 1", timeout=15000)
                page.wait_for_timeout(1200)
        except Exception as exc:
            print(f"  拉开节点失败: {exc}")
        
        # conn-hit 是连线点击区；取 SVG 曲线中点的屏幕坐标，避免命中包围盒空白。
        conn_hit = page.eval_on_selector_all(".conn-hit", "els => els.length")
        failures += not check("连线存在 conn-hit 点击区", conn_hit >= 1, str(conn_hit))

        if conn_hit >= 1:
            hit_box = page.eval_on_selector(".conn-hit >> nth=0", """el => {
                // 2026-10-18：中点常压在节点/端口上（防误剪区）→ 沿曲线采样挑空白点
                const L = el.getTotalLength();
                const cand = [];
                for (let i = 1; i < 20; i++) {
                    const p = el.getPointAtLength(L * i / 20);
                    const s = new DOMPoint(p.x, p.y).matrixTransform(el.getScreenCTM());
                    cand.push({cx: Math.round(s.x), cy: Math.round(s.y)});
                }
                const clean = cand.find(c => {
                    const stack = document.elementsFromPoint ? document.elementsFromPoint(c.cx, c.cy) : [];
                    return stack.length && !stack.some(e => e.closest && (e.closest(".image-node")
                        || e.closest(".composer") || e.closest(".node-port")));
                });
                return clean || cand[Math.floor(cand.length / 2)];
            }""")
            page.mouse.move(hit_box["cx"], hit_box["cy"])
            # 剪刀需光标在同一条线上停留满 CONN_SCISSOR_SHOW_DELAY(480ms) 才弹出，
            # 单次 move 只喂一个 pointermove，必须持续微抖动停留跨过延迟。
            for _ in range(10):
                page.mouse.move(hit_box["cx"] + 0.5, hit_box["cy"] + 0.5)
                page.wait_for_timeout(90)
            page.wait_for_function(
                "() => document.querySelector('svg.connection-layer g.conn-scissor')?.classList.contains('show')",
                timeout=5000,
            )
            page.locator("svg.connection-layer g.conn-scissor.show").click(timeout=5000)
            page.wait_for_function("() => canvas.connections.length < 1", timeout=5000)
            conns2 = connections()
            failures += not check("点击剪刀按钮后 canvas.connections 减少",
                                  len(conns2) < len(conns), f"{len(conns)} -> {len(conns2)}")

        # 无 JS 报错
        real_errors = [e for e in errors if "WebSocket" not in e and "stats" not in e]
        failures += not check("无 JS 报错", len(real_errors) == 0, str(real_errors[:3]))

        browser.close()

    total = 11
    passed = total - failures
    print(f"\nRESULT: {passed}/{total}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
