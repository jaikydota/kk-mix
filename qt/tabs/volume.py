"""批量调整音量。对应 kk.py 中的 create_volume_tab / batch_volume_operation / _volume_change_ffmpeg。"""
from __future__ import annotations

import os
from pathlib import Path

from qfluentwidgets import BodyLabel, DoubleSpinBox, FluentIcon, LineEdit

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.paths import ensure_dir, list_media, VIDEO_EXTS

from .base import BaseTab


class VolumeWorker(BatchWorker):
    def __init__(self, ffmpeg_path, ctrl: BatchControl, settings: AppSettings,
                 folder: str, output_folder: str, factor: float):
        super().__init__(ffmpeg_path, ctrl, settings)
        self.folder = folder
        self.output_folder = output_folder
        self.factor = factor

    def run_batch(self) -> tuple[bool, str]:
        ensure_dir(self.output_folder)
        files = list_media(self.folder, VIDEO_EXTS)
        if not files:
            self.log("✗ 文件夹中没有视频文件")
            return False, "无视频文件"

        bar = "=" * 60
        self.log(f"\n{bar}\n开始批量调整音量   视频数: {len(files)}   倍数: {self.factor}\n{bar}")

        success = 0
        for idx, name in enumerate(files, 1):
            if self.ctrl.wait_if_paused():
                self.log("已手动停止")
                break

            in_path = os.path.join(self.folder, name)
            out_name = f"volume_{idx:03d}_{self.factor}x_{Path(name).stem}.mp4"
            out_path = os.path.join(self.output_folder, out_name)

            self.log(f"\n[{idx}/{len(files)}] 处理: {name}")
            if self._volume_ffmpeg(in_path, out_path):
                success += 1
                size_mb = os.path.getsize(out_path) / 1024 / 1024
                self.log(f"  ✓ 成功: {out_name} ({size_mb:.1f} MB)")
            else:
                self.log(f"  ✗ 失败: {name}")

            self.set_progress(idx / len(files) * 100)
            self.set_status(f"音量调整中 {idx}/{len(files)}")

        self.log(f"\n{bar}\n完成！成功处理 {success}/{len(files)} 个视频\n{bar}")
        return success > 0, f"成功 {success}/{len(files)}"

    def _volume_ffmpeg(self, in_path: str, out_path: str) -> bool:
        cmd = [
            self.ffmpeg_path,
            "-i", in_path,
            "-c:v", "copy",
            "-af", f"volume={self.factor}",
            "-c:a", "aac",
            "-threads", "0",
            "-y",
            out_path,
        ]
        try:
            r = self.run_cmd(cmd, timeout=300)
            if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return True
            tail = (r.stderr or "")[-400:]
            if tail:
                self.log(f"    stderr: {tail.strip()}")
            return False
        except Exception as e:
            self.log(f"  ✗ 异常: {e}")
            return False


class VolumeTab(BaseTab):
    NAME = "volume"
    TITLE = "批量调整音量"
    ICON = FluentIcon.VOLUME

    def build_form(self):
        self.video_folder = LineEdit(self)
        self._add_folder_row(
            0, "视频文件夹", self.video_folder,
            placeholder="选择需处理视频所在文件夹",
        )

        self.output_folder = LineEdit(self)
        self.output_folder.setText(
            os.path.join(os.path.expanduser("~"), "Desktop", "视频输出")
        )
        self._add_folder_row(1, "输出文件夹", self.output_folder, is_output=True)

        self.factor = DoubleSpinBox(self)
        self.factor.setRange(0.1, 10.0)
        self.factor.setValue(1.0)
        self.factor.setSingleStep(0.1)
        self.factor.setDecimals(2)
        self.factor.setSuffix(" x")
        self._add_param_row(
            2, "音量倍数", self.factor,
            hint="0.5 = 减半   1.0 = 不变   2.0 = 加倍",
        )

    def build_worker(self):
        folder = self.video_folder.text().strip()
        output_folder = self.output_folder.text().strip()
        factor = self.factor.value()

        if not self._require_folder(folder, "视频文件夹"):
            return None
        if not self._require_folder(output_folder, "输出文件夹"):
            return None
        if not self._require_dir_exists(folder, "视频文件夹"):
            return None

        return VolumeWorker(
            self.main.ffmpeg_path, self.main.ctrl, self.main.settings,
            folder, output_folder, factor,
        )
