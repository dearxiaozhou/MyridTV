# -*- coding: utf-8 -*-
"""Regression guard for the multitask culling fix (2026-10-06).

1) A *visible* running node must still get a live progress ring: the ring exists and
   its stroke-dashoffset / mask follow the model progress on every update.
2) A running node that is culled OFF-screen must NOT trigger a full render() per poll.
3) When that node scrolls back into view, the cull render must draw it with its ring,
   so the user never loses progress UI.

Runs against the disposable instance on 3217 (MYRIDTV_TEST_BASE).
"""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217").rstrip("/")
CHROME = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
VIEWPORT = {"width": 1200, "height": 800}
results = []


def check(label, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + label + (" | " + str(detail)[:220] if detail else ""))


def api(method, path, payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=body,
                                 headers={"Content-Type": "application/json"} if body else {}, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def create_canvas():
    # 视口裁剪有门槛（CULL_MIN_NODES=80），测试画布必须够大才会真的裁剪。
    # rg-visible 落在首屏；rg-offscreen 丢到画布远端（必然被裁）。
    nodes = [
        {"id": "rg-visible", "type": "smart-image", "x": 120, "y": 120, "w": 220, "h": 180, "images": []},
        {"id": "rg-offscreen", "type": "smart-image", "x": 5200, "y": 4200, "w": 220, "h": 180, "images": []},
    ]
    for i in range(120):
        nodes.append({"id": f"rg-fill-{i:03d}", "type": "smart-image",
                      "x": 60 + (i % 12) * 260, "y": 60 + (i // 12) * 220,
                      "w": 200, "h": 170, "images": []})
    return api("POST", "/api/canvases", {"title": "cull regression", "nodes": nodes, "connections": [],
                                         "settings": {}, "inputMode": "connections"})["canvas"]["id"]


def main():
    canvas_id = create_canvas()
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
        pg = b.new_context(viewport=VIEWPORT).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)[:200]))
        pg.route("**/static/app_config.json*", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps({"proxy": {"base_url": BASE}})))
        pg.goto(f"{BASE}/smart-canvas.html?id={canvas_id}", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_function("() => Array.isArray(nodes) && nodes.length === 122 && canvas?.id", timeout=60000)
        pg.wait_for_selector('.image-node[data-id="rg-visible"]', timeout=20000)
        # 首屏渲染是一次全量绘制，之后才有 cull 巡查把远处的节点摘掉
        pg.wait_for_function("() => !document.querySelector('.image-node[data-id=\"rg-offscreen\"]')",
                             timeout=10000)

        check("画面外节点确实被视口裁剪",
              pg.locator('.image-node[data-id="rg-offscreen"]').count() == 0,
              f"offscreen in DOM={pg.locator('.image-node[data-id=\"rg-offscreen\"]').count()}")

        # ---- 1) 可见节点：进度环照常更新 ----
        pg.evaluate("""() => {
            const n = nodes.find(x => x.id === 'rg-visible');
            n.pending = 1; n.comfyStatus = 'running'; n.comfyJobId = 'rg-1';
            n.comfyProgress = 10; n.comfyStartedAt = Date.now(); n.runStartedAt = n.comfyStartedAt;
            updateComfyNodeLiveState(n, {started_at: n.comfyStartedAt/1000, progress: 10});
        }""")
        ring = pg.locator('.image-node[data-id="rg-visible"] .comfy-node-progress')
        check("可见节点出现进度环", ring.count() == 1, f"count={ring.count()}")
        off1 = pg.evaluate("() => document.querySelector('.image-node[data-id=\"rg-visible\"] .comfy-node-progress-path')?.getAttribute('stroke-dashoffset')")
        pg.evaluate("() => { const n = nodes.find(x=>x.id==='rg-visible'); n.comfyProgress = 55; updateComfyNodeLiveState(n, {started_at: n.comfyStartedAt/1000, progress: 55}); }")
        off2 = pg.evaluate("() => document.querySelector('.image-node[data-id=\"rg-visible\"] .comfy-node-progress-path')?.getAttribute('stroke-dashoffset')")
        check("进度环跟着进度更新", off1 != off2 and off2 is not None, f"before={off1} after={off2}")

        # ---- 2) 视野外节点：不允许每轮轮询触发全量 render() ----
        renders = pg.evaluate("""async () => {
            const n = nodes.find(x => x.id === 'rg-offscreen');
            n.pending = 1; n.comfyStatus = 'running'; n.comfyJobId = 'rg-2';
            n.comfyProgress = 5; n.comfyStartedAt = Date.now(); n.runStartedAt = n.comfyStartedAt;
            const orig = window.render;
            let calls = 0;
            window.render = function(...a){ calls++; return orig.apply(this, a); };
            for (let i = 0; i < 20; i++) {
                n.comfyProgress = 5 + i * 2;
                window.updateComfyNodeLiveState(n, {started_at: n.comfyStartedAt/1000, progress: n.comfyProgress});
            }
            window.render = orig;
            return calls;
        }""")
        check("视野外节点轮询不再触发全量渲染", renders == 0, f"render() calls={renders}")

        # ---- 3) 平移回来：cull 重绘必须带上进度环 ----
        pg.evaluate("""async () => {
            const n = nodes.find(x => x.id === 'rg-offscreen');
            viewport.x = -5000; viewport.y = -4000;
            applyViewport();
            render();
            await new Promise(r => setTimeout(r, 120));
            return true;
        }""")
        ring2 = pg.locator('.image-node[data-id="rg-offscreen"] .comfy-node-progress')
        off3 = pg.evaluate("() => document.querySelector('.image-node[data-id=\"rg-offscreen\"] .comfy-node-progress-path')?.getAttribute('stroke-dashoffset')")
        check("平移回来后节点重新出现在 DOM", ring2.count() >= 0 and pg.locator('.image-node[data-id="rg-offscreen"]').count() == 1)
        check("平移回来后进度环按最新进度渲染", ring2.count() == 1 and off3 is not None, f"ring={ring2.count()} dashoffset={off3}")

        check("无未捕获脚本异常", not errors, errors[:3])
        b.close()

    passed = sum(results)
    print(f"RESULT: {passed}/{len(results)}")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
