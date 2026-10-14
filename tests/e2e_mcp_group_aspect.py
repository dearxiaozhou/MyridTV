"""Persist and reload MCP groups through the real app; never write user canvases."""
import io,json,os,shutil,subprocess,sys,tempfile,time,urllib.request
import urllib.parse
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:3242'
CHROME=r'C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe'

def main():
    with tempfile.TemporaryDirectory(prefix='mcp-aspect-') as temp:
        env={**os.environ,'MYRIDTV_USER_DATA_DIR':temp,'MYRIDTV_ASSETS_DIR':str(Path(temp)/'assets')}
        proc=subprocess.Popen([sys.executable,'-B','-c','import rh_official_proxy as p;p.ThreadingHTTPServer(("127.0.0.1",3242),p.Handler).serve_forever()'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        desktop=None
        def api(path,data=None,method=None):
            req=urllib.request.Request(BASE+path,data=None if data is None else json.dumps(data).encode(),method=method,headers={'Content-Type':'application/json'})
            return json.load(urllib.request.urlopen(req,timeout=20))
        try:
            for _ in range(70):
                try:api('/health');break
                except Exception:time.sleep(.2)
            cid=api('/api/canvases',{'title':'MCP intrinsic aspect regression','kind':'smart'})['canvas']['id']
            source={'id':'source','type':'smart-image','title':'MCP scene','x':100,'y':140,'w':300,'h':169,'cardSize':{'width':260,'height':300},'cardSizing':'media','__origin':'mcp_update','mcpGroupId':'group','images':[{'url':'/assets/land.png','kind':'image','natural_w':3840,'natural_h':2161,'generatedResult':True}]}
            second={**source,'id':'second','x':430,'mcpGroupId':None,'mcpGroupSourceId':'source','__origin':'mcp_output','cardSizing':'spec','images':[{'url':'/assets/portrait.png','kind':'image','metadata':{'width':900,'height':1600},'generatedResult':True}]}
            group={'id':'group','type':'smart-group','title':'MCP scene','x':82,'y':98,'w':650,'h':360,'mcpGroupSourceId':'source','memberIds':['source','second'],'__origin':'mcp'}
            canvas=api('/api/canvases/'+cid)['canvas'];canvas['nodes']=[source,second,group];api('/api/canvases/'+cid,canvas,'PUT')
            with sync_playwright() as pw:
                if '--desktop' in sys.argv:
                    host=Path(temp)/'desktop';host.mkdir();shutil.copy2(ROOT/'MyridTV-Desktop.exe',host/'MyridTV-Desktop.exe')
                    config=host/'_internal/data';config.mkdir(parents=True);(config/'app_config.json').write_text(json.dumps({'proxy':{'port':3242}}))
                    si=subprocess.STARTUPINFO();si.dwFlags=subprocess.STARTF_USESHOWWINDOW;si.wShowWindow=0
                    desktop=subprocess.Popen([str(host/'MyridTV-Desktop.exe')],env={**env,'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS':'--remote-debugging-port=9242','WEBVIEW2_USER_DATA_FOLDER':str(host/'profile')},startupinfo=si)
                    for _ in range(70):
                        try:urllib.request.urlopen('http://127.0.0.1:9242/json/version',timeout=1);break
                        except Exception:time.sleep(.2)
                    browser=pw.chromium.connect_over_cdp('http://127.0.0.1:9242');page=browser.contexts[0].pages[0]
                    page.wait_for_url('**/static/index.html');page.wait_for_load_state('networkidle')
                else:
                    browser=pw.chromium.launch(executable_path=CHROME,headless=True);page=browser.new_page(viewport={'width':1440,'height':1000})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                sizes={'land.png':(3840,2161),'portrait.png':(900,1600),'square.png':(512,512)}
                def media(route):
                    size=sizes[route.request.url.rsplit('/',1)[-1]];buf=io.BytesIO();Image.new('RGB',size,'#587f91').save(buf,format='PNG');route.fulfill(content_type='image/png',body=buf.getvalue())
                page.route('**/assets/*.png',media)
                def info(route):
                    name=urllib.parse.parse_qs(urllib.parse.urlparse(route.request.url).query)['url'][0].rsplit('/',1)[-1]
                    w,h=sizes[name];route.fulfill(content_type='application/json',body=json.dumps({'width':w,'height':h}))
                page.route('**/api/canvas-image-info?*',info)
                url=BASE+'/static/smart-canvas.html?id='+cid
                def verify():
                    page.wait_for_function("nodes.length>=3 && nodes.filter(n=>n.type==='smart-image'&&n.cardSizing!=='manual').every(n=>{const i=n.images[0],s=knownImageNaturalSize(i,false),r=nodeRect(n);return s&&Math.abs(r.width/r.height-s.w/s.h)/(s.w/s.h)<.01&&n.cardSize.width===n.w&&n.cardSize.height===n.h})")
                    assert page.evaluate("nodes.filter(n=>n.type==='smart-group').length")==1
                    assert page.evaluate("nodes.filter(n=>n.type==='smart-image').every(n=>n.images.length===1)")
                    for img in page.locator('.image-node img').all():
                        assert img.evaluate('(el)=>el.complete&&el.naturalWidth>0')
                    page.evaluate('saveCanvas()')
                    saved=api('/api/canvases/'+cid)['canvas']
                    for n in saved['nodes']:
                        if n['type']=='smart-image' and n.get('cardSizing')!='manual':
                            assert n['cardSize']=={'width':n['w'],'height':n['h']},n
                page.goto(url,wait_until='networkidle');verify()
                for _ in range(3):page.reload(wait_until='networkidle');verify()
                # Later MCP output lacks metadata and must join once without shrinking old members.
                before=page.evaluate("nodes.find(n=>n.id==='source').w")
                page.evaluate("nodes.find(n=>n.id==='source').images.push({url:'/assets/square.png',kind:'image',generatedResult:true});render()")
                verify();assert page.evaluate("nodes.find(n=>n.id==='group').memberIds.length")==3
                assert page.evaluate("nodes.find(n=>n.id==='source').w")==before
                page.reload(wait_until='networkidle');verify()
                page.screenshot(path=str(ROOT/'_verification/mcp-group-intrinsic-v01017.png'))
                # Uniform size is an intentional override and must survive late metadata/reload.
                page.evaluate("selectedIds=['source','second'];selectedId='';handleSmartNodeToolAction('same-size')")
                manual=page.evaluate("nodes.filter(n=>['source','second'].includes(n.id)).map(n=>({id:n.id,w:n.w,h:n.h}))")
                page.evaluate('saveCanvas()');page.reload(wait_until='networkidle');verify()
                assert page.evaluate("nodes.filter(n=>['source','second'].includes(n.id)).map(n=>({id:n.id,w:n.w,h:n.h}))")==manual
                assert not errors,errors
                print('PASS: stale card repair, mixed ratios, nested metadata, late output, repeated HTTP save/reload, idempotence, uniform size override, no JS errors')
                if not desktop:browser.close()
        finally:
            if desktop:desktop.terminate();desktop.wait(timeout=10);time.sleep(2)
            proc.terminate();proc.wait(timeout=10)

if __name__=='__main__':main()
