# -*- coding: utf-8 -*-
"""Browser regression for canvas undo snapshots and node tombstone recovery."""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright


import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
VERSION = json.loads(urllib.request.urlopen(BASE + "/health", timeout=10).read())["version"]
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:220] if detail else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch(
        executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
        headless=True,
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1680, "height": 980})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)

    setup = page.evaluate("""() => {
      canvas={connections:[],deleted:[]};
      nodes=[]; selectedId=''; selectedIds=[]; selectedImage={nodeId:'',index:-1};
      render();
      return {module:typeof CanvasUndoController==='object',depth:CanvasUndoController.getUndoDepth(),suppressed:undoSuppressed};
    }""")
    check("撤销模块加载且初始状态为空", setup["module"] and setup["depth"] == 0 and not setup["suppressed"], setup)

    created = page.evaluate("""() => {
      const node=createNode(240,180,[]);
      return {id:node.id,x:node.x,count:nodes.length,depth:CanvasUndoController.getUndoDepth()};
    }""")
    check("创建节点会记录可撤销的初始快照", created["count"] == 1 and created["depth"] == 1, created)

    page.evaluate("""() => {
      capturePendingUndo();
      nodes[0].x=420;
      commitPendingUndo();
      render();
    }""")
    page.keyboard.press("Control+z")
    page.wait_for_function("nodes.length===1 && nodes[0].x===240")
    moved_undo = page.evaluate("""() => ({x:nodes[0]?.x,depth:CanvasUndoController.getUndoDepth(),suppressed:undoSuppressed})""")
    check("拖动类待提交快照可撤销且恢复抑制状态", moved_undo["x"] == 240 and moved_undo["depth"] == 1 and not moved_undo["suppressed"], moved_undo)

    page.keyboard.press("Control+z")
    page.wait_for_function("nodes.length===0")
    check("再次撤销恢复到创建前的空画布", page.evaluate("nodes.length===0 && CanvasUndoController.getUndoDepth()===0"))

    deleted = page.evaluate("""() => {
      const node=createNode(360,220,[]);
      deleteSelectedNodesFromKeyboard();
      return {id:node.id,count:nodes.length,tombstoned:canvas.deleted.some(item=>item.id===node.id)};
    }""")
    check("删除节点写入删除标记", deleted["count"] == 0 and deleted["tombstoned"], deleted)
    page.keyboard.press("Control+z")
    page.wait_for_function("nodes.length===1")
    restored = page.evaluate("""() => ({
      id:nodes[0]?.id,
      rendered:!!document.querySelector('.image-node'),
      tombstoned:canvas.deleted.some(item=>item.id===nodes[0]?.id)
    })""")
    check("撤销删除恢复节点并清除删除标记", restored["id"] == deleted["id"] and restored["rendered"] and not restored["tombstoned"], restored)
    check("撤销操作没有页面脚本异常", not errors, errors[:3])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
