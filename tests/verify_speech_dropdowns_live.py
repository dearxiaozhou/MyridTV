"""Read-only visual/interaction checks against the user's running development app."""
from pathlib import Path
import json
import urllib.request
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:3107'
CHROME=r'C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe'
def api(path):
    with urllib.request.urlopen(BASE+path,timeout=10) as response:return json.loads(response.read())
assert api('/health')['ok']
canvases=api('/api/canvases')['canvases']
canvas=next(c for c in canvases if c['title']=='MiMo 语音示例')
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=CHROME,headless=True)
    page=browser.new_page(viewport={'width':1440,'height':960})
    errors=[]
    page.on('pageerror',lambda err:errors.append(str(err)))
    page.goto(BASE+'/static/smart-canvas.html?id='+canvas['id'])
    page.locator('.speech-smart-node').first.wait_for()
    assert page.locator('script[src*="canvas-speech.js?v=0.8.12"]').count()==1
    assert page.locator('.speech-card select:visible').count()==0
    for field in ['speechProvider','speechModel','speechVoice','speechFormat','speechSinging','speechSpeed','speechEmotion','speechDialect']:
        trigger=page.locator(f'[data-speech-picker="{field}"]').first
        if not trigger.count():continue
        assert trigger.evaluate("el=>getComputedStyle(el).borderTopWidth")=='1px'
        trigger.click()
        menu=page.locator('.speech-picker-menu')
        assert menu.is_visible()
        rect=menu.bounding_box(); assert rect['x']>=0 and rect['y']>=0 and rect['x']+rect['width']<=1440 and rect['y']+rect['height']<=960
        assert trigger.locator('svg').evaluate('el=>getComputedStyle(el).width')=='13px'
        if field=='speechVoice':page.screenshot(path=str(ROOT/'verification-speech-live-v0812.png'))
        page.keyboard.press('Escape')
        assert menu.count()==0 and trigger.evaluate('el=>document.activeElement===el')
    assert page.locator('[data-speech=speechText]').first.evaluate("el=>getComputedStyle(el).fontSize")=='15px'
    original=page.locator('#world').evaluate('el=>el.style.transform')
    page.locator('#world').evaluate("el=>el.style.transform+=' scale(.75)'")
    page.locator('[data-speech-picker=speechEmotion]').first.click()
    menu=page.locator('.speech-picker-menu').bounding_box()
    anchor=page.locator('[data-speech-picker=speechEmotion]').first.bounding_box()
    assert abs(menu['x']-anchor['x'])<2
    page.keyboard.press('Escape')
    page.locator('#world').evaluate('(el,value)=>el.style.transform=value',original)
    page.locator('[data-speech=speechText]').first.click()
    assert page.locator('[data-speech=speechText]').first.evaluate('el=>document.activeElement===el')
    assert not errors,errors
    # Same live stylesheet, representative editor markup; DOM-only probes cannot save user data.
    sample='超写实次世代3D渲染，UE5电影级渲染风格，CG电影感写实。16:9 单张完整电影画面。'
    result=page.evaluate("""sample=>{
        const host=document.createElement('div');host.id='font-verification';
        host.style.cssText='position:fixed;inset:70px 30px 80px;z-index:999;background:var(--x-card);padding:20px;display:grid;grid-template-columns:1fr 1fr;gap:16px;overflow:auto';
        document.body.append(host);
        const fields=[['RH','composer rh-single-row','<div class="composer-card"><div class="prompt-input" contenteditable="true"></div></div>','.prompt-input'],['ComfyUI','composer comfy-layout','<div class="composer-card"><div class="prompt-input" contenteditable="true"></div></div>','.prompt-input'],['API 图片','composer api-single-row','<div class="composer-card"><div class="prompt-input" contenteditable="true"></div></div>','.prompt-input'],['API 视频','composer api-video-row','<div class="composer-card"><div class="prompt-input" contenteditable="true"></div></div>','.prompt-input'],['文本节点','image-node prompt-smart-node','<textarea class="prompt-node-text"></textarea>','textarea'],['剧本节点','image-node script-smart-node','<textarea class="prompt-node-text"></textarea>','textarea'],['循环节点','image-node','<div class="loop-smart-text" contenteditable="true"></div>','.loop-smart-text'],['提示词属性','image-node','<textarea class="smart-image-prompt-text"></textarea>','textarea'],['LLM 指令','image-node','<div class="prompt-node-llm"><textarea></textarea></div>','textarea']];
        return fields.map(([label,classes,html,selector])=>{
            const block=document.createElement('section'),node=document.createElement('div');block.innerHTML='<strong>'+label+'</strong>';node.className=classes;node.innerHTML=html;
            node.style.cssText='position:relative;inset:auto;width:100%;height:auto;opacity:1;visibility:visible;transform:none';block.append(node);host.append(block);
            const editor=node.querySelector(selector);if(editor.tagName==='TEXTAREA')editor.value=sample;else editor.textContent=sample;
            editor.style.minHeight='100px';editor.style.height='100px';
            const style=getComputedStyle(editor);return {label,size:style.fontSize,line:style.lineHeight};
        });
    }""",sample)
    assert all(field['size']=='15px' and field['line']=='23.25px' for field in result),result
    page.screenshot(path=str(ROOT/'verification-prompt-fonts-v0812.png'))
    print('PASS RH font parity in actual running styles:',json.dumps(result,ensure_ascii=False))
    page.evaluate("document.getElementById('font-verification').remove()")
    assert not errors,errors
    browser.close()
print('PASS actual development runtime: custom menus, matching icons, keyboard focus, bounds and zoom anchoring; no user data changed or remote calls')
