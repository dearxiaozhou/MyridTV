# -*- coding: utf-8 -*-
"""Browser regression for RunningHub workflow graph and image-slot discovery."""
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
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:180] if detail else ""))


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
    page.wait_for_timeout(1800)

    result = page.evaluate("""() => {
      const cache = runningHubWorkflowCache;
      const oldOrdered = cache.__e2e_rh_ordered;
      const oldFallback = cache.__e2e_rh_fallback;
      cache.__e2e_rh_ordered = {workflowJson: {
        '10': {class_type:'LoadImage', _meta:{title:'输入图'}, inputs:{image:'ten.png'}},
        '2': {class_type:'LoadImage', _meta:{title:'输入图'}, inputs:{image:'two.png'}},
        '100': {class_type:'KSampler', inputs:{ref_image_1:['10',0], ref_image_0:['2',0]}}
      }, fields:[
        {nodeId:'10', enabled:true}, {nodeId:'2', enabled:true}, {nodeId:'100', enabled:true}
      ]};
      cache.__e2e_rh_fallback = {workflowJson: {
        '23': {class_type:'LoadImage', inputs:{image:'twenty-three.png'}},
        '7': {class_type:'LoadImage', inputs:{image:'seven.png'}},
        '100': {class_type:'KSampler', inputs:{image:['23',0]}}
      }};
      const orderedRef = {kind:'workflow', id:'__e2e_rh_ordered'};
      const fallbackRef = {kind:'workflow', id:'__e2e_rh_fallback'};
      const nodes = CanvasRhControls.rhWorkflowNodeList(orderedRef);
      const semanticSlots = CanvasRhControls.rhWorkflowImageSlots(orderedRef);
      const fallbackSlots = CanvasRhControls.rhWorkflowImageSlots(fallbackRef);
      const api = {
        exported: typeof CanvasRhControls.rhWorkflowImageSlots === 'function' && typeof CanvasRhControls.rhWorkflowNodeList === 'function',
        nodeIds: nodes.map(node => node.id),
        labels: nodes.slice(0,2).map(node => node.label),
        semanticOrder: semanticSlots.map(slot => slot.nodeId),
        fields: semanticSlots.map(slot => slot.fieldName),
        fallbackOrder: fallbackSlots.map(slot => slot.nodeId)
      };
      if(oldOrdered === undefined) delete cache.__e2e_rh_ordered; else cache.__e2e_rh_ordered = oldOrdered;
      if(oldFallback === undefined) delete cache.__e2e_rh_fallback; else cache.__e2e_rh_fallback = oldFallback;
      return api;
    }""")
    check("RH 工作流模型方法由模块导出", result["exported"])
    check("节点按数字 ID 排序并区分重名", result["nodeIds"] == ["2", "10", "100"] and result["labels"] == ["输入图 #1", "输入图 #2"], result)
    check("图片槽位按工作流语义编号排序", result["semanticOrder"] == ["2", "10"] and result["fields"] == ["image", "image"], result)
    check("缺少编号连线时按节点数字 ID 排序", result["fallbackOrder"] == ["7", "23"], result)
    check("工作流模型流程无页面脚本异常", not errors, errors[:2])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
