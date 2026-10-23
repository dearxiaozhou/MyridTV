"""宿主侧自检：确认 claude-canvas-mcp.py → MyridTV 后端这条链是通的。

必须在**运行 MyridTV 的那台机器**上跑（后端只绑 127.0.0.1）。
用法：双击 测试画布MCP.cmd，或直接 `python 测试画布MCP.py`
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.join(HERE, "claude-canvas-mcp.py")


def read_base():
    override = (os.environ.get("MYRIDTV_MCP_BASE") or "").strip()
    if override:
        return override.rstrip("/")
    path = os.path.join(os.environ.get("APPDATA", ""), "MyridTV", "data", "app_config.json")
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            config = json.load(handle)
        proxy = config.get("proxy") or {}
        if proxy.get("base_url"):
            return str(proxy["base_url"]).rstrip("/")
        if proxy.get("port"):
            return "http://{}:{}".format(proxy.get("host") or "127.0.0.1", int(proxy["port"]))
    except (OSError, ValueError, TypeError):
        pass
    return "http://127.0.0.1:3113"


def step(number, title):
    print("\n[{}/3] {}".format(number, title))


def main():
    base = read_base()
    print("后端基址：{}".format(base))
    print("适配器　：{}".format(BRIDGE))

    ok = True

    step(1, "后端 /health")
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(base + "/health", timeout=5) as response:
            print("    " + response.read().decode("utf-8", "replace")[:300])
    except Exception as exc:
        ok = False
        print("    ✗ 不可达：{}".format(exc))
        print("    → 先确认 MyridTV 正在运行（启动研发版.cmd）。")

    step(2, "经 stdio 桥 tools/list")
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "selftest", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    payload = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in requests)
    try:
        proc = subprocess.run(
            [sys.executable, BRIDGE],
            input=payload, capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
    except Exception as exc:
        ok = False
        print("    ✗ 桥启动失败：{}".format(exc))
        return 1 if not ok else 0

    names = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if message.get("id") == 2:
            if "error" in message:
                ok = False
                print("    ✗ {}".format(message["error"].get("message")))
            else:
                names = [tool.get("name") for tool in message.get("result", {}).get("tools", [])]
                print("    共 {} 个工具".format(len(names)))
    if names:
        want = ("canvas_get_state", "canvas_create_generation_node", "canvas_upsert_flow")
        for tool in want:
            print("    {} {}".format("✓" if tool in names else "·", tool))
    if proc.stderr:
        print("    stderr: " + (proc.stderr.strip().splitlines() or [""])[0])

    step(3, "真实读一次画布 3253737")
    call = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                       "params": {"name": "canvas_get_state",
                                  "arguments": {"canvas_id": "3253737"}}}, ensure_ascii=False)
    try:
        proc = subprocess.run(
            [sys.executable, BRIDGE],
            input=call + "\n", capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        text = ""
        for line in (proc.stdout or "").splitlines():
            if not line.strip():
                continue
            message = json.loads(line)
            if message.get("id") == 3:
                if "error" in message:
                    ok = False
                    print("    ✗ {}".format(message["error"].get("message")))
                else:
                    text = json.dumps(message.get("result", {}), ensure_ascii=False)
        if text:
            print("    " + text[:400])
    except Exception as exc:
        ok = False
        print("    ✗ {}".format(exc))

    print("\n" + ("=== 通过：可以把它挂到 Claude 当 MCP 用了 ===" if ok
                  else "=== 未通过：先让 MyridTV 跑起来再看上面哪一步断的 ==="))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())