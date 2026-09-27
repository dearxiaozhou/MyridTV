# -*- coding: utf-8 -*-
"""Browser regression for the canvas header navigation module."""
import json
import sys
import urllib.request
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
VERSION = json.loads(urllib.request.urlopen(BASE + "/health", timeout=10).read())["version"]
results = []
requests = []
canvases = {
    "canvas-current": {"id": "canvas-current", "title": "当前画布", "nodes": [], "connections": [], "logs": [], "viewport": {"x": 0, "y": 0, "scale": 1}, "settings": {}, "deleted": [], "artifacts": [], "inputMode": "connections", "formatVersion": 1, "updated_at": 1000},
    "canvas-other": {"id": "canvas-other", "title": "目标画布", "nodes": [], "connections": [], "logs": [], "viewport": {"x": 0, "y": 0, "scale": 1}, "settings": {}, "deleted": [], "artifacts": [], "inputMode": "connections", "formatVersion": 1, "updated_at": 2000},
}


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:220] if detail else ""))


def json_response(route, payload, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(payload, ensure_ascii=False))


def canvas_api(route):
    request = route.request
    method = request.method
    path = urlparse(request.url).path
    requests.append({"method": method, "path": path, "body": request.post_data_json if request.post_data else None})
    if path == "/api/canvases":
        if method == "GET":
            json_response(route, {"canvases": [canvases["canvas-current"], canvases["canvas-other"]]})
            return
        if method == "POST":
            canvases["canvas-new"] = {"id": "canvas-new", "title": "未命名画布", "nodes": [], "connections": [], "logs": [], "viewport": {"x": 0, "y": 0, "scale": 1}, "settings": {}, "deleted": [], "artifacts": [], "inputMode": "connections", "formatVersion": 1, "updated_at": 3000}
            json_response(route, {"canvas": canvases["canvas-new"]}, 201)
            return
    canvas_id = path.rsplit("/", 1)[-1]
    if canvas_id in canvases and method == "GET":
        json_response(route, {"canvas": canvases[canvas_id]})
        return
    if canvas_id in canvases and method == "PUT":
        payload = request.post_data_json or {}
        canvases[canvas_id].update(payload)
        json_response(route, {"ok": True})
        return
    route.continue_()


with sync_playwright() as pw:
    browser = pw.chromium.launch(
        executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
        headless=True,
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1680, "height": 980})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/static/app_config.json*", lambda route: json_response(route, {"proxy": {"base_url": BASE}}))
    page.route("**/api/canvases**", canvas_api)
    page.goto(f"{BASE}/smart-canvas.html?id=canvas-current&v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(1300)

    loaded = page.evaluate("""() => ({
      module:typeof CanvasHeaderNavigation==='object' && typeof CanvasHeaderNavigation.openDropdown==='function',
      title:document.querySelector('#canvasTitleText')?.textContent,
      dropdown:!!document.querySelector('#canvasListDropdown')
    })""")
    check("顶部导航模块加载并显示当前画布", loaded["module"] and loaded["title"] == "当前画布" and loaded["dropdown"], loaded)

    page.locator(".canvas-title-caret").click()
    page.locator(".canvas-dropdown-item").first.wait_for()
    opened = page.evaluate("""() => ({
      open:document.querySelector('#canvasListDropdown')?.style.display==='flex',
      ids:[...document.querySelectorAll('.canvas-dropdown-item')].map(item=>item.dataset.canvasId)
    })""")
    check("下拉菜单加载画布列表", opened["open"] and set(opened["ids"]) == {"canvas-current", "canvas-other"}, opened)

    page.locator("#canvasDropdownSearch").fill("目标")
    filtered = page.locator(".canvas-dropdown-item").evaluate_all("items => items.map(item=>item.dataset.canvasId)")
    page.locator("#canvasDropdownSearch").fill("")
    restored = page.locator(".canvas-dropdown-item").count()
    check("列表搜索过滤并可恢复全部画布", filtered == ["canvas-other"] and restored == 2, {"filtered": filtered, "restored": restored})

    page.locator('.canvas-dropdown-item[data-canvas-id="canvas-other"]').click()
    page.wait_for_url("**/smart-canvas.html?id=canvas-other")
    page.wait_for_function("document.querySelector('#canvasTitleText')?.textContent==='目标画布'")
    check("选择列表项切换到对应画布", "id=canvas-other" in page.url and page.locator("#canvasTitleText").inner_text() == "目标画布", page.url)

    page.locator(".canvas-title-text").click()
    page.locator("#canvasTitleInput").fill("重命名画布")
    page.locator("#canvasTitleInput").press("Enter")
    page.wait_for_function("document.querySelector('#canvasTitleText')?.textContent==='重命名画布'")
    renamed = [item for item in requests if item["method"] == "PUT" and item["path"] == "/api/canvases/canvas-other"]
    check("标题重命名写回当前画布并更新界面", bool(renamed) and renamed[-1]["body"].get("title") == "重命名画布" and page.title() == "重命名画布", renamed[-1] if renamed else requests[-4:])

    page.locator(".canvas-title-caret").click()
    page.locator(".canvas-dropdown-new-btn").click()
    page.wait_for_url("**/smart-canvas.html?id=canvas-new")
    created = [item for item in requests if item["method"] == "POST" and item["path"] == "/api/canvases"]
    check("下拉菜单新建画布后切换到新画布", bool(created) and "id=canvas-new" in page.url, {"url": page.url, "post": created[-1] if created else None})
    check("顶部导航操作无页面脚本异常", not errors, errors[:3])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
