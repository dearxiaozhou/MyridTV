# -*- coding: utf-8 -*-
"""Smoke-check accessible names on frequently used controls."""
import os

from playwright.sync_api import sync_playwright


BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217").rstrip("/")
CHROME = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
results = []


def check(label, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + label + (" | " + str(detail)[:220] if detail else ""))


def main():
    page_errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=CHROME,
            headless=True,
            args=["--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        page.goto(f"{BASE}/api-settings.html", wait_until="domcontentloaded", timeout=30000)
        provider_add = page.get_by_role("button", name="新增平台")
        provider_add.wait_for(state="visible", timeout=20000)
        check("API 配置的新增平台按钮有可访问名称", provider_add.get_attribute("aria-label") == "新增平台")
        check("协议下拉框有可访问名称", page.get_by_role("combobox", name="协议").count() == 1)
        model_fields = page.locator(".model-value-input")
        if model_fields.count():
            model_names = [
                (field.get_attribute("aria-label") or "").strip()
                for field in model_fields.all()
                if field.is_visible()
            ]
        else:
            # A clean install has no saved providers/models. Exercise the live
            # renderer without adding or saving a fake provider to user data.
            model_names = page.evaluate("""() => {
                const cases = [
                    {kind:'image', item:{id:'a11y-probe', protocol:'openai', image_models:[]}, index:0, value:'probe-image'},
                    {kind:'video', item:{id:'a11y-probe', protocol:'openai', video_models:['probe-video-a','probe-video-b']}, index:1, value:'probe-video-b'}
                ];
                return cases.map(({kind, item, index, value}) => {
                    const template = document.createElement('template');
                    template.innerHTML = renderModelValueControl(item, kind, index, value);
                    const control = template.content.querySelector('.model-value-input');
                    return control?.getAttribute('aria-label') || '';
                });
            }""")
        check(
            "所有可见模型输入和下拉框都有名称",
            bool(model_names) and all(model_names),
            f"model fields={model_fields.count()}, labels={model_names}",
        )
        if not page.locator(".provider-card").count():
            page.evaluate("""() => {
                const probe = document.createElement('button');
                probe.type = 'button';
                probe.className = 'provider-card';
                probe.textContent = 'a11y keyboard focus probe';
                document.querySelector('#providerList')?.prepend(probe);
            }""")
        focused_provider = page.locator(".provider-list .provider-card:focus-visible")
        for _ in range(24):
            if focused_provider.count():
                break
            page.keyboard.press("Tab")
        if focused_provider.count():
            page.wait_for_timeout(200)  # Allow the card's 150 ms transition to finish.
        focus_outline = focused_provider.first.evaluate("""el => {
            const style = getComputedStyle(el);
            return {visible: style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2,
                    outline: style.outline, offset: style.outlineOffset};
        }""") if focused_provider.count() else None
        check("API 平台卡片获得键盘焦点时有清晰焦点环", bool(focus_outline and focus_outline["visible"]), focus_outline)
        page.evaluate("""() => {
            document.documentElement.classList.remove('studio-theme-dark', 'theme-dark');
            document.body.classList.remove('studio-theme-dark', 'theme-dark');
            document.documentElement.classList.add('theme-light');
            document.body.classList.add('theme-light');
        }""")
        page.wait_for_timeout(200)
        light_focus_outline = focused_provider.first.evaluate("""el => {
            const style = getComputedStyle(el);
            return {visible: style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2,
                    outline: style.outline, offset: style.outlineOffset};
        }""") if focused_provider.count() else None
        check("API 平台卡片的浅色主题也保留清晰焦点环", bool(light_focus_outline and light_focus_outline["visible"]), light_focus_outline)

        page.goto(f"{BASE}/asset-manager.html", wait_until="domcontentloaded", timeout=30000)
        provider_label = page.evaluate("""() => {
            apiProviders = [{id:'apimart', name:'APIMart', protocol:'apimart', enabled:true, has_key:true}];
            const host = document.createElement('div');
            host.innerHTML = renderAvatarSection({id:'a11y-probe', registrations:{}});
            document.body.appendChild(host);
            return host.querySelector('[data-avatar-provider]')?.getAttribute('aria-label') || '';
        }""")
        check("素材库认证平台下拉框有可访问名称", provider_label == "认证平台", provider_label)

        page.goto(f"{BASE}/comfyui-settings.html", wait_until="domcontentloaded", timeout=30000)
        preview_controls = page.evaluate("""() => {
            const host = document.createElement('div');
            host.innerHTML = [
                renderPreviewField({id:'a11y-prompt', name:'提示词', input:'prompt', type:'textarea', default:''}),
                renderPreviewField({id:'a11y-switch', name:'启用功能', input:'enabled', type:'boolean', default:false})
            ].join('');
            document.body.appendChild(host);
            const prompt = host.querySelector('textarea');
            const toggle = host.querySelector('[role="switch"]');
            toggle.focus();
            return {promptLabel:prompt?.getAttribute('aria-label') || '', switchLabel:toggle?.getAttribute('aria-label') || '', initial:toggle?.getAttribute('aria-checked') || ''};
        }""")
        check("Comfy 工作流提示词预览框有名称", preview_controls["promptLabel"] == "提示词", preview_controls)
        check("Comfy 开关有名称和状态", preview_controls["switchLabel"] == "启用功能" and preview_controls["initial"] == "false", preview_controls)
        page.keyboard.press("Space")
        toggle_state = page.locator('[role="switch"][aria-label="启用功能"]').get_attribute("aria-checked")
        check("Comfy 开关可用键盘切换并同步读屏状态", toggle_state == "true", toggle_state)

        page.goto(f"{BASE}/smart-canvas.html", wait_until="domcontentloaded", timeout=30000)
        run_button = page.locator("#runBtn")
        run_button.wait_for(state="attached", timeout=20000)
        check("画布运行按钮有可访问名称", (run_button.get_attribute("aria-label") or "").strip() == "运行")
        style_button = page.locator(".style-mode-control > .smart-pill")
        check("画布风格选择按钮有可访问名称", (style_button.get_attribute("aria-label") or "").startswith("风格"))
        prompt = page.locator("#promptInput")
        focused_prompt = page.locator("#promptInput:focus-visible")
        for _ in range(48):
            if focused_prompt.count():
                break
            page.keyboard.press("Tab")
        if focused_prompt.count():
            page.wait_for_timeout(200)
        prompt_outline = focused_prompt.evaluate("""el => {
            const style = getComputedStyle(el);
            return {visible: style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2,
                    outline: style.outline, offset: style.outlineOffset};
        }""") if focused_prompt.count() else None
        check("画布提示词编辑框可通过键盘到达且有清晰焦点环", bool(prompt_outline and prompt_outline["visible"]), prompt_outline)
        check("可访问性用例没有脚本异常", not page_errors, page_errors[:3])
        browser.close()

    passed = sum(results)
    print(f"RESULT: {passed}/{len(results)}")
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
