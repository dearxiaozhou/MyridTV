# -*- coding: utf-8 -*-
"""Regression for extracted canvas parameter event binding."""
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
    page.wait_for_timeout(2400)

    setup = page.evaluate("""() => {
        settings.engine = 'api';
        settings.apiKind = 'video';
        settings.videoDuration = 5;
        renderDynamicParams();
        const container = document.getElementById('dynamicParams');
        container.insertAdjacentHTML('beforeend', `
          <div id="paramEventProbeControl" class="smart-control">
            <button id="paramEventProbePill" class="smart-pill" type="button">测试参数菜单</button>
          </div>
          <button id="paramEventProbeParam" type="button" data-smart-param="videoDuration" data-smart-value="10">10秒</button>
        `);
        CanvasParamEvents.bindDynamicParams();
        return {module: typeof CanvasParamEvents === 'object', pill: !!document.getElementById('paramEventProbePill'), param: !!document.getElementById('paramEventProbeParam')};
    }""")
    check("参数事件模块加载并绑定到参数容器", setup["module"] and setup["pill"] and setup["param"], setup)

    page.evaluate("document.getElementById('paramEventProbePill').click()")
    pill_state = page.evaluate("document.getElementById('paramEventProbeControl').classList.contains('pinned')")
    check("参数 pill 点击后展开", pill_state)

    page.evaluate("document.getElementById('paramEventProbeParam').click()")
    duration = page.evaluate("settings.videoDuration")
    check("参数事件更新视频时长并触发面板重绘", duration == 10, duration)

    mode_results = page.evaluate("""() => {
        const noop = () => {};
        CanvasParamEvents.configure({
          getContainer: () => null,
          resolveComfyWorkflowName: () => 'event-probe-workflow',
          getComfyWorkflowCache: () => ({}),
          syncComfyModesChrome: noop,
          syncComfyDetailsAndParams: noop,
          persistActiveSmartSettings: noop,
          scheduleSave: noop,
          selectedRunningHubRef: () => ({kind:'workflow', id:'event-probe-rh'}),
          runningHubEntryKey: () => 'workflow:event-probe-rh',
          syncRhNodesChrome: noop,
          syncRhDetailsAndParams: noop,
          refreshIcons: noop
        });
        const evt = {preventDefault:noop, stopPropagation:noop};
        const comfyButton = document.createElement('button');
        comfyButton.dataset.comfyNodeMode = 'node-1';
        settings.comfyWorkflow = 'event-probe-workflow';
        settings.comfyModes = {};
        handleComfyNodeModeToggle(comfyButton, evt);
        const comfyDisabled = settings.comfyModes['event-probe-workflow']?.['node-1'] === 'bypass';
        handleComfyNodeModeToggle(comfyButton, evt);
        const comfyEnabled = !settings.comfyModes['event-probe-workflow'];

        const rhButton = document.createElement('button');
        rhButton.dataset.rhNodeMode = 'node-2';
        settings.rhNodeOff = {};
        handleRhNodeModeToggle(rhButton, evt);
        const rhDisabled = settings.rhNodeOff['workflow:event-probe-rh']?.['node-2'] === true;
        handleRhNodeModeToggle(rhButton, evt);
        const rhEnabled = !settings.rhNodeOff['workflow:event-probe-rh'];
        return {comfyDisabled, comfyEnabled, rhDisabled, rhEnabled};
    }""")
    check("Comfy 与 RunningHub 节点开关可切换并还原", all(mode_results.values()), mode_results)
    check("参数事件交互无页面脚本异常", not errors, errors[:2])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
