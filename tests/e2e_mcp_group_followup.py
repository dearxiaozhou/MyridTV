"""Check a later generated image joins the existing native group once."""
import json
from pathlib import Path
import urllib.request
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:3107"
CANVAS_ID = "6584629"
SOURCE_ID = "agent_ad446e2d8408"


def read():
    with urllib.request.urlopen(BASE + "/api/canvases/" + CANVAS_ID, timeout=10) as reply:
        return json.loads(reply.read())["canvas"]


before = read()
source = next(n for n in before["nodes"] if n["id"] == SOURCE_ID)
group = next(n for n in before["nodes"] if n.get("type") == "smart-group" and n.get("mcpGroupSourceId") == SOURCE_ID)
all_urls = {image["url"] for n in before["nodes"] if n["id"] in group["memberIds"] for image in n.get("images", [])}
all_urls.update(image["url"] for image in source.get("images", []))

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{BASE}/static/smart-canvas.html?id={CANVAS_ID}&focus_node={group['id']}", wait_until="domcontentloaded")
    page.wait_for_function("id => nodes.some(n => n.id === id)", arg=group["id"], timeout=30000)
    page.wait_for_function("([sourceId,count]) => {const s=nodes.find(n=>n.id===sourceId);const g=nodes.find(n=>n.type==='smart-group' && n.mcpGroupSourceId===sourceId);return s?.images?.length===1 && g?.memberIds?.length>=count}", arg=[SOURCE_ID,len(all_urls)], timeout=30000)
    page.wait_for_timeout(1300)
    page.screenshot(path=str(ROOT / "_verification/mcp-group-v01013-followup.png"))
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function("id => nodes.some(n=>n.type==='smart-group' && n.mcpGroupSourceId===id)", arg=SOURCE_ID, timeout=30000)
    page.wait_for_timeout(700)
    browser.close()

after = read()
group = next(n for n in after["nodes"] if n.get("type") == "smart-group" and n.get("mcpGroupSourceId") == SOURCE_ID)
members = [next(n for n in after["nodes"] if n["id"] == mid) for mid in group["memberIds"]]
urls = [image["url"] for n in members for image in n.get("images", [])]
assert len(urls) == len(set(urls)), urls
assert all_urls.issubset(set(urls)), {"missing": list(all_urls - set(urls))}
assert all(len(n.get("images") or []) == 1 for n in members)
assert next(n for n in members if n["id"] == SOURCE_ID)["images"][0]["url"] == source["images"][0]["url"]
print(json.dumps({"ok":True,"group_id":group["id"],"title":group["title"],
                  "members":len(members),"unique_urls":len(urls),"source_images":1}, ensure_ascii=False),flush=True)
