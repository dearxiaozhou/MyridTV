# -*- coding: utf-8 -*-
"""Browser regression for pure crop/outpaint geometry and canvas wrappers."""
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

    result = page.evaluate("""() => {
      const model=CanvasImageEditCropGeometryModel;
      const cropInput={x:-10,y:100,w:200,h:5,token:'preserved'};
      const crop=model.clampCrop(cropInput,{w:100,h:80});
      const minimum=model.clampCrop({x:-5,y:-7,w:2,h:3},{w:100,h:80});
      const outpaint=model.clampOutpaint({x:500,y:-5,w:160,h:130},{w:100,h:80});
      const resetCrop=model.resetRect({w:251,h:199},'crop');
      const resetOutpaint=model.resetRect({w:251,h:199},'outpaint');
      const resizeLeft=model.resizeOutpaint({x:10,y:20,w:120,h:100},'outpaint-left',-10,0,{w:100,h:80});
      const resizeTop=model.resizeOutpaint({x:10,y:20,w:120,h:100},'outpaint-top',0,-15,{w:100,h:80});
      const resizeCorner=model.resizeOutpaint({x:10,y:20,w:120,h:100},'outpaint-corner',10,15,{w:100,h:80});

      const previous={mode:imageEditMode,state:cropState,drag:cropDrag,view:{...CanvasImageEditViewportController.getState()}};
      CanvasImageEditViewportController.setBaseSize(100,80); CanvasImageEditViewportController.setZoom(1);
      imageEditMode='crop';
      cropState={x:-20,y:90,w:200,h:10,token:'kept'};
      clampCrop();
      const integratedCrop={...cropState};
      imageEditMode='outpaint';
      cropState={x:30,y:40,w:50,h:50};
      clampCrop();
      const integratedOutpaint={...cropState};
      cropState={x:10,y:20,w:120,h:100};
      cropDrag={mode:'outpaint-left',start:{...cropState}};
      resizeOutpaintFromDrag(-10,0);
      const integratedResize={...cropState};
      imageEditMode=previous.mode; cropState=previous.state; cropDrag=previous.drag;
      CanvasImageEditViewportController.setBaseSize(previous.view.baseW,previous.view.baseH);
      CanvasImageEditViewportController.setZoom(previous.view.zoom);
      return {
        module:typeof model==='object' && ['clampCrop','clampOutpaint','resetRect','resizeOutpaint'].every(name=>typeof model[name]==='function'),
        cropInput,crop,minimum,outpaint,resetCrop,resetOutpaint,resizeLeft,resizeTop,resizeCorner,
        integratedCrop,integratedOutpaint,integratedResize
      };
    }""")

    check("裁剪扩图几何模型加载且接口完整", result["module"])
    check("裁剪框限制在图片范围且保留附加状态", result["crop"] == {
        "x": 0, "y": 56, "w": 100, "h": 24, "token": "preserved"
    } and result["cropInput"] == {"x": -10, "y": 100, "w": 200, "h": 5, "token": "preserved"}, result["crop"])
    check("裁剪框保持最小尺寸", result["minimum"] == {"x": 0, "y": 0, "w": 24, "h": 24}, result["minimum"])
    check("扩图范围至少覆盖原图并限制可见原图的位置", result["outpaint"] == {
        "x": 60, "y": 0, "w": 160, "h": 130
    }, result["outpaint"])
    check("裁剪和扩图重置矩形与现有比例一致", result["resetCrop"] == {
        "x": 20, "y": 16, "w": 211, "h": 167
    } and result["resetOutpaint"] == {"x": 0, "y": 0, "w": 251, "h": 199}, result["resetCrop"])
    check("扩图边缘与角点拖动都保持中心锚点", result["resizeLeft"] == {
        "x": 20, "y": 20, "w": 140, "h": 100
    } and result["resizeTop"] == {"x": 10, "y": 35, "w": 120, "h": 130}
          and result["resizeCorner"] == {"x": 20, "y": 35, "w": 140, "h": 130}, result["resizeCorner"])
    check("画布裁剪入口委托给新几何模型", result["integratedCrop"]["x"] == 0
          and result["integratedCrop"]["y"] == 56
          and result["integratedCrop"]["w"] == 100
          and result["integratedCrop"]["h"] == 24, result["integratedCrop"])
    check("画布扩图约束与边缘拖动入口结果正确", result["integratedOutpaint"] == {
        "x": 0, "y": 0, "w": 100, "h": 80
    } and result["integratedResize"] == {"x": 20, "y": 20, "w": 140, "h": 100}, result["integratedResize"])
    check("正式服务验证会话没有画布写请求", not blocked_writes, blocked_writes)
    check("画布页面无脚本异常", not errors, errors[:3])

    screenshot = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
    if screenshot:
        page.screenshot(path=screenshot, full_page=False)
        print("SCREENSHOT: " + screenshot)
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
