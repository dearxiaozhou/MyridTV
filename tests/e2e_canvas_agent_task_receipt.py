# -*- coding: utf-8 -*-
"""Exercise duplicate Agent task completion in the running canvas UI."""
import os
import json
import time
import urllib.request
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
CHROMIUM = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=["--no-sandbox"])
    page = browser.new_page()
    page.goto(BASE + "/smart-canvas.html", wait_until="domcontentloaded")
    page.wait_for_function("typeof finalizeSmartPendingTask === 'function'")
    result = page.evaluate("""async () => {
        canvas = {id:'', logs:[]};
        const taskId = 'regression_agent_task_1';
        const node = {
            id:'regression_node', type:'smart-image', title:'Regression image',
            __origin:'agent_tool_generation', images:[], pending:1,
            pendingTasks:[{taskId,kind:'image'}],
            runSettings:{engine:'api',provider_id:'runninghub',model:'test-model'},
            runPrompt:'test prompt', runStartedAt:Date.now()-1000
        };
        const output = [{url:'/assets/input/regression.png',name:'regression.png',kind:'image'}];
        await Promise.all([
            finalizeSmartPendingTask(node,taskId,output,'image'),
            finalizeSmartPendingTask(node,taskId,output,'image')
        ]);
        const first = {images:node.images.length,logs:canvas.logs.length,
            imageTaskId:node.images[0]?.generationTaskId,logTaskId:canvas.logs[0]?.taskId};
        const restored = JSON.parse(JSON.stringify(node));
        await finalizeSmartPendingTask(restored,taskId,output,'image');
        return {first,afterReloadImages:restored.images.length,afterReloadLogs:canvas.logs.length};
    }""")
    browser.close()

assert result == {
    "first": {"images": 1, "logs": 1,
              "imageTaskId": "regression_agent_task_1", "logTaskId": "regression_agent_task_1"},
    "afterReloadImages": 1,
    "afterReloadLogs": 1,
}, result
print("PASS: concurrent and repeated completion keeps one image and one canvas log")


def api(method, path, payload=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(BASE + path, data=body, method=method,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import myridtv_agent_generation
import myridtv_agent_state

myridtv_agent_state._port_getter = lambda: int(BASE.rsplit(":", 1)[-1])
created = api("POST", "/api/canvases", {"title": "Agent task receipt regression"})["canvas"]
canvas_id = created["id"]
node_id = "agent_regression_node"
node = {"id": node_id, "type": "smart-image", "title": "Regression image",
        "__origin": "agent_tool_generation", "runPrompt": "test prompt",
        "runSettings": {"provider_id": "runninghub", "model": "test-model"}, "images": []}
api("PUT", "/api/canvases/" + canvas_id, {"nodes": [node], "base_updated_at": created["updated_at"]})
task_id = "regression_backend_task_1"
state = {"status": "succeeded", "canvas_id": canvas_id, "node_id": node_id,
         "provider_id": "runninghub", "model": "test-model",
         "created_at": time.time() - 2, "completed_at": time.time(),
         "result": {"images": [{"url": "/assets/input/regression.png"}]}}
myridtv_agent_generation.record_agent_generation_task_log(task_id, state)
myridtv_agent_generation.record_agent_generation_task_log(task_id, state)
canvas = api("GET", "/api/canvases/" + canvas_id)["canvas"]
assert len(canvas["logs"]) == 1 and canvas["logs"][0]["taskId"] == task_id, canvas["logs"]
api("PUT", "/api/canvases/" + canvas_id,
    {"logs": [], "base_updated_at": canvas["updated_at"]})
canvas = api("GET", "/api/canvases/" + canvas_id)["canvas"]
assert len(canvas["logs"]) == 1, canvas["logs"]
assert myridtv_agent_generation._agent_attach_result_to_node(
    canvas_id, canvas, node_id, ["/assets/input/regression.png"], task_id)
canvas = api("GET", "/api/canvases/" + canvas_id)["canvas"]
assert myridtv_agent_generation._agent_attach_result_to_node(
    canvas_id, canvas, node_id, ["/assets/input/regression.png"], task_id)
canvas = api("GET", "/api/canvases/" + canvas_id)["canvas"]
assert len(canvas["nodes"][0]["images"]) == 1, canvas["nodes"][0]["images"]
print("PASS: backend receipt survives a stale save and repeated check attaches one image")

api("PUT", "/api/canvases/" + canvas_id, {
    "nodes": [], "deleted": [{"id": node_id, "at": int(time.time() * 1000), "by": "regression"}],
    "base_updated_at": canvas["updated_at"]})
myridtv_agent_generation.record_agent_generation_task_log(
    "regression_deleted_node_task_2", {**state, "node_title": "Deleted node"})
canvas = api("GET", "/api/canvases/" + canvas_id)["canvas"]
assert len(canvas["logs"]) == 2, canvas["logs"]
print("PASS: completed Agent task keeps its receipt after the node is deleted")
