# -*- coding: utf-8 -*-
"""Browser regression for image-edit brush, mask, label, and grid gestures."""
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
        status=200, content_type="application/json", body=json.dumps({"proxy": {"base_url": BASE}})))
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    outcome = page.evaluate("""() => {
      const controller=CanvasImageEditDrawingController;
      const ops=[];
      const pixels=new Uint8ClampedArray([10,20,30,200,0,0,0,0]);
      const context={lineCap:'',lineJoin:'',lineWidth:0,strokeStyle:'',fillStyle:'',globalCompositeOperation:'',
        beginPath(){ops.push(['begin']);},moveTo(x,y){ops.push(['move',x,y]);},lineTo(x,y){ops.push(['line',x,y]);},
        stroke(){ops.push(['stroke']);},fill(){ops.push(['fill']);},arc(...args){ops.push(['arc',...args]);},
        strokeRect(...args){ops.push(['rect',...args]);},ellipse(...args){ops.push(['ellipse',...args]);},
        save(){ops.push(['save']);},restore(){ops.push(['restore']);},strokeText(text,x,y){ops.push(['strokeText',text,x,y]);},
        fillText(text,x,y){ops.push(['fillText',text,x,y]);},getImageData(){return {data:pixels};},putImageData(){ops.push(['putImageData']);}};
      const pointer={captured:[],released:[],setPointerCapture(id){this.captured.push(id);},releasePointerCapture(id){this.released.push(id);}};
      const canvas={...pointer,width:100,height:100,getBoundingClientRect:()=>({left:10,top:20,width:200,height:50}),getContext:()=>context};
      const cropCanvas={classList:{values:new Set(),toggle(name,value){value?this.values.add(name):this.values.delete(name);}}};
      const grid={custom:false,dragging:false,begins:[],moves:[],ends:0,
        isCustomMode(){return this.custom;},isDragging(){return this.dragging;},
        beginLineEdit(point,w,h,id){this.begins.push({point,w,h,id});this.dragging=true;},
        moveLineEdit(point,w,h){this.moves.push({point,w,h});},endLineEdit(){this.ends++;this.dragging=false;}};
      const counters={push:0,snapshot:0,restore:0,gridUndo:0,gridPreview:0,historySync:0,inlineRemove:0,textSync:0};
      let mode='brush';
      controller.configure({getCanvas:()=>canvas,getMode:()=>mode,getGridController:()=>grid,
        getElementById:id=>id==='maskBrushSize'?{value:'12'}:id==='paintBrushSize'?{value:'8'}:
          id==='paintBrushColor'?{value:'#123456'}:id==='cropCanvas'?cropCanvas:null,
        removeInlineEditor:()=>counters.inlineRemove++,syncTextToolState:()=>counters.textSync++,
        pushHistory:()=>counters.push++,snapshot:()=>{counters.snapshot++;return {mark:'snap'};},
        restoreSnapshot:value=>{if(value?.mark==='snap')counters.restore++;},
        syncGridUndoButton:()=>counters.gridUndo++,refreshGridPreview:()=>counters.gridPreview++,
        syncHistoryButtons:()=>counters.historySync++});
      const event=(x,y,id=1,coalesced=null)=>({clientX:x,clientY:y,pointerId:id,prevented:0,stopped:0,
        preventDefault(){this.prevented++;},stopPropagation(){this.stopped++;},
        getCoalescedEvents:coalesced?()=>coalesced:undefined});
      const point=controller.point(event(110,45));
      mode='crop'; const cropEvent=event(30,40,10); controller.begin(cropEvent);
      const cropUntouched=cropEvent.prevented===0;
      mode='brush'; controller.setTool('free');
      const down=event(110,45,11); controller.begin(down);
      const move=event(190,65,11,[event(150,55,11),event(190,65,11)]); controller.move(move);
      const freeStrokes=ops.filter(item=>item[0]==='stroke').length;
      controller.end(event(190,65,11));
      const freeEnded=controller.getState().draw===null && canvas.released.includes(11);

      controller.setTool('rect');
      controller.begin(event(50,50,12)); controller.move(event(90,80,12));
      const shapeDrawn=ops.some(item=>item[0]==='rect' && item[1]===20 && item[2]===60 && item[3]===20 && item[4]===60);
      controller.end(event(90,80,12));

      controller.setTool('label'); controller.begin(event(70,70,13));
      const label=ops.find(item=>item[0]==='strokeText');
      const labelState={label:label?.[1],counter:controller.getLabelCounter(),activeDraw:controller.getState().draw};

      mode='mask'; pixels.set([10,20,30,200,0,0,0,0]); controller.setTool('free');
      controller.begin(event(70,70,14));
      const maskPixel=Array.from(pixels.slice(0,4));
      controller.end(event(70,70,14));

      mode='grid'; grid.custom=true;
      controller.begin(event(110,45,15)); controller.move(event(150,55,15)); controller.end(event(150,55,15));
      const gridResult={begin:grid.begins.at(-1),move:grid.moves.at(-1),ends:grid.ends,undo:counters.gridUndo,preview:counters.gridPreview};

      mode='brush'; const inlineBefore=counters.inlineRemove; controller.setTool('text');
      const textInlinePreserved=counters.inlineRemove===inlineBefore;
      const textMode=cropCanvas.classList.values.has('text-mode');
      const fallbackTool=controller.setTool('invalid');
      return {point,cropUntouched,freeStrokes,freeEnded,freeDownPrevented:down.prevented,freeMovePrevented:move.prevented,
        shapeDrawn,restores:counters.restore,labelState,maskPixel,gridResult,textMode,fallbackTool,
        inlineRemovedForText:textInlinePreserved,inlineRemoveCount:counters.inlineRemove,
        pushes:counters.push,snapshots:counters.snapshot,historySyncs:counters.historySync,
        tool:controller.getTool(),draw:controller.getState().draw};
    }""")

    check("指针坐标按画布实际尺寸换算，裁剪模式不启动绘制", outcome["point"] == {"x":50,"y":50}
          and outcome["cropUntouched"], outcome)
    check("自由笔刷处理合并指针事件并在结束时释放捕获", outcome["freeStrokes"] >= 2 and outcome["freeEnded"]
          and outcome["freeDownPrevented"] == 1 and outcome["freeMovePrevented"] == 1, outcome)
    check("矩形笔刷每次移动还原快照后绘制形状", outcome["shapeDrawn"] and outcome["restores"] >= 1, outcome)
    check("编号标签绘制后释放捕获并递增编号", outcome["labelState"] == {"label":"①","counter":2,"activeDraw":None}, outcome["labelState"])
    check("蒙版笔刷颜色归一为白色且透明度不超过上限", outcome["maskPixel"] == [255,255,255,115], outcome["maskPixel"])
    check("自定义网格手势交由网格控制器并刷新撤销/预览", outcome["gridResult"]["begin"]["point"] == {"x":50,"y":50}
          and outcome["gridResult"]["move"]["point"] == {"x":70,"y":70}
          and outcome["gridResult"]["undo"] == 1 and outcome["gridResult"]["preview"] == 2, outcome["gridResult"])
    check("工具切换保持文本模式样式并将无效工具收敛到自由笔刷", outcome["textMode"]
          and outcome["inlineRemovedForText"] and outcome["fallbackTool"] == "free"
          and outcome["tool"] == "free" and outcome["draw"] is None, outcome)
    check("正式服务验收会话没有画布写请求", not blocked_writes, blocked_writes)
    check("画布页面无脚本异常", not errors, errors[:3])

    screenshot = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
    if screenshot:
        page.screenshot(path=screenshot, full_page=False)
        print("SCREENSHOT: " + screenshot)
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
