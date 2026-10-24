# -*- coding: utf-8 -*-
"""Browser regression for the batch-generate node (type smart-loop) controls.

2026-10-23：原「循环节点」已并入「批量生成」节点（CanvasBatchGenerate）。
旧的 mode/count 字段与 `[data-loop-mode]/.loop-number-control` 控件已不存在，
本用例按新结构（`[data-batch-*]`）重写。
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
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:220] if detail else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch(
        executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
        headless=True,
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1680, "height": 980})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    page.evaluate("""() => {
      canvas={connections:[],deleted:[]}; nodes=[];
      selectedId=''; selectedIds=[]; selectedImage={nodeId:'',index:-1};
      // 2026-10-24：批量节点的比例/分辨率规格 pill 在工作流引擎(comfy/runninghub)下按设计不渲染，
      // 所以这里把引擎固定成非工作流引擎，避免受前序用例遗留的 settings 影响（否则用例会假红/假绿）。
      settings.engine='api';
      render();
    }""")

    created = page.evaluate("""() => {
      const node = createLoopNode(320,260);
      const card = document.querySelector('.image-node[data-id="'+node.id+'"]');
      return {
        module: typeof CanvasBatchGenerate === 'object',
        id: node.id, type: node.type, title: node.title, prompts: (node.prompts||[]).slice(),
        engine: (node.runSettings||{}).engine,
        hasCard: !!card,
        hasRun: !!card?.querySelector('[data-batch-run]'),
        hasAdd: !!card?.querySelector('[data-batch-prompt-add]'),
        promptRows: card ? card.querySelectorAll('[data-batch-prompt]').length : 0,
        hasEngine: !!card?.querySelector('[data-batch-engine-toggle]'),
        hasRatio: !!card?.querySelector('[data-batch-spec-toggle="ratio"]'),
        hasResolution: !!card?.querySelector('[data-batch-spec-toggle="resolution"]'),
        outputCount: CanvasBatchGenerate.outputCount(node)
      };
    }""")
    check("批量生成节点控件模块加载并渲染（提示词/规格/引擎/运行）",
          created["module"] and created["type"] == "smart-loop" and created["title"] == "批量生成"
          and created["engine"] == "api" and created["prompts"] == [""] and created["hasCard"]
          and created["hasRun"] and created["hasAdd"]
          and created["promptRows"] == 1 and created["hasEngine"] and created["hasRatio"]
          and created["hasResolution"] and created["outputCount"] == 0,
          created)
    card = f'.image-node[data-id="{created["id"]}"]'

    page.locator(card + " [data-batch-prompt-add]").click()
    added = page.evaluate("""id => ({
        prompts: (nodes.find(n => n.id === id)?.prompts || []).length,
        rows: document.querySelectorAll(`[data-id="${id}"] [data-batch-prompt]`).length
    })""", created["id"])
    check("可增加一段提示词", added["prompts"] == 2 and added["rows"] == 2, added)

    page.locator(card + ' [data-batch-prompt="0"]').fill("镜头一：清晨")
    page.locator(card + ' [data-batch-prompt="1"]').click()
    page.wait_for_timeout(200)
    typed = page.evaluate("""id => ((nodes.find(n => n.id === id)?.prompts) || [])[0] || ''""", created["id"])
    check("编辑提示词写回节点数据", "清晨" in (typed or ""), typed)

    page.locator(card + ' [data-batch-prompt-del="1"]').click()
    after_del = page.evaluate("""id => ({
        prompts: (nodes.find(n => n.id === id)?.prompts || []).length,
        rows: document.querySelectorAll(`[data-id="${id}"] [data-batch-prompt]`).length,
        delDisabled: !!document.querySelector(`[data-id="${id}"] [data-batch-prompt-del]`)?.disabled
    })""", created["id"])
    check("删除提示词后至少保留一段且删除键置灰",
          after_del["prompts"] == 1 and after_del["rows"] == 1 and after_del["delDisabled"], after_del)

    page.locator(card + ' [data-batch-spec-toggle="ratio"]').click()
    page.wait_for_timeout(300)
    ratio_opts = page.locator("[data-batch-spec-item]").count()
    first_val = page.locator("[data-batch-spec-item]").first.get_attribute("data-batch-spec-item") if ratio_opts else None
    if ratio_opts:
        page.locator("[data-batch-spec-item]").first.click()
        page.wait_for_timeout(300)
    ratio_after = page.evaluate("""id => ({
        ratio: (nodes.find(n => n.id === id)?.runSettings || {}).ratio,
        pickerOpen: document.querySelectorAll('.batch-engine-float.open').length
    })""", created["id"])
    check("规格弹层可展开选择并回写运行设置",
          ratio_opts > 1 and ratio_after["ratio"] == first_val and ratio_after["pickerOpen"] == 0,
          {"options": ratio_opts, "picked": first_val, **ratio_after})

    page.locator(card + " [data-batch-engine-toggle]").click()
    page.wait_for_timeout(300)
    engine_opts = page.locator("[data-batch-engine-item]").count()
    if engine_opts:
        page.locator("[data-batch-engine-item]").first.click()
        page.wait_for_timeout(300)
    engine_after = page.evaluate("""() => ({pickerOpen: document.querySelectorAll('.batch-engine-float.open').length})""")
    check("引擎弹层可展开并可选后关闭", engine_opts > 0 and engine_after["pickerOpen"] == 0,
          {"options": engine_opts, **engine_after})

    # 2026-10-24：把「工作流引擎下按设计不渲染规格 pill」这个新意图也锁进断言，
    # 免得以后有人把它当 bug 修掉，或者用例又受引擎状态影响而假红。
    workflow_engine = page.evaluate("""() => {
      settings.engine='comfy';
      const node=createLoopNode(760,260);
      const card=document.querySelector('.image-node[data-id="'+node.id+'"]');
      const out={engine:(node.runSettings||{}).engine,
        hasRatio:!!card?.querySelector('[data-batch-spec-toggle="ratio"]'),
        hasResolution:!!card?.querySelector('[data-batch-spec-toggle="resolution"]'),
        hasEnginePicker:!!card?.querySelector('[data-batch-engine-toggle]'),
        hasRun:!!card?.querySelector('[data-batch-run]')};
      settings.engine='api'; render();
      return out;
    }""")
    check("工作流引擎（comfy/runninghub）下按设计不渲染比例/分辨率规格 pill",
          "comfy" in str(workflow_engine["engine"]).lower()
          and workflow_engine["hasRatio"] is False and workflow_engine["hasResolution"] is False
          and workflow_engine["hasEnginePicker"] and workflow_engine["hasRun"],
          workflow_engine)

    check("批量生成控件交互无页面脚本异常", not errors, errors[:3])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)