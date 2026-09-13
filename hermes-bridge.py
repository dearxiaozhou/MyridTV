#!/usr/bin/env python3
"""
Hermes Agent Canvas Bridge — OpenAI 兼容 API + 画布桥接
MyridTV 可以通过注册自定义 API 平台来连接此桥接。
"""

import json, os, sys, subprocess, time, uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

VERSION = "0.2.0"
SERVICE = "hermes-canvas-agent"
PORT = 47329


class BridgeHandler(BaseHTTPRequestHandler):
    connected = False

    def log_message(self, fmt, *args):
        if args:
            print(f"[bridge] {args[0]}")

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode() if length else ""

    # ============ OpenAI 兼容 API ============

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/v1/models":
            self._send_json({
                "object": "list",
                "data": [
                    {"id": "hermes-agent", "object": "model", "created": int(time.time()), "owned_by": "nous"},
                    {"id": "hermes-canvas", "object": "model", "created": int(time.time()), "owned_by": "nous"},
                ]
            })
        elif path in ("/health", "/agent/health"):
            self._send_json({
                "ok": True, "service": SERVICE, "version": VERSION,
                "connected": self.connected, "expose": "/agent/connect",
            })
        elif path in ("/capabilities", "/agent/capabilities"):
            quick = parse_qs(parsed.query).get("mode", [""])[0] == "quick"
            self._send_json({
                "ok": True,
                "capabilities": ["create_node", "connect_nodes", "run_generation", "chat_completion"],
                "mode": "quick" if quick else "full",
            })
        elif path == "/agent":
            self._send_json({"ok": True, "service": SERVICE, "version": VERSION})
        else:
            self._send_json({"error": "not found", "status": 404}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        # OpenAI 聊天补全接口
        if path == "/v1/chat/completions":
            self._handle_chat_completion()
            return

        # 画布桥接
        if path in ("/connect", "/agent/connect"):
            self.connected = True
            self._send_json({"ok": True, "connected": True, "message": "已链接"})
            return
        if path == "/disconnect":
            self.connected = False
            self._send_json({"ok": True, "connected": False, "message": "已断开"})
            return

        self._send_json({"error": "not found", "status": 404}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    # ============ 核心处理 ============

    def _handle_chat_completion(self):
        body = self._read_body()
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON", "status": 400}, 400)
            return

        messages = data.get("messages", [])
        model = data.get("model", "hermes-agent")
        stream = data.get("stream", False)

        # 提取最后一条用户消息
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = msg.get("content", "")
                break

        print(f"[bridge] chat: model={model} len={len(last_user)} stream={stream}")

        if stream:
            self._handle_stream(last_user, model)
        else:
            self._handle_sync(last_user, model)

    def _handle_sync(self, prompt, model):
        try:
            result = subprocess.run(
                ["hermes", "chat", "-q", "--no-tools", prompt],
                capture_output=True, text=True, timeout=180
            )
            reply = result.stdout.strip() or "（无回复）"
        except subprocess.TimeoutExpired:
            reply = "（请求超时）"
        except Exception as e:
            reply = f"（错误：{e}）"

        resp = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": reply},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": -1, "completion_tokens": -1, "total_tokens": -1},
        }
        self._send_json(resp)

    def _handle_stream(self, prompt, model):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            result = subprocess.run(
                ["hermes", "chat", "-q", "--no-tools", prompt],
                capture_output=True, text=True, timeout=180
            )
            reply = result.stdout.strip() or "（无回复）"
        except Exception as e:
            reply = f"（错误：{e}）"

        # 流式输出（作为一个 chunk 发出，简化实现）
        chunk = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
        }
        self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Hermes Agent Canvas Bridge")
    parser.add_argument("--port", type=int, default=PORT, help=f"端口 (默认 {PORT})")
    args = parser.parse_args()

    server = HTTPServer(("127.0.0.1", args.port), BridgeHandler)
    print(f"\n{'='*55}")
    print(f"  Hermes Agent Canvas Bridge v{VERSION}")
    print(f"  {'='*55}")
    print(f"  OpenAI API: http://127.0.0.1:{args.port}/v1")
    print(f"  画布桥接:  http://127.0.0.1:{args.port}/agent")
    print(f"")
    print(f"  请先在 API 设置中新增自定义平台：")
    print(f"    请求地址 → http://127.0.0.1:{args.port}/v1")
    print(f"    协议     → OpenAI 直连")
    print(f"  然后在 Agent 配置中选择该平台即可。")
    print(f"{'='*55}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[bridge] 已停止")
        server.server_close()


if __name__ == "__main__":
    main()
