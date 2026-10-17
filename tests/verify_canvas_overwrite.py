"""Verify real disk archival and GUI overwrite in a private application runtime."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import struct
import zlib
from urllib.parse import unquote
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '_verification/overwrite'


def fixture_png(color):
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    pixels=bytes.fromhex(color.lstrip('#'))*64
    raw=(b'\x00'+pixels)*48
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',64,48,8,2,0,0,0))+
            chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='myrid-overwrite-') as tmp:
        runtime = Path(tmp)
        assets = runtime / 'assets'
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0))
            port = probe.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        env = {**os.environ,'MYRIDTV_TEST_PORT':str(port),'MYRIDTV_TEST_DATA_DIR':str(runtime/'userdata'),
               'MYRIDTV_ASSETS_DIR':str(assets),'PYTHONUTF8':'1'}
        with (OUT/'server.log').open('w',encoding='utf-8') as log:
            server = subprocess.Popen([sys.executable,str(ROOT/'tests/launch_test_instance.py')],cwd=ROOT,env=env,stdout=log,stderr=log)
            try:
                with sync_playwright() as p:
                    request = p.request.new_context(base_url=base)
                    for _ in range(60):
                        try:
                            if request.get('/health',timeout=500).ok:
                                break
                        except Exception:
                            pass
                        time.sleep(.2)
                    else:
                        raise RuntimeError('Server not ready')
                    canvas = request.post('/api/canvases',data={'name':'Overwrite verification','nodes':[],'connections':[]}).json()['canvas']
                    def upload(name,color):
                        path=runtime/name
                        path.write_bytes(fixture_png(color))
                        result=request.post('/api/ai/upload?scope=canvas&canvas_id='+canvas['id'],multipart={
                            'files':{'name':name,'mimeType':'image/png','buffer':path.read_bytes()}})
                        assert result.ok,result.text()
                        return result.json()['files'][0]
                    old=upload('old.png','#6288c9'); new=upload('new.png','#cd7055'); third=upload('third.png','#65a878'); fourth=upload('fourth.png','#7b61b0')
                    def local(url):
                        return assets/unquote(url.split('/assets/',1)[1])
                    executable=os.environ.get('MYRIDTV_TEST_BROWSER')
                    if not executable and not Path(p.chromium.executable_path).exists():
                        candidates=sorted((Path(os.environ.get('LOCALAPPDATA',''))/'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'))
                        executable=str(candidates[-1]) if candidates else None
                    browser=p.chromium.launch(headless=True,**({'executable_path':executable} if executable else {}))
                    page=browser.new_page(viewport={'width':1440,'height':1000})
                    page.route('**/static/app_config.json*',lambda r:r.fulfill(json={'proxy':{'base_url':base}}))
                    page.goto(base+'/smart-canvas.html?id='+canvas['id'],wait_until='networkidle')
                    page.evaluate("""({old,next}) => {
                        const media=item=>({...item,natural_w:64,natural_h:48,kind:'image'});
                        nodes=[{id:'target',type:'smart-image',x:150,y:150,w:320,h:240,cardSize:{width:320,height:240},scale:1,
                            __origin:'mcp',title:'Original node',images:[media(old)],promptDraftHtml:'Replace fixture',
                            runSettings:{...settings,engine:'api',apiKind:'image',count:1}},
                            {id:'reference',type:'smart-image',x:800,y:150,scale:1,images:[media(old)]}];
                        fixtureProviderCalls=0;fixtureProviderRefs=[];
                        smartGeneratedOutputItems=async(items,kind)=>items.map(item=>({...media(typeof item==='string'?{url:item}:item),kind,generatedResult:true}));
                        CanvasGenerationRunner.configure({ensureCustomComfyWorkflowReady:async()=>{},
                            buildPromptRequest:()=>({prompt:'Replace fixture',displayPrompt:'Replace fixture',refs:[{url:old.url,kind:'image'}]}),
                            runApiGeneration:async(prompt,refs)=>{fixtureProviderCalls++;fixtureProviderRefs=refs;return {taskIds:['fixture-task']};},
                            resumeSmartPendingNode:async n=>finalizeSmartPendingTask(n,'fixture-task',[next],'image'),
                            addSmartGenerationLog:()=>{}});
                        render();Object.assign(viewport,{x:0,y:0,scale:1});applyViewport();
                    }""",{'old':old,'next':new})
                    page.locator('[data-id="target"] img').first.click()
                    page.locator('#runBtn').click()
                    page.wait_for_function("url => nodes.find(n=>n.id==='target')?.images[0]?.url===url",arg=new['url'])
                    state=page.evaluate("() => ({ids:nodes.map(n=>n.id),url:nodes.find(n=>n.id==='target').images[0].url,reference:nodes.find(n=>n.id==='reference').images[0].url})")
                    assert sorted(state['ids'])==['reference','target'],state
                    assert state['url']==new['url'] and '/history/' in state['reference'],state
                    assert page.evaluate('fixtureProviderRefs[0].url')==state['reference']
                    assert not local(old['url']).exists() and local(state['reference']).exists()
                    assert local(new['url']).exists()
                    # The alternative result-replacement path must also archive only on disk.
                    await_result=page.evaluate("""async next => {
                        await replaceOutputsToNodeWithHistory(nodes.find(n=>n.id==='target'),[next],'image',null,{skipShift:true});render();
                        return {ids:nodes.map(n=>n.id),url:nodes.find(n=>n.id==='target').images[0].url};
                    }""",third)
                    assert sorted(await_result['ids'])==['reference','target'] and await_result['url']==third['url'],await_result
                    assert not local(new['url']).exists() and local(third['url']).exists()
                    assert len(list(assets.rglob('history/**/new.png')))==1
                    page.screenshot(path=str(OUT/'latest-only.png'))
                    # A failed generation keeps the last available image on the original node.
                    page.evaluate("CanvasGenerationRunner.configure({runApiGeneration:async()=>{fixtureProviderCalls++;throw new Error('fixture generation failure')}})")
                    page.locator('#runBtn').click()
                    page.wait_for_function("nodes.find(n=>n.id==='target').runError?.includes('fixture generation failure')")
                    retained=page.evaluate("nodes.find(n=>n.id==='target').images[0].url")
                    assert '/history/' in retained and local(retained).exists()
                    assert sorted(page.evaluate('nodes.map(n=>n.id)'))==['reference','target']
                    await_result=page.evaluate("""async next => {
                        await replaceOutputsToNodeWithHistory(nodes.find(n=>n.id==='target'),[next],'image',null,{skipShift:true});render();
                        return nodes.find(n=>n.id==='target').images[0].url;
                    }""",fourth)
                    assert await_result==fourth['url']
                    # Disk failure must stop before provider submission and preserve the latest image.
                    page.route('**/api/move-to-history',lambda r:r.fulfill(status=503,json={'detail':'fixture archive failure'}))
                    calls=page.evaluate('fixtureProviderCalls')
                    page.locator('#runBtn').click()
                    page.wait_for_function("nodes.find(n=>n.id==='target').runError?.includes('归档失败')")
                    assert page.evaluate('fixtureProviderCalls')==calls
                    assert page.evaluate("nodes.find(n=>n.id==='target').images[0].url")==fourth['url']
                    assert local(fourth['url']).exists()
                    page.evaluate('saveCanvas()')
                    page.reload(wait_until='networkidle')
                    page.wait_for_function("url => nodes.find(n=>n.id==='target')?.images[0]?.url===url",arg=fourth['url'])
                    assert sorted(page.evaluate('nodes.map(n=>n.id)'))==['reference','target']
                    # No origin, import title or UI refresh may implicitly create a group.
                    page.evaluate("""url => {
                        const origins=['mcp','mcp_update','agent_tool_generation','mcp_flow','user_manual'];
                        for(const [i,origin] of origins.entries()) nodes.push({id:'multi_'+i,type:'smart-image',
                            title:'Images',__origin:origin,x:100+i*250,y:500,scale:1,
                            images:[{url,kind:'image'},{url:url+'?second',kind:'image'}]});
                        render();render();
                    }""",fourth['url'])
                    assert page.evaluate("nodes.filter(n=>n.type==='smart-group').length")==0
                    assert page.evaluate("nodes.filter(n=>n.id.startsWith('multi_')).every(n=>n.images.length===2)")
                    page.evaluate('saveCanvas()')
                    page.reload(wait_until='networkidle')
                    page.wait_for_function("nodes.some(n=>n.id==='multi_4')")
                    assert page.evaluate("nodes.filter(n=>n.type==='smart-group').length")==0
                    assert page.evaluate("nodes.filter(n=>n.id.startsWith('multi_')).length")==5
                    imported=page.evaluate("""url => {
                        const n=CanvasImageNodeMediaController.appendImages([{url,kind:'image'},{url:url+'?import',kind:'image'}],
                            '',{forceNew:true,point:{x:100,y:900}});
                        return {id:n.id,type:n.type,count:n.images.length,groups:nodes.filter(n=>n.type==='smart-group').length};
                    }""",fourth['url'])
                    assert imported['type']=='smart-image' and imported['count']==2 and imported['groups']==0,imported
                    # Explicit manual grouping remains available and persists.
                    page.evaluate("selectedIds=['multi_0','multi_1'];selectedId='';handleSmartNodeToolAction('group')")
                    group=page.evaluate("nodes.find(n=>n.type==='smart-group')")
                    assert group and set(group['memberIds'])=={'multi_0','multi_1'}
                    page.evaluate('saveCanvas()')
                    page.reload(wait_until='networkidle')
                    page.wait_for_function("id=>nodes.some(n=>n.id===id)",arg=group['id'])
                    assert page.evaluate("id=>nodes.find(n=>n.id===id).memberIds.length",group['id'])==2
                    page.screenshot(path=str(OUT/'no-auto-group.png'))
                    (OUT/'results.json').write_text(json.dumps({'passed':True,'nodeIds':state['ids'],'oldFileArchived':True,
                        'originalNodeOverwritten':True,'noNewGroup':True,'sharedReferenceKept':True,'alternativePathPassed':True,
                        'archiveFailurePreservesImage':True,'generationFailureKeepsLastImage':True,'reloadKeepsLatest':True,
                        'allAgentOriginsStayUngrouped':True,'legacyImportStaysUngrouped':True,'multiUploadStaysUngrouped':True,
                        'manualGroupingPersists':True},indent=2),encoding='utf-8')
                    browser.close()
                    print('PASS - overwrite, disk history, failure safety, no automatic groups across origins/import/reload, manual grouping')
            finally:
                server.terminate();server.wait(timeout=10)


if __name__=='__main__':
    main()
