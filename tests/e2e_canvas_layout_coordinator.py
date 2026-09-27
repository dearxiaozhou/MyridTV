# -*- coding: utf-8 -*-
"""Verify the smart-canvas layout coordinator against the isolated app runtime."""
import json
import os
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("MYRIDTV_TEST_BASE") or os.environ.get("MYRIDTV_LAYOUT_BASE_URL", "http://127.0.0.1:3217")
CHROME = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"


def create_empty_canvas():
    if BASE != "http://127.0.0.1:3217":
        return "layout-coordinator-check"
    request = urllib.request.Request(
        f"{BASE}/api/canvases",
        data=json.dumps({"name": "layout-coordinator-check", "nodes": [], "connections": []}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())["canvas"]["id"]


def main():
    canvas_id = create_empty_canvas()
    failures = []
    harness = f"""<!doctype html><html><head><meta charset="utf-8"><style>
      * {{ box-sizing: border-box; }} html,body {{ margin:0; width:100%; height:100%; overflow:hidden; }}
      #frame-smart-canvas {{ position:absolute; inset:0; width:100%; height:100%; border:0; display:block; }}
      .bottom-dock-shell {{ position:absolute; left:50%; bottom:5px; z-index:30; width:470px; height:44px;
        display:flex; align-items:flex-end; gap:6px; transform:translateX(-50%); transition:left .22s ease; }}
      body.smart-agent-open .bottom-dock-shell {{ left:var(--smart-agent-dock-center,50%); }}
      .dock-toggle {{ flex:0 0 32px; height:32px; }} .bottom-dock {{ width:394px; height:44px; }}
    </style></head><body><iframe id="frame-smart-canvas" src="{BASE}/smart-canvas.html?id={canvas_id}"></iframe>
    <div class="bottom-dock-shell"><button class="dock-toggle"></button><nav class="bottom-dock"></nav><button class="dock-toggle"></button></div>
    </body></html>"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=CHROME,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1100, "height": 900})
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.route(f"{BASE}/api/canvases/{canvas_id}*", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"canvas":{"id":canvas_id,"title":"Layout coordinator check","nodes":[],"connections":[],"logs":[],"viewport":{"x":0,"y":0,"scale":1},"settings":{},"deleted":[],"artifacts":[],"inputMode":"connections","formatVersion":1,"updated_at":1}})))
        page.route("**/static/app_config.json*", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"proxy":{"base_url":BASE}})))
        page.add_style_tag(content="*,*::before,*::after{animation:none!important;transition:none!important}")
        page.route(
            f"{BASE}/_layout_harness",
            lambda route: route.fulfill(status=200, content_type="text/html", body=harness),
        )
        page.goto(f"{BASE}/_layout_harness", wait_until="domcontentloaded", timeout=15000)
        frame_locator = page.frame_locator("#frame-smart-canvas")
        frame_locator.locator("#canvasAgentToggle").wait_for(timeout=30000)
        frame = next((item for item in page.frames if "smart-canvas.html" in item.url), None)
        assert frame is not None, "smart canvas frame did not load"
        if not frame.locator("#canvasAgentPanel").evaluate("el => el.classList.contains('open')"):
            frame.locator("#canvasAgentToggle").click(timeout=5000, force=True)
        page.wait_for_timeout(350)

        measured = frame.locator("body").evaluate(
            """body => {
              const panel = body.ownerDocument.querySelector('#canvasAgentPanel');
              const panelRect = panel.getBoundingClientRect();
              const frameRect = body.ownerDocument.defaultView.frameElement.getBoundingClientRect();
              const toolsRect = body.ownerDocument.querySelector('.canvas-bottom-cluster').getBoundingClientRect();
              return {
                coordinator: typeof body.ownerDocument.defaultView.CanvasLayoutCoordinator,
                agentOpen: panel.classList.contains('open'),
                shifted: body.ownerDocument.defaultView.parent.document.body.classList.contains('smart-agent-open'),
                panelLeft: panelRect.left + frameRect.left,
                leftToolsRight: toolsRect.right + frameRect.left,
                clearance: panel.style.getPropertyValue('--agent-dock-clearance'),
              };
            }"""
        )
        shell = page.locator(".bottom-dock-shell").bounding_box()
        shell_left = shell["x"]
        shell_right = shell["x"] + shell["width"]
        measured["shellLeft"] = shell_left
        measured["shellRight"] = shell_right
        measured["panelGap"] = measured["panelLeft"] - shell_right
        measured["leftToolGap"] = shell_left - measured["leftToolsRight"]

        if measured["coordinator"] != "object":
            failures.append("layout coordinator did not load")
        if not measured["agentOpen"] or not measured["shifted"]:
            failures.append("opening Agent did not activate dock coordination")
        if measured["panelGap"] < -1:
            failures.append(f"dock overlaps Agent panel by {-measured['panelGap']:.1f}px")
        if measured["leftToolGap"] < -1:
            failures.append(f"dock overlaps left tools by {-measured['leftToolGap']:.1f}px")
        if page_errors:
            failures.append(f"browser page errors: {page_errors}")

        screenshot = os.path.join(os.environ.get("TEMP", "."), "myrid-layout-coordinator-e2e.png")
        page.screenshot(path=screenshot)
        browser.close()

    print(json.dumps({"canvasId": canvas_id, "layout": measured, "screenshot": screenshot, "failures": failures}, ensure_ascii=False))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()







