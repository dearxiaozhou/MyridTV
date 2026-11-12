# -*- coding: utf-8 -*-
"""MyridTV ComfyUI 平台域（后端拆分第7刀）：实例配置写回、实例基址解析、Comfy HTTP、
workflow 字段注入、输出节点挑选/构建提交/轮询、产物 URL 映射、最近输出与簇拆分。

逐字迁移自 rh_official_proxy.py 连续块 L(write_comfy_instances)..L(create_workflow_record)
（11 函数 316 行，可逆还原行级 diff=0）。行为零变更。
configure() 注入：COMFY_WORKFLOW_POLL_TIMEOUT_SECONDS 值（import 时定、零重绑）、
LOG_FILE getter、7 个块外函数 lambda 闭包（instances 读写族 / media_localize 产物路径族 /
read_workflow_record）。core 直用 ApiError/append_log/write_json_file。
主文件对块外仍调用的 6 函数留同名薄代理，调用点不改。
"""
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
import threading

_COMFY_LOCALIZE_LOCK = threading.Lock()
# 日期序号占用名缓存（按输出目录维度）：避免每次落盘都全目录 rglob。
# 结构：{str(output_dir): {"date": "MM-DD", "used": set(已占用文件名)}}
# 跨天自动失效重建；分配时仍有「顶层 + history/ 各一次 exists()」兜底校验，
# 外部（手动产物/归档移动）新占用的名字不会被重复分配。
_COMFY_NAME_CACHE = {}

import comfy_flow_service
from comfy_flow_compiler import compile_prompt as compile_comfy_prompt
from comfy_flow_compiler import normalize_aspect_ratios
from myridtv_libraries import read_workflow_record

from myridtv_core import ApiError, append_log, write_json_file

_POLL_TIMEOUT = 600
_log_file = lambda: None
_USER_DATA_DIR = None
_r_comfy_instances_file_path = None
_r_read_comfy_instances = None
_r_normalize_comfy_instances = None
_r_asset_output_media_dir = None
_r_asset_output_url = None
_r_canvas_output_folder_name = None
_r_read_workflow_record = None
_r_save_workflow_config = None


# ComfyUI 媒体加载节点：class_type -> 文件名输入键。
# 用于：① 提交前“死文件”体检；② 导入工作流时自动暴露素材槽。
_COMFY_MEDIA_LOADERS = {
    "LoadImage": "image",
    "LoadImageMask": "image",
    "LoadMask": "mask",
    "LoadAudio": "audio",
    "LoadVideo": "video",
    "VHS_LoadVideo": "video",
    "VHS_LoadVideoPath": "video",
    "VHS_LoadAudioUpload": "audio",
    "Load3D": "file",
    "LoadVector": "vector",
    "LoadGLTF": "glb",
}


def configure(user_data_dir, poll_timeout, log_file_getter,
              comfy_instances_file_path, read_comfy_instances, normalize_comfy_instances,
              asset_output_media_dir, asset_output_url, canvas_output_folder_name,
              read_workflow_record, save_workflow_config=None):
    global _USER_DATA_DIR, _POLL_TIMEOUT, _log_file
    _USER_DATA_DIR = user_data_dir
    global _r_comfy_instances_file_path, _r_read_comfy_instances, _r_normalize_comfy_instances
    global _r_asset_output_media_dir, _r_asset_output_url, _r_canvas_output_folder_name
    global _r_read_workflow_record
    _POLL_TIMEOUT = poll_timeout
    _log_file = log_file_getter
    _r_comfy_instances_file_path = comfy_instances_file_path
    _r_read_comfy_instances = read_comfy_instances
    _r_normalize_comfy_instances = normalize_comfy_instances
    _r_asset_output_media_dir = asset_output_media_dir
    _r_asset_output_url = asset_output_url
    _r_canvas_output_folder_name = canvas_output_folder_name
    _r_read_workflow_record = read_workflow_record
    global _r_save_workflow_config
    _r_save_workflow_config = save_workflow_config

    # 服务层注入（原块顶层 comfy_flow_service.configure，依赖注入值故挪到此处）
    comfy_flow_service.configure(
        base_provider=comfy_instance_base,
        asset_saver=comfy_output_asset_url,
        cache_path=_USER_DATA_DIR / "cache" / "comfy_object_info.json",
        job_store_path=_USER_DATA_DIR / "data" / "comfy_jobs.json",
        ensure_alive=ensure_comfy_alive,
    )


def write_comfy_instances(instances):
    safe = _r_normalize_comfy_instances(instances)
    write_json_file(_r_comfy_instances_file_path(), {"instances": safe})
    return safe


def comfy_instance_base():
    instances = _r_read_comfy_instances()
    raw = instances[0] if instances else "127.0.0.1:8188"
    if isinstance(raw, dict):
        raw = raw.get("url") or ""
    base = str(raw or "").strip()
    if not base:
        base = "127.0.0.1:8188"
    if not re.match(r"^https?://", base, re.I):
        base = "http://" + base
    return base.rstrip("/")


# --------------------------------------------------------------------------
# ComfyUI 自动拉起（实例配置了本地路径时，连接不上就先拉起再继续任务）
# --------------------------------------------------------------------------
import socket as _socket
import subprocess as _subprocess
import shutil as _shutil

_COMFY_LAUNCH_LOCK = threading.Lock()
_COMFY_LAUNCHED = set()  # base -> 本进程已尝试拉起过（避免重复 Popen）
# 自动拉起进行中标记（顶栏状态灯的「启动中」黄灯数据源）
_COMFY_LAUNCH_STATE = {"launching": False}


def _parse_host_port(base):
    """'http://127.0.0.1:8188/' -> ('127.0.0.1', 8188)"""
    s = str(base or "").strip().rstrip("/")
    if not re.match(r"^https?://", s, re.I):
        s = "http://" + s
    parsed = urllib.parse.urlparse(s)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8188
    return host, port


def _comfy_port_open(host, port, timeout=1.5):
    try:
        with _socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _find_bundled_python(comfy_dir):
    """只找随 ComfyUI 分发/项目自带的 python（便携版 / 独立包 / venv），不做系统兜底。"""
    d = Path(comfy_dir)
    for c in (
        d / "python_embeded" / "python.exe",
        d / "python" / "python.exe",          # 独立包变体（如 F:/ComfyUI/python）
        d / "venv" / "Scripts" / "python.exe",
        d / ".venv" / "Scripts" / "python.exe",
    ):
        if c.is_file():
            return str(c)
    return None


def _find_python(comfy_dir):
    """自带 python 优先，系统 python 仅作最后兜底。"""
    return _find_bundled_python(comfy_dir) or _shutil.which("python") or _shutil.which("python3")


def _is_bundled_runtime(py_path, comfy_dir):
    """python 是否为随 ComfyUI 分发的独立运行时（python_embeded / python 目录）——
    这类运行时跑 main.py 需要带 --windows-standalone-build（官方 bat 就是这么调的），
    否则会去找系统目录的依赖而崩。venv / 系统 python 不加。"""
    try:
        p = Path(py_path).resolve()
    except Exception:
        return False
    for anchor in (Path(comfy_dir), Path(comfy_dir).parent):
        try:
            anchor = anchor.resolve()
        except Exception:
            continue
        for name in ("python_embeded", "python"):
            runtime_root = anchor / name
            try:
                if runtime_root.is_dir() and anchor in p.parents:
                    return True
            except Exception:
                continue
    return False


def _build_launch_cmd(comfy_dir, host, port):
    """根据本地路径推导 (cwd, args)；识别不了返回 None。

    兼容三种布局：
      1. 指向启动脚本（.bat/.cmd/.exe）——直接用。
      2. 标准/独立包目录：run_*.bat / start*.bat / 启动*.bat（中文命名），或 main.py + 自带 python。
      3. 填了内层源码目录（main.py 所在）而启动环境（bat / python 运行时）在外一层——
         自动向上一层找（老王的 F:\\ComfyUI\\ComfyUI 就是这种）。"""
    d = Path(comfy_dir)
    if not d.exists():
        return None
    if d.is_file() and d.suffix.lower() in (".bat", ".cmd", ".exe", ".ps1"):
        return (str(d.parent), [str(d)])
    if not d.is_dir():
        return None
    # 候选目录：填的目录 + 父层
    dirs = [d]
    if d.parent != d:
        dirs.append(d.parent)
    # 启动脚本优先：bat 自带正确的环境设置（cwd / standalone 标志 / 端口默认 8188）
    for cur in dirs:
        for pat in ("run_*.bat", "run_*.cmd", "start*.bat", "start*.cmd",
                    "启动*.bat", "启动*.cmd"):
            hits = sorted(cur.glob(pat))
            if hits:
                return (str(cur), [str(hits[0])])
    # main.py + 自带 python（当前层找不到运行时就看父层；系统 python 仅作最后兜底）
    for cur in dirs:
        main_py = cur / "main.py"
        if not main_py.is_file():
            continue
        py = (_find_bundled_python(cur) or _find_bundled_python(cur.parent)
              or _shutil.which("python") or _shutil.which("python3"))
        if not py:
            continue
        args = [py, str(main_py), "--listen", host, "--port", str(port)]
        if _is_bundled_runtime(py, cur):
            args.append("--windows-standalone-build")
        return (str(cur), args)
    return None


def ensure_comfy_alive(base):
    """访问 ComfyUI 前确保其在线。后端自动拉起逻辑（仅依赖配置里的本地路径）：

    - 端口已通：直接返回（最快路径，已开着时不闪「正在启动」）。
    - 不通且配了本地路径：自动探测启动方式（main.py / run_*.bat）拉起，轮询等就绪（最多 90s）。
    - 不通且没配路径：什么也不做，交给上层按原逻辑报错。

    拉起失败 / 端口冲突时抛 RuntimeError（会透传到前端节点失败提示）。"""
    host, port = _parse_host_port(base)
    if _comfy_port_open(host, port):
        return True
    # 只取第一个配置了本地路径的实例（简化后只需填一个路径）
    instances = _r_read_comfy_instances()
    path = ""
    for it in instances:
        p = str((it or {}).get("path") or "").strip()
        if p:
            path = p
            break
    if not path:
        return True

    with _COMFY_LAUNCH_LOCK:
        if _comfy_port_open(host, port):
            return True
        # 子进程输出重定向到 DEVNULL（避免继承父进程管道导致调用方无法退出 / 管道泄漏），
        # 并进入独立进程组，不随本进程信号一并被终止。
        _launch_stdout = _subprocess.DEVNULL
        _launch_stderr = _subprocess.DEVNULL
        _launch_flags = getattr(_subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        built = _build_launch_cmd(path, host, port)
        if not built:
            raise RuntimeError(
                f"ComfyUI 本地路径无法识别启动方式：{path}\n"
                f"请填启动脚本（如 启动ComfyUI.bat / run_nvidia_gpu.bat）所在的目录，"
                f"或含 main.py 的 ComfyUI 目录。"
            )
        cwd, args = built
        append_log(_log_file(), f"comfy auto-launch: cwd={cwd} args={args}")
        _subprocess.Popen(args, cwd=cwd, stdout=_launch_stdout, stderr=_launch_stderr, creationflags=_launch_flags)
        _COMFY_LAUNCHED.add(base)
        _COMFY_LAUNCH_STATE["launching"] = True

    # 轮询等端口就绪（最多 90s）；期间顶栏状态灯亮黄（comfy_status.launching）
    try:
        deadline = time.time() + 90
        while time.time() < deadline:
            if _comfy_port_open(host, port, timeout=2):
                append_log(_log_file(), f"comfy auto-launch ready: {base}")
                return True
            time.sleep(1.5)
        raise RuntimeError(
            f"已尝试自动拉起 ComfyUI（{path}），但 {host}:{port} 在 90 秒内仍未就绪。"
            f"请手动启动 ComfyUI 后重试，或检查日志。"
        )
    finally:
        _COMFY_LAUNCH_STATE["launching"] = False


def comfy_status():
    """ComfyUI 在线状态（顶栏状态灯轮询用，轻量、不打日志）：
    online=端口已通（绿灯）；launching=自动拉起进行中（黄灯）；都不满足=未启动（红灯）。"""
    try:
        host, port = _parse_host_port(comfy_instance_base())
        online = _comfy_port_open(host, port, timeout=0.6)
    except Exception:
        online = False
    return {"online": bool(online), "launching": bool(_COMFY_LAUNCH_STATE.get("launching"))}


def comfy_start_async():
    """顶栏状态灯「启动」：后台线程拉起 ComfyUI（不阻塞 HTTP，黄灯立即亮起）。
    返回 (thread, error)；已在线时返回 (None, None)（前端靠轮询看到绿灯）。"""
    path = ""
    for it in _r_read_comfy_instances():
        p = str((it or {}).get("path") or "").strip()
        if p:
            path = p
            break
    if not path:
        return None, "未配置 ComfyUI 本地路径，请先到「工作流设置」里填写"
    base = comfy_instance_base()
    host, port = _parse_host_port(base)
    if _comfy_port_open(host, port, timeout=0.6):
        return None, None

    _COMFY_LAUNCH_STATE["launching"] = True  # 先亮黄灯（ensure 内部会再置一次，finally 统一复位）

    def _worker():
        try:
            ensure_comfy_alive(base)
        except Exception:
            pass  # 失败原因已落日志；launching 由 ensure 的 finally 复位 → 前端回落红灯

    t = threading.Thread(target=_worker, daemon=True, name="comfy-ui-toggle-start")
    t.start()
    return t, None


def _pid_listening_on_port(port):
    """返回监听指定 TCP 端口的进程 PID（netstat 解析），找不到返回 None。"""
    try:
        raw = _subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, timeout=10,
        ).stdout or b""
    except Exception:
        return None
    # 中文 Windows 的 netstat 输出是 GBK（表头「活动连接」等），utf-8 直接解会炸
    try:
        out = raw.decode("gbk", errors="replace")
    except Exception:
        out = raw.decode("utf-8", errors="replace")
    for line in out.splitlines():
        parts = line.split()
        # TCP    127.0.0.1:8188    0.0.0.0:0    LISTENING    1234
        if len(parts) >= 5 and parts[3].upper() == "LISTENING":
            local = parts[1]
            if local.rsplit(":", 1)[-1] == str(port):
                return parts[4]
    return None


def comfy_stop():
    """顶栏状态灯「退出」：杀掉监听 ComfyUI 端口的进程树（/T 带走子进程）。
    按 PID 精确制导，不按映像名乱杀——别人家的 python 进程不受影响。"""
    host, port = _parse_host_port(comfy_instance_base())
    pid = _pid_listening_on_port(port)
    if not pid:
        return {"stopped": False}
    try:
        # 不带 text=True：中文 Windows 的 taskkill 输出是 GBK，utf-8 解码会在 reader 线程炸
        _subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                        capture_output=True, timeout=15)
    except Exception:
        return {"stopped": False}
    append_log(_log_file(), f"comfy stop: killed pid={pid} listening on {host}:{port}")
    return {"stopped": True, "pid": pid}


def comfy_request_json(base, path, method="GET", payload=None, timeout=120):
    raw = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(base + path, data=raw, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        # 与 comfy_flow_service._request_json 同口径，复用同一份实现（不另抄一遍）：
        # ComfyUI 的 node_errors 在错误响应体里，丢掉就只剩「HTTP Error 400」。
        raise RuntimeError(comfy_flow_service._http_error_detail(exc)) from None
    except urllib.error.URLError as exc:
        # 连接失败（ComfyUI 未启动）：尝试自动拉起后再重试一次
        try:
            ensure_comfy_alive(base)
        except Exception as launch_err:
            raise RuntimeError(f"ComfyUI 连接失败且自动拉起未成功：{launch_err}") from None
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as he:
            raise RuntimeError(comfy_flow_service._http_error_detail(he)) from None
        except Exception as retry_err:
            raise RuntimeError(f"ComfyUI 已尝试拉起但连接仍失败：{retry_err}") from None
    return json.loads(body.decode("utf-8") or "{}")


def apply_comfy_workflow_fields(workflow, config, fields):
    result = json.loads(json.dumps(workflow if isinstance(workflow, dict) else {}))
    safe_config = config if isinstance(config, dict) else {}
    safe_fields = fields if isinstance(fields, dict) else {}
    applied_media = []
    for field in safe_config.get("fields") or []:
        if not isinstance(field, dict):
            continue
        node_id = str(field.get("node") or "").strip()
        input_key = str(field.get("input") or "").strip()
        if not node_id or not input_key or node_id not in result:
            continue
        supplied = field.get("id") in safe_fields
        value = safe_fields.get(field.get("id"), field.get("default"))
        field_type = str(field.get("type") or "").lower()
        field_id = field.get("id")
        if field_type in ("number", "slider"):
            try:
                value = float(value)
                if value.is_integer():
                    value = int(value)
            except Exception:
                pass
        elif field_type == "boolean":
            value = bool(value)
        result.setdefault(node_id, {}).setdefault("inputs", {})[input_key] = value
        if field_type in {"image", "video", "audio"}:
            applied_media.append({
                "id": str(field_id or ""),
                "type": field_type,
                "node": node_id,
                "input": input_key,
                "value": str(value or "")[:240],
                "supplied": supplied,
            })
    if applied_media:
        append_log(_log_file(), "comfy workflow media fields applied " + json.dumps(applied_media, ensure_ascii=False))
    return result


def _comfy_localized_name(output_dir, prompt_id, ext=".png", file_key=""):
    """ComfyUI 产物落盘名遵循画布「生成产物」规范（MM-DD-NN.<ext> 日期序号，与
    save_generated_remote_asset 同口径），不再用 comfy_<uuid>_<工作流原名> 这种难看且
    冗余的乱名。prompt_id 做稳定绑定：同一产物（recent/卡死恢复反复调用）落到同一文件；
    与手动产物（同为日期序号）重号时自动顺延，互不覆盖。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # 稳定映射落在画布目录级（output_dir 的父级），不放进 images/videos 素材目录，
    # 免得被导出或目录扫描当成素材。images/videos 共用同一份映射，key 是 prompt_id；
    # 命中时还会按当前 output_dir 再校验一次文件存在（图/视频各自目录互不干扰）。
    map_path = output_dir.parent / ".comfy_localized_map.json"
    pid = str(prompt_id or "").strip()
    # key 必须带上原始文件名：同一 prompt 可能一次吐多张图（batch / 多输出节点），
    # 只拿 prompt_id 当 key 会让第二张命中第一张的落盘名、把它覆盖掉。
    key = (pid + "|" + str(file_key or "").strip()).strip("|")
    with _COMFY_LOCALIZE_LOCK:
        mapping = {}
        if map_path.exists():
            try:
                mapping = json.loads(map_path.read_text(encoding="utf-8") or "{}")
            except Exception:
                mapping = {}
        if key and key in mapping:
            candidate = mapping[key]
            if (output_dir / candidate).exists():
                return candidate
        date_prefix = time.strftime("%m-%d")
        # 序号占用判断必须**递归含 history/ 子目录**（2026-10-06 修）：
        # 前端每次「覆盖重跑」都会调 /api/move-to-history 把上一张产物挪进 images/history/，
        # 于是 images/ 顶层就腾出空位。原来只 exists() 顶层 → 同一个 MM-DD-NN 被反复重新分配，
        # 新图覆盖旧图、history/ 里堆出一串 10-06-01_N 重名副本（实测已堆到 _12）。
        # 占用名缓存（2026-10-09）：冷启动/跨天时 rglob 全量建一次，之后增量维护；
        # 分配时对候选名再做「顶层 + history/ 各一次 exists()」兜底，双保险不重号。
        used_names = None
        cached = _COMFY_NAME_CACHE.get(str(output_dir))
        if isinstance(cached, dict) and cached.get("date") == date_prefix and isinstance(cached.get("used"), set):
            used_names = cached["used"]
        if used_names is None:
            used_names = set()
            try:
                for path in output_dir.rglob("*"):
                    if path.is_file():
                        used_names.add(path.name)
            except Exception:
                used_names = set()
            _COMFY_NAME_CACHE[str(output_dir)] = {"date": date_prefix, "used": used_names}
        counter = 1
        history_dir = output_dir / "history"
        while True:
            name = f"{date_prefix}-{counter:02d}{ext}"
            if name not in used_names:
                # 缓存外的兜底校验：缓存建立后外部新写入/归档移动的同名文件也算占位
                if not (output_dir / name).exists() and not (history_dir / name).exists():
                    break
                used_names.add(name)
            counter += 1
            if counter > 9999:
                name = f"{date_prefix}-{uuid.uuid4().hex[:6]}{ext}"
                break
        used_names.add(name)
        if key:
            mapping[key] = name
            try:
                map_path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
        return name


def comfy_output_asset_url(base, item, prompt_id, kind="image", canvas_title="", canvas_id=""):
    filename = str(item.get("filename") or "").strip()
    if not filename:
        return ""
    params = {
        "filename": filename,
        "type": str(item.get("type") or "output"),
        "subfolder": str(item.get("subfolder") or ""),
    }
    url = base + "/view?" + urllib.parse.urlencode(params)
    media_kind = str(kind or "image").strip().lower() or "image"
    canvas_folder = _r_canvas_output_folder_name(canvas_title, canvas_id) if canvas_title or canvas_id else ""
    output_dir = _r_asset_output_media_dir(media_kind, canvas_folder)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^0-9A-Za-z._-]+", "_", filename)
    # 画布「生成产物」规范命名：MM-DD-NN.<ext> 日期序号（与 save_generated_remote_asset
    # 同口径），不再用 comfy_<uuid>_<工作流原名> 这种难看且冗余的乱名。prompt_id 做稳定
    # 绑定保证同一产物多次调用（recent/卡死恢复）落到同一文件，与手动产物重号时自动顺延。
    ext = Path(safe_name).suffix.lower() or (".mp4" if media_kind == "video" else ".png")
    target = output_dir / _comfy_localized_name(output_dir, prompt_id, ext, file_key=safe_name)
    # 幂等短路（2026-10-01）：本函数被 recent-outputs 这类「只读查询」接口调用，而前端
    # 「卡死恢复」会在每次窗口 focus / 画布合并重载时调它一次——旧逻辑每调一次就把同一个
    # 文件从 ComfyUI /view 重新下载并覆盖写一遍，ComfyUI_temp_*.png 和几十 MB 的 mp4 被
    # 反复搬运进 assets/output。已落盘就直接复用本地文件（URL 与旧行为完全一致）。
    # 落盘必须原子（2026-10-01 补）：只用 exists() 短路的话，上一次下载中途被打断留下的
    # 半截文件会被永久当成完整文件复用（图片裂图、视频 0 字节）。改成先写 .part 临时文件、
    # 校验非空后 os.replace 原子改名；中断只会留下 .part，不会污染正式文件名。
    if not target.exists():
        tmp = target.with_name(target.name + ".part")
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                raw = response.read()
            if not raw:
                raise ValueError("ComfyUI /view 返回空内容")
            tmp.write_bytes(raw)
            os.replace(tmp, target)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
        if media_kind == "video":
            # 生成产物与上传素材同口径（2026-09-30）：VHS/ffmpeg 可能吐 HEVC 等内嵌
            # WebView2 解不动的编码，落盘后就地兜底转 H.264（文件名不变故 URL 不变）；
            # 保守原则同上传路径：只转明确不可播的，失败/无 ffmpeg 原样保留。
            try:
                import myridtv_video_codec
                myridtv_video_codec.ensure_playable_video(target)
            except Exception:
                pass
    return _r_asset_output_url(target.name, media_kind, canvas_folder=canvas_folder)


# 工作流卡片节点依赖的服务层：节点元数据缓存与异步任务队列。
# 宿主能力在这里注入，服务层不反向 import 本模块。


def select_comfy_output_nodes(history):
    outputs = history.get("outputs") if isinstance(history, dict) else {}
    if not isinstance(outputs, dict):
        return []
    image_nodes = []
    video_nodes = []
    for node_id, node_output in outputs.items():
        if not isinstance(node_output, dict):
            continue
        if node_output.get("images"):
            image_nodes.append((str(node_id), node_output))
        elif node_output.get("videos") or node_output.get("gifs") or node_output.get("video"):
            video_nodes.append((str(node_id), node_output))
    # 视频优先互斥（2026-10-01，与 comfy_flow_service._collect_outputs 同口径）：
    # 视频工作流常带 PreviewImage 过程预览节点（ComfyUI_temp_*.png）。旧逻辑 images
    # 优先且二选一——只要工作流有任何预览图，真正的视频产出就被整体忽略；recent-outputs
    # 的调用方（前端「卡死恢复 recoverStuckComfyNodes」按 prompt_id 认领）因此把 temp
    # 预览图反复回填节点，用户删掉后下一轮恢复又填回来。
    if video_nodes:
        return [video_nodes[-1]]
    if len(image_nodes) > 1:
        return [image_nodes[-1]]
    return image_nodes


def comfy_check_media_files(prompt, base=None):
    """提交前“死文件”体检：扫描最终 prompt 里的媒体加载节点，凡是引用文件在 ComfyUI 输入目录
    不存在的，直接抛出中文错误（指出节点号/标题/文件名），把 ComfyUI 的 'Invalid image file'
    黑话变成可行动提示。

    探测手段：对每个加载节点的文件名请求 ComfyUI ``/view?type=input``，404 即文件缺失。
    （这是导入工作流从别处带来“异地死文件名”的典型翻车点。）
    连接画布的素材已先上传到 ComfyUI，故不在本体检范围内；网络/非 404 错误一律放行，
    让 ComfyUI 自己的报错暴露，避免误拦截。
    """
    if not isinstance(prompt, dict) or not prompt:
        return
    if base is None:
        base = comfy_instance_base()
    missing = []
    checked = 0
    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        input_key = _COMFY_MEDIA_LOADERS.get(str(node.get("class_type") or ""))
        if not input_key:
            continue
        value = (node.get("inputs") or {}).get(input_key)
        if not isinstance(value, str) or not value.strip():
            continue
        checked += 1
        if checked > 40:
            break
        fn = value.strip()
        subfolder = str((node.get("inputs") or {}).get("subfolder") or "").strip().strip("/")
        url = base + "/view?" + urllib.parse.urlencode(
            {"filename": fn, "type": "input", "subfolder": subfolder})
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=5):
                pass
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                title = (node.get("_meta") or {}).get("title") or str(node.get("class_type") or "")
                missing.append((str(node_id), str(title), input_key, fn))
        except Exception:
            # 连不上 / 其它错误：放行，交给真实提交暴露。
            pass
    if missing:
        lines = "\n".join(
            "  · 节点「{}」({}) 的 {} = {}".format(t, nid, k, f)
            for (nid, t, k, f) in missing)
        raise ApiError(400,
            "提交失败：工作流里有 {} 个素材文件在 ComfyUI 输入目录中不存在"
            "（多半是工作流从别处导入、带的是“异地死文件名”）：\n{}\n"
            "请到该节点的「参数调整」面板把对应素材槽暴露出来并连上图片/音频，"
            "或在 ComfyUI 里放好这个文件后再跑。"
            "（已连到画布的素材会自动上传，无需处理）".format(len(missing), lines))


# —— 提示词槽位识别：让「画布上写的剧本」能进任何工作流 ——
# 收紧规则：排除预览/保存类节点、排除负面提示词，且只认字符串字面量（连线输入是 list）。
_PROMPT_EXCLUDE_CLASS = re.compile(
    r"preview|showtext|save_?text|save_?file|output|note|markdown|display|path|filename", re.I)
_PROMPT_CLASS = re.compile(
    r"cliptextencode|cr\s*prompt|primitivestring|stringmultiline|multiline|prompt|text", re.I)
_PROMPT_INPUT_KEY = re.compile(r"^(prompt|positive|text|value|string)$", re.I)
_NEGATIVE_HINT = re.compile(r"negative|负面|负向", re.I)


def _is_prompt_slot(class_type, node_title, input_key, value):
    """判断某个 (节点, 输入键) 是否是一条可用的「正向提示词」槽位。"""
    if not isinstance(value, str) or not str(value).strip():
        return False
    ct = str(class_type or "")
    title = str(node_title or "")
    key = str(input_key or "")
    if _PROMPT_EXCLUDE_CLASS.search(ct) or _NEGATIVE_HINT.search(title) or _NEGATIVE_HINT.search(key):
        return False
    if not (_PROMPT_CLASS.search(ct) or re.search(r"提示词|正向|剧本|文案", title)):
        return False
    return bool(_PROMPT_INPUT_KEY.match(key))


def auto_expose_workflow_fields(name):
    """导入/加载工作流时，把「必要槽位」自动暴露成 config 字段 —— 通用规则，不针对某个工作流。

    覆盖三类，缺一不可：
      1. 媒体槽（LoadImage/LoadAudio/LoadVideo 等）—— 没有槽位，画布的图/音频无处注入，
         ComfyUI 只能吃工作流里写死的文件名，表现为“用的不是画布素材”。
      2. 提示词槽（CR Prompt Text / CLIPTextEncode / PrimitiveStringMultiline 等）—— 没有槽位，
         画布上写的剧本台词根本进不去，每次跑的都是工作流里写死的提示词（2026-10-01 的真凶）。
      3. 失效清理：工作流改过之后，指向已不存在节点的 ``auto_`` 字段会被移除，
         否则槽位只增不减、面板越来越乱。手工字段（非 auto_ 前缀）一律不动。

    幂等：已暴露的 (node, input) 跳过；仅处理自定义（非内置）工作流。
    默认值一律取工作流里的当前原文 —— 不填就完全保持原行为，不会清空任何写死内容。
    """
    record = read_workflow_record(name)
    config = record.get("config") if isinstance(record.get("config"), dict) else {}
    if record.get("builtin"):
        return {"ok": True, "added": 0, "pruned": 0, "skipped": "builtin"}
    workflow = record.get("workflow") if isinstance(record.get("workflow"), dict) else {}
    fields = [f for f in (config.get("fields") or []) if isinstance(f, dict)]
    existing = {
        (str(f.get("node") or "").strip(), str(f.get("input") or "").strip())
        for f in fields
    }
    # 字段类型归一：mask/file/vector/glb 都按 image 媒体处理，audio/video 各归其位。
    type_for = {"image": "image", "mask": "image", "video": "video",
                "audio": "audio", "file": "image", "vector": "image", "glb": "image"}

    def _slot_kind(node_id, node):
        """返回该节点应暴露的槽位类型：('media'|'prompt', input_key) 或 None。"""
        if not isinstance(node, dict):
            return None
        class_type = str(node.get("class_type") or "")
        input_key = _COMFY_MEDIA_LOADERS.get(class_type)
        if input_key:
            return ("media", input_key)
        title = (node.get("_meta") or {}).get("title") or class_type
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        for key, value in inputs.items():
            if _is_prompt_slot(class_type, title, key, value):
                return ("prompt", str(key))
        return None

    # —— 1) 清理：只删 auto_ 前缀且节点/槽位已失效的字段（手工字段永不动） ——
    pruned = []
    kept = []
    for f in fields:
        nid = str(f.get("node") or "").strip()
        is_auto = str(f.get("id") or "").startswith("auto_")
        node = workflow.get(nid)
        if is_auto:
            kind = _slot_kind(nid, node)
            still_valid = bool(kind) and str(f.get("input") or "").strip() == kind[1]
            if nid not in workflow or not still_valid:
                pruned.append(str(f.get("id") or ""))
                existing.discard((nid, str(f.get("input") or "").strip()))
                continue
        kept.append(f)
    fields = kept

    # —— 2) 补充缺失槽位 ——
    added = []
    for node_id, node in workflow.items():
        kind = _slot_kind(node_id, node)
        if not kind:
            continue
        kind_name, input_key = kind
        key = (str(node_id).strip(), input_key)
        if key in existing:
            continue
        existing.add(key)
        title = (node.get("_meta") or {}).get("title") or str(node.get("class_type") or "")
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        if kind_name == "media":
            field = {
                "id": "auto_{}_{}".format(input_key, node_id),
                "node": str(node_id),
                "input": input_key,
                "name": str(title),
                "type": type_for.get(input_key, "image"),
                "options": [],
            }
        else:
            # 默认值取工作流当前原文：不填 = 完全保持写死行为，不会把提示词清成空。
            field = {
                "id": "auto_prompt_{}_{}".format(node_id, input_key),
                "node": str(node_id),
                "input": input_key,
                "name": str(title) or "提示词",
                "type": "textarea",
                "default": str(inputs.get(input_key) or ""),
                "options": [],
            }
        added.append(field)

    # 提示词槽放最前（前端把第一个 prompt 字段当作画布提示词的落点），媒体槽接在后面。
    if added:
        prompts = [f for f in added if f.get("type") == "textarea"]
        medias = [f for f in added if f.get("type") != "textarea"]
        # 长文本优先：正文剧本通常比“增强/模版”类短提示词长得多，
        # 前端把第一个 prompt 字段当作画布提示词的落点，顺序错了会把剧本塞错节点。
        prompts.sort(key=lambda f: len(str(f.get("default") or "")), reverse=True)
        # 同步回 added，保证返回值顺序与实际落盘顺序一致（面板与接口不会打架）。
        added = prompts + medias
        fields = prompts + fields + medias
    # 同名去重：多个节点 title 相同时加 #节点号，面板上才分得清哪个槽对应哪个节点。
    counts = {}
    for f in fields:
        counts[str(f.get("name") or "")] = counts.get(str(f.get("name") or ""), 0) + 1
    if any(v > 1 for v in counts.values()):
        seen = {}
        for f in fields:
            nm = str(f.get("name") or "")
            if counts.get(nm, 0) > 1:
                seen[nm] = seen.get(nm, 0) + 1
                f["name"] = "{} #{}".format(nm, str(f.get("node") or ""))
    if added or pruned:
        config["fields"] = fields
        if _r_save_workflow_config is not None:
            _r_save_workflow_config(name, config)
    return {
        "ok": True,
        "added": len(added),
        "pruned": len(pruned),
        "added_fields": added,
        "pruned_ids": pruned,
        "fields": fields,
    }


def auto_expose_media_fields(name):
    """旧入口：现为 :func:`auto_expose_workflow_fields` 的薄包装（媒体 + 提示词 + 清理）。"""
    return auto_expose_workflow_fields(name)


def build_comfy_workflow_prompt(name, payload):
    """按 payload 构造最终要提交给 ComfyUI 的 prompt（字段覆盖 / 节点开关编译都在这里）。"""
    record = _r_read_workflow_record(name)
    config = payload.get("config") if isinstance(payload.get("config"), dict) else record.get("config")
    modes = payload.get("modes") if isinstance(payload.get("modes"), dict) else None
    if modes:
        # 画布生成节点传来的节点开关（bypass / mute），交给编译器改写整张图。
        # 这一步是必需的：ComfyUI 的 /prompt 不认识 mode 字段，bypass 得自己算。
        # 先应用暴露字段（提示词/参数），再叠加节点开关，两者可同时生效。
        base_prompt = apply_comfy_workflow_fields(
            record.get("workflow") if isinstance(record.get("workflow"), dict) else {},
            config,
            payload.get("fields"),
        )
        if isinstance(payload.get("params"), dict) and payload.get("params"):
            base_prompt = json.loads(json.dumps(base_prompt or {}))
            for node_id, overrides in payload.get("params", {}).items():
                if not isinstance(overrides, dict) or str(node_id) not in base_prompt:
                    continue
                base_prompt[str(node_id)].setdefault("inputs", {}).update(overrides)
        prompt, _report = compile_comfy_prompt(
            base_prompt or {},
            {},
            modes,
            comfy_flow_service.load_object_info(),
        )
    elif isinstance(payload.get("params"), dict):
        # Canvas custom-Comfy calls already provide node/input overrides.
        # Keep this path local to Comfy workflow execution; legacy API modes
        # continue to use their existing compatibility handler.
        prompt = json.loads(json.dumps(record.get("workflow") if isinstance(record.get("workflow"), dict) else {}))
        for node_id, overrides in payload.get("params", {}).items():
            if not isinstance(overrides, dict) or str(node_id) not in prompt:
                continue
            prompt[str(node_id)].setdefault("inputs", {}).update(overrides)
    else:
        prompt = apply_comfy_workflow_fields(record.get("workflow"), config, payload.get("fields"))
    if not prompt:
        raise ApiError(400, "工作流为空")
    normalize_aspect_ratios(prompt, comfy_flow_service.load_object_info())
    # 提交前“死文件”体检：拦截导入工作流携带的异地死文件名，给出可行动的中文报错。
    comfy_check_media_files(prompt)
    return prompt


def submit_comfy_workflow_job(name, payload, prompt=None):
    """走全局 FIFO 队列提交一条工作流，立即返回 job（HTTP 不阻塞）。

    以前这里是直接 POST /prompt 再 while 轮询 /history，会把 HTTP 请求一直挂到
    工作流跑完（上限 3600 秒），而且绕开队列、可能和画布节点抢显存。
    """
    payload = payload if isinstance(payload, dict) else {}
    if prompt is None:
        prompt = build_comfy_workflow_prompt(name, payload)
    client_id = str(payload.get("client_id") or uuid.uuid4().hex)
    meta = {
        "source": "workflow_run",
        "workflow": str(name or ""),
        "canvas_id": str(payload.get("canvas_id") or "").strip(),
        "canvas_title": str(payload.get("canvas_title") or "").strip(),
    }
    job = comfy_flow_service.MANAGER.submit(str(name or ""), prompt, client_id, meta=meta)
    append_log(_log_file(), f"comfy workflow queued name={name} job_id={job.id} position={job.queue_position}")
    return job


def run_comfy_workflow(name, payload):
    """同步执行一条工作流：底层走统一 FIFO 队列，外层等结果。

    payload['async'] = True 时只入队并立即返回 job_id，HTTP 不再挂到跑完
    （设置页试跑走这条，免得一个请求卡一小时）。
    """
    payload = payload if isinstance(payload, dict) else {}
    prompt = build_comfy_workflow_prompt(name, payload)
    job = submit_comfy_workflow_job(name, payload, prompt=prompt)
    if payload.get("async") is True or payload.get("wait") is False:
        return {
            "ok": True,
            "async": True,
            "job_id": job.id,
            "status": job.status,
            "queue_position": job.queue_position,
        }
    finished = comfy_flow_service.MANAGER.wait(job.id, timeout=_POLL_TIMEOUT)
    if finished is None:
        raise ApiError(504, "任务记录已丢失，后端可能重启过")
    if finished.status == comfy_flow_service.STATUS_ERROR:
        raise ApiError(502, finished.error or "ComfyUI 执行失败")
    if finished.status == comfy_flow_service.STATUS_CANCELLED:
        raise ApiError(409, "任务已取消")
    if finished.status != comfy_flow_service.STATUS_DONE:
        elapsed = int(time.time() - (job.created_at or time.time()))
        append_log(_log_file(), f"comfy workflow timeout name={name} job_id={job.id} elapsed={elapsed}s")
        raise ApiError(504, f"ComfyUI 执行超时：已等待 {elapsed} 秒，工作流可能仍在后台运行。")
    append_log(_log_file(), f"comfy workflow succeeded name={name} prompt_id={finished.prompt_id} job_id={finished.id} images={len(finished.images)} videos={len(finished.videos)}")
    return {
        "ok": True,
        "prompt_id": finished.prompt_id,
        "images": finished.images,
        "videos": finished.videos,
        "job_id": finished.id,
    }


def recent_comfy_outputs(payload=None):
    payload = payload if isinstance(payload, dict) else {}
    limit = max(1, min(20, int(payload.get("limit") or 6)))
    base = comfy_instance_base()
    history_all = comfy_request_json(base, "/history", "GET", timeout=30)
    # 只归档 MyridTV 自己提交的任务：外部（含 ComfyUI 网页手动跑）的 prompt 不落盘，
    # 防止窗口 focus 时把别人的图拷进 assets/output/images/history。
    known_jobs = {}
    try:
        for job in comfy_flow_service.MANAGER.list_jobs(limit=100):
            pid = str(job.get("prompt_id") or "").strip()
            if pid:
                known_jobs[pid] = job
    except Exception:
        pass
    rows = []
    if isinstance(history_all, dict):
        for prompt_id, history in history_all.items():
            if str(prompt_id) not in known_jobs:
                continue
            job = known_jobs[str(prompt_id)]
            meta = job.get("meta") if isinstance(job.get("meta"), dict) else {}
            canvas_title = str(meta.get("canvas_title") or "").strip()
            canvas_id = str(meta.get("canvas_id") or "").strip()
            if not isinstance(history, dict):
                continue
            # 官方 task_done 成功/失败都落 history：失败任务的 outputs 里照样躺着前面
            # 节点出的预览图。不过滤的话，卡死恢复会把它们当产物回填进画布（"假成功"）。
            if comfy_flow_service.history_failure_reason(history):
                continue
            order = 0
            prompt_info = history.get("prompt")
            if isinstance(prompt_info, list) and prompt_info:
                try:
                    order = int(prompt_info[0])
                except Exception:
                    order = 0
            images = []
            videos = []
            for _node_id, node_output in select_comfy_output_nodes(history):
                if not isinstance(node_output, dict):
                    continue
                for item in node_output.get("images") or []:
                    url = comfy_output_asset_url(base, item, str(prompt_id), "image", canvas_title=canvas_title, canvas_id=canvas_id)
                    if url and url not in images:
                        images.append(url)
                for item in (node_output.get("videos") or []) + (node_output.get("gifs") or []):
                    url = comfy_output_asset_url(base, item, str(prompt_id), "video", canvas_title=canvas_title, canvas_id=canvas_id)
                    if url and url not in videos:
                        videos.append(url)
            # 视频优先互斥（与 comfy_flow_service._collect_outputs 同口径）：视频工作流
            # 常带 PreviewImage 过程预览图（ComfyUI_temp_*.png），若不互斥，前端
            # 「卡死恢复 recoverStuckComfyNodes」会按 images 优先把 temp 预览图当产出
            # 回填节点、视频被无视，且用户删掉后下一轮恢复又填回来。
            if videos:
                images = []
            if images or videos:
                rows.append({"prompt_id": str(prompt_id), "order": order, "images": images, "videos": videos})
    rows.sort(key=lambda item: int(item.get("order") or 0), reverse=True)
    return {"ok": True, "outputs": rows[:limit]}


def comfy_workflow_split_clusters(workflow):
    """多管线集合检测：按输出节点沿上游回溯聚簇。

    返回 (clusters, dropped)：
    - clusters: [{"nodes": {id: node}, "save_id": 输出节点id}, ...]，按簇规模降序
    - dropped: 未归属任何簇的节点 id 集合（悬空预览、未连线节点、多余原图 SaveImage）
    只有聚出 >=2 个互不重叠的簇才视为集合；单输出或交叠图（同一链上双 SaveImage）返回 ([], set())。
    """
    if not isinstance(workflow, dict) or not workflow:
        return [], set()

    def upstream(nid):
        seen = set()
        stack = [nid]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            node = workflow.get(cur)
            if not isinstance(node, dict):
                continue
            for value in (node.get("inputs") or {}).values():
                if isinstance(value, list) and len(value) == 2 and str(value[0]) in workflow:
                    stack.append(str(value[0]))
        return seen

    save_ids = [str(nid) for nid, node in workflow.items()
                if isinstance(node, dict) and str(node.get("class_type") or "").lower() in ("saveimage", "vhs_videocombine")]
    if len(save_ids) < 2:
        return [], set()
    clusters = []
    claimed = set()
    for sid in sorted(save_ids, key=lambda x: -len(upstream(x))):
        nodes = upstream(sid)
        if not nodes or (nodes & claimed):
            continue  # 与更大簇共享节点（同一链上的双 SaveImage）→ 不独立成簇
        claimed |= nodes
        clusters.append({"nodes": {nid: workflow[nid] for nid in nodes}, "save_id": sid})
    if len(clusters) < 2:
        return [], set()
    clusters.sort(key=lambda c: -len(c["nodes"]))
    dropped = {str(nid) for nid in workflow if nid not in claimed}
    return clusters, dropped


