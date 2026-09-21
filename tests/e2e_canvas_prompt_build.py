# -*- coding: utf-8 -*-
"""
e2e_canvas_prompt_build.py
===========================
守护「提示词 → 生成请求构建」链路（阶段 1，2026-09-21）：
填写画布提示词框 → collectPromptParts 收集 → buildPromptRequest 组包。

真实 UI 交互 + 数据断言：
1. 用 ?id=<画布id> 加载真实画布
2. 创建 prompt 节点
3. 在全局 .prompt-input（contenteditable，画布级输入框）填入提示词
4. collectPromptParts() 能收集到该文本
5. buildPromptRequest(node) 返回的 prompt 包含提示词文本

关键教训（2026-09-21 探测）：
- 提示词输入框是画布级全局 .prompt-input，不在节点 DOM 内
  （节点内无 [contenteditable=true]，填节点内会失败）
- collectPromptParts 收集 {type:'text', text:'...'}；buildPromptRequest 返回
  {prompt, displayPrompt, refs, mentioned}
- 必须 ?id= 加载真实画布（canvas 初始化，buildPromptRequest 依赖全局状态）

依赖：隔离测试实例 3217
"""
import json, sys, urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:3217"


def create_test_canvas():
    req = urllib.request.Request(
        f"{BASE}/api/canvases",
        data=json.dumps({"name": "e2e-prompt", "nodes": [], "connections": []}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["canvas"]["id"]


def check(label, ok, detail=""):
    sym = "PASS" if ok else "FAIL"
    print(f"{sym} - {label} | {detail}")
    return 1 if ok else 0


def main():
    failures = 0
    canvas_id = create_test_canvas()
    print(f"测试画布: {canvas_id}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
            headless=True,
            args=["--no-sandbox"],
        )
        ctx = browser.new_context(viewport={"width": 1680, "height": 980})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        def rc(route):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"proxy": {"base_url": BASE}}))

        page.route("**/static/app_config.json", rc)
        page.goto(f"{BASE}/smart-canvas.html?id={canvas_id}", wait_until="networkidle")
        page.wait_for_timeout(2500)

        # === 1. 创建 prompt 节点 ===
        page.click("#canvasAddToggle")
        page.wait_for_timeout(300)
        page.click('[data-create-type="prompt"]')
        page.wait_for_timeout(1500)
        nid = page.eval_on_selector(".image-node", "el => el.getAttribute('data-id')")
        failures += not check("创建 prompt 节点", bool(nid and nid.startswith("prompt_")), str(nid))

        # === 2. 填全局 .prompt-input ===
        PROMPT_TEXT = "一只猫在窗台上晒太阳"
        filled = page.evaluate("""(PROMPT_TEXT) => {
            const editable = document.querySelector('.prompt-input');
            if(!editable) return 'no .prompt-input';
            editable.textContent = PROMPT_TEXT;
            editable.dispatchEvent(new Event('input', {bubbles: true}));
            editable.dispatchEvent(new Event('change', {bubbles: true}));
            return 'filled';
        }""", PROMPT_TEXT)
        failures += not check("填全局 .prompt-input", filled == "filled", str(filled))
        page.wait_for_timeout(800)

        # === 3. collectPromptParts 收集到文本 ===
        parts = page.evaluate("() => collectPromptParts().map(p=>({type:p.type, text:(p.text||'')}))")
        text_parts = [p for p in parts if p["type"] == "text" and p["text"] == PROMPT_TEXT]
        failures += not check("collectPromptParts 收集到提示词", len(text_parts) >= 1, json.dumps(parts, ensure_ascii=False))

        # === 4. buildPromptRequest 返回 prompt 含提示词 ===
        result = page.evaluate("""(id) => {
            const n = nodes.find(x=>x.id===id);
            if(!n) return 'no node';
            try {
                const r = buildPromptRequest(n);
                return {prompt: (r && r.prompt || ''), hasPrompt: !!(r && r.prompt)};
            } catch(e) { return 'ERR: ' + e.message; }
        }""", nid)
        failures += not check("buildPromptRequest 含提示词", isinstance(result, dict) and PROMPT_TEXT in result.get("prompt", ""), json.dumps(result, ensure_ascii=False))

        # === 5. 幂等：清空后 rebuild 不再含旧文本 ===
        cleared = page.evaluate("""() => {
            const editable = document.querySelector('.prompt-input');
            if(!editable) return 'no input';
            editable.textContent = '';
            editable.dispatchEvent(new Event('input', {bubbles: true}));
            editable.dispatchEvent(new Event('change', {bubbles: true}));
            return 'cleared';
        }""")
        page.wait_for_timeout(500)
        result2 = page.evaluate("""(id) => {
            const n = nodes.find(x=>x.id===id);
            if(!n) return 'no node';
            try {
                const r = buildPromptRequest(n);
                return {prompt: (r && r.prompt || '')};
            } catch(e) { return 'ERR: ' + e.message; }
        }""", nid)
        failures += not check("清空后 prompt 不含旧文本", not (isinstance(result2, dict) and PROMPT_TEXT in result2.get("prompt", "")), json.dumps(result2, ensure_ascii=False))

        # 无 JS 报错
        real_errors = [e for e in errors if "WebSocket" not in e and "stats" not in e]
        failures += not check("无 JS 报错", len(real_errors) == 0, str(real_errors[:3]))

        browser.close()

    total = 6
    passed = total - failures
    print(f"\nRESULT: {passed}/{total}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
