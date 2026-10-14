"""Deterministic UI state baseline. No generation or real canvas writes."""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('MYRIDTV_TEST_BASE', 'http://127.0.0.1:3217')
OUT = Path(os.environ.get('MYRIDTV_UI_ARTIFACTS', '_verification/ui-baseline'))


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    # GitHub runners are several times slower than a dev box. Playwright's 5s
    # assertion default passes locally and then times out there on ordinary
    # render/sync latency, which reads as "the UI never rendered".
    expect.set_options(timeout=20000)
    results = []
    with sync_playwright() as p:
        executable = os.environ.get('MYRIDTV_TEST_BROWSER')
        if not executable and not Path(p.chromium.executable_path).exists():
            candidates = sorted((Path(os.environ.get('LOCALAPPDATA', '')) / 'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'))
            if candidates:
                executable = str(candidates[-1])
        browser = p.chromium.launch(headless=True, **({'executable_path': executable} if executable else {}))
        for theme in ('dark', 'light'):
            for width in (1100, 1680):
                label = f'{theme}-{width}'
                context = browser.new_context(viewport={'width': width, 'height': 900})
                context.set_default_timeout(20000)
                context.add_init_script(f"localStorage.setItem('studio_theme', '{theme}'); localStorage.setItem('studio_ui_scale_mode', '100');")
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                context.tracing.start(screenshots=True, snapshots=True, sources=True)
                def route_request(route):
                    request = route.request
                    path = urlsplit(request.url).path
                    if not request.url.startswith(BASE + '/'):
                        route.abort()
                    elif path == '/static/app_config.json':
                        route.fulfill(json={'proxy': {'base_url': BASE}})
                    elif request.method not in ('GET', 'HEAD'):
                        # All state is an in-memory fixture; nothing reaches a provider or user canvas.
                        route.fulfill(json={'ok': True})
                    else:
                        route.continue_()
                # Static assets must NOT pass through the Python route handler: a cold canvas
                # pulls 130+ scripts, each paying a round trip to the test process. On a slow
                # runner the browser gives up waiting, the request fails with no status, the
                # module never assigns its global and the entry script aborts mid-file (which
                # is what produced the random "CanvasXxxController is not defined" errors).
                def needs_intercept(url):
                    path = urlsplit(url).path
                    if path == '/static/app_config.json':
                        return True
                    return not (url.startswith(BASE + '/') and path.startswith('/static/'))
                page.route(needs_intercept, route_request)
                try:
                    # 'networkidle' is unreliable while every request goes through the Python
                    # route handler: a short lull between queued script requests reads as idle
                    # and goto() returns while the entry script is still executing. That is why
                    # slow runners saw "settings/viewport is not defined" - the top-level lets
                    # were still in their temporal dead zone. Wait for load + readyState instead.
                    page.goto(BASE + '/smart-canvas.html', wait_until='load')
                    # render() is a hoisted function declaration, so it already exists the moment
                    # the 17.5k-line entry script starts executing; it proves nothing. Require the
                    # top-level lets themselves (typeof throws inside the TDZ, hence try/catch).
                    page.wait_for_function(
                        "document.readyState === 'complete' && typeof CanvasParamEvents === 'object' && typeof render === 'function' && "
                        "(() => { try { return typeof settings === 'object' && typeof viewport === 'object'; } catch (e) { return false; } })()"
                    )
                    page.evaluate("""() => {
                        settings.engine = 'api'; settings.apiKind = 'video';
                        canvas = {id:'ui-fixture',title:'UI state fixture',nodes:[],connections:[],settings:{},logs:[]};
                        nodes = ['first', 'second'].map((id, i) => ({
                            id, type:'smart-image', title:'UI baseline ' + id,
                            x:100 + i * 500, y:100, w:260, h:180, scale:1,
                            images:[], status:'ready', role:'media',
                            promptDraftHtml:'Draft ' + id,
                            promptDraftText:('Long prompt / 长提示词，用于验证编辑面板。 ').repeat(12),
                            runSettings:{...settings, engine:'api', apiKind:'video', videoReferenceMode:i ? 'first_last' : 'mixed'}
                        }));
                        viewport.x = 0; viewport.y = 0; viewport.scale = 0.8;
                        render(); applyViewport();
                    }""")
                    node = page.locator('.image-node[data-id="first"]')
                    node.click(position={'x': 35, 'y': 3})
                    expect(node).to_have_class(re.compile(r'\bselected\b'))
                    expect(page.locator('#promptInput')).to_have_text('Draft first')
                    page.locator('#promptInput').fill('Edited draft first')
                    pill = page.locator('#composerReferenceModeSlot .smart-control > .smart-pill').first
                    expect(pill).to_be_visible()
                    def assert_editor_bounds(w, h):
                        page.wait_for_function("getComputedStyle(document.getElementById('composer')).opacity === '1'")
                        editor = page.locator('#composer').bounding_box()
                        assert editor and editor['x'] >= -1 and editor['y'] >= -1, editor
                        assert editor['x'] + editor['width'] <= w + 1, editor
                        assert editor['y'] + editor['height'] <= h + 1, editor
                    assert_editor_bounds(width, 900)
                    expect(pill).to_have_attribute('aria-expanded', 'false')
                    pill.click()
                    expect(pill).to_have_attribute('aria-expanded', 'true')
                    pop = page.locator('#composerReferenceModeSlot .smart-popover').first
                    expect(pop).to_be_visible()
                    bounds = pop.bounding_box()
                    assert bounds and bounds['x'] >= -1 and bounds['y'] >= -1, bounds
                    assert bounds['x'] + bounds['width'] <= width + 1, bounds
                    assert bounds['y'] + bounds['height'] <= 901, bounds
                    tools = page.locator('.canvas-tool-dock').bounding_box()
                    assert bounds['x'] >= tools['x'] + tools['width'], (bounds, tools)
                    page.screenshot(path=str(OUT / f'{label}-open.png'))
                    pill.click()
                    expect(pill).to_have_attribute('aria-expanded', 'false')
                    expect(pop).to_be_hidden()
                    pill.click()
                    page.keyboard.press('Escape')
                    expect(pill).to_have_attribute('aria-expanded', 'false')
                    expect(pop).to_be_hidden()
                    expect(pill).to_be_focused()
                    # Keyboard focus must not reopen a dismissed menu.
                    page.keyboard.press('Enter')
                    expect(pop).to_be_visible()
                    # Opening a menu then shrinking the window must re-fit it.
                    page.set_viewport_size({'width': 900, 'height': 720})
                    page.wait_for_timeout(300)
                    assert_editor_bounds(900, 720)
                    resized = pop.bounding_box()
                    assert resized and resized['x'] >= -1 and resized['y'] >= -1, resized
                    assert resized['x'] + resized['width'] <= 901, resized
                    assert resized['y'] + resized['height'] <= 721, resized
                    page.set_viewport_size({'width': width, 'height': 900})
                    page.keyboard.press('Escape')
                    # Reopen after Escape and switch nodes through real pointer input.
                    pill.click()
                    page.mouse.click(width - 30, 750)
                    expect(pop).to_be_hidden()
                    # Reopen the old owner's menu, then switch directly to another node.
                    node.click(position={'x': 35, 'y': 3})
                    pill.click()
                    second = page.locator('.image-node[data-id="second"]')
                    second.click(position={'x': 35, 'y': 3})
                    expect(second).to_have_class(re.compile(r'\bselected\b'))
                    expect(pill).to_have_attribute('aria-expanded', 'false')
                    expect(page.locator('#promptInput')).to_have_text('Draft second')
                    state = page.evaluate("CanvasStateHub.get('ui')")
                    assert state['selection']['primaryId'] == 'second' and state['editor']['nodeId'] == 'second', state
                    assert page.evaluate("nodes.find(n=>n.id==='first').promptDraftText") == 'Edited draft first'
                    assert page.evaluate("settings.videoReferenceMode") == 'first_last'
                    page.locator('#promptInput').fill('Edited draft second')
                    node.click(position={'x': 35, 'y': 3})
                    expect(page.locator('#promptInput')).to_have_text('Edited draft first')
                    second.click(position={'x': 35, 'y': 3})
                    expect(page.locator('#promptInput')).to_have_text('Edited draft second')
                    payload_keys = page.evaluate("Object.keys(buildCanvasStoragePayload())")
                    assert not set(payload_keys) & {'ui','selection','editor','canvasUiState','selectedId','selectedImage','transitions'}
                    # Canvas zoom uses real wheel events; menus must remain usable afterwards.
                    before = second.bounding_box()['width']
                    page.mouse.move(width - 40, 700)
                    page.mouse.wheel(0, -180)
                    page.wait_for_function("w => Math.abs(document.querySelector('[data-id=second]').getBoundingClientRect().width - w) > 1", arg=before)
                    assert_editor_bounds(width, 900)
                    pill.click()
                    expect(pop).to_be_visible()
                    choice = pop.locator('[data-smart-param]').first
                    choice.click()
                    page.keyboard.press('Escape')
                    expect(pop).to_be_hidden()
                    assert page.locator('.smart-control.pinned').count() == 0
                    # Group frame, connection and multi-image card overlap deliberately.
                    # Their order must survive selection and subsequent renders.
                    page.evaluate("""() => {
                        const url='data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="160" height="100"><rect width="160" height="100" fill="#6588c5"/></svg>');
                        const image={url,name:'fixture.svg',kind:'image',natural_w:160,natural_h:100};
                        nodes=[
                            {id:'frame',type:'smart-group',x:180,y:140,w:800,h:480,title:'Group frame',memberIds:['multi','single']},
                            {id:'multi',type:'smart-image',x:230,y:230,scale:1,images:[{...image},{...image,name:'second.svg'}],
                                runSettings:{...settings,engine:'api',apiKind:'image'}},
                            {id:'single',type:'smart-image',x:800,y:230,scale:1,images:[{...image}]}
                        ];
                        canvas = {...(canvas || {}), connections:[{id:'baseline-line',from:'multi',to:'single'}]};
                        selectedIds=[]; selectedId=''; viewport.x=0;viewport.y=0;viewport.scale=0.65;
                        render();applyViewport();
                    }""")
                    multi = page.locator('[data-id="multi"].image-node')
                    frame = page.locator('[data-id="frame"].image-node')
                    expect(multi).to_have_class(re.compile(r'\bmulti-image-node\b'))
                    expect(frame).to_have_class(re.compile(r'\bcanvas-group-node\b'))
                    assert not frame.evaluate("e => e.classList.contains('multi-image-node')")
                    def assert_layers():
                        layers = page.evaluate("""() => {
                            const multi=document.querySelector('[data-id=multi]');
                            const frame=document.querySelector('[data-id=frame]');
                            const line=document.querySelector('.connection-layer');
                            const image=multi.querySelector('img');
                            const r=image.getBoundingClientRect();
                            const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
                            return {frame:+getComputedStyle(frame).zIndex,line:+getComputedStyle(line).zIndex,
                                multi:+getComputedStyle(multi).zIndex,hit:!!hit && multi.contains(hit)};
                        }""")
                        assert layers['frame'] < layers['line'] < layers['multi'] and layers['hit'], layers
                    expect(multi.locator('img').first).to_be_visible()
                    assert_layers()
                    # Select the frame through its header: it must stay behind its contents.
                    frame.locator('.canvas-group-header').click(position={'x': 100, 'y': 12})
                    expect(frame).to_have_class(re.compile(r'\bselected\b'))
                    assert_layers()
                    page.evaluate('render()')
                    assert_layers()
                    multi.locator('img').first.click()
                    expect(multi).to_have_class(re.compile(r'\bselected\b'))
                    assert_layers()
                    assert_editor_bounds(width, 900)
                    image_pill = page.locator('#dynamicParams .image-spec-control > .smart-pill').first
                    image_pill.click()
                    image_menu = page.locator('#dynamicParams .image-spec-control .smart-popover').first
                    expect(image_menu).to_be_visible()
                    image_bounds = image_menu.bounding_box()
                    assert image_bounds['x'] >= tools['x'] + tools['width'], image_bounds
                    assert image_bounds['x'] + image_bounds['width'] <= width + 1, image_bounds
                    page.keyboard.press('Escape')
                    expect(image_menu).to_be_hidden()
                    expect(image_pill).to_be_focused()
                    page.evaluate("""() => {
                        const node=nodes.find(n=>n.id==='multi'); node.x=60;node.y=650;
                        render();
                    }""")
                    assert_editor_bounds(width, 900)
                    editor = page.locator('#composer').bounding_box()
                    minimap = page.locator('#minimap').bounding_box()
                    if minimap:
                        overlap = (editor['x'] < minimap['x'] + minimap['width'] and
                                   editor['x'] + editor['width'] > minimap['x'] and
                                   editor['y'] < minimap['y'] + minimap['height'] and
                                   editor['y'] + editor['height'] > minimap['y'])
                        assert not overlap, (editor, minimap)
                    page.screenshot(path=str(OUT / f'{label}-components.png'))
                    assert not errors, errors
                    results.append({'case': label, 'passed': True})
                    print('PASS - ' + label)
                except Exception as exc:
                    # Dump what the page actually looks like: on GitHub runners the failure
                    # modes differ per case and the console alone never explained them.
                    diag = {}
                    try:
                        diag = page.evaluate("""() => ({
                            slotCount: document.querySelectorAll('#composerReferenceModeSlot').length,
                            slotHtml: (document.querySelector('#composerReferenceModeSlot') || {}).outerHTML?.slice(0, 600) || '',
                            composerControls: document.querySelectorAll('#composer .smart-control').length,
                            pillCount: document.querySelectorAll('#composer .smart-pill').length,
                            missingGlobals: ['CanvasParamControls','CanvasParamEvents','CanvasUndoController',
                                'CanvasImageDropPayload','CanvasUiState','CanvasCameraLanguage','CanvasStateHub']
                                .filter(n => typeof window[n] === 'undefined'),
                            readyState: document.readyState,
                            scripts: document.scripts.length
                        })""")
                    except Exception as diag_exc:
                        diag = {'diagError': str(diag_exc)[:300]}
                    results.append({'case': label, 'passed': False, 'error': str(exc),
                                    'pageErrors': errors, 'diag': diag})
                    page.screenshot(path=str(OUT / f'{label}-failure.png'))
                    print('FAIL - ' + label + ': ' + str(exc)[:500])
                finally:
                    context.tracing.stop(path=str(OUT / f'{label}-trace.zip'))
                    context.close()
        browser.close()
    (OUT / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'RESULT: {sum(r["passed"] for r in results)}/{len(results)}')
    raise SystemExit(0 if all(r['passed'] for r in results) else 1)


if __name__ == '__main__':
    run()
