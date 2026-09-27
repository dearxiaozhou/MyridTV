# -*- coding: utf-8 -*-
"""Browser regression for image-editor text annotation interactions."""
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
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    initial = page.evaluate("""() => {
      const text=CanvasImageEditTextController;
      const history=CanvasImageEditDrawingHistoryController;
      const draw=editDrawCanvas(), canvas=editTextCanvas();
      draw.width=300; draw.height=180; canvas.width=300; canvas.height=180;
      const rect={x:0,y:0,left:0,top:0,right:300,bottom:180,width:300,height:180,toJSON:()=>({})};
      draw.getBoundingClientRect=()=>rect; canvas.getBoundingClientRect=()=>rect;
      const crop=document.getElementById('cropCanvas'); crop.getBoundingClientRect=()=>rect;
      document.getElementById('imageEditModal').classList.add('open');
      canvas.setPointerCapture=()=>{}; canvas.releasePointerCapture=()=>{};
      editDrawCanvas().getContext('2d').clearRect(0,0,300,180);
      history.reset(); text.resetState();
      imageEditMode='brush'; CanvasImageEditDrawingController.setTool('text');
      const event=(x,y,pointerId)=>({clientX:x,clientY:y,pointerId,preventDefault(){},stopPropagation(){}});
      beginEditText(event(100,80,1));
      endEditText(event(100,80,1));
      const created=text.snapshotState();
      beginEditText(event(100,80,2));
      moveEditText(event(124,92,2));
      endEditText(event(124,92,2));
      const moved=text.snapshotState();
      return {
        module:typeof text==='object' && ['begin','move','end','beginInline','removeInlineEditor','snapshotState','resetState'].every(name=>typeof text[name]==='function'),
        created,moved,history:history.historyState(),toolClass:crop.classList.contains('text-mode')
      };
    }""")
    check("文字标注控制器加载并提供交互接口", initial["module"])
    check("点击画布创建并选中文字标注", len(initial["created"]["items"]) == 1
          and initial["created"]["items"][0]["x"] == 100
          and initial["created"]["items"][0]["y"] == 80
          and initial["created"]["selectedId"] == initial["created"]["items"][0]["id"], initial["created"])
    check("拖动标注更新画布坐标并结束拖动态", initial["moved"]["items"][0]["x"] == 124
          and initial["moved"]["items"][0]["y"] == 92
          and not initial["moved"]["dragging"] and initial["toolClass"], initial["moved"])

    item_id = initial["moved"]["selectedId"]
    page.evaluate("id => CanvasImageEditTextController.beginInline(CanvasImageEditTextController.getItems().find(item => item.id === id))", item_id)
    editor = page.locator(".edit-text-inline")
    editor.wait_for(state="visible")
    editor.fill("成熟软件")
    editor.press("Enter")
    committed = page.evaluate("""() => ({
      text:CanvasImageEditTextController.getItems()[0]?.text,
      inline:CanvasImageEditTextController.snapshotState().inlineEditing,
      history:CanvasImageEditDrawingHistoryController.historyState()
    })""")
    check("回车提交行内文字编辑并留下历史", committed["text"] == "成熟软件"
          and not committed["inline"] and committed["history"]["undo"] >= 2, committed)

    history_result = page.evaluate("""() => {
      const history=CanvasImageEditDrawingHistoryController, text=CanvasImageEditTextController;
      const undo=history.undo(); const afterUndo=text.getItems()[0]?.text;
      const redo=history.redo(); const afterRedo=text.getItems()[0]?.text;
      return {undo,afterUndo,redo,afterRedo,position:{x:text.getItems()[0]?.x,y:text.getItems()[0]?.y},history:history.historyState()};
    }""")
    check("撤销和重做行内改字时保留标注位置", history_result["undo"]
          and history_result["afterUndo"] != "成熟软件"
          and history_result["redo"] and history_result["afterRedo"] == "成熟软件"
          and history_result["position"] == {"x": 124, "y": 92}, history_result)

    page.evaluate("id => CanvasImageEditTextController.beginInline(CanvasImageEditTextController.getItems().find(item => item.id === id))", item_id)
    editor = page.locator(".edit-text-inline")
    editor.wait_for(state="visible")
    editor.fill("取消这次修改")
    editor.press("Escape")
    cancelled = page.evaluate("""() => ({
      text:CanvasImageEditTextController.getItems()[0]?.text,
      inline:CanvasImageEditTextController.snapshotState().inlineEditing,
      history:CanvasImageEditDrawingHistoryController.historyState(),
      modalOpen:document.getElementById('imageEditModal').classList.contains('open')
    })""")
    check("Esc 取消行内编辑且不增加历史", cancelled["text"] == "成熟软件"
          and not cancelled["inline"] and cancelled["history"] == history_result["history"]
          and cancelled["modalOpen"], cancelled)

    page.evaluate("""() => {
      CanvasImageEditTextController.resetState();
      CanvasImageEditDrawingHistoryController.reset();
      imageEditMode='crop'; CanvasImageEditDrawingController.setTool('free');
      document.getElementById('imageEditModal').classList.remove('open');
    }""")
    check("文字编辑验证没有触发画布写请求", not blocked_writes, blocked_writes)
    check("画布页面无脚本异常", not errors, errors[:3])

    screenshot = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
    if screenshot:
        page.screenshot(path=screenshot, full_page=False)
        print("SCREENSHOT: " + screenshot)
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
