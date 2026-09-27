# -*- coding: utf-8 -*-
"""Browser regression for preview wheel routing and listener binding."""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright


BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217").rstrip("/")
CHROMIUM = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
VERSION = json.loads(urllib.request.urlopen(BASE + "/health", timeout=10).read())["version"]
results = []
blocked_writes = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:300] if detail else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/*", lambda route: (
        blocked_writes.append({"method": route.request.method, "url": route.request.url})
        or route.fulfill(status=204, body="")
    ) if route.request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} else route.continue_())
    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({"proxy": {"base_url": BASE}})))
    page.add_init_script("""
      window.__previewWheelRegistrations=[];
      const tracked=new Set(['imageEditStage','previewStage','previewFrame','previewCurrentImage',
        'previewCurrentVideo','panoramaStage','panoramaCanvas']);
      const original=EventTarget.prototype.addEventListener;
      EventTarget.prototype.addEventListener=function(type,listener,options){
        if(type==='wheel' && tracked.has(this.id)) window.__previewWheelRegistrations.push({
          id:this.id,passive:typeof options==='object' ? Boolean(options.passive) : false,
          capture:typeof options==='object' ? Boolean(options.capture) : Boolean(options)
        });
        return original.call(this,type,listener,options);
      };
    """)
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    outcome = page.evaluate("""() => {
      const controller=CanvasImagePreviewInteractionController;
      const stage={getBoundingClientRect:()=>({left:10,top:20,width:400,height:300})};
      const imageStage={};
      const frame={getBoundingClientRect:()=>({left:25,top:30,width:200,height:100})};
      const state={fov:99};
      const calls={locked:0,seeks:[],zooms:[],labels:0};
      let open=true,mode='preview',panorama=false,videoReady=true;
      const previewTarget={closest(selector){
        if(selector.startsWith('button, input')) return null;
        return selector.includes('#previewStage') ? stage : null;
      }};
      const buttonTarget={closest(selector){return selector.startsWith('button, input') ? {} : null;}};
      const outsideTarget={closest:()=>null};
      function wheel(target,deltaY,extra={}){
        const event={target,currentTarget:null,deltaY,clientX:80,clientY:90,
          prevented:0,stopped:0,immediate:0,preventDefault(){this.prevented++;},
          stopPropagation(){this.stopped++;},stopImmediatePropagation(){this.immediate++;},
          composedPath:()=>[],...extra};
        return {event,result:controller.handleWheel(event)};
      }
      controller.configure({isModalOpen:()=>open,getMode:()=>mode,getPreviewStage:()=>stage,
        getImageStage:()=>imageStage,getFrame:()=>frame,isPanoramaEnabled:()=>panorama,
        getPanoramaState:()=>state,seekVideoFrames:direction=>{calls.seeks.push(direction);return videoReady;},
        lockRootScroll:()=>calls.locked++,updateZoomLabel:()=>calls.labels++,
        zoomAt:(x,y,rect,factor)=>calls.zooms.push({x,y,rect,factor})});

      const closed=(()=>{open=false;const r=wheel(previewTarget,1);open=true;return r;})();
      const wrongMode=(()=>{mode='crop';const r=wheel(previewTarget,1);mode='preview';return r;})();
      const control=wheel(buttonTarget,1);
      const outside=wheel(outsideTarget,1);
      const video=wheel(previewTarget,1);
      const beforeRepeat=calls.locked;
      const repeated=controller.handleWheel(video.event);
      const repeatDidNotLock=calls.locked===beforeRepeat;
      videoReady=false;
      panorama=true;
      const panoramaHigh=wheel(previewTarget,1);
      const panoramaHighClamped=state.fov===100;
      state.fov=36;
      const panoramaLow=wheel(previewTarget,-1);
      const panoramaLowClamped=state.fov===35;
      panorama=false;
      const image=wheel(previewTarget,-1);
      const firstBind=controller.bindWheelListeners(['imageEditStage','previewStage','previewFrame','previewCurrentImage',
        'previewCurrentVideo','panoramaStage','panoramaCanvas']);
      const secondBind=controller.bindWheelListeners(['previewStage']);
      return {closed:closed.result,wrongMode:wrongMode.result,control:control.result,outside:outside.result,
        video:video.result,videoPrevented:video.event.prevented,videoDelta:calls.seeks[0],
        repeated,repeatDidNotLock,
        panoramaHighClamped,panoramaLowClamped,panoramaHandled:panoramaHigh.result&&panoramaLow.result,
        image:image.result,zoom:calls.zooms[0],labels:calls.labels,locked:calls.locked,
        firstBind,secondBind,listeners:window.__previewWheelRegistrations,listenerState:controller.getState().listenersBound};
    }""")

    check("非预览模式、控件和画布外滚轮不会被截走", not outcome["closed"] and not outcome["wrongMode"]
          and not outcome["control"] and not outcome["outside"], outcome)
    check("视频预览滚轮转成逐帧前进并阻止默认滚动", outcome["video"] and outcome["videoDelta"] == 1
          and outcome["videoPrevented"] == 1 and outcome["repeated"] and outcome["repeatDidNotLock"], outcome)
    check("全景滚轮视角限制在允许范围", outcome["panoramaHandled"] and outcome["panoramaHighClamped"]
          and outcome["panoramaLowClamped"] and outcome["labels"] == 2, outcome)
    check("普通图片滚轮按鼠标位置缩放预览", outcome["image"] and outcome["zoom"]["x"] == 80
          and outcome["zoom"]["y"] == 90 and outcome["zoom"]["factor"] == 1.12
          and outcome["zoom"]["rect"] == {"left":25,"top":30,"width":200,"height":100}, outcome["zoom"])
    captured = [item for item in outcome["listeners"] if item["capture"]]
    check("全部预览元素均绑定非被动捕获监听，重复绑定会跳过", not outcome["firstBind"] and not outcome["secondBind"]
          and outcome["listenerState"] and len(captured) >= 7
          and len({item["id"] for item in captured}) == 7
          and all(not item["passive"] for item in captured),
          {"first":outcome["firstBind"],"second":outcome["secondBind"],"bound":outcome["listenerState"],
           "capturedIds":[item["id"] for item in captured],
           "otherWheelListeners":[item for item in outcome["listeners"] if not item["capture"]]})
    check("正式服务验收会话没有画布写请求", not blocked_writes, blocked_writes)
    check("画布页面无脚本异常", not errors, errors[:3])

    screenshot = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
    if screenshot:
        page.screenshot(path=screenshot, full_page=False)
        print("SCREENSHOT: " + screenshot)
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
