"""批量旋转/翻转。对应 kk.py 中的 create_rotate_tab / batch_rotate_operation / _rotate_video_ffmpeg。"""
from __future__ import annotations

import os
from pathlib import Path

from qfluentwidgets import ComboBox, FluentIcon, LineEdit

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.paths import ensure_dir, list_media, VIDEO_EXTS

from .base import BaseTab


_ANGLE_OPTIONS = [
    ("90", "90° 顺时针"),
    ("180", "180°"),
    ("270", "90° 逆时针"),
    ("hflip", "水平翻转"),
    ("vflip", "垂直翻转"),
]

_VF_BY_ANGLE = {
    "90": "transpose=1",
    "180": "rotate=PI",
    "270": "transpose=2",
    "hflip": "hflip",
    "vflip": "vflip",
}


class RotateWorker(BatchWorker):
    def __init__(self, ffmpeg_path, ctrl: BatchControl, settings: AppSettings,
                 folder: str, output_folder: str, angle: str):
        super().__init__(ffmpeg_path, ctrl, settings)
        self.folder = folder
        self.output_folder = output_folder
        self.angle = angle

    def run_batch(self) -> tuple[bool, str]:
        ensure_dir(self.output_folder)
        files = list_media(self.folder, VIDEO_EXTS)
        if not files:
            self.log("✗ 文件夹中没有视频文件")
            return False, "无视频文件"

        bar = "=" * 60
        self.log(f"\n{bar}\n开始批量旋转/翻转   视频数: {len(files)}   操作: {self.angle}\n{bar}")

        success = 0
        for idx, name in enumerate(files, 1):
            if self.ctrl.wait_if_paused():
                self.log("已手动停止"); break

            in_path = os.path.join(self.folder, name)
            out_name = f"rotate_{idx:03d}_{self.angle}_{Path(name).stem}.mp4"
            out_path = os.path.join(self.output_folder, out_name)

            self.log(f"\n[{idx}/{len(files)}] 处理: {name}")
            if self._rotate_ffmpeg(in_path, out_path):
                success += 1
                size_mb = os.path.getsize(out_path) / 1024 / 1024
                self.log(f"  ✓ 成功: {out_name} ({size_mb:.1f} MB)")
            else:
                self.log(f"  ✗ 失败: {name}")

            self.set_progress(idx / len(files) * 100)
            self.set_status(f"旋转中 {idx}/{len(files)}")

        self.log(f"\n{bar}\n完成！成功处理 {success}/{len(files)} 个视频\n{bar}")
        return success > 0, f"成功 {success}/{len(files)}"

    def _rotate_ffmpeg(self, in_path: str, out_path: str) -> bool:
        vf = _VF_BY_ANGLE.get(self.angle, "null")
        cmd = [
            self.ffmpeg_path,
            "-i", in_path,
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", self.preset(),
            *self.quality_args(),
            "-c:a", "copy",
            "-threads", "0",
            "-y",
            out_path,
        ]
        try:
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


class RotateTab(BaseTab):
    NAME = "rotate"
    TITLE = "批量旋转/翻转"
    ICON = FluentIcon.ROTATE

    def build_form(self):
        self.video_folder = LineEdit(self)
        self._add_folder_row(0, "视频文件夹", self.video_folder)

        self.output_folder = LineEdit(self)
        self.output_folder.setText(
            os.path.join(os.path.expanduser("~"), "Desktop", "视频输出")
        )
        self._add_folder_row(1, "输出文件夹", self.output_folder, is_output=True)

        self.angle = ComboBox(self)
        self._angle_values = [v for v, _ in _ANGLE_OPTIONS]
        for v, label in _ANGLE_OPTIONS:
            self.angle.addItem(f"{label}  ({v})")
        self.angle.setCurrentIndex(0)
        self._add_param_row(2, "选择操作", self.angle,
                            hint="90/180/270 为旋转，hflip/vflip 为翻转")

    def build_worker(self):
        folder = self.video_folder.text().strip()
        output_folder = self.output_folder.text().strip()
        angle = self._angle_values[self.angle.currentIndex()]

        if not self._require_folder(folder, "视频文件夹") \
           or not self._require_folder(output_folder, "输出文件夹") \
           or not self._require_dir_exists(folder, "视频文件夹"):
            return None

        return RotateWorker(
            self.main.ffmpeg_path, self.main.ctrl, self.main.settings,
            folder, output_folder, angle,
        )
