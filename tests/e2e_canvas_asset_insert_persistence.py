# -*- coding: utf-8 -*-
"""Exercise asset-library drag insertion through canvas save and reload."""
import base64
import json
import os
import sys
import time
import urllib.request
import uuid

from playwright.sync_api import sync_playwright


BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217").rstrip("/")
CHROME = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
VERSION = json.loads(urllib.request.urlopen(BASE + "/health", timeout=10).read())["version"]
ASSET_ID = "e2e-asset-" + uuid.uuid4().hex[:12]
ASSET_NAME = "画布素材持久化验收"
SVG = b"<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32'><rect width='32' height='32' fill='#4f46e5'/></svg>"
ASSET_URL = "data:image/svg+xml;base64," + base64.b64encode(SVG).decode("ascii")
results = []


def check(label, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + label + (" | " + str(detail)[:320] if detail else ""))


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


def create_canvas():
    return api("POST", "/api/canvases", {
        "title": "Asset insertion persistence regression",
        "nodes": [], "connections": [], "settings": {},
    })["canvas"]


def image_ref(canvas):
    for node in canvas.get("nodes", []):
        for image in node.get("images", []) if isinstance(node.get("images"), list) else []:
            if image.get("url") == ASSET_URL:
                return node, image
    return None, None


def main():
    canvas_record = create_canvas()
    library = api("GET", "/api/asset-library")["library"]
    libraries = library.get("libraries") or []
    selected_library = next(
        (item for item in libraries if item.get("id") == library.get("active_library_id")),
        libraries[0] if libraries else None,
    )
    if not selected_library:
        raise RuntimeError("isolated test instance has no asset library")
    category = next(
        (item for item in selected_library.get("categories", []) if (item.get("type") or "image") == "image"),
        None,
    )
    if not category:
        raise RuntimeError("isolated test instance has no image asset category")
    api("POST", "/api/asset-library/items", {
        "library_id": selected_library["id"],
        "category_id": category["id"],
        "id": ASSET_ID,
        "url": ASSET_URL,
        "name": ASSET_NAME,
        "kind": "image",
    })

    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route(
            "**/static/app_config.json*",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"proxy": {"base_url": BASE}}),
            ),
        )
        page.goto(f"{BASE}/smart-canvas.html?id={canvas_record['id']}", wait_until="domcontentloaded")
        page.locator("#canvasAddToggle").wait_for(state="visible", timeout=30000)
        page.wait_for_function("id => canvas?.id === id", arg=canvas_record["id"], timeout=15000)
        page.locator("#assetToggle").click()
        asset_card = page.locator(f'.asset-item[data-asset-id="{ASSET_ID}"]')
        asset_card.wait_for(state="visible", timeout=15000)
        check("画布素材库显示刚创建的隔离测试素材", asset_card.count() == 1, asset_card.get_attribute("data-name"))

        asset_card.drag_to(page.locator("#shell"), target_position={"x": 720, "y": 450}, timeout=10000)
        page.locator(".image-node").first.wait_for(state="visible", timeout=10000)
        page.wait_for_function(
            "url => (canvas?.nodes || []).some(node => (node.images || []).some(image => image.url === url))",
            arg=ASSET_URL,
            timeout=10000,
        )
        browser_state = page.evaluate(
            """url => {
              const node = (canvas?.nodes || []).find(n => (n.images || []).some(image => image.url === url));
              return {nodeId:node?.id || '', image:node?.images?.find(image => image.url === url) || null};
            }""",
            ASSET_URL,
        )
        check(
            "从素材库拖入画布后节点引用素材 ID 并跟随最新版本",
            browser_state["image"] and browser_state["image"].get("assetId") == ASSET_ID
            and browser_state["image"].get("assetVersionMode") == "latest",
            browser_state,
        )

        persisted = None
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            persisted = api("GET", f"/api/canvases/{canvas_record['id']}")["canvas"]
            node, image = image_ref(persisted)
            if image:
                break
            time.sleep(0.2)
        persisted_node, persisted_image = image_ref(persisted or {})
        check(
            "自动保存后服务端保留素材 URL 与素材 ID",
            bool(persisted_image and persisted_image.get("assetId") == ASSET_ID
                 and persisted_image.get("assetVersionMode") == "latest"),
            {"node": persisted_node, "image": persisted_image},
        )

        page.reload(wait_until="domcontentloaded")
        page.wait_for_function(
            "({id,url}) => canvas?.id === id && (canvas?.nodes || []).some(node => (node.images || []).some(image => image.url === url))",
            arg={"id": canvas_record["id"], "url": ASSET_URL},
            timeout=15000,
        )
        restored = page.evaluate(
            """url => {
              const node = (canvas?.nodes || []).find(n => (n.images || []).some(image => image.url === url));
              return {nodeId:node?.id || '', image:node?.images?.find(image => image.url === url) || null};
            }""",
            ASSET_URL,
        )
        check(
            "刷新重开后素材引用仍关联原素材及版本模式",
            restored["image"] and restored["image"].get("assetId") == ASSET_ID
            and restored["image"].get("assetVersionMode") == "latest",
            restored,
        )
        check("素材插入保存重开无页面脚本异常", not errors, errors[:3])
        screenshot_path = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
        if screenshot_path:
            page.screenshot(path=screenshot_path, full_page=True)
        browser.close()

    print(f"\nRESULT: {sum(results)}/{len(results)}")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
