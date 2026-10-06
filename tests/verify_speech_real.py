"""Explicit real-provider check: submits the chosen existing speech node once."""
from pathlib import Path
import argparse
import json,time,urllib.request
from playwright.sync_api import sync_playwright
parser=argparse.ArgumentParser();parser.add_argument('--canvas',required=True);parser.add_argument('--node',required=True);args=parser.parse_args()
ROOT=Path(__file__).resolve().parents[1];base='http://127.0.0.1:3107';cid=args.canvas;nid=args.node
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path=r'C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe',headless=True)
 page=browser.new_page(viewport={'width':1600,'height':1100});errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
 page.goto(base+'/static/smart-canvas.html?id='+cid)
 node=page.locator(f'.speech-smart-node[data-id="{nid}"]');node.wait_for();page.evaluate('fitAllNodesViewport()')
 start=time.monotonic();node.locator('[data-speech-run]').click();print('Submitted original speech node once with the configured TLS 1.2 transport',flush=True)
 try:
  page.wait_for_function('(id)=>!CanvasSpeech.isActive(id)',arg=nid,timeout=250000)
  result=page.evaluate('(id)=>{const n=nodes.find(n=>n.id===id);return {error:n.speechError,output:n.images?.[0]};}',nid)
  if result.get('error'):raise RuntimeError(result['error'])
  player=node.locator('.speech-output audio');player.wait_for();page.wait_for_function('(id)=>document.querySelector(`.speech-smart-node[data-id="${id}"] .speech-output audio`).readyState>=1',arg=nid)
  node.locator('.speech-output [data-audio-toggle]').click();page.wait_for_function('(id)=>!document.querySelector(`.speech-smart-node[data-id="${id}"] .speech-output audio`).paused',arg=nid)
  duration=player.evaluate('el=>el.duration');assert duration>0
  page.screenshot(path=str(ROOT/'verification-speech-real-v0813.png'))
  assert page.evaluate('saveCanvas()');page.wait_for_timeout(1000)
  with urllib.request.urlopen(base+'/api/canvases/'+cid) as response:stored=json.load(response)['canvas']
  saved=next(n for n in stored['nodes'] if n['id']==nid);assert not saved.get('speechError') and saved['images'][0]['url']==result['output']['url']
  with urllib.request.urlopen(base+result['output']['url']) as response:raw=response.read()
  assert len(raw)>1000 and result['output']['format']=='mp3'
  print('PASS real MiMo design: playable MP3, original node saved, old error cleared; duration',round(duration,3),'seconds; bytes',len(raw),'elapsed',round(time.monotonic()-start,1),'sec',flush=True)
  print('AUDIO_OUTPUT',result['output']['local_path'],flush=True)
  assert not errors,errors
 except Exception:
  page.screenshot(path=str(ROOT/'verification-speech-real-v0813.png'));raise
 finally:browser.close()
