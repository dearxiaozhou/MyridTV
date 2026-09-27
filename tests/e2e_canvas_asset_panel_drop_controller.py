# -*- coding: utf-8 -*-
"""Browser regression for asset-panel drop feedback and import routing."""
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
    screenshot_path = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
    if screenshot_path:
        page.screenshot(path=screenshot_path, full_page=True)

    result = page.evaluate("""async () => {
      const calls={added:[],uploaded:[],imported:[],toasts:[]};
      const panel=document.createElement('div'); panel.id='drop-test-panel';
      const zone=document.createElement('div'); zone.id='drop-test-zone';
      panel.append(zone); document.body.append(panel);
      CanvasAssetPanelDropController.configure({
        getPanel:()=>panel,getDropZone:()=>zone,
        dataTypes:transfer=>CanvasImageDropPayload.dataTypes(transfer),
        hasImageData:transfer=>CanvasImageDropPayload.hasImageData(transfer),
        resolvePayload:transfer=>CanvasImageDropPayload.resolve(transfer),
        imageNameFromUrl:url=>CanvasImageDropPayload.imageNameFromUrl(url),
        uploadFiles:async files=>{calls.uploaded.push(files.map(file=>file.name));return files.map(file=>({url:'/uploaded/'+file.name,name:file.name}));},
        importLocalImages:async paths=>{calls.imported.push([...paths]);return paths.map(path=>({url:'/imported/'+path.split(/[\\\\/]/).pop(),name:path.split(/[\\\\/]/).pop()}));},
        addUrlToAssetLibrary:async(url,name)=>calls.added.push({url,name}),
        toast:message=>calls.toasts.push(message),assetAddFailMessage:()=>'素材导入失败'
      });
      CanvasAssetPanelDropController.bind();
      const transfer=(values={},types=Object.keys(values),files=[])=>({types,files,getData:type=>values[type]||'',dropEffect:'none'});
      const imageDrag=transfer({},['application/x-smart-canvas-image']);
      let prevented=0,stopped=0;
      CanvasAssetPanelDropController.handleDragOver({dataTransfer:imageDrag,preventDefault:()=>prevented++,stopPropagation:()=>stopped++});
      const highlighted={panel:panel.classList.contains('drag-over'),zone:zone.classList.contains('drag-over'),effect:imageDrag.dropEffect,prevented,stopped};
      panel.dispatchEvent(Object.assign(new Event('dragleave'),{relatedTarget:document.body}));
      const cleared=!panel.classList.contains('drag-over')&&!zone.classList.contains('drag-over');

      const dropEvent=dataTransfer=>({dataTransfer,preventDefault(){this.prevented=true;},stopPropagation(){this.stopped=true;}});
      await CanvasAssetPanelDropController.handleDrop(dropEvent(transfer({'application/x-smart-canvas-image':JSON.stringify({url:'/canvas/frame.png',name:'画布帧'})},['application/x-smart-canvas-image'])));
      const files=[new File(['image'],'角色.png',{type:'image/png'}),new File(['bad'],'说明.pdf',{type:'application/pdf'})];
      await CanvasAssetPanelDropController.handleDrop(dropEvent(transfer({},['Files'],files)));
      await CanvasAssetPanelDropController.handleDrop(dropEvent(transfer({'text/plain':'C:\\\\Users\\\\Artist\\\\本地.png'})));
      await CanvasAssetPanelDropController.handleDrop(dropEvent(transfer({'text/uri-list':'https://cdn.example.test/look.png?size=1'})));
      const beforeUnsupported=calls.added.length;
      const unsupported=dropEvent(transfer({},['application/x-unknown']));
      await CanvasAssetPanelDropController.handleDrop(unsupported);
      const unsupportedIgnored=!unsupported.prevented&&calls.added.length===beforeUnsupported;

      const zoneDrag=transfer({},['application/x-smart-canvas-image']);
      CanvasAssetPanelDropController.handleDropZoneDragOver({dataTransfer:zoneDrag,preventDefault(){this.prevented=true;},stopPropagation(){this.stopped=true;}});
      const zoneHighlight=zone.classList.contains('drag-over');
      const badCanvasImage=dropEvent(transfer({'application/x-smart-canvas-image':'not json'},['application/x-smart-canvas-image']));
      await CanvasAssetPanelDropController.handleDrop(badCanvasImage);
      return {module:typeof CanvasAssetPanelDropController==='object',highlighted,cleared,calls,unsupportedIgnored,zoneHighlight,badCanvasImage:{prevented:badCanvasImage.prevented,stopped:badCanvasImage.stopped}};
    }""")

    check("素材库拖放控制器加载并绑定高亮状态", result["module"] and result["highlighted"] == {"panel": True, "zone": True, "effect": "copy", "prevented": 1, "stopped": 1}
          and result["cleared"] and result["zoneHighlight"], {"highlighted": result["highlighted"], "cleared": result["cleared"], "zoneHighlight": result["zoneHighlight"]})
    check("从画布拖入的图片直接加入素材库", {"url": "/canvas/frame.png", "name": "画布帧"} in result["calls"]["added"], result["calls"]["added"])
    check("拖入本地图片时上传并过滤不支持的文件", result["calls"]["uploaded"] == [["角色.png"]]
          and {"url": "/uploaded/角色.png", "name": "角色.png"} in result["calls"]["added"], result["calls"])
    check("拖入本地路径时经本地导入接口后加入素材库", result["calls"]["imported"] == [["C:\\Users\\Artist\\本地.png"]]
          and {"url": "/imported/本地.png", "name": "本地.png"} in result["calls"]["added"], result["calls"])
    check("拖入网页图片链接时提取文件名并加入素材库", {"url": "https://cdn.example.test/look.png?size=1", "name": "look.png"} in result["calls"]["added"], result["calls"]["added"])
    check("未知拖放不拦截画布事件且错误素材数据会提示", result["unsupportedIgnored"] and result["calls"]["toasts"] == ["素材导入失败"]
          and result["badCanvasImage"] == {"prevented": True, "stopped": True}, {"unsupportedIgnored": result["unsupportedIgnored"], "toasts": result["calls"]["toasts"]})
    check("素材库拖放路由无脚本异常或真实写请求", not errors and not blocked_writes, {"errors": errors[:3], "blockedWrites": blocked_writes})
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
