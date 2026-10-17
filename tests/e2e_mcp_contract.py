"""Exercise the running app's /mcp endpoint and both real stdio adapters."""
import asyncio
import concurrent.futures
import json
import os
from pathlib import Path
import sys
import urllib.request
import uuid
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3227")
proof = {"base": BASE, "checks": []}
RUN = uuid.uuid4().hex


def check(name, condition):
    proof["checks"].append({"name": name, "passed": bool(condition)})
    print(("PASS " if condition else "FAIL ") + name, flush=True)
    if not condition:
        raise AssertionError(name)


def rpc(method, params=None):
    req = urllib.request.Request(BASE + "/mcp", data=json.dumps({"jsonrpc": "2.0", "id": 1,
        "method": method, "params": params or {}}, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read())


def call(name, **args):
    if args.get("idempotency_key"):
        args["idempotency_key"] = RUN + ":" + args["idempotency_key"]
    control = {k:args.pop(k) for k in ('canvas_id','workflow_id','idempotency_key','expected_updated_at') if k in args}
    result = rpc("tools/call", {"name": 'canvas_execute', "arguments": {'action':name.removeprefix('canvas_'),'params':args,**control}})
    if "error" in result:
        raise RuntimeError(result["error"])
    value = json.loads(result["result"]["content"][0]["text"])
    return value, result["result"].get("isError", False)


async def adapters(expected, cid):
    for filename in ("codex-canvas-mcp.py", "hermes-canvas-mcp.py", "claude-canvas-mcp.py"):
        params = StdioServerParameters(command=sys.executable, args=[str(ROOT / filename)],
            env={**os.environ, "MYRIDTV_MCP_BASE": BASE})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                check(filename + " 工具清单一致", {t.name: t.inputSchema for t in listed.tools} == expected)
                good = await session.call_tool("canvas_execute", {"action":"get_state","canvas_id": cid})
                check(filename + " 真实读取", not good.isError and json.loads(good.content[0].text)["canvas_id"] == cid)
                bad = await session.call_tool("canvas_execute", {"action":"get_node","canvas_id": cid,"params":{"node_id":"does-not-exist"}})
                check(filename + " 保留 isError", bad.isError)
                legacy = await session.call_tool("canvas_get_state", {"canvas_id":cid})
                check(filename + " 旧入口不能绕过", legacy.isError and json.loads(legacy.content[0].text).get('entrypoint')=='canvas_execute')


def main():
    tools = rpc("tools/list")["result"]["tools"]
    expected = {t["name"]: t["inputSchema"] for t in tools}
    check("只公开统一入口", set(expected) == {'canvas_execute'})
    initialized = rpc("initialize")["result"]
    check("MCP报告软件版本", initialized["serverInfo"]["version"] == (ROOT/'VERSION').read_text().strip().lstrip('V'))
    created, error = call("canvas_create", title="MCP V0.10.12 实机验证", idempotency_key="runtime-create")
    cid = created["canvas_id"]
    proof["canvas_id"] = cid
    again, _ = call("canvas_create", title="MCP V0.10.12 实机验证", idempotency_key="runtime-create")
    check("新建画布幂等", not error and again == created)
    _, error = call("canvas_create_node", type="text", text="缺少目标不应写入")
    check("未指定画布拒绝写入", error)
    node, error = call("canvas_create_node", canvas_id=cid, type="text", text="MCP完整正文验证", title="接口验证节点", idempotency_key="node-one")
    check("真实创建文本节点", not error and bool(node.get("node_id")))
    nid = node["node_id"]
    details, error = call("canvas_get_node", canvas_id=cid, node_id=nid)
    check("完整正文可读取", not error and details["node"]["text"] == "MCP完整正文验证")
    _, error = call("canvas_update_node", canvas_id=cid, node_id=nid, text="", expected_updated_at=details["updated_at"])
    details, _ = call("canvas_get_node", canvas_id=cid, node_id=nid)
    check("可清空正文", not error and details["node"]["text"] == "")
    call("canvas_update_node", canvas_id=cid, node_id=nid, text="MCP完整正文验证")
    details, _ = call("canvas_get_node", canvas_id=cid, node_id=nid)
    image, error = call("canvas_create_generation_node", canvas_id=cid, prompt="只配置，不提交生图", title="待生成节点",
                        aspect_ratio="16:9", resolution="2k", quality="high", count=1, idempotency_key="gen-node")
    check("真实配置生成节点不产生费用", not error and image.get("save_ok"))
    image_details, _ = call("canvas_get_node", canvas_id=cid, node_id=image["node_id"])
    check("可读取生成参数", bool(image_details["node"].get("runSettings")))
    connected, error = call("canvas_connect_nodes", canvas_id=cid, from_id=nid, to_id=image["node_id"], kind="input")
    check("真实连线", not error)
    snapshot, error = call("canvas_snapshot", canvas_id=cid, label="删除前快照", idempotency_key="snapshot-one")
    check("持久快照保存", not error and bool(snapshot.get("snapshot_id")))
    batch_args = {"canvas_id": cid, "operations": [{"op_type": "delete_node", "target_id": nid}], "idempotency_key": "delete-batch"}
    deleted, error = call("canvas_batch_operations", **batch_args)
    replay, _ = call("canvas_batch_operations", **batch_args)
    check("批量删除幂等", not error and replay == deleted)
    undone, error = call("canvas_undo_batch", canvas_id=cid, batch_id=deleted["batch_id"])
    restored, _ = call("canvas_get_node", canvas_id=cid, node_id=nid)
    check("撤销恢复删除节点", not error and undone["save_ok"] and restored["node"]["text"] == "MCP完整正文验证")
    before, _ = call("canvas_get_state", canvas_id=cid)
    _, error = call("canvas_batch_operations", canvas_id=cid, operations=[
        {"op_type": "update_node", "target_id": nid, "params": {"text": "不应保存"}},
        {"op_type": "layer_operate", "target_id": nid, "params": {"action": "invalid"}}])
    after, _ = call("canvas_get_node", canvas_id=cid, node_id=nid)
    check("批量失败整批不保存", error and after["node"]["text"] == "MCP完整正文验证" and after["updated_at"] == before["updated_at"])
    newer, _ = call("canvas_batch_operations", canvas_id=cid, operations=[{"op_type": "update_node", "target_id": nid, "params": {"text": "批量修改"}}])
    call("canvas_update_node", canvas_id=cid, node_id=nid, text="保留用户后续修改")
    _, error = call("canvas_undo_batch", canvas_id=cid, batch_id=newer["batch_id"])
    check("撤销阻止覆盖新修改", error)
    state, _ = call("canvas_get_state", canvas_id=cid)
    restored, error = call("canvas_restore_snapshot", canvas_id=cid, snapshot_id=snapshot["snapshot_id"], expected_updated_at=state["updated_at"])
    check("真实恢复快照", not error and restored.get("save_ok"))
    searched, error = call("canvas_search", canvas_id=cid, query="完整正文")
    check("正文搜索", not error and searched["matches"] == 1)
    listed, _ = call("canvas_list_canvases")
    fixture = next(c for c in listed if c["title"] == "MCP任务查询验证")
    for status in ("running", "failed", "succeeded"):
        result, error = call("canvas_check_generation", canvas_id=fixture["id"], task_id="mcp-fixture-" + status)
        check("任务查询 " + status, not error and result.get("status") == status)
        if status == "succeeded":
            check("任务查询返回嵌套结果图片", result["images"][0]["url"] == "/assets/fixture.png")
    _, error = call("canvas_check_generation", canvas_id=cid, task_id="missing")
    check("不存在的任务明确报错", error)
    _, error = call("canvas_check_generation", canvas_id=cid, task_id="mcp-fixture-succeeded")
    check("跨画布任务拦截", error)
    def read(i):
        target = cid if i % 2 else fixture["id"]
        return call("canvas_get_state", canvas_id=target)[0]["canvas_id"] == target
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        check("真实HTTP跨画布并发读取", all(pool.map(read, range(32))))
    asyncio.run(adapters(expected, cid))
    proof["tools"] = list(expected)

    # Exercise the real app frontend against the same isolated backend.
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.route("**/static/app_config.json*", lambda route: route.fulfill(
            content_type="application/json", body=json.dumps({"proxy": {"base_url": BASE, "port": 3227}})))
        page.goto(BASE + "/static/smart-canvas.html?id=" + cid, wait_until="domcontentloaded")
        page.wait_for_function("id => typeof canvas !== 'undefined' && canvas && canvas.id === id", arg=cid, timeout=30000)
        page.locator('[data-id="' + nid + '"]').first.wait_for(state="visible", timeout=15000)
        page.wait_for_function("id => nodes.some(n => n.id === id && n.text === 'MCP完整正文验证')", arg=nid)
        page.evaluate("() => fitAllNodesViewport()")
        page.locator('[data-id="' + nid + '"]').first.get_by_text("MCP完整正文验证", exact=True).wait_for(state="visible", timeout=10000)
        check("真实前端显示恢复后的节点正文", True)
        page.screenshot(path=str(ROOT / "_verification/mcp-v01012-canvas.png"), full_page=True)
        page.goto(BASE + "/static/index.html", wait_until="domcontentloaded")
        check("运行界面版本信息", page.locator(".app-version").first.text_content().strip().endswith('版本：'+(ROOT/'VERSION').read_text().strip()))
        page.screenshot(path=str(ROOT / "_verification/mcp-v01012-home.png"), full_page=True)
        browser.close()


if __name__ == "__main__":
    try:
        main()
    finally:
        (ROOT / "_verification/mcp-v01012-runtime.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
