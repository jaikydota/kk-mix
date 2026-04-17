"""左右分屏合并。对应 kk.py 中的 create_merge_tab / batch_merge_operation / _merge_with_ffmpeg。

迁移策略：
  - 保留纯视频+视频的 FFmpeg hstack 路径（原 kk.py 主逻辑）
  - 图片路径暂时走同样的 FFmpeg 方案：通过 `-loop 1 + -t` 把图片变成等长视频后 hstack；
    原 kk.py 的 MoviePy 备用方案在此次迁移中暂不移植（减轻打包体积）
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QButtonGroup
from qfluentwidgets import FluentIcon, LineEdit, RadioButton, SpinBox

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.ffmpeg_helper import probe_duration
from qt.core.paths import ALL_MEDIA_EXTS, IMAGE_EXTS, VIDEO_EXTS, ensure_dir, list_media

from .base import BaseTab


class MergeWorker(BatchWorker):
    def __init__(self, ffmpeg_path, ctrl: BatchControl, settings: AppSettings,
                 folder1: str, folder2: str, output: str,
                 audio_source: str, image_duration: float):
        super().__init__(ffmpeg_path, ctrl, settings)
        self.folder1 = folder1
        self.folder2 = folder2
        self.output = output
        self.audio_source = audio_source     # "folder1" | "folder2" | "none"
        self.image_duration = image_duration

    def run_batch(self) -> tuple[bool, str]:
        ensure_dir(self.output)
        files1 = list_media(self.folder1, ALL_MEDIA_EXTS)
        files2 = list_media(self.folder2, ALL_MEDIA_EXTS)
        if not files1 or not files2:
            self.log("✗ 至少有一个文件夹中没有找到媒体文件")
            return False, "媒体文件不足"

        total = min(len(files1), len(files2))
        bar = "=" * 60
        self.log(f"\n{bar}\n开始分屏合并：文件夹1 有 {len(files1)} 个，文件夹2 有 {len(files2)} 个\n{bar}")

        success = 0
        for idx, (n1, n2) in enumerate(zip(files1, files2), 1):
            if self.ctrl.wait_if_paused():
                self.log("已手动停止"); break

            p1 = os.path.join(self.folder1, n1)
            p2 = os.path.join(self.folder2, n2)
            out_name = f"merge_{idx:03d}_{Path(n1).stem}_{Path(n2).stem}.mp4"
            out_path = os.path.join(self.output, out_name)

            self.log(f"\n[{idx}/{total}] 处理: {n1} + {n2}")
            if self._merge_ffmpeg(p1, p2, out_path):
                success += 1
                size_mb = os.path.getsize(out_path) / 1024 / 1024
                self.log(f"  ✓ 成功: {out_name} ({size_mb:.1f} MB)")
            else:
                self.log(f"  ✗ 失败")

            self.set_progress(idx / total * 100)
            self.set_status(f"分屏合并中 {idx}/{total}")

        self.log(f"\n{bar}\n完成！成功生成 {success}/{total} 个视频\n{bar}")
        return success > 0, f"成功 {success}/{total}"

    # ─── FFmpeg 核心 ───
    def _merge_ffmpeg(self, p1: str, p2: str, out_path: str) -> bool:
        try:
            ext1 = Path(p1).suffix.lower()
            ext2 = Path(p2).suffix.lower()
            is_img1 = ext1 in IMAGE_EXTS
            is_img2 = ext2 in IMAGE_EXTS

            inputs: list[str] = []
            if is_img1:
                inputs += ["-loop", "1", "-t", str(self.image_duration), "-i", p1]
            else:
                inputs += ["-i", p1]
            if is_img2:
                inputs += ["-loop", "1", "-t", str(self.image_duration), "-i", p2]
            else:
                inputs += ["-i", p2]

            video_filter = (
                "[0:v]scale=540:1080:force_original_aspect_ratio=decrease,"
                "pad=540:1080:(ow-iw)/2:(oh-ih)/2[v0];"
                "[1:v]scale=540:1080:force_original_aspect_ratio=decrease,"
                "pad=540:1080:(ow-iw)/2:(oh-ih)/2[v1];"
                "[v0][v1]hstack=inputs=2[v]"
            )

            # 音频分支
            filter_complex = video_filter
            audio_map: list[str] = []
            if self.audio_source == "folder1" and not is_img1:
                filter_complex += ";[0:a]anull[a]"
                audio_map = ["-map", "[a]", "-c:a", "aac"]
            elif self.audio_source == "folder2" and not is_img2:
                filter_complex += ";[1:a]anull[a]"
                audio_map = ["-map", "[a]", "-c:a", "aac"]
            else:
                audio_map = ["-an"]

            # 与原逻辑一致，纯视频对取较短时长
            min_duration = 0.0
            if not is_img1 and not is_img2:
                d1 = probe_duration(self.ffmpeg_path, p1)
                d2 = probe_duration(self.ffmpeg_path, p2)
                if d1 > 0 and d2 > 0:
                    min_duration = min(d1, d2)

            cmd = [self.ffmpeg_path, *inputs,
                   "-filter_complex", filter_complex,
                   "-map", "[v]", *audio_map,
                   "-c:v", "libx264",
                   "-preset", self.preset(),
                   *self.quality_args(),
                   "-threads", "0",
                   "-y", out_path]
            if min_duration > 0:
                cmd += ["-t", str(min_duration)]

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


class MergeTab(BaseTab):
    NAME = "merge"
    TITLE = "左右分屏合并"
    ICON = FluentIcon.ALIGNMENT

    def build_form(self):
        self.folder1 = LineEdit(self)
        self._add_folder_row(0, "文件夹 1（左）", self.folder1)

        self.folder2 = LineEdit(self)
        self._add_folder_row(1, "文件夹 2（右）", self.folder2)

        self.output = LineEdit(self)
        self.output.setText(
            os.path.join(os.path.expanduser("~"), "Desktop", "视频输出")
        )
        self._add_folder_row(2, "输出文件夹", self.output, is_output=True)

        # 音频源选择（3 个单选）
        self.audio_group = QButtonGroup(self)
        self._audio_source_values = ["folder1", "folder2", "none"]
        audio_labels = ["使用文件夹 1 音频", "使用文件夹 2 音频", "无音频"]
        from PySide6.QtWidgets import QWidget, QHBoxLayout
        holder = QWidget(self)
        h = QHBoxLayout(holder)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(18)
        for i, label in enumerate(audio_labels):
            rb = RadioButton(label, self)
            if i == 0:
                rb.setChecked(True)
            self.audio_group.addButton(rb, id=i)
            h.addWidget(rb)
        h.addStretch(1)
        self._add_param_row(3, "音频源", holder)

        self.image_duration = SpinBox(self)
        self.image_duration.setRange(1, 60)
        self.image_duration.setValue(5)
        self.image_duration.setSuffix(" 秒")
        self._add_param_row(4, "图片显示时长", self.image_duration,
                            hint="仅当某个输入是图片时生效")

    def build_worker(self):
        f1 = self.folder1.text().strip()
        f2 = self.folder2.text().strip()
        out = self.output.text().strip()
        audio_source = self._audio_source_values[max(0, self.audio_group.checkedId())]
        image_duration = float(self.image_duration.value())

        if not self._require_folder(f1, "文件夹 1") \
           or not self._require_folder(f2, "文件夹 2") \
           or not self._require_folder(out, "输出文件夹") \
           or not self._require_dir_exists(f1, "文件夹 1") \
           or not self._require_dir_exists(f2, "文件夹 2"):
            return None

        return MergeWorker(
            self.main.ffmpeg_path, self.main.ctrl, self.main.settings,
            f1, f2, out, audio_source, image_duration,
        )
