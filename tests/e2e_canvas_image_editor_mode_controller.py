# -*- coding: utf-8 -*-
"""Browser regression for image editor mode and toolbar synchronization."""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright


BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
CHROMIUM = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
VERSION = json.loads(urllib.request.urlopen(BASE + "/health", timeout=10).read())["version"]
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:300] if detail else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    blocked_writes = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def route_request(route):
        request = route.request
        if "/static/app_config.json" in request.url:
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"proxy": {"base_url": BASE}}))
        elif request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            blocked_writes.append({"method": request.method, "url": request.url})
            route.abort()
        else:
            route.continue_()

    page.route("**/*", route_request)
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(700)

    result = page.evaluate("""() => {
      const state={kind:'image',mode:'preview',touched:false,panorama:false};
      const calls={removeText:0,wheel:0,disposePanorama:0,ensureBase:0,zoom:0,resetCrop:0,resetOutpaint:0,overflow:0,resize:0,gridPreview:0,clear:0,history:0,brush:0,text:0,compare:0,icons:0};
      CanvasImageEditorModeController.configure({
        getEditKind:()=>state.kind,getMode:()=>state.mode,setMode:value=>{state.mode=value;},markModeTouched:()=>{state.touched=true;},
        isPanoramaEnabled:()=>state.panorama,previewDownloadGroupCount:()=>2,
        removeEditTextInlineEditor:()=>calls.removeText++,bindPreviewWheelListeners:()=>calls.wheel++,disposePanoramaPreview:()=>calls.disposePanorama++,
        translate:key=>'label:'+key,syncGridCustomCursor:()=>{},syncGridGapValue:()=>{},refreshComparePanel:()=>calls.compare++,
        ensureImageEditBaseSize:()=>calls.ensureBase++,applyImageEditZoom:()=>calls.zoom++,resetCropBox:()=>calls.resetCrop++,resetOutpaintBox:()=>calls.resetOutpaint++,
        syncImageEditOverflow:()=>calls.overflow++,resizeEditDrawCanvas:()=>calls.resize++,refreshGridSplitPreview:()=>calls.gridPreview++,clearEditDrawing:()=>calls.clear++,
        syncEditDrawingHistoryButtons:()=>calls.history++,syncBrushToolButtons:()=>calls.brush++,syncTextToolState:()=>calls.text++,refreshIcons:()=>calls.icons++
      });
      const originalRaf=window.requestAnimationFrame; window.requestAnimationFrame=callback=>{callback();return 1;};
      const api=CanvasImageEditorModeController;
      const cropMode=api.setMode('crop',true);
      const crop={mode:cropMode,touched:state.touched,cropVisible:document.getElementById('cropCanvas').style.display!=='none',
        previewHidden:document.getElementById('previewStage').style.display==='none',cropActive:document.querySelector('[data-image-edit-mode="crop"]')?.classList.contains('active'),
        applyVisible:document.getElementById('imageEditApplyBtn').style.display!=='none',applyText:document.getElementById('imageEditApplyBtn').textContent.trim(),resetCrop:calls.resetCrop};
      api.setMode('mask');
      const mask={active:document.getElementById('cropCanvas').classList.contains('mask-mode'),tools:document.getElementById('imageMaskTools').classList.contains('active'),
        applyText:document.getElementById('imageEditApplyBtn').textContent.trim()};
      api.setMode('preview');
      const preview={cropHidden:document.getElementById('cropCanvas').style.display==='none',stageVisible:document.getElementById('previewStage').style.display==='inline-flex',
        downloads:document.getElementById('previewDownloadAllBtn').style.display==='inline-flex',compare:document.getElementById('compareToggleBtn').style.display==='inline-flex',compareCalls:calls.compare};
      state.kind='video';
      api.setMode('crop');
      const video={mode:state.mode,panel:document.querySelector('.image-edit-panel').classList.contains('video-preview-mode'),
        modeBar:document.querySelector('.image-edit-mode').style.display,frameTools:document.getElementById('videoFrameTools').style.display,
        zoom:document.getElementById('imageEditZoomLabel').style.display,cancel:document.getElementById('imageEditCancelBtn').textContent,
        title:document.getElementById('imageEditTitle').textContent};
      state.kind='image';
      const invalid=api.setMode('invalid-mode');
      state.panorama=true;
      const brush=api.setMode('brush');
      window.requestAnimationFrame=originalRaf;
      return {module:typeof api==='object',modes:api.modes,crop,mask,preview,video,invalid,brush,disposeCount:calls.disposePanorama,calls};
    }""")

    check("图片编辑模式控制器提供全部支持模式", result["module"] and result["modes"] == ["preview", "crop", "outpaint", "mask", "brush", "grid"], result["modes"])
    check("裁剪模式同步画布、按钮和操作标签", result["crop"]["mode"] == "crop" and result["crop"]["touched"] and result["crop"]["cropVisible"]
          and result["crop"]["previewHidden"] and result["crop"]["cropActive"] and result["crop"]["applyVisible"]
          and "label:canvas.applyCrop" in result["crop"]["applyText"] and result["crop"]["resetCrop"] == 1, result["crop"])
    check("遮罩模式激活遮罩工具并更新操作标签", result["mask"] == {"active": True, "tools": True, "applyText": "label:canvas.applyMask"}, result["mask"])
    check("预览模式恢复预览区、对比和批量下载按钮", result["preview"]["cropHidden"] and result["preview"]["stageVisible"]
          and result["preview"]["downloads"] and result["preview"]["compare"] and result["preview"]["compareCalls"] == 1, result["preview"])
    check("视频预览强制保持预览并隐藏图像编辑工具", result["video"] == {"mode": "preview", "panel": True, "modeBar": "none", "frameTools": "flex", "zoom": "none", "cancel": "关闭", "title": "预览视频"}, result["video"])
    check("未知模式回退到预览，全景开启时切换编辑会关闭全景", result["invalid"] == "preview" and result["brush"] == "brush" and result["disposeCount"] == 1, {"invalid": result["invalid"], "brush": result["brush"], "dispose": result["disposeCount"]})
    check("模式切换调用绘制尺寸、历史和图标同步", result["calls"]["resize"] == 6 and result["calls"]["history"] == 6 and result["calls"]["icons"] == 6, result["calls"])
    check("图片编辑模式切换无脚本异常或真实写请求", not errors and not blocked_writes, {"errors": errors[:3], "blockedWrites": blocked_writes})
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
