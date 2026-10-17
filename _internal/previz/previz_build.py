# -*- coding: utf-8 -*-
"""
镜头预演拼接器（ffmpeg 端）
================================
读取 previz_render.py 直接输出的镜头 MP4 + manifest.json，
镜头间插入黑场后拼接成一个总预演视频。兼容旧 PNG 帧序列输入。

用法:
  python previz_build.py --input 输出目录 --output final.mp4
"""
import argparse
import json
import os
import subprocess
import sys

FFMPEG = "ffmpeg"
FONT_CN = r"C:\Windows\Fonts\simhei.ttf"
FONT_EN = r"C:\Windows\Fonts\arialbd.ttf"


def find_ffmpeg():
    for name in ("ffmpeg", r"C:\ffmpeg\bin\ffmpeg.exe"):
        try:
            r = subprocess.run([name, "-version"], capture_output=True, timeout=10)
            if r.returncode == 0:
                return name
        except Exception:
            continue
    return None


def esc(s):
    # drawtext 文本转义: 冒号/反斜杠/单引号/百分号
    s = s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "").replace("%", "\\%")
    return s


def ffpath(p):
    # fontfile 路径: 正斜杠 + 转义冒号（ffmpeg filter 语法）
    return p.replace("\\", "/").replace(":", "\\:")


def run(cmd):
    print("  $", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        sys.exit("ffmpeg 失败: " + " ".join(cmd[:6]) + " ...")
    return r


def build(input_dir, output_path):
    manifest_path = os.path.join(input_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        sys.exit("找不到 %s，请先运行 previz_render.py" % manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        sys.exit("未找到 ffmpeg，请安装并加入 PATH")
    font_cn = FONT_CN if os.path.exists(FONT_CN) else None
    font_en = FONT_EN if os.path.exists(FONT_EN) else None

    fps = manifest["fps"]
    w, h = manifest["分辨率"]
    black_sec = 0.4

    tmp = os.path.join(input_dir, "_tmp")
    os.makedirs(tmp, exist_ok=True)

    parts = []          # concat 用文件列表
    concat_lines = []
    for i, shot in enumerate(manifest["镜头"]):
        sid = shot["镜号"]
        # Blender now provides an MP4 directly.  Preserve legacy PNG support
        # for old retained runs, but never make PNGs in the new path.
        source_video = str(shot.get("视频") or "")
        if source_video and os.path.exists(source_video):
            shot_mp4 = source_video
        else:
            frames = os.path.join(input_dir, sid)
            if not os.path.exists(frames):
                print("跳过缺失镜头视频/目录:", sid)
                continue
            shot_mp4 = os.path.join(tmp, "%s.mp4" % sid)
            cmd = [ffmpeg, "-y", "-framerate", str(fps), "-i",
                   os.path.join(frames, "f%04d.png")]
            if shot.get("start_frame", 1) != 1:
                cmd = [ffmpeg, "-y", "-framerate", str(fps), "-start_number", str(shot.get("start_frame", 1)),
                       "-i", os.path.join(frames, "f%04d.png")]
            cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-pix_fmt", "yuv420p", "-r", str(fps), shot_mp4]
            run(cmd)
        parts.append(shot_mp4)
        concat_lines.append("file '%s'" % shot_mp4.replace("\\", "/"))

        # 镜头间黑场（最后一段之后不加）
        if i < len(manifest["镜头"]) - 1:
            black_mp4 = os.path.join(tmp, "black_%d.mp4" % i)
            run([ffmpeg, "-y", "-f", "lavfi", "-i",
                 "color=c=black:s=%dx%d:r=%d:d=%.2f" % (w, h, fps, black_sec),
                 "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                 "-pix_fmt", "yuv420p", "-r", str(fps), black_mp4])
            parts.append(black_mp4)
            concat_lines.append("file '%s'" % black_mp4.replace("\\", "/"))

    if not parts:
        sys.exit("没有可拼接的镜头")

    list_file = os.path.join(tmp, "concat.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        f.write("\n".join(concat_lines))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", list_file,
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", output_path])
    print("[previz] 完成 -> %s （%d 个镜头，总时长约 %.1fs）" % (output_path, len(parts), sum(m["时长秒"] for m in manifest["镜头"])))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="previz_render.py 的输出目录")
    ap.add_argument("--output", required=True, help="最终 mp4 路径")
    a = ap.parse_args()
    build(a.input, a.output)
