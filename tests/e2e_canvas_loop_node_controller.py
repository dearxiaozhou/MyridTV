# -*- coding: utf-8 -*-
"""Browser regression for loop-node controls and prompt editing."""
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
      const node=createLoopNode(320,260);
      return {module:typeof CanvasLoopNodeController==='object',id:node.id,mode:node.mode,count:node.count};
    }""")
    check("循环节点控件模块加载并渲染新节点", created["module"] and created["id"] and created["count"] == 1, created)
    card = f'.image-node[data-id="{created["id"]}"]'

    page.locator(card + ' [data-loop-mode="parallel"]').click()
    mode = page.evaluate("""id => nodes.find(node=>node.id===id)?.mode""", created["id"])
    check("运行模式选择写回并重新渲染", mode == "parallel", mode)

    page.locator(card + ' [data-loop-toggle="prompt"]').click()
    first_prompt = page.evaluate("""id => {
      const node=nodes.find(item=>item.id===id);
      return {shown:node.showPrompt,values:node.variablePrompts};
    }""", created["id"])
    check("开启提示词时生成默认提示词字段", first_prompt["shown"] and len(first_prompt["values"]) == 1 and "《计数》" in first_prompt["values"][0], first_prompt)

    page.locator(card + " [data-loop-prompt-add]").click()
    prompt_count = page.locator(card + " [data-loop-prompt-index]").count()
    check("提示词字段可新增", prompt_count == 2, prompt_count)

    page.locator(card + " [data-loop-prompt-index='0']").fill("镜头")
    page.locator(card + " [data-loop-token='《计数》']").click()
    token_value = page.evaluate("""id => nodes.find(item=>item.id===id)?.variablePrompts?.[0]||''""", created["id"])
    check("计数占位符按钮插入内容并同步节点数据", "镜头" in token_value and "《计数》" in token_value, token_value)

    page.locator(card + " [data-loop-prompt-delete='1']").click()
    prompt_count = page.locator(card + " [data-loop-prompt-index]").count()
    check("提示词字段可删除且至少保留一项", prompt_count == 1, prompt_count)

    page.locator(card + " .loop-smart-footer .loop-number-control").nth(1).locator(".loop-number-trigger").click()
    page.locator(card + ' [data-loop-number="count"][data-loop-value="3"]').click()
    count_value = page.evaluate("""id => nodes.find(item=>item.id===id)?.count""", created["id"])
    check("快捷数量选择更新循环次数", count_value == 3, count_value)

    page.locator(card + " .loop-smart-footer .loop-number-control").nth(1).locator(".loop-number-trigger").click()
    custom_count = page.locator(card + ' input[data-loop-number-input="count"]')
    custom_count.fill("999")
    custom_count.press("Tab")
    clamped = page.evaluate("""id => ({count:nodes.find(item=>item.id===id)?.count,input:document.querySelector(`[data-id="${id}"] input[data-loop-number-input="count"]`)?.value})""", created["id"])
    check("自定义循环次数遵守上限", clamped["count"] == 100 and clamped["input"] == "100", clamped)

    page.locator(card + ' [data-loop-toggle="image"]').click()
    image_enabled = page.evaluate("""id => nodes.find(item=>item.id===id)?.imageInput""", created["id"])
    check("图片输入开关同步循环节点状态", image_enabled is True, image_enabled)
    check("循环控件交互无页面脚本异常", not errors, errors[:3])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
