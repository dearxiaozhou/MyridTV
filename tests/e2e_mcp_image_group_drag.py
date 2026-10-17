"""Inspect a real two-image MCP node without saving changes to the user's canvas."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:3107"
CANVAS_ID = "6584629"
NODE_ID = "agent_ad446e2d8408"

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    # Drag only in an isolated browser page; intercept every canvas write.
    page.route("**/api/canvases/**", lambda route: route.fulfill(status=200, content_type="application/json",
        body=json.dumps({"ok": True, "canvas": json.loads(route.request.post_data or "{}")}) )
        if route.request.method in ("PUT", "POST", "DELETE", "PATCH") else route.continue_())
    page.goto(f"{BASE}/static/smart-canvas.html?id={CANVAS_ID}&focus_node={NODE_ID}", wait_until="domcontentloaded")
    page.wait_for_function("id => typeof canvas !== 'undefined' && canvas && canvas.id === id", arg=CANVAS_ID, timeout=30000)
    page.wait_for_function("id => nodes.some(n => n.type === 'smart-group' && n.mcpGroupSourceId === id)", arg=NODE_ID)
    group = page.evaluate("id => nodes.find(n => n.type === 'smart-group' && n.mcpGroupSourceId === id)", NODE_ID)
    assert group["title"] == "场景｜病房（S01 场景基准）", group
    assert len(group["memberIds"]) >= 2, group
    assert all(page.evaluate("id => nodes.find(n => n.id === id)?.images?.length", member_id) == 1 for member_id in group["memberIds"])
    group_element = page.locator(f'.image-node[data-id="{group["id"]}"]')
    assert group_element.locator('.canvas-group-title-display').inner_text() == group["title"]
    dragged_id = group["memberIds"][1]
    node = page.locator(f'.image-node[data-id="{dragged_id}"]')
    node.wait_for(state="visible", timeout=15000)
    page.wait_for_timeout(800)
    thumb = node.locator('.image-wrap img').first
    box = thumb.bounding_box()
    if not box or not (0 < box["x"] < 1440 and 0 < box["y"] < 900):
        page.evaluate("id => tcLocateNode(id)", NODE_ID)
        page.wait_for_timeout(500)
        box = thumb.bounding_box()
    print("thumb box", box, flush=True)
    def state(label):
        data = page.evaluate("id => { const n=nodes.find(n=>n.id===id); const el=document.querySelector(`[data-id='${id}']`); return {title:n?.title, images:n?.images?.length, dragState:dragState?.id, thumbDragState:thumbDragState?.nodeId, nodeRect:el?.getBoundingClientRect().toJSON(), thumbs:[...el.querySelectorAll('.image-wrap img')].map(img=>({complete:img.complete, naturalWidth:img.naturalWidth, rect:img.getBoundingClientRect().toJSON(), opacity:getComputedStyle(img).opacity, visibility:getComputedStyle(img).visibility}))} }", dragged_id)
        print(label, json.dumps(data, ensure_ascii=False), flush=True)
        assert data["images"] == 1, data
        assert data["thumbs"] and data["thumbs"][0]["complete"] and data["thumbs"][0]["naturalWidth"] > 0, data
        assert data["thumbs"][0]["visibility"] == "visible" and data["thumbs"][0]["opacity"] == "1", data
        page.screenshot(path=str(ROOT / f"_verification/mcp-group-{label}.png"))
    state("before")
    x, y = box["x"] + box["width"]/2, box["y"] + box["height"]/2
    hit = page.evaluate("([x,y]) => document.elementFromPoint(x,y)?.closest('.image-node')?.dataset?.id", [x,y])
    assert hit == dragged_id, {"expected": dragged_id, "hit": hit}
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x+40, y+20, steps=5)
    state("during")
    assert page.evaluate("() => dragState?.id") == dragged_id
    page.mouse.up()
    state("after")
    before_size = page.evaluate("id => {const n=nodes.find(n=>n.id===id); return {w:n.w,h:n.h}}", dragged_id)
    source_size = page.evaluate("id => {const n=nodes.find(n=>n.id===id); return {w:n.w,h:n.h}}", NODE_ID)
    handle = node.locator('.node-resize-handle')
    assert handle.count() == 1
    handle_box = handle.bounding_box()
    assert handle_box
    hx, hy = handle_box["x"]+handle_box["width"]/2, handle_box["y"]+handle_box["height"]/2
    page.mouse.move(hx, hy)
    page.mouse.down()
    page.mouse.move(hx+35, hy+20, steps=5)
    page.mouse.up()
    after_size = page.evaluate("id => {const n=nodes.find(n=>n.id===id); return {w:n.w,h:n.h}}", dragged_id)
    unchanged_source = page.evaluate("id => {const n=nodes.find(n=>n.id===id); return {w:n.w,h:n.h}}", NODE_ID)
    assert after_size["w"] > before_size["w"] and after_size["h"] > before_size["h"], (before_size, after_size)
    assert source_size == unchanged_source
    print("independent resize", json.dumps({"before":before_size,"after":after_size}), flush=True)
    browser.close()
