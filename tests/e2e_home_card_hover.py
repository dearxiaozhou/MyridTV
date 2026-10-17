"""Verify hover/leave/selection for every registered theme, not a fixed subset."""
import json
from playwright.sync_api import sync_playwright
from e2e_application_palette import BASE,ROOT,protect

def main():
 with sync_playwright() as p:
  browser=p.chromium.connect_over_cdp('http://127.0.0.1:9265')
  context=browser.contexts[0];context.route('**/api/**',protect)
  page=context.pages[0];errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE+'/static/canvas.html',wait_until='networkidle')
  themes=page.evaluate('StudioTheme.list()');checks=[]
  assert len(themes)>=7
  def color(key):
   return page.evaluate("k=>{let el=document.createElement('span');el.style.color='var(--x-'+k+')';document.body.append(el);let c=getComputedStyle(el).color;el.remove();return c}",key)
  for theme in themes:
   page.evaluate('t=>StudioTheme.set(t)',theme['id'])
   assert page.evaluate('StudioTheme.get()')==theme['id']
   for selector in ['.canvas-item:not(:has(.has-cover))','.canvas-item:has(.has-cover)']:
    card=page.locator(selector).first
    card.evaluate("e=>e.classList.remove('active')")
    for state in ['normal','hover','leave','selected']:
     if state=='hover':card.hover()
     elif state=='selected':card.evaluate("e=>e.classList.add('active')")
     else:page.mouse.move(1200,800)
     expected=color('selected-line' if state in ['hover','selected'] else 'line-strong')
     page.wait_for_function("([selector,c])=>getComputedStyle(document.querySelector(selector)).borderColor===c",arg=[selector,expected])
     assert card.evaluate('e=>getComputedStyle(e).borderWidth')=='1px'
     checks.append({'theme':theme['id'],'card':selector,'state':state,'color':expected})
     if state=='hover' and 'not' in selector:
      page.screenshot(path=str(ROOT/f'_verification/card-hover-all-{theme["id"]}.png'))
    card.evaluate("e=>e.classList.remove('active')")
   assert page.locator('.gate-list').evaluate('e=>getComputedStyle(e).borderWidth')=='0px'
  assert not errors,errors
  report={'themes':themes,'checks':checks,'errors':errors}
  (ROOT/'_verification/card-hover-all-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'themes':[t['zh'] for t in themes],'checks':len(checks),'errors':errors},ensure_ascii=False))

if __name__=='__main__':main()
