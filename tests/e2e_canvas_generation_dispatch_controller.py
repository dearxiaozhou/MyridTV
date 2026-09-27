# -*- coding: utf-8 -*-
"""Browser regression for canvas engine dispatch and task output normalization."""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright


import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
CHROMIUM = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
VERSION = json.loads(urllib.request.urlopen(BASE + "/health", timeout=10).read())["version"]
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:300] if detail else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1680, "height": 980})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(1200)

    result = page.evaluate("""async () => {
      const calls={comfy:[],api:[],video:[],runninghub:[],polls:[]};
      const media=value=>Array.isArray(value)?value:(value?.urls||value?.videos||value?.images||value?.audios||[]);
      CanvasGenerationDispatchController.configure({
        getSettings:()=>({engine:'api',apiKind:'image'}),
        generateComfyUrlsWithSettings:async(...args)=>{calls.comfy.push(args);return {urls:['comfy://output.png'],kind:'image'};},
        isApiLikeEngine:engine=>['api','volcengine','blender'].includes(engine),
        runApiVideoGeneration:async(...args)=>{calls.video.push(args);return {taskIds:['video-job']};},
        taskIdsFromResult:value=>value?.taskIds||[],
        resultMediaUrls:media,
        pollSmartCanvasTask:async id=>{calls.polls.push(id);return id==='video-job'?{videos:['video://output.mp4']}:{images:['image://output.png']};},
        mediaKindForUrls:(urls,fallback)=>urls.some(url=>String(url).endsWith('.mp4'))?'video':fallback,
        runApiGeneration:async(...args)=>{calls.api.push(args);return {taskIds:['image-job']};},
        runRunningHubGeneration:async(...args)=>{calls.runninghub.push(args);return ['/assets/rh-output.webp'];}
      });
      const node={id:'dispatch-node'};
      const refs=[{url:'/assets/reference.png',kind:'image'}];
      const comfySettings={engine:'comfy',comfyMode:'custom'};
      const comfy=await generateUrlsForCurrentSettings(node,'comfy prompt',refs,comfySettings);
      const imageSettings={engine:'api',apiKind:'image'};
      const image=await generateUrlsForCurrentSettings(node,'image prompt',refs,imageSettings);
      const videoSettings={engine:'volcengine',apiKind:'video'};
      const video=await generateUrlsForCurrentSettings(node,'video prompt',refs,videoSettings);
      const rhSettings={engine:'runninghub',apiKind:'image'};
      const runninghub=await generateUrlsForCurrentSettings(node,'rh prompt',refs,rhSettings);
      const fallback=await CanvasGenerationDispatchController.generate(node,'fallback prompt',refs);
      const unsupported=await generateUrlsForCurrentSettings(node,'unsupported prompt',refs,{engine:'other'});
      return {module:typeof CanvasGenerationDispatchController==='object',calls,comfy,image,video,runninghub,fallback,unsupported};
    }""")

    check("生成分发控制器加载且 Comfy 请求委托一次", result["module"]
          and len(result["calls"]["comfy"]) == 1
          and result["calls"]["comfy"][0][0] == {"engine":"comfy","comfyMode":"custom"}
          and result["calls"]["comfy"][0][1] == "comfy prompt"
          and result["calls"]["comfy"][0][2] == [{"url":"/assets/reference.png","kind":"image"}]
          and result["calls"]["comfy"][0][3]["id"] == "dispatch-node"
          and result["comfy"]["urls"] == ["comfy://output.png"], result)
    check("API 图片任务轮询后归一化为图片输出", result["image"] == {"urls":["image://output.png"],"kind":"image"}
          and result["calls"]["api"][0][0] == "image prompt"
          and result["calls"]["api"][0][1] == [{"url":"/assets/reference.png","kind":"image"}]
          and result["calls"]["api"][0][2] == {"engine":"api","apiKind":"image"}
          and result["calls"]["api"][0][3]["id"] == "dispatch-node", result["image"])
    check("API 视频任务轮询后归一化为视频输出", result["video"] == {"urls":["video://output.mp4"],"kind":"video"}
          and result["calls"]["video"][0][0] == "video prompt"
          and result["calls"]["video"][0][1] == [{"url":"/assets/reference.png","kind":"image"}]
          and result["calls"]["video"][0][2] == {"engine":"volcengine","apiKind":"video"}, result["video"])
    check("RunningHub 路由保留直接媒体结果", result["runninghub"] == {"urls":["/assets/rh-output.webp"],"kind":"image"}
          and len(result["calls"]["runninghub"]) == 1, result["runninghub"])
    check("未配置引擎不产生任务，返回空结果", result["unsupported"] == {"urls":[],"kind":"image"}, result["unsupported"])
    check("默认 settings 从注入上下文取得", result["fallback"] == {"urls":["image://output.png"],"kind":"image"}
          and result["calls"]["polls"].count("image-job") == 2, result["fallback"])
    check("两种异步输出任务均完成轮询", sorted(result["calls"]["polls"]) == ["image-job","image-job","video-job"], result["calls"]["polls"])
    check("生成分发流程无页面脚本异常", not errors, errors[:3])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
