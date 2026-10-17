"""Exercise real canvas upload UI/API and inspect files in all output folders."""
import argparse
import atexit
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import unquote
import wave
import uuid
import urllib.request

from playwright.sync_api import sync_playwright
from verify_canvas_overwrite import fixture_png

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import myridtv_video_codec

OUT = ROOT / '_verification/media-reuse'


def cleanup_canvas(base, canvas_id, title):
    url=base+'/api/canvases/'+canvas_id
    current=json.load(urllib.request.urlopen(url))['canvas']
    if current['title'] != title:
        raise RuntimeError('Verification canvas identity changed; cleanup stopped')
    urllib.request.urlopen(urllib.request.Request(url,method='DELETE')).close()
    urllib.request.urlopen(urllib.request.Request(url+'/purge',method='DELETE')).close()
    print('Verification canvas and its fixture output folder cleaned up')


def verify(base, assets, runtime, cleanup=False):
    image = runtime / 'picture.png'
    image.write_bytes(fixture_png('#6288c9'))
    audio = runtime / 'voice.wav'
    with wave.open(str(audio), 'wb') as wav:
        wav.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        wav.writeframes(b'\0\0' * 4000)
    video = runtime / 'clip.mp4'
    subprocess.run([myridtv_video_codec.ffmpeg_path(), '-y', '-f', 'lavfi', '-i',
                    'color=c=blue:s=64x48:d=0.5', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                    str(video)], check=True, capture_output=True)
    document = runtime / 'notes.txt'
    document.write_text('Upload reuse verification', encoding='utf-8')
    results = {}
    with sync_playwright() as p:
        candidates = sorted((Path(os.environ['LOCALAPPDATA']) / 'ms-playwright').glob('chromium-*/chrome-win*/chrome.exe'))
        browser = p.chromium.launch(headless=True, executable_path=str(candidates[-1]))
        page = browser.new_page(viewport={'width':1440, 'height':1000})
        request = page.request
        title='Upload reuse verification '+uuid.uuid4().hex[:8]
        response = request.post(base+'/api/canvases', data={'title':title, 'nodes':[], 'connections':[]})
        assert response.ok, response.text()
        canvas = response.json()['canvas']
        if cleanup:
            atexit.register(cleanup_canvas,base,canvas['id'],title)
        endpoint = base+'/api/ai/upload?scope=canvas&canvas_id='+canvas['id']
        page.route('**/static/app_config.json*', lambda r:r.fulfill(json={'proxy':{'base_url':base}}))
        page.goto(base+'/smart-canvas.html?id='+canvas['id'], wait_until='networkidle')
        for path, mime, folder in [(image,'image/png','images'), (audio,'audio/wav','audios'),
                                    (video,'video/mp4','videos'), (document,'text/plain','files')]:
            def upload(source):
                response = request.post(endpoint, multipart={'files':{'name':source.name,'mimeType':mime,'buffer':source.read_bytes()}})
                assert response.ok, response.text()
                return response.json()['files'][0]
            first = upload(path)
            local = assets / unquote(first['url'].split('/assets/',1)[1])
            assert local.parent.name == folder and local.exists(), first
            before = {f.name:(f.read_bytes(), f.stat().st_mtime_ns) for f in local.parent.iterdir() if f.is_file()}
            if folder != 'files':
                # Real file-input event, real frontend routing, no upload/provider mocks.
                with page.expect_response(lambda r:'/api/ai/upload?' in r.url and r.request.method=='POST') as event:
                    page.locator('#fileInput').set_input_files(str(local))
                returned = event.value.json()['files'][0]
                page.wait_for_function('url => nodes.some(n=>(n.images||[]).some(i=>i.url===url))', arg=first['url'])
            else:
                returned = upload(local)
            after = {f.name:(f.read_bytes(), f.stat().st_mtime_ns) for f in local.parent.iterdir() if f.is_file()}
            assert returned['reused'] and returned['url']==first['url'], returned
            assert before==after, folder
            changed = request.post(endpoint, multipart={'files':{'name':path.name,'mimeType':mime,'buffer':b'different content'}}).json()['files'][0]
            repeated = request.post(endpoint, multipart={'files':{'name':path.name,'mimeType':mime,'buffer':b'different content'}}).json()['files'][0]
            assert changed['url'] != first['url'] and repeated['url']==changed['url'] and repeated['reused']
            assert local.read_bytes()==before[local.name][0]
            assert len([f for f in local.parent.iterdir() if f.is_file()])==2
            results[folder]={'sameFileReused':True,'bytesAndTimestampUnchanged':True,'differentContentProtected':True,'repeatCollisionReused':True}
        for name, source, kind, folder in [('voice.aac',audio,'audio','audios'),('clip.m4v',video,'video','videos')]:
            payload={'files':{'name':name,'mimeType':'application/octet-stream','buffer':source.read_bytes()}}
            first=request.post(endpoint,multipart=payload).json()['files'][0]
            local=assets / unquote(first['url'].split('/assets/',1)[1])
            before=local.stat().st_mtime_ns
            second=request.post(endpoint,multipart=payload).json()['files'][0]
            assert first['kind']==kind and local.parent.name==folder
            assert second['reused'] and second['url']==first['url'] and local.stat().st_mtime_ns==before
        results['unknownMimeFormats']={'aacAudioReused':True,'m4vVideoReused':True}
        page.screenshot(path=str(OUT/'canvas.png'))
        browser.close()
    (OUT/'results.json').write_text(json.dumps({'base':base,'passed':True,'folders':results},indent=2),encoding='utf-8')
    print('PASS - real UI image/audio/video imports and file upload API; all four folders reuse unchanged files')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base')
    parser.add_argument('--assets')
    args=parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='myrid-media-reuse-') as tmp:
        runtime=Path(tmp)
        if args.base:
            verify(args.base, Path(args.assets), runtime, cleanup=True)
            return
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0))
            port=probe.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        assets=runtime/'assets'
        env={**os.environ,'MYRIDTV_TEST_PORT':str(port),'MYRIDTV_TEST_DATA_DIR':str(runtime/'userdata'),
             'MYRIDTV_ASSETS_DIR':str(assets),'PYTHONUTF8':'1'}
        with (OUT/'server.log').open('w',encoding='utf-8') as log:
            server=subprocess.Popen([sys.executable,str(ROOT/'tests/launch_test_instance.py')],cwd=ROOT,env=env,stdout=log,stderr=log)
            try:
                import urllib.request
                for _ in range(60):
                    try:
                        urllib.request.urlopen(base+'/health',timeout=.5).close()
                        break
                    except OSError:
                        time.sleep(.2)
                else:
                    raise RuntimeError('Server not ready')
                verify(base, assets, runtime)
            finally:
                server.terminate()
                server.wait(timeout=10)


if __name__=='__main__':
    main()
