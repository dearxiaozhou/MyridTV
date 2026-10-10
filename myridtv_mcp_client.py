"""Shared stdio bridge client. The running backend is the schema authority."""
import itertools
import json
import os
import urllib.request

BACKEND = os.environ.get("MYRIDTV_MCP_BASE", "http://127.0.0.1:3107").rstrip("/")
_ids = itertools.count(1)


def post(method, params=None):
    body = json.dumps({"jsonrpc": "2.0", "id": next(_ids), "method": method,
                       "params": params or {}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BACKEND + "/mcp", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    # Vision/workflow tools can exceed ten seconds. A timeout is an unknown outcome;
    # callers retry writes with the same idempotency_key, never blindly submit twice.
    with opener.open(req, timeout=3600 if method == "tools/call" else 15) as response:
        result = json.loads(response.read().decode("utf-8"))
    if "error" in result:
        raise RuntimeError(result["error"].get("message", str(result["error"])))
    return result


def load_tools():
    # Fetch each discovery request; a disconnected startup cannot pin stale schemas.
    return post("tools/list")["result"]["tools"]


def call_tool(name, arguments):
    return post("tools/call", {"name": name, "arguments": arguments or {}})["result"]
