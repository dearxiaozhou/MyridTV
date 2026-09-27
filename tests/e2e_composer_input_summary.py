# -*- coding: utf-8 -*-
"""Active composer UI contract: keep the removed input-count strip out of the canvas."""
import json
import sys
from playwright.sync_api import sync_playwright

import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
CHROME = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"

results = []
def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail)) if detail else "")

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1680, "height": 980})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    page.route("**/api/providers**", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({"providers": []})))
    page.goto(BASE + "/smart-canvas.html", wait_until="networkidle")
    page.wait_for_timeout(1200)
    page.click("#canvasAddToggle")
    page.wait_for_timeout(250)
    page.click('[data-create-type="comfy"]')
    page.wait_for_timeout(1000)

    engine = page.evaluate("() => settings.engine")
    check("Comfy 生成节点进入当前 composer", engine == "comfy", engine)
    check("统一工作流选择器可见", page.locator(".unified-picker-pill").count() == 1)
    legacy_count_rows = page.locator(".dynamic-params .cfn-inputs-row, .dynamic-params .cfn-inputs-wrap").count()
    check("旧素材数量行保持移除", legacy_count_rows == 0, legacy_count_rows)
    check("无 JavaScript 异常", not errors, errors[:2])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
