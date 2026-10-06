# -*- coding: utf-8 -*-
"""视频编码探测与转码域：上传落盘前探测视频实际编码，遇到 WebView2/Edge 内核解不了的
编码（典型如 HEVC/H.265）就用 ffmpeg 就地转成 H.264，保证导入的素材一定能出画面。

背景：MyridTV 前端跑在 WebView2（Edge 154）上，其 HEVC 解码依赖系统是否安装微软
「HEVC 视频扩展」。未安装时 `<video>` 能解出 duration 与音轨、play() 也不报错，但
videoWidth/videoHeight 恒为 0 —— 表现就是"素材在、画面全黑"。本机实测
（outputs/_verify_transcoded.py，msedge.exe 内核）：HEVC 原文件 0x0，转 H.264 后
1600x928 正常出画面，15 秒视频转码耗时 1.28s。

设计原则（保守，宁可不转也不错转）：
- 只在**明确判定不可播**时才转码；探测不出/未知编码一律放行，绝不误伤素材。
- 转码失败、超时、ffmpeg 缺失时**原样保留原文件**，只写日志，不让素材丢失。
- 转码先写临时文件、校验非空后才原子替换，中途崩溃不会留下半个文件。

configure(getters) 注入：LOG_FILE getter（值型全局走 getter，与主文件零重绑）。
"""
import os
import shutil
import struct
import subprocess
import tempfile
import time
from pathlib import Path

_G_LOG_FILE = lambda: None

# 明确可播（WebView2/Edge 原生支持，无需系统扩展）
PLAYABLE_FORMATS = {
    "avc1": "h264", "avc3": "h264", "avc4": "h264",
    "vp08": "vp8", "vp09": "vp9",
    "av01": "av1",
    "theora": "theora",
}
# 明确不可播 / 需系统付费扩展（探测到这些才转码）
UNPLAYABLE_FORMATS = {
    "hvc1": "hevc", "hev1": "hevc", "hvc2": "hevc",
    "mp4v": "mpeg4-part2",
    "apcn": "prores", "apch": "prores", "apcs": "prores", "apco": "prores",
    "ap4h": "prores", "ap4n": "prores",
    "avdh": "dnxhr", "avdn": "dnxhd",
    "r210": "raw", "v210": "raw", "v308": "raw", "yuv2": "raw",
}

# 探测时最多读取的头部/尾部字节（moov 可能在文件末尾）
_PROBE_HEAD_BYTES = 8 * 1024 * 1024
_PROBE_TAIL_BYTES = 8 * 1024 * 1024
# 转码超时（秒）：超时则放弃转码，保留原文件
_TRANSCODE_TIMEOUT = 300


def configure(getters):
    global _G_LOG_FILE
    _G_LOG_FILE = getters.get("LOG_FILE") or (lambda: None)


def _log(msg):
    try:
        from myridtv_core import append_log
        append_log(_G_LOG_FILE(), msg)
    except Exception:
        pass


def bundled_ffmpeg_path():
    """随包内置的 ffmpeg（可选）。放在 _internal/bin/ffmpeg.exe 即自动生效
    （installer/MyridTV.iss 是整目录递归打包，放进去就会进安装包）。"""
    try:
        here = Path(__file__).resolve().parent
        for rel in ("bin/ffmpeg.exe", "ffmpeg.exe", "_internal/bin/ffmpeg.exe"):
            p = here / rel
            if p.exists():
                return str(p)
    except Exception:
        pass
    return ""


def ffmpeg_path():
    """查找可用 ffmpeg：系统 PATH 优先，其次随包内置，都没有返回空串。"""
    found = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if found:
        return found
    return bundled_ffmpeg_path()


def _read_probe_window(path):
    """读头部 + 尾部（moov 常在末尾），拼成一块用于搜索 stsd。"""
    size = os.path.getsize(path)
    out = b""
    with open(path, "rb") as f:
        out += f.read(min(size, _PROBE_HEAD_BYTES))
        if size > _PROBE_HEAD_BYTES:
            f.seek(max(0, size - _PROBE_TAIL_BYTES))
            out += f.read()
    return out


def probe_video_codec(path):
    """探测视频轨编码，返回 (fourcc, family)。探测不出返回 ("", "unknown")。

    只解析 ISO BMFF（mp4/mov/m4v）的 stsd sample entry：定位 'stsd' 后按
    size(4)+version/flags(4)+entry_count(4)+[entry_size(4)+format(4)] 读取。
    不递归 box 树，够用且对 moov 在头/尾两种情况都成立。
    """
    try:
        blob = _read_probe_window(path)
    except Exception as exc:
        _log(f"video codec probe read failed: {exc}")
        return "", "unknown"
    pos = blob.find(b"stsd")
    if pos < 0:
        return "", "unknown"
    base = pos + 4 + 4  # 跳过 'stsd' + version/flags
    if base + 4 > len(blob):
        return "", "unknown"
    try:
        count = struct.unpack(">I", blob[base:base + 4])[0]
    except Exception:
        return "", "unknown"
    cursor = base + 4
    for _ in range(max(1, min(int(count), 8))):
        if cursor + 8 > len(blob):
            break
        fmt = blob[cursor + 4:cursor + 8]
        try:
            fourcc = fmt.decode("latin-1")
        except Exception:
            break
        if fourcc in PLAYABLE_FORMATS:
            return fourcc, PLAYABLE_FORMATS[fourcc]
        if fourcc in UNPLAYABLE_FORMATS:
            return fourcc, UNPLAYABLE_FORMATS[fourcc]
        # 未知格式：尝试下一个 entry
        try:
            entry_size = struct.unpack(">I", blob[cursor:cursor + 4])[0]
        except Exception:
            break
        if entry_size < 8:
            break
        cursor += entry_size
    return "", "unknown"


def needs_transcode(path):
    """是否必须转码才能在 WebView2 里出画面。未知编码一律 False（保守放行）。"""
    fourcc, family = probe_video_codec(path)
    if not fourcc:
        return False, fourcc, family
    return (fourcc in UNPLAYABLE_FORMATS), fourcc, family


def transcode_to_h264(src_path, dst_path):
    """用 ffmpeg 转成 H.264/AAC + faststart。返回 (ok, 备注)。"""
    exe = ffmpeg_path()
    if not exe:
        return False, "ffmpeg not found"
    cmd = [
        exe, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src_path),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(dst_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=_TRANSCODE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, f"transcode timeout >{_TRANSCODE_TIMEOUT}s"
    except Exception as exc:
        return False, f"transcode exec error: {exc}"
    if proc.returncode != 0:
        tail = (proc.stderr or b"").decode("utf-8", "replace")[-300:]
        return False, f"ffmpeg rc={proc.returncode}: {tail}"
    try:
        if os.path.getsize(dst_path) <= 0:
            return False, "transcode produced empty file"
    except Exception:
        return False, "transcode output missing"
    return True, "ok"


def ensure_playable_video(path):
    """主入口：就地确保视频可被 WebView2 播放。

    探测 → 不可播则用 ffmpeg 转 H.264 → 写临时文件 → 校验后原子替换。
    任何一步失败都保留原文件并返回原因，绝不删除/损坏原始素材。
    返回 (最终路径, 是否转码过, 备注)。
    """
    try:
        needed, fourcc, family = needs_transcode(path)
    except Exception as exc:
        return path, False, f"probe error({exc})"
    if not needed:
        if fourcc:
            _log(f"video codec ok: {fourcc}({family}) keep as-is: {os.path.basename(str(path))}")
        return path, False, "ok"

    src = Path(str(path))
    if not src.exists():
        return path, False, "source missing"
    t0 = time.time()
    tmp_dir = str(src.parent)
    fd, tmp_path = tempfile.mkstemp(prefix=".tr_", suffix=src.suffix or ".mp4", dir=tmp_dir)
    os.close(fd)
    try:
        ok, note = transcode_to_h264(str(src), tmp_path)
        if not ok:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            _log(f"video transcode skipped ({fourcc}/{family}) {src.name}: {note}")
            return path, False, note
        before = src.stat().st_size
        after = os.path.getsize(tmp_path)
        os.replace(tmp_path, str(src))
        cost = time.time() - t0
        _log(f"video transcode done: {src.name} {fourcc}({family}) -> h264 "
             f"{before}->{after} bytes in {cost:.2f}s")
        return str(src), True, f"{family}->h264 {before}->{after}B {cost:.2f}s"
    except Exception as exc:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        _log(f"video transcode failed {src.name}: {exc}")
        return path, False, f"transcode error: {exc}"
