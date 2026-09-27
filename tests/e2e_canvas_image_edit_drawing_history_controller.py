# -*- coding: utf-8 -*-
"""Browser regression for image-edit drawing history snapshots."""
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

    result = page.evaluate("""() => {
      const history=CanvasImageEditDrawingHistoryController;
      const canvas=editDrawCanvas();
      const textCanvas=editTextCanvas();
      const text=CanvasImageEditTextController;
      canvas.width=8; canvas.height=8;
      textCanvas.width=8; textCanvas.height=8;
      const ctx=canvas.getContext('2d');
      ctx.clearRect(0,0,8,8);
      history.reset();
      const alphaAt=(x,y)=>ctx.getImageData(x,y,1,1).data[3];
      CanvasImageEditDrawingController.setLabelCounter(3);
      text.setItems([{id:'before',text:'before',x:2,y:2,size:18,color:'#123456'}]);
      text.setSelectedId('before');
      ctx.fillStyle='#f00'; ctx.fillRect(1,1,1,1);
      pushEditDrawHistory();
      const afterPush={history:history.historyState(),undoDisabled:document.getElementById('brushUndoBtn').disabled};

      ctx.fillRect(2,2,1,1);
      text.setItems([...text.getItems(),{id:'after',text:'after',x:4,y:4,size:18,color:'#654321'}]);
      text.setSelectedId('after');
      CanvasImageEditDrawingController.setLabelCounter(5);
      const undoResult=undoEditDrawing();
      const afterUndo={
        pixels:[alphaAt(1,1),alphaAt(2,2)],
        ids:text.getItems().map(item=>item.id),selected:text.getSelectedId(),counter:CanvasImageEditDrawingController.getLabelCounter(),
        history:history.historyState(),redoDisabled:document.getElementById('brushRedoBtn').disabled
      };
      const redoResult=redoEditDrawing();
      const afterRedo={
        pixels:[alphaAt(1,1),alphaAt(2,2)],
        ids:text.getItems().map(item=>item.id),selected:text.getSelectedId(),counter:CanvasImageEditDrawingController.getLabelCounter(),
        history:history.historyState()
      };
      clearEditDrawing(false);
      const afterClear={pixels:[alphaAt(1,1),alphaAt(2,2)],ids:text.getItems().map(item=>item.id),counter:CanvasImageEditDrawingController.getLabelCounter(),history:history.historyState()};
      const clearUndoResult=undoEditDrawing();
      const restoredClear={pixels:[alphaAt(1,1),alphaAt(2,2)],ids:text.getItems().map(item=>item.id),counter:CanvasImageEditDrawingController.getLabelCounter()};
      const beforeSilent=history.historyState();
      clearEditDrawing(true);
      const afterSilent={pixels:[alphaAt(1,1),alphaAt(2,2)],history:history.historyState()};
      history.reset();
      return {
        module:typeof history==='object' && ['snapshot','restore','push','undo','redo','clear','reset'].every(name=>typeof history[name]==='function'),
        afterPush,undoResult,afterUndo,redoResult,afterRedo,afterClear,clearUndoResult,restoredClear,beforeSilent,afterSilent,
        afterReset:{history:history.historyState(),counter:CanvasImageEditDrawingController.getLabelCounter(),ids:text.getItems().map(item=>item.id),undoDisabled:document.getElementById('brushUndoBtn').disabled,redoDisabled:document.getElementById('brushRedoBtn').disabled}
      };
    }""")

    check("绘制历史控制器加载并提供完整操作", result["module"])
    check("推入快照后撤销按钮同步启用", result["afterPush"]["history"] == {"undo": 1, "redo": 0}
          and not result["afterPush"]["undoDisabled"], result["afterPush"])
    check("撤销同时恢复像素、文字、选中项和序号", result["undoResult"]
          and result["afterUndo"]["pixels"] == [255, 0]
          and result["afterUndo"]["ids"] == ["before"]
          and result["afterUndo"]["selected"] == "before"
          and result["afterUndo"]["counter"] == 3
          and result["afterUndo"]["history"] == {"undo": 0, "redo": 1}
          and not result["afterUndo"]["redoDisabled"], result["afterUndo"])
    check("重做完整恢复撤销前内容", result["redoResult"]
          and result["afterRedo"]["pixels"] == [255, 255]
          and result["afterRedo"]["ids"] == ["before", "after"]
          and result["afterRedo"]["selected"] == "after"
          and result["afterRedo"]["counter"] == 5, result["afterRedo"])
    check("清空会记录一次可撤销的快照并重置文字计数", result["afterClear"]["pixels"] == [0, 0]
          and result["afterClear"]["ids"] == [] and result["afterClear"]["counter"] == 1
          and result["afterClear"]["history"]["undo"] == 2, result["afterClear"])
    check("撤销清空可恢复此前画布内容", result["clearUndoResult"]
          and result["restoredClear"]["pixels"] == [255, 255]
          and result["restoredClear"]["ids"] == ["before", "after"], result["restoredClear"])
    check("静默清空不增加历史记录", result["afterSilent"]["pixels"] == [0, 0]
          and result["afterSilent"]["history"] == result["beforeSilent"], result["afterSilent"])
    check("重置会清除历史、文字和计数", result["afterReset"] == {
        "history": {"undo": 0, "redo": 0}, "counter": 1, "ids": [], "undoDisabled": True, "redoDisabled": True
    }, result["afterReset"])
    check("正式服务验证会话没有画布写请求", not blocked_writes, blocked_writes)
    check("画布页面无脚本异常", not errors, errors[:3])

    screenshot = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
    if screenshot:
        page.screenshot(path=screenshot, full_page=False)
        print("SCREENSHOT: " + screenshot)
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
