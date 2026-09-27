# -*- coding: utf-8 -*-
"""Browser regression for stopping an in-flight canvas Agent request."""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright


BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217").rstrip("/")
CHROME = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
results = []


def check(label, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + label + (" | " + str(detail)[:260] if detail else ""))


def create_canvas():
    request = urllib.request.Request(
        BASE + "/api/canvases",
        data=json.dumps({"title": "Agent stop regression", "nodes": [], "connections": [], "settings": {}}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode())["canvas"]["id"]


def main():
    canvas_id = create_canvas()
    stop_requests = []
    errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route(
            "**/static/app_config.json*",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"proxy": {"base_url": BASE}}),
            ),
        )

        def stop_route(route):
            try:
                stop_requests.append(json.loads(route.request.post_data or "{}"))
            except Exception:
                stop_requests.append({})
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))

        page.route("**/api/canvas-llm-stop*", stop_route)
        page.goto(f"{BASE}/smart-canvas.html?id={canvas_id}", wait_until="domcontentloaded")
        page.locator("#canvasAgentSend").wait_for(state="attached", timeout=15000)
        page.wait_for_function("id => canvas?.id === id", arg=canvas_id, timeout=15000)

        page.evaluate(
            """() => {
              window.waitForCanvasAgentProxy = async () => true;
              window.persistCanvasAgentSession = async () => ({ok:true});
              window.canvasAgentChatProviders = () => [{id:'e2e-provider',chat_models:['e2e-model']}];
              window.resolveCanvasAgentChatModel = () => 'e2e-model';
              window.fetchCanvasAgentLLM = (payload, url, signal) => new Promise((resolve,reject) => {
                window.__agentStopSignal = signal;
                const abort = () => reject(Object.assign(new Error('request aborted'), {userStopped:true}));
                if(signal.aborted) abort();
                else signal.addEventListener('abort', abort, {once:true});
              });
              window.__agentStopToasts = [];
              window.toast = value => window.__agentStopToasts.push(String(value));
              setCanvasAgentOpen(true);
            }"""
        )
        page.locator("#canvasAgentSend").wait_for(state="visible", timeout=5000)
        page.locator("#canvasAgentInput").fill("Stop this test request")
        page.locator("#canvasAgentSend").click()
        page.wait_for_function("() => canvasAgentSending && window.__agentStopSignal", timeout=8000)
        before_stop = page.evaluate(
            """() => ({open:canvasAgentPanel.classList.contains('open'),sending:canvasAgentSending,
              buttonLabel:canvasAgentSend.getAttribute('aria-label'),requestId:canvasAgentActiveRequestId})"""
        )
        check("Agent 面板可打开并进入请求中状态", before_stop["open"] and before_stop["sending"] and before_stop["requestId"], before_stop)

        page.locator("#canvasAgentSend").click()
        page.wait_for_function(
            "() => !canvasAgentSending && !canvasAgentMessagesState.some(message=>message.status==='thinking')",
            timeout=8000,
        )
        page.wait_for_function("() => window.__agentStopSignal?.aborted && window.__agentStopToasts.includes('已停止生成')", timeout=5000)
        after_stop = page.evaluate(
            """() => ({aborted:window.__agentStopSignal?.aborted,sending:canvasAgentSending,
              buttonLabel:canvasAgentSend.getAttribute('aria-label'),thinking:canvasAgentMessagesState.some(message=>message.status==='thinking'),
              toast:window.__agentStopToasts.at(-1),requestId:canvasAgentActiveRequestId})"""
        )
        check("停止操作终止请求、清理思考态并恢复发送按钮",
              after_stop["aborted"] and not after_stop["sending"] and not after_stop["thinking"]
              and after_stop["buttonLabel"] == "发送" and after_stop["toast"] == "已停止生成", after_stop)
        page.wait_for_timeout(100)
        check("停止请求携带当前请求 ID", len(stop_requests) == 1 and stop_requests[0].get("request_id") == before_stop["requestId"], stop_requests)

        check("停止流程无页面脚本异常", not errors, errors[:3])
        browser.close()

    print(f"\nRESULT: {sum(results)}/{len(results)}")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
