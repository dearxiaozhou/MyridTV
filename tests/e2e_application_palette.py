"""Audit approved palette in real served pages without writing user runtime data."""
import json,os,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from myridtv_mcp_client import backend_base
BASE=os.environ.get('MYRIDTV_THEME_TEST_BASE',backend_base())
THEME_PAGES={'dark':'#15191c','light':'#eef3f0','champagne':'#1c1a18','obsidian':'#0b0c0e','sakura':'#fff3f8','taiyuan-yeyu':'#121714','nuanxuan-liujin':'#f4f0e7'}
PAGES={
 'home':('canvas.html',['body','.canvas-gate','.canvas-item','.gate-icon-btn','.smart-create-btn','.canvas-card-title']),
 'host':('index.html',['body','#tb-bar','.tb-pop','.bottom-dock','.tc-panel','.tc-analytics-card']),
 'api':('api-settings.html',['body','.page-head','.side-card','.content-head','.block','.mod-row','.action-btn','.model-value-input']),
 'workflow':('comfyui-settings.html',['body','.side-card','.content-head','.workflow-card','.field-frame','.save-btn','.run-btn']),
 'library':('asset-manager.html',['body','.asset-page','.asset-panel','.asset-tabs button','.asset-btn']),
 'assets-root':('assets-root.html',['body','.ar-card','.ar-path','.ar-btn.primary']),
 'canvas':('smart-canvas.html',['body','.shell','.image-node','.smart-pill','.prompt-template-panel','.canvas-asset-panel','.style-popover','.shared-native-select-menu'])}

def protect(route):
 if route.request.method in ('POST','PUT','PATCH','DELETE'):
  route.fulfill(status=200,content_type='application/json',body='{"ok":true}')
 else:route.continue_()

def states(page,name,theme):
 checks=[]
 def style(selector,prop):return page.locator(selector).first.evaluate('(el,p)=>getComputedStyle(el)[p]',prop)
 def token(key):return page.evaluate("key=>{const el=document.createElement('span');el.style.color='var(--x-'+key+')';document.body.append(el);const value=getComputedStyle(el).color;el.remove();return value}",key)
 def assert_color(label,selector,prop,key):
  expected=token(key)
  page.wait_for_function("([selector,prop,expected])=>getComputedStyle(document.querySelector(selector))[prop]===expected",arg=[selector,prop,expected],timeout=2500)
  actual=style(selector,prop)
  assert actual==expected,(name,theme,label,actual,expected)
  checks.append(label)
 def hover(selector):page.locator(selector).first.hover()
 if name=='home':
  hover('.canvas-item');assert_color('home card theme hover border','.canvas-item:hover','borderColor','selected-line')
  page.mouse.move(1200,800)
  assert_color('home card normal border','.canvas-item','borderColor','line-strong')
  assert_color('home card matches palette','.canvas-open:not(.has-cover)','backgroundColor','card')
  hover('.gate-icon-btn');assert_color('neutral hover','.gate-icon-btn','backgroundColor','hover-bg')
  page.locator('.gate-icon-btn').first.focus();assert_color('keyboard focus','.gate-icon-btn','outlineColor','selected-line')
  hover('.smart-create-btn');assert_color('primary hover','.smart-create-btn','backgroundColor','accent-hover')
  assert_color('primary text','.smart-create-btn','color','strong-text')
  page.locator('#gateCreateSmartBtn').click()
  page.locator('.gate-create-row').wait_for(state='visible')
  assert_color('new canvas naming row','.gate-create-row','backgroundColor','panel-solid')
  assert_color('naming row focus','.gate-create-row','borderColor','selected-line')
  assert_color('create confirmation primary','#gateConfirmBtn','backgroundColor','strong')
  assert_color('create confirmation text','#gateConfirmBtn','color','strong-text')
  assert_color('create cancel neutral','#gateCancelBtn','backgroundColor','soft')
  page.screenshot(path=str(ROOT/f'_verification/palette-new-canvas-{theme}.png'))
  hover('#gateConfirmBtn');assert_color('confirmation hover','#gateConfirmBtn','backgroundColor','accent-hover')
  hover('#gateCancelBtn');assert_color('cancel hover','#gateCancelBtn','backgroundColor','hover-bg')
  page.locator('#gateCancelBtn').click()
  assert not page.locator('.gate-create-row').is_visible()
  page.locator('#gateTrashBtn').click()
  # The home background layer intentionally makes the gate transparent.
  assert_color('recycle page shares background','body','backgroundColor','page')
  page.screenshot(path=str(ROOT/f'_verification/palette-recycle-{theme}.png'))
 elif name=='host':
  page.evaluate('toggleTaskConsole();tcSetStatsView(true)')
  page.wait_for_timeout(500)
  assert_color('statistics surface','.tc-analytics-card','backgroundColor','panel-solid')
  assert_color('statistics selected tab','#tc-tab-stats','backgroundColor','selected-fill')
  page.screenshot(path=str(ROOT/f'_verification/palette-statistics-{theme}.png'))
  page.evaluate('toggleTaskConsole()')
  menu=page.locator('.tb-menu')
  if menu.count() and menu.first.is_visible():
   menu.first.click()
   assert_color('title menu popup','.tb-pop.open','backgroundColor','panel-solid')
   page.screenshot(path=str(ROOT/f'_verification/palette-title-menu-{theme}.png'))
   page.keyboard.press('Escape')
   hover('.tb-winclose');assert_color('window close retains danger color','.tb-winclose','backgroundColor','window-close-bg')
   page.mouse.move(100,100)
  for frame in page.frames[1:]:
   if '/static/' in frame.url:
    assert frame.evaluate("getComputedStyle(document.body).getPropertyValue('--x-page').trim()") == THEME_PAGES[theme]
  checks.append('host and child frames share theme')
 elif name=='api':
  selector='.protocol-selector-wrap .shared-native-select-trigger'
  page.locator(selector).first.click()
  assert page.locator(selector).first.get_attribute('aria-expanded')=='true'
  assert_color('model/protocol popup','.shared-native-select-menu','backgroundColor','panel-solid')
  assert_color('selected option','.shared-native-select-option[aria-selected="true"]','backgroundColor','selected-fill')
  other='.shared-native-select-option[aria-selected="false"]'
  hover(other);assert_color('option hover',other,'backgroundColor','hover-bg')
  page.screenshot(path=str(ROOT/f'_verification/palette-dropdown-{theme}.png'))
  page.keyboard.press('Escape')
  assert page.locator(selector).first.get_attribute('aria-expanded')=='false'
  checks.append('expanded state closes correctly')
  field='#baseInput'
  if not page.locator(field).count():field='input:not([type=hidden]):not(:disabled)'
  page.locator(field).first.focus();assert_color('input focus',field,'borderColor','selected-line')
 elif name=='workflow':
  selector='.workflow-card:not(.active)';hover(selector);assert_color('workflow hover',selector,'backgroundColor','hover-bg')
  assert_color('workflow selected','.workflow-card.active','backgroundColor','selected-fill')
 elif name=='library':
  selector='.asset-tabs button:not(.active)';hover(selector);assert_color('library tab hover',selector,'backgroundColor','hover-bg')
  assert_color('library selected','.asset-tabs button.active','backgroundColor','selected-fill')
 elif name=='assets-root':
  hover('.ar-btn.primary');assert_color('asset path primary hover','.ar-btn.primary','backgroundColor','accent-hover')
 elif name=='canvas':
  assert_color('node filename label','.smart-image-name-label','backgroundColor','panel-solid')
  assert_color('node filename text','.smart-image-name-label','color','text')
  hover('.image-wrap');assert_color('resolution badge','.image-resolution-badge','backgroundColor','panel-solid')
  assert_color('resolution text','.image-resolution-badge','color','text')
  assert_color('add tool icon','#canvasAddToggle .canvas-dock-icon','backgroundColor','soft')
  page.screenshot(path=str(ROOT/f'_verification/palette-node-details-{theme}.png'))
  hover('#canvasAddToggle');assert_color('add tool icon hover','#canvasAddToggle .canvas-dock-icon','backgroundColor','hover-bg')
  page.mouse.move(1100,80)
  page.locator('#assetToggle').click()
  assert_color('canvas material drawer','#assetPanel','backgroundColor','panel-solid')
  page.screenshot(path=str(ROOT/f'_verification/palette-canvas-assets-{theme}.png'))
  page.locator('#assetCloseBtn').click()
  page.evaluate("document.getElementById('promptTemplatePanel').classList.add('open')")
  assert_color('prompt library panel','#promptTemplatePanel','backgroundColor','panel-solid')
  page.evaluate("document.getElementById('promptTemplatePanel').classList.remove('open')")
  page.locator('#styleToggle').click()
  assert_color('style library panel','.style-popover','backgroundColor','panel-solid')
  page.screenshot(path=str(ROOT/f'_verification/palette-canvas-styles-{theme}.png'))
  page.locator('#styleToggle').click()
  selector='.speech-picker'
  if page.locator(selector).count():
   page.locator(selector).first.click()
   assert_color('speech dropdown','.speech-picker-menu','backgroundColor','panel-solid')
   page.keyboard.press('Escape')
  toggle=page.locator('#canvasAgentToggle')
  if toggle.count() and toggle.is_visible():toggle.click()
  assert_color('Agent panel shares palette','#canvasAgentPanel','backgroundColor','panel-solid')
  page.wait_for_timeout(350)
  page.screenshot(path=str(ROOT/f'_verification/palette-agent-{theme}.png'))
 return checks

def main():
 report=[]
 with sync_playwright() as p:
  if '--desktop' in sys.argv:
   browser=p.chromium.connect_over_cdp(os.environ.get('MYRIDTV_THEME_CDP','http://127.0.0.1:9265'));context=browser.contexts[0];page=context.pages[0]
   if page.url=='about:blank':page.wait_for_url('**/static/index.html')
   page.wait_for_load_state('networkidle')
  else:
   browser=p.chromium.launch(executable_path=r'C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe',headless=True)
   context=browser.new_context(viewport={'width':1500,'height':1000});page=context.new_page()
  context.route('**/api/**',protect)
  context.add_init_script("localStorage.setItem('studio_ui_scale_mode','100')")
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE+'/static/canvas.html',wait_until='networkidle')
  registered=page.evaluate('StudioTheme.list()')
  if '--all-themes' in sys.argv:
   assert set(THEME_PAGES)=={t['id'] for t in registered},'Update expected palette values for newly registered themes'
  for theme in ([t['id'] for t in registered] if '--all-themes' in sys.argv else ['dark','light']):
   mode=next(t['mode'] for t in registered if t['id']==theme)
   context.add_init_script(f"localStorage.setItem('studio_theme_id','{theme}');localStorage.setItem('studio_theme','{mode}');localStorage.setItem('canvas_theme','{mode}')")
   for name,(filename,selectors) in PAGES.items():
    page.goto(BASE+'/static/'+filename,wait_until='networkidle')
    page.wait_for_function("typeof StudioTheme==='object'")
    page.evaluate('t=>StudioTheme.set(t)',theme)
    page.wait_for_function("!!document.querySelector('#studio-application-palette')?.sheet")
    if name=='canvas':
     page.evaluate("""() => {canvas={id:'theme-preview',connections:[]};nodes.splice(0,nodes.length,
       {id:'theme-image',type:'smart-image',title:'图像节点',x:100,y:120,w:440,h:248,cardSize:{width:440,height:248},cardSizing:'manual',images:[{url:'/static/images/myrid-icon.png',name:'10-16-15.jpg',natural_w:512,natural_h:512}]},
       {id:'theme-prompt',type:'smart-prompt',title:'文本节点',x:620,y:120,w:632,h:388,text:'统一的背景、正文和输入框',llmEnabled:false},
       {id:'theme-speech',type:'smart-speech',title:'语音节点',x:100,y:600,w:1000,h:540,speechLayout:3,images:[]});
       selectedId='';selectedIds=[];Object.assign(viewport,{x:0,y:0,scale:.8});render();applyViewport();} """)
    result=page.evaluate("""selectors => ({
      tokens:Object.fromEntries(['page','card','soft','text','muted','strong','strong-text','selected-fill'].map(k=>[k,getComputedStyle(document.body).getPropertyValue('--x-'+k).trim()])),
      surfaces:selectors.map(selector=>{const el=document.querySelector(selector);if(!el)return{selector,missing:true};const s=getComputedStyle(el);return{selector,bg:s.backgroundColor,image:s.backgroundImage,color:s.color,border:s.borderColor,display:s.display}}),
      links:[...document.querySelectorAll('link[rel=stylesheet]')].map(el=>el.getAttribute('href'))
    })""",selectors)
    result.update(page=name,theme=theme)
    expected=THEME_PAGES[theme]
    assert result['tokens']['page']==expected,(name,theme,result)
    expected_rgb='rgb('+', '.join(str(int(expected[i:i+2],16)) for i in [1,3,5])+')'
    assert result['surfaces'][0]['bg']==expected_rgb,(name,theme,result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    report.append(result)
    page.screenshot(path=str(ROOT/f'_verification/palette-{name}-{theme}.png'))
    result['interactions']=states(page,name,theme)
  (ROOT/'_verification/application-palette-audit.json').write_text(json.dumps({'base':BASE,'pages':report,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
  print('TOTAL_PAGES',len(report),'JS_ERRORS',errors)
  if '--desktop' not in sys.argv:browser.close()

if __name__=='__main__':main()
