# -*- coding: utf-8 -*-
"""Regression for the isolated canvas Agent skill manager.

All skill API calls are mocked in the browser. This test never changes user skill files.
"""
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


skills = [{"name": "已有技能", "file": "existing.md", "size": 12, "updatedAt": "2026-09-25T12:00:00Z"}]
skill_contents = {"已有技能": "已有技能的正文"}
mutations = []


with sync_playwright() as pw:
    browser = pw.chromium.launch(
        executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
        headless=True,
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))

    def config_route(route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"skills": skills}))

    def skill_route(route):
        request = route.request
        if request.method == "GET":
            name = request.url.split("name=", 1)[1].split("&", 1)[0] if "name=" in request.url else ""
            from urllib.parse import unquote_plus
            name = unquote_plus(name)
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"skill": {"name": name, "content": skill_contents.get(name, "")}}))
            return
        payload = json.loads(request.post_data or "{}")
        name = str(payload.get("name") or "")
        mutations.append(payload.copy())
        if payload.get("delete"):
            skills[:] = [item for item in skills if item.get("name") != name]
            skill_contents.pop(name, None)
        else:
            skill_contents[name] = str(payload.get("content") or "")
            if not any(item.get("name") == name for item in skills):
                skills.append({"name": name, "file": name + ".md", "size": len(skill_contents[name])})
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))

    page.route("**/api/canvas-agent-config*", config_route)
    page.route("**/api/canvas-agent-skill**", skill_route)
    page.goto(BASE + "/smart-canvas.html?v=" + VERSION, wait_until="domcontentloaded")
    page.wait_for_timeout(2400)

    page.click("#canvasAgentToggle")
    page.wait_for_selector("#canvasAgentPanel.open")
    page.click("#canvasAgentSkillToggle")
    page.wait_for_selector("#canvasAgentSkillPanel.open")
    page.wait_for_selector('[data-skill-edit="已有技能"]')
    check("打开管理器并加载模拟技能列表", page.locator("#canvasAgentSkillList").inner_text().find("@已有技能") >= 0)

    page.click('[data-skill-edit="已有技能"]')
    page.wait_for_function("document.getElementById('canvasAgentSkillContent').value === '已有技能的正文'")
    check("编辑器加载现有技能正文", page.locator("#canvasAgentSkillContent").input_value() == "已有技能的正文")

    race_value = page.evaluate("""async () => {
        const realFetch = window.fetch;
        let releaseSlow;
        window.fetch = (input, init) => {
            const url = new URL(typeof input === 'string' ? input : input.url, location.href);
            const name = url.searchParams.get('name');
            const response = content => Promise.resolve(new Response(
                JSON.stringify({skill:{content}}), {status:200, headers:{'Content-Type':'application/json'}}));
            if (name === 'slow') return new Promise(resolve => { releaseSlow = () => resolve(new Response(
                JSON.stringify({skill:{content:'过期正文'}}), {status:200, headers:{'Content-Type':'application/json'}})); });
            if (name === 'fast') return response('当前正文');
            return realFetch(input, init);
        };
        CanvasAgentSkillManager.openEditor('slow');
        CanvasAgentSkillManager.openEditor('fast');
        await new Promise(resolve => setTimeout(resolve, 0));
        releaseSlow();
        await new Promise(resolve => setTimeout(resolve, 20));
        window.fetch = realFetch;
        return document.getElementById('canvasAgentSkillContent').value;
    }""")
    check("快速切换编辑项时旧请求不覆盖新正文", race_value == "当前正文", race_value)

    page.click("#canvasAgentSkillNew")
    page.fill("#canvasAgentSkillName", "回归技能")
    page.fill("#canvasAgentSkillContent", "仅存在于模拟接口的数据")
    page.click("#canvasAgentSkillSave")
    page.wait_for_selector('[data-skill-edit="回归技能"]')
    check("新建并保存后列表刷新", any(item.get("name") == "回归技能" for item in skills))

    delete_button = page.locator('[data-skill-delete="回归技能"]')
    delete_button.click()
    check("列表删除需要二次确认", page.locator('[data-skill-delete="回归技能"] span').inner_text() == "确认删除？")
    page.locator('[data-skill-delete="回归技能"]').click()
    page.wait_for_selector('[data-skill-edit="回归技能"]', state="detached")
    check("二次确认后删除并刷新列表", not any(item.get("name") == "回归技能" for item in skills))

    page.click('[data-skill-edit="已有技能"]')
    page.wait_for_function("document.getElementById('canvasAgentSkillContent').value === '已有技能的正文'")
    page.once("dialog", lambda dialog: dialog.accept())
    page.click("#canvasAgentSkillDelete")
    page.wait_for_selector('[data-skill-edit="已有技能"]', state="detached")
    check("编辑器删除二次确认后删除", not any(item.get("name") == "已有技能" for item in skills))
    check("保存与两种删除都只调用模拟接口", len(mutations) == 3, mutations)

    page.click("#canvasAgentSkillClose")
    check("关闭按钮收起管理器", "open" not in (page.get_attribute("#canvasAgentSkillPanel", "class") or ""))
    relevant_errors = [error for error in page_errors if not any(token in error for token in ("WebSocket", "stats", "favicon"))]
    check("技能管理流程无页面脚本异常", not relevant_errors, relevant_errors[:2])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
