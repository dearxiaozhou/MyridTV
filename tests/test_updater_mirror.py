"""Mirror fallback tests for myridtv_updater (GitHub -> Gitee raw file tree).

Runs standalone with the system Python (no pytest required):
    python tests/test_updater_mirror.py
"""
import importlib.util
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("myridtv_updater", REPO / "myridtv_updater.py")
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class _FailHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(500)
        self.end_headers()
        self.wfile.write(b"boom")
    def log_message(self, *args):
        pass


class _OkHandler(BaseHTTPRequestHandler):
    payload = b"mirror-ok"

    def do_GET(self):
        body = self.payload
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass


def _start(handler, port):
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ---- remap_to_gitee: 结构化 URL 重写（GitHub release -> Gitee raw 文件树） ----

def test_remap_release_url_to_gitee_raw():
    url = "https://github.com/dearxiaozhou/MyridTV-updates/releases/download/V0.10.9/blob-abc"
    assert updater.remap_to_gitee(url) == (
        "https://gitee.com/myridtv/myrid-tv-updates/raw/master/V0.10.9/blob-abc")


def test_remap_latest_feed_to_gitee_root():
    url = "https://github.com/dearxiaozhou/MyridTV-updates/releases/latest/download/update-manifest.json"
    assert updater.remap_to_gitee(url) == (
        "https://gitee.com/myridtv/myrid-tv-updates/raw/master/update-manifest.json")


def test_remap_non_github_returns_none():
    assert updater.remap_to_gitee("https://gitee.com/x/y/raw/master/V0.10.9/blob") is None
    assert updater.remap_to_gitee("http://127.0.0.1:9001/file") is None


def test_mirror_candidates_includes_remap():
    url = "https://github.com/dearxiaozhou/MyridTV-updates/releases/download/V0.10.9/blob-abc"
    cands = updater.mirror_candidates(url)
    assert cands[0] == url
    assert "https://gitee.com/myridtv/myrid-tv-updates/raw/master/V0.10.9/blob-abc" in cands


def test_mirror_candidates_no_extra_for_gitee_raw():
    url = "https://gitee.com/myridtv/myrid-tv-updates/raw/master/V0.10.9/blob-abc"
    assert updater.mirror_candidates(url) == [url]


def test_mirror_candidates_extra_prefix():
    url = "http://127.0.0.1:9001/file"
    cands = updater.mirror_candidates(url, extra=[("127.0.0.1:9001", "127.0.0.1:9002")])
    assert "http://127.0.0.1:9002/file" in cands


# ---- get_bytes 集成：主源失败自动回退镜像 ----

def test_get_bytes_falls_back_to_mirror():
    _OkHandler.payload = b"from-mirror"
    _start(_FailHandler, 9001)
    _start(_OkHandler, 9002)
    url = "http://127.0.0.1:9001/file"
    data = updater.get_bytes(
        url, limit=1024, allow_local=True, fast=True,
        mirror_hosts=[("127.0.0.1:9001", "127.0.0.1:9002")],
    )
    assert data == b"from-mirror"


def test_get_bytes_prefers_primary_when_ok():
    _OkHandler.payload = b"from-primary"
    _start(_OkHandler, 9003)
    _start(_FailHandler, 9004)
    url = "http://127.0.0.1:9003/file"
    data = updater.get_bytes(
        url, limit=1024, allow_local=True, fast=True,
        mirror_hosts=[("127.0.0.1:9003", "127.0.0.1:9004")],
    )
    assert data == b"from-primary"


def test_get_bytes_raises_when_all_fail():
    _start(_FailHandler, 9005)
    _start(_FailHandler, 9006)
    url = "http://127.0.0.1:9005/file"
    raised = False
    try:
        updater.get_bytes(
            url, limit=1024, allow_local=True, fast=True,
            mirror_hosts=[("127.0.0.1:9005", "127.0.0.1:9006")],
        )
    except Exception:  # noqa: BLE001
        raised = True
    assert raised


def test_humanize_error_chinese():
    assert "超时" in updater.humanize_error(ConnectionError("WinError 10060"))
    assert "中断" in updater.humanize_error(RuntimeError("SSL: UNEXPECTED_EOF"))


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        else:
            print(f"PASS {t.__name__}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
