"""Migrate the user's named canvas in the real app, with a recoverable snapshot."""
import json
from pathlib import Path
import urllib.request
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:3107"
CANVAS_ID = "6584629"
NODE_ID = "agent_ad446e2d8408"


def get_canvas():
    with urllib.request.urlopen(BASE + "/api/canvases/" + CANVAS_ID, timeout=10) as response:
        return json.loads(response.read())["canvas"]


def mcp(name, arguments):
    body = json.dumps({"jsonrpc":"2.0", "id":1, "method":"tools/call",
                       "params":{"name":name, "arguments":arguments}}, ensure_ascii=False).encode()
    req = urllib.request.Request(BASE + "/mcp", data=body, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=20) as response:
        reply = json.loads(response.read())
    if reply.get("error") or reply.get("result", {}).get("isError"):
        raise RuntimeError(reply)
    return json.loads(reply["result"]["content"][0]["text"])


before = get_canvas()
source = next(n for n in before["nodes"] if n["id"] == NODE_ID)
if len(source.get("images") or []) != 2 or source.get("__origin") != "mcp_update":
    raise RuntimeError("目标节点已变化，停止迁移")
prior_urls = [image["url"] for image in source["images"]]
snapshot = mcp("canvas_snapshot", {"canvas_id": CANVAS_ID, "label": "V0.10.13 MCP双图修复前"})
print("snapshot_id=" + snapshot["snapshot_id"], flush=True)

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{BASE}/static/smart-canvas.html?id={CANVAS_ID}&focus_node={NODE_ID}", wait_until="domcontentloaded")
    page.wait_for_function("id => nodes.some(n => n.type === 'smart-group' && n.mcpGroupSourceId === id)", arg=NODE_ID, timeout=30000)
    page.wait_for_timeout(1500)
    page.screenshot(path=str(ROOT / "_verification/mcp-group-v01013-real-canvas.png"))
    group = page.evaluate("id => nodes.find(n => n.type === 'smart-group' && n.mcpGroupSourceId === id)", NODE_ID)
    assert group["title"] == source["title"]
    page.wait_for_function("id => fetch('/api/canvases/'+id).then(r=>r.json()).then(d=>d.canvas.nodes.some(n=>n.type==='smart-group' && n.mcpGroupSourceId==='agent_ad446e2d8408'))", arg=CANVAS_ID, timeout=20000)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function("id => nodes.some(n => n.type === 'smart-group' && n.mcpGroupSourceId === id)", arg=NODE_ID, timeout=30000)
    browser.close()

after = get_canvas()
groups = [n for n in after["nodes"] if n.get("type") == "smart-group" and n.get("mcpGroupSourceId") == NODE_ID]
assert len(groups) == 1, groups
members = [next(n for n in after["nodes"] if n["id"] == mid) for mid in groups[0]["memberIds"]]
assert len(members) == 2
assert all(len(n.get("images") or []) == 1 for n in members)
assert [n["images"][0]["url"] for n in members] == prior_urls
assert groups[0]["title"] == source["title"]
assert next(n for n in members if n["id"] == NODE_ID)["runSettings"] == source["runSettings"]
print(json.dumps({"ok":True, "snapshot_id":snapshot["snapshot_id"], "group_id":groups[0]["id"],
                  "member_ids":groups[0]["memberIds"], "title":groups[0]["title"],
                  "image_count":len(members), "updated_at":after["updated_at"]}, ensure_ascii=False), flush=True)
