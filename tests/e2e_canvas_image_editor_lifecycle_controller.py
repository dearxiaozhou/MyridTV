# -*- coding: utf-8 -*-
"""Browser regression for image editor opening, closing, and preview navigation."""
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
      const svg=(color)=>'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="16"><rect width="24" height="16" fill="${color}"/></svg>`);
      const red=svg('red'),blue=svg('blue');
      nodes.push({id:'lifecycle-image-node',x:20,y:20,title:'Preview group',images:[
        {url:red,name:'red.svg',kind:'image',natural_w:24,natural_h:16},
        {url:blue,name:'blue.svg',kind:'image',natural_w:24,natural_h:16}
      ],scale:1});
      nodes.push({id:'lifecycle-video-node',x:40,y:40,title:'Video preview',images:[{url:'/static/demo.mp4',name:'demo.mp4',kind:'video'}],scale:1});
      openImageEditor('lifecycle-image-node',0);
      const first={open:imageEditModal.classList.contains('open'),selected:{...selectedImage},cropState:{...cropState},nav:{...previewNavState},src:document.getElementById('cropImage').getAttribute('src'),
        navVisible:document.getElementById('previewNextBtn').classList.contains('visible')};
      const staleLoad= document.getElementById('cropImage').onload;
      openImageEditor('lifecycle-image-node',1);
      const currentBeforeStale=CanvasImageEditViewportController.getState().baseW;
      staleLoad?.();
      const staleIgnored=CanvasImageEditViewportController.getState().baseW===currentBeforeStale;
      const second={selected:{...selectedImage},nav:{...previewNavState},src:document.getElementById('cropImage').getAttribute('src')};
      navigatePreviewImage(1);
      const wrapped={index:selectedImage.index,navIndex:previewNavState.index};
      const closingLoad=document.getElementById('cropImage').onload;
      closeImageEditor();
      const closed={open:imageEditModal.classList.contains('open'),source:document.getElementById('cropImage').getAttribute('src'),cropState,nav:{...previewNavState},onload:document.getElementById('cropImage').onload};
      closingLoad?.();
      const staleCloseIgnored=CanvasImageEditViewportController.getState().baseW===0;
      openImageEditor('lifecycle-video-node',0);
      const video={open:imageEditModal.classList.contains('open'),mode:imageEditMode,panel:document.querySelector('.image-edit-panel').classList.contains('video-preview-mode'),
        modeBar:document.querySelector('.image-edit-mode').style.display,tools:document.getElementById('videoFrameTools').style.display,
        imageSrc:document.getElementById('cropImage').getAttribute('src'),nav:{...previewNavState}};
      closeImageEditor();
      return {module:typeof CanvasImageEditorLifecycleController==='object',first,second,staleIgnored,wrapped,closed,staleCloseIgnored,video};
    }""")
    screenshot_path = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
    if screenshot_path:
        page.screenshot(path=screenshot_path, full_page=True)

    check("编辑器生命周期控制器加载并打开图片预览", result["module"] and result["first"]["open"]
          and result["first"]["selected"] == {"nodeId": "lifecycle-image-node", "index": 0}
          and result["first"]["cropState"]["imageIndex"] == 0 and result["first"]["nav"]["count"] == 2 and result["first"]["navVisible"], result["first"])
    check("切换预览图时更新节点索引和图片地址", result["second"]["selected"]["index"] == 1 and result["second"]["nav"]["index"] == 1
          and result["second"]["src"] != result["first"]["src"], {"first": result["first"], "second": result["second"]})
    check("较早图片的延迟 onload 不会覆盖当前编辑状态", result["staleIgnored"], result["staleIgnored"])
    check("预览导航从最后一张循环回第一张", result["wrapped"] == {"index": 0, "navIndex": 0}, result["wrapped"])
    check("关闭后清除媒体源、裁剪状态、导航和加载回调", result["closed"] == {"open": False, "source": None, "cropState": None, "nav": {"nodeId": "", "index": 0, "count": 0}, "onload": None}, result["closed"])
    check("关闭后失效的图片回调不会恢复编辑状态", result["staleCloseIgnored"], result["staleCloseIgnored"])
    check("视频只进入受限预览，不挂到图片裁剪层", result["video"]["open"] and result["video"]["mode"] == "preview" and result["video"]["panel"]
          and result["video"]["modeBar"] == "none" and result["video"]["tools"] == "flex" and result["video"]["imageSrc"] is None, result["video"])
    check("图片编辑器生命周期无脚本异常或正式数据写入", not errors and not blocked_writes, {"errors": errors[:3], "blockedWrites": blocked_writes})
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
