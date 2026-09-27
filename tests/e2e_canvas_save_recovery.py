# -*- coding: utf-8 -*-
"""Exercise automatic canvas persistence, retry recovery, and 409 merging."""
import json
import os
import sys
import time
import urllib.request
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217").rstrip("/")
CHROME = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
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
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def create_canvas(title):
    return api("POST", "/api/canvases", {"title": title, "nodes": [], "connections": [], "settings": {}})["canvas"]


def add_comfy_node(page):
    page.locator("#canvasAddToggle").click()
    page.locator('[data-create-type="comfy"]').wait_for(state="visible", timeout=5000)
    page.locator('[data-create-type="comfy"]').click()
    page.locator(".image-node").first.wait_for(state="visible", timeout=8000)
    return page.locator(".image-node").first.get_attribute("data-id")


def configure_canvas_page(page, canvas_id, errors):
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route(
        "**/static/app_config.json*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"proxy": {"base_url": BASE}}),
        ),
    )
    page.goto(f"{BASE}/smart-canvas.html?id={canvas_id}", wait_until="domcontentloaded")
    page.locator("#canvasAddToggle").wait_for(state="visible", timeout=30000)
    page.wait_for_function("id => typeof canvas !== 'undefined' && canvas?.id === id", arg=canvas_id, timeout=15000)


def main():
    recovery_canvas = create_canvas("Save recovery regression")
    conflict_canvas = create_canvas("Concurrent save regression")
    failures = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1440, "height": 900})

        # 503 once, then pass through to the isolated backend. The local draft must survive
        # the first failed write and the automatic retry must persist it before reload.
        page = context.new_page()
        errors = []
        configure_canvas_page(page, recovery_canvas["id"], errors)
        save_attempts = []
        save_responses = []
        save_requests = []
        page.on(
            "request",
            lambda request: save_requests.append({"method": request.method, "url": request.url})
            if request.method == "PUT" and f"/api/canvases/{recovery_canvas['id']}" in request.url
            else None,
        )

        def record_save_response(response):
            if response.request.method == "PUT" and urlparse(response.url).path == f"/api/canvases/{recovery_canvas['id']}":
                save_responses.append(response.status)

        page.on("response", record_save_response)

        def fail_once(route):
            request = route.request
            if request.method == "PUT" and urlparse(request.url).path == f"/api/canvases/{recovery_canvas['id']}":
                if not save_attempts:
                    save_attempts.append(503)
                    route.fulfill(
                        status=503,
                        content_type="application/json",
                        body=json.dumps({"detail": "simulated temporary storage outage"}),
                    )
                    return
                save_attempts.append(200)
            route.continue_()

        page.route("**/api/canvases/**", fail_once)
        client_node_id = add_comfy_node(page)
        page.wait_for_function(
            "() => /画布保存失败|Canvas save failed/.test(document.querySelector('#toast')?.textContent || '')",
            timeout=10000,
        )
        failure_toast = page.locator("#toast").inner_text()
        check("保存失败在界面明确提示原因", "simulated temporary storage outage" in failure_toast, failure_toast)

        page.wait_for_function(
            "id => !!localStorage.getItem('myridtv:canvas-draft:' + id)",
            arg=recovery_canvas["id"],
            timeout=5000,
        )
        check("服务器失败时本地草稿仍保留", True)
        draft_state = page.evaluate(
            """id => {
              const draft = JSON.parse(localStorage.getItem('myridtv:canvas-draft:' + id) || 'null');
              return {present:!!draft,inputMode:draft?.inputMode,nodes:draft?.nodes?.length||0};
            }""",
            recovery_canvas["id"],
        )
        check("本地草稿保留画布输入模式", draft_state["present"] and draft_state["inputMode"] == "connections", draft_state)
        page.wait_for_timeout(2500)
        page.wait_for_function(
            "async ({id,nodeId}) => { const r=await fetch('/api/canvases/'+encodeURIComponent(id)); const d=await r.json(); return d.canvas?.nodes?.some(n=>n.id===nodeId); }",
            arg={"id": recovery_canvas["id"], "nodeId": client_node_id},
            timeout=12000,
        )
        check("临时错误后自动重试并写入服务端", 503 in save_responses and 200 in save_responses, {"route": save_attempts, "requests": save_requests, "responses": save_responses})
        page.wait_for_function(
            "id => localStorage.getItem('myridtv:canvas-draft:' + id) === null",
            arg=recovery_canvas["id"],
            timeout=5000,
        )
        page.reload(wait_until="domcontentloaded")
        page.locator(f'.image-node[data-id="{client_node_id}"]').wait_for(state="visible", timeout=15000)
        check("重开画布后恢复已保存节点", page.locator(f'.image-node[data-id="{client_node_id}"]').count() == 1)

        # Verify that non-node canvas state shares the same save/reopen contract.
        persistence_canvas = create_canvas("Canvas state persistence regression")
        persistence_page = context.new_page()
        persistence_errors = []
        configure_canvas_page(persistence_page, persistence_canvas["id"], persistence_errors)
        persistence_requests = []
        persistence_responses = []
        persistence_page.on("request", lambda request: persistence_requests.append({"method": request.method, "url": request.url})
                            if "/api/canvases/" in request.url else None)
        persistence_page.on("response", lambda response: persistence_responses.append(response.status)
                            if response.request.method == "PUT" and f"/api/canvases/{persistence_canvas['id']}" in response.url else None)
        source_node_id = add_comfy_node(persistence_page)
        target_node_id = add_comfy_node(persistence_page)
        before_save = persistence_page.evaluate(
            """({sourceId,targetId}) => {
              canvas.connections = [{from:sourceId,to:targetId,kind:'input'}];
              const settingsState = {engine:'api',apiKind:'image',provider_id:'e2e-provider',model:'persisted-model',ratio:'square',resolution:'2k'};
              settings = {...settings,...settingsState};
              canvasDefaultSmartSettings = {...settingsState};
              canvasAgentArtifactsState = [{id:'e2e-persisted-artifact',kind:'image',url:'/assets/input/persisted.png'}];
              scheduleSave();
              return {canvasId:canvasId, canvasObjectId:canvas?.id, nodes:(nodes||[]).map(n=>n.id), updatedAt:canvas?.updated_at};
            }""",
            {"sourceId": source_node_id, "targetId": target_node_id},
        )
        persisted = None
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            persisted = api("GET", f"/api/canvases/{persistence_canvas['id']}")["canvas"]
            persisted_ids = [node.get("id") for node in persisted.get("nodes", [])]
            if (source_node_id in persisted_ids and target_node_id in persisted_ids
                    and any(conn.get("from") == source_node_id and conn.get("to") == target_node_id for conn in persisted.get("connections", []))
                    and persisted.get("settings", {}).get("model") == "persisted-model"
                    and any(item.get("id") == "e2e-persisted-artifact" for item in persisted.get("artifacts", []))):
                break
            time.sleep(0.15)
        persisted_ids = [node.get("id") for node in (persisted or {}).get("nodes", [])]
        persisted_ok = (source_node_id in persisted_ids and target_node_id in persisted_ids
                        and any(conn.get("from") == source_node_id and conn.get("to") == target_node_id for conn in (persisted or {}).get("connections", []))
                        and (persisted or {}).get("settings", {}).get("model") == "persisted-model"
                        and any(item.get("id") == "e2e-persisted-artifact" for item in (persisted or {}).get("artifacts", [])))
        check("连线、生成设置和产物均写入服务端", persisted_ok, {"before": before_save, "requests": persistence_requests, "responses": persistence_responses, "server": persisted})
        persistence_page.reload(wait_until="domcontentloaded")
        persistence_page.wait_for_function(
            "({id,sourceId,targetId}) => canvas?.id === id && (nodes||[]).some(n=>n.id===sourceId) && (nodes||[]).some(n=>n.id===targetId) && canvas.connections?.some(c=>c.from===sourceId && c.to===targetId) && canvas.settings?.model==='persisted-model' && (canvasAgentArtifactsState||[]).some(a=>a.id==='e2e-persisted-artifact')",
            arg={"id": persistence_canvas["id"], "sourceId": source_node_id, "targetId": target_node_id}, timeout=15000,
        )
        restored_state = persistence_page.evaluate(
            """() => ({
              nodeIds:(nodes||[]).map(n=>n.id),connections:canvas.connections||[],
              engine:canvas.settings?.engine,model:canvas.settings?.model,
              artifactIds:(canvasAgentArtifactsState||[]).map(item=>item.id)
            })"""
        )
        check(
            "重开后连线、设置与产物状态完整",
            source_node_id in restored_state["nodeIds"] and target_node_id in restored_state["nodeIds"]
            and any(conn.get("from") == source_node_id and conn.get("to") == target_node_id for conn in restored_state["connections"])
            and restored_state["engine"] == "api" and restored_state["model"] == "persisted-model"
            and "e2e-persisted-artifact" in restored_state["artifactIds"],
            restored_state,
        )

        # Simulate another client committing a valid server node just before the browser's
        # stale PUT. The real backend returns the latest canvas at the top level on HTTP 409.
        conflict_page = context.new_page()
        conflict_errors = []
        configure_canvas_page(conflict_page, conflict_canvas["id"], conflict_errors)
        conflict_statuses = []
        conflict_network = []
        conflict_page.on("request", lambda request: conflict_network.append({"method": request.method, "url": request.url}))
        initial_updated_at = conflict_page.evaluate("canvas.updated_at")
        server_node = {
            "id": "e2e-concurrent-server-node",
            "type": "smart-image",
            "title": "Concurrent server node",
            "x": 980,
            "y": 300,
            "w": 260,
            "h": 260,
            "scale": 1,
            "status": "ready",
            "role": "media",
            "created_at": 1,
            "images": [],
        }
        conflict_page.on(
            "response",
            lambda response: conflict_statuses.append(response.status)
            if response.request.method == "PUT" and urlparse(response.url).path == f"/api/canvases/{conflict_canvas['id']}"
            else None,
        )

        # Insert a competing server commit immediately before the browser submits its
        # changed canvas, so the request is guaranteed to carry a stale base version.
        injected = []
        conflict_requests = []

        def inject_concurrent_write(route):
            request = route.request
            path = urlparse(request.url).path
            if request.method == "PUT" and path == f"/api/canvases/{conflict_canvas['id']}":
                payload = request.post_data_json
                conflict_requests.append({"base": payload.get("base_updated_at"), "nodes": [n.get("id") for n in payload.get("nodes", [])]})
                if not injected and initial_updated_at:
                    current = api("GET", f"/api/canvases/{conflict_canvas['id']}")["canvas"]
                    server_payload = {
                        "title": current["title"], "icon": current["icon"],
                        "nodes": [*(current.get("nodes") or []), server_node],
                        "connections": current.get("connections") or [], "logs": current.get("logs") or [],
                        "settings": current.get("settings") or {},
                        "viewport": current.get("viewport") or {"x": 0, "y": 0, "scale": 1},
                        "deleted": current.get("deleted") or [], "artifacts": current.get("artifacts") or [],
                        "inputMode": current.get("inputMode") or "connections",
                        "base_updated_at": current.get("updated_at") or 0,
                        "client_id": "e2e-concurrent-client",
                    }
                    api("PUT", f"/api/canvases/{conflict_canvas['id']}", server_payload)
                    injected.append({"client_base": payload.get("base_updated_at"), "server_previous": current.get("updated_at")})
            route.continue_()

        conflict_page.route("**/api/canvases/**", inject_concurrent_write)
        client_node_id = add_comfy_node(conflict_page)
        conflict_page.wait_for_timeout(1800)
        server_snapshot = api("GET", f"/api/canvases/{conflict_canvas['id']}")["canvas"]
        page_snapshot = conflict_page.evaluate("({canvasId:canvas?.id, updatedAt:canvas?.updated_at, nodes:(canvas?.nodes||[]).map(n=>n.id), draft:localStorage.getItem('myridtv:canvas-draft:'+canvas?.id)})")
        server_ids = [node.get("id") for node in server_snapshot.get("nodes", [])]
        conflict_ok = 409 in conflict_statuses and 200 in conflict_statuses and client_node_id in server_ids and "e2e-concurrent-server-node" in server_ids
        diagnostics = {"statuses": conflict_statuses, "requests": conflict_requests, "network": conflict_network, "injected": injected, "initial": initial_updated_at, "page": page_snapshot, "serverIds": server_ids}
        check("409 冲突合并同时保留本地与并发节点", conflict_ok, diagnostics)
        if conflict_ok:
            conflict_page.reload(wait_until="domcontentloaded")
            conflict_page.locator(f'.image-node[data-id="{client_node_id}"]').wait_for(state="visible", timeout=15000)
            conflict_page.locator('.image-node[data-id="e2e-concurrent-server-node"]').wait_for(state="visible", timeout=15000)
            check("并发合并结果在重开后仍完整", True)

        all_errors = [error for error in errors + persistence_errors + conflict_errors if "WebSocket" not in error and "stats" not in error]
        check("保存恢复流程无页面脚本异常", not all_errors, all_errors[:3])
        browser.close()

    print(f"\nRESULT: {sum(results)}/{len(results)}")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
