# -*- coding: utf-8 -*-
"""隔离测试实例：独立端口 3217 + 独立用户数据目录，不碰老王的 3107 正式实例。
用完即杀，不留后台进程。
"""
import os
import sys
import threading

TEST_PORT = 3217
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DATA = os.path.join(APP_ROOT, "_test_userdata")
os.environ["MYRIDTV_USER_DATA_DIR"] = TEST_DATA
os.makedirs(TEST_DATA, exist_ok=True)

sys.path.insert(0, APP_ROOT)
import rh_official_proxy as proxy

proxy.PORT = TEST_PORT

from http.server import ThreadingHTTPServer

proxy.append_log(proxy.LOG_FILE, f"[TEST] isolated instance starting pid={os.getpid()} port={TEST_PORT}")
try:
    proxy.patch_static_versions_once()
except Exception as exc:
    print("patch_static_versions_once failed:", exc)
threading.Thread(target=proxy.patch_static_versions_loop, daemon=True).start()

print(f"[TEST] serving on http://127.0.0.1:{TEST_PORT}", flush=True)
ThreadingHTTPServer(("127.0.0.1", TEST_PORT), proxy.Handler).serve_forever()
