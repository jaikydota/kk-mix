"""批量变速/倒放。对应 kk.py 中的 create_speed_tab / batch_speed_operation / _speed_change_ffmpeg。"""
from __future__ import annotations

from qt.core.i18n import tr

import os
from pathlib import Path

from qfluentwidgets import CheckBox, DoubleSpinBox, FluentIcon, LineEdit

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.paths import ensure_dir, list_media, VIDEO_EXTS

from .base import BaseTab


class SpeedWorker(BatchWorker):
    def __init__(self, ffmpeg_path, ctrl: BatchControl, settings: AppSettings,
                 folder: str, output_folder: str, factor: float, reverse: bool):
        super().__init__(ffmpeg_path, ctrl, settings)
        self.folder = folder
        self.output_folder = output_folder
        self.output_dir = output_folder
        self.factor = factor
        self.reverse = reverse

    def run_batch(self) -> tuple[bool, str]:
        ensure_dir(self.output_folder)
        files = list_media(self.folder, VIDEO_EXTS)
        if not files:
            self.log(tr("✗ 文件夹中没有视频文件"))
            return False, tr("无视频文件")

        bar = "=" * 60
        self.log(tr('\n{0}\n开始批量变速/倒放   视频数: {1}   倍数: {2}x   倒放: {3}\n{4}').format(bar, len(files), self.factor, tr("是") if self.reverse else tr("否"), bar))

        success = 0
        for idx, name in enumerate(files, 1):
            if self.ctrl.wait_if_paused():
                self.log(tr("已手动停止")); break

            in_path = os.path.join(self.folder, name)
            suffix = "reverse" if self.reverse else f"{self.factor}x"
            out_name = f"speed_{idx:03d}_{suffix}_{Path(name).stem}.mp4"
            out_path = os.path.join(self.output_folder, out_name)

            self.log(tr('\n[{0}/{1}] 处理: {2}').format(idx, len(files), name))
            if self._speed_ffmpeg(in_path, out_path):
                success += 1
                size_mb = os.path.getsize(out_path) / 1024 / 1024
                self.log(tr("  ✓ 成功: {0} ({1:.1f} MB)").format(out_name, size_mb))
            else:
                self.log(tr("  ✗ 失败: {0}").format(name))

            self.set_progress(idx / len(files) * 100)
            self.set_status(tr("变速中 {0}/{1}").format(idx, len(files)))

        self.log(tr('\n{0}\n完成！成功处理 {1}/{2} 个视频\n{3}').format(bar, success, len(files), bar))
        return success > 0, tr("成功 {0}/{1}").format(success, len(files))

    def _speed_ffmpeg(self, in_path: str, out_path: str) -> bool:
        vf_filters: list[str] = []
        if self.factor != 1.0:
            vf_filters.append(f"setpts=PTS/{self.factor}")
        if self.reverse:
            vf_filters.append("reverse")

        af_filters: list[str] = []
        if self.factor != 1.0:
            af_filters.append(f"atempo={self.factor}")

        vf = ",".join(vf_filters) if vf_filters else "null"
        af = ",".join(af_filters) if af_filters else "null"

        cmd = [
            self.ffmpeg_path,
            "-i", in_path,
            "-vf", vf,
            "-af", af,
            "-c:v", "libx264",
            "-preset", self.preset(),
            *self.quality_args(),
            "-c:a", "aac",
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
            self.log(tr("  ✗ 异常: {0}").format(e))
            return False


class SpeedTab(BaseTab):
    NAME = "speed"
    TITLE = "批量变速/倒放"
    ICON = FluentIcon.SPEED_HIGH

    def build_form(self):
        self.video_folder = LineEdit(self)
        self._add_folder_row(0, tr("视频文件夹"), self.video_folder)

        self.output_folder = LineEdit(self)
        self.output_folder.setText(
            os.path.join(os.path.expanduser("~"), "Desktop", tr("视频输出"))
        )
        self._add_folder_row(1, tr("输出文件夹"), self.output_folder, is_output=True)

        self.factor = DoubleSpinBox(self)
        self.factor.setRange(0.1, 5.0)
        self.factor.setValue(1.5)
        self.factor.setSingleStep(0.1)
        self.factor.setDecimals(2)
        self.factor.setSuffix(" x")
        self._add_param_row(2, tr("速度倍数"), self.factor,
                            hint=tr("0.5 = 慢放   2.0 = 快放"))

        self.reverse = CheckBox(tr("倒放视频"), self)
        self._add_param_row(3, tr("倒放"), self.reverse)

    def build_worker(self):
        folder = self.video_folder.text().strip()
        output_folder = self.output_folder.text().strip()
        factor = self.factor.value()
        reverse = self.reverse.isChecked()

        if not self._require_folder(folder, tr("视频文件夹")) \
           or not self._require_folder(output_folder, tr("输出文件夹")) \
           or not self._require_dir_exists(folder, tr("视频文件夹")):
            return None

        return SpeedWorker(
            self.main.ffmpeg_path, self.main.ctrl, self.main.settings,
            folder, output_folder, factor, reverse,
        )
