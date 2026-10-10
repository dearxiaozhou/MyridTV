"""Real browser/API regression: an open canvas must not resurrect removed media."""
import copy, json, os, time
from pathlib import Path
from e2e_canvas_save_recovery import api, configure_canvas_page, CHROME, BASE
from playwright.sync_api import sync_playwright

OUT=Path(__file__).resolve().parents[1]/'_verification'/('canvas-sync-v01011-live-results.json' if os.environ.get('MYRIDTV_SYNC_FRONTEND_ONLY')=='1' else 'canvas-sync-v01011-results.json')
checks=[]
LIVE_FRONTEND=os.environ.get('MYRIDTV_SYNC_FRONTEND_ONLY')=='1'
def check(label, condition):
    assert condition, label
    checks.append(label)
    print('PASS - '+label, flush=True)
def snapshot(cid): return api('GET','/api/canvases/'+cid)['canvas']
def put(cid, canvas):
    payload=copy.deepcopy(canvas)
    payload['base_updated_at']=canvas['updated_at']
    return api('PUT','/api/canvases/'+cid,payload)['canvas']
def images(page): return page.evaluate("nodes.find(n=>n.id==='media').images.map(i=>i.url)")

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=CHROME,headless=True)
    page=browser.new_page(viewport={'width':1440,'height':900})
    errors=[]
    svg='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><rect width="80" height="80" fill="green"/></svg>'
    cv=api('POST','/api/canvases',{'kind':'smart','title':'Sync deletion regression','nodes':[
        {'id':'media','type':'smart-image','x':100,'y':100,'w':280,'h':200,'title':'media','text':'old text','images':[{'url':svg}]},
        {'id':'remove-me','type':'smart-prompt','x':500,'y':100,'w':280,'h':200,'text':'delete me','images':[]}], 'connections':[{'from':'media','to':'remove-me','kind':'input'}]})['canvas']
    cid=cv['id']
    configure_canvas_page(page,cid,errors)
    page.wait_for_function("nodes.length===2")
    # Hold the browser PUT while another API writer deletes media/node/text.
    page.evaluate("() => {clearTimeout(saveTimer); saveTimer=null; clearInterval(canvasMetaPollTimer); canvasMetaPollTimer=null;}")
    injected=[];statuses=[]
    page.on('response',lambda r:statuses.append(r.status) if r.request.method=='PUT' and '/api/canvases/'+cid in r.url else None)
    def conflict(route):
        if route.request.method=='PUT' and not injected:
            current=snapshot(cid)
            current['nodes']=[n for n in current['nodes'] if n['id']!='remove-me']
            current['nodes'][0]['images']=[]
            current['nodes'][0]['text']=''
            if LIVE_FRONTEND:
                current['nodes'][0]['content']=''
                current['deleted']=[{'id':'remove-me','at':int(time.time()*1000),'by':'verification'}]
            current['connections']=[]
            put(cid,current);injected.append(True)
        route.continue_()
    page.route('**/api/canvases/'+cid,conflict)
    page.evaluate("() => {nodes.find(n=>n.id==='media').x=333; scheduleSave();}")
    page.wait_for_timeout(2500)
    page.wait_for_function("nodes.length===1 && nodes[0].images.length===0 && nodes[0].text===''")
    page.wait_for_timeout(1600)
    saved=snapshot(cid)
    check('409 conflict occurred and retry succeeded',409 in statuses and 200 in statuses)
    check('API image deletion survived browser autosave',saved['nodes'][0]['images']==[])
    check('API text clear survived browser autosave',saved['nodes'][0]['text']=='')
    check('Unrelated unsaved local position survived',saved['nodes'][0]['x']==333)
    check('Deleted node and connection stayed deleted',len(saved['nodes'])==1 and saved['connections']==[])
    check('Deletion tombstone persisted' if LIVE_FRONTEND else 'Backend recorded implicit node deletion',any(t['id']=='remove-me' for t in saved['deleted']))
    # The selected node's composer is also in-memory state. Refresh it on remote edits.
    page.evaluate("() => {selectedId='media'; selectedIds=['media']; render();}")
    current=snapshot(cid)
    current['nodes'][0].update({'runPrompt':'API prompt','promptDraftText':'API prompt','promptDraftHtml':'API prompt'})
    remote=put(cid,current)
    page.evaluate('remote => applyMergedServerCanvas(remote)',remote)
    check('Selected composer refreshed from API update',page.locator('#promptInput').inner_text()=='API prompt')
    page.evaluate('scheduleSave()'); page.wait_for_timeout(1200)
    check('Composer did not overwrite API prompt on autosave',snapshot(cid)['nodes'][0]['promptDraftText']=='API prompt')
    # Replace media via API while browser stays open; test WS/meta synchronization.
    page.unroute('**/api/canvases/'+cid,conflict)
    page.evaluate('startCanvasMetaPoll()')
    replacement=svg.replace('green','blue')
    current=snapshot(cid); current['nodes'][0]['images']=[{'url':replacement}]
    put(cid,current)
    page.wait_for_function("url => nodes[0].images.length===1 && nodes[0].images[0].url===url",arg=replacement,timeout=16000)
    page.evaluate('scheduleSave()');page.wait_for_timeout(1500)
    check('Live API replacement was synchronized without old image union',images(page)==[replacement])
    check('Autosave kept only replacement media',snapshot(cid)['nodes'][0]['images'][0]['url']==replacement and len(snapshot(cid)['nodes'][0]['images'])==1)
    page.reload(wait_until='domcontentloaded'); page.wait_for_function("nodes.length===1")
    check('Reload did not restore removed node or image',images(page)==[replacement])
    check('No browser script errors',not errors)
    page.screenshot(path=str(OUT.with_suffix('.png')))
    OUT.parent.mkdir(exist_ok=True,parents=True);OUT.write_text(json.dumps({'base':BASE,'canvas':cid,'checks':checks,'statuses':statuses,'errors':errors},indent=2),encoding='utf-8')
    browser.close()
