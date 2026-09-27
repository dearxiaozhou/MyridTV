# -*- coding: utf-8 -*-
"""Exercise ComfyUI backend address settings through save and page reload."""
import json
import os
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright


BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217").rstrip("/")
CHROME = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
TEST_BACKEND = "comfy-persistence.e2e.invalid:8188"
results = []


def check(label, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + label + (" | " + str(detail)[:280] if detail else ""))


def get_instances():
    with urllib.request.urlopen(BASE + "/api/comfyui/instances", timeout=10) as response:
        return json.loads(response.read().decode("utf-8")).get("instances", [])


def main():
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route(
            "**/static/app_config.json*",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"proxy": {"base_url": BASE}}),
            ),
        )
        page.goto(f"{BASE}/static/comfyui-settings.html", wait_until="domcontentloaded")
        page.locator("button[onclick='addComfyInstance()']").wait_for(state="visible", timeout=15000)
        page.locator("button[onclick='addComfyInstance()']").click()
        inputs = page.locator("#comfyInstancesList .comfy-instance-input")
        inputs.last.wait_for(state="visible", timeout=5000)
        inputs.last.fill(TEST_BACKEND)
        page.locator("button[onclick='saveComfyInstances()']").click()
        page.wait_for_function(
            "() => document.getElementById('status')?.textContent.includes('已保存')",
            timeout=10000,
        )

        saved = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            saved = get_instances()
            if TEST_BACKEND in saved:
                break
            time.sleep(0.15)
        check("Comfy 设置页保存后端地址到服务端", bool(saved and TEST_BACKEND in saved), saved)

        page.reload(wait_until="domcontentloaded")
        page.locator("button[onclick='addComfyInstance()']").wait_for(state="visible", timeout=15000)
        page.wait_for_function(
            "value => [...document.querySelectorAll('#comfyInstancesList .comfy-instance-input')].some(input => input.value === value)",
            arg=TEST_BACKEND,
            timeout=10000,
        )
        restored_values = page.locator("#comfyInstancesList .comfy-instance-input").evaluate_all("els => els.map(input => input.value)")
        check("刷新设置页后 Comfy 后端地址保持一致", TEST_BACKEND in restored_values, restored_values)
        check("Comfy 设置保存重载无页面脚本异常", not errors, errors[:3])
        screenshot_path = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
        if screenshot_path:
            page.screenshot(path=screenshot_path, full_page=True)
        browser.close()

    print(f"\nRESULT: {sum(results)}/{len(results)}")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
