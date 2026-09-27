# -*- coding: utf-8 -*-
"""Browser regression for the extracted Blender/previz composer controls."""
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
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    page.goto(BASE + "/smart-canvas.html?v=" + VERSION, wait_until="domcontentloaded")
    page.wait_for_timeout(2300)

    initial = page.evaluate("""() => {
        composer.classList.add('open');
        settings.engine = 'blender';
        renderDynamicParams();
        return {
          module: typeof CanvasPrevizControls === 'object',
          composerBlender: composer.classList.contains('blender-layout'),
          ratioOptions: document.querySelectorAll('#blenderRatioControl .blender-ratio-opt').length,
          lensOptions: document.querySelectorAll('#previzLensControl .previz-lens-opt').length,
          runLabel: document.querySelector('#runBtn span')?.textContent.trim(),
          runInHeader: !!document.querySelector('.composer-head-left #runBtn'),
          paramsEmpty: dynamicParams.childElementCount === 0
        };
    }""")
    check("切入 3D 预演后渲染独立参数视图", initial["module"] and initial["composerBlender"] and initial["ratioOptions"] == 7 and initial["lensOptions"] > 30 and initial["runLabel"] == "生成预演" and initial["runInHeader"] and initial["paramsEmpty"], initial)

    page.click("#blenderRatioPill")
    pinned = page.evaluate("document.getElementById('blenderRatioControl').classList.contains('pinned')")
    check("比例菜单正常展开", pinned)
    page.click('#blenderRatioControl [data-ratio-value="square"]')
    ratio = page.evaluate("({value:settings.ratio,label:document.querySelector('#blenderRatioPill .blender-ratio-label')?.textContent})")
    check("选择比例后更新设置与按钮摘要", ratio["value"] == "square" and "1:1" in (ratio["label"] or ""), ratio)

    page.click("#previzLensControl .previz-lens-pill")
    page.locator("#previzLensControl .previz-lens-opt").first.click()
    prompt_text = page.locator("#promptInput").inner_text()
    check("选择镜头模板后写入提示词", bool(prompt_text.strip()), prompt_text[:80])

    cleanup = page.evaluate("""() => {
        settings.engine = 'api';
        renderDynamicParams();
        return {
          blenderControls: document.querySelectorAll('.blender-ratio-item,.blender-lens-item,.previz-llm-row').length,
          runLabel: document.querySelector('#runBtn span')?.textContent.trim(),
          runInActions: !!document.querySelector('.composer-actions #runBtn'),
          composerBlender: composer.classList.contains('blender-layout')
        };
    }""")
    check("切回普通引擎后清除预演控件并恢复运行区", cleanup["blenderControls"] == 0 and cleanup["runLabel"] == "运行" and cleanup["runInActions"] and not cleanup["composerBlender"], cleanup)
    check("预演视图流程无页面脚本异常", not errors, errors[:2])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
