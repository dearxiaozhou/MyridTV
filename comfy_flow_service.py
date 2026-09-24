"""ComfyUI 工作流服务层：节点元数据缓存 + 异步任务队列。

这里只管「怎么把工作流跑起来并跟踪进度」，图的改写逻辑在 comfy_flow_compiler 里。
模块不 import rh_official_proxy，下载产物等宿主能力通过 configure() 注入，避免循环依赖。
"""

from __future__ import annotations

import base64
import json
import os
import re
import socket
import struct
import threading
import time
import urllib.parse
import urllib.request
import uuid

from comfy_flow_compiler import CompileError, compile_prompt

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"
STATUS_GONE = "gone"  # 后端重启过，任务记录已丢失

JOB_TTL_SECONDS = 3600
JOB_KEEP_LIMIT = 60
COMFY_JOB_TIMEOUT_SECONDS = 3600


def _positive_env_int(name, default, low, high):
    try:
        value = int(str(os.environ.get(name) or "").strip() or default)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


# 同一时刻最多向 ComfyUI 提交多少个任务。默认 1 = 严格串行：
# ComfyUI 本来就单 worker 执行，串行提交既能杜绝显存竞争，又能让「排队第几位」可观测。
# 显存充裕想并发时，用环境变量 COMFY_JOB_CONCURRENCY 调大（1~8）。
COMFY_JOB_CONCURRENCY = _positive_env_int("COMFY_JOB_CONCURRENCY", 1, 1, 8)

# ---- 显存治理（2026-09-23）----
# 事故：上一个任务 finished 后 0.07 秒就把下一个塞给了 ComfyUI，下一个跑 10 秒后
# 报「VRAM grow failed: 250148864 bytes」。原因是 ComfyUI 写完 /history 就算完成，
# 但 PyTorch 的显存池要过一会儿才真正归还，紧接着提交必然撞上显存没释放完。
# 所以：每个任务收尾都主动让 ComfyUI 卸载模型 + 清缓存，再冷却几秒才交棒。
COMFY_JOB_COOLDOWN_SECONDS = _positive_env_int("COMFY_JOB_COOLDOWN_SECONDS", 5, 0, 120)

# 提交前要求的最小空闲显存（MB），不到就等，等不到才硬着头皮提交。0 = 不检查。
COMFY_JOB_MIN_FREE_VRAM_MB = _positive_env_int("COMFY_JOB_MIN_FREE_VRAM_MB", 2048, 0, 65536)
COMFY_JOB_VRAM_WAIT_SECONDS = _positive_env_int("COMFY_JOB_VRAM_WAIT_SECONDS", 120, 0, 900)

# 显存类失败自动重试：先 /free 再退避，最多重试 N 次。
COMFY_JOB_VRAM_RETRY = _positive_env_int("COMFY_JOB_VRAM_RETRY", 2, 0, 5)
COMFY_JOB_VRAM_RETRY_WAIT = _positive_env_int("COMFY_JOB_VRAM_RETRY_WAIT", 15, 1, 300)

# 命中这些关键词 = 显存不足，值得重试；其它错误（工作流填错、节点缺失）重试没意义。
_VRAM_ERROR_RE = re.compile(
    r"vram grow failed|out of memory|allocation on device|cudamalloc|failed to allocate"
    r"|not enough memory|vram state|cuda error|cublas|hip out of memory",
    re.I,
)

# 由宿主注入
_BASE_PROVIDER = None
_ASSET_SAVER = None
_OBJECT_INFO_CACHE_PATH = None
_DEFAULT_BASE = "http://127.0.0.1:8188"


def configure(base_provider=None, asset_saver=None, cache_path=None, job_store_path=None):
    """宿主（rh_official_proxy）在启动时注入环境相关的能力。"""
    global _BASE_PROVIDER, _ASSET_SAVER, _OBJECT_INFO_CACHE_PATH
    if base_provider is not None:
        _BASE_PROVIDER = base_provider
    if asset_saver is not None:
        _ASSET_SAVER = asset_saver
    if cache_path is not None:
        _OBJECT_INFO_CACHE_PATH = cache_path
    if job_store_path is not None:
        # 任务记录落盘：进程重启后才知道「之前提交过哪些 prompt_id」，
        # 前端才能按 prompt_id 把 ComfyUI 已经跑完的结果认领回画布节点。
        MANAGER.set_store_path(str(job_store_path))


def comfy_base():
    if _BASE_PROVIDER:
        try:
            base = str(_BASE_PROVIDER() or "").strip().rstrip("/")
            if base:
                return base
        except Exception:
            pass
    return _DEFAULT_BASE


def _request_json(path, method="GET", payload=None, timeout=120):
    raw = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(comfy_base() + path, data=raw, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def _is_vram_error(message):
    """是不是「显存不够」这类值得自动重试的错误。"""
    return bool(_VRAM_ERROR_RE.search(str(message or "")))


def _free_comfy_memory(unload_models=True, free_memory=True):
    """让 ComfyUI 卸载模型并清空显存缓存。失败不影响主流程。"""
    try:
        _request_json(
            "/free",
            "POST",
            {"unload_models": bool(unload_models), "free_memory": bool(free_memory)},
            timeout=60,
        )
        return True
    except Exception:
        return False


def _vram_free_bytes():
    """读 ComfyUI 报告的空闲显存（字节）。拿不到返回 None——此时按「不阻塞」处理。"""
    try:
        stats = _request_json("/system_stats", "GET", timeout=15)
    except Exception:
        return None
    devices = stats.get("devices") if isinstance(stats, dict) else None
    for device in devices or []:
        if not isinstance(device, dict):
            continue
        if str(device.get("type") or "").lower() != "cuda":
            continue
        try:
            return int(device.get("vram_free") or 0)
        except (TypeError, ValueError):
            return None
    return None


# --------------------------------------------------------------------------
# 节点元数据（/object_info）
# --------------------------------------------------------------------------

_object_info_cache = {"data": None, "loaded_at": 0}
_object_info_lock = threading.Lock()
OBJECT_INFO_TTL_SECONDS = 3600


def load_object_info(force=False, timeout=180):
    """取 ComfyUI 全量 /object_info，带内存缓存与磁盘缓存。

    全量响应有 8MB 上下，前端不可能整包吃下，所以这里只在后端持有，
    对外通过 object_info_subset() 按 class_type 切片返回。
    """
    now = time.time()
    with _object_info_lock:
        cached = _object_info_cache.get("data")
        if cached and not force and now - _object_info_cache.get("loaded_at", 0) < OBJECT_INFO_TTL_SECONDS:
            return cached
        if cached is None and _OBJECT_INFO_CACHE_PATH and os.path.exists(_OBJECT_INFO_CACHE_PATH):
            try:
                with open(_OBJECT_INFO_CACHE_PATH, "r", encoding="utf-8") as handle:
                    disk = json.load(handle)
                if isinstance(disk, dict) and disk:
                    _object_info_cache["data"] = disk
                    _object_info_cache["loaded_at"] = now
                    return disk
            except Exception:
                pass
        data = _request_json("/object_info", timeout=timeout)
        _object_info_cache["data"] = data
        _object_info_cache["loaded_at"] = now
        if _OBJECT_INFO_CACHE_PATH:
            try:
                os.makedirs(os.path.dirname(_OBJECT_INFO_CACHE_PATH), exist_ok=True)
                with open(_OBJECT_INFO_CACHE_PATH, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, ensure_ascii=False)
            except Exception:
                pass
        return data


def object_info_subset(class_types=None):
    """按 class_type 切片返回节点元数据；不传则只返回全部类型名。"""
    data = load_object_info()
    if not class_types:
        return {"types": sorted(data.keys()), "count": len(data)}
    wanted = {str(x) for x in class_types if str(x).strip()}
    return {name: data[name] for name in wanted if name in data}


# --------------------------------------------------------------------------
# 最小 WebSocket 客户端（RFC6455 文本帧）
# --------------------------------------------------------------------------
# ComfyUI 的运行期进度只有 ws 才有（executing / progress 事件）。装第三方库会污染
# 打包环境，所以这里手写一个够用的子集：握手 + 掩码发送 + 文本帧接收。


class MiniWebSocket:
    def __init__(self, host, port, path, on_message, timeout=10):
        self.host = host
        self.port = port
        self.path = path
        self.on_message = on_message
        self.timeout = timeout
        self.sock = None
        self._running = False
        self._thread = None

    def connect(self):
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        self.sock.sendall(handshake.encode("ascii"))
        buffer = b""
        while b"\r\n\r\n" not in buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("WebSocket 握手失败：连接被关闭")
            buffer += chunk
        head = buffer.split(b"\r\n\r\n", 1)[0].decode("ascii", "ignore")
        if " 101 " not in head.split("\r\n", 1)[0]:
            raise ConnectionError("WebSocket 握手失败：" + head.split("\r\n", 1)[0])
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _read_exact(self, count):
        data = b""
        while len(data) < count:
            chunk = self.sock.recv(count - len(data))
            if not chunk:
                raise ConnectionError("WebSocket 连接中断")
            data += chunk
        return data

    def _recv_frame(self):
        header = self._read_exact(2)
        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._read_exact(8))[0]
        mask = self._read_exact(4) if masked else None
        payload = self._read_exact(length) if length else b""
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload

    def _loop(self):
        while self._running:
            try:
                opcode, payload = self._recv_frame()
            except (socket.timeout, TimeoutError):
                continue
            except Exception:
                break
            if opcode == 0x8:
                break
            if opcode in (0x1, 0x2):
                try:
                    self.on_message(json.loads(payload.decode("utf-8")))
                except Exception:
                    pass

    def close(self):
        self._running = False
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass


def open_progress_stream(client_id, on_message):
    """订阅 ComfyUI 的运行期事件，返回一个 close() 回调。

    优先用宿主已装的 websockets 库；装不上就退回手写的 MiniWebSocket。
    两者都失败时返回空的 close()，任务照常靠轮询 /history 完成，只是没有节点级进度。
    """
    host, port = _ws_endpoint()
    path = "/ws?clientId=" + urllib.parse.quote(str(client_id))

    try:
        from websockets.sync.client import connect as ws_connect
    except Exception:
        ws_connect = None

    if ws_connect is not None:
        try:
            connection = ws_connect(f"ws://{host}:{port}{path}", open_timeout=10)

            def _pump():
                try:
                    for raw in connection:
                        try:
                            on_message(json.loads(raw))
                        except Exception:
                            continue
                except Exception:
                    return

            threading.Thread(target=_pump, daemon=True).start()
            return connection.close
        except Exception:
            pass

    try:
        return MiniWebSocket(host, port, path, on_message, timeout=5).connect().close
    except Exception:
        return lambda: None


def _ws_endpoint():
    parsed = urllib.parse.urlparse(comfy_base())
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 8188)
    return host, port


# --------------------------------------------------------------------------
# 异步任务
# --------------------------------------------------------------------------


class ComfyJob:
    def __init__(self, job_id, workflow_name, prompt, client_id="", meta=None):
        self.id = job_id
        self.workflow_name = workflow_name
        self.prompt = prompt
        self.client_id = client_id
        # 提交参数快照（overrides/modes/refs 计数等），供任务控制台展示"当时提交了什么"
        self.meta = meta if isinstance(meta, dict) else {}
        self.status = STATUS_QUEUED
        self.progress = 0
        self.current_node = ""
        self.current_node_title = ""
        self.images = []
        self.videos = []
        self.error = ""
        self.report = {}
        self.prompt_id = ""
        self.created_at = time.time()
        self.started_at = 0
        self.finished_at = 0
        self._cancel_requested = False
        # 排队位次：-1=不在队列（已出队/已完成/历史恢复），0=队首（正在跑或即将跑），>=1=前方还有几个
        self.queue_position = -1
        # 节点 id -> 标题，供运行期进度展示；随 job 一起入队，worker 才能拿到
        self.node_titles = {}
        # 显存不足自动重试的次数（0 = 还没重试过）
        self.vram_retry = 0
        # 运行期提示语，给前端显示「等待显存释放…」「显存不足，正在重试(1/2)」
        self.notice = ""

    def to_dict(self):
        elapsed = int((self.finished_at or time.time()) - (self.started_at or self.created_at))
        return {
            "job_id": self.id,
            "workflow_name": self.workflow_name,
            "status": self.status,
            "meta": self.meta,
            "progress": self.progress,
            "current_node": self.current_node,
            "current_node_title": self.current_node_title,
            "images": self.images,
            "videos": self.videos,
            "error": self.error,
            "report": self.report,
            "prompt_id": self.prompt_id,
            "queue_position": self.queue_position,
            "vram_retry": self.vram_retry,
            "notice": self.notice,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed": max(0, elapsed),
            "cancellable": self.status in (STATUS_QUEUED, STATUS_RUNNING),
        }


class JobManager:
    def __init__(self):
        self._jobs = {}
        self._lock = threading.RLock()
        self._store_path = None
        # FIFO 队列：存 job_id，保证同一时刻最多 COMFY_JOB_CONCURRENCY 个任务提交给 ComfyUI。
        # 之前是「提交即起线程、无并发上限」，多任务会一次性全塞进 ComfyUI，
        # 排队不可见且容易显存竞争失败。
        self._queue = []
        self._workers = 0

    # ---- 落盘（后端重启后任务不丢）----

    def set_store_path(self, path):
        self._store_path = str(path) if path else None
        self._load()

    def _load(self):
        if not self._store_path or not os.path.exists(self._store_path):
            return
        try:
            with open(self._store_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        now = time.time()
        with self._lock:
            for job_id, item in raw.items():
                if not isinstance(item, dict):
                    continue
                job = ComfyJob(str(job_id), str(item.get("workflow_name") or ""), {}, "", meta=item.get("meta") if isinstance(item.get("meta"), dict) else {})
                job.prompt_id = str(item.get("prompt_id") or "")
                try:
                    job.created_at = float(item.get("created_at") or now)
                    job.started_at = float(item.get("started_at") or 0)
                    job.finished_at = float(item.get("finished_at") or 0)
                except (TypeError, ValueError):
                    job.created_at, job.started_at, job.finished_at = now, 0, 0
                job.images = list(item.get("images") or [])
                job.videos = list(item.get("videos") or [])
                job.error = str(item.get("error") or "")
                status = str(item.get("status") or "")
                if status in (STATUS_QUEUED, STATUS_RUNNING):
                    # 轮询它的进程已经没了，别再假装还在跑；prompt_id 保留，
                    # 前端可以按 prompt_id 去 ComfyUI /history 认领结果。
                    status = STATUS_GONE
                    job.finished_at = job.finished_at or now
                    job.error = job.error or "后端重启，任务轮询中断"
                job.status = status or STATUS_GONE
                self._jobs[job.id] = job
        self._save()

    def _save(self):
        if not self._store_path:
            return
        try:
            with self._lock:
                data = {
                    job.id: {
                        "workflow_name": job.workflow_name,
                        "prompt_id": job.prompt_id,
                        "status": job.status,
                        "created_at": job.created_at,
                        "started_at": job.started_at,
                        "finished_at": job.finished_at,
                        "images": list(job.images),
                        "videos": list(job.videos),
                        "error": job.error,
                        "meta": job.meta,
                    }
                    for job in self._jobs.values()
                }
                target = self._store_path
            os.makedirs(os.path.dirname(target), exist_ok=True)
            tmp = target + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False)
            os.replace(tmp, target)
        except Exception:
            pass

    def submit(self, workflow_name, prompt, client_id="", node_titles=None, meta=None):
        job = ComfyJob(uuid.uuid4().hex[:12], workflow_name, prompt, client_id, meta=meta)
        job.node_titles = dict(node_titles or {})
        with self._lock:
            self._jobs[job.id] = job
            self._queue.append(job.id)
            self._prune()
            self._sync_positions_locked()
        self._save()
        self._pump()
        return job

    # ---- 队列调度：最多 COMFY_JOB_CONCURRENCY 个 worker 同时消费 ----

    def _pump(self):
        """补足 worker：队列里还有活、且没到并发上限时，再起一个消费线程。"""
        while True:
            with self._lock:
                if not self._queue or self._workers >= COMFY_JOB_CONCURRENCY:
                    return
                self._workers += 1
            threading.Thread(target=self._worker_loop, daemon=True).start()

    def _worker_loop(self):
        try:
            while True:
                with self._lock:
                    if not self._queue:
                        return
                    job_id = self._queue.pop(0)
                    job = self._jobs.get(job_id)
                    self._sync_positions_locked()
                if job is None:
                    continue
                self._run_with_vram_retry(job)
                with self._lock:
                    self._sync_positions_locked()
                    has_more = bool(self._queue)
                self._save()
                # 交棒清理。注意必须无条件 /free：worker 是「队列空了就退出」的，
                # 下一个任务可能由新起的 worker 接手，它不会再走一遍交棒，
                # 于是就成了「上一个刚 done、0.07 秒后就提交」的撞车现场。
                # 只有确实还排着队才额外冷却等待，队列空了就别白等这几秒。
                if not job._cancel_requested:
                    self._release_between_jobs(cooldown=has_more)
        finally:
            with self._lock:
                self._workers = max(0, self._workers - 1)
                has_more = bool(self._queue)
            if has_more:
                self._pump()

    def _run_with_vram_retry(self, job):
        """执行一次；若因显存不足失败且还有额度，就 /free + 退避后重跑。"""
        while True:
            try:
                self._run(job)
            except Exception:
                # _run 内部已兜底；这里只保证 worker 不会因为异常提前退出
                pass
            if not self._should_retry_vram(job):
                break
            job.vram_retry += 1
            job.status = STATUS_RUNNING
            job.progress = 0
            job.error = ""
            job.notice = "显存不足，正在重试（%d/%d）" % (job.vram_retry, COMFY_JOB_VRAM_RETRY)
            self._save()
            _free_comfy_memory()
            time.sleep(COMFY_JOB_VRAM_RETRY_WAIT)
        job.notice = ""

    def _should_retry_vram(self, job):
        """显存类失败才重试——工作流填错、节点缺失这类重试多少次都一样。"""
        if COMFY_JOB_VRAM_RETRY <= 0 or job is None:
            return False
        if job._cancel_requested or job.status != STATUS_ERROR:
            return False
        if job.vram_retry >= COMFY_JOB_VRAM_RETRY:
            return False
        return _is_vram_error(job.error)

    def _release_between_jobs(self, cooldown=True):
        """任务收尾：卸载模型 + 清缓存，必要时再冷却几秒。

        ComfyUI 写完 /history 就算「完成」，但显存池归还要时间。实测上一个
        finished 后 0.07 秒提交下一个，下一个跑 10 秒就 VRAM grow failed。

        /free 是无条件的（便宜且幂等），cooldown 只在后面还排着队时才等——
        队列空了还干等，下一个任务是几分钟后的事，白拖慢启动。
        """
        _free_comfy_memory()
        if cooldown and COMFY_JOB_COOLDOWN_SECONDS > 0:
            time.sleep(COMFY_JOB_COOLDOWN_SECONDS)

    def _wait_for_free_vram(self, job):
        """提交前等显存回到安全线；等超时或读不到显存就照常提交，不阻塞队列。"""
        if COMFY_JOB_MIN_FREE_VRAM_MB <= 0:
            return
        need = COMFY_JOB_MIN_FREE_VRAM_MB * 1024 * 1024
        deadline = time.time() + max(1, COMFY_JOB_VRAM_WAIT_SECONDS)
        freed = False
        while time.time() < deadline:
            if job._cancel_requested:
                break
            free = _vram_free_bytes()
            # 读不到显存（老版本 ComfyUI / 接口异常）就不拦，别把整个队列卡死
            if free is None or free >= need:
                break
            if not freed:
                # 先主动让 ComfyUI 卸模型清缓存，别干等着
                _free_comfy_memory()
                freed = True
            job.notice = "等待显存释放（空闲 %dMB / 需 %dMB）" % (
                int(free / 1048576), COMFY_JOB_MIN_FREE_VRAM_MB)
            time.sleep(2)
        job.notice = ""

    def _sync_positions_locked(self):
        """按当前队列顺序刷新每个 job 的 queue_position（调用方需持锁）。"""
        # 位次从 1 开始：1 = 下一个就跑。
        # 不能用 0 起步 —— 正在执行的任务已被 worker 从 _queue 里 pop 出去，
        # 若队首记为 0，前端「>0 才显示排队」的判定会让它看起来没在排队，
        # 可它其实还在等前面那个跑完。
        for index, job_id in enumerate(self._queue):
            job = self._jobs.get(job_id)
            if job is not None:
                job.queue_position = index + 1
        queued = set(self._queue)
        for job in self._jobs.values():
            if job.id not in queued:
                job.queue_position = -1

    def queue_snapshot(self):
        """对外暴露的队列视图：正在跑的 + 还在排的（含位次）。"""
        with self._lock:
            self._sync_positions_locked()
            # 正在跑的任务已被 worker 移出 _queue，所以只能按状态认，不能按队列位置认。
            running = [
                job.to_dict() for job in self._jobs.values()
                if job.status == STATUS_RUNNING
            ]
            pending = []
            for job_id in self._queue:
                job = self._jobs.get(job_id)
                if job is not None:
                    pending.append(job.to_dict())
            running.sort(key=lambda row: row.get("started_at") or 0)
            pending.sort(key=lambda row: row.get("queue_position") or 0)
            return {
                "ok": True,
                "concurrency": COMFY_JOB_CONCURRENCY,
                "running": running,
                "pending": pending,
                "running_count": len(running),
                "pending_count": len(pending),
            }

    def wait(self, job_id, timeout=COMFY_JOB_TIMEOUT_SECONDS, poll=0.5):
        """同步阻塞等任务结束，返回 job；超时返回最后一次看到的 job。

        只给「必须拿到产物 URL 才能往下走」的调用方用（Agent 工具、同步 API）。
        任务本身已经在队列里排队/执行，这里只是等，不会再额外占用 ComfyUI。
        """
        deadline = time.time() + max(1, float(timeout))
        job = self.get(job_id)
        while time.time() < deadline:
            if job is None:
                return None
            if job.status in (STATUS_DONE, STATUS_ERROR, STATUS_CANCELLED):
                return job
            time.sleep(poll)
            job = self.get(job_id)
        return job

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(str(job_id or "").strip())
        if not job:
            return None
        return job

    def cancel(self, job_id):
        job = self.get(job_id)
        if not job:
            return None
        job._cancel_requested = True
        # 只有真正在 ComfyUI 里跑起来的任务才需要 /interrupt；
        # 还在排队的一律只出队 —— 否则会把队首那个不相干的任务一起打断。
        should_interrupt = job.status == STATUS_RUNNING
        with self._lock:
            if job.id in self._queue:
                self._queue = [jid for jid in self._queue if jid != job.id]
                self._sync_positions_locked()
        if should_interrupt:
            try:
                _request_json("/interrupt", "POST", {}, timeout=10)
            except Exception:
                pass
        if job.status in (STATUS_QUEUED, STATUS_RUNNING):
            job.status = STATUS_CANCELLED
            job.finished_at = time.time()
        self._save()
        return job

    def list_jobs(self, limit=20):
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return [job.to_dict() for job in jobs[:limit]]

    def _prune(self):
        if len(self._jobs) <= JOB_KEEP_LIMIT:
            return
        now = time.time()
        stale = [
            job_id for job_id, job in self._jobs.items()
            if now - job.created_at > JOB_TTL_SECONDS
        ]
        for job_id in stale:
            self._jobs.pop(job_id, None)
        while len(self._jobs) > JOB_KEEP_LIMIT:
            oldest = min(self._jobs.values(), key=lambda j: j.created_at)
            self._jobs.pop(oldest.id, None)

    # ---- 执行体（跑在后台线程）----

    def _run(self, job):
        # 只有被 worker 从队列里取出来的任务才会走到这里，
        # 所以「还在 _queue 里」= 排队中(queued)，「进了 _run」= 运行中(running)。
        node_titles = job.node_titles or {}
        client_id = job.client_id or uuid.uuid4().hex
        close_stream = None
        try:
            def on_message(message):
                if not isinstance(message, dict):
                    return
                kind = str(message.get("type") or "")
                data = message.get("data")
                data = data if isinstance(data, dict) else {}
                if str(data.get("prompt_id") or "") and job.prompt_id and data.get("prompt_id") != job.prompt_id:
                    return
                if kind == "execution_start":
                    job.status = STATUS_RUNNING
                    job.started_at = job.started_at or time.time()
                elif kind == "executing":
                    node_id = str(data.get("node") or "")
                    if node_id:
                        job.current_node = node_id
                        job.current_node_title = str(node_titles.get(node_id) or "")
                    job.status = STATUS_RUNNING
                    job.started_at = job.started_at or time.time()
                elif kind == "progress":
                    value = data.get("value") or 0
                    maximum = data.get("max") or 0
                    try:
                        job.progress = int(float(value) / float(maximum) * 100) if maximum else 0
                    except (TypeError, ValueError, ZeroDivisionError):
                        job.progress = 0
                    node_id = str(data.get("node") or "")
                    if node_id:
                        job.current_node = node_id
                        job.current_node_title = str(node_titles.get(node_id) or "")
                elif kind == "execution_error":
                    job.status = STATUS_ERROR
                    job.error = str(data.get("exception_message") or "ComfyUI 执行出错")[:500]
                    job.finished_at = time.time()
                elif kind == "executed":
                    job.progress = max(job.progress, 99)

            # 拿不到节点级进度就退回纯轮询，不影响任务本身
            close_stream = open_progress_stream(client_id, on_message)

            # 提交前先确认显存够不够，不够就等一会儿（上一个任务的显存可能还没归还）
            self._wait_for_free_vram(job)

            submitted = _request_json(
                "/prompt", "POST", {"prompt": job.prompt, "client_id": client_id}, timeout=120
            )
            job.prompt_id = str(submitted.get("prompt_id") or "")
            self._save()
            if not job.prompt_id:
                raise RuntimeError("ComfyUI 未返回 prompt_id")
            if submitted.get("node_errors"):
                raise RuntimeError("工作流校验失败：" + json.dumps(submitted["node_errors"], ensure_ascii=False)[:400])
            job.status = STATUS_RUNNING
            job.started_at = job.started_at or time.time()

            history = None
            deadline = time.time() + COMFY_JOB_TIMEOUT_SECONDS
            while time.time() < deadline:
                if job._cancel_requested or job.status in (STATUS_CANCELLED, STATUS_ERROR):
                    break
                history_all = _request_json("/history/" + urllib.parse.quote(job.prompt_id), timeout=30)
                history = history_all.get(job.prompt_id) if isinstance(history_all, dict) else None
                if history:
                    break
                time.sleep(1)

            if job.status == STATUS_CANCELLED:
                return
            if job.status == STATUS_ERROR:
                return
            if not history:
                job.status = STATUS_ERROR
                job.error = f"ComfyUI 执行超时（{COMFY_JOB_TIMEOUT_SECONDS} 秒）"
                job.finished_at = time.time()
                return

            self._collect_outputs(job, history)
            if job.status != STATUS_ERROR:
                job.status = STATUS_DONE
                job.progress = 100
            job.finished_at = time.time()
        except Exception as exc:
            job.status = STATUS_ERROR
            job.error = str(exc)[:500]
            job.finished_at = time.time()
        finally:
            self._save()
            if close_stream:
                try:
                    close_stream()
                except Exception:
                    pass

    def _collect_outputs(self, job, history):
        outputs = history.get("outputs") if isinstance(history, dict) else {}
        if not isinstance(outputs, dict):
            job.error = "ComfyUI 没有返回任何输出"
            job.status = STATUS_ERROR
            return
        image_nodes = []
        video_nodes = []
        for node_id, node_output in outputs.items():
            if not isinstance(node_output, dict):
                continue
            if node_output.get("images"):
                image_nodes.append((str(node_id), node_output))
            elif node_output.get("videos") or node_output.get("gifs"):
                video_nodes.append((str(node_id), node_output))
        if len(image_nodes) > 1:
            image_nodes = [image_nodes[-1]]
        if len(video_nodes) > 1:
            video_nodes = [video_nodes[-1]]
        # 画布上下文：同步老路径会把产物归到画布专属目录，走队列后也得保持一致
        meta = job.meta if isinstance(job.meta, dict) else {}
        canvas_title = str(meta.get("canvas_title") or "").strip()
        canvas_id = str(meta.get("canvas_id") or "").strip()
        for _node_id, node_output in image_nodes:
            for item in node_output.get("images") or []:
                url = _save_asset(item, job.prompt_id, "image", canvas_title, canvas_id)
                if url:
                    job.images.append(url)
        for _node_id, node_output in video_nodes:
            for item in (node_output.get("videos") or []) + (node_output.get("gifs") or []):
                url = _save_asset(item, job.prompt_id, "video", canvas_title, canvas_id)
                if url:
                    job.videos.append(url)
        if not job.images and not job.videos:
            job.status = STATUS_ERROR
            job.error = job.error or "工作流跑完了但没有产出图片或视频"


def _save_asset(item, prompt_id, kind, canvas_title="", canvas_id=""):
    """落盘一张产物。canvas 上下文用于把图归到对应画布目录（同步老路径也依赖它）。"""
    if not _ASSET_SAVER:
        return ""
    try:
        try:
            return str(_ASSET_SAVER(comfy_base(), item, prompt_id, kind, canvas_title, canvas_id) or "")
        except TypeError:
            # 兼容只接受 4 个参数的简易 saver
            return str(_ASSET_SAVER(comfy_base(), item, prompt_id, kind) or "")
    except Exception:
        return ""


# COMFY_JOB_TIMEOUT_SECONDS 见模块顶部

MANAGER = JobManager()


def submit_job(workflow_record, overrides=None, modes=None, prefs=None, client_id="", meta=None):
    """编译 + 提交，返回 job 字典。工作流图在这里被改写成最终 prompt。"""
    from comfy_flow_compiler import describe_workflow  # 局部导入保持模块边界清晰

    workflow = workflow_record.get("workflow") if isinstance(workflow_record, dict) else None
    if not isinstance(workflow, dict) or not workflow:
        raise CompileError("工作流为空")
    object_info = load_object_info()
    prompt, report = compile_prompt(workflow, overrides, modes, object_info)
    titles = {}
    for item in describe_workflow(workflow, object_info, prefs):
        titles[item["id"]] = item["title"]
    job_meta = {
        "overrides": _compact_param_map(overrides),
        "modes": dict(modes or {}),
        "prefs": dict(prefs or {}),
        "node_titles": {str(k): str(v) for k, v in (titles or {}).items()},
        "params_flat": _flatten_overrides(overrides, titles),
    }
    if isinstance(meta, dict):
        job_meta.update(meta)
    job = MANAGER.submit(
        str(workflow_record.get("name") or ""),
        prompt,
        client_id,
        node_titles=titles,
        meta=job_meta,
    )
    job.report = report
    return job


def _flatten_overrides(overrides, node_titles=None, max_len=200):
    """把 {节点id: {输入名: 值}} 展平成 ["节点标题.输入名 = 值", ...]，供控制台展示。

    提示词类长文本截断；节点 id 翻译成人类可读标题（拿不到标题时退回 id）。
    """
    titles = {str(k): str(v) for k, v in (node_titles or {}).items()}
    flat = []
    for node_id, inputs in (overrides or {}).items():
        label = titles.get(str(node_id), str(node_id))
        if not isinstance(inputs, dict):
            continue
        for input_name, value in inputs.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            text = str(value if value is not None else "")
            if len(text) > max_len:
                text = text[:max_len] + "…"
            flat.append("{}.{} = {}".format(label, input_name, text))
            if len(flat) >= 40:
                return flat
    return flat


def _compact_param_map(mapping, max_len=400):
    """参数快照压缩：值截断，总键数封顶，避免超长提示词/二进制值撑爆落盘。"""
    out = {}
    for key, value in (mapping or {}).items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        text = str(value if value is not None else "")
        out[str(key)] = text if len(text) <= max_len else text[:max_len] + "…"
        if len(out) >= 60:
            break
    return out
