# -*- coding: utf-8 -*-
"""Ensure broken canvas image references show a clear, accessible status."""
import json
import os
import urllib.request

from playwright.sync_api import sync_playwright


BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217").rstrip("/")
CHROME = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
results = []


def check(label, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + label + (" | " + str(detail)[:280] if detail else ""))


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


def image_node(node_id, image_urls, x):
    return {
        "id": node_id,
        "type": "smart-image",
        "x": x,
        "y": 120,
        "w": 360,
        "h": 260,
        "images": [
            {"url": url, "name": url.rsplit("/", 1)[-1], "kind": "image"}
            for url in image_urls
        ],
    }


def main():
    canvas_record = api("POST", "/api/canvases", {
        "title": "Missing media feedback regression",
        "nodes": [
            image_node("missing-single", ["/assets/output/images/e2e-missing-single.png"], 120),
            image_node("missing-group", [
                "/assets/output/images/e2e-missing-group-a.png",
                "/assets/output/images/e2e-missing-group-b.png",
            ], 560),
        ],
        "connections": [],
        "settings": {},
    })["canvas"]
    page_errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=CHROME,
            headless=True,
            args=["--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda error: page_errors.append(str(error)))
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
        page.wait_for_function(
            "id => typeof canvas !== 'undefined' && canvas?.id === id",
            arg=canvas_record["id"],
            timeout=15000,
        )
        page.locator('.image-node[data-id="missing-single"] .media-load-error').wait_for(
            state="visible", timeout=12000
        )
        page.wait_for_function(
            "() => document.querySelectorAll('.image-node[data-id=\"missing-group\"] .media-load-error').length === 2",
            timeout=12000,
        )
        state = page.evaluate("""() => ({
            single: document.querySelector('.image-node[data-id="missing-single"] .media-load-error')?.textContent || '',
            groupErrors: [...document.querySelectorAll('.image-node[data-id="missing-group"] .media-load-error')].map(el => ({
                text: el.textContent,
                role: el.getAttribute('role'),
                label: el.getAttribute('aria-label')
            })),
            hiddenBrokenImages: [...document.querySelectorAll('.image-node img[data-canvas-image-load-failed="1"]')]
                .every(img => getComputedStyle(img).visibility === 'hidden')
        })""")
        check("单张失效图片显示明确的加载失败说明", "图片无法加载" in state["single"])
        check("多图组里的每张失效图片都有占位反馈", len(state["groupErrors"]) == 2 and all("图片无法加载" in item["text"] for item in state["groupErrors"]))
        check("失效图片状态具有可访问名称", all(item["role"] == "img" and item["label"].startswith("图片加载失败") for item in state["groupErrors"]))
        check("损坏图片本身被隐藏，避免破图标记透出", state["hiddenBrokenImages"])
        check("处理失效素材时无未捕获脚本异常", not page_errors, page_errors)
        browser.close()

    passed = sum(results)
    print(f"RESULT: {passed}/{len(results)}")
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
