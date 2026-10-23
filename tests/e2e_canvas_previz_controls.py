# -*- coding: utf-8 -*-
"""Browser regression for the Blender/previz composer host seam + 离线预演插件的运镜参数面板。

2026-10-23：预演参数区已迁到 offline-previs 插件（web/motion.js，manifest.frontend，
服务端以 /api/plugins/offline-previs/web/plugin.js 路径提供其内容）。
旧的 `#blenderRatioControl/#previzLensControl` pill+popover 结构已不存在；
本用例按新结构重写，断言以真机实测的 DOM 为准。
"""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright


BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
VERSION = json.loads(urllib.request.urlopen(BASE + "/health", timeout=10).read())["version"]
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:200] if detail else ""))


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

    setup = page.evaluate("""() => {
        canvas={connections:[],deleted:[]}; nodes=[];
        selectedId=''; selectedIds=[]; selectedImage={nodeId:'',index:-1}; render();
        const node=createLoopNode(320,260);
        window.__pvNodeId = node.id;
        composer.classList.add('open');
        window.__pvApplied=[]; window.__pvNotices=[];
        window.__pvSettings={engine:'blender', ratio:'wide'};
        CanvasPrevizControls.configure({getContext: () => ({
          settings: window.__pvSettings,
          getNode: () => ({id: window.__pvNodeId, type:'smart-image'}),
          applyOfflinePatch: patch => { window.__pvApplied.push({...patch}); Object.assign(window.__pvSettings, patch); },
          notify: message => window.__pvNotices.push(String(message)),
          layoutOffline: null,
          promptInput: document.getElementById('promptInput'),
          dynamicParams: dynamicParams,
          container: dynamicParams,
          head: document.querySelector('.composer-head-left'),
          composer
        })});
        const ok = CanvasPrevizControls.renderBlenderControls();
        const run = document.getElementById('runBtn');
        return {
          module: typeof CanvasPrevizControls === 'object', ok,
          hasUnmount: typeof (globalThis.CanvasOfflinePrevis || {}).unmount === 'function',
          runLabel: run?.querySelector('span')?.textContent.trim(),
          runParent: run?.parentElement?.className
        };
    }""")
    check("切入 3D 预演：宿主接管 composer（运行键归位到动作区并改文案为生成预演）",
          setup["module"] and setup["ok"] and setup["runLabel"] == "生成预演"
          and setup["runParent"] == "composer-actions",
          setup)
    check("插件导出 unmount（宿主切回普通引擎时依赖它清理）", setup["hasUnmount"], {"hasUnmount": setup["hasUnmount"]})

    mounted = True
    try:
        page.wait_for_selector(".pv-inline-panel", timeout=15000)
    except Exception:
        mounted = False
    panel = page.evaluate("""() => {
        const panel=document.querySelector('.pv-inline-panel');
        const n = sel => panel ? panel.querySelectorAll(sel).length : 0;
        return {
          mounted: !!panel,
          inContainer: !!(panel && dynamicParams && dynamicParams.contains(panel)),
          cls: panel ? panel.className : '',
          namedFields: n('[name]'),
          selects: n('select'),
          shootFields: n('.pv-shoot-grid [name]'),
          hasSubject: !!panel?.querySelector('input[name="subject"]'),
          hasAddAction: !!panel?.querySelector('[data-pv-add]'),
          actionRows: n('[data-pv-actions] [name]'),
          layoutButtons: n('[data-pv-layout]'),
          notices: window.__pvNotices
        };
    }""")
    check("运镜参数面板挂进参数区且控件齐备（景别/人物/机位/动作/站位）",
          mounted and panel["mounted"] and panel["inContainer"] and "pv-motion-dialog" in panel["cls"]
          and panel["namedFields"] >= 8 and panel["selects"] >= 8 and panel["shootFields"] >= 8
          and panel["hasSubject"] and panel["hasAddAction"] and panel["layoutButtons"] == 3,
          panel)

    if mounted:
        page.select_option('.pv-inline-panel select[name="framing"]', "full")
        page.wait_for_timeout(300)
        framing = page.evaluate("""() => ({
            domValue: document.querySelector('.pv-inline-panel select[name="framing"]')?.value,
            hasFull: [...document.querySelectorAll('.pv-inline-panel select[name="framing"] option')].some(o => o.value === 'full')
        })""")
        check("面板控件可交互（景别选择生效）",
              framing["domValue"] == "full" and framing["hasFull"], framing)

    cleanup = page.evaluate("""() => {
        window.__pvSettings.engine='api';
        renderDynamicParams();
        return {
          panels: document.querySelectorAll('.pv-inline-panel').length,
          runLabel: document.querySelector('#runBtn span')?.textContent.trim(),
          runInActions: !!document.querySelector('.composer-actions #runBtn'),
          notices: window.__pvNotices
        };
    }""")
    check("切回普通引擎后预演面板清掉、运行区复位",
          cleanup["panels"] == 0 and cleanup["runInActions"], cleanup)
    check("预演视图流程无页面脚本异常", not errors, errors[:2])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)