"""Real MCP single-output center alignment, including native size-save feedback."""
import copy,json
from playwright.sync_api import sync_playwright
from e2e_mcp_flow_layout import BASE,ROOT,api,call,read,positions
from myridtv_flow_layout import node_size

def main():
 cid=call('canvas_create',{'title':'MCP 单输出中心线验收'})['canvas_id']
 canvas=read(cid)
 parent={'id':'source','type':'smart-image','title':'固定位置的现有上游','x':80,'y':1200,
         'w':520,'h':300,'cardSize':{'width':520,'height':300},'cardSizing':'manual',
         'images':[{'url':'/static/images/myrid-icon.png','name':'source.png','natural_w':512,'natural_h':512}]}
 note={'id':'unrelated','type':'smart-prompt','x':2800,'y':200,'w':632,'h':388,'text':'不移动'}
 canvas['nodes']=[parent,note];api('/api/canvases/'+cid,canvas,'PUT')
 req={'canvas_id':cid,'workflow_id':'single-output','nodes':[
      {'id':'output','type':'generation','title':'唯一输出：大小不同仍沿中心线','prompt':'单输出对齐验证，不提交生成任务',
       'width':320,'height':600,'images':[{'url':'/static/images/myrid-icon.png','name':'output.png','natural_w':512,'natural_h':512}]}],
      'edges':[{'from':'source','to':'output','kind':'input'}]}
 def validate():
  saved=read(cid);byid={n['id']:n for n in saved['nodes']}
  a,b=byid['source'],byid['output']
  assert abs(a['y']+node_size(a)[1]/2-b['y']-node_size(b)[1]/2)<=1,(a['y'],b['y'])
  assert (a['x'],a['y'])==(80,1200)
  assert (byid['unrelated']['x'],byid['unrelated']['y'])==(2800,200)
  return saved
 call('canvas_upsert_flow',req);validate()
 before=positions(read(cid));call('canvas_upsert_flow',req)
 assert before==positions(read(cid))
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=r'C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe',headless=True)
  page=browser.new_page(viewport={'width':1500,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE+'/static/smart-canvas.html?id='+cid,wait_until='networkidle')
  page.wait_for_function("nodes.some(n=>n.id==='output')")
  page.evaluate('saveCanvas()');page.wait_for_timeout(700);validate()
  for height in [420,180]:
   saved=read(cid);child=next(n for n in saved['nodes'] if n['id']=='output')
   child.update(h=height,cardSize={'width':320,'height':height},cardSizing='manual')
   child['flowLayout'].pop('measuredSize',None)
   api('/api/canvases/'+cid,saved,'PUT');validate()
  page.reload(wait_until='networkidle');page.wait_for_function("nodes.some(n=>n.id==='output')")
  page.evaluate("""() => {const a=nodeRect(nodes.find(n=>n.id==='source'));Object.assign(viewport,{scale:1,x:50-a.x,y:300-a.y});render();applyViewport();} """)
  actual=page.evaluate("() => ['source','output'].map(id=>{const r=nodeRect(nodes.find(n=>n.id===id));return r.y+r.height/2})")
  assert abs(actual[0]-actual[1])<=1,actual
  assert positions(read(cid))=={n['id']:(n['x'],n['y']) for n in page.evaluate('nodes')}
  assert page.locator('svg.connection-layer path.conn-hit').count()==1
  page.screenshot(path=str(ROOT/'_verification/mcp-single-output-center.png'))
  assert not errors,errors
  browser.close()
 (ROOT/'_verification/mcp-single-output-audit.json').write_text(json.dumps({'base':BASE,'canvas_id':cid,'checks':['MCP creates one aligned output','repeat call stable','unrelated source and note fixed','size changes retain centers','actual rendered node centers align','reload positions persist','one connection rendered'],'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
 print('Single-output MCP, resize, real canvas render/save/reload passed; canvas',cid)

if __name__=='__main__':main()
