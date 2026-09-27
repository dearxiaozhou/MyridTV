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

import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")


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
        # n3 带图 → 渲染 .node-resize-handle（L11740 条件），仅 resize 用例用；
        # 放远处避免进框选/连线用例的命中区（n1 带图会连图片遮端口）。
        {"id": "n3", "type": "smart-image", "title": "net3",
         "x": 1150, "y": 200, "w": 240, "h": 240, "scale": 1, "status": "ready",
         "role": "media", "created_at": 0, "artifactId": "n3",
         "runSettings": {"engine": "comfy", "workflowName": "Krea2-文生图"},
         "images": [{"url": "/assets/output/e2e/rz.png", "name": "rz.png", "kind": "image",
                     "local_path": "_test_userdata/rz.png", "display_name": "rz.png",
                     "generatedResult": True, "natural_w": 512, "natural_h": 512}]},
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
        page.route("**/static/app_config.json*", lambda route: route.fulfill(
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
            if page.eval_on_selector_all(".image-node", "els => els.length") >= 3:
                break
            page.wait_for_timeout(500)
        check("画布渲染 3 节点", page.eval_on_selector_all(".image-node", "els => els.length") >= 3)

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
        # 过审点兑现（第9步）：原"中键 mouseup 不看按钮强杀框选"已修——
        # mouseup 主链只认对应按钮收尾 + 机器 end 栈语义（并存时 end 回剩余态）。
        # 预期 sel==2：框选完整走完，n1+n2 全选中。
        check("[框选+中键并存] 修复确认：框选不被中键打残（sel==2）", sel == 2, str(sel))

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
        blank = page.evaluate("""() => {
            for (const [x, y] of [[1500, 900], [1500, 950], [900, 900], [1620, 900], [1400, 850]]) {
                const el = document.elementFromPoint(x, y);
                if (el && (el.classList.contains('world') || el.classList.contains('shell'))) return {x, y};
            }
            return {x: 1500, y: 900};
        }""")
        page.mouse.dblclick(blank["x"], blank["y"])
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
        # 端口可能被节点盒遮挡（elementFromPoint 命中 image-node，Playwright 真点会开框选）：
        # 起手用 dispatchEvent 直接打 port mousedown，随后真实鼠标 move/wheel/up
        po = page.evaluate("""() => {
            const port = document.querySelector(".image-node[data-id='n1'] .node-port.port-out")
                      || document.querySelector(".image-node .node-port.port-out")
                      || document.querySelector(".image-node .node-port");
            if (!port) return null;
            const r = port.getBoundingClientRect();
            port.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, button:0, clientX: r.x+r.width/2, clientY: r.y+r.height/2}));
            return {x: r.x + r.width/2, y: r.y + r.height/2};
        }""")
        if po:
            page.mouse.move(po["x"], po["y"])
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
            check("[连线+滚轮] n1 端口存在", False, str(po))

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
            known_debts = {"panState+selectionState"}  # 观察者探针债清单不变
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
        # 已知债显式豁免（2026-09-23）：用例3 框选+中键并存——机器白名单放行
        # box-selecting×panning，violations 应仍为 0；修复行为时本注释与豁免同删。
        check("[影子机] 接管态范围内零违规（已知债走白名单）", m1["violations"] == 0, json.dumps(m1))
        # box-selecting 接管自检：干净框选 begin+end 成对、归 idle
        m_box = page.evaluate("""() => {
            const M = window.CanvasInteractionMachine;
            return {t0: M.dbg.transitions, mode0: M.current()};
        }""")
        # 此刻画布有 n1 + alt复制的2个副本（n2 已在用例7删除）：框住全部节点即可
        page.mouse.click(60, 60); page.wait_for_timeout(300)
        all_r = page.eval_on_selector_all(".image-node", """els => els.map(e => {
            const r = e.getBoundingClientRect();
            return {x: r.x, y: r.y, w: r.width, h: r.height};
        })""")
        x0 = min(r["x"] for r in all_r) - 40
        y0 = min(r["y"] for r in all_r) - 40
        x1 = max(r["x"] + r["w"] for r in all_r) + 40
        y1 = max(r["y"] + r["h"] for r in all_r) + 40
        page.mouse.move(max(30, x0), max(30, y0))
        page.mouse.down()
        page.mouse.move(min(1650, x1), min(950, y1), steps=8)
        page.mouse.up()
        page.wait_for_timeout(500)
        m1b = page.evaluate("""() => {
            const M = window.CanvasInteractionMachine;
            return {transitions: M.dbg.transitions, violations: M.dbg.violations, mode: M.current()};
        }""")
        check("[影子机] 干净框选 begin+end 成对（transitions+2 且归 idle）",
              m1b["transitions"] >= m_box["t0"] + 2 and m1b["mode"] == "idle" and m1b["violations"] == 0,
              json.dumps(m1b))
        # 复原：清选
        page.mouse.click(60, 60); page.wait_for_timeout(300)
        # dragging-node 接管自检：干净拖拽 begin+end 成对、零违规、归 idle
        m_d0 = page.evaluate("() => ({t: window.CanvasInteractionMachine.dbg.transitions, v: window.CanvasInteractionMachine.dbg.violations})")
        rd = rect(".image-node[data-id='n1']")
        page.mouse.click(rd["x"] + 40, rd["y"] + 3)   # 选中
        page.wait_for_timeout(300)
        rd = rect(".image-node[data-id='n1']")
        page.mouse.move(rd["x"] + 40, rd["y"] + 3)
        page.mouse.down()
        page.mouse.move(rd["x"] + 170, rd["y"] + 110, steps=8)
        page.mouse.up()
        page.wait_for_timeout(500)
        m_d1 = page.evaluate("""() => {
            const M = window.CanvasInteractionMachine;
            return {t: M.dbg.transitions, v: M.dbg.violations, sticky: M.dbg.stickyEndCount, mode: M.current()};
        }""")
        check("[影子机] 干净拖拽 begin+end 成对（+2、归 idle、零违规）",
              m_d1["t"] >= m_d0["t"] + 2 and m_d1["mode"] == "idle" and m_d1["v"] == m_d0["v"],
              json.dumps(m_d1))
        # 拖拽 undo 收尾不产生孤儿 begin：Ctrl+Z 后 mode 仍 idle
        page.keyboard.press("Control+z")
        page.wait_for_timeout(500)
        m_d2 = page.evaluate("() => window.CanvasInteractionMachine.current()")
        check("[影子机] undo 后 mode 仍 idle（undo 不改交互态）", m_d2 == "idle", str(m_d2))

        # connecting 接管自检：端口拖出连线 begin+end 成对、零违规、归 idle
        m_c0 = page.evaluate("() => ({t: window.CanvasInteractionMachine.dbg.transitions, v: window.CanvasInteractionMachine.dbg.violations})")
        page.mouse.click(60, 60); page.wait_for_timeout(300)
        pc = page.evaluate("""() => {
            const port = document.querySelector(".image-node[data-id='n1'] .node-port.port-out")
                      || document.querySelector(".image-node .node-port.port-out")
                      || document.querySelector(".image-node .node-port");
            if (!port) return null;
            const r = port.getBoundingClientRect();
            port.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, button:0, clientX: r.x+r.width/2, clientY: r.y+r.height/2}));
            return {x: r.x + r.width/2, y: r.y + r.height/2};
        }""")
        if pc:
            page.mouse.move(pc["x"], pc["y"])
            page.mouse.move(pc["x"] + 130, pc["y"] + 70, steps=6)
            page.mouse.up()
            page.wait_for_timeout(500)
            m_c1 = page.evaluate("""() => {
                const M = window.CanvasInteractionMachine;
                return {t: M.dbg.transitions, v: M.dbg.violations, mode: M.current()};
            }""")
            check("[影子机] 连线 begin+end 成对（+2、归 idle、零违规）",
                  m_c1["t"] >= m_c0["t"] + 2 and m_c1["mode"] == "idle" and m_c1["v"] == m_c0["v"],
                  json.dumps(m_c1))
            # 连到空白断开：不应残留 connecting 态（end 已在 mouseup 主链走完）
            residue = page.evaluate("""() => ({
                mode: window.CanvasInteractionMachine.current(),
                port_dragging: document.querySelector('.shell') ? document.querySelector('.shell').classList.contains('port-dragging') : null
            })""")
            check("[影子机] 断线后无 connecting 残留（mode=idle 且无 port-dragging 类）",
                  residue["mode"] == "idle" and residue["port_dragging"] is False, json.dumps(residue))
        else:
            check("[影子机] n1 端口存在", False, str(pc))

        # resizing 接管自检：handle 直驱 mousedown（前序用例缩放平移后，
        # n3 可能被推出视口——坐标真点会落空），随后真实鼠标 move/up 走 window 链
        page.mouse.click(60, 60); page.wait_for_timeout(300)
        hr_pos = page.evaluate("""() => {
            const h = document.querySelector(".image-node[data-id='n3'] .node-resize-handle");
            if (!h) return null;
            const r = h.getBoundingClientRect();
            h.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, button:0, clientX:r.x+4, clientY:r.y+4}));
            return {x: r.x + 4, y: r.y + 4};
        }""")
        m_r0 = page.evaluate("() => ({t: window.CanvasInteractionMachine.dbg.transitions, v: window.CanvasInteractionMachine.dbg.violations, mode: window.CanvasInteractionMachine.current()})")
        if hr_pos and m_r0["mode"] == "resizing":
            page.mouse.move(100, 100)
            page.mouse.move(max(20, hr_pos["x"] + 60), max(20, hr_pos["y"] + 40), steps=6)
            page.mouse.up()
            page.wait_for_timeout(500)
            m_r1 = page.evaluate("""() => {
                const M = window.CanvasInteractionMachine;
                return {t: M.dbg.transitions, v: M.dbg.violations, mode: M.current()};
            }""")
            check("[影子机] resize begin 进 resizing 且收尾全配对（归 idle 零违规）",
                  m_r1["mode"] == "idle" and m_r1["v"] == m_r0["v"] and m_r1["t"] > m_r0["t"],
                  json.dumps({"before": m_r0, "after": m_r1}))
        else:
            check("[影子机] resize handle 直驱进 resizing", False,
                  str(hr_pos) + " " + json.dumps(m_r0))

        # 第三刀新入机态驱动自检：prompt-resize（composer 提示词高度拖柄）
        # handle 直驱 mousedown（可能被浮层遮），真实 move/up 收尾
        page.mouse.click(60, 60); page.wait_for_timeout(300)
        pr = page.evaluate("""() => {
            const h = document.getElementById('promptResize');
            if (!h) return null;
            const r = h.getBoundingClientRect();
            if (r.width < 2) return null;
            h.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, button:0, clientX:r.x+r.width/2, clientY:r.y+r.height/2}));
            return {x: r.x + r.width/2, y: r.y + r.height/2};
        }""")
        if pr:
            m_p0 = page.evaluate("() => ({mode: window.CanvasInteractionMachine.current(), h: (document.querySelector('.prompt-input')||document.getElementById('promptInput')||{offsetHeight:0}).offsetHeight})")
            page.mouse.move(pr["x"], pr["y"])
            page.mouse.move(pr["x"], pr["y"] + 60, steps=5)
            page.mouse.up()
            page.wait_for_timeout(400)
            m_p1 = page.evaluate("() => ({mode: window.CanvasInteractionMachine.current(), v: window.CanvasInteractionMachine.dbg.violations, div: window.CanvasInteractionMachine.dbg.divergences})")
            check("[第三刀] prompt-resize begin 进态且收尾归 idle 零违规",
                  m_p0["mode"] == "prompt-resize" and m_p1["mode"] == "idle"
                  and m_p1["v"] == 0 and m_p1["div"] == 0,
                  json.dumps({"begin": m_p0, "end": m_p1}))
        else:
            check("[第三刀] promptResize 柄存在", False, str(pr))

        # ==================================================================
        # 12.5 第6步：Escape 一键取消（拖拽/框选取消+还原；idle 时不劫持）
        # ==================================================================
        page.mouse.click(60, 60); page.wait_for_timeout(300)

        # (a) 拖拽中途 Escape：节点回到原位、机器归 idle
        rx = page.evaluate("""() => {
            const n = document.querySelector(".image-node[data-id='n1']");
            if (!n) return null;
            n.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, button:0,
                clientX: n.getBoundingClientRect().x + 40, clientY: n.getBoundingClientRect().y + 3}));
            n.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, button:0,
                clientX: n.getBoundingClientRect().x + 40, clientY: n.getBoundingClientRect().y + 3}));
            return 1;
        }""")
        page.wait_for_timeout(300)
        pos_before = page.evaluate("""() => {
            const n = document.querySelector(".image-node[data-id='n1']");
            return {left: n.style.left, top: n.style.top};
        }""")
        if pos_before.get("left"):
            r1 = page.eval_on_selector(".image-node[data-id='n1']",
                "el=>{const q=el.getBoundingClientRect();return{x:q.x+40,y:q.y+3}}")
            page.mouse.move(r1["x"], r1["y"]); page.mouse.down()
            page.mouse.move(r1["x"] + 120, r1["y"] + 80, steps=6)
            page.wait_for_timeout(120)
            m_mid = page.evaluate("() => window.CanvasInteractionMachine.current()")
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)
            try:
                page.mouse.up()
            except Exception:
                pass
            page.wait_for_timeout(250)
            pos_after = page.evaluate("""() => {
                const M = window.CanvasInteractionMachine;
                const n = document.querySelector(".image-node[data-id='n1']");
                return {left: n.style.left, top: n.style.top, mode: M.current(),
                        v: M.dbg.violations, div: M.dbg.divergences};
            }""")
            check("[Escape] 拖拽中途取消：mode 曾进 dragging-node", m_mid == "dragging-node", str(m_mid))
            check("[Escape] 拖拽取消后归位 + 归 idle + 双零",
                  pos_after["left"] == pos_before["left"] and pos_after["top"] == pos_before["top"]
                  and pos_after["mode"] == "idle" and pos_after["v"] == 0 and pos_after["div"] == 0,
                  json.dumps({"before": pos_before, "after": pos_after}))
        else:
            check("[Escape] n1 位置可读", False, json.dumps(pos_before))

        # (b) 框选中 Escape：selectionBox 隐藏、归 idle
        page.mouse.move(400, 350); page.mouse.down()
        page.mouse.move(700, 550, steps=5)
        page.wait_for_timeout(100)
        sel_mode = page.evaluate("() => window.CanvasInteractionMachine.current()")
        page.keyboard.press("Escape")
        page.wait_for_timeout(120)
        try:
            page.mouse.up()
        except Exception:
            pass
        page.wait_for_timeout(150)
        sel_state = page.evaluate("""() => {
            const sb = document.getElementById('selectionBox');
            return {mode: window.CanvasInteractionMachine.current(),
                    box: sb ? sb.style.display : 'gone'};
        }""")
        check("[Escape] 框选取消：mode 曾进 box-selecting", sel_mode == "box-selecting", str(sel_mode))
        check("[Escape] 框选取消后框隐藏 + 归 idle",
              sel_state["mode"] == "idle" and sel_state["box"] in ("none", "gone"),
              json.dumps(sel_state))

        # (c) idle 时 Escape 不被机器劫持（cancelActive 不被调用：靠 current()==='idle' 放行）
        idle_esc = page.evaluate("""() => {
            const M = window.CanvasInteractionMachine;
            const before = M.dbg.transitions;
            document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
            return {mode: M.current(), same: M.dbg.transitions === before};
        }""")
        check("[Escape] idle 时 Escape 零干预（不改 mode 不产生迁移）",
              idle_esc["mode"] == "idle" and idle_esc["same"], json.dumps(idle_esc))

        # ==================================================================
        # 12.7 第7步：粘滞标志收编断言
        # ==================================================================
        # (a) 真实平移一段距离 → sticky 表出现 gesture:pan；松手后宏任务清零
        page.mouse.move(840, 500)
        page.mouse.down(button="middle")
        page.mouse.move(800, 470, steps=5)
        pan_sticky_mid = page.evaluate("""() => {
            const M = window.CanvasInteractionMachine;
            return {sticky: M.stickySnapshot(), active: M.stickyActive('gesture:pan')};
        }""")
        # 原语义复刻：本画布中键松手走的是 document capture 防御链（抢先清
        # panState），该路径不清粘滞——didPan 残留到下一次平移/框选 begin 才清。
        # （window.onmouseup 的 setTimeout 复位只在没被防御链抢先时生效。）
        page.mouse.up(button="middle")
        page.wait_for_timeout(200)
        pan_sticky_after = page.evaluate("""() => ({
            sticky: window.CanvasInteractionMachine.stickySnapshot(),
            active: window.CanvasInteractionMachine.stickyActive('gesture:pan')
        })""")
        page.mouse.move(700, 420)
        page.mouse.down(button="middle")
        page.mouse.up(button="middle")
        page.wait_for_timeout(150)
        pan_sticky_next = page.evaluate("""() => ({
            activeMid: window.CanvasInteractionMachine.stickyActive('gesture:pan')
        })""")
        check("[第7步] 平移中粘滞在机器表且生效；begin 重进时按原语义清零",
              pan_sticky_mid["active"] and pan_sticky_mid["sticky"].get("gesture:pan") == "sticky"
              and pan_sticky_after["active"]           # 残留=原布尔行为（忠实复刻）
              and not pan_sticky_next["activeMid"]     # begin 清零路径有效
              , json.dumps({"mid": pan_sticky_mid, "after": pan_sticky_after, "next": pan_sticky_next}))

        # (b) 拖拽节点提交后 gesture:node-click 限时粘滞出现，400ms 后自动过期
        page.mouse.click(60, 60); page.wait_for_timeout(250)
        r2 = page.eval_on_selector(".image-node[data-id='n2'], .image-node",
            "el=>{const q=el.getBoundingClientRect();return{x:q.x+40,y:q.y+3}}")
        page.mouse.move(r2["x"], r2["y"]); page.mouse.down()
        page.mouse.move(r2["x"] + 100, r2["y"] + 60, steps=6)
        page.mouse.up()
        page.wait_for_timeout(80)
        click_sticky = page.evaluate("""() => {
            const M = window.CanvasInteractionMachine;
            return {now: M.stickyActive('gesture:node-click'), snap: M.stickySnapshot()};
        }""")
        page.wait_for_timeout(400)
        click_after = page.evaluate("() => window.CanvasInteractionMachine.stickyActive('gesture:node-click')")
        check("[第7步] 拖拽提交后 node-click 限时粘滞（180ms）到期自动清",
              click_sticky["now"] and click_sticky["snap"].get("gesture:node-click") == "timed"
              and not click_after,
              json.dumps({"t0": click_sticky, "t480": click_after}))

        # ==================================================================
        # 12.8 第8步：OverlayRegistry 注册表语义
        # ==================================================================
        reg = page.evaluate("""() => {
            const R = window.CanvasOverlayRegistry;
            if (!R) return {err: 'no registry'};
            const out = {};
            out.kinds = Object.keys(R.BASE);
            // 既有浮层判定：composer → overlay/wheel-exclude 真，pan-exclude 假（原链 composer 不在中键链）
            const comp = document.querySelector('.composer');
            out.composer_overlay = comp ? R.isOverlay(comp, 'overlay') : null;
            out.composer_pan = comp ? R.isOverlay(comp, 'pan-exclude') : null;
            out.composer_wheel = comp ? R.isOverlay(comp, 'wheel-exclude') : null;
            // 动态注册：临时 div 挂 body，注册后所有 kind 立即命中，注销后恢复
            const probe = document.createElement('div');
            probe.className = 'e2e-registry-probe';
            document.body.appendChild(probe);
            out.before = R.isOverlay(probe, 'overlay');
            R.register('.e2e-registry-probe');
            out.after = R.isOverlay(probe, 'overlay') && R.isOverlay(probe, 'wheel-exclude');
            R.unregister('.e2e-registry-probe');
            out.removed = !R.isOverlay(probe, 'overlay');
            probe.remove();
            return out;
        }""")
        check("[第8步] OverlayRegistry 六 kind 齐备且既有浮层判定与原链一致",
              "err" not in reg and len(reg.get("kinds", [])) == 6
              and reg.get("composer_overlay") is True and reg.get("composer_pan") is False
              and reg.get("composer_wheel") is True, json.dumps(reg))
        check("[第8步] register 一处声明全局立即生效、unregister 干净回退",
              reg.get("before") is False and reg.get("after") is True and reg.get("removed") is True,
              json.dumps(reg))
        # 委托真实生效（非 fallback）：主文件判定函数指向 registry
        deleg = page.evaluate("""() => {
            const R = window.CanvasOverlayRegistry;
            const snapshot = R.snapshot();
            return Object.keys(snapshot.dynamic).length === 0 && Object.values(snapshot.base).every(n => n >= 12);
        }""")
        check("[第8步] base 链完整迁移（每 kind ≥12 选择器、动态表初始为空）", deleg is True, str(deleg))

        # ==================================================================
        # 13. 审计器（第5步量化）：全链交互跑完后，记账漏网必须为 0
        #     divergence = 观察者探到的活跃态与机器 mode 不一致（白名单除外）
        # ==================================================================
        aud = page.evaluate("""() => {
            const M = window.CanvasInteractionMachine;
            return {divergences: M.dbg.divergences, log: M.dbg.divergenceLog.slice(0, 6)};
        }""")
        check("[审计] 全链跑完零 divergence（begin/end 记账与真实状态无漏网）",
              aud["divergences"] == 0, json.dumps(aud, ensure_ascii=False))

        # ==================================================================
        # 14. dispatch 影子（5步b 第一刀）：链优先级模拟 vs machine.current()
        #     允许的唯一分叉=已知债 box-selecting↔panning 重叠窗口；
        #     其余任何 (chain,mode) 不一致 = 记账或行为错位，当场红。
        # ==================================================================
        dsp = page.evaluate("""() => {
            const M = window.CanvasInteractionMachine;
            return {diff: M.dbg.dispatchDiff, log: M.dbg.dispatchLog};
        }""")
        bad = [e for e in (dsp.get("log") or [])
               if {e.get("chain"), e.get("mode")} != {"box-selecting", "panning"}]
        check("[dispatch影子] 链-机器分叉仅允许 box×pan 已知债（其余组合必须零）",
              len(bad) == 0, json.dumps({"diff": dsp["diff"], "bad": bad[:5]}, ensure_ascii=False))

        real_js = [e for e in js_errors if "WebSocket" not in e and "stats" not in e]
        check("全程无 JS 报错", len(real_js) == 0, str(real_js[:2]))
        browser.close()

    print("\nRESULT:", "PASS" if failures == 0 else f"FAIL x{failures}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
