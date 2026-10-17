"""Real MCP + native canvas acceptance: 3 branches, DAG refs, incremental layout."""
import copy,json,os,sys,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from myridtv_flow_layout import node_size,overlap

ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ.get('MYRIDTV_FLOW_TEST_BASE','http://127.0.0.1:3250')
proof=[]
def check(name,condition):
    assert condition,name
    proof.append(name);print('PASS '+name,flush=True)
def api(path,data=None,method=None):
    req=urllib.request.Request(BASE+path,data=None if data is None else json.dumps(data).encode(),method=method,headers={'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(req,timeout=30))
def call(name,args,ok=True):
    args=copy.deepcopy(args)
    control={k:args.pop(k) for k in ('canvas_id','workflow_id','idempotency_key','expected_updated_at') if k in args}
    reply=api('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'canvas_execute','arguments':{'action':name.removeprefix('canvas_'),'params':args,**control}}})
    result=reply['result'];data=json.loads(result['content'][0]['text'])
    if ok:assert not result.get('isError'),data
    else:assert result.get('isError'),data
    return data
def read(cid):return api('/api/canvases/'+cid)['canvas']
def positions(canvas):return {n['id']:(n.get('x'),n.get('y')) for n in canvas['nodes']}
def validate(canvas):
    nodes=canvas['nodes'];byid={n['id']:n for n in nodes}
    assert len(nodes)==len(byid)
    for i,a in enumerate(nodes):
        for b in nodes[i+1:]:
            assert not overlap((a['x'],a['y'],*node_size(a)),(b['x'],b['y'],*node_size(b))),(a['id'],b['id'])
    for e in canvas['connections']:
        a,b=byid[e['from']],byid[e['to']]
        if (b.get('flowLayout') or {}).get('workflowId')=='director-scene':
            assert a['x']+node_size(a)[0]<=b['x'],e
            if e['kind']=='input':assert a['id'] in b['inputNodeIds']

def main():
    tools=api('/mcp',{'jsonrpc':'2.0','id':2,'method':'tools/list'})['result']['tools']
    check('MCP only exposes gateway; flow actions available', {t['name'] for t in tools}=={'canvas_execute'} and {'upsert_flow','layout_flow'}<=set(tools[0]['inputSchema']['properties']['action']['enum']))
    cid=call('canvas_create',{'title':'MCP 树状三分支验收'})['canvas_id']
    canvas=read(cid)
    canvas['nodes']=[{'id':'unrelated','type':'smart-prompt','title':'无关手工笔记','text':'保留原位','x':40,'y':40,'w':632,'h':388},
                     {'id':'shared-character','type':'smart-image','title':'已有角色，共享引用','x':40,'y':650,'w':260,'h':400,'images':[]}]
    api('/api/canvases/'+cid,canvas,'PUT')
    specs=[{'id':'scene','type':'generation','title':'场景资产','prompt':'清晨的居民家客厅，窗边有一张木桌','width':360,'height':210}]
    edges=[]
    for i,(w,h) in enumerate([(320,180),(280,420),(420,240)],1):
        specs.extend([{'id':f'shot{i}','type':'generation','title':f'镜头参考 {i}','prompt':f'镜头{i}，角色站在窗边，明确构图和景深','parent_id':'scene','branch_order':i,'width':w,'height':h},
                      {'id':f'video{i}','type':'video','title':f'视频 {i}','prompt':f'镜头{i}缓慢推进，保持人物一致性','depends_on':[f'shot{i}'],'branch_order':i,'width':480,'height':270}])
        edges.append({'from':'shared-character','to':f'shot{i}','kind':'input'})
    request={'canvas_id':cid,'workflow_id':'director-scene','layout':'tree_lr','nodes':specs,'edges':edges,'idempotency_key':'three-branches'}
    result=call('canvas_upsert_flow',request)
    canvas=read(cid);validate(canvas)
    check('atomic batch creates 7 native flow nodes + 9 edges',len(result['created'])==7 and len(canvas['connections'])==9)
    check('shared character referenced once without cloning',sum(n['id']=='shared-character' for n in canvas['nodes'])==1)
    byid={n['id']:n for n in canvas['nodes']}
    check('branchOrder controls top-to-bottom order',byid['shot1']['y']<byid['shot2']['y']<byid['shot3']['y'])
    parent_center=byid['scene']['y']+node_size(byid['scene'])[1]/2
    children_center=(byid['shot1']['y']+byid['shot3']['y']+node_size(byid['shot3'])[1])/2
    check('scene centered over its three child branches',abs(parent_center-children_center)<2)
    before=positions(canvas);call('canvas_upsert_flow',request);check('idempotency receipt replay changes nothing',positions(read(cid))==before)
    repeated={k:v for k,v in request.items() if k!='idempotency_key'}
    call('canvas_upsert_flow',repeated);check('stable IDs without receipt also avoid duplicates and jumps',positions(read(cid))==before)
    call('canvas_upsert_flow',{'canvas_id':cid,'workflow_id':'other-flow','nodes':[{'id':'other','type':'text','title':'另一工作流','text':'另一工作流保持原位'}]})
    call('canvas_upsert_flow',{'canvas_id':cid,'workflow_id':'director-scene','nodes':[{'id':'scene','locked':True}]})
    baseline=read(cid);stable={k:positions(baseline)[k] for k in ('unrelated','shared-character','other','scene')}
    call('canvas_upsert_flow',{'canvas_id':cid,'workflow_id':'director-scene','nodes':[
        {'id':'branch2-detail','type':'generation','title':'第二分支继续生产','prompt':'第二镜头的手部细节，保持服装和光线连续','parent_id':'shot2','branch_order':2,'width':350,'height':220},
        {'id':'branch2-next','type':'video','title':'第二分支视频延伸','prompt':'手部缓慢动作，镜头保持稳定','parent_id':'branch2-detail','width':420,'height':230}]})
    canvas=read(cid);validate(canvas)
    check('incremental multi-level branch remains rightward',len(canvas['nodes'])==12)
    check('unrelated nodes, other workflow and locked node stay put',all(positions(canvas)[k]==v for k,v in stable.items()))
    # A real native canvas save reports changed dimensions; store hook reflows only this flow.
    changed=copy.deepcopy(canvas);shot=next(n for n in changed['nodes'] if n['id']=='shot2')
    shot['w']=780;shot['h']=620;shot['cardSize']={'width':780,'height':620};shot['cardSizing']='manual';shot['flowLayout'].pop('measuredSize',None)
    api('/api/canvases/'+cid,changed,'PUT');canvas=read(cid);validate(canvas)
    check('changed card size automatically reflows without overlap',all(positions(canvas)[k]==v for k,v in stable.items()))
    version=canvas['updated_at']
    call('canvas_upsert_flow',{'canvas_id':cid,'workflow_id':'director-scene','nodes':[],'edges':[{'from':'video1','to':'scene'}]},ok=False)
    check('cycle rejected atomically',read(cid)['updated_at']==version)
    call('canvas_upsert_flow',{'canvas_id':cid,'workflow_id':'director-scene','nodes':[{'id':'bad','type':'text','text':'不应保存','parent_id':'missing'}]},ok=False)
    check('missing dependency rejected without partial nodes',not any(n['id']=='bad' for n in read(cid)['nodes']))
    with sync_playwright() as pw:
        if '--desktop' in sys.argv:
            browser=pw.chromium.connect_over_cdp('http://127.0.0.1:9250');page=browser.contexts[0].pages[0]
            if page.url=='about:blank':page.wait_for_url('**/static/index.html')
            page.wait_for_load_state('networkidle')
        else:
            browser=pw.chromium.launch(executable_path=r'C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe',headless=True)
            page=browser.new_page(viewport={'width':1600,'height':1000})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(BASE+'/static/smart-canvas.html?id='+cid,wait_until='networkidle')
        page.wait_for_function("nodes.some(n=>n.id==='branch2-next')")
        page.evaluate("() => { const flow=nodes.filter(n=>n.flowLayout?.workflowId==='director-scene');const rs=flow.map(nodeRect);const left=Math.min(...rs.map(r=>r.x)),top=Math.min(...rs.map(r=>r.y)),right=Math.max(...rs.map(r=>r.x+r.width)),bottom=Math.max(...rs.map(r=>r.y+r.height));Object.assign(viewport,{scale:Math.min(1,1200/(right-left),700/(bottom-top)),x:100-left*Math.min(1,1200/(right-left),700/(bottom-top)),y:100-top*Math.min(1,1200/(right-left),700/(bottom-top))});render();applyViewport();}")
        page.evaluate('saveCanvas()');page.wait_for_timeout(600)
        validate(read(cid))
        # Resize through the live UI model, save and ensure acknowledged layout is displayed.
        page.evaluate("() => {const n=nodes.find(n=>n.id==='shot1');n.w=900;n.h=700;n.cardSize={width:900,height:700};n.cardSizing='manual';render();}")
        page.evaluate('saveCanvas()');page.wait_for_timeout(600)
        actual=read(cid);validate(actual)
        check('live UI receives reflow after real measured-size save',page.evaluate("Object.fromEntries(nodes.filter(n=>n.flowLayout).map(n=>[n.id,[n.x,n.y]]))")=={n['id']:[n['x'],n['y']] for n in actual['nodes'] if n.get('flowLayout')})
        page.evaluate("selectedIds=nodes.map(n=>n.id);selectedId='';render();CanvasViewport.fitAllNodesViewport();")
        page.wait_for_timeout(400)
        page.screenshot(path=str(ROOT/'_verification/mcp-flow-three-branches-v01018.png'))
        persisted=positions(actual)
        page.reload(wait_until='networkidle');page.wait_for_timeout(500)
        check('native canvas refresh preserves saved coordinates',page.evaluate("Object.fromEntries(nodes.map(n=>[n.id,[n.x,n.y]]))")=={k:list(v) for k,v in persisted.items()})
        check('actual canvas renders all dependencies on right/left ports',page.locator('svg.connection-layer path.conn-hit').count()==len(actual['connections']))
        check('no browser errors',not errors)
        if '--desktop' not in sys.argv:browser.close()
    (ROOT/'_verification/mcp-flow-v01018.json').write_text(json.dumps({'base':BASE,'canvas_id':cid,'checks':proof,'locked_positions':stable},ensure_ascii=False,indent=2),encoding='utf-8')
    print('CANVAS_ID='+cid)

if __name__=='__main__':main()
