"""Verify the real desktop catalog and import currently offered MiMo chat models."""
import json
from pathlib import Path
import urllib.request
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:3107'
with sync_playwright() as pw:
    browser=pw.chromium.connect_over_cdp('http://127.0.0.1:9235')
    page=browser.contexts[0].pages[0]
    page.goto(BASE+'/static/api-settings.html',wait_until='networkidle')
    pid=page.evaluate("providers.find(p=>(p.base_url||'').includes('xiaomimimo.com')).id")
    page.evaluate('id=>selectProvider(id)',pid)
    with page.expect_response(lambda r:'/api/providers/fetch-models' in r.url) as response:
        page.locator('#fetchModelsBtn').click()
    result=response.value.json()
    assert result['ok'] and len(result['all'])>=9,result
    page.locator('#modelPickerOverlay').wait_for(state='visible')
    assert page.evaluate("Object.keys(pickerState.category).includes('mimo-v2.6-pro')")
    for model in result['chat_models']:
        if not page.evaluate('id=>pickerState.selected[id]',model):
            page.locator('.picker-row').filter(has=page.locator('[title="'+model+'"]')).click()
    page.screenshot(path=str(ROOT/'_verification/mimo-real-catalog-v01015.png'))
    page.evaluate('applyModelPicker()')
    page.evaluate("selectApiModelTab('chat')")
    assert page.locator('#chatModelList .model-value-input').count()>=5
    with page.expect_response(lambda r:r.url.endswith('/api/providers') and r.request.method=='PUT') as response:
        page.locator('#saveModelsBtn').click()
    assert response.value.ok
    saved=next(p for p in json.load(urllib.request.urlopen(BASE+'/api/providers'))['providers'] if p['id']==pid)
    assert set(result['chat_models'])<=set(saved['chat_models'])
    page.reload(wait_until='networkidle');page.evaluate('id=>selectProvider(id)',pid)
    page.evaluate("selectApiModelTab('chat')")
    page.wait_for_timeout(650)
    page.screenshot(path=str(ROOT/'_verification/mimo-saved-models-v01015.png'))
    page.goto(BASE+'/static/smart-canvas.html',wait_until='networkidle')
    page.wait_for_function('id=>providerChatModels(id).length>=5',arg=pid)
    print(json.dumps({'ok':True,'catalog_count':len(result['all']),'saved_chat_models':saved['chat_models'],'canvas_models':page.evaluate('id=>providerChatModels(id)',pid)},ensure_ascii=False))
