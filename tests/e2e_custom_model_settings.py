"""Actual HTTP/UI save and reload with isolated user data and a local model API."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:3238'
CHROME=r'C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe'

class Models(BaseHTTPRequestHandler):
    fail=False
    def do_GET(self):
        self.send_response(403 if self.fail else 200)
        self.send_header('Content-Type','application/json');self.end_headers()
        self.wfile.write(json.dumps({'data':[{'id':m} for m in ['chat-future','image-future','video-future','tts-future']]}).encode())
    def log_message(self,*args):pass

def main():
    fixture=ThreadingHTTPServer(('127.0.0.1',0),Models)
    threading.Thread(target=fixture.serve_forever,daemon=True).start()
    with tempfile.TemporaryDirectory(prefix='custom-models-') as temp:
        env={**os.environ,'MYRIDTV_USER_DATA_DIR':temp,'MYRIDTV_ASSETS_DIR':str(Path(temp)/'assets')}
        with open(Path(temp)/'runtime.log','w') as log:
            proc=subprocess.Popen([sys.executable,'-B','-c','import rh_official_proxy as p; p.ThreadingHTTPServer(("127.0.0.1",3238),p.Handler).serve_forever()'],cwd=ROOT,env=env,stdout=log,stderr=log)
            def api(path,data=None,method=None):
                req=urllib.request.Request(BASE+path,data=None if data is None else json.dumps(data).encode(),method=method,headers={'Content-Type':'application/json'})
                return json.load(urllib.request.urlopen(req,timeout=15))
            try:
                for _ in range(80):
                    try:api('/health');break
                    except Exception:time.sleep(.2)
                record={'id':'custom-api','name':'自定义模型验证','base_url':f'http://127.0.0.1:{fixture.server_port}/v1','protocol':'openai','enabled':True,
                        'image_models':[],'chat_models':['manual-unlisted'],'video_models':[],'audio_models':[]}
                api('/api/providers',[record],'PUT')
                with sync_playwright() as pw:
                    desktop=None
                    if '--desktop' in sys.argv:
                        host=Path(temp)/'desktop';host.mkdir()
                        shutil.copy2(ROOT/'MyridTV-Desktop.exe',host/'MyridTV-Desktop.exe')
                        config=host/'_internal/data';config.mkdir(parents=True)
                        (config/'app_config.json').write_text(json.dumps({'proxy':{'port':3238}}))
                        startup=subprocess.STARTUPINFO();startup.dwFlags=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
                        desktop=subprocess.Popen([str(host/'MyridTV-Desktop.exe')],env={**env,'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS':'--remote-debugging-port=9236','WEBVIEW2_USER_DATA_FOLDER':str(host/'profile')},startupinfo=startup)
                        for _ in range(80):
                            try:urllib.request.urlopen('http://127.0.0.1:9236/json/version',timeout=1);break
                            except Exception:time.sleep(.2)
                        browser=pw.chromium.connect_over_cdp('http://127.0.0.1:9236')
                        page=browser.contexts[0].pages[0]
                        page.wait_for_url('**/static/index.html',timeout=15000)
                        page.wait_for_load_state('networkidle')
                    else:
                        browser=pw.chromium.launch(executable_path=CHROME,headless=True)
                        page=browser.new_page(viewport={'width':1440,'height':1000})
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.on('dialog',lambda d:d.dismiss())
                    page.goto(BASE+'/static/api-settings.html',wait_until='networkidle')
                    page.evaluate("selectProvider('custom-api')")
                    page.locator('#fetchModelsBtn').click()
                    overlay=page.locator('#modelPickerOverlay');overlay.wait_for(state='visible')
                    assert page.locator('.picker-row').count()==5
                    assert page.evaluate("pickerState.category['tts-future']")=='audio'
                    # A user can override guesses and retain unlisted manual models.
                    page.locator('[aria-label="chat-future 模型分类"]').select_option('audio')
                    page.locator('.picker-row').filter(has=page.locator('[title="chat-future"]')).click()
                    page.locator('.picker-row').filter(has=page.locator('[title="tts-future"]')).click()
                    page.evaluate('applyModelPicker()')
                    page.evaluate("selectApiModelTab('chat');addModel('chat')")
                    fields=page.locator('#chatModelList input.model-value-input')
                    assert fields.count()==1
                    fields.last.fill('typed-any-new-model')
                    fields.last.press('Enter')
                    assert page.locator('#chatModelList input[list]').count()==0
                    model_trigger=page.locator('#chatModelList .shared-native-select-trigger').last
                    model_trigger.click()
                    assert model_trigger.get_attribute('aria-expanded')=='true'
                    page.locator('.shared-native-select-option').filter(has_text='手动输入模型 ID').click()
                    edit=page.locator('#chatModelList input.model-value-input')
                    edit.fill('cancel-this-model');edit.press('Escape')
                    assert page.evaluate("provider().chat_models.includes('typed-any-new-model')")
                    for theme in ('dark','light'):
                        page.evaluate('theme=>StudioTheme.set(theme)',theme)
                        trigger=page.locator('#chatModelList .shared-native-select-trigger').last
                        trigger.click()
                        options=page.locator('.shared-native-select-option')
                        options.first.hover()
                        selected=page.locator('.shared-native-select-option[aria-selected="true"]')
                        assert selected.count()==1
                        style=selected.evaluate('(el)=>({bg:getComputedStyle(el).backgroundColor,text:getComputedStyle(el).color})')
                        assert style['bg']!='rgba(0, 0, 0, 0)',style
                        page.screenshot(path=str(ROOT/f'_verification/model-dropdown-{theme}-v01016.png'))
                        trigger.press('Escape')
                        assert trigger.get_attribute('aria-expanded')=='false'
                        trigger.focus()
                        assert trigger.evaluate('el=>el===document.activeElement')
                    with page.expect_response(lambda r:r.url.endswith('/api/providers') and r.request.method=='PUT') as response:
                        page.locator('#saveModelsBtn').click()
                    assert response.value.ok
                    page.wait_for_load_state('networkidle')
                    saved=api('/api/providers')['providers'][0]
                    assert set(saved['chat_models'])=={'manual-unlisted','typed-any-new-model'},saved
                    assert set(saved['audio_models'])=={'chat-future','tts-future'},saved
                    page.reload(wait_until='networkidle');page.evaluate("selectProvider('custom-api')")
                    assert page.evaluate('provider().chat_models')==saved['chat_models']
                    page.locator('#fetchModelsBtn').click();overlay.wait_for(state='visible')
                    assert page.evaluate("pickerState.category['chat-future']")=='audio'
                    assert page.evaluate("pickerState.selected['typed-any-new-model']") is True
                    page.evaluate("StudioTheme.set('dark')")
                    page.screenshot(path=str(ROOT/'_verification/custom-model-picker-dark-v01015.png'))
                    page.evaluate("StudioTheme.set('light')")
                    page.screenshot(path=str(ROOT/'_verification/custom-model-picker-light-v01015.png'))
                    page.evaluate('closeModelPicker()');Models.fail=True
                    page.locator('#fetchModelsBtn').click()
                    page.wait_for_function("!document.getElementById('fetchModelsBtn').disabled")
                    assert page.evaluate('provider().chat_models')==saved['chat_models']
                    assert '手动填写' in page.evaluate('statusEl.textContent')
                    page.goto(BASE+'/static/smart-canvas.html',wait_until='networkidle')
                    page.evaluate('p => {apiProviders=[{...p,has_key:true}];nodes.push({id:"speech-test",type:"smart-speech",x:100,y:100,w:1000,h:540,speechProvider:p.id,speechModel:"tts-future",speechLayout:3});render();}',saved)
                    assert page.evaluate("providerChatModels('custom-api')")==saved['chat_models']
                    options=page.locator('[data-speech="speechModel"] option').evaluate_all('(opts)=>opts.map(o=>o.value)')
                    assert set(options)==set(saved['audio_models']),options
                    page.screenshot(path=str(ROOT/'_verification/custom-models-canvas-v01015.png'))
                    assert not errors,errors
                    if desktop:
                        desktop.terminate();desktop.wait(timeout=10)
                        time.sleep(2)  # WebView2 releases its profile after the host exits.
                    else:browser.close()
                print('PASS: four categories, reclassification, arbitrary IDs, unlisted preservation, HTTP save/reload, failed fetch preservation, no JS errors')
            finally:
                if 'desktop' in locals() and desktop and desktop.poll() is None:
                    desktop.terminate();desktop.wait(timeout=10);time.sleep(2)
                proc.terminate();proc.wait(timeout=10)
    fixture.shutdown();fixture.server_close()

if __name__=='__main__':main()
