# -*- coding: utf-8 -*-
"""Opt-in interaction benchmark for 50/100/300 node canvases.

Run with:
  powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_regression.ps1 -Only scale_benchmark -IncludePerformanceBenchmarks

The runner provides a disposable backend and user-data directory. Timings include
browser automation overhead, so compare runs made on the same machine and browser.
"""
import json
import math
import os
import time
import urllib.request

from playwright.sync_api import sync_playwright


BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217").rstrip("/")
CHROME = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
NODE_COUNTS = (50, 100, 300)
LOAD_SAMPLES = 8
INTERACTION_SAMPLES = 8
CONNECT_SAMPLES = 5
VIEWPORT = {"width": 1680, "height": 980}
P95_BUDGET_MS = {
    "load": 750,
    "drag": 200,
    "zoom": 120,
    "connect": 500,
    "save": 200,
}
SVG_FIXTURE = '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="96"><rect width="128" height="96" fill="#365f91"/><circle cx="64" cy="48" r="28" fill="#e6c36a"/></svg>'
IMAGE_FIXTURE_URL = "/benchmark-media.svg"
results = []


def check(label, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + label + (" | " + str(detail)[:260] if detail else ""))


def api(method, path, payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        BASE + path,
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def create_canvas(node_count):
    nodes = []
    for index in range(node_count):
        if index == 0:
            x, y = 100, 100
        elif index == 1:
            x, y = 620, 100
        else:
            offset = index - 2
            x = 100 + (offset % 12) * 270
            y = 440 + (offset // 12) * 210
        nodes.append({
            "id": f"scale-{node_count}-{index:03d}",
            "type": "smart-image",
            "x": x,
            "y": y,
            "w": 220,
            "h": 180,
            # Every synthetic image node has a tiny inline image. This includes
            # media layout/decode work without relying on user assets or network.
            "images": [{"url": IMAGE_FIXTURE_URL, "name": "benchmark.svg", "kind": "image"}],
        })
    canvas = api("POST", "/api/canvases", {
        "title": f"Canvas scale benchmark {node_count}",
        "nodes": nodes,
        "connections": [],
        "settings": {},
        "inputMode": "connections",
    })["canvas"]
    return canvas["id"]


def prepare_page(page, canvas_id, node_count, errors):
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route(
        "**/static/app_config.json*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"proxy": {"base_url": BASE}}),
        ),
    )
    page.route(
        "**/benchmark-media.svg*",
        lambda route: route.fulfill(status=200, content_type="image/svg+xml", body=SVG_FIXTURE),
    )
    page.goto(f"{BASE}/smart-canvas.html?id={canvas_id}", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_function(
        "count => Array.isArray(nodes) && nodes.length === count && canvas?.id",
        arg=node_count,
        timeout=60000,
    )
    page.locator(f'.image-node[data-id="scale-{node_count}-000"]').wait_for(state="attached", timeout=30000)
    page.locator(f'.image-node[data-id="scale-{node_count}-001"] .node-port.port-in').wait_for(state="attached", timeout=30000)
    page.wait_for_function(
        "() => [...document.querySelectorAll('.image-node .node-img')].every(img => img.complete && img.naturalWidth > 0)",
        timeout=30000,
    )


def percentile(values, pct):
    ordered = sorted(float(value) for value in values)
    index = max(0, min(len(ordered) - 1, math.ceil((pct / 100) * len(ordered)) - 1))
    return round(ordered[index], 2)


def summarize(values):
    return {"samples": len(values), "p50_ms": percentile(values, 50), "p95_ms": percentile(values, 95), "max_ms": round(max(values), 2)}


def center(page, selector):
    box = page.locator(selector).bounding_box()
    if not box:
        raise RuntimeError(f"target is not rendered: {selector}")
    # Port hit areas touch the node boundary; keep fractional coordinates so
    # rounding does not move the pointer one pixel outside the hovered node.
    return (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def run_drag(page, node_id, node_count, sample):
    selector = f'.image-node[data-id="{node_id}"]'
    start_model = page.evaluate("id => {const n=nodes.find(item=>item.id===id);return {x:n.x,y:n.y}}", node_id)
    box = page.locator(selector).bounding_box()
    if not box:
        raise RuntimeError(f"drag node is not rendered: {node_id}")
    start_x = round(box["x"] + box["width"] * 0.72)
    start_y = round(box["y"] + box["height"] * 0.66)
    delta = 24 if sample % 2 == 0 else -24
    began = time.perf_counter()
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x + delta, start_y + 12, steps=3)
    page.mouse.up()
    page.wait_for_function(
        "arg => {const n=nodes.find(item=>item.id===arg.id);return n && (n.x!==arg.x || n.y!==arg.y)}",
        arg={"id": node_id, "x": start_model["x"], "y": start_model["y"]},
        timeout=5000,
    )
    return (time.perf_counter() - began) * 1000


def run_zoom(page, sample):
    before = page.evaluate("CanvasViewport.viewport.scale")
    page.mouse.move(VIEWPORT["width"] // 2, VIEWPORT["height"] // 2)
    began = time.perf_counter()
    page.mouse.wheel(0, -60 if sample % 2 == 0 else 60)
    page.wait_for_function("before => CanvasViewport.viewport.scale !== before", arg=before, timeout=5000)
    return (time.perf_counter() - began) * 1000


def run_connect(page, node_count):
    source_node = f'scale-{node_count}-000'
    # Keep the source port hit target enabled while the cursor moves off the node.
    # Selection is test setup only; the measured connection remains a real pointer drag.
    page.evaluate("id => { selectedId = id; selectedIds = []; syncSelectionUi(); }", source_node)
    source = f'.image-node[data-id="scale-{node_count}-000"] .node-port.port-out'
    target = f'.image-node[data-id="scale-{node_count}-001"] .node-port.port-in'
    source_x, source_y = center(page, source)
    target_x, target_y = center(page, target)
    before = page.evaluate("canvas.connections.length")
    began = time.perf_counter()
    page.mouse.move(source_x, source_y)
    page.mouse.down()
    try:
        page.wait_for_function(
            "() => portDragState && portDragState.fromPort === 'out'",
            timeout=3000,
        )
    except Exception:
        start_debug = page.evaluate("""point => ({
            mode:canvasInputMode(),
            drag:typeof portDragState === 'undefined' ? null : portDragState,
            hit:(el=>el ? {tag:el.tagName,cls:el.className,node:el.closest('.image-node')?.dataset.id} : null)(document.elementFromPoint(point.x,point.y)),
            source:document.querySelector('.image-node[data-id="scale-' + nodes.length + '-000"]')?.outerHTML.slice(0,900),
            bodyOverflow:document.body.scrollHeight
        })""", {"x": source_x, "y": source_y})
        print("PORT_START_DEBUG: " + json.dumps({"source": [source_x, source_y], "detail": start_debug}, ensure_ascii=False))
        raise
    page.mouse.move(target_x, target_y, steps=8)
    page.wait_for_function(
        "() => portDragState && portDragState.hoverPort === 'in'",
        timeout=3000,
    )
    page.mouse.up()
    try:
        page.wait_for_function("before => canvas.connections.length > before", arg=before, timeout=5000)
    except Exception:
        debug = page.evaluate("""() => ({
            mode:canvasInputMode(),
            connections:canvas.connections,
            portDragState:typeof portDragState === 'undefined' ? null : portDragState,
            ports:[...document.querySelectorAll('.node-port')].slice(0,8).map(el=>({
                cls:el.className,
                node:el.closest('.image-node')?.dataset.id,
                rect:(r=>({x:r.x,y:r.y,width:r.width,height:r.height}))(el.getBoundingClientRect())
            })),
            anchorNodes:nodes.slice(0,2).map(n=>({id:n.id,x:n.x,y:n.y}))
        })""")
        print("CONNECT_DEBUG: " + json.dumps({"source": [source_x, source_y], "target": [target_x, target_y], "before": before, "after": debug}, ensure_ascii=False))
        raise
    elapsed = (time.perf_counter() - began) * 1000
    # Reset only the disposable fixture between samples; connection timing above is
    # measured through the real port drag gesture and path creation.
    page.evaluate("""() => {
        canvas.connections.splice(0);
        clearTimeout(saveTimer);
        saveTimer = null;
        render();
    }""")
    return elapsed


def run_save(page):
    began = time.perf_counter()
    saved = page.evaluate("async () => await saveCanvas()")
    elapsed = (time.perf_counter() - began) * 1000
    if not saved:
        raise RuntimeError("saveCanvas returned false")
    return elapsed


def main():
    browser_errors = []
    report = {
        "browser": "",
        "viewport": VIEWPORT,
        "load_cache": "first navigation plus same-context warm-cache navigations",
        "p95_budget_ms": P95_BUDGET_MS,
        "node_counts": {},
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=CHROME,
            headless=True,
            args=["--no-sandbox"],
        )
        report["browser"] = "Chromium " + browser.version
        context = browser.new_context(viewport=VIEWPORT)
        for node_count in NODE_COUNTS:
            canvas_id = create_canvas(node_count)
            load_times = []
            working_page = None
            for sample in range(LOAD_SAMPLES):
                page = context.new_page()
                began = time.perf_counter()
                prepare_page(page, canvas_id, node_count, browser_errors)
                load_times.append((time.perf_counter() - began) * 1000)
                if sample + 1 == LOAD_SAMPLES:
                    working_page = page
                else:
                    page.close()

            node_id = f"scale-{node_count}-000"
            drag_times = [run_drag(working_page, node_id, node_count, sample) for sample in range(INTERACTION_SAMPLES)]
            zoom_times = [run_zoom(working_page, sample) for sample in range(INTERACTION_SAMPLES)]
            connect_times = [run_connect(working_page, node_count) for _ in range(CONNECT_SAMPLES)]
            working_page.wait_for_function("!canvasSyncInFlight", timeout=15000)
            working_page.evaluate("() => { clearTimeout(saveTimer); saveTimer = null; }")
            save_times = [run_save(working_page) for _ in range(INTERACTION_SAMPLES)]
            rendered_count = working_page.locator(".image-node").count()
            decoded_image_count = working_page.locator(".image-node .node-img").count()
            check(f"{node_count} 节点画布完整加载", len(load_times) == LOAD_SAMPLES, f"rendered DOM nodes={rendered_count}; decoded images={decoded_image_count}")
            check(f"{node_count} 节点拖动实测完成", len(drag_times) == INTERACTION_SAMPLES)
            check(f"{node_count} 节点缩放实测完成", len(zoom_times) == INTERACTION_SAMPLES)
            check(f"{node_count} 节点端口连线实测完成", len(connect_times) == CONNECT_SAMPLES)
            check(f"{node_count} 节点服务端保存成功", len(save_times) == INTERACTION_SAMPLES)
            measured = {
                "rendered_dom_nodes": rendered_count,
                "decoded_dom_images": decoded_image_count,
                "load": summarize(load_times),
                "drag": summarize(drag_times),
                "zoom": summarize(zoom_times),
                "connect": summarize(connect_times),
                "save": summarize(save_times),
            }
            for operation, budget in P95_BUDGET_MS.items():
                p95 = measured[operation]["p95_ms"]
                check(f"{node_count} 节点{operation} p95 在预算内", p95 <= budget, f"{p95}ms / {budget}ms")
            report["node_counts"][str(node_count)] = measured
            working_page.close()
        context.close()
        browser.close()

    check("性能基线操作无未捕获脚本异常", not browser_errors, browser_errors[:5])
    print("PERFORMANCE_BASELINE: " + json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    passed = sum(results)
    print(f"RESULT: {passed}/{len(results)}")
    raise SystemExit(0 if passed == len(results) else 1)
if __name__ == "__main__":
    main()
