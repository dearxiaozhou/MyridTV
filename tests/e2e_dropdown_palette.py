"""Exercise the formerly native library menus in the actual desktop WebView.
All backend mutations are intercepted; selections only affect the test profile.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from e2e_application_palette import BASE, ROOT, protect

def main():
    report=[]
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp('http://127.0.0.1:9265')
        context=browser.contexts[0]
        context.route('**/api/**',protect)
        context.add_init_script("localStorage.setItem('studio_ui_scale_mode','100')")
        page=context.pages[0]
        page.on('pageerror',lambda e:errors.append(str(e)))
        def check(selector,prop,token):
            actual=page.locator(selector).first.evaluate('(el,p)=>getComputedStyle(el)[p]',prop)
            expected=page.evaluate("k=>{const el=document.createElement('span');el.style.color='var(--x-'+k+')';document.body.append(el);const v=getComputedStyle(el).color;el.remove();return v}",token)
            assert actual==expected,(selector,prop,actual,expected)
        def menu(select_id,theme):
            trigger=page.locator(f'#{select_id}').locator('..').locator('.shared-native-select-trigger')
            assert trigger.count()==1,select_id
            trigger.click()
            assert trigger.get_attribute('aria-expanded')=='true'
            page.wait_for_timeout(200)
            check('.shared-native-select-menu','backgroundColor','panel-solid')
            check('.shared-native-select-option[aria-selected=true]','backgroundColor','selected-fill')
            page.screenshot(path=str(ROOT/f'_verification/dropdown-{select_id}-{theme}.png'))
            page.keyboard.press('Escape')
            assert trigger.get_attribute('aria-expanded')=='false'
            assert page.locator('.shared-native-select-menu').count()==0
            report.append(f'{theme}: {select_id} opens, selects and closes with theme')
        for theme in ['dark','light']:
            context.add_init_script(f"localStorage.setItem('studio_theme','{theme}');localStorage.setItem('canvas_theme','{theme}')")
            page.goto(BASE+'/static/smart-canvas.html',wait_until='networkidle')
            page.wait_for_function('!!window.StudioSelectMenu')
            page.locator('#assetToggle').click()
            menu('assetLibrarySelect',theme)
            menu('assetCategorySelect',theme)
            # Choose another real folder via keyboard, retaining the native change path.
            select=page.locator('#assetCategorySelect')
            if select.locator('option').count()>1:
                page.evaluate("() => {window.categoryChanges=0;assetCategorySelect.addEventListener('change',()=>window.categoryChanges++);} ")
                trigger=select.locator('..').locator('.shared-native-select-trigger')
                trigger.click();page.keyboard.press('ArrowDown');page.keyboard.press('Enter')
                assert page.evaluate('window.categoryChanges')==1
                assert trigger.inner_text().strip()==select.locator('option:checked').inner_text().strip()
                report.append(f'{theme}: folder choice dispatches one native change and updates label')
            page.locator('#assetCloseBtn').click()
            page.evaluate("document.getElementById('promptTemplatePanel').classList.add('open')")
            menu('promptTemplateLibrarySelect',theme)
            page.evaluate("document.getElementById('promptTemplatePanel').classList.remove('open')")
            page.evaluate("""() => {canvas={id:'dropdown-preview',connections:[]};nodes.splice(0,nodes.length,
                {id:'theme-previz',type:'smart-image',title:'3D 预演',x:300,y:100,w:440,h:248,cardSize:{width:440,height:248},cardSizing:'manual',images:[],runSettings:{engine:'blender',provider_id:'blender',model:'blender-previz'}});
                selectedId='theme-previz';selectedIds=['theme-previz'];Object.assign(viewport,{x:0,y:0,scale:1});render();applyViewport();updateComposer();} """)
            page.locator('.composer.open').wait_for(state='visible')
            page.wait_for_timeout(300)
            check('.composer-card','backgroundColor','panel-solid')
            check('#promptInput','backgroundColor','soft')
            check('.previz-llm-toggle','backgroundColor','soft')
            page.screenshot(path=str(ROOT/f'_verification/dropdown-composer-{theme}.png'))
            # Dynamic fields use the same adapter; grouped-disabled choices stay disabled.
            page.evaluate("""() => {const box=document.createElement('div');box.id='dropdown-fixture';box.style='position:fixed;top:100px;left:300px;width:240px;z-index:10000';box.innerHTML='<select id="dynamic-theme-select"><option value="a">动态参数 A</option><optgroup label="不可用" disabled><option value="x">禁用参数</option></optgroup><option value="b">动态参数 B</option></select>';document.body.append(box);} """)
            page.wait_for_function("document.querySelector('#dynamic-theme-select').dataset.sharedSelectEnhanced==='true'")
            trigger=page.locator('#dropdown-fixture .shared-native-select-trigger')
            trigger.click()
            assert page.locator('.shared-native-select-option:disabled').count()==1
            page.keyboard.press('ArrowDown');page.keyboard.press('Enter')
            assert page.locator('#dynamic-theme-select').input_value()=='b'
            page.evaluate("document.getElementById('dynamic-theme-select').disabled=true")
            page.wait_for_function("document.querySelector('#dropdown-fixture button').disabled")
            page.locator('#dropdown-fixture').evaluate('(el)=>el.remove()')
            report.append(f'{theme}: dynamic fields, disabled groups and programmatic disabled state')
            page.goto(BASE+'/static/canvas.html',wait_until='networkidle')
            page.locator('.canvas-preview-mark').first.click()
            check('.canvas-meta-pop','backgroundColor','panel-solid')
            check('.canvas-meta-label','color','muted')
            check('.canvas-cover-btn','backgroundColor','soft')
            check('.emoji-option','color','muted')
            colors=page.locator('.canvas-color-swatch:not(.cc-none)').evaluate_all('(els)=>els.map(el=>getComputedStyle(el).backgroundColor)')
            assert len(set(colors))>4,colors
            page.locator('.canvas-owner-input').focus()
            check('.canvas-owner-input','borderColor','selected-line')
            page.mouse.move(1000,800);page.wait_for_timeout(200)
            page.screenshot(path=str(ROOT/f'_verification/dropdown-card-editor-{theme}.png'))
            report.append(f'{theme}: metadata panel, input focus, icons, cover buttons; swatches preserved')
        assert not errors,errors
        (ROOT/'_verification/dropdown-theme-audit.json').write_text(json.dumps({'base':BASE,'checks':report,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'checks':report,'errors':errors},ensure_ascii=False))

if __name__=='__main__':main()
