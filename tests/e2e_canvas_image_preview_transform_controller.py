# -*- coding: utf-8 -*-
"""Browser regression for preview zoom, pan, and wheel interaction."""
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
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    outcome = page.evaluate("""() => {
      const controller=CanvasImagePreviewTransformController;
      const frame=document.getElementById('previewFrame');
      const originalRect=frame.getBoundingClientRect.bind(frame);
      frame.getBoundingClientRect=()=>({left:100,top:50,width:400,height:200,right:500,bottom:250});
      let panorama=false, labels=0;
      controller.configure({getFrame:()=>frame,isPanoramaEnabled:()=>panorama,updateZoomLabel:()=>labels++});
      const state=()=>({zoom:controller.getState().zoom,pan:{...controller.getState().pan}});
      controller.reset();
      const initial={state:state(),transform:frame.style.transform};
      controller.zoomAt(400,150,frame.getBoundingClientRect(),2);
      const anchored={state:state(),transform:frame.style.transform};
      controller.setPan({x:25,y:-15});
      const panned={state:state(),transform:frame.style.transform};
      controller.zoomAt(300,150,frame.getBoundingClientRect(),100);
      const maxZoom=state().zoom;
      controller.reset();
      controller.zoomAt(300,150,frame.getBoundingClientRect(),0.001);
      const minZoom=state().zoom;
      panorama=true; controller.apply();
      const panoramaTransform=frame.style.transform;

      panorama=false; imageEditMode='preview';
      imageEditModal.classList.add('open');
      controller.reset();
      const target=frame;
      const wheel=new WheelEvent('wheel',{deltaY:-100,clientX:400,clientY:150,bubbles:true,cancelable:true});
      target.dispatchEvent(wheel);
      const wheelResult={prevented:wheel.defaultPrevented,state:state()};
      const zoomBeforeButton=state().zoom;
      const button=document.createElement('button');
      frame.appendChild(button);
      const buttonWheel=new WheelEvent('wheel',{deltaY:-100,clientX:400,clientY:150,bubbles:true,cancelable:true});
      button.dispatchEvent(buttonWheel);
      const buttonResult={zoomBefore:zoomBeforeButton,zoomAfter:state().zoom};
      button.remove();
      imageEditModal.classList.remove('open');
      frame.getBoundingClientRect=originalRect;
      controller.reset();
      return {initial,anchored,panned,maxZoom,minZoom,panoramaTransform,wheelResult,buttonResult,labels};
    }""")

    check("初始状态为原始比例且无位移", outcome["initial"] == {
        "state": {"zoom": 1, "pan": {"x": 0, "y": 0}}, "transform": "translate(0px, 0px) scale(1)"
    }, outcome["initial"])
    check("缩放围绕鼠标位置保持画面锚点", outcome["anchored"] == {
        "state": {"zoom": 2, "pan": {"x": -100, "y": 0}}, "transform": "translate(-100px, 0px) scale(2)"
    }, outcome["anchored"])
    check("拖移位移同步更新 CSS 变换", outcome["panned"] == {
        "state": {"zoom": 2, "pan": {"x": 25, "y": -15}}, "transform": "translate(25px, -15px) scale(2)"
    }, outcome["panned"])
    check("放大和缩小均被限制在可用范围", outcome["maxZoom"] == 12 and outcome["minZoom"] == 0.05,
          {"max": outcome["maxZoom"], "min": outcome["minZoom"]})
    check("全景模式不叠加普通预览变换", outcome["panoramaTransform"] == "", outcome["panoramaTransform"])
    check("正式预览滚轮缩放委托给变换控制器并阻止页面滚动",
          outcome["wheelResult"]["prevented"] and abs(outcome["wheelResult"]["state"]["zoom"]-1.12)<1e-9,
          outcome["wheelResult"])
    check("预览工具按钮上的滚轮不会误触发图片缩放", outcome["buttonResult"]["zoomAfter"] == outcome["buttonResult"]["zoomBefore"], outcome["buttonResult"])
    check("缩放变化会刷新界面比例标签", outcome["labels"] >= 5, outcome["labels"])
    check("正式服务验收会话没有画布写请求", not blocked_writes, blocked_writes)
    check("画布页面无脚本异常", not errors, errors[:3])

    screenshot = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
    if screenshot:
        page.screenshot(path=screenshot, full_page=False)
        print("SCREENSHOT: " + screenshot)
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
