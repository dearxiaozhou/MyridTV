"""Exercise rich clipboard paste, undo and saved prompts in the actual canvas runtime."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CHROME = r'C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe'


def main():
    with tempfile.TemporaryDirectory(prefix='myridtv-paste-') as temp:
        base = 'http://127.0.0.1:3230'
        env = {**os.environ,'MYRIDTV_USER_DATA_DIR':temp,'MYRIDTV_ASSETS_DIR':str(Path(temp)/'assets')}
        with open(Path(temp)/'runtime.log','w',encoding='utf-8') as log:
            proc = subprocess.Popen([sys.executable,'-B','-c','import rh_official_proxy as p; p.ThreadingHTTPServer(("127.0.0.1",3230),p.Handler).serve_forever()'],cwd=ROOT,env=env,stdout=log,stderr=log)
            def api(path,payload=None):
                data = None if payload is None else json.dumps(payload).encode()
                request = urllib.request.Request(base+path,data=data,headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request,timeout=15) as response: return json.load(response)
            try:
                for _ in range(60):
                    try: api('/health'); break
                    except Exception: time.sleep(.2)
                else: raise RuntimeError('test runtime did not start')
                node = {'id':'paste_node','type':'smart-image','title':'纯文本粘贴验证','x':560,'y':120,'w':300,'h':220,'images':[],
                        'runSettings':{'engine':'api','apiKind':'image'},'promptDraftRefsEdited':True,
                        'promptDraftHtml':'<div style="background:white;color:black;font-size:11px"><p><b>旧背景文本</b></p><span class="mention-style-token" contenteditable="false" data-style-id="test" data-style-text="测试风格">@测试风格</span></div>'}
                cid = api('/api/canvases',{'title':'纯文本粘贴验证','kind':'smart','nodes':[node],'connections':[],'viewport':{'x':0,'y':0,'scale':1}})['canvas']['id']
                report = []
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(executable_path=CHROME,headless=True)
                    context = browser.new_context(viewport={'width':1440,'height':960},permissions=['clipboard-read','clipboard-write'])
                    page = context.new_page(); errors=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.route('**/static/app_config.json*',lambda route:route.fulfill(json={'proxy':{'base_url':base}}))
                    page.goto(base+'/static/smart-canvas.html?id='+cid)
                    page.locator('[data-id="paste_node"]').wait_for()
                    page.evaluate("selectNodeFromPointer('paste_node');syncSelectionUi();render();")
                    editor = page.locator('#promptInput');editor.wait_for(state='visible')
                    assert editor.locator('[style],b,strong,font').count()==0
                    assert editor.locator('.mention-style-token').count()==1
                    assert editor.locator('.mention-style-token').get_attribute('data-style-text')=='测试风格'
                    assert '旧背景文本' in editor.inner_text()
                    report.append('old background and fonts removed while internal reference survives')

                    async_clipboard = """async ({plain,html})=>navigator.clipboard.write([new ClipboardItem({'text/plain':new Blob([plain],{type:'text/plain'}),'text/html':new Blob([html],{type:'text/html'})})])"""
                    plain = 'subject definitions:\n• 人物一：沉稳的年轻男性\n\nsummary:\n保留换行与标点 <Subject 1> & 中文。'
                    rich = '<div style="background:#ffffff;color:black;font-size:10px"><h1>subject definitions:</h1><ul><li>人物一：沉稳的年轻男性</li></ul><p><b>summary:</b><br>保留换行与标点 &lt;Subject 1&gt; &amp; 中文。</p></div>'
                    # Real OS/browser clipboard -> Ctrl+V, including replacement and browser undo.
                    editor.click();page.keyboard.press('Control+a');page.keyboard.type('前文旧内容后文')
                    page.evaluate("()=>{const e=document.querySelector('#promptInput'),t=e.firstChild,r=document.createRange();r.setStart(t,2);r.setEnd(t,5);const s=getSelection();s.removeAllRanges();s.addRange(r);}")
                    page.evaluate(async_clipboard,{'plain':plain,'html':rich})
                    page.keyboard.press('Control+v')
                    assert editor.inner_text()=='前文'+plain+'后文',repr(editor.inner_text())
                    assert editor.locator('[style],font,h1,ul,b,strong').count()==0
                    assert editor.evaluate('el=>getComputedStyle(el).fontSize')=='15px'
                    page.keyboard.type('尾')
                    assert editor.inner_text()=='前文'+plain+'尾后文'
                    page.keyboard.press('Control+z')
                    assert editor.inner_text()=='前文'+plain+'后文',repr(editor.inner_text())
                    page.keyboard.press('Control+z')
                    assert editor.inner_text()=='前文旧内容后文'
                    page.keyboard.press('Control+Shift+z')
                    assert editor.inner_text()=='前文'+plain+'后文'
                    report.append('real rich clipboard pastes plain text at selection, keeps lines/caret and supports undo/redo')
                    # The same editor is reused by all generation engines.
                    for engine in ['rh','comfy','api']:
                        page.evaluate('(engine)=>{settings.engine=engine;renderDynamicParams();}',engine)
                        editor.click();page.keyboard.press('Control+a')
                        page.evaluate(async_clipboard,{'plain':plain,'html':rich})
                        page.keyboard.press('Control+v')
                        assert editor.inner_text()==plain
                        assert editor.locator('[style],font,h1,ul,b,strong').count()==0
                    report.append('RH, ComfyUI and API prompt editors use the same plain paste behavior')
                    page.screenshot(path=str(ROOT/'verification-plain-paste-v0816.png'))
                    page.wait_for_timeout(1200);page.reload()
                    page.locator('[data-id="paste_node"]').wait_for()
                    page.evaluate("selectNodeFromPointer('paste_node');syncSelectionUi();render();")
                    editor.wait_for(state='visible')
                    assert editor.inner_text()==plain
                    assert editor.locator('[style],font,h1,ul,b,strong').count()==0
                    report.append('pasted text persists after save/reload without imported formatting')
                    # Existing reference chips outside the pasted selection must remain intact.
                    page.evaluate("()=>{const e=document.querySelector('#promptInput');e.innerHTML='<span class=\"mention-style-token\" contenteditable=\"false\" data-style-id=\"test\" data-style-text=\"测试风格\">@测试风格</span> 原文';e.focus();const r=document.createRange();r.selectNodeContents(e);r.collapse(false);const s=getSelection();s.removeAllRanges();s.addRange(r);}")
                    page.evaluate(async_clipboard,{'plain':' 添加文字','html':'<b style="background:white"> 添加文字</b>'})
                    page.keyboard.press('Control+v')
                    assert editor.locator('.mention-style-token').count()==1
                    assert editor.locator('.mention-style-token').get_attribute('data-style-text')=='测试风格'
                    report.append('pasting after an internal reference keeps its metadata')
                    # HTML-only clipboard fallback and dynamic loop editors use safe text.
                    result=page.evaluate("""()=>{const e=document.createElement('div');e.className='loop-smart-text';e.contentEditable='true';e.style.whiteSpace='pre-wrap';document.body.append(e);e.focus();const r=document.createRange();r.selectNodeContents(e);r.collapse(false);const s=getSelection();s.removeAllRanges();s.addRange(r);const data=new DataTransfer();data.setData('text/html','<p style="background:white">第一行<br>第二行</p><ul><li>第三行</li></ul>');const ev=new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:data});e.dispatchEvent(ev);const result={text:e.innerText,html:e.innerHTML,prevented:ev.defaultPrevented};e.remove();return result;}""")
                    assert result['text']=='第一行\n第二行\n• 第三行',result
                    assert result['prevented'] and 'style=' not in result['html']
                    report.append('dynamic loop editor and HTML-only clipboard preserve text/lines without styles')
                    # A clipboard file remains available to the existing media upload handler.
                    file_result=page.evaluate("""()=>{const e=document.createElement('div');e.className='loop-smart-text';e.contentEditable='true';document.body.append(e);const data=new DataTransfer();data.items.add(new File(['fixture'],'unsupported.xyz',{type:'application/octet-stream'}));const ev=new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:data});e.dispatchEvent(ev);e.remove();return ev.defaultPrevented;}""")
                    assert not file_result
                    report.append('file clipboard is left to existing media handling')
                    assert not errors,errors
                    browser.close()
                    for line in report: print('PASS '+line,flush=True)
                    (ROOT/'verification-plain-paste-v0816.json').write_text(json.dumps({'runtime':base,'passed':report,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
            finally:
                proc.terminate();proc.wait(timeout=10)


if __name__=='__main__': main()
