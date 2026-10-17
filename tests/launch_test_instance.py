# -*- coding: utf-8 -*-
"""隔离测试实例：独立端口 3217 + 每次回归独立用户数据目录，不碰 3107 正式实例。"""
import os
import sys
import threading

TEST_PORT = int(os.environ.get("MYRIDTV_TEST_PORT") or 3217)
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DATA = os.path.abspath(os.environ.get("MYRIDTV_TEST_DATA_DIR") or os.path.join(APP_ROOT, "_test_userdata"))
os.environ["MYRIDTV_USER_DATA_DIR"] = TEST_DATA
os.makedirs(TEST_DATA, exist_ok=True)

sys.path.insert(0, APP_ROOT)
import rh_official_proxy as proxy

proxy.PORT = TEST_PORT

# 2026-10-18：MCP_BASE 是 import 期定值（rh_official_proxy L1649 取 app_config 的
# base_url，apply_app_config 只重算 PORT 不重算它），测试实例必须显式重绑到自己的
# 端口，否则 MCP 工具（含 canvas_create）会把请求打到 3107 正式实例：画布建在真实
# 用户数据里、本实例读不到 -> GET /api/canvases/<id> 404，还污染真实画布列表。
_TEST_BASE = "http://127.0.0.1:{}".format(TEST_PORT)
proxy.MCP_BASE = _TEST_BASE
proxy.APP_BASE = _TEST_BASE
try:
    proxy.PROXY_CONFIG["port"] = TEST_PORT
    proxy.PROXY_CONFIG["base_url"] = _TEST_BASE
except Exception:
    pass
try:
    import myridtv_mcp
    myridtv_mcp.configure(_TEST_BASE)
except Exception as _exc:
    print("mcp base rebind failed:", _exc)


# 2026-10-15: 用 CanvasProxyServer（request_queue_size=128 + daemon_threads）而非裸
# ThreadingHTTPServer（默认 backlog=5）。冷启动拉 130+ 静态脚本时，5 的监听队列会在
# 浏览器并发握手的瞬间丢连接（status=-1）→ 模块未加载 → UI baseline 门随机缺全局。
# 这与生产入口（rh_official_proxy.py 的 CanvasProxyServer）保持一致。

proxy.append_log(proxy.LOG_FILE, f"[TEST] isolated instance starting pid={os.getpid()} port={TEST_PORT} data={TEST_DATA}")
try:
    proxy.patch_static_versions_once()
except Exception as exc:
    print("patch_static_versions_once failed:", exc)
threading.Thread(target=proxy.patch_static_versions_loop, daemon=True).start()

print(f"[TEST] serving on http://127.0.0.1:{TEST_PORT}", flush=True)
proxy.CanvasProxyServer(("127.0.0.1", TEST_PORT), proxy.Handler).serve_forever()
