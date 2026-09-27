# -*- coding: utf-8 -*-
"""Browser regression for image-grid geometry, interaction state, and preview."""
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
    page.wait_for_timeout(1100)

    result = page.evaluate("""() => {
      const controller=CanvasImageGridSplitController;
      const preset=CanvasImageGridSplitModel.rects(300,200,{rows:2,cols:3,gap:4});
      const custom=CanvasImageGridSplitModel.rects(300,180,{
        custom:true,gap:6,
        customLines:[
          {type:'v',pos:2/3},{type:'h',pos:.5},{type:'v',pos:1/3},
          {type:'v',pos:1/3},{type:'h',pos:.5}
        ]
      });
      const empty=CanvasImageGridSplitModel.rects(20,20,{rows:1,cols:2,gap:999});
      const zero=CanvasImageGridSplitModel.rects(0,100,{rows:2,cols:2,gap:4});
      const layout=CanvasImageGridSplitModel.layoutFromRects(custom,'grid-test');

      document.getElementById('gridHorizontalLines').value='1';
      document.getElementById('gridVerticalLines').value='2';
      document.getElementById('gridGapSize').value='4';
      controller.reset();
      const integratedPreset=gridSplitRects(300,200);

      controller.toggleCustomMode();
      controller.setOrientation('h');
      controller.beginLineEdit({x:10,y:90},300,180,1);
      controller.endLineEdit();
      controller.setOrientation('v');
      controller.beginLineEdit({x:200,y:10},300,180,2);
      controller.endLineEdit();
      controller.beginLineEdit({x:100,y:10},300,180,3);
      controller.endLineEdit();
      const beforeDrag=controller.snapshot();
      controller.setOrientation('h');
      controller.beginLineEdit({x:120,y:92},300,180,4);
      controller.moveLineEdit({x:120,y:0},300,180);
      const dragged=controller.snapshot();
      controller.endLineEdit();
      const undoWorked=controller.undoLine();
      const afterUndo=controller.snapshot();
      controller.clearLines();
      const afterClear=controller.snapshot();

      controller.setOrientation('h');
      controller.beginLineEdit({x:0,y:90},300,180,5); controller.endLineEdit();
      controller.setOrientation('v');
      controller.beginLineEdit({x:200,y:0},300,180,6); controller.endLineEdit();
      controller.beginLineEdit({x:100,y:0},300,180,7); controller.endLineEdit();
      document.getElementById('gridGapSize').value='6';
      const integratedCustom=gridSplitRects(300,180);
      const integratedLayout=gridLayoutFromRects(integratedCustom);
      imageEditMode='grid';
      editDrawCanvas().width=300;
      editDrawCanvas().height=180;
      refreshGridSplitPreview();
      const customPreviewCount=document.getElementById('gridSplitCount').textContent;
      controller.applyPreset();
      refreshGridSplitPreview();
      const presetPreviewCount=document.getElementById('gridSplitCount').textContent;
      imageEditMode='preview';
      return {
        module:typeof CanvasImageGridSplitModel==='object',
        hasFunctions:['clampGap','rects','presetRects','customRects','layoutFromRects']
          .every(name=>typeof CanvasImageGridSplitModel[name]==='function'),
        controller:typeof controller==='object' && ['reset','toggleCustomMode','beginLineEdit','moveLineEdit','undoLine','clearLines','rects','refreshPreview']
          .every(name=>typeof controller[name]==='function'),
        preset,custom,empty,zero,layout,
        integratedPreset,integratedCustom,integratedLayout,
        interaction:{beforeDrag,dragged,undoWorked,afterUndo,afterClear},
        preview:{custom:customPreviewCount,preset:presetPreviewCount}
      };
    }""")

    check("网格几何模型和交互控制器接口完整", result["module"] and result["hasFunctions"] and result["controller"])
    check("预设网格按行列和间距生成六个矩形", len(result["preset"]) == 6
          and result["preset"][0] == {"row": 0, "col": 0, "x": 0, "y": 0, "w": 98, "h": 98}
          and result["preset"][-1] == {"row": 1, "col": 2, "x": 202, "y": 102, "w": 98, "h": 98}, result["preset"])
    check("自定义切线排序去重并生成有效区域", len(result["custom"]) == 6
          and result["custom"][0] == {"row": 0, "col": 0, "x": 0, "y": 0, "w": 97, "h": 87}
          and result["custom"][-1] == {"row": 1, "col": 2, "x": 203, "y": 93, "w": 97, "h": 87}, result["custom"])
    check("间距限制和零尺寸会安全省略无效矩形", result["empty"] == [] and result["zero"] == [])
    check("布局模型保留组标识并正确统计行列", result["layout"] == {
        "type": "grid-split", "groupId": "grid-test", "rows": 2, "cols": 3
    }, result["layout"])
    check("画布预设入口委托给新几何模型", result["integratedPreset"] == result["preset"])
    check("画布自定义入口与模型计算保持一致", result["integratedCustom"] == result["custom"]
          and result["integratedLayout"]["type"] == "grid-split"
          and result["integratedLayout"]["rows"] == 2
          and result["integratedLayout"]["cols"] == 3)
    interaction = result["interaction"]
    check("自定义切线新增、拖动边界和撤销状态正确", interaction["beforeDrag"]["custom"]
          and len(interaction["beforeDrag"]["lines"]) == 3
          and interaction["dragged"]["lines"][0]["pos"] == 0.001
          and interaction["dragged"]["historyDepth"] == interaction["beforeDrag"]["historyDepth"] + 1
          and interaction["undoWorked"]
          and interaction["afterUndo"]["lines"] == interaction["beforeDrag"]["lines"], interaction)
    check("清空切线会同时清掉撤销栈", interaction["afterClear"]["lines"] == []
          and interaction["afterClear"]["historyDepth"] == 0 and not interaction["afterClear"]["dragging"], interaction["afterClear"])
    check("预设与自定义预览计数跟随当前网格", "6" in result["preview"]["custom"]
          and "6" in result["preview"]["preset"], result["preview"])
    check("测试会话没有发出画布写请求", not blocked_writes, blocked_writes)
    check("画布页面无脚本异常", not errors, errors[:3])

    screenshot = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
    if screenshot:
        page.screenshot(path=screenshot, full_page=False)
        print("SCREENSHOT: " + screenshot)
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
