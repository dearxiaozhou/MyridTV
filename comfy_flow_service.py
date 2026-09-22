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
            "elapsed": max(0, elapsed),
            "cancellable": self.status in (STATUS_QUEUED, STATUS_RUNNING),
        }


class JobManager:
    def __init__(self):
        self._jobs = {}
        self._lock = threading.RLock()
        self._store_path = None

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
        with self._lock:
            self._jobs[job.id] = job
            self._prune()
        self._save()
        worker = threading.Thread(
            target=self._run,
            args=(job, node_titles or {}),
            daemon=True,
        )
        worker.start()
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

    def _run(self, job, node_titles):
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
        for _node_id, node_output in image_nodes:
            for item in node_output.get("images") or []:
                url = _save_asset(item, job.prompt_id, "image")
                if url:
                    job.images.append(url)
        for _node_id, node_output in video_nodes:
            for item in (node_output.get("videos") or []) + (node_output.get("gifs") or []):
                url = _save_asset(item, job.prompt_id, "video")
                if url:
                    job.videos.append(url)
        if not job.images and not job.videos:
            job.status = STATUS_ERROR
            job.error = job.error or "工作流跑完了但没有产出图片或视频"


def _save_asset(item, prompt_id, kind):
    if not _ASSET_SAVER:
        return ""
    try:
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
