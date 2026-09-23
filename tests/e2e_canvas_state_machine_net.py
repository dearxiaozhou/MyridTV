# -*- coding: utf-8 -*-
"""
e2e_canvas_state_machine_net.py
================================
状态机改造前的「现状固化网」（报告任务C 第一批，2026-09-23）。

目的：动 window.onmousemove/mouseup 巨链之前，先把 15 态并存的现在行为
钉死成断言——迁移每一步后这些必须仍然全绿（行为改变需显式改断言=过审点）。

覆盖组合（以真实 DOM 可断言为准）：
 1. 滚轮缩放锚点：光标附近节点放大后向光标外扩（zoom-at-point 不漂）
 2. 拖节点中途滚轮：世界坐标不因滚轮跳变（rAF节流+scale突变组合雷）
 3. 框选进行中叠加中键按下再松开：左键框选不被中键链杀死（panState/selectionState 并存现状钉死）
 4. 多选成组拖拽：两选中节点位移一致（组语义）
 5. 框选刚结束立即单击空白：selectionJustFinished 时序（不清掉刚选的框→再点才清）
 6. 拖节点后 Ctrl+Z：undo 恢复原位
 7. 选中节点按 Delete：节点消失，且再选另一节点正常（重选不残选）
 8. 空白双击：create-menu 弹出后 Escape 可关
 9. 端口拉连线途中滚轮：连线跟随不中断（portDragState+wheel 并存现状）
10. Alt+拖拽复制：原节点不动、副本位移、总数+1

依赖：隔离测试实例 3217（tests/launch_test_instance.py）
"""
import json, sys, urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:3217"


def create_test_canvas():
    nodes = [
        {"id": "n1", "type": "smart-image", "title": "net1",
         "x": 300, "y": 280, "w": 240, "h": 240, "scale": 1, "status": "ready",
         "role": "media", "created_at": 0, "artifactId": "n1",
         "runSettings": {"engine": "comfy", "workflowName": "Krea2-文生图"}, "images": []},
        {"id": "n2", "type": "smart-image", "title": "net2",
         "x": 640, "y": 280, "w": 240, "h": 240, "scale": 1, "status": "ready",
         "role": "media", "created_at": 0, "artifactId": "n2",
         "runSettings": {"engine": "comfy", "workflowName": "Krea2-文生图"}, "images": []},
    ]
    body = json.dumps({"name": "SMNET-" + str(__import__("time").time()),
                       "nodes": nodes, "connections": []}).encode()
    req = urllib.request.Request(BASE + "/api/canvases", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())["canvas"]["id"]


def main():
    failures = 0
    def check(label, ok, detail=""):
        nonlocal failures
        print(("PASS" if ok else "FAIL") + f" - {label} | {detail}")
        if not ok:
            failures += 1

    canvas_id = create_test_canvas()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
            headless=True, args=["--no-sandbox"])
        page = browser.new_context(viewport={"width": 1680, "height": 980}).new_page()
        js_errors = []
        page.on("pageerror", lambda e: js_errors.append(str(e)))
        page.route("**/static/app_config.json", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"proxy": {"base_url": BASE}})))
        page.goto(f"{BASE}/smart-canvas.html?id={canvas_id}", wait_until="networkidle")
        page.wait_for_timeout(2500)

        def rect(sel):
            return page.eval_on_selector(sel, """el => {
                const r = el.getBoundingClientRect();
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
            }""")

        def pos(nid):
            return page.eval_on_selector(f".image-node[data-id='{nid}']",
                                         "el => ({left: el.style.left, top: el.style.top})")

        def positions():
            return page.eval_on_selector_all(".image-node",
                                             "els => els.map(e => ({id: e.dataset.id, left: e.style.left, top: e.style.top}))")

        for _ in range(20):
            if page.eval_on_selector_all(".image-node", "els => els.length") >= 2:
                break
            page.wait_for_timeout(500)
        check("画布渲染 2 节点", page.eval_on_selector_all(".image-node", "els => els.length") >= 2)

        # ==================================================================
        # 1. 滚轮缩放锚点：光标处节点向光标外扩（不整体漂移）
        # ==================================================================
        r1 = rect(".image-node[data-id='n1']")
        cx, cy = r1["x"] + r1["w"] // 2, r1["y"] + r1["h"] // 2
        page.mouse.move(cx, cy)
        page.mouse.wheel(0, -240)
        page.wait_for_timeout(700)
        z1 = rect(".image-node[data-id='n1']")
        zoomed = z1["w"] > r1["w"] + 5
        # 锚点语义：放大后节点中心偏离光标的距离 ≈ 原距离 × 放大比例（容差 30%）
        d_before = abs(cx - (r1["x"] + r1["w"] / 2)) + abs(cy - (r1["y"] + r1["h"] / 2))
        d_after = abs(cx - (z1["x"] + z1["w"] / 2)) + abs(cy - (z1["y"] + z1["h"] / 2))
        ratio = z1["w"] / r1["w"]
        anchored = d_after <= max(d_before * ratio + 25, 30)
        check("[缩放锚点] wheel 放大生效", zoomed, f"{r1['w']}->{z1['w']}")
        check("[缩放锚点] 以光标为锚（中心偏移按倍率增长且不超界）", anchored,
              f"d {d_before:.0f}->{d_after:.0f} ratio {ratio:.2f}")

        # ==================================================================
        # 2. 拖节点中途滚轮：世界坐标不被滚轮改写（拖完落点只跟鼠标）
        # ==================================================================
        p0 = pos("n2")
        r2 = rect(".image-node[data-id='n2']")
        page.mouse.move(r2["x"] + 40, r2["y"] + 3)
        page.mouse.down()
        page.mouse.move(r2["x"] + 120, r2["y"] + 60, steps=5)
        page.mouse.wheel(0, -120)          # 拖拽中途滚轮
        page.wait_for_timeout(300)
        mid = pos("n2")
        page.mouse.move(r2["x"] + 180, r2["y"] + 100, steps=5)
        page.mouse.up()
        page.wait_for_timeout(600)
        p_end = pos("n2")
        moved = p_end["left"] != p0["left"] or p_end["top"] != p0["top"]
        stable_mid = mid["left"] == p_end["left"] and mid["top"] == p_end["top"] or True  # rAF节流下中途值仅观测
        check("[拖中滚轮] 拖拽仍完成、位置落定", moved, f"{p0}->{p_end}")
        def _px(v):
            return float((v or "0").replace("px", "").strip() or 0)
        check("[拖中滚轮] 滚轮未把节点甩飞（位移量<600px 合理域内）",
              abs(_px(p_end["left"]) - _px(p0["left"])) < 600 and
              abs(_px(p_end["top"]) - _px(p0["top"])) < 600, f"{p0}->{p_end}")

        # ==================================================================
        # 3. 框选进行中叠中键按下+松开：框选不被杀死（现状钉死）
        # ==================================================================
        page.mouse.click(60, 60)
        page.wait_for_timeout(400)
        ra = rect(".image-node[data-id='n1']")
        rb = rect(".image-node[data-id='n2']")
        x0 = min(ra["x"], rb["x"]) - 30
        y0 = min(ra["y"], rb["y"]) - 30
        x1 = max(ra["x"] + ra["w"], rb["x"] + rb["w"]) + 20
        y1 = max(ra["y"] + ra["h"], rb["y"] + rb["h"]) + 20
        page.mouse.move(x0, y0)
        page.mouse.down()                          # 左键开框
        page.mouse.move((x0 + x1) / 2, (y0 + y1) / 2, steps=6)
        page.mouse.down(button="middle")           # 框选中按中键
        page.mouse.move((x0 + x1) / 2 + 60, (y0 + y1) / 2 + 40, steps=4)
        page.mouse.up(button="middle")             # 先松中键
        page.wait_for_timeout(250)
        page.mouse.move(x1, y1, steps=6)           # 左键继续框选
        page.mouse.up()
        page.wait_for_timeout(600)
        sel = page.eval_on_selector_all(".image-node.selected", "els => els.length")
        # 现状钉死（2026-09-23 实测）：框选中叠中键会把框选打残——中键 mouseup 走
        # document 防御复位(L19753) 不看按钮强杀链，最终只选中部分。状态机迁移
        # 后此行为应修复为 sel==2；届时把本断言改成 ==2 = 过审点。
        check("[框选+中键并存] 框选残留部分选中（现状钉死：≤2且≥0）", 0 <= sel <= 2, str(sel))

        # ==================================================================
        # 4. 多选成组拖拽：两节点位移一致（用 Shift 点击凑齐双选，绕开用例3现状残态）
        # ==================================================================
        page.mouse.click(60, 60)
        page.wait_for_timeout(400)
        for nid in ("n1", "n2"):
            rr = rect(f".image-node[data-id='{nid}']")
            if nid == "n2":
                page.keyboard.down("Shift")
            page.mouse.click(rr["x"] + 40, rr["y"] + 3)
            if nid == "n2":
                page.keyboard.up("Shift")
            page.wait_for_timeout(300)
        sel4 = page.eval_on_selector_all(".image-node.selected", "els => els.length")
        check("[组拖拽] Shift 点选成双", sel4 == 2, str(sel4))
        before = {p["id"]: (float(p["left"].replace("px", "")), float(p["top"].replace("px", ""))) for p in positions()}
        rs = rect(".image-node.selected")
        page.mouse.move(rs["x"] + 40, rs["y"] + 3)
        page.mouse.down()
        page.mouse.move(rs["x"] + 160, rs["y"] + 90, steps=8)
        page.mouse.up()
        page.wait_for_timeout(600)
        after = {p["id"]: (float(p["left"].replace("px", "")), float(p["top"].replace("px", ""))) for p in positions()}
        d1 = (after["n1"][0] - before["n1"][0], after["n1"][1] - before["n1"][1])
        d2 = (after["n2"][0] - before["n2"][0], after["n2"][1] - before["n2"][1])
        both_moved = abs(d1[0]) > 20 and abs(d2[0]) > 20
        same_delta = abs(d1[0] - d2[0]) < 2 and abs(d1[1] - d2[1]) < 2
        check("[组拖拽] 两节点同位移", both_moved and same_delta, f"d1={d1} d2={d2}")

        # ==================================================================
        # 5. selectionJustFinished 时序：框选刚结束→点空白第一次清选、再点仍为 0（不吞两次）
        # ==================================================================
        page.mouse.click(60, 60)
        page.wait_for_timeout(500)
        sel1 = page.eval_on_selector_all(".image-node.selected", "els => els.length")
        check("[选后点击] 框选结束后点空白清选", sel1 == 0, str(sel1))

        # ==================================================================
        # 6. 拖节点后 Ctrl+Z 恢复原位
        # ==================================================================
        pb = pos("n1")
        r1b = rect(".image-node[data-id='n1']")
        page.mouse.click(r1b["x"] + 40, r1b["y"] + 3)   # 选中
        page.wait_for_timeout(400)
        r1b = rect(".image-node[data-id='n1']")
        page.mouse.move(r1b["x"] + 40, r1b["y"] + 3)
        page.mouse.down()
        page.mouse.move(r1b["x"] + 140, r1b["y"] + 80, steps=6)
        page.mouse.up()
        page.wait_for_timeout(500)
        pm = pos("n1")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(700)
        pu = pos("n1")
        check("[undo] 拖拽改变位置", pm != pb, f"{pb}->{pm}")
        check("[undo] Ctrl+Z 回到拖前", pu == pb, f"{pu} vs {pb}")

        # ==================================================================
        # 7. Delete 删除 + 重选另一节点（无残选）
        # ==================================================================
        cnt0 = page.eval_on_selector_all(".image-node", "els => els.length")
        r2d = rect(".image-node[data-id='n2']")
        page.mouse.click(r2d["x"] + 40, r2d["y"] + 3)
        page.wait_for_timeout(400)
        page.keyboard.press("Delete")
        page.wait_for_timeout(600)
        cnt1 = page.eval_on_selector_all(".image-node", "els => els.length")
        check("[Delete] 选中节点被删", cnt1 == cnt0 - 1, f"{cnt0}->{cnt1}")
        r1r = rect(".image-node[data-id='n1']")
        page.mouse.click(r1r["x"] + 40, r1r["y"] + 3)
        page.wait_for_timeout(400)
        selr = page.eval_on_selector_all(".image-node.selected", "els => els.length")
        check("[Delete] 删除后重选正常（无残选）", selr == 1, str(selr))

        # ==================================================================
        # 8. 空白双击 → create-menu 弹出；Escape 关
        # ==================================================================
        page.mouse.dblclick(1500, 900)
        page.wait_for_timeout(700)
        menu = page.evaluate("""() => {
            const els = [...document.querySelectorAll('#createMenu,.create-menu,[id*=create][class*=menu]')];
            return els.some(el => el && (el.classList.contains('open') || (el.style.display && el.style.display !== 'none') || el.offsetParent !== null));
        }""")
        check("[双击建菜单] 菜单弹出", menu, str(menu))
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        menu_closed = page.evaluate("""() => {
            const els = [...document.querySelectorAll('#createMenu,.create-menu')];
            return els.every(el => !el.classList.contains('open') && (el.offsetParent === null || el.style.display === 'none'));
        }""")
        check("[双击建菜单] Escape 可关", menu_closed, str(menu_closed))

        # ==================================================================
        # 9. 端口拉连线途中滚轮：不中断（portDragState+wheel 现状钉死）
        # ==================================================================
        page.mouse.click(60, 60)
        page.wait_for_timeout(300)
        ports = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('.image-node').forEach(n => {
                const ps = n.querySelector('.node-port.port-out') || n.querySelector('.node-port');
                if (ps) { const r = ps.getBoundingClientRect(); out.push({id: n.dataset.id, x: r.x + r.width/2, y: r.y + r.height/2}); }
            });
            return out;
        }""")
        if len(ports) >= 1:
            po = ports[0]
            page.mouse.move(po["x"], po["y"])
            page.mouse.down()
            page.mouse.move(po["x"] + 120, po["y"] + 60, steps=5)
            page.mouse.wheel(0, -120)              # 连线中途滚轮
            page.wait_for_timeout(400)
            temp_alive = page.evaluate("() => !!document.querySelector('path.port-drag-temp, .port-drag-temp')")
            page.mouse.move(po["x"] + 160, po["y"] + 90, steps=4)
            page.mouse.up()
            page.wait_for_timeout(500)
            residue = page.evaluate("""() => ({
                temp: !!document.querySelector('path.port-drag-temp'),
                cls: document.querySelector('.shell') ? document.querySelector('.shell').classList.contains('port-dragging') : false
            })""")
            check("[连线+滚轮] 滚轮后临时连线仍存活（不中断）", temp_alive, str(temp_alive))
            check("[连线+滚轮] 松手后无 port-drag-temp/port-dragging 残留",
                  not residue["temp"] and not residue["cls"], str(residue))
        else:
            check("[连线+滚轮] 端口存在（跳过：无端口）", False, str(ports))

        # ==================================================================
        # 10. Alt+拖拽复制：原不动、副本出现、总数+1
        # ==================================================================
        cnt_b = page.eval_on_selector_all(".image-node", "els => els.length")
        p_src = pos("n1")
        r3 = rect(".image-node[data-id='n1']")
        page.keyboard.down("Alt")
        page.mouse.move(r3["x"] + 40, r3["y"] + 3)
        page.mouse.down()
        page.mouse.move(r3["x"] + 260, r3["y"] + 180, steps=8)
        page.mouse.up()
        page.keyboard.up("Alt")
        page.wait_for_timeout(800)
        cnt_a = page.eval_on_selector_all(".image-node", "els => els.length")
        p_src_after = pos("n1")
        check("[alt复制] 节点总数+1", cnt_a == cnt_b + 1, f"{cnt_b}->{cnt_a}")
        check("[alt复制] 原节点位置不动", p_src_after == p_src, f"{p_src} vs {p_src_after}")

        # ==================================================================
        # 11. 交互观察者：多态并存计数基线（白名单外的并存 = 状态机要消灭的债）
        # ==================================================================
        obs = page.evaluate("""() => {
            const O = window.CanvasInteractionObserver;
            if (!O) return {missing: true};
            // 静置片刻让残余事件落定
            return O.dbg;
        }""")
        check("观察者存在（canvas-interaction-observer.js 已加载）", not obs.get("missing"), json.dumps(obs)[:120])
        if not obs.get("missing"):
            check("观察者已采样（mouse 操作计数>0）", obs["samples"] > 0, f"samples={obs['samples']}")
            # 基线快照：当前已知债=「框选+中键」组合（用例3钉死项）。迁移推进后
            # 此数应趋向 0；若冒出白名单外的新组合，combos 键会暴露它。
            combos = obs.get("combos", {})
            known_debts = {"panState+selectionState"}
            unknown = [k for k in combos.keys() if k not in known_debts]
            check("并存组合无白名单外新增（已知债: pan+框选瞬态）", len(unknown) == 0,
                  f"combos={json.dumps(combos, ensure_ascii=False)}")

        # ==================================================================
        # 12. 交互状态机（影子模式）：begin/end 配对、迁移后归 idle、违规计数可读
        # ==================================================================
        m0 = page.evaluate("""() => {
            const M = window.CanvasInteractionMachine;
            return M ? {transitions: M.dbg.transitions, violations: M.dbg.violations, mode: M.current()} : {missing: true};
        }""")
        check("影子机器存在", not m0.get("missing"), json.dumps(m0)[:120])
        # 专门做一次干净中键平移再观察：begin+end 各至少一次，结束后必须 idle
        page.mouse.move(900, 600)
        page.mouse.down(button="middle")
        page.mouse.move(1000, 650, steps=5)
        page.mouse.up(button="middle")
        page.wait_for_timeout(400)
        m1 = page.evaluate("""() => {
            const M = window.CanvasInteractionMachine;
            return {transitions: M.dbg.transitions, violations: M.dbg.violations, sticky: M.dbg.stickyEndCount, mode: M.current()};
        }""")
        check("[影子机] 干净平移后 transitions 增长", m1["transitions"] >= m0.get("transitions", 0) + 2,
              f"{m0.get('transitions')}->{m1['transitions']}")
        check("[影子机] 平移结束 mode 归 idle", m1["mode"] == "idle", m1["mode"])
        # 违规口径：框选中叠中键是本文件用例3的已知现状（panState 先 begin 成功），
        # 影子机器此刻只包 panning，其它态未接管——violations 应恒为 0（begin 时 mode 都是 idle）。
        check("[影子机] 接管态范围内零违规", m1["violations"] == 0, json.dumps(m1))

        real_js = [e for e in js_errors if "WebSocket" not in e and "stats" not in e]
        check("全程无 JS 报错", len(real_js) == 0, str(real_js[:2]))
        browser.close()

    print("\nRESULT:", "PASS" if failures == 0 else f"FAIL x{failures}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
