# -*- coding: utf-8 -*-
"""Exercise API provider settings through the real settings page save/reload path."""
import json
import os
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright


BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217").rstrip("/")
CHROME = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
PROVIDER_NAME = "E2E 设置持久化验证"
PROVIDER_BASE_URL = "https://settings-check.example.invalid/v1"
results = []


def check(label, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + label + (" | " + str(detail)[:260] if detail else ""))


def get_providers():
    with urllib.request.urlopen(BASE + "/api/providers", timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
        return data.get("providers", [])


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
        page.goto(f"{BASE}/api-settings.html", wait_until="domcontentloaded")
        page.locator("#providerList .provider-card").first.wait_for(state="visible", timeout=15000)
        page.locator(".provider-add-inline").click()
        page.locator("#nameInput").fill(PROVIDER_NAME)
        page.locator("#baseInput").fill(PROVIDER_BASE_URL)
        page.locator(".api-page-save-btn").click()

        provider = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            provider = next((item for item in get_providers() if item.get("name") == PROVIDER_NAME), None)
            if provider and provider.get("base_url") == PROVIDER_BASE_URL:
                break
            time.sleep(0.15)
        check(
            "API 设置页保存自定义平台到后端",
            bool(provider and provider.get("base_url") == PROVIDER_BASE_URL and provider.get("protocol") == "openai"),
            provider,
        )

        page.reload(wait_until="domcontentloaded")
        page.locator(f'.provider-card[data-provider-id="{provider["id"]}"]').click()
        page.wait_for_function(
            "({name,url}) => document.getElementById('nameInput')?.value === name && document.getElementById('baseInput')?.value === url",
            arg={"name": PROVIDER_NAME, "url": PROVIDER_BASE_URL},
            timeout=10000,
        )
        restored = page.evaluate(
            """() => ({name:document.getElementById('nameInput').value,
              baseUrl:document.getElementById('baseInput').value,
              protocol:document.getElementById('protocolInput').value})"""
        )
        check(
            "重开 API 设置页后平台名称、地址和协议一致",
            restored == {"name": PROVIDER_NAME, "baseUrl": PROVIDER_BASE_URL, "protocol": "openai"},
            restored,
        )
        check("API 设置保存流程无页面脚本异常", not errors, errors[:3])
        browser.close()

    print(f"\nRESULT: {sum(results)}/{len(results)}")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
