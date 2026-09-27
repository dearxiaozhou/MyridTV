# -*- coding: utf-8 -*-
"""Browser regression for prompt-node editing and LLM controls."""
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
      selectedId=''; selectedIds=[]; selectedImage={nodeId:'',index:-1}; render();
    }""")

    created = page.evaluate("""() => {
      const node=createPromptNode(320,240,{text:'初始提示词'});
      return {module:typeof CanvasPromptNodeController==='object',id:node.id,llmEnabled:node.llmEnabled};
    }""")
    check("提示词节点控件模块加载", created["module"] and created["id"] and not created["llmEnabled"], created)
    card = f'.image-node[data-id="{created["id"]}"]'

    page.locator(card + " .prompt-node-text").fill("修改后的提示词")
    prompt_text = page.evaluate("""id => nodes.find(node=>node.id===id)?.text""", created["id"])
    check("提示词文本编辑实时写回节点", prompt_text == "修改后的提示词", prompt_text)

    page.locator(card + " .prompt-llm-toggle").click()
    llm_state = page.evaluate("""id => {
      const node=nodes.find(item=>item.id===id);
      return {enabled:node.llmEnabled,provider:node.llmProvider,model:node.llmModel,hasSystemToggle:!!document.querySelector(`[data-id="${id}"] .prompt-system-toggle`)};
    }""", created["id"])
    check("开启 LLM 时补齐模型并显示系统提示设置", llm_state["enabled"] and llm_state["hasSystemToggle"], llm_state)

    page.locator(card + " .prompt-system-toggle").click()
    page.locator(card + " .prompt-llm-system").fill("请保持镜头连续")
    page.locator(card + " .prompt-llm-instruction").fill("只优化构图")
    system_values = page.evaluate("""id => {
      const node=nodes.find(item=>item.id===id);
      return {enabled:node.llmSystemEnabled,system:node.llmSystemPrompt,instruction:node.llmInstruction};
    }""", created["id"])
    check("系统提示词与额外指令分别保存", system_values["enabled"] and system_values["system"] == "请保持镜头连续" and system_values["instruction"] == "只优化构图", system_values)

    page.locator(card + " .prompt-system-toggle").click()
    system_disabled = page.evaluate("""id => nodes.find(item=>item.id===id)?.llmSystemEnabled""", created["id"])
    check("系统提示设置可关闭", system_disabled is False, system_disabled)

    page.locator(card + " .prompt-llm-toggle").click()
    llm_disabled = page.evaluate("""id => ({enabled:nodes.find(item=>item.id===id)?.llmEnabled,systemField:!!document.querySelector(`[data-id="${id}"] .prompt-llm-system`)})""", created["id"])
    check("LLM 控件关闭后收起模型参数", llm_disabled["enabled"] is False and not llm_disabled["systemField"], llm_disabled)
    check("提示词节点交互无页面脚本异常", not errors, errors[:3])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
