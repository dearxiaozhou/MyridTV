# -*- coding: utf-8 -*-
"""Browser regression for multi-node copy/paste and internal connection remapping."""
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
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:320] if detail else ""))


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
      const a=createNode(100,180,[],{skipUndo:true});
      const b=createNode(600,200,[],{skipUndo:true});
      const c=createNode(1100,220,[],{skipUndo:true});
      a.artifactId='artifact-a';b.artifactId='artifact-b';c.artifactId='artifact-c';
      b.inputNodeIds=[a.id,c.id];
      b.sourceNodeId=a.id;
      canvas.connections=[{from:a.id,to:b.id,kind:'flow'},{from:b.id,to:c.id,kind:'flow'}];
      selectedId='';selectedIds=[];selectedImage={nodeId:'',index:-1};
      render();
      return {module:typeof CanvasNodeClipboardController==='object',ids:[a.id,b.id,c.id],connections:canvas.connections.length,undoDepth:CanvasUndoController.getUndoDepth()};
    }""")
    check("节点剪贴板控制器加载", setup["module"], setup)
    check("三个源节点和两条原始连线已准备", setup["connections"] == 2 and setup["undoDepth"] == 0, setup)

    page.locator(f'.image-node[data-id="{setup["ids"][0]}"]').click()
    page.locator(f'.image-node[data-id="{setup["ids"][1]}"]').click(modifiers=["Shift"])
    selection = page.evaluate("""() => ({selectedIds:[...selectedIds],selectedDom:document.querySelectorAll('.image-node.selected').length})""")
    check("通过真实点击选中两个待复制节点", set(selection["selectedIds"]) == set(setup["ids"][:2])
          and selection["selectedDom"] == 2, selection)

    page.keyboard.press("Control+c")
    copied = page.evaluate("""() => ({nodeCount:nodes.length,hasClipboard:CanvasNodeClipboardController.hasClipboardNodes()})""")
    check("复制只写入剪贴板，不增加画布节点", copied["nodeCount"] == 3 and copied["hasClipboard"], copied)

    page.keyboard.press("Control+v")
    page.wait_for_function("nodes.length===5", timeout=5000)
    pasted = page.evaluate("""(sourceIds) => {
      const copies=nodes.filter(node=>!sourceIds.includes(node.id));
      const ids=new Set(copies.map(node=>node.id));
      const clonedInternal=canvas.connections.filter(conn=>ids.has(conn.from)&&ids.has(conn.to));
      const copiedB=copies.find(node=>node.title==='万能节点' && node.inputNodeIds?.length);
      return {
        total:nodes.length,copies:copies.map(node=>({id:node.id,artifactId:node.artifactId,inputNodeIds:node.inputNodeIds,sourceNodeId:node.sourceNodeId})),
        connections:canvas.connections.map(conn=>`${conn.from}>${conn.to}`),clonedInternal:clonedInternal.length,
        copiedInputs:copiedB?.inputNodeIds,copiedSource:copiedB?.sourceNodeId,
        selectedIds:[...selectedIds],selectedDom:document.querySelectorAll('.image-node.selected').length,
        undoDepth:CanvasUndoController.getUndoDepth()
      };
    }""", setup["ids"])
    copy_ids = [node["id"] for node in pasted["copies"]]
    copied_a = next((node for node in pasted["copies"] if not node["inputNodeIds"]), {})
    copied_b = next((node for node in pasted["copies"] if node["inputNodeIds"]), {})
    check("粘贴新增两个节点并生成独立身份", len(copy_ids) == 2 and not set(copy_ids).intersection(setup["ids"])
          and all(node["artifactId"] not in {"artifact-a", "artifact-b", "artifact-c"} for node in pasted["copies"]), pasted["copies"])
    check("只复制选中节点之间的内部连线", pasted["clonedInternal"] == 1 and len(pasted["connections"]) == 3, pasted["connections"])
    check("节点输入与来源引用映射到对应副本", copied_b.get("inputNodeIds") == [copied_a.get("id")]
          and pasted["copiedInputs"] == [copied_a.get("id")] and pasted["copiedSource"] == copied_a.get("id"), pasted["copies"])
    check("粘贴作为单个撤销步骤记录", pasted["undoDepth"] == 1, pasted["undoDepth"])
    check("粘贴后两个副本成为当前选区", set(pasted["selectedIds"]) == set(copy_ids) and pasted["selectedDom"] == 2, pasted)

    page.keyboard.press("Control+z")
    page.wait_for_function("nodes.length===3")
    undone = page.evaluate("""(sourceIds) => ({
      count:nodes.length,connections:canvas.connections.map(conn=>`${conn.from}>${conn.to}`),
      selectedIds:[...selectedIds],selectedDom:document.querySelectorAll('.image-node.selected').length,
      sourceSet:sourceIds.every(id=>nodes.some(node=>node.id===id)),
      hasClipboard:CanvasNodeClipboardController.hasClipboardNodes(),undoDepth:CanvasUndoController.getUndoDepth()
    })""", setup["ids"])
    check("一次撤销完整移除粘贴副本并恢复源节点、连线和选区",
          undone["count"] == 3 and len(undone["connections"]) == 2 and undone["sourceSet"]
          and set(undone["selectedIds"]) == set(setup["ids"][:2]) and undone["selectedDom"] == 2
          and undone["hasClipboard"] and undone["undoDepth"] == 0, undone)
    check("复制粘贴流程无页面脚本异常", not errors, errors[:3])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
