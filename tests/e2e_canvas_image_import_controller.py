# -*- coding: utf-8 -*-
"""Browser regression for uploaded and locally imported canvas media."""
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
      const calls={requests:[],undo:0,append:[],toasts:[]};
      let failNextUpload=false;
      let failNextLocalImport=false;
      const responseFor=(data={})=>({ok:true,json:async()=>data,text:async()=>''});
      CanvasImageImportController.configure({
        pushUndo:()=>calls.undo++,appendImagesToNode:(images,targetId,options)=>calls.append.push({images,targetId,options}),toast:message=>calls.toasts.push(message),
        fetcher:async(url,options={})=>{
          if(url==='/api/ai/upload'){
            const names=[...options.body.entries()].map(([,file])=>file.name); calls.requests.push({url,method:options.method,names});
            if(failNextUpload){failNextUpload=false;return {ok:false,text:async()=>'upload denied'};}
            return responseFor({files:names.map(name=>({url:'/uploaded/'+name,name}))});
          }
          const body=JSON.parse(options.body); calls.requests.push({url,method:options.method,body});
          if(failNextLocalImport){failNextLocalImport=false;return {ok:false,clone:()=>({json:async()=>({detail:'local path denied'})}),text:async()=>'local path denied'};}
          return responseFor({files:body.paths.map(path=>({url:'/imported/'+path.split(/[\\\\/]/).pop(),name:path.split(/[\\\\/]/).pop()}))});
        }
      });
      const api=CanvasImageImportController;
      const image=new File(['a'],'a.png',{type:'image/png'});
      const video=new File(['v'],'clip.mp4',{type:'video/mp4'});
      const pdf=new File(['p'],'readme.pdf',{type:'application/pdf'});
      const direct=await api.uploadFiles([image,video,pdf]);
      const emptyUpload=await api.uploadFiles([pdf]);
      const emptyLocal=await api.importLocalImages([]);
      const local=await api.importLocalImages(['C:/Assets/local.png']);
      await api.handleFiles([video,pdf],'target',{skipUndo:false,point:{x:7,y:8}});
      await api.handleDropPayload({type:'localPaths',localPaths:['C:/Assets/drop.png']},'local-target',{point:{x:9,y:10}});
      await api.handleDropPayload({type:'asset',url:'/assets/ref.png',assetId:'asset-9'},'asset-target',{});
      await api.handleDropPayload({type:'url',url:'https://cdn.example.test/%E5%9B%BE.png?size=1'},'url-target',{skipUndo:true});
      failNextLocalImport=true;
      await api.handleDropPayload({type:'localPaths',localPaths:['C:/bad.png']},'failed-target',{});
      failNextUpload=true;
      await api.handleFiles([image],'failed-upload-target',{});
      return {module:typeof api==='object',direct:direct.map(file=>({name:file.name,kind:file.kind})),emptyUpload,emptyLocal,local,
        requests:calls.requests,undo:calls.undo,append:calls.append,toasts:calls.toasts};
    }""")

    check("媒体导入控制器加载", result["module"], result["module"])
    check("上传只发送支持的图片和视频并补齐媒体类型", result["direct"] == [{"name": "a.png", "kind": "image"}, {"name": "clip.mp4", "kind": "video"}]
          and result["requests"][0] == {"url": "/api/ai/upload", "method": "POST", "names": ["a.png", "clip.mp4"]}, {"direct": result["direct"], "request": result["requests"][0]})
    check("没有支持格式时跳过上传请求，空本地路径跳过导入", result["emptyUpload"] == [] and result["emptyLocal"] == [] and result["local"] == [{"url": "/imported/local.png", "name": "local.png"}]
          and sum(request["url"] == "/api/ai/upload" for request in result["requests"]) == 3, {"emptyUpload": result["emptyUpload"], "local": result["local"], "requests": result["requests"]})
    check("文件导入上传成功后才记录撤销并写入目标节点", result["append"][0] == {"images": [{"url": "/uploaded/clip.mp4", "name": "clip.mp4", "kind": "video"}], "targetId": "target", "options": {"skipUndo": False, "point": {"x": 7, "y": 8}}}, result["append"][0])
    check("本地路径导入会保存结果并保留目标位置", result["append"][1] == {"images": [{"url": "/imported/drop.png", "name": "drop.png"}], "targetId": "local-target", "options": {"point": {"x": 9, "y": 10}}}, result["append"][1])
    check("素材引用保留最新版本标识，网页图片名可解码", result["append"][2]["images"] == [{"url": "/assets/ref.png", "name": "ref.png", "kind": "image", "assetId": "asset-9", "assetVersionMode": "latest"}]
          and result["append"][3]["images"] == [{"url": "https://cdn.example.test/%E5%9B%BE.png?size=1", "name": "图.png", "kind": "image"}], {"asset": result["append"][2], "url": result["append"][3]})
    check("skipUndo 生效且失败导入显示服务错误", result["undo"] == 4 and "local path denied" in result["toasts"] and "upload denied" in result["toasts"], {"undo": result["undo"], "toasts": result["toasts"]})
    check("媒体导入流程无脚本异常或真实写请求", not errors and not blocked_writes, {"errors": errors[:3], "blockedWrites": blocked_writes})
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
