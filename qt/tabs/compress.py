"""批量压缩视频。对应 kk.py 中的 batch_compress_operation / _compress_ffmpeg。"""
from __future__ import annotations

import os
import re
from pathlib import Path

from qfluentwidgets import CheckBox, ComboBox, FluentIcon, LineEdit

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.paths import VIDEO_EXTS, ensure_dir, list_media

from .base import BaseTab


_BITRATE_OPTIONS = ["0.5M", "1M", "1.5M", "2M", "3M", "4M", "6M", "8M"]


class CompressWorker(BatchWorker):
    def __init__(self, ffmpeg_path, ctrl: BatchControl, settings: AppSettings,
                 source_folder: str, output_folder: str, bitrate: str, use_h265: bool):
        super().__init__(ffmpeg_path, ctrl, settings)
        self.source_folder = source_folder
        self.output_folder = output_folder
        self.bitrate = bitrate
        self.use_h265 = use_h265

    def run_batch(self) -> tuple[bool, str]:
        ensure_dir(self.output_folder)
        files = list_media(self.source_folder, VIDEO_EXTS)
        if not files:
            self.log("✗ 文件夹中没有视频文件")
            return False, "无视频文件"

        bar = "=" * 60
        codec_label = "H.265 (libx265)" if self.use_h265 else "H.264 (libx264)"
        self.log(f"\n{bar}\n开始批量压缩   视频数: {len(files)}   码率: {self.bitrate}   编码: {codec_label}\n{bar}")

        success = 0
        for idx, name in enumerate(files, 1):
            if self.ctrl.wait_if_paused():
                self.log("已手动停止"); break

            in_path = os.path.join(self.source_folder, name)
            out_name = f"compress_{self.bitrate}_{idx:03d}_{Path(name).stem}.mp4"
            out_path = os.path.join(self.output_folder, out_name)

            self.log(f"\n[{idx}/{len(files)}] 处理: {name}")
            if self._compress_ffmpeg(in_path, out_path):
                success += 1
                size_mb = os.path.getsize(out_path) / 1024 / 1024
                self.log(f"  ✓ 成功: {out_name} ({size_mb:.1f} MB)")
            else:
                self.log(f"  ✗ 失败: {name}")

            self.set_progress(idx / len(files) * 100)
            self.set_status(f"压缩中 {idx}/{len(files)}")

        self.log(f"\n{bar}\n完成！成功压缩 {success}/{len(files)} 个视频\n{bar}")
        return success > 0, f"成功 {success}/{len(files)}"

    def _compress_ffmpeg(self, in_path: str, out_path: str) -> bool:
        try:
            codec = "libx265" if self.use_h265 else "libx264"
            cmd = [
                self.ffmpeg_path,
                "-i", in_path,
                "-c:v", codec,
                "-preset", self.preset(),
                "-b:v", self.bitrate,
                "-r", "25",
                "-c:a", "aac", "-b:a", "128k",
                "-y", out_path,
            ]
            r = self.run_cmd(cmd, timeout=1200)
            if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return True
            tail = (r.stderr or "")[-400:]
            if tail:
                self.log(f"    stderr: {tail.strip()}")
            return False
        except Exception as e:
            self.log(f"  ✗ 异常: {e}")
            return False


class CompressTab(BaseTab):
    NAME = "compress"
    TITLE = "批量压缩视频"
    ICON = FluentIcon.ZIP_FOLDER

    def build_form(self):
        self.source_folder = LineEdit(self)
        self._add_folder_row(0, "视频文件夹", self.source_folder)

        self.output_folder = LineEdit(self)
        self.output_folder.setText(
            os.path.join(os.path.expanduser("~"), "Desktop", "视频输出")
        )
        self._add_folder_row(1, "输出文件夹", self.output_folder, is_output=True)

        self.bitrate = ComboBox(self)
        self.bitrate.addItems(_BITRATE_OPTIONS)
        self.bitrate.setCurrentText("2M")
        self._add_param_row(2, "目标码率", self.bitrate,
                            hint="越大画质越好，文件越大")

        self.use_h265 = CheckBox("使用 H.265 编码（体积更小，编码更慢）", self)
        self._add_param_row(3, "编码器", self.use_h265)

    def build_worker(self):
        source = self.source_folder.text().strip()
        output = self.output_folder.text().strip()
        bitrate = self.bitrate.currentText().strip().upper()
        use_h265 = self.use_h265.isChecked()

        if not self._require_folder(source, "视频文件夹") \
           or not self._require_folder(output, "输出文件夹") \
           or not self._require_dir_exists(source, "视频文件夹"):
            return None

        if not re.match(r"^[0-9.]+M$", bitrate):
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error("码率格式错误", f"{bitrate}（应为 2M / 1.5M 等）",
                          parent=self.main, position=InfoBarPosition.TOP)
            return None

        return CompressWorker(
            self.main.ffmpeg_path, self.main.ctrl, self.main.settings,
            source, output, bitrate, use_h265,
        )
