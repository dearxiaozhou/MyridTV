"""Only one public MCP tool; even sequential creation automatically gets DAG layout."""
import concurrent.futures,json,os,sys,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from myridtv_flow_layout import node_size,overlap,AUTOMATIC_LAYOUT_ENABLED
BASE=os.environ.get('MYRIDTV_TEST_BASE','http://127.0.0.1:3261')
ROOT=Path(__file__).resolve().parents[1]
checks=[]
def check(label,ok):
    assert ok,label
    checks.append(label);print('PASS '+label,flush=True)
def api(path,data=None,method=None):
    req=urllib.request.Request(BASE+path,data=None if data is None else json.dumps(data).encode(),method=method,headers={'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(req,timeout=30))
def rpc(name,args):return api('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}})
def call(action,params=None,ok=True,**control):
    response=rpc('canvas_execute',{'action':action,'params':params or {},**control})['result']
    value=json.loads(response['content'][0]['text'])
    if ok:assert not response.get('isError'),value
    else:assert response.get('isError'),value
    return value
def read(cid):return api('/api/canvases/'+cid)['canvas']
def positions(canvas):return {n['id']:(n.get('x'),n.get('y')) for n in canvas['nodes']}

def main():
    listed=api('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/list'})['result']['tools']
    check('exactly one public entrypoint', [t['name'] for t in listed]==['canvas_execute'])
    schema=call('describe',{'action':'create_generation_node'})['params_schema']
    # 2026-10-17:坐标只在自动布局开启时由软件统一计算才隐藏；开关关闭时调用方自行给坐标是契约的一部分。
    hidden={'canvas_id','workflow_id','idempotency_key','expected_updated_at'}
    if AUTOMATIC_LAYOUT_ENABLED:hidden |= {'x','y'}
    check('action schema excludes coordinates and target override',not hidden&set(schema['properties']))
    cid=call('create',{'title':'统一入口：逐个创建三分支'})['canvas_id']
    cv=read(cid);cv['nodes']=[{'id':'manual','type':'smart-prompt','title':'手工节点保留','text':'不要移动','x':40,'y':40,'w':632,'h':388,'layoutLocked':True}]
    api('/api/canvases/'+cid,cv,'PUT');manual=positions(read(cid))['manual']
    def create(label,key,wid=None):
        return call('create_generation_node',{'title':label,'prompt':label+'，清晨窗光下的居民家，明确的构图与细节'},canvas_id=cid,idempotency_key=key,**({'workflow_id':wid} if wid else {}))['node_id']
    parent=create('场景资产','scene')
    branches=[]
    for i in range(1,4):
        shot=create('镜头参考 '+str(i),'shot'+str(i));video=create('视频画面 '+str(i),'video'+str(i))
        call('connect_nodes',{'from_id':parent,'to_id':shot,'kind':'input'},canvas_id=cid)
        call('connect_nodes',{'from_id':shot,'to_id':video,'kind':'input'},canvas_id=cid)
        branches.append((shot,video))
    cv=read(cid);flow=[n for n in cv['nodes'] if n['id']!='manual'];byid={n['id']:n for n in cv['nodes']}
    check('sequential creation is enrolled without workflow/layout calls',all(n['flowLayout']['workflowId']=='external:'+cid and n['flowLayout']['layout']=='tree_lr' for n in flow))
    check('all three branches go left to right',all(byid[parent]['x']+node_size(byid[parent])[0]<=byid[s]['x'] and byid[s]['x']+node_size(byid[s])[0]<=byid[v]['x'] for s,v in branches))
    check('automatic node geometry has no overlaps',all(not overlap((a['x'],a['y'],*node_size(a)),(b['x'],b['y'],*node_size(b))) for i,a in enumerate(cv['nodes']) for b in cv['nodes'][i+1:]))
    check('manual node unchanged',positions(cv)['manual']==manual and 'flowLayout' not in byid['manual'])
    count=len(cv['nodes']);same=create('场景资产','scene')
    check('single-node creation retry is idempotent',same==parent and len(read(cid)['nodes'])==count)
    conflict=call('create_generation_node',{'title':'场景资产','prompt':'场景资产，清晨窗光下的居民家，明确的构图与细节'},canvas_id=cid,workflow_id='different',idempotency_key='scene',ok=False)
    check('idempotency cannot silently switch workflow',conflict['error_code']=='idempotency_conflict')
    legacy=rpc('canvas_create_generation_node',{'canvas_id':cid,'prompt':'旧入口不得执行'})['result']
    check('cached legacy tool rejected with migration guidance',legacy['isError'] and json.loads(legacy['content'][0]['text'])['entrypoint']=='canvas_execute' and len(read(cid)['nodes'])==count)
    invalid=call('create_generation_node',{'prompt':'坐标不允许','x':900},canvas_id=cid,ok=False)
    check('coordinates cannot bypass managed layout',invalid['error_code']=='coordinates_managed' and len(read(cid)['nodes'])==count)
    call('get_state',{'canvas_id':'different'},canvas_id=cid,ok=False)
    call('get_state',ok=False)
    check('canvas target is explicit and cannot be shadowed',len(read(cid)['nodes'])==count)
    call('batch_operations',{'operations':[{'op_type':'add_node','params':{'node_type':'generation','title':'批量新增','prompt':'窗边的木桌上放着一本打开的书','artifact_id':'batch-asset-1'}}]},canvas_id=cid)
    cv=read(cid)
    check('batch node construction also uses managed workflow',all(n.get('flowLayout',{}).get('layout')=='tree_lr' for n in cv['nodes'] if n['id']!='manual'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        ids=list(pool.map(lambda w:create('并发工作流 '+w,w,w),('isolated-a','isolated-b')))
    byid={n['id']:n for n in read(cid)['nodes']}
    check('concurrent requests do not leak workflow context',[byid[i]['flowLayout']['workflowId'] for i in ids]==['isolated-a','isolated-b'])
    video=call('create_video_node',{'title':'视频节点参数保留','prompt':'木桌特写缓慢推进，保持窗光连续','duration':6,'video_aspect':'16:9','submit':False},canvas_id=cid,idempotency_key='video-config')
    actual_video=next(n for n in read(cid)['nodes'] if n['id']==video['node_id'])
    check('video creation keeps native parameters and automatic layout',actual_video['flowLayout']['layout']=='tree_lr' and actual_video['runSettings']['apiKind']=='video' and actual_video['runSettings']['videoAspect']=='16:9' and not video['submitted'])
    legacy_canvas=call('create',{'title':'旧 Agent 节点继续操作'})['canvas_id']
    old=read(legacy_canvas)
    old['nodes']=[{'id':'agent_old_parent','type':'smart-image','title':'旧场景','promptDraftText':'清晨窗边木桌','__origin':'mcp','x':900,'y':100,'w':400,'h':240,'layoutLocked':True},
                  {'id':'agent_old_child','type':'smart-image','title':'旧镜头','promptDraftText':'窗边的人物特写','__origin':'agent_tool_generation','x':100,'y':600,'w':300,'h':400},
                  {'id':'manual_keep','type':'smart-prompt','title':'手工卡片','text':'保留','x':40,'y':40,'w':632,'h':388},
                  {'id':'agent_unrelated','type':'smart-image','title':'另一个未触及任务','__origin':'mcp','x':2200,'y':100,'w':300,'h':200}]
    api('/api/canvases/'+legacy_canvas,old,'PUT')
    revision=read(legacy_canvas)['updated_at']
    call('connect_nodes',{'from_id':'agent_old_parent','to_id':'missing'},canvas_id=legacy_canvas,ok=False)
    failed=read(legacy_canvas)
    check('failed legacy operation cannot partially migrate nodes',failed['updated_at']==revision and all('flowLayout' not in n for n in failed['nodes']))
    call('connect_nodes',{'from_id':'agent_old_parent','to_id':'agent_old_child'},canvas_id=legacy_canvas)
    old_nodes={n['id']:n for n in read(legacy_canvas)['nodes']}
    check('continuing legacy Agent nodes also activates layout',all(old_nodes[k].get('flowLayout',{}).get('layout')=='tree_lr' for k in ('agent_old_parent','agent_old_child')) and old_nodes['agent_old_parent']['x']+400<=old_nodes['agent_old_child']['x'])
    check('locked legacy Agent position is preserved',(old_nodes['agent_old_parent']['x'],old_nodes['agent_old_parent']['y'])==(900,100))
    check('legacy migration leaves manual and unrelated Agent cards alone','flowLayout' not in old_nodes['manual_keep'] and 'flowLayout' not in old_nodes['agent_unrelated'] and (old_nodes['manual_keep']['x'],old_nodes['manual_keep']['y'])==(40,40) and old_nodes['agent_unrelated']['x']==2200)
    with sync_playwright() as pw:
        if '--desktop' in sys.argv:
            browser=pw.chromium.connect_over_cdp('http://127.0.0.1:9261');page=browser.contexts[0].pages[0]
            if page.url=='about:blank':page.wait_for_url('**/static/index.html')
            page.wait_for_load_state('networkidle')
        else:
            browser=pw.chromium.launch(executable_path=r'C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe',headless=True);page=browser.new_page(viewport={'width':1500,'height':1000})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(BASE+'/static/smart-canvas.html?id='+cid,wait_until='networkidle')
        page.wait_for_function('id=>nodes.some(n=>n.id===id)',arg=parent)
        page.evaluate('saveCanvas()');page.wait_for_timeout(600)
        persisted=positions(read(cid))
        page.reload(wait_until='networkidle')
        check('real canvas save/reload preserves automatic positions',page.evaluate('Object.fromEntries(nodes.map(n=>[n.id,[n.x,n.y]]))')=={k:list(v) for k,v in persisted.items()})
        page.evaluate('selectedIds=nodes.map(n=>n.id);render();CanvasViewport.fitAllNodesViewport()');page.wait_for_timeout(350)
        page.screenshot(path=str(ROOT/'_verification/canvas-gateway-v0126.png'))
        check('native links and canvas render without errors',page.locator('svg.connection-layer path.conn-hit').count()==6 and not errors)
        if '--desktop' not in sys.argv:browser.close()
    (ROOT/'_verification/canvas-gateway-v0126.json').write_text(json.dumps({'base':BASE,'canvas_id':cid,'checks':checks,'canvas':read(cid)},ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
