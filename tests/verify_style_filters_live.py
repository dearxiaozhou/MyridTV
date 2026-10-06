"""Read-only UI verification against the launched development runtime."""
import json
import io
import hashlib
from urllib.parse import quote
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
CHROME=r'C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe'

def main():
    base='http://127.0.0.1:3107'
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=CHROME,headless=True)
        page=browser.new_page(viewport={'width':1440,'height':960})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        assert page.request.get(base+'/health').ok
        homepage=page.request.get(base+'/').text()
        version=(ROOT/'VERSION').read_text(encoding='utf-8').strip()
        assert '版本：'+version in homepage
        canvases=page.request.get(base+'/api/canvases').json()['canvases']
        cid=next(c['id'] for c in canvases if c.get('kind')=='smart')
        # All personal canvas writes and model calls are blocked in this check.
        def read_only(route):
            if route.request.method not in ('GET','HEAD','OPTIONS'):
                route.fulfill(status=200,json={'ok':True})
            else:route.continue_()
        page.route('**/api/**',read_only)
        page.goto(base+'/static/smart-canvas.html?id='+cid)
        page.wait_for_function('!!canvas && typeof CanvasFilterPresets!=="undefined"')
        page.wait_for_timeout(1200)
        assert page.evaluate('CanvasStylePresets.presets.length')==153
        # Lift the real control into a visible position, without editing canvas state.
        page.evaluate("""()=>{
            document.body.appendChild(composerStyleModeSlot);
            composerStyleModeSlot.id='verificationStyleSlot';
            composerStyleModeSlot.style.cssText='position:fixed;left:720px;top:680px;z-index:9999';
            renderComposerStyleControl();
        }""")
        page.wait_for_timeout(1000)
        page.locator('.style-mode-control > .smart-pill').click(timeout=3000)
        panel=page.locator('.style-mode-control .style-popover')
        panel.wait_for(state='visible')
        presets=page.evaluate('CanvasStylePresets.presets')
        assert all(p['image'].startswith('/static/images/styles/generated/') for p in presets)
        assert len({p['image'] for p in presets})==153, 'Duplicate preview URLs'
        digests={}
        for preset in presets:
            assert preset['image'].endswith('/'+preset['id']+'.png'),preset['id']
            response=page.request.get(base+preset['image'])
            assert response.ok,preset['id']
            digest=hashlib.sha256(response.body()).hexdigest()
            assert digest not in digests,(preset['id'],digests.get(digest))
            digests[digest]=preset['id']
            image=Image.open(io.BytesIO(response.body()))
            assert min(image.size)>=512,(preset['id'],image.size)
        assert all('previewSize' not in p and 'previewPosition' not in p for p in presets)
        preview_selector='img.style-tile-img[src^="/static/images/styles/generated/"]'
        def wait_visible_previews():
            panel.locator('img.style-tile-img').evaluate_all('''images=>Promise.all(images.filter(img=>{const r=img.getBoundingClientRect();return r.width>0&&r.height>0&&r.top<innerHeight&&r.bottom>0}).map(async img=>{img.loading='eager';await img.decode()}))''')
            page.wait_for_timeout(300)
        wait_visible_previews()
        tile=panel.locator('[data-style-option]').first
        thumb=tile.locator('img.style-tile-img')
        original=thumb.get_attribute('src')
        aspect_checks=[]
        for name,width,height in [('landscape',400,160),('portrait',160,400),('square',240,240)]:
            svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect width="100%" height="100%" fill="#152a35"/><circle cx="{width/2}" cy="{height/2}" r="30" fill="#00ff00"/></svg>'
            thumb.evaluate('(e,src)=>{e.src=src;return e.decode()}', 'data:image/svg+xml,'+quote(svg))
            screenshot=tile.screenshot(path=str(ROOT/f'verification-style-aspect-{name}-v090.png'))
            im=Image.open(io.BytesIO(screenshot)).convert('RGB')
            green=[(x,y) for y in range(im.height) for x in range(im.width) if (lambda p:p[1]>220 and p[0]<25 and p[2]<25)(im.getpixel((x,y)))]
            assert green,name
            gw=max(x for x,y in green)-min(x for x,y in green)+1
            gh=max(y for x,y in green)-min(y for x,y in green)+1
            assert abs(gw-gh)<=2,(name,gw,gh)
            assert thumb.evaluate('(e)=>getComputedStyle(e).objectFit')=='cover'
            aspect_checks.append({'shape':name,'rendered_circle':[gw,gh]})
        thumb.evaluate('(e,src)=>{e.src=src;return e.decode()}',original)
        geometry=tile.evaluate('''e=>{const r=e.getBoundingClientRect(),n=e.querySelector('.style-tile-name'),nr=n.getBoundingClientRect();return {width:r.width,height:r.height,nameInside:nr.top>r.top&&nr.bottom<=r.bottom,overlay:getComputedStyle(n).position}}''')
        assert abs(geometry['width']-geometry['height'])<2 and geometry['nameInside'] and geometry['overlay']=='absolute',geometry
        results=panel.locator('.style-library-results')
        before=page.evaluate('({...viewport})')
        results.hover();page.mouse.wheel(0,900);page.wait_for_timeout(250)
        assert results.evaluate('(e)=>e.scrollTop')>0
        page.mouse.wheel(0,-1600);page.wait_for_timeout(250)
        assert results.evaluate('(e)=>e.scrollTop')==0
        assert page.evaluate('({...viewport})')==before
        page.screenshot(path=str(ROOT/'verification-style-live-v090.png'))
        for category,count in [('live',73),('3d',20),('2d',60)]:
            page.locator('[data-style-category="'+category+'"]').click()
            assert page.locator('[data-style-option]:visible').count()==count
            wait_visible_previews()
            page.screenshot(path=str(ROOT/f'verification-style-{category}-v090.png'))
        results.hover();page.mouse.wheel(0,2400);page.wait_for_timeout(250)
        assert page.locator('[data-style-option="rh-2d-american-cutout"]').is_visible()
        page.screenshot(path=str(ROOT/'verification-style-2d-bottom-v090.png'))
        page.locator('.filter-mode-control > .smart-pill').click()
        filters=page.locator('.filter-popover');filters.wait_for(state='visible')
        page.wait_for_timeout(200)
        assert filters.locator('[data-filter-option]').count()==12
        bounds=filters.bounding_box()
        assert 0<=bounds['x'] and 0<=bounds['y'] and bounds['x']+bounds['width']<=1440 and bounds['y']+bounds['height']<=960
        page.screenshot(path=str(ROOT/'verification-filter-live-v090.png'))
        page.locator('[data-filter-search]').fill('胶片')
        assert page.locator('[data-filter-option="ft-cinematic"]').is_visible()
        page.locator('[data-filter-close]').click();filters.wait_for(state='hidden')
        assert not errors,errors
        report={'runtime':base,'version':version,'style_count':153,'unique_preview_urls':len(digests),'unique_preview_files':len(digests),'filter_count':12,'wheel_down_and_up':True,'canvas_unchanged':True,'original_square_cards':geometry,'undistorted_thumbnails':aspect_checks,'runninghub_images':False,'errors':errors}
        (ROOT/'verification-style-filters-live-v090.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
        browser.close()

if __name__=='__main__':main()
