# -*- coding: utf-8 -*-
"""Multi-task (many concurrent ComfyUI jobs) frontend cost measurement.

Runs against the disposable instance on 3217. Emulates K concurrent running nodes
without touching ComfyUI: the job endpoints are stubbed, but every frontend path
(poll -> live-state update -> progress ring write -> save) is the real one.

Measurements: frame pacing (p95 / dropped frames) and long-task occupancy.
"""
import json
import math
import os
import statistics
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217").rstrip("/")
CHROME = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
USE_EDGE = os.environ.get("MYRIDTV_PERF_EDGE") == "1"
VIEWPORT = {"width": 1680, "height": 980}
NODE_COUNT = int(os.environ.get("MYRIDTV_PERF_NODES", "200"))
CONN_COUNT = 40
SAMPLE_MS = 6000

SVG_FIXTURE = ('<svg xmlns="http://www.w3.org/2000/svg" width="128" height="96">'
               '<rect width="128" height="96" fill="#365f91"/>'
               '<circle cx="64" cy="48" r="28" fill="#e6c36a"/></svg>')
# MYRIDTV_PERF_BIG=1 -> 用真实的 1254px 风格缩略图当节点内容，逼近用户画布的光栅化压力
BIG_IMAGES = [
    "/static/images/styles/generated/rh-2d-adult-psychological.webp",
    "/static/images/styles/generated/rh-2d-adventure-shonen.webp",
    "/static/images/styles/generated/rh-2d-action-classic.webp",
    "/static/images/styles/generated/rh-2d-adult-melancholy.webp",
]
USE_BIG = os.environ.get("MYRIDTV_PERF_BIG") == "1"
IMAGE_URL = "/benchmark-media.svg"

VARIANTS = [
    ("A-baseline", {"css": "", "noSave": False}),
    ("B-no-comet-filter", {"css": ".connection-layer .conn-comet{filter:none !important}", "noSave": False}),
    ("C-no-poll-save", {"css": "", "noSave": True}),
    ("D-both", {"css": ".connection-layer .conn-comet{filter:none !important}", "noSave": True}),
]

START_BENCH = """([jobCount, noSave]) => {
  clearTimeout(saveTimer); saveTimer = null;
  const targets = nodes.slice(0, jobCount);
  targets.forEach((n, i) => {
    n.pending = 1;
    n.comfyStatus = 'running';
    n.comfyJobId = 'bench-' + i;
    n.comfyRunToken = 'tok' + i;
    n.comfyProgress = 8 + (i % 9) * 9;
    n.runStartedAt = n.comfyStartedAt = Date.now();
  });
  render();
  if (noSave) { window.__origScheduleSave = scheduleSave; try { eval('scheduleSave = function(){}'); } catch(e) {} }
  startComfyJobSupervisor();
  let tick = 0;
  window.__stopBench = () => { clearInterval(window.__fg); stopComfyJobSupervisor(); };
  window.__fg = setInterval(() => {
    tick++;
    targets.forEach((n, i) => {
      n.comfyProgress = (Number(n.comfyProgress || 0) + 1.3) % 96;
      updateComfyNodeLiveState(n, {started_at: Number(n.comfyStartedAt || 0) / 1000, progress: n.comfyProgress});
    });
    if (tick % 3 === 0) { if (!noSave) window.__origScheduleSave ? scheduleSave() : scheduleSave(); }
  }, 900);
  return targets.length;
}"""

MEASURE = """(durationMs) => new Promise(resolve => {
  const long = [];
  const po = new PerformanceObserver(list => { for (const e of list.getEntries()) long.push(e.duration); });
  try { po.observe({entryTypes:['longtask']}); } catch(e) {}
  const frames = [];
  const t0 = performance.now();
  let last = t0;
  function tick(now){
    const dt = now - last; last = now;
    if (frames.length >= 0 && dt > 0) frames.push(dt);
    if (now - t0 < durationMs) requestAnimationFrame(tick);
    else {
      po.disconnect();
      const elapsed = now - t0;
      const sorted = frames.slice(1).sort((a,b)=>a-b);
      const pct = p => sorted.length ? +sorted[Math.min(sorted.length-1, Math.ceil(p/100*sorted.length)-1)].toFixed(1) : 0;
      resolve({
        elapsedMs: Math.round(elapsed),
        frames: sorted.length,
        fps: +(sorted.length / (elapsed/1000)).toFixed(1),
        frame_p50: pct(50), frame_p95: pct(95), frame_max: +(Math.max(...sorted, 0)).toFixed(1),
        dropped: sorted.filter(v => v > 33).length,
        longtasks: long.length,
        longtask_ms: Math.round(long.reduce((a,b)=>a+b, 0)),
        busy_pct: +(long.reduce((a,b)=>a+b, 0) / elapsed * 100).toFixed(1),
      });
    }
  }
  requestAnimationFrame(tick);
})"""


def api(method, path, payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=body,
                                 headers={"Content-Type": "application/json"} if body else {},
                                 method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def create_canvas(job_count):
    nodes = []
    for i in range(NODE_COUNT):
        nodes.append({
            "id": f"mt-{i:03d}",
            "type": "smart-image",
            "x": 80 + (i % 10) * 300,
            "y": 80 + (i // 10) * 260,
            "w": 220, "h": 180,
            "images": [{"url": (BIG_IMAGES[i % len(BIG_IMAGES)] if USE_BIG else IMAGE_URL),
                        "name": "benchmark", "kind": "image"}],
        })
    conns = []
    for i in range(CONN_COUNT):
        conns.append({"from": f"mt-{i:03d}", "to": f"mt-{i+1:03d}", "kind": "flow"})
    return api("POST", "/api/canvases", {
        "title": f"multitask perf {job_count} jobs",
        "nodes": nodes,
        "connections": conns,
        "settings": {},
        "inputMode": "connections",
    })["canvas"]["id"]


def stub_jobs(route):
    """Return a synthetic running job so no ComfyUI work happens."""
    body = json.dumps({
        "ok": True,
        "job_id": "bench",
        "status": "running",
        "progress": 42.0,
        "queue_position": -1,
        "current_node": "KSampler",
        "current_node_title": "采样器",
        "started_at": time.time(),
        "finished_at": 0,
        "error": "",
        "notice": "",
        "prompt_id": "bench-prompt",
        "images": [],
        "videos": [],
    })
    route.fulfill(status=200, content_type="application/json", body=body)


def main():
    job_count = int(os.environ.get("MYRIDTV_PERF_JOBS", "12"))
    canvas_id = create_canvas(job_count)
    print(f"canvas={canvas_id} nodes={NODE_COUNT} connections={CONN_COUNT} jobs={job_count}")
    results = {}
    with sync_playwright() as pw:
        exe = EDGE if USE_EDGE else CHROME
        browser = pw.chromium.launch(executable_path=exe, headless=not USE_EDGE,
                                     args=["--no-sandbox", "--force-device-scale-factor=1",
                                           "--window-size=1680,980"])
        ctx = browser.new_context(viewport=VIEWPORT)
        page = ctx.new_page()
        page.on("pageerror", lambda e: print("PAGEERROR:", str(e)[:200]))
        page.route("**/static/app_config.json*", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"proxy": {"base_url": BASE}})))
        page.route("**/benchmark-media.svg*", lambda route: route.fulfill(
            status=200, content_type="image/svg+xml", body=SVG_FIXTURE))
        page.route("**/api/comfyui/jobs**", stub_jobs)
        for label, cfg in VARIANTS:
            page.goto(f"{BASE}/smart-canvas.html?id={canvas_id}", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_function("count => Array.isArray(nodes) && nodes.length === count && canvas?.id",
                                   arg=NODE_COUNT, timeout=60000)
            page.wait_for_function(
                "() => { const imgs=[...document.querySelectorAll('.image-node .node-img')];"
                "const done=imgs.filter(i=>i.complete&&i.naturalWidth>0).length;"
                "return imgs.length>0 && done/imgs.length >= 0.8; }",
                timeout=120000)
            if cfg["css"]:
                page.add_style_tag(content=cfg["css"])
            n = page.evaluate(START_BENCH, [job_count, cfg["noSave"]])
            page.wait_for_timeout(700)
            r = page.evaluate(MEASURE, SAMPLE_MS)
            page.evaluate("() => { try { window.__stopBench && window.__stopBench(); } catch(e){} }")
            results[label] = r
            print(f"{label:20s} jobs={n:3d} fps={r['fps']:5.1f} p95={r['frame_p95']:6.1f}ms max={r['frame_max']:7.1f}ms "
                  f"dropped={r['dropped']:4d} longtask={r['longtasks']:4d} busy={r['busy_pct']:5.1f}%")
            page.wait_for_timeout(400)
        ctx.close()
        browser.close()
    print("RESULT_JSON: " + json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
