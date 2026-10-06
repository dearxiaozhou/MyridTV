"""Verify SET mode switching through the UI against the development server.

Uses a dedicated temporary canvas and bundled sample images. No generation calls.
Set MYRIDTV_KEEP_TEST_CANVAS=1 to retain the fixture for desktop verification.
"""
import json
import os
from pathlib import Path
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get('MYRIDTV_TEST_BASE', 'http://127.0.0.1:3217')
ROOT = Path(__file__).resolve().parents[1]
CHROME = r'C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe'


def api(path, method='GET', payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def fixture():
    def image_node(node_id, title, x, y, image=None):
        return dict(id=node_id, type='smart-image', title=title, x=x, y=y,
                    w=230, h=160, scale=1, status='ready', images=[dict(
                        url=BASE + '/static/images/styles/' + image, name=image,
                        kind='image', natural_w=512, natural_h=512)] if image else [],
                    runSettings={'engine': 'api', 'apiKind': 'image'})
    a = image_node('set_a', '原有有线素材', 160, 180, 'st-clay.webp')
    b = image_node('set_b', '无线新增素材', 160, 420, 'st-flat-minimal.webp')
    b['canvasSetEnabled'] = True
    c = image_node('set_c', '下游引用节点', 600, 220)
    d = image_node('set_d', '另一个下游', 950, 220)
    return dict(title='SET 切换验证（临时）', kind='smart', nodes=[a, b, c, d],
                connections=[dict(from_='set_a', to='set_c', kind='input'),
                             dict(from_='set_a', to='set_d', kind='flow')],
                inputMode='connections', viewport={'x': 0, 'y': 0, 'scale': 1})


def main():
    assert api('/health')['ok']
    payload = fixture()
    for connection in payload['connections']:
        connection['from'] = connection.pop('from_')
    canvas_id = api('/api/canvases', 'POST', payload)['canvas']['id']
    print('TEST_CANVAS=' + canvas_id, flush=True)
    report = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=CHROME, headless=True)
            page = browser.new_page(viewport={'width': 1426, 'height': 950})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(BASE + '/static/smart-canvas.html?id=' + canvas_id)
            page.locator('[data-id="set_c"]').wait_for()

            def verify(label, condition):
                assert condition, label
                report.append(label)
                print('PASS ' + label, flush=True)

            def pick_consumer(node_id='set_c'):
                if page.locator('#canvasObjectRefPicker.open').count():
                    page.locator('.object-ref-close').click()
                page.evaluate('(id) => { selectNodeFromPointer(id); syncSelectionUi(); render(); }', node_id)
                page.locator('[data-object-ref-open]').click()
                page.locator('#canvasObjectRefPicker.open').wait_for()

            def refs(node_id='set_c'):
                return page.evaluate('(id)=>defaultInputImagesFor(nodes.find(n=>n.id===id)).map(img=>img.nodeId)', node_id)

            # Actual mode button must create checked references in each downstream picker.
            page.locator('#canvasInputModeToggle').click()
            pick_consumer()
            verify('wired source automatically checked', page.locator('[data-object-ref-pick="set_a"].is-selected').count() == 1)
            verify('source automatically SET', page.evaluate('nodes.find(n=>n.id==="set_a").canvasSetEnabled===true'))
            verify('existing thumbnail retained exactly once', refs() == ['set_a'])
            pick_consumer('set_d')
            verify('flow input checked in second consumer', page.locator('[data-object-ref-pick="set_a"].is-selected').count() == 1)
            pick_consumer()
            page.locator('[data-object-ref-pick="set_b"]').click()
            verify('wireless source appended to thumbnails', refs() == ['set_a', 'set_b'])
            page.screenshot(path=str(ROOT / 'verification-set-wireless-v0815.png'))
            page.locator('.object-ref-close').click()
            page.locator('#canvasInputModeToggle').click()
            verify('wireless source becomes input connection', page.evaluate('canvas.connections.some(c=>c.from==="set_b" && c.to==="set_c" && c.kind==="input")'))
            verify('wired thumbnails preserve order', refs() == ['set_a', 'set_b'])
            verify('wired edge rendered', page.locator('.conn-hit').count() == 3)
            page.screenshot(path=str(ROOT / 'verification-set-wired-v0815.png'))
            page.evaluate('CanvasUndoController.undo()')
            verify('undo restores mode and wireless references together', page.evaluate('canvasObjectsMode() && !canvas.connections.some(c=>c.from==="set_b" && c.to==="set_c")') and refs() == ['set_a', 'set_b'])
            page.locator('#canvasInputModeToggle').click()

            # Repeat switches, save, and reopen to verify durable state without duplication.
            for _ in range(3):
                page.locator('#canvasInputModeToggle').click()
                page.locator('#canvasInputModeToggle').click()
            verify('round trips do not duplicate connections', page.evaluate('canvas.connections.length===3'))
            page.evaluate('saveCanvas()')
            page.reload()
            page.locator('[data-id="set_c"]').wait_for()
            verify('saved wired reference survives reload', refs() == ['set_a', 'set_b'])
            page.locator('#canvasInputModeToggle').click()
            pick_consumer()
            verify('saved references remain checked', page.locator('.object-ref-item.is-selected').count() == 2)
            page.locator('[data-object-ref-pick="set_a"]').click()
            verify('uncheck removes hidden input and thumbnail', refs() == ['set_b'] and page.evaluate('!canvas.connections.some(c=>c.from==="set_a" && c.to==="set_c")'))
            page.locator('.object-ref-close').click()
            page.locator('#canvasInputModeToggle').click()
            verify('uncheck survives return to wired mode', refs() == ['set_b'])
            index = page.evaluate('canvas.connections.findIndex(c=>c.from==="set_b" && c.to==="set_c")')
            page.evaluate('(index)=>cutConnectionIndexes([index])', index)
            page.locator('#canvasInputModeToggle').click()
            pick_consumer()
            verify('wired disconnect does not revive stale wireless check', page.locator('.object-ref-item.is-selected').count() == 0 and refs() == [])
            page.locator('[data-object-ref-pick="set_b"]').click()
            page.locator('.object-ref-close').click()
            page.locator('[data-object-ref-remove]').click()
            verify('thumbnail remove clears wireless reference', refs() == [])
            verify('no application script errors', not errors)

            # Restore a useful two-input fixture for the independent desktop window check.
            page.evaluate('setCanvasInputMode("connections", {silent:true})')
            page.evaluate('connectInputNode("set_a","set_c"); render();')
            page.evaluate('saveCanvas()')
            browser.close()
        (ROOT / 'verification-set-mode-sync-v0815.json').write_text(json.dumps(
            {'base': BASE, 'canvas_id': canvas_id, 'passed': report, 'errors': errors},
            ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        if os.environ.get('MYRIDTV_KEEP_TEST_CANVAS') != '1':
            api('/api/canvases/' + canvas_id, 'DELETE')
            api('/api/canvases/' + canvas_id + '/purge', 'DELETE')


if __name__ == '__main__':
    main()
