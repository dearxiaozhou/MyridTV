"""Claude 桌面版 stdio 适配器 → MyridTV 权威 MCP 后端（POST /mcp）。

与 hermes-canvas-mcp.py / codex-canvas-mcp.py 同一套路，唯一区别是**零第三方依赖**：
只用标准库，所以宿主上任何 python3 都能直接跑，不需要装 `mcp` 包、不需要建 venv。

后端地址解析顺序（与 myridtv_mcp_client.py 保持一致）：
  1. 环境变量 MYRIDTV_MCP_BASE
  2. %APPDATA%\\MyridTV\\data\\app_config.json 的 proxy.base_url / proxy.port
  3. http://127.0.0.1:3113

注意：MyridTV 后端只绑 127.0.0.1，所以本进程必须在**运行 MyridTV 的那台机器**上启动。
stdout 只输出 JSON-RPC；所有日志走 stderr。
"""

import itertools
import json
import os
import sys
import time
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:3113"
PROTOCOL_VERSION = "2024-11-05"

# 每次被宿主进程拉起都记一行，用来判断"服务到底有没有被启动"——
# 会话里看不到 canvas_* 工具时，靠这个把"注册没生效"和"注册生效但会话没刷新"分开。
SPAWN_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "canvas-mcp-bridge.log")

_ids = itertools.count(1)
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def log(message):
    sys.stderr.write("[myridtv-canvas] {}\n".format(message))
    sys.stderr.flush()


def _hostname():
    """记日志用：区分"宿主上被 App 拉起"和"被沙箱误拉起"（后者是 linux）。"""
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return "?"


def probe_backend(start=3107, end=3130):
    """app_config 失效时按 /health 逐个端口问，谁能应答就用谁。

    与 myridtv_mcp_client.py 的 _probe_backend 同一行为：启动器在端口占不住时
    会把后端往后挪（3107→+1..+20）并回写 app_config，所以死记默认值不能当作最终答案。
    """
    for port in range(start, end):
        try:
            with _opener.open("http://127.0.0.1:{}/health".format(port), timeout=0.6) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if isinstance(data, dict) and data.get("ok"):
            return "http://127.0.0.1:{}".format(port)
    return None


def backend_base():
    override = (os.environ.get("MYRIDTV_MCP_BASE") or "").strip()
    if override:
        return override.rstrip("/")
    config_path = os.path.join(os.environ.get("APPDATA", ""), "MyridTV", "data", "app_config.json")
    try:
        with open(config_path, "r", encoding="utf-8-sig") as handle:
            config = json.load(handle)
        proxy = config.get("proxy") if isinstance(config, dict) else None
        proxy = proxy if isinstance(proxy, dict) else {}
        if proxy.get("base_url"):
            return str(proxy["base_url"]).rstrip("/")
        if proxy.get("port"):
            return "http://{}:{}".format(proxy.get("host") or "127.0.0.1", int(proxy["port"]))
    except (OSError, ValueError, TypeError):
        pass
    return probe_backend() or DEFAULT_BASE


BASE = backend_base()


def post(method, params=None):
    global BASE
    body = json.dumps(
        {"jsonrpc": "2.0", "id": next(_ids), "method": method, "params": params or {}},
        ensure_ascii=False,
    ).encode("utf-8")
    # 生图 / 看图类工具会远超十秒。超时意味着"结果未知"：
    # 调用方应按同一 idempotency_key 重试，而不是换键盲目重发。
    timeout = 3600 if method == "tools/call" else 15

    def _attempt(base):
        request = urllib.request.Request(
            base + "/mcp",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with _opener.open(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        return _attempt(BASE)
    except Exception:
        # 后端端口运行中可能漂移（10-14 3107→3113 事故）：BASE 是 import 期固化的，
        # 不重解析的话，后端一重启换端口，整个会话就僵死在旧端口上直到宿主重启。
        # 失败一次就重新解析再试；显式的 MYRIDTV_MCP_BASE 仍优先——指错了就老实
        # 报错，不偷偷覆盖用户显式指定的地址。
        BASE = backend_base()
        return _attempt(BASE)


def send(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def reply_ok(request_id, result):
    send({"jsonrpc": "2.0", "id": request_id, "result": result})


def reply_error(request_id, code, message):
    send({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def handle(request):
    method = request.get("method") or ""
    request_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        client_version = str(params.get("protocolVersion") or "").strip()
        reply_ok(request_id, {
            "protocolVersion": client_version or PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "myridtv-canvas", "version": "1.0.0"},
        })
        return

    if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
        return

    if method == "ping":
        reply_ok(request_id, {})
        return

    if method == "tools/list":
        try:
            tools = post("tools/list").get("result", {}).get("tools", [])
        except Exception as exc:
            reply_error(request_id, -32000, "MyridTV 后端不可达 {}: {}".format(BASE, exc))
            return
        reply_ok(request_id, {"tools": tools})
        return

    if method == "tools/call":
        try:
            answer = post("tools/call", {
                "name": params.get("name"),
                "arguments": params.get("arguments") or {},
            })
        except Exception as exc:
            reply_error(request_id, -32000, "MyridTV 后端不可达 {}: {}".format(BASE, exc))
            return
        if "error" in answer:
            error = answer.get("error") or {}
            reply_error(request_id, error.get("code", -32000), error.get("message", str(error)))
            return
        reply_ok(request_id, answer.get("result", {}))
        return

    if request_id is None:
        return
    reply_error(request_id, -32601, "本桥不处理该方法: {}".format(method))


def main():
    try:
        with open(SPAWN_LOG, "a", encoding="utf-8") as fh:
            fh.write("{}  spawned  pid={}  platform={}  host={}  backend={}\n".format(
                time.strftime("%Y-%m-%d %H:%M:%S"), os.getpid(), sys.platform,
                _hostname(), BASE))
    except OSError:
        pass
    log("stdio 桥已启动；后端={}".format(BASE))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            continue
        try:
            handle(request)
        except Exception as exc:  # 单个请求出错不能拖垮整条 stdio 通道
            log("handler error: {}".format(exc))
            if isinstance(request, dict) and request.get("id") is not None:
                reply_error(request["id"], -32603, str(exc))


if __name__ == "__main__":
    main()