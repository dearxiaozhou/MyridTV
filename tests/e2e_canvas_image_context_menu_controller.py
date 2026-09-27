# -*- coding: utf-8 -*-
"""Browser regression for canvas image context menu lifecycle and actions."""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright


import os

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
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"proxy":{"base_url":BASE}}))
        elif request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            blocked_writes.append({"method":request.method,"url":request.url})
            route.abort()
        else:
            route.continue_()
    page.route("**/*", route_request)
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(900)

    result = page.evaluate("""async () => {
      const image={url:'/output.webp',name:'output.webp',kind:'image',assetId:'asset-1',assetVersionMode:'latest'};
      const node={id:'node-1',x:120,y:80,title:'结果节点',images:[image]};
      const nodes=[node];
      const calls={front:[],assetMode:[],assetVersion:[],agent:[],duplicate:[],opened:[],created:[],connected:[],inserted:[],fetch:[],library:[],toasts:[],sync:0,composer:0,persist:0,params:0,render:0,saves:0,clipboard:'',bodyClicks:0};
      let selectedIds=['node-1','node-2'];
      let selectedId='node-2';
      let selectedImage={nodeId:'',index:-1};
      let settings={engine:'api',apiKind:'video',model:'demo'};
      let library={libraries:[]};
      let libraryLoaded=false;
      const ids=['add-agent','duplicate-node','view-image','img2img','save-asset','copy-path','open-folder','set-cover','asset-follow-latest','asset-pin-version','asset-save-version'];
      const sourceRect={width:300,height:200};
      window.open=(...args)=>calls.opened.push(args);
      Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:value=>{calls.clipboard=value;return Promise.resolve();}}});
      document.body.addEventListener('click',()=>calls.bodyClicks++);
      CanvasImageContextMenuController.configure({
        getActionIds:()=>ids,translate:key=>key,escapeAttr:value=>String(value),escapeHtml:value=>String(value),
        getNodes:()=>nodes,getCanvasId:()=> 'canvas-1',toast:value=>calls.toasts.push(value),
        fetcher:async(url,options={})=>{calls.fetch.push({url,method:options.method||'GET',body:options.body?JSON.parse(options.body):null});return {ok:true,json:async()=>({ok:true})};},
        setAssetVersionMode:(...args)=>calls.assetMode.push(args),saveAssetVersion:(...args)=>calls.assetVersion.push(args),
        addImageNodeRefToAgent:(...args)=>calls.agent.push(args),duplicateNodeWithConnections:id=>calls.duplicate.push(id),
        nodeRect:()=>sourceRect,getSettings:()=>settings,createGeneratorNode:(point,options)=>{calls.created.push({point,options});return {id:'generated-1'};},
        settingsForStorage:value=>value,cloneSettings:value=>JSON.parse(JSON.stringify(value)),connectInputNode:(...args)=>calls.connected.push(args),
        setSelectedId:value=>{selectedId=value;},setSelectedIds:value=>{selectedIds=value;},setSelectedImage:value=>{selectedImage=value;},
        isApiLikeEngine:engine=>engine==='api',setApiKind:value=>{settings.apiKind=value;},syncSelectionUi:()=>calls.sync++,updateComposer:()=>calls.composer++,
        insertImageReferenceIntoPrompt:value=>calls.inserted.push(value),mediaKindForItem:value=>value?.kind||'image',
        persistActiveSettings:()=>calls.persist++,renderDynamicParams:()=>calls.params++,render:()=>calls.render++,scheduleSave:()=>calls.saves++,
        getAssetLibrary:()=>library,loadAssetLibrary:async()=>{libraryLoaded=true;library={libraries:[{}]};},
        addUrlToAssetLibrary:(...args)=>calls.library.push(args),getSelectedNodeIds:()=>selectedIds,bringNodesToFront:value=>calls.front.push(value)
      });
      const click=action=>document.querySelector(`[data-smart-image-menu-action="${action}"]`).click();
      openSmartImageContextMenu(node.id,0,{clientX:2000,clientY:1300});
      const menu=document.getElementById('smartImageContextMenu');
      const initial={count:document.querySelectorAll('#smartImageContextMenu').length,styleCount:document.querySelectorAll('#smartImageContextMenuStyle').length,
        actionCount:menu.querySelectorAll('[data-smart-image-menu-action]').length,left:menu.style.left,top:menu.style.top,open:menu.classList.contains('open'),
        followHidden:menu.querySelector('[data-smart-image-menu-action="asset-follow-latest"]').style.display==='none',
        pinVisible:menu.querySelector('[data-smart-image-menu-action="asset-pin-version"]').style.display!=='none'};
      const multi={selectedId,selectedIds:[...selectedIds],selectedImage:{...selectedImage},front:calls.front.at(-1)};
      image.assetVersionMode='pinned';
      openSmartImageContextMenu(node.id,0,{clientX:20,clientY:30});
      const pinned={followVisible:menu.querySelector('[data-smart-image-menu-action="asset-follow-latest"]').style.display!=='none',
        pinHidden:menu.querySelector('[data-smart-image-menu-action="asset-pin-version"]').style.display==='none'};
      selectedIds=['node-1']; selectedId='node-2';
      openSmartImageContextMenu(node.id,0,{clientX:20,clientY:30});
      const single={selectedId,selectedIds:[...selectedIds],selectedImage:{...selectedImage},front:calls.front.at(-1)};

      click('set-cover'); await new Promise(resolve=>setTimeout(resolve,0));
      click('asset-follow-latest'); click('asset-pin-version'); click('asset-save-version');
      click('add-agent'); click('duplicate-node'); click('view-image'); click('img2img');
      click('save-asset'); click('copy-path'); click('open-folder');
      await new Promise(resolve=>setTimeout(resolve,0));
      const openFolder=calls.fetch.find(item=>item.url==='/api/open-folder');
      const cover=calls.fetch.find(item=>item.url==='/api/canvases/canvas-1/meta');
      closeSmartImageContextMenu();
      return {module:typeof CanvasImageContextMenuController==='object',initial,multi,pinned,single,calls,libraryLoaded,
        generated:{...calls.created[0],connected:calls.connected[0],settings:calls.created[0]&&calls.created[0].options},
        inserted:calls.inserted[0],openFolder,cover,closed:!menu.classList.contains('open')};
    }""")
    calls = result["calls"]
    check("菜单控制器创建单例菜单并包含所有操作", result["module"] and result["initial"]["count"] == 1
          and result["initial"]["styleCount"] == 1 and result["initial"]["actionCount"] == 11, result["initial"])
    check("弹层位置限制在视口内并按素材版本显示选项", result["initial"]["left"] == "1240px" and result["initial"]["top"] == "780px"
          and result["initial"]["open"] and result["initial"]["followHidden"] and result["initial"]["pinVisible"]
          and result["pinned"] == {"followVisible":True,"pinHidden":True}, {"initial":result["initial"],"pinned":result["pinned"]})
    check("右键选中保留多选，单选时切换焦点并提升节点", result["multi"]["selectedIds"] == ["node-1","node-2"]
          and result["multi"]["selectedId"] == "node-2" and result["single"]["selectedId"] == "node-1"
          and result["single"]["selectedIds"] == [] and result["single"]["front"] == "node-1", {"multi":result["multi"],"single":result["single"]})
    check("封面设置发送正确地址并给出反馈", result["cover"] == {"url":"/api/canvases/canvas-1/meta","method":"POST","body":{"cover":"/output.webp"}}
          and "已设置为画布封面" in calls["toasts"], {"cover":result["cover"],"toasts":calls["toasts"]})
    check("图生图创建节点、连接输入、设置图片模式并插入引用", result["generated"]["point"] == {"x":680,"y":180}
          and result["generated"]["connected"] == ["node-1","generated-1"]
          and result["generated"]["settings"]["apiKind"] == "image" and result["inserted"]["imageIndex"] == 0
          and calls["persist"] == 1 and calls["params"] == 1 and calls["saves"] == 1, result["generated"])
    check("素材库与素材版本动作透传正确", result["libraryLoaded"] and calls["library"] == [["/output.webp","output.webp"]]
          and calls["assetMode"] == [["node-1",0,"latest"],["node-1",0,"pinned"]]
          and calls["assetVersion"] == [["node-1",0]], {"library":calls["library"],"assetMode":calls["assetMode"],"assetVersion":calls["assetVersion"]})
    check("Agent、复制、打开图片与文件夹动作正常", calls["agent"] == [["node-1",0]] and calls["duplicate"] == ["node-1"]
          and calls["opened"] == [["/output.webp","_blank"]] and calls["clipboard"] == f"{BASE}/output.webp"
          and result["openFolder"]["body"]["url"] == "/output.webp" and result["openFolder"]["body"]["name"] == "output.webp", calls)
    check("关闭菜单且菜单事件不冒泡到画布", result["closed"] and calls["bodyClicks"] == 0, {"closed":result["closed"],"bodyClicks":calls["bodyClicks"]})
    check("右键菜单行为无脚本异常或真实写请求", not errors and not blocked_writes, {"errors":errors[:3],"blockedWrites":blocked_writes})
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
