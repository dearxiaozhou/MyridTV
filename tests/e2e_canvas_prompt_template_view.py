# -*- coding: utf-8 -*-
"""Browser regression for prompt-template view and controller modules."""
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
    page = browser.new_page(viewport={"width": 1680, "height": 980})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    page.route("**/api/prompt-libraries", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({
            "ok": True,
            "library": {"libraries": [{
                "id": "system", "name": "系统提示词库", "readonly": True,
                "items": [
                    {"id": "view-1", "name": "城市分镜", "category": "storyboard", "scene": "城市街景", "positive": "城市分镜正文一", "negative": "排除文字"},
                    {"id": "view-2", "name": "山间风景", "category": "view", "scene": "山谷晨雾", "positive": "山间风景正文二", "negative": ""},
                ]
            }]}
        })))
    page.goto(BASE + "/smart-canvas.html?v=" + VERSION, wait_until="domcontentloaded")
    page.wait_for_timeout(1800)

    setup = page.evaluate("""() => {
      const nodeId='template-view-e2e';
      if(!nodes.some(node => node.id === nodeId)) nodes.push({id:nodeId,type:'smart-image',title:'测试节点',x:420,y:300,w:320,h:220,images:[]});
      selectedId=nodeId; selectedIds=[nodeId];
      render();
      promptTemplateCategory='all'; promptTemplateSelectedId=''; promptTemplateEditing=false; promptTemplateGroupEditMode=false;
      openPromptTemplatePanel('', '', {target:'composer'});
      composer.classList.add('open');
      return {
        module: typeof CanvasPromptTemplateView === 'object' && typeof CanvasPromptTemplateView.render === 'function',
        controller: typeof CanvasPromptTemplateController === 'object' && typeof CanvasPromptTemplateController.openPanel === 'function',
        opened: promptTemplatePanel.classList.contains('open'),
        cardIds: [...promptTemplatePanel.querySelectorAll('.prompt-template-card')].map(card => card.dataset.templateId)
      };
    }""")
    check("模板视图与控制器模块加载并能打开面板", setup["module"] and setup["controller"] and setup["opened"], setup)
    check("模板视图渲染接口返回当前库条目", setup["cardIds"] == ["view-1", "view-2"], setup["cardIds"])

    page.locator('[data-template-cat="storyboard"]').click()
    categorized = page.evaluate("""() => ({
      category:promptTemplateCategory,
      ids:[...promptTemplatePanel.querySelectorAll('.prompt-template-card')].map(card=>card.dataset.templateId)
    })""")
    check("分类点击由控制器更新状态并过滤条目", categorized["category"] == "storyboard" and categorized["ids"] == ["view-1"], categorized)
    page.locator('[data-template-cat="all"]').click()

    page.locator("#promptTemplateSearch").fill("山间")
    filtered = page.evaluate("""() => ({
      ids:[...promptTemplatePanel.querySelectorAll('.prompt-template-card')].map(card=>card.dataset.templateId),
      selected:promptTemplateSelectedId,
      preview:promptTemplatePanel.querySelector('.prompt-template-preview-content')?.innerText || ''
    })""")
    check("搜索过滤模板并同步选中项与预览", filtered["ids"] == ["view-2"] and filtered["selected"] == "view-2" and "山间风景正文二" in filtered["preview"], filtered)

    page.locator('.prompt-template-card[data-template-id="view-2"]').click()
    page.locator('[data-template-apply="positive"]').click()
    applied = page.evaluate("""() => ({
      text:promptInput.textContent,
      panelOpen:promptTemplatePanel.classList.contains('open')
    })""")
    check("点击应用后正文写入输入框并关闭面板", "山间风景正文二" in applied["text"] and not applied["panelOpen"], applied)

    page.locator("#promptTemplateSearch").fill("")
    page.evaluate("openPromptTemplatePanel('template-view-e2e', 'view-1', {target:'node'})")
    node_open = page.evaluate("""() => ({
      target:promptTemplatePanel.dataset.target,
      nodeId:promptTemplatePanel.dataset.nodeId,
      selected:promptTemplateSelectedId,
      ids:[...promptTemplatePanel.querySelectorAll('.prompt-template-card')].map(card=>card.dataset.templateId)
    })""")
    check("面板可定向打开指定画布节点模板", node_open["target"] == "node" and node_open["nodeId"] == "template-view-e2e" and node_open["selected"] == "view-1" and "view-1" in node_open["ids"], node_open)
    page.locator('.prompt-template-card[data-template-id="view-1"]').click()
    page.locator('[data-template-apply="positive"]').click()
    node_applied = page.evaluate("""() => ({
      text:nodes.find(node=>node.id==='template-view-e2e')?.text||'',
      panelOpen:promptTemplatePanel.classList.contains('open')
    })""")
    check("模板正向内容应用到画布节点并关闭面板", node_applied["text"] == "城市分镜正文一" and not node_applied["panelOpen"], node_applied)
    check("模板视图交互无页面脚本异常", not errors, errors[:2])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
