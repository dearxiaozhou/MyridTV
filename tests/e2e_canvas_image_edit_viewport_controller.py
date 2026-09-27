# -*- coding: utf-8 -*-
"""Browser regression for crop/outpaint viewport sizing and zoom coordination."""
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
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    outcome = page.evaluate("""() => {
      const controller=CanvasImageEditViewportController;
      const classes=()=>{const values=new Set();return {values,toggle(name,value){value?values.add(name):values.delete(name);},contains(name){return values.has(name);}};};
      const image={style:{},naturalWidth:4000,naturalHeight:2000,
        get clientWidth(){return parseFloat(this.style.width)||0;},get clientHeight(){return parseFloat(this.style.height)||0;}};
      const draw={style:{}},text={style:{}};
      const cropCanvas={style:{},classList:classes(),getBoundingClientRect:()=>({width:1100,height:650})};
      const cropBox={style:{}},outpaintFrame={style:{}},resolution={textContent:''},zoomLabel={textContent:''};
      const stage={clientWidth:900,clientHeight:500,scrollLeft:35,scrollTop:48,classList:classes()};
      const calls={resize:0,clamp:0,grid:0,panoramaReset:0,previewReset:0};
      let mode='crop',crop={x:100,y:50,w:600,h:300},panorama={enabled:false,fov:75};
      controller.reset();
      controller.configure({getImage:()=>image,getDrawCanvas:()=>draw,getTextCanvas:()=>text,getStage:()=>stage,
        getCropCanvas:()=>cropCanvas,getCropBox:()=>cropBox,getOutpaintFrame:()=>outpaintFrame,
        getOutpaintResolution:()=>resolution,getZoomLabel:()=>zoomLabel,getMode:()=>mode,getCropState:()=>crop,
        getWindowSize:()=>({width:1000,height:800}),getPreviewZoom:()=>1.5,getPanorama:()=>panorama,
        resizeDrawCanvas:()=>calls.resize++,clampCrop:()=>calls.clamp++,refreshGridSplitPreview:()=>calls.grid++,
        exceedsFourKStandard:(w,h)=>w>4096||h>4096,resetPanoramaView:()=>calls.panoramaReset++,
        resetPreviewTransform:()=>calls.previewReset++});
      controller.ensureBaseSize();
      const initial={...controller.getState(),size:controller.displaySize()};
      controller.setZoom(1.5);controller.applyZoom(1.5);
      const zoomed={state:{...controller.getState()},image:{width:image.style.width,height:image.style.height},crop:{...crop},
        display:controller.displaySize(),
        overflowX:stage.classList.contains('overflow-x'),overflowY:stage.classList.contains('overflow-y'),
        zoomLabel:zoomLabel.textContent,resizes:calls.resize,clamps:calls.clamp};
      mode='outpaint';crop={x:100,y:70,w:1600,h:900};controller.renderCropBox();
      const outpaint={image:{position:image.style.position,left:image.style.left,top:image.style.top},
        cropCanvas:{width:cropCanvas.style.width,height:cropCanvas.style.height},draw:{...draw.style},text:{...text.style},
        box:{...cropBox.style},frame:{...outpaintFrame.style},resolution:resolution.textContent,
        warning:cropCanvas.classList.contains('outpaint-warning'),natural:controller.outpaintNaturalSize()};
      mode='crop';controller.renderCropBox();
      const cropMode={image:{position:image.style.position,left:image.style.left,top:image.style.top},
        canvas:{width:cropCanvas.style.width,height:cropCanvas.style.height},frame:{...outpaintFrame.style}};
      crop={x:12,y:18,w:200,h:100};controller.resetZoom();
      const reset={zoom:controller.getZoom(),width:image.style.width,height:image.style.height,
        scrollLeft:stage.scrollLeft,scrollTop:stage.scrollTop,zoomLabel:zoomLabel.textContent};
      mode='preview';panorama={enabled:true,fov:50};controller.resetZoom();
      const panoramaReset=calls.panoramaReset;
      panorama={enabled:false,fov:75};controller.resetZoom();
      const previewReset=calls.previewReset;
      controller.setZoom(2);controller.setBaseSize(900,450);image.style.width='1px';image.style.height='1px';
      const fallbackSize=controller.displaySize();
      return {initial,zoomed,outpaint,cropMode,reset,panoramaReset,previewReset,fallbackSize,
        counts:calls};
    }""")

    check("按窗口限制初始化基准尺寸并提供显示尺寸", outcome["initial"]["baseW"] == 900
          and outcome["initial"]["baseH"] == 450 and outcome["initial"]["size"] == {"w":900,"h":450}, outcome["initial"])
    check("编辑缩放同步图像、裁剪框、叠层和溢出标记", outcome["zoomed"]["image"] == {"width":"1350px","height":"675px"}
          and outcome["zoomed"]["crop"] == {"x":150,"y":75,"w":900,"h":450}
          and outcome["zoomed"]["overflowX"] and outcome["zoomed"]["overflowY"]
          and outcome["zoomed"]["zoomLabel"] == "150%" and outcome["zoomed"]["resizes"] == 1, outcome["zoomed"])
    check("扩图视图将图片和绘制层同步定位并显示自然分辨率警示", outcome["outpaint"]["image"] == {
        "position":"absolute","left":"100px","top":"70px"}
          and outcome["outpaint"]["draw"] == {"left":"100px","top":"70px"}
          and outcome["outpaint"]["text"] == {"left":"100px","top":"70px"}
          and outcome["outpaint"]["resolution"].split(" x ")[0] == "4741"
          and outcome["outpaint"]["warning"], outcome["outpaint"])
    check("离开扩图后清除偏移和扩图尺寸并还原裁剪框坐标", outcome["cropMode"]["image"] == {
        "position":"","left":"","top":""} and outcome["cropMode"]["canvas"] == {"width":"","height":""}
          and outcome["cropMode"]["frame"]["left"] == "100px", outcome["cropMode"])
    check("重置编辑缩放恢复百分比和工作区滚动位置", outcome["reset"]["zoom"] == 1
          and outcome["reset"]["width"] == "900px" and outcome["reset"]["scrollLeft"] == 0
          and outcome["reset"]["scrollTop"] == 0 and outcome["reset"]["zoomLabel"] == "100%", outcome["reset"])
    check("预览重置按全景开关分流且小尺寸回退基于自然尺寸", outcome["panoramaReset"] == 1
          and outcome["previewReset"] == 1 and outcome["fallbackSize"] == {"w":1800,"h":900}, outcome)
    check("正式服务验收会话没有画布写请求", not blocked_writes, blocked_writes)
    check("画布页面无脚本异常", not errors, errors[:3])

    screenshot = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
    if screenshot:
        page.screenshot(path=screenshot, full_page=False)
        print("SCREENSHOT: " + screenshot)
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
