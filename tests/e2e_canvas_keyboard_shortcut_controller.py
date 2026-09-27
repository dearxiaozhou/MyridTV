# -*- coding: utf-8 -*-
"""Browser regression for canvas keyboard routing and focus guards."""
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
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:280] if detail else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1680, "height": 980})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(1200)

    setup = page.evaluate("""() => {
      canvas={connections:[],deleted:[]};
      nodes=[];selectedId='';selectedIds=[];selectedImage={nodeId:'',index:-1};
      render();
      const a=createNode(120,180,[{url:'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='}],{skipUndo:true});
      const b=createNode(560,220,[{url:'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='}],{skipUndo:true});
      selectedId='';selectedIds=[];selectedImage={nodeId:'',index:-1};
      render();
      return {module:typeof CanvasKeyboardShortcutController==='object',ids:[a.id,b.id],undoDepth:CanvasUndoController.getUndoDepth()};
    }""")
    check("键盘快捷键控制器已加载", setup["module"], setup)
    check("验收节点准备完成且撤销栈为空", len(setup["ids"]) == 2 and setup["undoDepth"] == 0, setup)

    page.locator(f'.image-node[data-id="{setup["ids"][0]}"]').click()
    page.locator(f'.image-node[data-id="{setup["ids"][1]}"]').click(modifiers=["Shift"])
    selection = page.evaluate("""() => ({selectedIds:[...selectedIds],selectedDom:document.querySelectorAll('.image-node.selected').length})""")
    check("快捷键前两个节点真实多选", set(selection["selectedIds"]) == set(setup["ids"])
          and selection["selectedDom"] == 2, selection)

    page.evaluate("""() => {
      const input=document.createElement('input');
      input.className='canvas-group-title-input';
      document.body.appendChild(input);
      input.focus();
    }""")
    page.keyboard.press("Control+g")
    input_guard = page.evaluate("""() => ({groups:nodes.filter(node=>node.type==='smart-group').length,focus:document.activeElement?.className})""")
    check("标题输入框聚焦时 Ctrl+G 不触发分组", input_guard["groups"] == 0, input_guard)

    page.evaluate("""() => {
      document.querySelector('.canvas-group-title-input')?.remove();
      CanvasNodeSelectionController.focusCanvasWorld();
    }""")
    page.keyboard.press("Control+g")
    page.wait_for_function("nodes.some(node=>node.type==='smart-group')", timeout=5000)
    grouped = page.evaluate("""() => {
      const group=nodes.find(node=>node.type==='smart-group');
      return {groups:nodes.filter(node=>node.type==='smart-group').length,
        groupId:group?.id,memberCount:group?.memberIds?.length,
        selectedId,undoDepth:CanvasUndoController.getUndoDepth()};
    }""")
    check("画布聚焦时 Ctrl+G 分组并记录一步撤销", grouped["groups"] == 1 and grouped["memberCount"] == 2
          and grouped["selectedId"] == grouped["groupId"] and grouped["undoDepth"] == 1, grouped)

    page.keyboard.press("Control+z")
    page.wait_for_function("nodes.filter(node=>node.type==='smart-group').length===0", timeout=5000)
    undone = page.evaluate("""() => ({nodeCount:nodes.length,selectedIds:[...selectedIds],undoDepth:CanvasUndoController.getUndoDepth()})""")
    check("Ctrl+Z 撤销键盘分组且恢复两个节点", undone["nodeCount"] == 2 and set(undone["selectedIds"]) == set(setup["ids"])
          and undone["undoDepth"] == 0, undone)

    page.evaluate("createMenu.classList.add('open')")
    page.keyboard.press("Escape")
    escaped = page.evaluate("createMenu.classList.contains('open')")
    check("Escape 关闭画布创建菜单", not escaped, escaped)
    check("快捷键流程无页面脚本异常", not errors, errors[:3])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
