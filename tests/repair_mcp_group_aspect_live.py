"""Repair the reported group through the desktop, with a recoverable JSON backup."""
import json,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:3107'
CID='7759942';SOURCE='agent_cdd8173df624'
def read():return json.load(urllib.request.urlopen(BASE+'/api/canvases/'+CID))['canvas']
before=read()
source=next(n for n in before['nodes'] if n['id']==SOURCE)
group=next(n for n in before['nodes'] if n.get('type')=='smart-group' and n.get('mcpGroupSourceId')==SOURCE)
assert '普通居民家中' in group['title']
backup=ROOT/'_verification/mcp-group-before-v01017.json'
if not backup.exists():backup.write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding='utf-8')
members=[n for n in before['nodes'] if n['id'] in group['memberIds']]
urls={n['id']:[i['url'] for i in n['images']] for n in members}
with sync_playwright() as pw:
    browser=pw.chromium.connect_over_cdp('http://127.0.0.1:9243');page=browser.contexts[0].pages[0]
    if page.url == 'about:blank':page.wait_for_url('**/static/index.html')
    page.wait_for_load_state('networkidle')
    page.goto(BASE+'/static/smart-canvas.html?id='+CID+'&focus_node='+group['id'],wait_until='networkidle')
    for i in range(3):
        page.wait_for_function('ids=>ids.every(id=>{const n=nodes.find(n=>n.id===id),s=knownImageNaturalSize(n?.images?.[0],false);if(!s)return false;const r=nodeRect(n);return Math.abs(r.width/r.height-s.w/s.h)/(s.w/s.h)<.01&&n.cardSize.width===n.w&&n.cardSize.height===n.h})',arg=group['memberIds'])
        page.evaluate('saveCanvas()')
        current=read()
        for old in members:
            new=next(n for n in current['nodes'] if n['id']==old['id'])
            assert [i['url'] for i in new['images']]==urls[old['id']]
            assert new.get('runSettings')==old.get('runSettings')
            assert new.get('runPrompt')==old.get('runPrompt')
            assert new['cardSize']=={'width':new['w'],'height':new['h']}
        assert sum(n.get('mcpGroupSourceId')==SOURCE and n['type']=='smart-group' for n in current['nodes'])==1
        page.screenshot(path=str(ROOT/f'_verification/mcp-group-real-v01017-reload{i}.png'))
        page.reload(wait_until='networkidle')
    print(json.dumps({'ok':True,'backup':str(backup),'group_id':group['id'],'reloads':3,'members':[{k:n.get(k) for k in ['id','w','h','cardSize','cardSizing']} for n in read()['nodes'] if n['id'] in group['memberIds']]},ensure_ascii=False))
