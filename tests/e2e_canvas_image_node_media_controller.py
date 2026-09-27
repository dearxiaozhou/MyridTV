# -*- coding: utf-8 -*-
"""Browser regression for adding imported media to canvas image nodes."""
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

    result = page.evaluate("""() => {
      const state={nodes:[],selectedId:'selected',created:[],renders:0,saves:0};
      const selected={id:'selected',type:'image',images:[{url:'/selected.png',kind:'image'}],scale:2};
      const target={id:'target',type:'image',images:[{url:'/before.png',kind:'image'}],scale:2,w:800,h:600};
      const canvasGroup={id:'group',type:'image',images:[{url:'/a.png',kind:'image'},{url:'/b.png',kind:'image'}],scale:2};
      const single={id:'single',type:'image',images:[],title:'Untitled',scale:2,w:200,h:160};
      state.nodes=[selected,target,canvasGroup,single];
      CanvasImageNodeMediaController.configure({
        getNodes:()=>state.nodes,selectedNode:()=>state.nodes.find(node=>node.id===state.selectedId),
        isImageNode:node=>node?.type==='image',viewportCenter:()=>({x:50,y:60}),
        createEmptyNodeAt:point=>{const node={id:'created-'+(state.created.length+1),type:'image',x:point.x,y:point.y,images:[],scale:2};state.created.push({point:{...point},node});state.nodes.push(node);return node;},
        isFile:value=>value instanceof File,mediaKindForFile:file=>file.type.startsWith('video/')?'video':'image',
        mediaKindForItem:item=>item.kind||'image',defaultImageNodeScale:2,defaultGroupNodeScale:0.8,previousGroupNodeScale:1.6,
        setSelectedId:value=>{state.selectedId=value;},render:()=>state.renders++,scheduleSave:()=>state.saves++
      });
      const api=CanvasImageNodeMediaController;
      const groupResult=api.appendImages([{url:'/after.png',name:'after.png'}],'target');
      const group={id:groupResult.id,count:groupResult.images.length,title:groupResult.title,scale:groupResult.scale,hasSize:'w'in groupResult||'h'in groupResult};
      canvasGroup.scale=2;
      api.appendImages([{url:'/c.png',kind:'image'}],'group');
      const existingGroupScale=canvasGroup.scale;
      const singleResult=api.appendImages([{url:'/one.png'}],'single');
      const singleState={title:singleResult.title,count:singleResult.images.length,hasSize:'w'in singleResult||'h'in singleResult};
      const selectedBefore=state.selectedId;
      const newNode=api.appendImages([{url:'/new-a.png'},{url:'/new-b.png'}],'', {point:{x:120,y:240},forceNew:true});
      const created={id:newNode.id,point:state.created[0]?.point,count:newNode.images.length,title:newNode.title,scale:newNode.scale,selectedId:state.selectedId};
      const rendersBefore=state.renders,savesBefore=state.saves;
      const empty=api.appendImages([{name:'missing-url'}]);
      return {module:typeof api==='object',titles:{images:api.uploadTitleForItems([{kind:'image'},{kind:'image'}]),mixed:api.uploadTitleForItems([{kind:'image'},{kind:'video'}]),audio:api.uploadTitleForItems([{kind:'audio'}])},
        group,existingGroupScale,singleState,created,selectedBefore,emptySkipped:empty===null&&state.renders===rendersBefore&&state.saves===savesBefore,
        state:{selectedId:state.selectedId,renders:state.renders,saves:state.saves}};
    }""")

    check("图片节点媒体控制器加载并提供组标题归类", result["module"] and result["titles"] == {"images": "Group", "mixed": "Media", "audio": "Audio"}, result["titles"])
    check("给指定节点追加图片后转为组图并按默认规则放大", result["group"] == {"id": "target", "count": 2, "title": "Group", "scale": 0.8, "hasSize": False}, result["group"])
    check("已存在组图保持用户当前缩放", result["existingGroupScale"] == 2, result["existingGroupScale"])
    check("单张图片保持单图标题并清除旧尺寸缓存", result["singleState"] == {"title": "Image", "count": 1, "hasSize": False}, result["singleState"])
    check("强制新建组图沿用指定画布坐标并更新选中项", result["created"] == {"id": "created-1", "point": {"x": 120, "y": 240}, "count": 2, "title": "Group", "scale": 0.8, "selectedId": "created-1"}, result["created"])
    check("空图片列表不渲染也不保存", result["emptySkipped"] and result["state"]["renders"] == 4 and result["state"]["saves"] == 4, result["state"])
    check("媒体节点更新无脚本异常或真实写请求", not errors and not blocked_writes, {"errors": errors[:3], "blockedWrites": blocked_writes})
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
