# -*- coding: utf-8 -*-
"""
e2e_canvas_prompt_lib_picker.py
================================
守护提示词框「~ 快捷调出提示词库」面板（2026-09-23）：

交互定稿：光标在提示词框按 ~ → 下方弹出面板，只显示条目标题；~后输入按标题过滤；
↑↓ 移动、Enter/点击插入 positive 全文（会删掉 ~查询串）、Esc 关闭并擦掉 ~查询。

断言：
1. 输入 ~ → 面板出现（display!=none），含标题列表与「管理提示词库」行
2. 每行只显示名称（含书签图标 span），无正文泄漏
3. ~ 后继续输入关键词 → 过滤到匹配项
4. ArrowDown 移动 active 态
5. Enter 插入选中条目 positive、面板关闭、提示词框无残留 ~查询
6. Esc 关闭且擦除临时 ~文本
7. 空匹配显示占位提示
8. 面板数据源=/api/prompt-libraries（fetch mock 验证 URL）
9. 无 JS 报错

依赖：隔离测试实例 3217
"""
import json, sys
from playwright.sync_api import sync_playwright

import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} - {label} | {str(detail)[:160]}")
    return 1 if ok else 0


def main():
    failures = 0
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
        lib_calls = []

        def rc(route):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"proxy": {"base_url": BASE}}))
        page.route("**/static/app_config.json*", rc)

        # mock 提示词库接口（不依赖用户真实库内容，保证断言确定）
        def lib_route(route):
            lib_calls.append(route.request.url)
            route.fulfill(status=200, content_type="application/json", body=json.dumps({
                "ok": True,
                "library": {"libraries": [
                    {"id": "system", "name": "系统提示词库", "items": [
                        {"id": "t1", "name": "九宫格分镜", "positive": "生成九宫格分镜内容POSITIVE1", "negative": "禁文字NEG1"},
                        {"id": "t2", "name": "360全景图", "positive": "生成全景POSITIVE2", "negative": ""},
                        {"id": "t3", "name": "赛博朋克角色", "positive": "POSITIVE3", "negative": ""},
                        {"id": "t_hide", "name": "要被隐藏的内置", "positive": "HIDE_ME", "negative": ""},
                    ]},
                    {"id": "mine", "name": "我的库", "items": [
                        {"id": "t4", "name": "产品主图", "positive": "POSITIVE4", "negative": ""},
                        {"id": "t5", "name": "", "positive": "", "negative": ""},
                    ]},
                ]}
            }))
        page.route("**/api/prompt-libraries", lib_route)

        page.goto(f"{BASE}/smart-canvas.html", wait_until="domcontentloaded")
        page.evaluate("""() => {
            localStorage.setItem('canvas_prompt_template_overrides', JSON.stringify({
                hiddenBuiltinIds: ['t_hide'],
                editedBuiltins: { t3: { name: '赛博朋克角色(改)', positive: 'EDITED_POS' } }
            }));
        }""")
        page.wait_for_timeout(1200)

        # 面板模块加载
        has_mod = page.evaluate("() => typeof CanvasPromptLibPicker !== 'undefined' && typeof CanvasPromptLibPicker.open === 'function'")
        failures += not check("模块已加载", has_mod, "")
        if not has_mod:
            print("\nRESULT: 0/10"); sys.exit(1)

        # 打开一个带输入区的 composer：预置一个图片节点并选中→composer 出现 promptInput
        page.evaluate("""() => {
            nodes.push({id:'plib_node', type:'smart-image', title:'测', x:400, y:300, w:300, h:200,
                images:[{url:'/assets/input/ai_ref_b402b83fb32e.png', name:'t', kind:'image', generatedResult:true}]});
            selectedId = 'plib_node'; selectedIds = ['plib_node'];
            render();
            promptInput.textContent = '';
            promptInput.dispatchEvent(new Event('input', {bubbles:true}));
        }""")
        page.wait_for_timeout(400)

        # 1. 真实键盘输入 ~ 打开面板
        page.click("#promptInput")
        page.keyboard.type("~")
        page.wait_for_timeout(800)
        open1 = page.evaluate("""() => {
            const el = document.querySelector('.prompt-lib-picker');
            return {display: el ? getComputedStyle(el).display : 'none',
                    items: [...document.querySelectorAll('.prompt-lib-item')].map(b => b.textContent.trim()),
                    hasManage: !!document.querySelector('[data-plib-manage]'),
                    isOpen: CanvasPromptLibPicker.isOpen()};
        }""")
        names = [i.replace("\u200b", "") for i in open1["items"]]
        # system库4项(t_hide 被隐藏→3) + mine库(t4, t5无正文被过滤) = 4
        ok1 = (open1["display"] != "none" and open1["isOpen"]
               and len(open1["items"]) == 4 and open1["hasManage"]
               and all("隐藏" not in n for n in names)
               and any("赛博朋克角色(改)" in n for n in names))
        failures += not check("~ 键弹出面板+localStorage覆盖层(隐藏内置/编辑名)与旧页面同源", ok1, json.dumps(open1, ensure_ascii=False)[:220])

        # 2. 只显示标题，无正文
        no_body = all("POSITIVE" not in i for i in open1["items"])
        failures += not check("只显标题无正文泄漏", no_body, str(open1["items"]))

        # 3. 数据源 URL
        failures += not check("数据源=/api/prompt-libraries", any("/api/prompt-libraries" in u for u in lib_calls), str(lib_calls[:2]))

        # 4. 继续输入过滤
        page.keyboard.type("九宫")
        page.wait_for_timeout(400)
        filt = page.evaluate("() => [...document.querySelectorAll('.prompt-lib-item')].map(b => b.textContent.trim())")
        failures += not check("~后输入按标题过滤", len(filt) == 1 and "九宫格" in filt[0], str(filt))

        # 5. Enter 插入正文并清 ~查询
        page.keyboard.press("Enter")
        page.wait_for_timeout(400)
        after = page.evaluate("""() => ({text: promptInput.textContent, open: CanvasPromptLibPicker.isOpen()})""")
        ok5 = after["text"].startswith("生成九宫格分镜") and "POSITIVE1" in after["text"] and "~" not in after["text"] and not after["open"]
        failures += not check("Enter 插入 positive 且擦除~查询、面板关闭", ok5, json.dumps(after, ensure_ascii=False)[:150])

        # 6. Esc 关闭并擦除（先清空输入框，再输入 ~全）
        page.evaluate("() => { promptInput.textContent=''; promptInput.dispatchEvent(new Event('input',{bubbles:true})); }")
        page.keyboard.type("~全")
        page.wait_for_timeout(500)
        mid = page.evaluate("() => ({text: promptInput.textContent, open: CanvasPromptLibPicker.isOpen()})")
        if not mid["open"]:
            # caret 丢失时点击输入框末尾再试
            page.click("#promptInput")
            page.evaluate("""() => { const r=document.createRange(); r.selectNodeContents(promptInput); r.collapse(false); const s=getSelection(); s.removeAllRanges(); s.addRange(r); }""")
            page.keyboard.type("~全")
            page.wait_for_timeout(500)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        esc = page.evaluate("""() => ({text: promptInput.textContent, open: CanvasPromptLibPicker.isOpen()})""")
        failures += not check("Esc 关闭且擦除临时文本", "~" not in esc["text"] and "全" not in esc["text"] and not esc["open"], json.dumps(esc, ensure_ascii=False))

        # 7. ArrowDown 移动 + 点击插入
        page.keyboard.type("~")
        page.wait_for_timeout(600)
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(200)
        act = page.evaluate("() => { const el = document.querySelector('.prompt-lib-item.active'); return el ? el.textContent.trim() : 'NONE'; }")
        failures += not check("ArrowDown 高亮下移", "360全景" in act or "赛博" in act, act)
        # 点高亮的第 2 项（360全景图）
        page.click(".prompt-lib-item.active")
        page.wait_for_timeout(400)
        clicked = page.evaluate("""() => ({text: promptInput.textContent, open: CanvasPromptLibPicker.isOpen()})""")
        failures += not check("点击 active 条目插入并关闭", "POSITIVE2" in clicked["text"] and "~" not in clicked["text"] and not clicked["open"], json.dumps(clicked, ensure_ascii=False)[:140])

        # 8. 空匹配占位
        page.evaluate("() => { promptInput.textContent=''; promptInput.dispatchEvent(new Event('input',{bubbles:true})); }")
        page.keyboard.type("~zzzz不存在zzz")
        page.wait_for_timeout(500)
        empty = page.evaluate("() => { const el = document.querySelector('.prompt-lib-empty'); return el ? el.textContent : 'NO_EMPTY'; }")
        failures += not check("无匹配显示占位提示", "没有匹配" in empty, empty[:60])
        page.keyboard.press("Escape")

        # 10. 占位提示：空=显示，打字=隐藏，删空(含残留<br>)=重现
        page.evaluate("() => { CanvasPromptLibPicker.close({keepTyped:true}); promptInput.innerHTML=''; promptInput.dispatchEvent(new Event('input',{bubbles:true})); }")
        page.wait_for_timeout(200)
        ph0 = page.evaluate("() => promptInput.classList.contains('show-placeholder')")
        page.keyboard.type("你好")
        page.wait_for_timeout(200)
        ph1 = page.evaluate("() => promptInput.classList.contains('show-placeholder')")
        # 模拟删空但残留 <br>（:empty 会失配的场景）
        page.evaluate("() => { promptInput.innerHTML = '<br>'; promptInput.dispatchEvent(new Event('input',{bubbles:true})); }")
        page.wait_for_timeout(200)
        ph2 = page.evaluate("() => promptInput.classList.contains('show-placeholder')")
        # 只有 @ 引用 token 没有文字 → 视为有内容，占位应隐藏
        ph3 = page.evaluate("""() => {
            promptInput.innerHTML = '<span class="mention-image-token" contenteditable="false" data-url="/assets/input/x.png">@图片1</span>';
            promptInput.dispatchEvent(new Event('input',{bubbles:true}));
            return promptInput.classList.contains('show-placeholder');
        }""")
        failures += not check("占位:空显示/打字隐藏/删空重现/仅引用token隐藏",
                      ph0 and not ph1 and ph2 and not ph3, f"empty={ph0} typed={ph1} br={ph2} token={ph3}")
        page.evaluate("() => { promptInput.textContent=''; promptInput.dispatchEvent(new Event('input',{bubbles:true})); localStorage.removeItem('canvas_prompt_template_overrides'); }")

        real_errors = [e for e in errors if "WebSocket" not in e and "stats" not in e]
        failures += not check("无 JS 报错", len(real_errors) == 0, str(real_errors[:2]))

        browser.close()

    total = 10
    print(f"\nRESULT: {total - failures}/{total}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
