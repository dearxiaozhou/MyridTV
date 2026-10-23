from pathlib import Path
import json, os
from playwright.sync_api import sync_playwright
out=Path('_verification/comfy-columns');out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    exe=sorted((Path(os.environ['LOCALAPPDATA'])/'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'))[-1]
    browser=p.chromium.launch(headless=True,executable_path=str(exe))
    page=browser.new_page(viewport={'width':1280,'height':850})
    page.route('**/static/app_config.json*',lambda r:r.fulfill(json={'proxy':{'base_url':'http://127.0.0.1:3113'}}))
    page.goto('http://127.0.0.1:3113/smart-canvas.html',wait_until='networkidle')
    page.evaluate('''() => {
        const fields=[{id:'ratio',name:'视频比例',type:'dropdown',options:['16:9 (Widescreen)','9:16'],default:'16:9 (Widescreen)'},
            {id:'pixels',name:'百万像素',type:'number',default:.6},
            {id:'duration',name:'时长',type:'number',default:10},
            {id:'steps',name:'步数',type:'number',default:8},
            {id:'lora',name:'去油lora强度',type:'slider',min:0,max:1,step:.1,default:.2}];
        CanvasComfyControls.configure({visibleComfyFields:f=>f,comfyFieldKind:f=>f.type,comfyParamValue:f=>f.default});
        CanvasDynamicParamEngine.configure({comfyParamValue:f=>f.default});
        const c=document.querySelector('#composer');c.className='composer comfy-layout';
        c.style.cssText='display:block;position:fixed;left:120px;top:380px;width:740px;transform:none;opacity:1;visibility:visible';
        const d=document.getElementById('dynamicParams');
        d.innerHTML=CanvasComfyControls.renderComfyParamsControl({},fields);
        d.querySelector('.smart-control').classList.add('pinned');
    }''')
    results={}
    for theme in ['dark','light']:
        page.evaluate('''theme=>{document.documentElement.classList.toggle('theme-light',theme==='light');document.body.classList.toggle('theme-light',theme==='light');document.documentElement.classList.toggle('theme-dark',theme==='dark');document.body.classList.toggle('theme-dark',theme==='dark');document.documentElement.classList.toggle('studio-theme-dark',theme==='dark');document.body.classList.toggle('studio-theme-dark',theme==='dark');}''',theme)
        page.wait_for_timeout(250)
        cells=page.locator('[data-comfy-param]').evaluate_all('''els=>els.map(e=>{const c=e.closest('.cfn-size-cell,.pfield');const r=c.getBoundingClientRect();return {id:e.dataset.comfyParam,x:r.x,y:r.y,w:r.width,h:r.height}})''')
        rows={}
        for cell in cells:rows.setdefault(round(cell['y']),[]).append(cell['id'])
        assert list(map(len,rows.values()))==[2,2,1],cells
        assert all(185<c['w']<215 for c in cells),cells
        page.locator('.comfy-params-popover input[type=number]').first.focus()
        page.screenshot(path=str(out/f'{theme}.png'))
        results[theme]={'rows':list(rows.values()),'cells':cells}
    (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    browser.close()
print('PASS - live app CSS and real parameter renderer: 2/2/1 in light and dark themes')
