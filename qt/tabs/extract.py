"""批量提取视频帧。对应 kk.py 中的 create_extract_tab / batch_extract_operation / _extract_frames_ffmpeg。"""
from __future__ import annotations

import os
from pathlib import Path

from qfluentwidgets import DoubleSpinBox, FluentIcon, LineEdit

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.paths import ensure_dir, list_media, VIDEO_EXTS

from .base import BaseTab


class ExtractFramesWorker(BatchWorker):
    def __init__(self, ffmpeg_path, ctrl: BatchControl, settings: AppSettings,
                 folder: str, output_folder: str, interval: float):
        super().__init__(ffmpeg_path, ctrl, settings)
        self.folder = folder
        self.output_folder = output_folder
        self.output_dir = output_folder
        self.interval = interval

    def run_batch(self) -> tuple[bool, str]:
        ensure_dir(self.output_folder)
        files = list_media(self.folder, VIDEO_EXTS)
        if not files:
            self.log("✗ 文件夹中没有视频文件")
            return False, "无视频文件"

        bar = "=" * 60
        self.log(f"\n{bar}\n开始批量提取视频帧   视频数: {len(files)}   间隔: {self.interval} 秒\n{bar}")

        total_frames = 0
        for idx, name in enumerate(files, 1):
            if self.ctrl.wait_if_paused():
                self.log("已手动停止"); break

            in_path = os.path.join(self.folder, name)
            stem = Path(name).stem
            video_out_dir = os.path.join(self.output_folder, f"frames_{stem}")
            ensure_dir(video_out_dir)

            self.log(f"\n[{idx}/{len(files)}] 处理: {name}")
            count = self._extract_ffmpeg(in_path, video_out_dir, stem)
            if count > 0:
                total_frames += count
                self.log(f"  ✓ 提取 {count} 帧到 {video_out_dir}")
            else:
                self.log(f"  ✗ 失败: {name}")

            self.set_progress(idx / len(files) * 100)
            self.set_status(f"提取帧中 {idx}/{len(files)}")

        self.log(f"\n{bar}\n完成！总计提取 {total_frames} 帧\n{bar}")
        return total_frames > 0, f"总计 {total_frames} 帧"

    def _extract_ffmpeg(self, in_path: str, out_folder: str, stem: str) -> int:
        pattern = os.path.join(out_folder, f"{stem}_%04d.jpg")
        cmd = [
            self.ffmpeg_path,
            "-i", in_path,
            "-vf", f"fps=1/{self.interval}",
            "-q:v", "2",
            "-y",
            pattern,
        ]
        try:
            r = self.run_cmd(cmd, timeout=600)
            if r.returncode == 0:
                return len([f for f in os.listdir(out_folder) if f.lower().endswith(".jpg")])
            tail = (r.stderr or "")[-400:]
            if tail:
                self.log(f"    stderr: {tail.strip()}")
            return 0
        except Exception as e:
            self.log(f"  ✗ 异常: {e}")
            return 0


class ExtractTab(BaseTab):
    NAME = "extract"
    TITLE = "批量提取帧"
    ICON = FluentIcon.PHOTO

    def build_form(self):
        self.video_folder = LineEdit(self)
        self._add_folder_row(0, "视频文件夹", self.video_folder,
                             placeholder="选择需要提取帧的视频所在文件夹")

        self.output_folder = LineEdit(self)
        self.output_folder.setText(
            os.path.join(os.path.expanduser("~"), "Desktop", "视频输出")
        )
        self._add_folder_row(1, "输出文件夹", self.output_folder, is_output=True)

        self.interval = DoubleSpinBox(self)
        self.interval.setRange(0.1, 600.0)
        self.interval.setValue(5.0)
        self.interval.setSingleStep(1.0)
        self.interval.setDecimals(2)
        self.interval.setSuffix(" 秒")
        self._add_param_row(2, "提取间隔", self.interval, hint="每 N 秒提取 1 帧")

    def build_worker(self):
        folder = self.video_folder.text().strip()
        output_folder = self.output_folder.text().strip()
        interval = self.interval.value()

        if not self._require_folder(folder, "视频文件夹") \
           or not self._require_folder(output_folder, "输出文件夹") \
           or not self._require_dir_exists(folder, "视频文件夹"):
            return None

        return ExtractFramesWorker(
            self.main.ffmpeg_path, self.main.ctrl, self.main.settings,
            folder, output_folder, interval,
        )
