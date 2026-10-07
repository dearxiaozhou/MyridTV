# -*- coding: utf-8 -*-
"""Instrumentation pass: count hot calls + total cost per call during a multitask run.

Answers: during N concurrent jobs, how many times per second do we call render(),
refreshConnectionLayer(), updateComfyNodeLiveState(), scheduleSave(), and how many
ms does each account for? Uses the disposable instance on 3217.
"""
import json
import os
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217").rstrip("/")
CHROME = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
VIEWPORT = {"width": 1680, "height": 980}
NODE_COUNT = 200
CONN_COUNT = 40
PERIOD_MS = 6000
SVG_FIXTURE = ('<svg xmlns="http://www.w3.org/2000/svg" width="128" height="96">'
               '<rect width="128" height="96" fill="#365f91"/></svg>')
IMAGE_URL = "/benchmark-media.svg"

INSTRUMENT = """([jobCount]) => {
  const stats = window.__stats = {};
  const wrap = (name, fnHolder) => {
    let fn = (typeof fnHolder === 'function') ? fnHolder : window[fnHolder];
    stats[name] = {calls: 0, ms: 0};
    const wrapped = function(...args){
      const t = performance.now();
      const out = fn.apply(this, args);
      stats[name].calls++; stats[name].ms += performance.now() - t;
      return out;
    };
    return wrapped;
  };
  // hot candidates
  window.render = wrap('render', () => renderBody());
  function renderBody(){ return window.__origRender(); }
  const origRender = window.render;
  // keep original callable
  window.__origRenderGuard = true;
  return true;
}"""

INSTRUMENT2 = """([jobCount]) => {
  const stats = window.__stats = {};
  function patch(name, get){
    const orig = get();
    if (typeof orig !== 'function') return;
    stats[name] = {calls: 0, ms: 0};
    const wrapped = function(...a){
      const t = performance.now();
      try { return orig.apply(this, a); }
      finally { stats[name].calls++; stats[name].ms += performance.now() - t; }
    };
    return wrapped;
  }
  // render is a top-level function declaration -> reassignable on window
  const origRender = window.render;
  stats['render'] = {calls:0, ms:0};
  window.render = function(...a){
    const t = performance.now();
    try { return origRender.apply(this, a); }
    finally { stats['render'].calls++; stats['render'].ms += performance.now() - t; }
  };
  if (window.refreshConnectionLayer){
    const origRcl = window.refreshConnectionLayer;
    stats['refreshConnectionLayer'] = {calls:0, ms:0};
    window.refreshConnectionLayer = function(...a){
      const t = performance.now();
      try { return origRcl.apply(this, a); }
      finally { stats['refreshConnectionLayer'].calls++; stats['refreshConnectionLayer'].ms += performance.now() - t; }
    };
  }
  if (window.updateComfyNodeLiveState){
    const orig = window.updateComfyNodeLiveState;
    stats['updateComfyNodeLiveState'] = {calls:0, ms:0};
    window.updateComfyNodeLiveState = function(...a){
      const t = performance.now();
      try { return orig.apply(this, a); }
      finally { stats['updateComfyNodeLiveState'].calls++; stats['updateComfyNodeLiveState'].ms += performance.now() - t; }
    };
  }
  if (window.renderConnections){
    const orig = window.renderConnections;
    stats['renderConnections'] = {calls:0, ms:0};
    window.renderConnections = function(...a){
      const t = performance.now();
      try { return orig.apply(this, a); }
      finally { stats['renderConnections'].calls++; stats['renderConnections'].ms += performance.now() - t; }
    };
  }
  stats['saveCanvas'] = {calls:0, ms:0};
  const origSave = window.saveCanvas;
  window.saveCanvas = async function(...a){
    const t = performance.now();
    try { return await origSave.apply(this, a); }
    finally { stats['saveCanvas'].calls++; stats['saveCanvas'].ms += performance.now() - t; }
  };
  if (window.syncNodeProgressRing){}
  stats['t0'] = performance.now();
  return Object.keys(stats);
}"""

READ_STATS = """() => {
  const el = performance.now() - window.__stats.t0;
  const out = {};
  for (const [k, v] of Object.entries(window.__stats)) {
    if (k === 't0') continue;
    out[k] = {calls: v.calls, ms: Math.round(v.ms), calls_per_s: +(v.calls / (el/1000)).toFixed(1), ms_per_call: v.calls ? +(v.ms/v.calls).toFixed(2) : 0};
  }
  out['__windowMs'] = Math.round(el);
  return out;
}"""

START = """([jobCount]) => {
  const targets = nodes.slice(0, jobCount);
  targets.forEach((n, i) => {
    n.pending = 1; n.comfyStatus = 'running'; n.comfyJobId = 'bench-' + i;
    n.comfyRunToken = 'tok' + i; n.comfyProgress = 8 + (i % 9) * 9;
    n.runStartedAt = n.comfyStartedAt = Date.now();
  });
  render();
  startComfyJobSupervisor();
  let tick = 0;
  window.__stop = () => { clearInterval(window.__fg); stopComfyJobSupervisor(); };
  window.__fg = setInterval(() => {
    tick++;
    targets.forEach((n) => {
      n.comfyProgress = (Number(n.comfyProgress || 0) + 1.3) % 96;
      window.updateComfyNodeLiveState(n, {started_at: Number(n.comfyStartedAt || 0)/1000, progress: n.comfyProgress});
    });
    if (tick % 3 === 0) scheduleSave();
  }, 900);
  return targets.length;
}"""


def api(method, path, payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=body,
                                 headers={"Content-Type": "application/json"} if body else {}, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def create_canvas(job_count, offscreen):
    nodes = []
    for i in range(NODE_COUNT):
        # OFFSCREEN=1：把「运行中」的那批节点丢到画布远端（画面外），复现用户场景 ——
        # 这批节点会被视口裁剪掉、不在 DOM 里。
        far = offscreen and i < job_count
        nodes.append({
            "id": f"mt-{i:03d}", "type": "smart-image",
            "x": (5000 + (i % 6) * 300) if far else 80 + (i % 10) * 300,
            "y": (4000 + (i // 6) * 260) if far else 80 + (i // 10) * 260,
            "w": 220, "h": 180,
            "images": [{"url": IMAGE_URL, "name": "benchmark.svg", "kind": "image"}],
        })
    conns = [{"from": f"mt-{i:03d}", "to": f"mt-{i+1:03d}", "kind": "flow"} for i in range(CONN_COUNT)]
    return api("POST", "/api/canvases", {"title": "multitask instrument", "nodes": nodes,
                                         "connections": conns, "settings": {}, "inputMode": "connections"})["canvas"]["id"]


def main():
    job_count = int(os.environ.get("MYRIDTV_PERF_JOBS", "12"))
    offscreen = os.environ.get("MYRIDTV_PERF_OFFSCREEN") == "1"
    canvas_id = create_canvas(job_count, offscreen)
    print(f"canvas={canvas_id} nodes={NODE_COUNT} conns={CONN_COUNT} jobs={job_count} offscreen={offscreen}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport=VIEWPORT)
        page = ctx.new_page()
        page.on("pageerror", lambda e: print("PAGEERROR:", str(e)[:160]))
        page.route("**/static/app_config.json*", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps({"proxy": {"base_url": BASE}})))
        page.route("**/benchmark-media.svg*", lambda r: r.fulfill(
            status=200, content_type="image/svg+xml", body=SVG_FIXTURE))
        body = {"ok": True, "job_id": "bench", "status": "running", "progress": 42.0, "queue_position": -1,
                "started_at": time.time(), "finished_at": 0, "error": "", "notice": "",
                "prompt_id": "bench-prompt", "images": [], "videos": []}
        page.route("**/api/comfyui/jobs**", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(body)))
        page.goto(f"{BASE}/smart-canvas.html?id={canvas_id}", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_function("c => Array.isArray(nodes) && nodes.length === c && canvas?.id", arg=NODE_COUNT, timeout=60000)
        page.wait_for_function("() => [...document.querySelectorAll('.image-node .node-img')].every(i=>i.complete&&i.naturalWidth>0)", timeout=30000)
        print("instrumented:", page.evaluate(INSTRUMENT2, [job_count]))
        page.evaluate(START, [job_count])
        page.wait_for_timeout(PERIOD_MS)
        stats = page.evaluate(READ_STATS)
        page.evaluate("() => { try{window.__stop && window.__stop();}catch(e){} }")
        ctx.close(); browser.close()
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    win = stats.pop("__windowMs", 0)
    for k, v in sorted(stats.items(), key=lambda kv: -kv[1]["ms"]):
        print(f"{k:28s} calls={v['calls']:5d} ({v['calls_per_s']:6.1f}/s) total={v['ms']:6d}ms ({round(v['ms']/win*100,1):5.1f}% of window) per={v['ms_per_call']}ms")


if __name__ == "__main__":
    main()
