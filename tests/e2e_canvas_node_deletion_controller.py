# -*- coding: utf-8 -*-
"""Browser regression for atomic multi-node deletion and undo recovery."""
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
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:240] if detail else ""))


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
      nodes=[]; selectedId=''; selectedIds=[]; selectedImage={nodeId:'',index:-1};
      render();
      return {module:typeof CanvasNodeDeletionController==='object',selectionModule:typeof CanvasNodeSelectionController==='object',depth:CanvasUndoController.getUndoDepth()};
    }""")
    check("删除事务控制器加载", setup["module"], setup)
    check("节点选择控制器加载", setup["selectionModule"], setup)
    check("测试画布从干净撤销状态开始", setup["depth"] == 0, setup)

    created = page.evaluate("""() => {
      const a=createNode(80,180,[],{skipUndo:true});
      const spacing=nodeRect(a).width+96;
      const b=createNode(80+spacing,180,[],{skipUndo:true});
      const c=createNode(80+spacing*2,180,[],{skipUndo:true});
      const d=createNode(80+spacing*3,180,[],{skipUndo:true});
      const history={id:'history-a',type:'smart-image',x:80,y:520,title:'History',images:[{url:'https://example.test/history.png'}],historyFor:a.id,isHistoryGroup:true};
      nodes.push(history);
      c.inputNodeIds=[a.id,d.id];
      c.objectReferences=[{id:'from-a',sourceNodeId:a.id},{id:'from-d',sourceNodeId:d.id}];
      canvas.connections=[
        {from:a.id,to:c.id,kind:'flow'},
        {from:d.id,to:c.id,kind:'flow'},
        {from:a.id,to:history.id,kind:'history'}
      ];
      selectedId=''; selectedIds=[]; selectedImage={nodeId:'',index:-1};
      render();
      return {ids:[a.id,b.id,c.id,d.id],history:history.id,undoDepth:CanvasUndoController.getUndoDepth()};
    }""")
    page.locator(f'.image-node[data-id="{created["ids"][0]}"]').click()
    page.locator(f'.image-node[data-id="{created["ids"][1]}"]').click(modifiers=["Shift"])
    selection = page.evaluate("""() => ({selectedId,selectedIds:[...selectedIds],selectedDom:document.querySelectorAll('.image-node.selected').length})""")
    check("真实点击与 Shift 多选同步维护数据和 DOM", set(selection["selectedIds"]) == set(created["ids"][:2])
          and selection["selectedDom"] == 2, selection)

    page.locator(f'.image-node[data-id="{created["ids"][1]}"]').click(modifiers=["Shift"])
    toggled = page.evaluate("""() => ({selectedIds:[...selectedIds],selectedDom:document.querySelectorAll('.image-node.selected').length})""")
    check("Shift 再次点击可将节点从多选中移除", toggled["selectedIds"] == [created["ids"][0]]
          and toggled["selectedDom"] == 1, toggled)
    page.locator(f'.image-node[data-id="{created["ids"][1]}"]').click(modifiers=["Shift"])

    page.keyboard.press("Delete")
    page.wait_for_timeout(250)
    after_delete = page.evaluate("""() => ({
      ids:nodes.map(node=>node.id),
      connections:canvas.connections.map(conn=>`${conn.from}>${conn.to}`),
      inputs:nodes.find(node=>node.id===arguments[0])?.inputNodeIds,
      refs:nodes.find(node=>node.id===arguments[0])?.objectReferences?.map(ref=>ref.sourceNodeId),
      selectedId:selectedId,selectedIds:[...selectedIds],selectedImage:{...selectedImage},
      tombstones:canvas.deleted.map(item=>item.id),undoDepth:CanvasUndoController.getUndoDepth()
    })""".replace("arguments[0]", json.dumps(created["ids"][2])), None)
    deleted_ok = (
        after_delete["ids"] == [created["ids"][2], created["ids"][3]]
        and after_delete["connections"] == [f"{created['ids'][3]}>{created['ids'][2]}"]
        and after_delete["inputs"] == [created["ids"][3]]
        and after_delete["refs"] == [created["ids"][3]]
        and after_delete["selectedId"] == ""
        and after_delete["selectedIds"] == []
        and after_delete["selectedImage"]["nodeId"] == ""
        and set(after_delete["tombstones"]) == {created["ids"][0], created["ids"][1], created["history"]}
        and after_delete["undoDepth"] == created["undoDepth"] + 1
    )
    check("Delete 一次原子删除多选节点并清理关联，只记一条撤销", deleted_ok, after_delete)

    page.keyboard.press("Control+z")
    page.wait_for_function("nodes.length===5")
    restored = page.evaluate("""() => ({
      ids:nodes.map(node=>node.id),connections:canvas.connections.map(conn=>`${conn.from}>${conn.to}`),
      inputs:nodes.find(node=>node.id===arguments[0])?.inputNodeIds,
      refs:nodes.find(node=>node.id===arguments[0])?.objectReferences?.map(ref=>ref.sourceNodeId),
      selectedIds:[...selectedIds],selectedDom:document.querySelectorAll('.image-node.selected').length,selectedImage:{...selectedImage},
      tombstones:canvas.deleted.map(item=>item.id)
    })""".replace("arguments[0]", json.dumps(created["ids"][2])), None)
    restore_ok = (
        set(restored["ids"]) == {created["ids"][0], created["ids"][1], created["ids"][2], created["ids"][3], created["history"]}
        and len(restored["connections"]) == 3
        and restored["inputs"] == [created["ids"][0], created["ids"][3]]
        and restored["refs"] == [created["ids"][0], created["ids"][3]]
        and set(restored["selectedIds"]) == {created["ids"][0], created["ids"][1]}
        and restored["selectedDom"] == 2
        and restored["selectedImage"] == {"nodeId": "", "index": -1}
        and not restored["tombstones"]
    )
    check("撤销恢复节点、关联、选区并清除所有删除标记", restore_ok, {
        "selectedIds": restored["selectedIds"], "selectedDom": restored["selectedDom"],
        "selectedImage": restored["selectedImage"], "idsRestored": len(restored["ids"]) == 5,
        "connectionsRestored": len(restored["connections"]) == 3,
        "referencesRestored": restored["inputs"] == [created["ids"][0], created["ids"][3]]
        and restored["refs"] == [created["ids"][0], created["ids"][3]],
        "tombstonesCleared": not restored["tombstones"]
    })

    page.evaluate("""(id) => {
      const node=nodes.find(item=>item.id===id);
      node.images=[{url:'https://example.test/image.png'}];
      node.w=360;node.h=240;
      node.cardSize={width:360,height:240};node.cardSizing='spec';
      selectedId=id;selectedIds=[];selectedImage={nodeId:id,index:0};
      render();
    }""", created["ids"][0])
    image_node = page.locator(f'.image-node[data-id="{created["ids"][0]}"]')
    image_node.hover()
    image_node.locator(".floating-node-actions .node-delete").click()
    page.wait_for_timeout(200)
    cleared = page.evaluate("""(id) => {
      const node=nodes.find(item=>item.id===id);
      return {exists:!!node,images:node?.images?.length,title:node?.title,hasSize:'w' in (node||{}) || 'h' in (node||{}),
        hasCardSize:'cardSize' in (node||{}) || 'cardSizing' in (node||{}),
        historyExists:nodes.some(item=>item.id==='history-a'),undoDepth:CanvasUndoController.getUndoDepth()};
    }""", created["ids"][0])
    check("素材节点删除按钮先清空素材，保留节点并只记录一次撤销",
          cleared["exists"] and cleared["images"] == 0 and not cleared["hasSize"] and not cleared["hasCardSize"]
          and not cleared["historyExists"] and cleared["undoDepth"] == 1, cleared)

    page.keyboard.press("Control+z")
    page.wait_for_function("id => nodes.some(node=>node.id===id && node.images?.length===1) && nodes.some(node=>node.id==='history-a')", arg=created["ids"][0])
    media_restored = page.evaluate("""(id) => ({
      imageCount:nodes.find(node=>node.id===id)?.images?.length,
      cardSize:nodes.find(node=>node.id===id)?.cardSize,cardSizing:nodes.find(node=>node.id===id)?.cardSizing,
      historyExists:nodes.some(node=>node.id==='history-a'),
      historyLink:canvas.connections.some(conn=>conn.from===id && conn.to==='history-a'),
      tombstoned:canvas.deleted.some(item=>item.id==='history-a')
    })""", created["ids"][0])
    check("撤销清空素材可恢复素材节点、历史分组和连线", media_restored["imageCount"] == 1
          and media_restored["cardSize"] == {"width":360,"height":240} and media_restored["cardSizing"] == "spec"
          and media_restored["historyExists"] and media_restored["historyLink"]
          and not media_restored["tombstoned"], media_restored)

    image_node = page.locator(f'.image-node[data-id="{created["ids"][0]}"]')
    image_node.hover()
    image_node.locator(".floating-node-actions .node-delete").click(force=True)
    page.wait_for_timeout(200)
    check("恢复后的有素材节点再次执行清空动作", page.evaluate("id => nodes.find(node=>node.id===id)?.images?.length===0", created["ids"][0]))
    image_node = page.locator(f'.image-node[data-id="{created["ids"][0]}"]')
    image_node.hover()
    image_node.locator(".floating-node-actions .node-delete").click(force=True)
    page.wait_for_timeout(200)
    check("空素材节点再次点击删除按钮后整节点移除",
          page.evaluate("id => !nodes.some(node=>node.id===id)", created["ids"][0]))

    editable_guard = page.evaluate("""() => {
      const input=document.createElement('input');document.body.append(input);
      selectedIds=[nodes[0].id,nodes[1].id];render();
      const before=nodes.length;
      const handled=deleteSelectedNodesFromKeyboard({target:input,preventDefault(){},stopPropagation(){},stopImmediatePropagation(){}});
      input.remove();
      return {handled,before,after:nodes.length};
    }""")
    check("输入框获得焦点时删除快捷键不移除节点", not editable_guard["handled"] and editable_guard["before"] == editable_guard["after"], editable_guard)
    check("删除流程无页面脚本异常", not errors, errors[:3])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
