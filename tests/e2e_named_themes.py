"""Named palette persistence, menu choices and frame propagation."""
import json
from playwright.sync_api import sync_playwright
from e2e_application_palette import BASE,ROOT,protect

def main():
 with sync_playwright() as p:
  native=p.chromium.connect_over_cdp('http://127.0.0.1:9265')
  desktop=native.contexts[0].pages[0]
  desktop.goto(BASE+'/static/index.html',wait_until='networkidle')
  themes=desktop.evaluate('StudioTheme.list()')
  assert len(themes)>=7 and len({t['id'] for t in themes})==len(themes)
  for theme in themes:
   desktop.locator('.tb-menu').filter(has_text='设置').click()
   desktop.get_by_text('主题',exact=True).hover()
   desktop.get_by_text(theme['zh'],exact=True).click()
   assert desktop.evaluate('StudioTheme.get()')==theme['id']
   desktop.wait_for_function("id=>[...document.querySelectorAll('iframe')].filter(f=>f.contentDocument?.body && f.src.includes('/static/')).every(f=>f.contentDocument.documentElement.dataset.studioTheme===id)",arg=theme['id'])
   assert desktop.evaluate("localStorage.getItem('studio_theme')")==theme['mode']
   desktop.locator('.tb-menu').filter(has_text='设置').click()
   desktop.get_by_text('主题',exact=True).hover()
   desktop.screenshot(path=str(ROOT/f'_verification/named-theme-menu-{theme["id"]}.png'))
   desktop.keyboard.press('Escape')
  browser=p.chromium.launch(executable_path=r'C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe',headless=True)
  context=browser.new_context();context.route('**/api/**',protect)
  page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE+'/static/index.html',wait_until='networkidle')
  for theme in themes:
   page.evaluate('id=>StudioTheme.set(id)',theme['id'])
   page.reload(wait_until='networkidle')
   assert page.evaluate('StudioTheme.get()')==theme['id']
   assert page.evaluate("document.documentElement.classList.contains('theme-dark')")== (theme['mode']=='dark')
   page.goto(BASE+'/static/smart-canvas.html',wait_until='networkidle')
   assert page.evaluate('document.documentElement.dataset.studioTheme')==theme['id']
   assert page.evaluate("document.body.classList.contains('theme-dark')")== (theme['mode']=='dark')
   page.goto(BASE+'/static/index.html',wait_until='networkidle')
  # Old preferences migrate without a named identity; unknown values safely fall back.
  page.evaluate("localStorage.removeItem('studio_theme_id');localStorage.setItem('studio_theme','light')")
  page.reload(wait_until='networkidle');assert page.evaluate('StudioTheme.get()')=='light'
  page.evaluate("StudioTheme.set('obsidian');StudioTheme.set('invalid')")
  assert page.evaluate('StudioTheme.get()')=='obsidian'
  assert not errors,errors
  print(json.dumps({'menu_choices':len(themes),'persisted':len(themes),'frame_propagation':'passed','legacy':'passed','errors':errors}))
  browser.close()

if __name__=='__main__':main()
