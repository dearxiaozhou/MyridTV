# -*- coding: utf-8 -*-
"""Browser regression for preview and grouped image downloads."""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright
from e2e_support import record_blocked_write


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
        record_blocked_write(blocked_writes, route.request.method, route.request.url)
        or route.fulfill(status=204, body="")
    ) if route.request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} else route.continue_())
    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    outcome = page.evaluate("""async () => {
      const controller=CanvasImagePreviewDownloadController;
      const links=[],requests=[],toasts=[],revoked=[];
      let responseMode='ok';
      const node={id:'group-1',title:'Group/Test',images:[
        {url:'/b.png',name:'B.png',grid:{row:1,col:1}},
        {url:'/c.png',name:'C.png'},
        {url:'/a.png',name:'A.png',grid:{row:0,col:0}},
        {name:'missing.png'}
      ]};
      controller.configure({
        getNavigation:()=>({nodeId:'group-1',index:0}),getNodes:()=>[node],
        safeExportFileName:(name,fallback='archive.zip')=>String(name||fallback).replace(/[\\/:*?"<>|]+/g,'_').trim()||fallback,
        downloadNameForMediaItem:(item,fallback='output')=>item?.name||fallback,
        fetch:async(url,options)=>{requests.push({url,options});return responseMode==='ok'
          ? {ok:true,blob:async()=>new Blob(['zip-content'])}
          : {ok:false,text:async()=>'temporary download failure'};},
        toast:message=>toasts.push(message),
        createLink:()=>{const link={click(){this.clicked=true;},remove(){this.removed=true;}};links.push(link);return link;},
        appendLink:link=>{link.appended=true;},removeLink:link=>{link.removed=true;},
        createObjectURL:()=> 'blob:preview-group',revokeObjectURL:url=>revoked.push(url),schedule:callback=>callback()
      });
      const ordered=controller.groupItems().map(item=>item.url);
      const currentResult=controller.downloadCurrent();
      const currentLink={href:links[0].href,name:links[0].download,clicked:links[0].clicked,removed:links[0].removed};
      const fileResult=controller.downloadFile({url:'/one file.mp4',name:'clip.mp4'});
      const fileLink={href:links[1].href,name:links[1].download};
      const groupResult=await controller.downloadGroup();
      const request={url:requests[0].url,method:requests[0].options.method,contentType:requests[0].options.headers['Content-Type'],body:JSON.parse(requests[0].options.body)};
      const groupLink={href:links[2].href,name:links[2].download,clicked:links[2].clicked,removed:links[2].removed};
      node.images=[];
      const emptyResult=await controller.downloadGroup();
      const requestCountAfterEmpty=requests.length;
      node.images=[{url:'/a.png',name:'A.png'}]; responseMode='fail';
      const failureResult=await controller.downloadGroup();
      return {ordered,currentResult,currentLink,fileResult,fileLink,groupResult,request,groupLink,revoked,emptyResult,requestCountAfterEmpty,failureResult,toasts,requestCount:requests.length};
    }""")

    check("组图按行列顺序排序并跳过没有地址的项", outcome["ordered"] == ["/a.png", "/b.png", "/c.png"], outcome["ordered"])
    check("下载当前预览读取当前导航项并安全编码地址", outcome["currentResult"]
          and outcome["currentLink"]["name"] == "B.png"
          and "/api/download-output?url=%2Fb.png&name=B.png" == outcome["currentLink"]["href"]
          and outcome["currentLink"]["clicked"] and outcome["currentLink"]["removed"], outcome["currentLink"])
    check("单文件下载使用指定媒体名并编码含空格的路径", outcome["fileResult"]
          and outcome["fileLink"] == {"href":"/api/download-output?url=%2Fone%20file.mp4&name=clip.mp4","name":"clip.mp4"}, outcome["fileLink"])
    check("组图打包使用排序后的地址和名称并POST到下载接口", outcome["groupResult"]
          and outcome["request"] == {
              "url":"/api/canvas-assets/download","method":"POST","contentType":"application/json",
              "body":{"filename":"Group_Test.zip","urls":["/a.png","/b.png","/c.png"],
                      "items":[{"url":"/a.png","name":"A.png"},{"url":"/b.png","name":"B.png"},{"url":"/c.png","name":"C.png"}]}
          }, outcome["request"])
    check("成功组图下载触发 ZIP 下载并释放临时链接", outcome["groupLink"] == {
        "href":"blob:preview-group","name":"Group_Test.zip","clicked":True,"removed":True
    } and outcome["revoked"] == ["blob:preview-group"], {"link":outcome["groupLink"],"revoked":outcome["revoked"]})
    check("空组图不会请求打包接口", outcome["emptyResult"] is False and outcome["requestCountAfterEmpty"] == 1,
          {"result":outcome["emptyResult"],"requestCount":outcome["requestCountAfterEmpty"]})
    check("打包失败显示服务返回的错误信息", outcome["failureResult"] is False
          and outcome["toasts"] == ["temporary download failure"], outcome["toasts"])
    check("正式服务验收会话没有外部画布写请求", not blocked_writes, blocked_writes)
    check("画布页面无脚本异常", not errors, errors[:3])

    screenshot = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
    if screenshot:
        page.screenshot(path=screenshot, full_page=False)
        print("SCREENSHOT: " + screenshot)
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
