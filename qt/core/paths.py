"""路径 / 常量 / 小工具。"""
from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path


VERSION = "v10.3.0"
APP_NAME = "中巨量 - 巨量剪辑"   # 显示时 tr(APP_NAME)，勿直接拼接

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
AUDIO_EXTS = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".wma", ".m4a"}
ALL_MEDIA_EXTS = VIDEO_EXTS | IMAGE_EXTS


def resource_path(relative_path: str) -> str:
    """兼容 PyInstaller 打包路径；开发环境返回项目根目录下的路径。"""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, relative_path)


def settings_path() -> Path:
    """settings.json 与 kk.exe / kk_qt.py 同级目录。"""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(sys.argv[0]).resolve().parent
    return base / "settings.json"


def make_startupinfo():
    """Windows 下隐藏子进程黑窗。"""
    if sys.platform != "win32":
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return si


def list_media(folder: str, exts: set[str] = VIDEO_EXTS) -> list[str]:
    """列出指定文件夹下所有匹配扩展名的文件（排序后）。"""
    if not folder or not os.path.isdir(folder):
        return []
    return sorted(
        f for f in os.listdir(folder) if Path(f).suffix.lower() in exts
    )


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)
