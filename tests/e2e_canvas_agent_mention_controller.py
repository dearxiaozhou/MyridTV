# -*- coding: utf-8 -*-
"""Browser regression for Agent @reference search and keyboard selection."""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright


import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
CHROMIUM = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
VERSION = json.loads(urllib.request.urlopen(BASE + "/health", timeout=10).read())["version"]
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:280] if detail else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1680, "height": 980})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(1200)

    setup = page.evaluate("""() => {
      const image={url:'http://127.0.0.1:3217/assets/ref-image.png',name:'林间小屋',kind:'image'};
      const video={url:'http://127.0.0.1:3217/assets/ref-video.mp4',name:'雨夜片段',kind:'video'};
      canvasAgentRefsState=[image,video];
      canvasAgentMentionPoolSnapshot=[];
      canvasAgentMentionIndex=-1;
      setCanvasAgentOpen(true);
      return {module:typeof CanvasAgentMentionController==='object',panelOpen:canvasAgentPanel.classList.contains('open')};
    }""")
    check("Agent @引用控制器加载且面板打开", setup["module"] and setup["panelOpen"], setup)
    page.wait_for_timeout(280)
    page.locator("#canvasAgentInput").fill("@")
    opened = page.evaluate("""() => {
      const picker=canvasAgentPanel.querySelector('.canvas-agent-mention');
      return {open:picker?.classList.contains('open'),items:picker?._items?.length||0,index:canvasAgentMentionIndex};
    }""")
    check("输入 @ 后显示候选并聚焦首项", opened["open"] and opened["items"] == 2 and opened["index"] == 0, opened)

    page.keyboard.press("ArrowDown")
    moved = page.evaluate("""() => ({
      index:canvasAgentMentionIndex,
      active:canvasAgentPanel.querySelector('.canvas-agent-mention [data-agent-mention-index].active')?.dataset.agentMentionIndex,
      focused:document.activeElement===canvasAgentInput,activeId:document.activeElement?.id
    })""")
    check("向下键移动候选焦点", moved["index"] == 1 and moved["active"] == "1", moved)

    page.keyboard.press("Enter")
    inserted = page.evaluate("""() => ({
      value:canvasAgentInput.value,
      selectedVideo:canvasAgentRefsState.some(ref=>ref.url.endsWith('ref-video.mp4')),
      pickerOpen:canvasAgentPanel.querySelector('.canvas-agent-mention')?.classList.contains('open')||false,
      pool:canvasAgentMentionPoolSnapshot.map(ref=>ref.name)
    })""")
    check("Enter 插入选中视频引用并保留稳定编号", "@视频1 " in inserted["value"] and inserted["selectedVideo"]
          and inserted["pool"] == ["林间小屋", "雨夜片段"], inserted)
    check("插入引用后候选面板收起", not inserted["pickerOpen"], inserted)

    page.locator("#canvasAgentInput").fill("@")
    page.keyboard.press("Escape")
    escaped = page.evaluate("canvasAgentPanel.querySelector('.canvas-agent-mention')?.classList.contains('open')||false")
    check("Escape 关闭 Agent @候选", not escaped, escaped)

    page.locator("#canvasAgentInput").fill("@不存在")
    empty = page.evaluate("""() => {
      canvasAgentRefsState=[];
      canvasAgentMentionPoolSnapshot=[];
      renderCanvasAgentMention();
      const picker=canvasAgentPanel.querySelector('.canvas-agent-mention');
      return {open:picker?.classList.contains('open'),count:picker?.querySelectorAll('[data-agent-mention-index]').length||0,
        hint:picker?.textContent||'',index:canvasAgentMentionIndex};
    }""")
    check("无匹配资源时显示空状态并清除焦点索引", empty["open"] and empty["count"] == 0
          and "没有可引用的图片" in empty["hint"] and empty["index"] == -1, empty)
    page.keyboard.press("Escape")
    empty_escape = page.evaluate("canvasAgentPanel.querySelector('.canvas-agent-mention')?.classList.contains('open')||false")
    check("空结果状态也可用 Escape 收起", not empty_escape, empty_escape)
    check("@引用交互无页面脚本异常", not errors, errors[:3])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
