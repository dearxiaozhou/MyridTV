# -*- coding: utf-8 -*-
"""Browser regression for the canvas free-crop interaction."""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright


import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
VERSION = json.loads(urllib.request.urlopen(BASE + "/health", timeout=10).read())["version"]
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:160] if detail else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch(
        executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
        headless=True,
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page_errors = []
    uploads = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))

    def upload_route(route):
        uploads.append(route.request.method)
        route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "files": [{"url": "/static/images/myrid-icon-24.png", "name": "crop-result.png", "kind": "image"}]
        }))

    page.route("**/api/ai/upload", upload_route)
    page.goto(BASE + "/smart-canvas.html?v=" + VERSION, wait_until="domcontentloaded")
    page.wait_for_timeout(2300)
    setup = page.evaluate("""() => {
        const p = CanvasViewport.viewportCenter();
        const node = createNode(p.x - 150, p.y - 90, [{
            url: '/static/images/myrid-icon-128.png', name: 'crop-source.png', kind: 'image', natural_w: 128, natural_h: 128
        }]);
        return {id: node.id, module: typeof CanvasImageCrop === 'object'};
    }""")
    node_id = setup["id"]
    image = page.locator(f'.image-node[data-id="{node_id}"] .image-wrap img')
    image.wait_for(state="visible")
    image.evaluate("img => img.decode()")
    check("自由裁剪模块加载且图片节点可用", setup["module"] and image.count() == 1)

    image.dblclick()
    preview_opened = page.evaluate("imageEditModal.classList.contains('open') && imageEditMode==='preview'")
    check("双击图片缩略图打开预览", preview_opened)
    page.keyboard.press("Escape")
    page.wait_for_function("!imageEditModal.classList.contains('open')")

    page.locator(f'.image-node[data-id="{node_id}"] .smart-crop-action[data-tool-mode="crop"]').click()
    toolbar_opened_editor = page.evaluate("imageEditModal.classList.contains('open') && imageEditMode==='crop'")
    check("点击节点裁剪工具打开图像编辑器", toolbar_opened_editor)
    page.keyboard.press("Escape")
    page.wait_for_function("!imageEditModal.classList.contains('open')")

    diagnostics = page.evaluate("""id => {
        const node = nodes.find(item => item.id === id);
        const nodeEl = world.querySelector('.image-node[data-id="' + CSS.escape(id) + '"]');
        const item = nodeEl?.querySelector('[data-image-index="0"]');
        return {node:!!node, imageUrl:node?.images?.[0]?.url, kind:node?.images?.[0] ? mediaKindForItem(node.images[0]) : '', nodeEl:!!nodeEl, item:!!item, img:!!item?.querySelector('img'), world:!!world};
    }""", node_id)
    page.evaluate("id => openSmartImageTool(id, 0, 'free-crop')", node_id)
    active = page.evaluate("CanvasImageCrop.isActive() && document.body.classList.contains('smart-free-cropping')")
    check("进入自由裁剪状态", active, diagnostics)
    if active:
        page.keyboard.press("Escape")
        cancelled = page.evaluate("!CanvasImageCrop.isActive() && !document.body.classList.contains('smart-free-cropping')")
        check("Esc 取消裁剪并清理状态", cancelled)

        page.evaluate("id => openSmartImageTool(id, 0, 'free-crop')", node_id)
        rect = image.bounding_box()
        if not rect:
            check("图片框选区域存在", False, "no bounding box")
        else:
            x1, y1 = rect["x"] + rect["width"] * 0.2, rect["y"] + rect["height"] * 0.2
            x2, y2 = rect["x"] + rect["width"] * 0.75, rect["y"] + rect["height"] * 0.75
            page.mouse.move(x1, y1)
            page.mouse.down()
            page.mouse.move(x2, y2, steps=4)
            page.mouse.up()
            page.wait_for_function("""() => {
                const box = document.querySelector('.smart-free-crop-box');
                return box && parseFloat(box.style.width) > 3 && parseFloat(box.style.height) > 3;
            }""")
            before = page.locator(".image-node").count()
            page.keyboard.press("Enter")
            page.wait_for_function("""({before}) => document.querySelectorAll('.image-node').length === before + 1""", arg={"before": before})
            check("拖拽框选并按 Enter 上传裁剪结果", len(uploads) == 1 and page.locator(".image-node").count() == before + 1, uploads)
            check("完成后退出裁剪状态", not page.evaluate("CanvasImageCrop.isActive()"))

    relevant_errors = [error for error in page_errors if not any(token in error for token in ("WebSocket", "stats", "favicon"))]
    check("自由裁剪流程无页面脚本异常", not relevant_errors, relevant_errors[:2])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
