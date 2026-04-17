"""画中画合成。对应 kk.py 中的 create_pip_tab / batch_pip_operation / _pip_ffmpeg。"""
from __future__ import annotations

import os
from pathlib import Path

from qfluentwidgets import ComboBox, DoubleSpinBox, FluentIcon, LineEdit

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.ffmpeg_helper import probe_resolution_fps
from qt.core.paths import ALL_MEDIA_EXTS, ensure_dir, list_media

from .base import BaseTab


_POSITION_OPTIONS = [
    ("top_left", "左上"),
    ("top_right", "右上"),
    ("bottom_left", "左下"),
    ("bottom_right", "右下"),
]


class PipWorker(BatchWorker):
    def __init__(self, ffmpeg_path, ctrl: BatchControl, settings: AppSettings,
                 bg_folder: str, fg_folder: str, output: str,
                 position: str, scale: float):
        super().__init__(ffmpeg_path, ctrl, settings)
        self.bg_folder = bg_folder
        self.fg_folder = fg_folder
        self.output = output
        self.position = position
        self.scale = scale

    def run_batch(self) -> tuple[bool, str]:
        ensure_dir(self.output)
        bg_files = list_media(self.bg_folder, ALL_MEDIA_EXTS)
        fg_files = list_media(self.fg_folder, ALL_MEDIA_EXTS)
        if not bg_files or not fg_files:
            self.log("✗ 有文件夹中没有找到媒体文件")
            return False, "媒体文件不足"

        n = min(len(bg_files), len(fg_files))
        bar = "=" * 60
        self.log(f"\n{bar}\n开始批量画中画合成   视频对数: {n}   位置: {self.position}   缩放: {self.scale}\n{bar}")

        success = 0
        for i in range(n):
            if self.ctrl.wait_if_paused():
                self.log("已手动停止"); break

            bg_path = os.path.join(self.bg_folder, bg_files[i])
            fg_path = os.path.join(self.fg_folder, fg_files[i])
            out_name = f"pip_{i+1:03d}_{Path(bg_files[i]).stem}.mp4"
            out_path = os.path.join(self.output, out_name)

            self.log(f"\n[{i+1}/{n}] 处理: {bg_files[i]} + {fg_files[i]}")
            if self._pip_ffmpeg(bg_path, fg_path, out_path):
                success += 1
                size_mb = os.path.getsize(out_path) / 1024 / 1024
                self.log(f"  ✓ 成功: {out_name} ({size_mb:.1f} MB)")
            else:
                self.log(f"  ✗ 失败")

            self.set_progress((i + 1) / n * 100)
            self.set_status(f"画中画合成中 {i+1}/{n}")

        self.log(f"\n{bar}\n完成！成功生成 {success}/{n} 个视频\n{bar}")
        return success > 0, f"成功 {success}/{n}"

    def _pip_ffmpeg(self, bg_path: str, fg_path: str, out_path: str) -> bool:
        try:
            bg_w, bg_h, _ = probe_resolution_fps(self.ffmpeg_path, bg_path)
            fg_w = int(bg_w * self.scale)
            fg_h = int(bg_h * self.scale)

            margin = int(bg_w * 0.02)
            if self.position == "top_left":
                x, y = margin, margin
            elif self.position == "top_right":
                x, y = bg_w - fg_w - margin, margin
            elif self.position == "bottom_left":
                x, y = margin, bg_h - fg_h - margin
            else:  # bottom_right
                x, y = bg_w - fg_w - margin, bg_h - fg_h - margin

            filter_complex = (
                f"[1:v]scale={fg_w}:{fg_h}[fg];"
                f"[0:v][fg]overlay=x={x}:y={y}[v]"
            )

            cmd = [
                self.ffmpeg_path,
                "-i", bg_path,
                "-i", fg_path,
                "-filter_complex", filter_complex,
                "-map", "[v]",
                "-map", "0:a",
                "-c:v", "libx264",
                "-preset", self.preset(),
                *self.quality_args(),
                "-c:a", "copy",
                "-threads", "0",
                "-y",
                out_path,
            ]

            r = self.run_cmd(cmd, timeout=600)
            if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return True
            tail = (r.stderr or "")[-400:]
            if tail:
                self.log(f"    stderr: {tail.strip()}")
            return False
        except Exception as e:
            self.log(f"  ✗ 异常: {e}")
            return False


class PipTab(BaseTab):
    NAME = "pip"
    TITLE = "画中画合成"
    ICON = FluentIcon.VIEW

    def build_form(self):
        self.bg_folder = LineEdit(self)
        self._add_folder_row(0, "背景视频文件夹", self.bg_folder)

        self.fg_folder = LineEdit(self)
        self._add_folder_row(1, "前景视频/图片文件夹", self.fg_folder)

        self.output = LineEdit(self)
        self.output.setText(
            os.path.join(os.path.expanduser("~"), "Desktop", "视频输出")
        )
        self._add_folder_row(2, "输出文件夹", self.output, is_output=True)

        self.position = ComboBox(self)
        self._position_values = [v for v, _ in _POSITION_OPTIONS]
        for v, label in _POSITION_OPTIONS:
            self.position.addItem(f"{label}  ({v})")
        self._add_param_row(3, "位置", self.position)

        self.scale = DoubleSpinBox(self)
        self.scale.setRange(0.1, 1.0); self.scale.setValue(0.3)
        self.scale.setSingleStep(0.05); self.scale.setDecimals(2)
        self._add_param_row(4, "缩放比例", self.scale, hint="相对背景视频的比例 0.1 - 1.0")

    def build_worker(self):
        bg = self.bg_folder.text().strip()
        fg = self.fg_folder.text().strip()
        out = self.output.text().strip()
        position = self._position_values[self.position.currentIndex()]
        scale = self.scale.value()

        if not self._require_folder(bg, "背景视频文件夹") \
           or not self._require_folder(fg, "前景文件夹") \
           or not self._require_folder(out, "输出文件夹") \
           or not self._require_dir_exists(bg, "背景视频文件夹") \
           or not self._require_dir_exists(fg, "前景文件夹"):
            return None

        return PipWorker(
            self.main.ffmpeg_path, self.main.ctrl, self.main.settings,
            bg, fg, out, position, scale,
        )
