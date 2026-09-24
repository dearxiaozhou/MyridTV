# -*- coding: utf-8 -*-
"""
e2e_canvas_group_zorder.py
==========================
守护「分组后组内节点点击命中」修复（2026-09-23）：

旧 bug：nodeLayerZ() 不认 smart-group，render 模板内联特判组=1，
但 syncSelectionUi / refreshNodeLayerStyles 事后用 nodeLayerZ 直写 style.zIndex
会把组框抬成 2 = 与未选中成员同层 → 覆盖关系退化成 DOM 追加顺序（随增量重渲染漂移），
组框盖住成员时点成员 = 命中组框（选中组而非节点），表现为「有时死活点不到」。

断言：
1. 建组后 render → 组 zIndex == '1'
2. 点选组内成员（走 syncSelectionUi 路径）→ 成员=4，组仍=1（修复前此处组会变 2）
3. bringNodesToFront(成员) → refreshNodeLayerStyles 全量刷 → 组仍=1
4. 成员中心点 elementsFromPoint 命中在成员自身（不被组框拦截）
5. Ctrl+G groupSelectedNodes 建组路径 → 新组 zIndex=1
"""
import json, sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:3217"


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} - {label} | {detail}")
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

        # 预置：两个有图节点 + 一个组（组框覆盖成员区域）
        setup = page.evaluate("""() => {
            const mkNode = (id, x, y) => nodes.push({
                id, type: 'smart-image', title: id, x, y, w: 300, h: 200,
                images: [{url: '/assets/input/ref_test.png', name: 't', kind: 'image', generatedResult: true}]
            });
            mkNode('gz_n1', 400, 300);
            mkNode('gz_n2', 720, 300);
            nodes.push({
                id: 'gz_group', type: 'smart-group', title: '测试组',
                x: 380, y: 258, w: 660, h: 260, memberIds: ['gz_n1', 'gz_n2'],
                created_at: Date.now()
            });
            render();
            scheduleSave();
            const z = id => {
                const el = document.querySelector(`.image-node[data-id="${id}"]`);
                return el ? (el.style.zIndex || getComputedStyle(el).zIndex) : 'MISSING';
            };
            return {groupZ0: z('gz_group'), n1Z0: z('gz_n1')};
        }""")
        failures += not check("render 后组 zIndex=1", setup["groupZ0"] == "1", str(setup))

        # 1) 走真实选中路径：selectNodeFromPointer（内部 syncSelectionUi 直写 zIndex）
        step1 = page.evaluate("""() => {
            selectNodeFromPointer('gz_n1', null, {});
            const z = id => document.querySelector(`.image-node[data-id="${id}"]`).style.zIndex;
            return {memberZ: z('gz_n1'), groupZ: z('gz_group'), unselectedZ: z('gz_n2')};
        }""")
        failures += not check("点选成员后：成员抬到 4", step1["memberZ"] == "4", str(step1))
        failures += not check("点选成员后：组仍压在底下 =1（修复前=2 与成员旧值同层）", step1["groupZ"] == "1", str(step1))

        # 2) bringNodesToFront 全量刷新路径
        step2 = page.evaluate("""() => {
            bringNodesToFront(['gz_n1']);
            const z = id => document.querySelector(`.image-node[data-id="${id}"]`).style.zIndex;
            return {groupZ: z('gz_group'), memberZ: z('gz_n1')};
        }""")
        failures += not check("bringNodesToFront 全量刷后组仍=1", step2["groupZ"] == "1", str(step2))

        # 3) 真实命中：成员中心的 elementsFromPoint 第一个 .image-node 必须是成员
        hit = page.evaluate("""() => {
            const el = document.querySelector('.image-node[data-id="gz_n1"]');
            const r = el.getBoundingClientRect();
            const stack = document.elementsFromPoint(r.x + r.width/2, r.y + r.height/2);
            const top = stack.find(x => x.classList && x.classList.contains('image-node'));
            return top ? top.dataset.id : 'NONE';
        }""")
        failures += not check("成员中心命中在成员本体（不被组框拦截）", hit == "gz_n1", hit)

        # 4) Ctrl+G 建组路径产出的组同样 =1
        step4 = page.evaluate("""() => {
            selectedIds = []; selectedId = '';
            // 用真实交互：选中两个图片节点再 groupSelectedNodes
            const a = document.querySelector('.image-node[data-id="gz_n1"]');
            a.dispatchEvent(new MouseEvent('pointerdown', {bubbles: true}));
            a.dispatchEvent(new MouseEvent('pointerup', {bubbles: true}));
            return 'manual';
        }""")
        step4b = page.evaluate("""() => {
            // 直接调用应用函数验证其经 render 后组 z=1
            selectedIds = ['gz_n1', 'gz_n2']; selectedId = '';
            render();
            groupSelectedNodes();
            const gid = nodes.find(n => n.type === 'smart-group' && !n.id.startsWith('gz_')) ;
            const el = gid && document.querySelector(`.image-node[data-id="${gid.id}"]`);
            return el ? el.style.zIndex : 'NO_GROUP_EL';
        }""")
        failures += not check("Ctrl+G 建组后新组 zIndex=1", step4b == "1", str(step4b))

        real_errors = [e for e in errors if "WebSocket" not in e and "stats" not in e]
        failures += not check("无 JS 报错", len(real_errors) == 0, str(real_errors[:3]))

        browser.close()

    total = 6
    print(f"\nRESULT: {total - failures}/{total}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
