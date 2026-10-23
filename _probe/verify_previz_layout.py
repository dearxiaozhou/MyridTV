from pathlib import Path
from playwright.sync_api import sync_playwright
import os,json
OUT=Path('_verification/previz-layout');OUT.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    exe=sorted((Path(os.environ['LOCALAPPDATA'])/'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'))[-1]
    browser=p.chromium.launch(headless=True,executable_path=str(exe))
    page=browser.new_page(viewport={'width':1500,'height':1000})
    page.goto('http://127.0.0.1:3107/smart-canvas.html',wait_until='networkidle')
    page.evaluate("composer.classList.add('open');composer.style.cssText='left:240px;top:300px;opacity:1;pointer-events:auto;transform:none'")
    measure='''() => {
        const r=e=>{const q=e.getBoundingClientRect();return {y:q.y,bottom:q.bottom,h:q.height}};
        const card=r(document.querySelector('.composer-card')),prompt=r(document.querySelector('.prompt-row'));
        const buttons=[...composer.querySelectorAll('.smart-pill')].filter(e=>e.getBoundingClientRect().height>0).map(e=>({text:e.textContent,...r(e)}));
        return {buttons,above:buttons[0].y-prompt.bottom,below:card.bottom-buttons[0].bottom};
    }'''
    page.evaluate("settings.engine='api';renderDynamicParams()")
    baseline=page.evaluate(measure)
    page.evaluate("settings.engine='blender';renderDynamicParams()")
    blender=page.evaluate(measure)
    assert all(b['h']==baseline['buttons'][0]['h']==30 for b in blender['buttons']),blender
    assert blender['above']==baseline['above'] and blender['below']==baseline['below'],(baseline,blender)
    results={'baseline':baseline,'previz':blender,'themes':{}}
    for theme in ['dark','light']:
        page.evaluate('''theme=>{
            for(const el of [document.documentElement,document.body]){
                el.classList.toggle('studio-theme-dark',theme==='dark');el.classList.toggle('theme-dark',theme==='dark');el.classList.toggle('theme-light',theme==='light');
            }
        }''',theme)
        page.locator('#blenderRatioPill').click()
        assert page.locator('#blenderRatioPill').get_attribute('aria-expanded')=='true'
        colors=page.locator('.blender-ratio-popover').evaluate('''e=>{
            const s=getComputedStyle(e),probe=document.createElement('div');probe.style.background='var(--x-panel-solid)';document.body.append(probe);
            const token=getComputedStyle(probe).backgroundColor;probe.remove();return {actual:s.backgroundColor,token};
        }''')
        assert colors['actual']==colors['token'],colors
        page.locator('.blender-ratio-opt:not(.active)').first.hover()
        page.screenshot(path=str(OUT/f'{theme}-hover.png'))
        page.locator('.blender-ratio-opt').nth(1).click()
        assert page.locator('#blenderRatioPill').get_attribute('aria-expanded')=='false'
        assert page.locator('.blender-ratio-opt').nth(1).evaluate("e=>e.classList.contains('active')")
        page.locator('#blenderRatioPill').focus()
        page.keyboard.press('Enter')
        assert page.locator('#blenderRatioPill').get_attribute('aria-expanded')=='true'
        page.screenshot(path=str(OUT/f'{theme}-focus.png'))
        page.evaluate('closeAllSmartPopovers()')
        results['themes'][theme]=colors
    assert results['themes']['dark']['actual'] != results['themes']['light']['actual'],results['themes']
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    browser.close()
print('PASS: 30px controls; API-equivalent upper/lower spacing; live theme/hover/selection/focus/expanded state')
