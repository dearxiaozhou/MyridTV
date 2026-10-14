"""Exercise real file-input uploads against an isolated running application."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import unquote

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '_verification' / 'upload-reuse'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='myrid-upload-reuse-') as tmp:
        runtime = Path(tmp)
        assets = runtime / 'assets'
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        env = {**os.environ, 'MYRIDTV_TEST_PORT': str(port),
               'MYRIDTV_TEST_DATA_DIR': str(runtime / 'userdata'),
               'MYRIDTV_ASSETS_DIR': str(assets), 'PYTHONUTF8': '1'}
        with (OUT / 'server.log').open('w', encoding='utf-8') as log:
            server = subprocess.Popen([sys.executable, str(ROOT / 'tests/launch_test_instance.py')],
                                      cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                with sync_playwright() as p:
                    request = p.request.new_context(base_url=base)
                    for _ in range(60):
                        try:
                            if request.get('/health', timeout=500).ok:
                                break
                        except Exception:
                            pass
                        if server.poll() is not None:
                            raise RuntimeError('Isolated server exited; see server.log')
                        time.sleep(0.2)
                    else:
                        raise RuntimeError('Isolated server did not become ready')
                    response = request.post('/api/canvases', data={'name': 'Upload reuse verification', 'nodes': [], 'connections': []})
                    assert response.ok, response.text()
                    canvas_id = response.json()['canvas']['id']
                    source = runtime / 'sample.png'
                    Image.new('RGB', (64, 48), '#6288c9').save(source)
                    executable = os.environ.get('MYRIDTV_TEST_BROWSER')
                    if not executable and not Path(p.chromium.executable_path).exists():
                        candidates = sorted((Path(os.environ.get('LOCALAPPDATA', '')) / 'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'))
                        if candidates:
                            executable = str(candidates[-1])
                    browser = p.chromium.launch(headless=True, **({'executable_path': executable} if executable else {}))
                    page = browser.new_page(viewport={'width': 1280, 'height': 900})
                    page.route('**/static/app_config.json*', lambda r: r.fulfill(json={'proxy': {'base_url': base}}))
                    page.goto(base + '/smart-canvas.html?id=' + canvas_id, wait_until='networkidle')
                    def upload(path):
                        with page.expect_response(lambda r: '/api/ai/upload?' in r.url and r.request.method == 'POST') as result:
                            page.locator('#fileInput').set_input_files(str(path))
                        assert result.value.ok, result.value.text()
                        return result.value.json()['files'][0]
                    first = upload(source)
                    local = assets / unquote(first['url'].split('/assets/', 1)[1])
                    assert local.is_file(), first
                    before = sorted(p.name for p in local.parent.iterdir())
                    stamp = local.stat().st_mtime_ns
                    second = upload(local)  # Select the file from the canvas's own output folder.
                    assert second['reused'] and first['url'] == second['url'], (first, second)
                    assert sorted(p.name for p in local.parent.iterdir()) == before
                    assert local.stat().st_mtime_ns == stamp
                    page.wait_for_function("() => [...document.querySelectorAll('.image-node img')].some(i=>i.complete && i.naturalWidth===64)")
                    page.screenshot(path=str(OUT / 'same-folder-upload.png'))
                    # Same basename, different image: preserve both files.
                    Image.new('RGB', (64, 48), '#cd7055').save(source)
                    third = upload(source)
                    assert not third['reused'] and third['url'] != first['url'], third
                    assert len(list(local.parent.iterdir())) == len(before) + 1
                    assert local.stat().st_mtime_ns == stamp
                    report = {'passed': True, 'sameFolderReused': True, 'existingFileUnchanged': True,
                              'sameNameDifferentImagePreserved': True, 'filesAfterSameFolderUpload': before,
                              'firstUrl': first['url'], 'reusedUrl': second['url'], 'differentUrl': third['url']}
                    (OUT / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                    browser.close()
                    request.dispose()
                    print('PASS - same-folder upload reuses original; different content remains separate; image renders')
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__ == '__main__':
    main()
