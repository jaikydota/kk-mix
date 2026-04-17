"""批量分割视频。对应 kk.py 中的 create_split_tab / batch_split_operation / split_video_ffmpeg。"""
from __future__ import annotations

import os
from pathlib import Path

from qfluentwidgets import CheckBox, DoubleSpinBox, FluentIcon, LineEdit

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.ffmpeg_helper import probe_duration
from qt.core.paths import ensure_dir, list_media, VIDEO_EXTS

from .base import BaseTab


class SplitWorker(BatchWorker):
    def __init__(self, ffmpeg_path, ctrl: BatchControl, settings: AppSettings,
                 folder: str, output: str, audio_output: str,
                 duration: float, extract_audio: bool, keep_remainder: bool):
        super().__init__(ffmpeg_path, ctrl, settings)
        self.folder = folder
        self.output = output
        self.output_dir = output
        self.audio_output = audio_output
        self.duration = duration
        self.extract_audio = extract_audio
        self.keep_remainder = keep_remainder

    def run_batch(self) -> tuple[bool, str]:
        ensure_dir(self.output)
        if self.extract_audio:
            ensure_dir(self.audio_output)

        files = list_media(self.folder, VIDEO_EXTS)
        if not files:
            self.log("✗ 文件夹中没有视频文件")
            return False, "无视频文件"

        bar = "=" * 60
        self.log(f"\n{bar}\n开始批量分割   视频数: {len(files)}   片段时长: {self.duration} 秒\n{bar}")

        total_segments = 0
        for idx, name in enumerate(files, 1):
            if self.ctrl.wait_if_paused():
                self.log("已手动停止"); break

            video_path = os.path.join(self.folder, name)
            count = self._split_one(video_path)
            total_segments += count

            self.set_progress(idx / len(files) * 100)
            self.set_status(f"分割中 {idx}/{len(files)}")

        self.log(f"\n{bar}\n完成！总计 {total_segments} 片段\n{bar}")
        return total_segments > 0, f"{total_segments} 片段"

    def _split_one(self, video_path: str) -> int:
        stem = Path(video_path).stem
        self.log(f"\n=== 处理: {stem} ===")

        if not os.path.exists(video_path):
            self.log(f"✗ 文件不存在: {video_path}")
            return 0

        total_duration = probe_duration(self.ffmpeg_path, video_path)
        if total_duration <= 0:
            self.log("  ✗ 无法读取时长，跳过")
            return 0

        if total_duration < self.duration:
            if self.keep_remainder:
                num_segments = 1
            else:
                self.log("  时长不足，跳过")
                return 0
        else:
            num_segments = int(total_duration // self.duration)
            remainder = total_duration % self.duration
            if self.keep_remainder and remainder > 0.5:
                num_segments += 1

        self.log(f"  将分割为 {num_segments} 个片段")

        produced = 0
        for i in range(num_segments):
            if self.ctrl.wait_if_paused():
                break

            start = i * self.duration
            end = min(start + self.duration, total_duration)
            seg_duration = end - start

            out_name = f"{stem}_part{i+1:03d}.mp4"
            out_path = os.path.join(self.output, out_name)
            self.log(f"  片段 {i+1}/{num_segments}: {start:.1f}-{end:.1f}s ({seg_duration:.1f}s)")

            if self._split_ffmpeg(video_path, out_path, start, seg_duration):
                produced += 1
                if self.extract_audio:
                    audio_name = f"{stem}_part{i+1:03d}.mp3"
                    audio_path = os.path.join(self.audio_output, audio_name)
                    self._extract_audio(video_path, audio_path, start, seg_duration)

        return produced

    def _split_ffmpeg(self, in_path: str, out_path: str, start: float, seg_duration: float) -> bool:
        try:
            cmd = [
                self.ffmpeg_path,
                "-i", in_path,
                "-ss", str(start),
                "-t", str(seg_duration),
                "-c:v", "libx264",
                "-preset", self.preset(),
                *self.quality_args(),
                "-c:a", "aac",
                "-threads", "0",
                "-avoid_negative_ts", "make_zero",
                "-y",
                out_path,
            ]
            r = self.run_cmd(cmd, timeout=300)
            if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                size_mb = os.path.getsize(out_path) / 1024 / 1024
                self.log(f"    ✓ {os.path.basename(out_path)} ({size_mb:.1f} MB)")
                return True
            tail = (r.stderr or "")[-300:]
            if tail:
                self.log(f"    stderr: {tail.strip()}")
            return False
        except Exception as e:
            self.log(f"    ✗ 异常: {e}")
            return False

    def _extract_audio(self, in_path: str, out_path: str, start: float, seg_duration: float) -> bool:
        try:
            cmd = [
                self.ffmpeg_path,
                "-i", in_path,
                "-ss", str(start),
                "-t", str(seg_duration),
                "-vn",
                "-c:a", "libmp3lame",
                "-q:a", "4",
                "-y",
                out_path,
            ]
            r = self.run_cmd(cmd, timeout=300)
            return r.returncode == 0 and os.path.exists(out_path)
        except Exception:
            return False


class SplitTab(BaseTab):
    NAME = "split"
    TITLE = "批量分割视频"
    ICON = FluentIcon.CUT

    def build_form(self):
        self.video_folder = LineEdit(self)
        self._add_folder_row(0, "视频文件夹", self.video_folder)

        self.output_folder = LineEdit(self)
        self.output_folder.setText(
            os.path.join(os.path.expanduser("~"), "Desktop", "视频输出")
        )
        self._add_folder_row(1, "视频输出文件夹", self.output_folder, is_output=True)

        self.audio_folder = LineEdit(self)
        self._add_folder_row(2, "音频输出文件夹", self.audio_folder, is_output=True)

        self.duration = DoubleSpinBox(self)
        self.duration.setRange(1.0, 3600.0)
        self.duration.setValue(10.0)
        self.duration.setSingleStep(1.0)
        self.duration.setDecimals(1)
        self.duration.setSuffix(" 秒")
        self._add_param_row(3, "片段时长", self.duration)

        self.extract_audio = CheckBox("同时提取 MP3 音频", self)
        self._add_param_row(4, "提取音频", self.extract_audio)

        self.keep_remainder = CheckBox("保留末尾不足片段", self)
        self.keep_remainder.setChecked(True)
        self._add_param_row(5, "余数片段", self.keep_remainder)

    def build_worker(self):
        folder = self.video_folder.text().strip()
        output = self.output_folder.text().strip()
        audio_output = self.audio_folder.text().strip()
        duration = self.duration.value()
        extract = self.extract_audio.isChecked()
        keep = self.keep_remainder.isChecked()

        if not self._require_folder(folder, "视频文件夹") \
           or not self._require_folder(output, "视频输出文件夹") \
           or not self._require_dir_exists(folder, "视频文件夹"):
            return None
        if extract and not self._require_folder(audio_output, "音频输出文件夹"):
            return None

        return SplitWorker(
            self.main.ffmpeg_path, self.main.ctrl, self.main.settings,
            folder, output, audio_output, duration, extract, keep,
        )
