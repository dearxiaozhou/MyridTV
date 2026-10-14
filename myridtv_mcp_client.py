"""Shared stdio bridge client. The running backend is the schema authority."""
import itertools
import json
import os
from pathlib import Path
import urllib.request

_ids = itertools.count(1)


def backend_base(config_file=None):
    override = os.environ.get('MYRIDTV_MCP_BASE', '').strip()
    if override:
        return override.rstrip('/')
    path = Path(config_file) if config_file else Path(__file__).resolve().parent / '_internal/data/app_config.json'
    try:
        config = json.loads(path.read_text(encoding='utf-8-sig'))
        proxy = config.get('proxy') if isinstance(config, dict) else {}
        proxy = proxy if isinstance(proxy, dict) else {}
        if proxy.get('base_url'):
            return str(proxy['base_url']).rstrip('/')
        if proxy.get('port'):
            return f"http://{proxy.get('host') or '127.0.0.1'}:{int(proxy['port'])}"
    except (OSError, ValueError, TypeError):
        pass
    return 'http://127.0.0.1:3107'


def post(method, params=None):
    body = json.dumps({"jsonrpc": "2.0", "id": next(_ids), "method": method,
                       "params": params or {}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(backend_base() + "/mcp", data=body, method="POST",
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
