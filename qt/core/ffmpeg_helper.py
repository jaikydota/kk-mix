"""FFmpeg 路径查找与编码参数构造。"""
from __future__ import annotations

import os
import sys
import subprocess


def find_ffmpeg() -> str | None:
    """沿用 kk.py 中的查找顺序。"""
    if getattr(sys, "frozen", False):
        bundled = os.path.join(sys._MEIPASS, "ffmpeg.exe")  # type: ignore[attr-defined]
        if os.path.exists(bundled):
            return bundled
        exe_dir = os.path.dirname(sys.executable)
        local = os.path.join(exe_dir, "ffmpeg.exe")
        if os.path.exists(local):
            return local

    for cmd in ("ffmpeg", "ffmpeg.exe"):
        try:
            subprocess.run([cmd, "-version"], capture_output=True, check=True)
            return cmd
        except Exception:
            pass

    for path in (
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"D:\ffmpeg\bin\ffmpeg.exe",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ffmpeg.exe"),
    ):
        path = os.path.abspath(path)
        if os.path.exists(path):
            return path
    return None


def find_ffprobe() -> str | None:
    """ffprobe 查找，和 ffmpeg 同目录优先。"""
    if getattr(sys, "frozen", False):
        bundled = os.path.join(sys._MEIPASS, "ffprobe.exe")  # type: ignore[attr-defined]
        if os.path.exists(bundled):
            return bundled
        exe_dir = os.path.dirname(sys.executable)
        local = os.path.join(exe_dir, "ffprobe.exe")
        if os.path.exists(local):
            return local

    for cmd in ("ffprobe", "ffprobe.exe"):
        try:
            subprocess.run([cmd, "-version"], capture_output=True, check=True)
            return cmd
        except Exception:
            pass
    return None


def ffprobe_for(ffmpeg_path: str) -> str:
    """由 ffmpeg 路径推导同目录的 ffprobe。

    不能用 path.replace("ffmpeg", "ffprobe")：当项目本身位于含 "ffmpeg" 的目录
    （如 D:\\ffmpeg\\kk-mix\\）时会把目录名一起改坏。
    """
    if not ffmpeg_path:
        return find_ffprobe() or ""
    folder, name = os.path.split(ffmpeg_path)
    probe_name = "ffprobe.exe" if name.lower().endswith(".exe") else "ffprobe"
    if not folder:                       # PATH 中的裸命令
        return probe_name
    candidate = os.path.join(folder, probe_name)
    if os.path.exists(candidate):
        return candidate
    return find_ffprobe() or candidate


def _make_si():
    if sys.platform != "win32":
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return si


def probe_resolution_fps(ffmpeg_path: str, video_path: str) -> tuple[int, int, float]:
    """对应 kk.py 的 get_video_resolution_fps：单次 ffprobe 拿分辨率和帧率。

    返回 (width, height, fps)；失败时返回 (1920, 1080, 25.0)。
    """
    import re

    ffprobe_path = ffprobe_for(ffmpeg_path)
    if ffprobe_path:
        try:
            cmd = [
                ffprobe_path, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,avg_frame_rate",
                "-of", "default=noprint_wrappers=1:nokey=1", video_path,
            ]
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                startupinfo=_make_si(), encoding="utf-8", errors="ignore",
            )
            if r.returncode == 0:
                lines = [l.strip() for l in r.stdout.strip().splitlines() if l.strip()]
                if len(lines) >= 3:
                    w, h = int(lines[0]), int(lines[1])
                    fps_str = lines[2]
                    if "/" in fps_str:
                        num, den = fps_str.split("/")
                        fps = round(int(num) / int(den), 6) if int(den) else 25.0
                    else:
                        fps = float(fps_str) if fps_str else 25.0
                    return w, h, fps
        except Exception:
            pass

    try:
        cmd = [ffmpeg_path, "-i", video_path, "-f", "null", "-"]
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            startupinfo=_make_si(), encoding="utf-8", errors="ignore",
        )
        w, h, fps = 1920, 1080, 25.0
        for line in r.stderr.split("\n"):
            if "Stream #0:0" in line and "Video:" in line:
                m = re.search(r"(\d{2,5})x(\d{2,5})", line)
                if m:
                    w, h = int(m.group(1)), int(m.group(2))
                m = re.search(r"([\d.]+)\s*(?:fps|tbr)", line)
                if m:
                    fps = float(m.group(1))
                break
        return w, h, fps
    except Exception:
        return 1920, 1080, 25.0


def probe_video_info(ffmpeg_path: str, video_path: str) -> tuple[int, int, float, bool]:
    """返回 (width, height, fps, has_audio)；失败时保守返回 (1920, 1080, 25.0, True)。

    对应 kk.py 的 _get_video_info。
    """
    import json

    ffprobe_path = ffprobe_for(ffmpeg_path)
    if ffprobe_path:
        try:
            cmd = [
                ffprobe_path, "-v", "error", "-show_streams",
                "-show_entries", "stream=codec_type,width,height,avg_frame_rate",
                "-of", "json", video_path,
            ]
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                startupinfo=_make_si(), encoding="utf-8", errors="ignore",
            )
            if r.returncode == 0 and r.stdout.strip():
                streams = json.loads(r.stdout).get("streams", [])
                w, h, fps, has_audio = 1920, 1080, 25.0, False
                got_video = False
                for s in streams:
                    ctype = s.get("codec_type", "")
                    if ctype == "video" and not got_video:
                        w = s.get("width", 1920)
                        h = s.get("height", 1080)
                        fps_str = s.get("avg_frame_rate", "25/1")
                        if "/" in fps_str:
                            num, den = fps_str.split("/")
                            fps = round(int(num) / int(den), 6) if int(den) else 25.0
                        else:
                            fps = float(fps_str) if fps_str else 25.0
                        got_video = True
                    elif ctype == "audio":
                        has_audio = True
                return w, h, fps, has_audio
        except Exception:
            pass

    w, h, fps = probe_resolution_fps(ffmpeg_path, video_path)
    return w, h, fps, True


def probe_duration(ffmpeg_path: str, video_path: str) -> float:
    """用 ffprobe 获取视频时长（秒）；失败返回 0.0。"""
    ffprobe_path = ffprobe_for(ffmpeg_path)
    if not ffprobe_path:
        return 0.0
    try:
        cmd = [
            ffprobe_path, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            startupinfo=_make_si(), encoding="utf-8", errors="ignore",
        )
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.strip())
    except Exception:
        pass
    return 0.0


def encode_preset(speed_priority: bool) -> str:
    """极速模式返回 ultrafast，否则 medium（对应 kk.py 的 _preset）。"""
    return "ultrafast" if speed_priority else "medium"


def quality_args(compress_video: bool, bitrate: str) -> list[str]:
    """码率控制：开启压缩返回 -b:v <bitrate>，否则 -crf 23（对应 kk.py 的 _quality_args）。"""
    if compress_video:
        return ["-b:v", bitrate]
    return ["-crf", "23"]
