"""Actual style library UI, prompt composition and persistence, without generation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
CHROME=r'C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe'

def main():
    with tempfile.TemporaryDirectory(prefix='myridtv-styles-') as temp:
        base='http://127.0.0.1:3231'
        env={**os.environ,'MYRIDTV_USER_DATA_DIR':temp,'MYRIDTV_ASSETS_DIR':str(Path(temp)/'assets')}
        with open(Path(temp)/'runtime.log','w',encoding='utf-8') as log:
            proc=subprocess.Popen([sys.executable,'-B','-c','import rh_official_proxy as p; p.CanvasProxyServer(("127.0.0.1",3231),p.Handler).serve_forever()'],cwd=ROOT,env=env,stdout=log,stderr=log)
            def api(path,payload=None):
                data=None if payload is None else json.dumps(payload).encode()
                with urllib.request.urlopen(urllib.request.Request(base+path,data=data,headers={'Content-Type':'application/json'}),timeout=15) as response:return json.load(response)
            try:
                for _ in range(60):
                    try:api('/health');break
                    except Exception:time.sleep(.2)
                else:raise RuntimeError('runtime not started')
                cid=api('/api/canvases',{'title':'风格库扩充验证','kind':'smart'})['canvas']['id']
                with sync_playwright() as p:
                    browser=p.chromium.launch(executable_path=CHROME,headless=True)
                    page=browser.new_page(viewport={'width':1440,'height':1000})
                    errors=[];report=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.route('**/static/app_config.json*',lambda route:route.fulfill(json={'proxy':{'base_url':base}}))
                    page.goto(base+'/static/smart-canvas.html?id='+cid)
                    page.wait_for_function('!!canvas && typeof CanvasStylePresets!=="undefined"')
                    # Create real media node and select its normal prompt composer.
                    page.locator('#canvasAddToggle').click();page.locator('[data-create-type="image"]').click()
                    page.wait_for_function('!!selectedId')
                    node_id=page.evaluate('selectedId')
                    page.evaluate('()=>{viewport.x=0;viewport.y=0;viewport.scale=1;const n=selectedNode();n.x=540;n.y=150;n.w=300;n.h=200;applyViewport();render();}')
                    page.evaluate("()=>{saveStylePreset({id:'us-kept',name:'已有自建风格',text:'自定义柔和光影'});renderComposerStyleControl();}")
                    def open_library():
                        page.locator('.style-mode-control > .smart-pill').click()
                        page.locator('.style-mode-control .style-popover').wait_for(state='visible')
                    def visible_count():return page.locator('[data-style-option]:visible').count()
                    open_library()
                    presets=page.evaluate('CanvasStylePresets.presets')
                    assert len(presets)==153 and len({x['id'] for x in presets})==153
                    assert len({x['name'] for x in presets})==153
                    assert all(len(x['text'])>=100 for x in presets)
                    assert len({x['text'] for x in presets})==153
                    assert all('主体、动作、服装与场景以用户正文为准' in x['text'] for x in presets)
                    assert visible_count()==154
                    cats=page.evaluate('CanvasStylePresets.categories')
                    assert [c['name'] for c in cats]==['真人','3D','2D']
                    assert {c['id']:sum(x['category']==c['id'] for x in presets) for c in cats}=={'live':73,'3d':20,'2d':60}
                    for cat in cats:
                        page.locator('[data-style-category="'+cat['id']+'"]').click()
                        assert visible_count()==sum(x['category']==cat['id'] for x in presets),cat
                    assert page.evaluate("!!stylePresetById('st-felt') && isBuiltinStyleId('st-felt')")
                    assert page.locator('[data-style-option="st-felt"]').count()==0
                    report.append('153 screenshot presets in three media categories; archived IDs and custom library retained')
                    page.locator('[data-style-category="all"]').click()
                    search=page.locator('[data-style-search]');search.fill('水墨')
                    assert visible_count()>=2
                    assert page.locator('[data-style-option="rh-2d-ink"]').is_visible()
                    assert search.evaluate('(e)=>e===document.activeElement')
                    search.fill('不存在的风格XYZ');assert visible_count()==0
                    assert page.locator('[data-style-empty]').is_visible()
                    search.fill('');page.locator('[data-style-category="mine"]').click()
                    assert visible_count()==1
                    page.locator('[data-style-category="all"]').click()
                    report.append('search matches names/prompt keywords, keeps focus, and category/empty states work')
                    box=page.locator('.style-mode-control .style-popover').bounding_box()
                    assert box['x']>=0 and box['y']>=0 and box['x']+box['width']<=1440 and box['y']+box['height']<=1000,box
                    results=page.locator('.style-mode-control .style-library-results')
                    assert results.evaluate('(e)=>e.scrollHeight>e.clientHeight')
                    before=page.evaluate('({...viewport})')
                    results.hover();page.mouse.wheel(0,700);page.wait_for_timeout(250)
                    assert results.evaluate('(e)=>e.scrollTop')>0
                    page.mouse.wheel(0,-900);page.wait_for_timeout(250)
                    assert results.evaluate('(e)=>e.scrollTop')==0
                    page.locator('.style-mode-control .style-popover-head').hover();page.mouse.wheel(0,500);page.wait_for_timeout(250)
                    assert results.evaluate('(e)=>e.scrollTop')>0
                    assert page.evaluate('({...viewport})')==before
                    page.screenshot(path=str(ROOT/'verification-style-library-v090.png'))
                    # Preview resources are local and all load; new covers explicitly say schematic.
                    urls=page.evaluate('CanvasStylePresets.presets.map(stylePresetImageUrl)')
                    for url in set(urls):assert page.request.get(base+url).ok,url
                    report.append('all local preview resources load and library scroll stays inside the viewport')
                    page.locator('[data-style-category="3d"]').click()
                    search.fill('手绘质感');page.locator('[data-style-option="rh-3d-hand-painted"]').click()
                    assert page.locator('#promptInput .mention-style-token[data-style-id="rh-3d-hand-painted"]').count()==1
                    prompt=page.evaluate('(id)=>buildPromptRequest(nodes.find(n=>n.id===id),[],false).prompt',node_id)
                    style_text=page.evaluate("stylePresetById('rh-3d-hand-painted').text")
                    assert style_text in prompt and '@手绘质感3D动画' not in prompt,prompt
                    open_library();page.locator('[data-style-option="rh-3d-hand-painted"]').click()
                    assert page.locator('#promptInput .mention-style-token[data-style-id="rh-3d-hand-painted"]').count()==1
                    report.append('new style inserts a real token and expands its full prompt once, not just its name')
                    page.wait_for_timeout(1200);page.reload()
                    page.wait_for_function('!!canvas && nodes.length>0')
                    page.evaluate('(id)=>{selectNodeFromPointer(id);syncSelectionUi();render();}',node_id)
                    assert page.locator('#promptInput .mention-style-token[data-style-id="rh-3d-hand-painted"]').count()==1
                    assert page.evaluate("stylePresetById('us-kept').text")=='自定义柔和光影'
                    page.locator('#promptInput .style-token-x').click()
                    assert page.locator('#promptInput .mention-style-token').count()==0
                    assert style_text not in page.evaluate('(id)=>buildPromptRequest(nodes.find(n=>n.id===id),[],false).prompt',node_id)
                    report.append('saved new style and custom styles survive reload; removing token removes its prompt suffix')
                    open_library();page.locator('[data-style-category="all"]').click()
                    page.locator('[data-style-search]').fill('国风赛璐璐')
                    tile=page.locator('[data-style-option="rh-2d-guoman-cel"]');tile.focus();page.keyboard.press('Enter')
                    assert page.locator('#promptInput [data-style-id="rh-2d-guoman-cel"]').count()==1
                    report.append('style cards support keyboard selection')
                    open_library();page.locator('[data-style-search]').fill('');page.locator('[data-style-category="mine"]').click()
                    page.locator('[data-style-new]').click()
                    page.locator('#assetDialogInput').fill('新增测试风格');page.locator('#assetDialogOk').click()
                    page.locator('#assetDialogInput').fill('通透柔和的蓝绿色调');page.locator('#assetDialogOk').click()
                    page.wait_for_function("userStylePresets.some(p=>p.name==='新增测试风格')")
                    open_library();assert visible_count()==2
                    custom=page.locator('[data-style-option]').filter(has=page.locator('.style-tile-name',has_text='新增测试风格'))
                    custom.hover();custom.locator('.style-tile-del').click();custom.locator('.style-tile-del').click()
                    assert page.evaluate("!userStylePresets.some(p=>p.name==='新增测试风格')")
                    assert page.evaluate("!!stylePresetById('us-kept')")
                    report.append('custom style create/delete still works without changing existing custom entries')
                    open_library();page.locator('[data-style-search]').focus();page.keyboard.press('Escape')
                    page.locator('.style-mode-control .style-popover').wait_for(state='hidden')
                    report.append('Escape closes the focused search menu')
                    for width,height,scale in [(960,720,1),(960,720,.7)]:
                        page.set_viewport_size({'width':width,'height':height})
                        page.evaluate('(scale)=>{viewport.x=0;viewport.y=0;viewport.scale=scale;applyViewport();render();}',scale)
                        open_library();box=page.locator('.style-mode-control .style-popover').bounding_box()
                        assert box['x']>=0 and box['y']>=0 and box['x']+box['width']<=width and box['y']+box['height']<=height,(width,height,scale,box,page.locator('.style-mode-control').evaluate('(e)=>({classes:e.className,rect:e.getBoundingClientRect().toJSON(),popover:e.querySelector(".style-popover").style.cssText})'))
                        page.keyboard.press('Escape')
                    report.append('smaller windows and canvas zoom keep the style panel within view')
                    # Filters use the same compact-chip mechanism, with one active filter.
                    page.set_viewport_size({'width':1440,'height':1000})
                    page.evaluate('()=>{viewport.scale=1;applyViewport();render();}')
                    style_box=page.locator('.style-mode-control').bounding_box()
                    filter_box=page.locator('.filter-mode-control').bounding_box()
                    assert filter_box['x']>=style_box['x']+style_box['width']
                    def open_filters():
                        page.locator('.filter-mode-control > .smart-pill').click()
                        page.locator('.filter-popover').wait_for(state='visible')
                    def request_prompt():return page.evaluate('(id)=>buildPromptRequest(nodes.find(n=>n.id===id),[],false).prompt',node_id)
                    page.locator('#promptInput').click()
                    page.keyboard.press('End');page.keyboard.type(' 测试主体与场景')
                    open_filters()
                    assert page.locator('[data-filter-option]').count()==12
                    assert page.evaluate('CanvasFilterPresets.presets.map(p=>p.name)')==['无','柯达','富士','伊尔福','电影胶片','宝丽来','电影光效','HDR','柔焦效果','胶片颗粒','赛博朋克','复古色调']
                    page.wait_for_timeout(200)
                    page.screenshot(path=str(ROOT/'verification-filter-library-v090.png'))
                    page.locator('[data-filter-search]').fill('柯达')
                    assert page.locator('[data-filter-option]:visible').count()==1
                    page.locator('[data-filter-option="ft-kodak"]').click()
                    chips=page.locator('#promptInput .mention-filter-token')
                    assert chips.count()==1
                    kodak=page.evaluate("CanvasFilterPresets.presets.find(p=>p.id==='ft-kodak').text")
                    assert kodak in request_prompt()
                    assert kodak not in page.locator('#promptInput').inner_text()
                    assert page.locator('#promptInput [data-style-id="rh-2d-guoman-cel"]').count()==1
                    assert '测试主体与场景' in page.locator('#promptInput').inner_text()
                    open_filters();page.locator('[data-filter-search]').fill('');page.locator('[data-filter-option="ft-fuji"]').click()
                    assert chips.count()==1 and chips.get_attribute('data-style-id')=='ft-fuji'
                    assert kodak not in request_prompt()
                    open_filters();page.locator('[data-filter-option="ft-fuji"]').click();assert chips.count()==1
                    page.wait_for_timeout(1200);page.reload()
                    page.wait_for_function('!!canvas && nodes.length>0')
                    page.evaluate('(id)=>{selectNodeFromPointer(id);syncSelectionUi();render();}',node_id)
                    assert chips.count()==1 and chips.get_attribute('data-style-id')=='ft-fuji'
                    assert '富士' in page.locator('.filter-mode-control > .smart-pill').get_attribute('aria-label')
                    page.screenshot(path=str(ROOT/'verification-filter-chip-v090.png'))
                    open_filters();page.locator('[data-filter-option="ft-none"]').click()
                    assert chips.count()==0 and page.locator('#promptInput [data-style-id="rh-2d-guoman-cel"]').count()==1
                    assert '测试主体与场景' in request_prompt()
                    open_filters();page.locator('[data-filter-option="ft-grain"]').focus();page.keyboard.press('Enter')
                    assert chips.count()==1 and '细腻均匀的胶片颗粒' in request_prompt()
                    chips.locator('.style-token-x').click()
                    assert chips.count()==0 and '细腻均匀的胶片颗粒' not in request_prompt()
                    open_filters();page.locator('[data-filter-search]').fill('不存在XYZ')
                    assert page.locator('[data-filter-option]:visible').count()==0
                    assert page.locator('[data-filter-empty]').is_visible()
                    page.keyboard.press('Escape');page.locator('.filter-popover').wait_for(state='hidden')
                    page.set_viewport_size({'width':960,'height':440})
                    page.evaluate('()=>{viewport.scale=1;selectedNode().y=-50;applyViewport();render();}')
                    open_filters();page.locator('[data-filter-search]').fill('')
                    box=page.locator('.filter-popover').bounding_box()
                    assert box['x']>=0 and box['y']>=0 and box['x']+box['width']<=960 and box['y']+box['height']<=440,box
                    results=page.locator('.filter-popover [data-preset-scroll]')
                    assert results.evaluate('(e)=>e.scrollHeight>e.clientHeight')
                    before=page.evaluate('({...viewport})')
                    results.hover();page.mouse.wheel(0,500);page.wait_for_timeout(250)
                    assert results.evaluate('(e)=>e.scrollTop')>0
                    page.mouse.wheel(0,-900);page.wait_for_timeout(250)
                    assert results.evaluate('(e)=>e.scrollTop')==0
                    page.mouse.down(button='middle');page.mouse.move(100,100);page.mouse.up(button='middle')
                    assert page.evaluate('({...viewport})')==before
                    page.locator('[data-filter-close]').click();page.locator('.filter-popover').wait_for(state='hidden')
                    report.append('12 filters right of styles, searchable chips, single replacement, full request expansion, reload, none/remove and keyboard selection')
                    report.append('filter panel stays within smaller windows, scrolls both ways, and middle-button gestures do not pan the canvas')
                    assert not errors,errors
                    browser.close()
                    for line in report:print('PASS '+line,flush=True)
                    (ROOT/'verification-style-filters-v090.json').write_text(json.dumps({'runtime':base,'passed':report,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
            finally:proc.terminate();proc.wait(timeout=10)

if __name__=='__main__':main()
