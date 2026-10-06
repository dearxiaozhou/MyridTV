# -*- coding: utf-8 -*-
"""
e2e_canvas_node_context_menu.py
================================
守护「画布节点右键菜单 + 提示词框编辑菜单」链路（2026-10-04）。

需求 1：画布节点（提示词节点）里的文本框要能鼠标右键复制/粘贴/全选
        —— 由画布自定义菜单提供复制/粘贴/全选，兼容 WebView2 宿主。
需求 2：空节点右击能"复制"和"删除节点"
        —— 实现方式：新增 CanvasNodeContextMenuController（复制节点/复制/删除节点）。

改造前：shell.oncontextmenu 开头就 `if(e.target.closest('.image-node')) return;`
        整个节点子树右键被吞，空节点右键什么都不弹。

依赖：隔离测试实例 3217
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
        data=json.dumps({"name": "e2e-node-ctx-menu", "nodes": [], "connections": []}).encode(),
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

        def nodes():
            return page.evaluate("() => (typeof nodes!=='undefined'?nodes:[]).map(n=>({id:n.id,type:n.type,title:n.title}))")

        def menu_open():
            return page.evaluate("() => Boolean(document.getElementById('smartNodeContextMenu')?.classList.contains('open'))")

        def editable_menu_open():
            return page.evaluate("() => Boolean(document.getElementById('smartEditableContextMenu')?.classList.contains('open'))")

        def actions():
            return page.evaluate("() => Array.from(document.querySelectorAll('#smartNodeContextMenu [data-smart-node-menu-action]')).map(b=>b.dataset.smartNodeMenuAction)")

        def visible_actions():
            return page.evaluate("""() => Array.from(document.querySelectorAll('#smartNodeContextMenu [data-smart-node-menu-action]'))
                .filter(button => getComputedStyle(button).display !== 'none' && button.getClientRects().length)
                .map(button => button.dataset.smartNodeMenuAction)""")

        def node_drop_point():
            """空节点 .node-drop 内、避开 upload 按钮的空白点（同时确认真的命中 .node-drop）。"""
            return page.evaluate("""() => {
                const el = document.querySelector('.image-node.empty-node .node-drop');
                if(!el) return null;
                const r = el.getBoundingClientRect();
                const x = Math.round(r.x + 30), y = Math.round(r.y + 40);
                const at = document.elementFromPoint(x, y);
                return (at && at.closest && at.closest('.node-drop')) ? {x, y} : null;
            }""")

        def right_click(x, y):
            page.mouse.move(x, y)
            page.mouse.down(button="right")
            page.mouse.up(button="right")
            page.wait_for_timeout(400)

        def node_point(node_id):
            return page.evaluate("""(nid) => {
                const el = document.querySelector('.image-node[data-id="'+nid+'"]');
                if(!el) return null;
                const r = el.getBoundingClientRect();
                const x = Math.round(r.x + 30), y = Math.round(r.y + 40);
                const at = document.elementFromPoint(x, y);
                if(at && at.closest && at.closest('.image-node') && !at.closest('.thumb-item, textarea, input')) return {x, y};
                return null;
            }""", node_id)

        # === 1. 建一个 comfy 节点（无产物 → empty-node，即"空节点"）===
        page.click("#canvasAddToggle")
        page.wait_for_timeout(300)
        page.click('[data-create-type="comfy"]')
        page.wait_for_timeout(1400)
        ns = nodes()
        total += 1
        failures += check("创建空节点", len(ns) == 1, json.dumps(ns, ensure_ascii=False))
        if not ns:
            print("RESULT: 0/1 (前置失败)")
            browser.close()
            sys.exit(1)
        first_id = ns[0]["id"]

        # === 2. 空节点右键弹菜单 ===
        pt = node_drop_point()
        total += 1
        failures += check("空节点可定位右键靶点", pt is not None, str(pt))
        if pt:
            right_click(pt["x"], pt["y"])
            total += 1
            failures += check("空节点右键弹出菜单", menu_open(), f"open={menu_open()}")
            total += 1
            failures += check("空节点菜单只显示复制节点和删除节点",
                              actions() == ["duplicate-node", "copy-node", "delete-node"]
                              and visible_actions() == ["duplicate-node", "delete-node"],
                              json.dumps({"all": actions(), "visible": visible_actions()}, ensure_ascii=False))
            total += 1
            failures += check("右键时该节点被选中",
                              first_id in page.evaluate("() => typeof selectedNodeIds!=='undefined'? selectedNodeIds() : []"),
                              str(page.evaluate("() => typeof selectedNodeIds!=='undefined'? selectedNodeIds() : []")))

            # === 3. 点菜单外关闭 ===
            page.mouse.click(200, 850)
            page.wait_for_timeout(400)
            total += 1
            failures += check("点菜单外关闭", menu_open() is False, f"open={menu_open()}")

            # === 4. 复制节点 ===
            right_click(pt["x"], pt["y"])
            page.click('#smartNodeContextMenu [data-smart-node-menu-action="duplicate-node"]')
            page.wait_for_timeout(1300)
            ns2 = nodes()
            total += 1
            failures += check("复制节点后节点数 +1", len(ns2) == 2, f"{len(ns2)}")
            total += 1
            failures += check("复制出的节点已关闭菜单", menu_open() is False, f"open={menu_open()}")
            dup_id = ns2[-1]["id"] if len(ns2) == 2 else ""

            # === 5. 删除节点（对复制出来那个）===
            if dup_id:
                dpt = node_point(dup_id)
                total += 1
                failures += check("副本可定位右键靶点", dpt is not None, str(dpt))
                if dpt:
                    right_click(dpt["x"], dpt["y"])
                    total += 1
                    failures += check("副本右键弹出菜单", menu_open(), f"open={menu_open()}")
                    page.click('#smartNodeContextMenu [data-smart-node-menu-action="delete-node"]')
                    page.wait_for_timeout(1300)
                    ns3 = nodes()
                    total += 1
                    failures += check("删除节点后节点数 -1", len(ns3) == 1 and ns3[0]["id"] == first_id,
                                      json.dumps(ns3, ensure_ascii=False))

        # === 6. 复制（进内部剪贴板）不改变节点数 ===
        before = len(nodes())
        # 空节点按设计隐藏「复制」。生成中的节点允许复制，因此切到该有效状态。
        page.evaluate("nid => { const node=nodes.find(item=>item.id===nid); if(node) node.pending=true; }", first_id)
        pt2 = node_drop_point()
        if pt2:
            right_click(pt2["x"], pt2["y"])
            if menu_open():
                total += 1
                failures += check("生成中节点显示复制操作",
                                  "copy-node" in visible_actions(), str(visible_actions()))
                page.click('#smartNodeContextMenu [data-smart-node-menu-action="copy-node"]')
                page.wait_for_timeout(900)
                total += 1
                failures += check("「复制」不新建节点（进剪贴板）", len(nodes()) == before,
                                  f"{before} -> {len(nodes())}")

        # === 7. Esc 关闭菜单 ===
        pt3 = node_drop_point()
        if pt3:
            right_click(pt3["x"], pt3["y"])
            if menu_open():
                page.keyboard.press("Escape")
                page.wait_for_timeout(400)
                total += 1
                failures += check("Esc 关闭节点菜单", menu_open() is False, f"open={menu_open()}")

        # === 8. 提示词节点文本框右键 → 画布自定义编辑菜单 ===
        page.click("#canvasAddToggle")
        page.wait_for_timeout(300)
        page.click('[data-create-type="prompt"]')
        page.wait_for_timeout(1300)
        has_prompt = page.evaluate("() => Boolean(document.querySelector('.prompt-node-text'))")
        total += 1
        failures += check("提示词节点文本框存在", has_prompt, str(has_prompt))
        if has_prompt:
            page.click(".prompt-node-text", button="right")
            page.wait_for_timeout(500)
            total += 1
            failures += check("文本框右键弹出编辑操作菜单",
                              editable_menu_open(), str(editable_menu_open()))
            total += 1
            edit_actions = page.locator("#smartEditableContextMenu [data-edit-action]").evaluate_all(
                "els => els.map(el => el.dataset.editAction)")
            failures += check("编辑菜单包含复制/粘贴/全选",
                              edit_actions == ["copy", "paste", "select-all"], str(edit_actions))
            total += 1
            failures += check("文本框右键不弹节点菜单", menu_open() is False, f"open={menu_open()}")
            total += 1
            failures += check("文本框右键不弹新建菜单",
                              page.evaluate("() => Boolean(document.getElementById('createMenu')?.classList.contains('open'))") is False, "")

        # === 9. 无 JS 报错 ===
        real_errors = [e for e in errors if "WebSocket" not in e and "stats" not in e]
        total += 1
        failures += check("无 JS 报错", len(real_errors) == 0, str(real_errors[:3]))

        browser.close()

    print(f"\nRESULT: {total - failures}/{total}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
