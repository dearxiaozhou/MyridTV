# -*- coding: utf-8 -*-
"""Browser regression for canvas image drop payload normalization."""
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
      const api=CanvasImageDropPayload;
      api.configure({isSupportedUploadFile:file=>/^image\\//.test(file?.type||'') || /\\.(png|jpe?g|webp|gif)$/i.test(file?.name||'')});
      const makeTransfer=(values={},types=Object.keys(values),files=[],items=[])=>({
        types,files,items,getData:type=>values[type]||''
      });
      const asset=api.payloadFromDataTransfer(makeTransfer({
        'application/x-smart-asset':JSON.stringify({url:'/assets/ref.png',name:'参考图',kind:'image',assetId:'asset-7'}),
        'text/uri-list':'https://example.test/ignored.png'
      }));
      const imageFile=new File(['img'],'portrait.png',{type:'image/png'});
      const pdfFile=new File(['pdf'],'notes.pdf',{type:'application/pdf'});
      const files=api.payloadFromDataTransfer(makeTransfer({},['Files'],[imageFile,pdfFile]));
      const html=api.payloadFromDataTransfer(makeTransfer({'text/html':'<a href="https://cdn.example.test/look.png">image</a>'}));
      const remote=api.payloadFromDataTransfer(makeTransfer({'text/uri-list':'# browser comment\\nhttps://cdn.example.test/hero.png'}));
      const local=api.payloadFromDataTransfer(makeTransfer({
        'text/plain':'file:///C:/Users/Art%20Team/Picture%20One.png\\nfile:///C:/Users/Art%20Team/Picture%20One.png\\nC:\\\\Users\\\\Art Team\\\\notes.pdf'
      }));
      const mkFileEntry=file=>({isFile:true,file:ok=>ok(file)});
      const mkDirectoryEntry=children=>({isDirectory:true,createReader(){let read=0;return {readEntries:ok=>ok(read++===0?children:[])}}});
      const directoryTransfer=makeTransfer({},['Files'],[],[{webkitGetAsEntry:()=>mkDirectoryEntry([
        mkFileEntry(new File(['ok'],'nested.jpg',{type:'image/jpeg'})),
        mkFileEntry(new File(['no'],'nested.pdf',{type:'application/pdf'}))
      ])}]);
      const directory=await api.resolve(directoryTransfer);
      const customAsset=makeTransfer({'application/x-smart-asset':JSON.stringify({url:'/assets/asset.png'})},['application/x-smart-asset']);
      const hiddenAsset=makeTransfer({},['application/x-smart-asset']);
      const inputThumb=makeTransfer({},['application/x-smart-input-thumb']);
      const hinted=makeTransfer({},['application/x-qt-windows-mime']);
      return {
        module:typeof api==='object',methods:['resolve','payloadFromDataTransfer','hasImageData','hasAsset','hasInputThumb'].every(key=>typeof api[key]==='function'),
        asset,files:{type:files.type,names:files.files?.map(file=>file.name)},html,remote,local,
        directory:{type:directory.type,names:directory.files?.map(file=>file.name)},
        detection:{asset:api.hasImageData(customAsset)&&api.hasAsset(customAsset),hiddenAsset:api.hasImageData(hiddenAsset),thumb:api.hasInputThumb(inputThumb),hint:api.hasImageData(hinted)},
        name:api.imageNameFromUrl('https://cdn.example.test/%E6%88%BF%E9%97%B4.png?width=300#preview')
      };
    }""")

    check("拖放识别模块加载并暴露稳定接口", result["module"] and result["methods"], {"module": result["module"], "methods": result["methods"]})
    check("素材引用优先保留素材版本标识", result["asset"] == {"type": "asset", "url": "/assets/ref.png", "name": "参考图", "kind": "image", "assetId": "asset-7"}, result["asset"])
    check("直接拖入文件只接受支持的图像格式", result["files"] == {"type": "files", "names": ["portrait.png"]}, result["files"])
    check("HTML 链接与 URI 列表可解析远端图片地址", result["html"] == {"type": "url", "url": "https://cdn.example.test/look.png"}
          and result["remote"] == {"type": "url", "url": "https://cdn.example.test/hero.png"}, {"html": result["html"], "remote": result["remote"]})
    check("本地路径文本不再被识别为可导入媒体（后端从未实现本地导入接口）", result["local"] == {"type": "none"}, result["local"])
    check("文件夹递归读取并过滤不支持文件", result["directory"] == {"type": "files", "names": ["nested.jpg"]}, result["directory"])
    check("识别素材拖放（含拖动中受限载荷）、输入缩略图及系统文件提示", result["detection"] == {"asset": True, "hiddenAsset": True, "thumb": True, "hint": True}, result["detection"])
    check("图片名称解码并忽略查询参数和片段", result["name"] == "房间.png", result["name"])
    check("拖放模块运行时无脚本异常或正式数据写入", not errors and not blocked_writes, {"errors": errors[:3], "blockedWrites": blocked_writes})
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
