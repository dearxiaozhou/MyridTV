# -*- coding: utf-8 -*-
"""Browser regression for the prompt-template HTTP repository boundary."""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright


import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
VERSION = json.loads(urllib.request.urlopen(BASE + "/health", timeout=10).read())["version"]
calls = []
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:200] if detail else ""))


def item_api(route):
    request = route.request
    body = json.loads(request.post_data or "{}")
    calls.append({"method": request.method, "url": request.url, "body": body})
    if body.get("name") == "fail":
        route.fulfill(status=409, content_type="application/json", body=json.dumps({"detail": "模板名冲突"}))
    elif request.method == "DELETE":
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))
    else:
        route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "ok": True, "item": {"id": "tpl-new"}, "library": {"libraries": []}
        }))


def category_api(route):
    request = route.request
    body = json.loads(request.post_data or "{}")
    calls.append({"method": request.method, "url": request.url, "body": body})
    if request.method == "DELETE":
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))
    else:
        route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "ok": True, "category": {"id": "cat-new"}, "library": {"libraries": []}
        }))


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
    page.route("**/api/prompt-libraries/items**", item_api)
    page.route("**/api/prompt-libraries/categories**", category_api)
    page.route("**/api/prompt-libraries", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({
            "ok": True,
            "library": {"libraries": [{"id": "personal", "name": "我的库", "readonly": False, "items": []}]}
        })))
    page.goto(BASE + "/smart-canvas.html?v=" + VERSION, wait_until="domcontentloaded")
    page.wait_for_timeout(1600)

    result = page.evaluate("""async () => {
      if(typeof CanvasPromptTemplateRepository !== 'object') return {loaded:false};
      const created=await CanvasPromptTemplateRepository.createItem({library_id:'personal',name:'新模板',category:'mine',positive:'正文'});
      const updated=await CanvasPromptTemplateRepository.updateItem('tpl / unsafe',{library_id:'personal',name:'已改名'});
      const deleted=await CanvasPromptTemplateRepository.deleteItem('tpl / unsafe');
      const createdCategory=await CanvasPromptTemplateRepository.createCategory({library_id:'personal',name:'新分组'});
      const updatedCategory=await CanvasPromptTemplateRepository.updateCategory('cat / unsafe',{library_id:'personal',name:'已改名'});
      const deletedCategory=await CanvasPromptTemplateRepository.deleteCategory('cat / unsafe');
      let failure='';
      try { await CanvasPromptTemplateRepository.createItem({library_id:'personal',name:'fail'}); }
      catch(error) { failure=error.message; }
      return {loaded:true,created:created.item?.id,updated:updated.item?.id,deleted:deleted.ok,
        createdCategory:createdCategory.category?.id,updatedCategory:updatedCategory.category?.id,
        deletedCategory:deletedCategory.ok,failure};
    }""")
    check("模板 API 仓储模块加载且串接成功响应", result.get("loaded") and result.get("created") == "tpl-new" and result.get("updated") == "tpl-new" and result.get("deleted"), result)
    check("分类新增/修改/删除通过独立仓储调用", result.get("createdCategory") == "cat-new" and result.get("updatedCategory") == "cat-new" and result.get("deletedCategory"), result)
    check("仓储保留服务端错误详情", result.get("failure") == "模板名冲突", result.get("failure"))
    encoded = [call["url"] for call in calls if "unsafe" in call["url"]]
    check("资源 ID 按 URL 规则编码", len(encoded) == 4 and all("%2F" in url and "%20" in url for url in encoded), encoded)
    check("请求方法和 JSON 载荷符合资源类型", [call["method"] for call in calls] == ["POST", "PATCH", "DELETE", "POST", "PATCH", "DELETE", "POST"] and calls[0]["body"].get("library_id") == "personal", [call["method"] for call in calls])
    check("仓储交互无页面脚本异常", not errors, errors[:2])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
