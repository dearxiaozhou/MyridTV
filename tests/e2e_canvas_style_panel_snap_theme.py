# -*- coding: utf-8 -*-
"""
e2e_canvas_style_panel_snap_theme.py
=====================================
守护 2026-10-05 老王提的四项画布改动：

【1】左侧工具栏「资产库」下面新增「风格」入口；风格库 + 滤镜预设整合进同一面板，
     通过面板内 tab 切换；底部 composer 的两个 pill 保留不动。
【2】组的背景不再透明，与画布底色有色差（可看出组边界）。
【3】拖拽吸附 + 对齐辅助线；开关在左下角「连线」开关之后。
【4】画布底色由纯黑改为深灰；点阵网格由 24px 加密到 20px。

依赖：隔离测试实例 3217

⚠️ 拖拽链路必须用【合成 MouseEvent】驱动，不能用 page.mouse.down()：
   画布的 pointerdown 捕获监听器会吃掉真实指针事件链里的 mousedown，
   page.mouse.* 走下来 dragState 永远起不来（既有行为，非本次改动引入）。
   合成 el.dispatchEvent(new MouseEvent('mousedown',...)) 可正常起拖。
"""
import json, os, sys, urllib.request
from playwright.sync_api import sync_playwright

# 本机 shell 常带 http_proxy 指向 127.0.0.1:50387，会把 localhost 也代理走 → 502。
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
CHROME = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"


def create_test_canvas():
    req = urllib.request.Request(
        f"{BASE}/api/canvases",
        data=json.dumps({"name": "e2e-style-snap-theme", "nodes": [], "connections": []}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["canvas"]["id"]


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} - {label} | {detail}")
    return 0 if ok else 1


def main():
    failures = 0
    total = 0

    def t(label, ok, detail=""):
        nonlocal failures, total
        total += 1
        failures += check(label, ok, detail)

    canvas_id = create_test_canvas()
    print(f"测试画布: {canvas_id}")

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
        page = browser.new_context(viewport={"width": 1680, "height": 980}).new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/static/app_config.json*",
                   lambda r: r.fulfill(status=200, content_type="application/json",
                                       body=json.dumps({"proxy": {"base_url": BASE}})))
        page.goto(f"{BASE}/smart-canvas.html?id={canvas_id}", wait_until="networkidle")
        page.wait_for_timeout(2500)

        # ============ 【4】画布底色 + 网格密度 ============
        shell_bg = page.evaluate("() => getComputedStyle(document.querySelector('.shell')).backgroundColor")
        shell_size = page.evaluate("() => getComputedStyle(document.querySelector('.shell')).backgroundSize")
        t("画布底色不再是纯黑", shell_bg == "rgb(28, 28, 28)", shell_bg)
        t("画布底色 --x-page = #1c1c1c",
          page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--x-page').trim()") == "#1c1c1c",
          page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--x-page').trim()"))
        t("点阵网格加密到 20px", shell_size == "20px 20px", shell_size)
        t("节点卡片色比底色亮（分层可见）",
          page.evaluate("() => { const c = getComputedStyle(document.documentElement).getPropertyValue('--x-card').trim(); return c === '#242424'; }"),
          page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--x-card').trim()"))

        # ============ 【1】左侧风格面板 ============
        t("左侧出现「风格」按钮", page.evaluate("() => Boolean(document.getElementById('styleToggle'))"), "")
        t("风格按钮在资产库下方",
          page.evaluate("""() => {
              const a = document.getElementById('assetToggle').getBoundingClientRect();
              const s = document.getElementById('styleToggle').getBoundingClientRect();
              return s.y > a.y;
          }"""), "")
        t("风格面板存在", page.evaluate("() => Boolean(document.getElementById('stylePanel'))"), "")

        page.click("#styleToggle")
        page.wait_for_timeout(700)
        t("点开后风格面板打开",
          page.evaluate("() => document.getElementById('stylePanel').classList.contains('open')"), "")
        style_tiles = page.evaluate("() => document.querySelectorAll('#stylePanel [data-panel-style-option]').length")
        t("风格库 tile 已渲染（>0）", style_tiles > 0, str(style_tiles))
        t("风格分类按钮已渲染（>0）",
          page.evaluate("() => document.querySelectorAll('#stylePanel [data-panel-style-category]').length") > 0, "")

        page.click('#stylePanel [data-style-tab="filter"]')
        page.wait_for_timeout(600)
        filter_tiles = page.evaluate("() => document.querySelectorAll('#stylePanel [data-panel-filter-option]').length")
        t("切到滤镜 tab 后滤镜 tile 已渲染（>0）", filter_tiles > 0, str(filter_tiles))
        t("滤镜 pane 显示、风格 pane 隐藏",
          page.evaluate("""() => document.getElementById('stylePanelFilterPane').style.display !== 'none'
                                  && document.getElementById('stylePanelStylePane').style.display === 'none'"""), "")

        # 点一个滤镜 → 应写进 composer 的 promptInput（保留底部入口，共享同一份选中态）
        page.click('#stylePanel [data-panel-filter-option="ft-kodak"]')
        page.wait_for_timeout(700)
        t("面板选滤镜 → composer 里出现滤镜 token",
          page.evaluate("() => Boolean(document.querySelector('.mention-filter-token'))"), "")

        page.click("#styleCloseBtn")
        page.wait_for_timeout(400)
        t("关闭按钮收起面板",
          page.evaluate("() => !document.getElementById('stylePanel').classList.contains('open')"), "")

        # 底部 composer 入口保留
        t("底部 composer 风格/滤镜入口未被移除",
          page.evaluate("""() => Boolean(document.querySelector('#composerStyleModeSlot .style-mode-control'))
                              && Boolean(document.querySelector('#composerStyleModeSlot .filter-mode-control'))"""), "")

        # ============ 【3】左下角吸附开关 ============
        t("左下角出现吸附开关", page.evaluate("() => Boolean(document.getElementById('canvasSnapToggle'))"), "")
        order = page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('.canvas-bottom-tools button'));
            return btns.map(b => ({id: b.id, x: Math.round(b.getBoundingClientRect().x)})).sort((a, b) => a.x - b.x).map(b => b.id);
        }""")
        # 视觉顺序：连线的下一项（更靠右）应为吸附
        t("吸附紧排在连线之后",
          order.index("canvasInputModeToggle") + 1 < len(order) and order[order.index("canvasInputModeToggle") + 1] == "canvasSnapToggle",
          str(order))
        t("吸附默认开启", page.evaluate("() => snapEnabled === true"), "")

        page.click("#canvasSnapToggle")
        page.wait_for_timeout(400)
        t("点一下关掉", page.evaluate("() => snapEnabled === false"), "")
        t("关闭后按钮 active 态移除",
          page.evaluate("() => !document.getElementById('canvasSnapToggle').classList.contains('active')"), "")
        t("开关状态已持久化到 localStorage",
          page.evaluate("() => localStorage.getItem('smart_canvas_snap_enabled') === '0'"), "")
        page.click("#canvasSnapToggle")
        page.wait_for_timeout(400)
        t("再点一下开回来", page.evaluate("() => snapEnabled === true"), "")

        # ============ 【3b】吸附 + 对齐辅助线（合成事件） ============
        # 建两个节点
        for _ in range(2):
            page.click("#canvasAddToggle")
            page.wait_for_timeout(300)
            page.click('[data-create-type="comfy"]')
            page.wait_for_timeout(1300)
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
        t("建出两个节点", page.evaluate("() => nodes.length === 2"), str(page.evaluate("() => nodes.length")))

        # 拉开位置，避免重叠
        page.evaluate("() => { nodes[0].x = 120; nodes[0].y = 120; nodes[1].x = 760; nodes[1].y = 460; render(); }")
        page.wait_for_timeout(900)

        # 合成事件起拖：把 A 的左边缘拖到 B 的左边缘（世界 x 相同）
        page.evaluate("""() => {
            const el = document.querySelector('.image-node[data-id="' + nodes[0].id + '"]');
            const r = el.getBoundingClientRect();
            const sx = Math.round(r.x + r.width / 2), sy = Math.round(r.y + r.height * 0.06);
            el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, clientX:sx, clientY:sy, button:0, view:window}));
            const scale = (typeof viewport !== 'undefined' && viewport.scale) || 1;
            const tx = sx + (nodes[1].x - nodes[0].x) * scale, ty = sy + 320 * scale;
            window.dispatchEvent(new MouseEvent('mousemove', {bubbles:true, cancelable:true, clientX:tx, clientY:ty, button:0, view:window}));
        }""")
        page.wait_for_timeout(600)

        mid = page.evaluate("""() => ({
            drag: dragState ? dragState.id : null,
            guides: (typeof snapGuides !== 'undefined') ? snapGuides : [],
            layer: Boolean(document.querySelector('svg.snap-guide-layer')),
            lines: document.querySelectorAll('.snap-guide-layer line.snap-guide').length,
            ax: nodes[0].x, bx: nodes[1].x, ay: nodes[0].y
        })""")
        t("拖拽已启动", mid["drag"] is not None, str(mid["drag"]))
        t("出现对齐辅助线（DOM 上真画了线）", mid["lines"] >= 1, f"lines={mid['lines']}")
        t("辅助线层存在于 #world 内",
          page.evaluate("() => Boolean(document.querySelector('#world > svg.snap-guide-layer'))"), "")
        t("辅助线层 pointer-events:none（不挡交互）",
          page.evaluate("() => getComputedStyle(document.querySelector('svg.snap-guide-layer')).pointerEvents") == "none", "")
        t("X 轴已吸附：A.x 精确等于 B.x", abs(mid["ax"] - mid["bx"]) < 0.01, f"A.x={mid['ax']} B.x={mid['bx']}")
        t("辅助线记录为 x 轴", any(g.get("axis") == "x" for g in mid["guides"]), str(mid["guides"]))

        page.evaluate("() => window.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, button:0, view:window}))")
        page.wait_for_timeout(500)
        after = page.evaluate("""() => ({
            drag: dragState,
            lines: document.querySelectorAll('.snap-guide-layer line.snap-guide').length,
            guides: (typeof snapGuides !== 'undefined') ? snapGuides.length : -1
        })""")
        t("松手后拖拽结束", after["drag"] is None, "")
        t("松手后辅助线清空", after["lines"] == 0 and after["guides"] == 0,
          f"lines={after['lines']} guides={after['guides']}")

        # 关掉吸附 → 再拖不该吸附
        page.check("#canvasSnapToggle") if False else None
        page.evaluate("() => setSnapEnabled(false, {silent:true})")
        page.evaluate("""() => {
            nodes[0].x = 120; nodes[0].y = 120; render();
        }""")
        page.wait_for_timeout(600)
        page.evaluate("""() => {
            const el = document.querySelector('.image-node[data-id="' + nodes[0].id + '"]');
            const r = el.getBoundingClientRect();
            const sx = Math.round(r.x + r.width / 2), sy = Math.round(r.y + r.height * 0.06);
            el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, clientX:sx, clientY:sy, button:0, view:window}));
            const scale = (typeof viewport !== 'undefined' && viewport.scale) || 1;
            const tx = sx + (nodes[1].x - nodes[0].x) * scale + 3, ty = sy + 320 * scale;
            window.dispatchEvent(new MouseEvent('mousemove', {bubbles:true, cancelable:true, clientX:tx, clientY:ty, button:0, view:window}));
        }""")
        page.wait_for_timeout(600)
        off = page.evaluate("""() => ({
            lines: document.querySelectorAll('.snap-guide-layer line.snap-guide').length,
            ax: nodes[0].x, bx: nodes[1].x
        })""")
        t("关闭吸附后不再画辅助线", off["lines"] == 0, f"lines={off['lines']}")
        t("关闭吸附后不再吸附（A.x 不等于 B.x）", abs(off["ax"] - off["bx"]) > 0.01, f"A.x={off['ax']} B.x={off['bx']}")
        page.evaluate("() => window.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, button:0, view:window}))")
        page.wait_for_timeout(300)
        page.evaluate("() => setSnapEnabled(true, {silent:true})")

        # ============ 【2】组背景 ============
        page.evaluate("""() => {
            nodes.push({id:'grp_e2e_1', type:'smart-group', x:1200, y:180, w:520, h:320, title:'E2E组', memberIds:[]});
            render();
        }""")
        page.wait_for_timeout(900)
        t("组节点已渲染", page.evaluate("() => Boolean(document.querySelector('.image-node.canvas-group-node'))"), "")
        group_bg = page.evaluate("() => { const el = document.querySelector('.image-node.canvas-group-node'); return el ? getComputedStyle(el).backgroundColor : 'none'; }")
        canvas_bg = page.evaluate("() => getComputedStyle(document.querySelector('.shell')).backgroundColor")
        t("组背景不透明（alpha=1）", "rgba" not in group_bg or ", 1)" in group_bg, group_bg)
        t("组背景与画布底色有色差", group_bg != canvas_bg, f"组={group_bg} 画布={canvas_bg}")

        # ============ 无 JS 报错 ============
        real_errors = [e for e in errors if "WebSocket" not in e and "stats" not in e]
        t("无 JS 报错", len(real_errors) == 0, str(real_errors[:3]))

        browser.close()

    print(f"\nRESULT: {total - failures}/{total}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
