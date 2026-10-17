"""Run the actual app Handler with isolated data/config; never stop the user's app."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import myridtv_env

PORT = int(os.environ.get("MYRIDTV_TEST_PORT", "3227"))
runtime = tempfile.TemporaryDirectory(prefix="myridtv-mcp-verification-")
root = Path(runtime.name)
os.environ["MYRIDTV_USER_DATA_DIR"] = str(root / "userdata")
os.environ["MYRIDTV_ASSETS_DIR"] = str(root / "assets")


def isolated_config():
    config = copy.deepcopy(myridtv_env._G_DEFAULT_CONFIG)
    config["proxy"] = {"host": "127.0.0.1", "port": PORT, "base_url": f"http://127.0.0.1:{PORT}"}
    config["paths"] = {"env_file": str(root / "empty.env"), "logs_dir": str(root / "logs"),
                       "proxy_log": str(root / "logs/proxy.log"), "startup_log": str(root / "logs/startup.log")}
    return config


myridtv_env.load_app_config = isolated_config
myridtv_env.write_static_app_config = lambda raw: None
import rh_official_proxy as app

# Deterministic task fixtures exercise the actual HTTP/MCP query route, without API charges.
canvas = app.myridtv_canvas_store.create_canvas_record({"title": "MCP任务查询验证", "nodes": [
    {"id": "fixture-node", "type": "smart-image", "title": "任务结果", "images": []}]})
for status in ("running", "failed", "succeeded"):
    app.myridtv_task_state.set_task_state("mcp-fixture-" + status, {
        "status": status, "backend": "verification", "canvas_id": canvas["id"], "node_id": "fixture-node",
        "localized_at": time.time(), "result": {"images": [{"url": "/assets/fixture.png"}]},
        "error": "验证失败分支" if status == "failed" else ""})
print(json.dumps({"ready": True, "port": PORT, "fixture_canvas_id": canvas["id"]}), flush=True)
server = app.ThreadingHTTPServer(("127.0.0.1", PORT), app.Handler)
try:
    server.serve_forever()
finally:
    server.server_close()
    runtime.cleanup()
