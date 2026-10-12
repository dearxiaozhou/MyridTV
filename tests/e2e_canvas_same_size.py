"""Exercise the size toolbar against the running local app without canvas writes."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:3107'

def verify(page):
    page.route('**/api/canvases/**', lambda r: r.fulfill(status=200, content_type='application/json', body='{"ok":true}')
               if r.request.method in ('PUT', 'POST', 'PATCH', 'DELETE') else r.continue_())
    page.goto(BASE + '/static/smart-canvas.html', wait_until='networkidle')
    page.wait_for_function("typeof CanvasNodeLayoutController === 'object'")
    page.evaluate("""() => {
        canvas={id:'same-size-verification',connections:[]};
        const image={url:'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="%234980ab"/></svg>',natural_w:640,natural_h:360,generatedResult:true};
        nodes.splice(0,nodes.length,
            {id:'size_ref',type:'smart-image',title:'尺寸基准',x:100,y:100,w:320,h:180,cardSize:{width:320,height:180},cardSizing:'media',images:[image]},
            {id:'size_empty',type:'smart-image',title:'空节点',x:480,y:100,w:512,h:288,cardSize:{width:512,height:288},cardSizing:'default',images:[]},
            {id:'size_result',type:'smart-image',title:'生成结果',x:100,y:440,w:240,h:320,cardSize:{width:240,height:320},cardSizing:'spec',images:[image]},
            {id:'size_upload',type:'smart-image',title:'上传节点',x:480,y:440,w:220,h:140,images:[{...image,generatedResult:false}]});
        selectedIds=nodes.map(n=>n.id);selectedId='';Object.assign(viewport,{x:0,y:0,scale:1});render();applyViewport();
    }""")
    read = "nodes.map(n=>({id:n.id,w:nodeRect(n).width,h:nodeRect(n).height,cardSize:n.cardSize,cardSizing:n.cardSizing}))"
    before = page.evaluate(read)
    page.locator('[data-id="size_ref"] [data-smart-node-action="same-size"]').click()
    page.wait_for_timeout(250)
    after = page.evaluate(read)
    print(json.dumps({'before':before,'after':after},ensure_ascii=False),flush=True)
    assert all(n['w']==320 and n['h']==180 for n in after), after
    for node in after:
        el=page.locator(f'.image-node[data-id="{node["id"]}"]')
        assert el.evaluate("el=>el.style.width==='320px' && el.style.height==='180px'")
    page.evaluate('render()')
    assert page.evaluate(read)==after
    page.screenshot(path=str(ROOT/'_verification/same-size-v01014.png'))
    page.evaluate('performUndo()')
    assert page.evaluate(read)==before, 'Undo must restore card sizes as well as w/h'
    print('PASS: actual toolbar click, fixed/empty/generated/upload cards, rerender, undo',flush=True)

if __name__=='__main__':
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe',headless=True)
        verify(browser.new_page(viewport={'width':1440,'height':1000}))
        browser.close()

