"""Real UI/backend integration with an isolated data store and local MiMo fixture."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
import os
import shutil
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import wave

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CHROME = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
requests = []
buf = io.BytesIO()
with wave.open(buf,'wb') as wav:
    wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
    wav.writeframes(b''.join(struct.pack('<h',int(3000*math.sin(2*math.pi*440*i/24000))) for i in range(24000)))
WAV = buf.getvalue()
MP3 = subprocess.run([shutil.which('ffmpeg'),'-hide_banner','-loglevel','error','-f','wav','-i','pipe:0','-codec:a','libmp3lame','-b:a','96k','-f','mp3','pipe:1'],input=WAV,stdout=subprocess.PIPE,check=True).stdout


class Fixture(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        requests.append(body)
        status = 429 if body['messages'][-1]['content'] == 'FAIL429' else 200
        raw = MP3 if body['audio']['format']=='mp3' else WAV
        data = {"choices":[{"message":{"audio":{"data":base64.b64encode(raw).decode()},"final_text_preview":'这是智能优化后的实际台词。' if body['audio'].get('optimize_text_preview') else ''}}]} if status == 200 else {"error":{"message":"quota"}}
        if body['messages'][-1]['content'] in ('FAILINCOMPLETE','CHUNKCOMPLETE'):
            raw=json.dumps(data).encode() if body['messages'][-1]['content']=='CHUNKCOMPLETE' else b'\n'
            self.send_response(200);self.send_header('Transfer-Encoding','chunked');self.end_headers()
            self.wfile.write(hex(len(raw))[2:].encode()+b'\r\n'+raw+b'\r\n');self.wfile.flush();self.close_connection=True
            return
        time.sleep(2.5 if len(requests)==1 else .35)
        self.send_response(status); self.send_header('Content-Type','application/json'); self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    def log_message(self,*args): pass


def main():
    fixture = ThreadingHTTPServer(('127.0.0.1',0),Fixture)
    threading.Thread(target=fixture.serve_forever,daemon=True).start()
    with tempfile.TemporaryDirectory(prefix='myridtv-speech-') as temp:
        env = {**os.environ, 'MYRIDTV_USER_DATA_DIR':temp, 'MYRIDTV_ASSETS_DIR':str(Path(temp)/'assets')}
        port = 3229
        base = f'http://127.0.0.1:{port}'
        log = open(Path(temp)/'runtime.log','w',encoding='utf-8')
        proc = subprocess.Popen([sys.executable,'-B','-c',f'import rh_official_proxy as p; p.ThreadingHTTPServer(("127.0.0.1",{port}),p.Handler).serve_forever()'], cwd=ROOT,env=env,stdout=log,stderr=log)
        def api(path,payload=None,method=None):
            data=None if payload is None else json.dumps(payload).encode()
            req=urllib.request.Request(base+path,data=data,method=method or ('GET' if data is None else 'POST'),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=10) as r: return json.loads(r.read())
        try:
            for _ in range(80):
                try: api('/health'); break
                except Exception: time.sleep(.2)
            else: raise RuntimeError('Test server failed: '+(Path(temp)/'runtime.log').read_text())
            providers = api('/api/providers')['providers']
            assert any(p['id']=='mimo' and len(p['audio_models'])==3 for p in providers)
            canvas = api('/api/canvases',{'title':'MiMo 语音首版验证','kind':'smart'})['canvas']
            cid=canvas['id']
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=CHROME,headless=True)
                page=browser.new_page(viewport={'width':1440,'height':960},accept_downloads=True)
                def choose(field,value):
                    page.locator(f'[data-speech-picker="{field}"]').click()
                    index=page.locator(f'select[data-speech="{field}"]').evaluate('(el,value)=>Array.from(el.options).findIndex(o=>o.value===value)',value)
                    assert index>=0
                    page.locator(f'.speech-picker-menu [data-speech-option="{index}"]').click()
                    assert page.locator(f'select[data-speech="{field}"]').input_value()==value
                    assert page.locator('.speech-picker-menu').count()==0
                errors=[]
                page.on('pageerror',lambda err:errors.append(str(err)))
                page.route('**/static/app_config.json*',lambda route:route.fulfill(json={'proxy':{'base_url':base}}))
                page.goto(base+'/static/api-settings.html')
                page.locator('.provider-card[data-provider-id="mimo"]').wait_for()
                page.locator('.provider-card[data-provider-id="mimo"]').click()
                page.locator('[data-model-tab="audio"]').click()
                assert page.locator('#audioModelList .mod-row').count()==3
                assert page.locator('[data-kind=audio] .muted-note').count()==0
                page.locator('#audioModelList .model-alias-input').first.fill('音色设计验证')
                page.locator('#saveModelsBtn').click()
                page.wait_for_function("document.getElementById('saveModelsBtn').textContent.includes('已保存')")
                page.reload()
                page.locator('.provider-card[data-provider-id="mimo"]').click()
                page.locator('[data-model-tab="audio"]').click()
                assert page.locator('#audioModelList .model-alias-input').first.input_value()=='音色设计验证'
                assert api('/api/providers')['providers'][-1]['image_models']==[]
                print('PASS API audio models save and reload independently of image/chat/video')
                page.screenshot(path=str(ROOT/'verification-speech-settings-v0814.png'),full_page=True)
                page.goto(base+f'/static/smart-canvas.html?id={cid}')
                page.wait_for_function("typeof CanvasSpeech === 'object' && CanvasSpeech.providers().length > 0")
                page.locator('#canvasAddToggle').click()
                assert page.locator('[data-create-type="script"]').count()==0
                assert page.locator('.create-menu-grid > button').evaluate_all('(els)=>els.slice(0,2).map(el=>el.dataset.createType)')==['image','speech']
                assert page.locator('[data-create-type="speech"] .create-card-icon').evaluate('el=>getComputedStyle(el).color')=='rgb(245, 158, 11)'
                page.screenshot(path=str(ROOT/'verification-speech-menu-v0814.png'))
                page.locator('[data-create-type="speech"]').click()
                card=page.locator('.speech-smart-node')
                bounds=card.bounding_box()
                assert bounds['width'] > bounds['height'] * 1.5
                assert not page.locator('#composer').evaluate("el=>el.classList.contains('open')")
                assert page.locator('[data-speech-settings]').count()==0
                assert page.locator('.speech-note').count()==0
                assert page.locator('[data-speech=speechTextSource]').count()==0
                assert page.locator('[data-speech=speechStyleSource]').count()==0
                position=page.evaluate("nodes.find(n=>n.type==='smart-speech').x")
                style=page.locator('[data-speech="speechStyle"]')
                page.evaluate("()=>{const i=nodes.findIndex(n=>n.type==='smart-speech');nodes[i]=structuredClone(nodes[i]);}")
                assert style.evaluate("el=>getComputedStyle(el).fontSize")=='15px'
                style.click()
                assert style.evaluate('(el)=>document.activeElement===el'), 'Click stole textarea focus'
                page.keyboard.insert_text('沉稳的年轻男性')
                script=page.locator('[data-speech="speechText"]')
                assert script.evaluate("el=>getComputedStyle(el).fontSize")=='15px'
                script.click()
                assert script.evaluate('(el)=>document.activeElement===el'), 'Click stole script focus'
                page.keyboard.insert_text('你好，欢迎来到无限画布。')
                page.keyboard.press('End')
                page.keyboard.type('!')
                page.keyboard.press('Backspace')
                assert script.input_value()=='你好，欢迎来到无限画布。'
                assert page.evaluate("nodes.find(n=>n.type==='smart-speech').speechText")=='你好，欢迎来到无限画布。'
                assert page.evaluate("nodes.find(n=>n.type==='smart-speech').x")==position
                mode=page.locator('[data-speech-picker="speechModel"]')
                mode.click()
                page.keyboard.press('ArrowDown')
                page.keyboard.press('Enter')
                assert page.locator('[data-speech="speechVoice"]').count()==1
                choose('speechModel','mimo-v2.5-tts-voicedesign')
                assert not page.locator('#composer').evaluate("el=>el.classList.contains('open')")
                assert page.locator('.speech-card select:visible').count()==0
                for field in ['speechProvider','speechModel','speechFormat','speechOptimize','speechSpeed','speechEmotion','speechDialect']:
                    trigger=page.locator(f'[data-speech-picker="{field}"]')
                    assert trigger.evaluate("el=>getComputedStyle(el).fontSize")=='11px'
                    assert trigger.evaluate("el=>getComputedStyle(el).borderTopWidth")=='1px'
                    assert trigger.evaluate("el=>getComputedStyle(el).borderRadius")=='8px'
                    assert trigger.locator('svg').evaluate("el=>getComputedStyle(el).width")=='13px'
                    assert trigger.locator('span').bounding_box()['width']>10
                    trigger.click()
                    assert trigger.get_attribute('aria-expanded')=='true'
                    menu=page.locator('.speech-picker-menu')
                    bounds=menu.bounding_box()
                    assert bounds['x']>=0 and bounds['y']>=0 and bounds['y']+bounds['height']<=960
                    if field=='speechEmotion': page.screenshot(path=str(ROOT/'verification-speech-dropdown-v0814.png'))
                    page.keyboard.press('Escape')
                    assert trigger.evaluate('(el)=>document.activeElement===el')
                    assert menu.count()==0
                page.locator('[data-speech-picker="speechFormat"]').click()
                page.locator('.speech-heading').click()
                assert page.locator('.speech-picker-menu').count()==0
                print('PASS matching custom menus, visible option clicks, keyboard selection/Escape, outside dismissal and viewport bounds')
                # Existing portrait nodes migrate; the title remains a drag handle.
                page.evaluate("()=>{const n=nodes.find(n=>n.type==='smart-speech');n.w=480;n.h=660;delete n.speechLayout;render();fitAllNodesViewport();}")
                assert page.evaluate("nodes.find(n=>n.type==='smart-speech').w")==1000
                assert page.evaluate("nodes.find(n=>n.type==='smart-speech').h")==540
                heading=page.locator('.speech-heading').bounding_box()
                before=page.evaluate("nodes.find(n=>n.type==='smart-speech').x")
                page.mouse.move(heading['x']+40,heading['y']+10)
                page.mouse.down()
                page.mouse.move(heading['x']+80,heading['y']+30,steps=8)
                page.mouse.up()
                assert page.evaluate("nodes.find(n=>n.type==='smart-speech').x")>before+20
                assert not page.locator('#composer').evaluate("el=>el.classList.contains('open')")
                print('PASS legacy portrait migration and heading drag without opening composer')
                page.locator('[data-speech-run]').click()
                page.wait_for_function("document.querySelector('.speech-status')?.textContent.includes('尚未配置')")
                assert requests==[]
                print('PASS missing key is actionable and never sends an upstream request')
                page.wait_for_timeout(700)
                assert page.evaluate('saveCanvas()'), errors
                stored=api('/api/canvases/'+cid)['canvas']
                assert any(n.get('type')=='smart-speech' for n in stored['nodes']), [(n.get('id'),n.get('type')) for n in stored['nodes']]
                fixture_provider={'id':'fixture','name':'MiMo 本地测试','protocol':'openai','base_url':f'http://127.0.0.1:{fixture.server_port}/v1','audio_models':['mimo-v2.5-tts-voicedesign','mimo-v2.5-tts','mimo-v2.5-tts-voiceclone'],'enabled':True,'api_key':'mock-only'}
                api('/api/providers', providers+[fixture_provider],method='PUT')
                page.reload()
                page.wait_for_function("CanvasSpeech.providers().some(p=>p.id==='fixture') && nodes.some(n=>n.type==='smart-speech')")
                choose('speechProvider','fixture')
                console=browser.new_page(viewport={'width':1440,'height':1000})
                console.route('**/static/app_config.json*',lambda route:route.fulfill(json={'proxy':{'base_url':base}}))
                console.on('pageerror',lambda err:errors.append(str(err)))
                console.goto(base+'/static/index.html')
                console.locator('#dock-console-btn').click()
                page.locator('[data-speech-run]').click()
                task_id=page.evaluate('canvas.logs[0].taskId')
                assert page.evaluate('canvas.logs[0].status')=='running'
                for _ in range(25):
                    running=next((t for t in api('/api/task-console')['tasks'] if t['task_id']==task_id),None)
                    if running:break
                    time.sleep(.04)
                assert running and running['status']=='running' and running['kind']=='语音' and running['platform']=='MiMo 本地测试'
                console.evaluate('tcRefresh()')
                console.wait_for_function('(id)=>tcData?.tasks.some(t=>t.task_id===id && t.status==="running")',arg=task_id)
                assert console.locator('.tc-item').filter(has_text='语音').count()>=1
                page.locator('#smartLogToggle').click()
                assert '运行中' in page.locator('#smartLogList .log-item').first.inner_text()
                page.locator('#smartLogModal button[onclick="closeSmartCanvasLog()"]').click()
                console.screenshot(path=str(ROOT/'verification-speech-console-running-v0814.png'))
                page.evaluate("()=>{const i=nodes.findIndex(n=>n.type==='smart-speech');nodes[i]=structuredClone(nodes[i]);}")
                page.wait_for_function("!!document.querySelector('.speech-output audio')")
                assert requests[-1]['messages']==[{'role':'user','content':'沉稳的年轻男性'},{'role':'assistant','content':'你好，欢迎来到无限画布。'}]
                assert requests[-1]['audio']=={'format':'wav','optimize_text_preview':False}
                player=page.locator('.speech-output audio')
                page.wait_for_function("document.querySelector('.speech-output audio').readyState >= 1")
                assert player.evaluate('(el)=>el.duration')==1
                page.locator('.speech-output [data-audio-toggle]').click()
                page.wait_for_function("!document.querySelector('.speech-output audio').paused")
                assert page.locator('.speech-output [data-audio-toggle]').evaluate("el=>{const a=el.getBoundingClientRect(),b=el.closest('[data-audio-player]').getBoundingClientRect();return a.top>=b.top && a.bottom<=b.bottom;}")
                with page.expect_download() as download:
                    page.locator('.speech-download').click()
                assert Path(download.value.path()).read_bytes()==WAV
                print('PASS design request, WAV localization, player starts and downloaded bytes match')
                output=page.evaluate("nodes.find(n=>n.speechTaskId===canvas.logs[0].taskId)")
                assert output and output['title']=='音频' and output['images'][0]['kind']=='audio'
                assert output['images'][0]['url']==page.locator('.speech-output audio').get_attribute('src')
                assert '/audios/' in output['images'][0]['url'] and Path(output['images'][0]['local_path']).parent.name=='audios'
                assert Path(output['images'][0]['local_path']).read_bytes()==WAV
                assert page.evaluate('(out)=>canvas.connections.some(c=>c.from===out.speechSourceId && c.to===out.id && c.kind==="input")',output)
                assert page.locator(f'.image-node[data-id="{output["id"]}"] audio').count()==1
                assert page.evaluate('(id)=>canvas.logs.filter(log=>log.taskId===id).length',task_id)==1
                assert page.evaluate('canvas.logs[0].status')=='success'
                snapshot=api('/api/task-console');task=next(t for t in snapshot['tasks'] if t['task_id']==task_id)
                assert task['status']=='succeeded' and task['output_audios']==1 and task['output_images']==0 and task['output_videos']==0
                assert snapshot['stats']['today_output_audios']==1 and snapshot['stats']['today_total_media']['audio']==1
                page.locator('#smartLogToggle').click()
                assert page.locator('#smartLogList .log-item').first.locator('audio').count()==1
                log_player=page.locator('#smartLogList .log-item').first
                assert log_player.locator('[data-audio-toggle]').is_visible()
                page.wait_for_function("document.querySelector('#smartLogList audio').readyState>=1")
                log_player.locator('[data-audio-toggle]').click()
                page.wait_for_function("!document.querySelector('#smartLogList audio').paused")
                log_player.locator('[data-audio-toggle]').click()
                page.screenshot(path=str(ROOT/'verification-speech-log-v0814.png'))
                page.locator('#smartLogModal button[onclick="closeSmartCanvasLog()"]').click()
                console.evaluate('tcRefresh()')
                console.wait_for_function('(id)=>tcData?.tasks.some(t=>t.task_id===id && t.status==="succeeded")',arg=task_id)
                assert '音频' in console.locator('#tc-stats').inner_text()
                console.screenshot(path=str(ROOT/'verification-speech-console-v0814.png'))
                print('PASS running/success canvas logs and task console, audio statistics, output node/link and audios directory')
                page.screenshot(path=str(ROOT/'verification-speech-design-v0814.png'),full_page=True)
                # Save/reload preserves fields and the real playable result.
                page.wait_for_timeout(1500)
                page.reload()
                assert page.locator('[data-speech="speechText"]').input_value()=='你好，欢迎来到无限画布。'
                assert page.locator('.speech-output audio').count()==1
                assert page.locator(f'.image-node[data-id="{output["id"]}"] audio').count()==1
                assert page.evaluate('(out)=>canvas.connections.some(c=>c.from===out.speechSourceId && c.to===out.id)',output)
                # Create and physically connect a script node through the canvas ports.
                page.locator('#canvasAddToggle').click()
                page.locator('[data-create-type="prompt"]').click()
                page.evaluate("""() => {const source=nodes.find(n=>n.type==='smart-prompt'); const target=nodes.find(n=>n.type==='smart-speech'); source.x=target.x-700; source.y=target.y; source.w=450; source.text='这是从上游节点读取的台词。'; render(); fitAllNodesViewport();} """)
                source=page.locator('.prompt-smart-node .node-port[data-port="out"]')
                target=page.locator('.speech-smart-node .node-port[data-port="in"]')
                a=source.bounding_box(); b=target.bounding_box()
                page.mouse.move(a['x']+a['width']/2,a['y']+a['height']/2); page.mouse.down()
                page.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2,steps=15); page.mouse.up()
                page.wait_for_function("document.querySelector('[data-speech=speechTextSource]').options.length > 1")
                source_id=page.locator('[data-speech="speechTextSource"] option').last.get_attribute('value')
                choose('speechTextSource',source_id)
                assert page.locator('[data-speech="speechText"]').input_value()=='这是从上游节点读取的台词。'
                assert page.locator('[data-speech="speechText"]').get_attribute('readonly') is not None
                choose('speechModel','mimo-v2.5-tts')
                choose('speechVoice','茉莉')
                page.locator('[data-speech-run]').click()
                page.wait_for_function("document.querySelector('.speech-status').textContent.includes('已生成')")
                assert requests[-1]['audio']=={'format':'wav','voice':'茉莉'}
                assert requests[-1]['messages'][-1]['content']=='这是从上游节点读取的台词。'
                print('PASS actual port connection, upstream script selection and preset voice request')
                page.screenshot(path=str(ROOT/'verification-speech-preset-v0814.png'),full_page=True)
                choose('speechTextSource','')
                # MP3 is requested from the provider, played and downloaded as MP3.
                choose('speechFormat','mp3')
                choose('speechSpeed','slow')
                choose('speechEmotion','tender')
                choose('speechDialect','cantonese')
                choose('speechSinging','true')
                page.locator('[data-speech="speechText"]').fill('这是一段MP3测试台词。')
                page.locator('[data-speech-run]').click()
                page.wait_for_function("document.querySelector('.speech-download')?.textContent.includes('MP3')")
                assert requests[-1]['audio']=={'format':'mp3','voice':'茉莉'}
                assert '语速缓慢；温柔；粤语' in requests[-1]['messages'][0]['content']
                assert requests[-1]['messages'][-1]['content']=='(唱歌)这是一段MP3测试台词。'
                page.wait_for_function("document.querySelector('.speech-output audio').readyState>=1")
                assert .9 < page.locator('.speech-output audio').evaluate('el=>el.duration') < 1.3
                page.locator('.speech-output [data-audio-toggle]').click()
                page.wait_for_function("!document.querySelector('.speech-output audio').paused")
                with page.expect_download() as mp3_download:
                    page.locator('.speech-download').click()
                assert Path(mp3_download.value.path()).read_bytes()==MP3
                assert mp3_download.value.suggested_filename.endswith('.mp3')
                print('PASS MP3 bytes/player/download and style/singing controls map to documented messages')
                # Tags are inserted at the script cursor, never into the voice description.
                script=page.locator('[data-speech="speechText"]')
                script.click();page.keyboard.press('End')
                page.locator('[data-speech-tag="轻笑"]').click()
                assert script.input_value().endswith('[轻笑]')
                choose('speechModel','mimo-v2.5-tts-voicedesign')
                choose('speechOptimize','true')
                page.locator('[data-speech="speechText"]').fill('')
                page.locator('[data-speech-run]').click()
                page.wait_for_function("!!document.querySelector('.speech-preview')")
                assert requests[-1]['audio']['optimize_text_preview'] is True
                assert len(requests[-1]['messages'])==1 and requests[-1]['messages'][0]['role']=='user'
                assert page.locator('.speech-preview').text_content().endswith('这是智能优化后的实际台词。')
                print('PASS optimize accepts empty script and exposes actual returned text')
                # Clone sample is uploaded to this canvas and stays a small URL in the node.
                choose('speechModel','mimo-v2.5-tts-voiceclone')
                page.locator('[data-speech-file]').set_input_files({'name':'reference.wav','mimeType':'audio/wav','buffer':WAV})
                page.wait_for_function("nodes.find(n=>n.type==='smart-speech').speechReference?.url")
                page.locator('[data-speech="speechText"]').fill('这是复刻音色。')
                page.locator('[data-speech-run]').click()
                page.wait_for_function("document.querySelector('.speech-status').textContent==='已生成'")
                assert requests[-1]['model']=='mimo-v2.5-tts-voiceclone'
                assert requests[-1]['audio']['voice']=='data:audio/wav;base64,'+base64.b64encode(WAV).decode()
                assert requests[-1]['messages'][-1]['content']=='这是复刻音色。'
                assert page.evaluate("JSON.stringify(nodes.find(n=>n.type==='smart-speech')).length")<15000
                page.wait_for_timeout(700);page.evaluate('saveCanvas()');page.reload()
                assert page.locator('.speech-reference > span').text_content()=='reference.wav'
                assert page.locator('[data-speech="speechFormat"]').input_value()=='mp3'
                assert page.locator('[data-speech="speechSpeed"]').input_value()=='slow'
                assert page.locator('[data-speech=speechTextSource]').count()==1
                page.screenshot(path=str(ROOT/'verification-speech-clone-v0814.png'),full_page=True)
                print('PASS clone uploads local sample, sends MIME/base64 and reloads sample and controls')
                previous=page.locator('.speech-output audio').get_attribute('src')
                count=len(requests)
                page.locator('[data-speech="speechText"]').fill('FAILINCOMPLETE')
                page.locator('[data-speech-run]').click()
                page.wait_for_function("document.querySelector('.speech-status')?.textContent.includes('响应中断或内容不完整')")
                assert 'IncompleteRead' not in page.locator('.speech-status').inner_text()
                assert not page.locator('[data-speech-run]').is_disabled()
                assert page.locator('.speech-output audio').get_attribute('src')==previous
                assert len(requests)==count+1, 'Unexpected automatic paid retry'
                page.locator('[data-speech="speechText"]').fill('CHUNKCOMPLETE')
                page.locator('[data-speech-run]').click()
                page.wait_for_function("previous=>document.querySelector('.speech-output audio')?.getAttribute('src')!==previous",arg=previous)
                page.wait_for_function("document.querySelector('.speech-output audio').readyState >= 1")
                assert page.locator('.speech-output audio').evaluate('el=>el.duration')>1
                print('PASS interrupted HTTP chunk response is actionable, preserves audio and never retries; complete JSON without final chunk recovers')
                page.locator('[data-speech="speechText"]').fill('FAIL429')
                page.locator('[data-speech-run]').click()
                page.wait_for_function("document.querySelector('.speech-status').textContent.includes('额度不足')")
                assert not page.locator('[data-speech-run]').is_disabled()
                assert page.locator('.speech-output audio').count()==1
                assert not errors, errors
                assert page.evaluate('canvas.logs[0].status')=='failed'
                failed_id=page.evaluate('canvas.logs[0].taskId')
                snapshot=api('/api/task-console');failed=next(t for t in snapshot['tasks'] if t['task_id']==failed_id)
                assert failed['status']=='failed' and '额度不足' in failed['error']
                assert len(snapshot['tasks'])==len(requests)
                assert page.evaluate("nodes.filter(n=>n.speechTaskId).length")==len([t for t in snapshot['tasks'] if t['status']=='succeeded'])
                page.wait_for_timeout(1000);page.evaluate('saveCanvas()')
                console.evaluate('tcRefresh()');console.wait_for_function('(id)=>tcData?.tasks.some(t=>t.task_id===id && t.status==="failed")',arg=failed_id)
                console.locator('#tc-tab-stats').click()
                assert '音频' in console.locator('#tc-a-media').inner_text()
                assert int(console.locator('#tc-a-outputs').inner_text())==snapshot['stats']['today_output_audios']
                console.screenshot(path=str(ROOT/'verification-speech-stats-v0814.png'))
                print('PASS failures logged once, output creation only on success, console audio statistics and no page errors')
                browser.close()
            before=api('/api/task-console')['tasks']
            command=proc.args;proc.terminate();proc.wait(timeout=10)
            proc=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=log)
            for _ in range(80):
                try:after=api('/api/task-console')['tasks'];break
                except Exception:time.sleep(.2)
            else:raise RuntimeError('Restart failed')
            assert {t['task_id']:t['status'] for t in before}=={t['task_id']:t['status'] for t in after}
            print('PASS task console records persist across backend restart')
            print('PASS all speech integration checks; MiMo remote API was not called')
        finally:
            proc.terminate();proc.wait(timeout=10);log.close();fixture.shutdown();fixture.server_close()


if __name__=='__main__':main()
