"""批量添加水印。对应 kk.py 中的 create_watermark_tab / batch_watermark_operation / _watermark_video_ffmpeg。"""
from __future__ import annotations

import os
from pathlib import Path

from qfluentwidgets import ComboBox, DoubleSpinBox, FluentIcon, LineEdit

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.ffmpeg_helper import probe_resolution_fps
from qt.core.paths import ensure_dir, list_media, VIDEO_EXTS

from .base import BaseTab


_POSITION_OPTIONS = [
    ("top_left", "左上"),
    ("top_right", "右上"),
    ("bottom_left", "左下"),
    ("bottom_right", "右下"),
    ("center", "居中"),
]


class WatermarkWorker(BatchWorker):
    def __init__(self, ffmpeg_path, ctrl: BatchControl, settings: AppSettings,
                 video_folder: str, watermark_image: str, output_folder: str,
                 position: str, opacity: float, scale: float):
        super().__init__(ffmpeg_path, ctrl, settings)
        self.video_folder = video_folder
        self.watermark_image = watermark_image
        self.output_folder = output_folder
        self.output_dir = output_folder
        self.position = position
        self.opacity = opacity
        self.scale = scale

    def run_batch(self) -> tuple[bool, str]:
        if not os.path.isfile(self.watermark_image):
            self.log("✗ 水印图片不存在")
            return False, "水印图片不存在"
        ensure_dir(self.output_folder)

        files = list_media(self.video_folder, VIDEO_EXTS)
        if not files:
            self.log("✗ 文件夹中没有视频文件")
            return False, "无视频文件"

        bar = "=" * 60
        self.log(f"\n{bar}\n开始批量添加水印   视频数: {len(files)}")
        self.log(f"位置: {self.position}   透明度: {self.opacity}   缩放: {self.scale}")
        self.log(bar)

        success = 0
        for idx, name in enumerate(files, 1):
            if self.ctrl.wait_if_paused():
                self.log("已手动停止"); break

            in_path = os.path.join(self.video_folder, name)
            out_name = f"watermark_{idx:03d}_{Path(name).stem}.mp4"
            out_path = os.path.join(self.output_folder, out_name)

            self.log(f"\n[{idx}/{len(files)}] 处理: {name}")
            if self._watermark_ffmpeg(in_path, out_path):
                success += 1
                size_mb = os.path.getsize(out_path) / 1024 / 1024
                self.log(f"  ✓ 成功: {out_name} ({size_mb:.1f} MB)")
            else:
                self.log(f"  ✗ 失败: {name}")

            self.set_progress(idx / len(files) * 100)
            self.set_status(f"添加水印中 {idx}/{len(files)}")

        self.log(f"\n{bar}\n完成！成功处理 {success}/{len(files)} 个视频\n{bar}")
        return success > 0, f"成功 {success}/{len(files)}"

    def _watermark_ffmpeg(self, in_path: str, out_path: str) -> bool:
        try:
            video_w, video_h, _ = probe_resolution_fps(self.ffmpeg_path, in_path)

            # 读水印图片原始分辨率以算等比缩放后的高度
            try:
                from PIL import Image
                with Image.open(self.watermark_image) as img:
                    wm_w, wm_h = img.size
            except Exception:
                wm_w, wm_h = 100, 100  # 容错默认

            target_w = int(video_w * self.scale)
            target_h = int(wm_h * (target_w / wm_w)) if wm_w else target_w

            if self.position == "top_left":
                x, y = 0, 0
            elif self.position == "top_right":
                x, y = video_w - target_w, 0
            elif self.position == "bottom_left":
                x, y = 0, video_h - target_h
            elif self.position == "bottom_right":
                x, y = video_w - target_w, video_h - target_h
            else:  # center
                x = (video_w - target_w) // 2
                y = (video_h - target_h) // 2

            filter_complex = (
                f"[1:v]scale={target_w}:{target_h}[wm];"
                f"[wm]format=rgba,colorchannelmixer=aa={self.opacity}[wm_alpha];"
                f"[0:v][wm_alpha]overlay=x={x}:y={y}[v]"
            )

            cmd = [
                self.ffmpeg_path,
                "-i", in_path,
                "-i", self.watermark_image,
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


class WatermarkTab(BaseTab):
    NAME = "watermark"
    TITLE = "批量添加水印"
    ICON = FluentIcon.TAG

    def build_form(self):
        self.video_folder = LineEdit(self)
        self._add_folder_row(0, "视频文件夹", self.video_folder)

        self.watermark_image = LineEdit(self)
        self._add_file_row(
            1, "水印图片", self.watermark_image,
            file_filter="图片 (*.png *.jpg *.jpeg *.webp)",
            placeholder="选择水印图片（推荐 PNG 透明底）",
        )

        self.output_folder = LineEdit(self)
        self.output_folder.setText(
            os.path.join(os.path.expanduser("~"), "Desktop", "视频输出")
        )
        self._add_folder_row(2, "输出文件夹", self.output_folder, is_output=True)

        self.position = ComboBox(self)
        self._position_values = [v for v, _ in _POSITION_OPTIONS]
        for v, label in _POSITION_OPTIONS:
            self.position.addItem(f"{label}  ({v})")
        self._add_param_row(3, "水印位置", self.position)

        self.opacity = DoubleSpinBox(self)
        self.opacity.setRange(0.05, 1.0); self.opacity.setValue(0.8)
        self.opacity.setSingleStep(0.05); self.opacity.setDecimals(2)
        self._add_param_row(4, "透明度", self.opacity, hint="0.1 - 1.0")

        self.scale = DoubleSpinBox(self)
        self.scale.setRange(0.02, 0.5); self.scale.setValue(0.2)
        self.scale.setSingleStep(0.01); self.scale.setDecimals(2)
        self._add_param_row(5, "缩放比例", self.scale, hint="相对视频宽度的比例，0.05 - 0.5")

    def build_worker(self):
        video_folder = self.video_folder.text().strip()
        watermark_image = self.watermark_image.text().strip()
        output_folder = self.output_folder.text().strip()
        position = self._position_values[self.position.currentIndex()]
        opacity = self.opacity.value()
        scale = self.scale.value()

        if not self._require_folder(video_folder, "视频文件夹") \
           or not self._require_folder(watermark_image, "水印图片") \
           or not self._require_folder(output_folder, "输出文件夹") \
           or not self._require_dir_exists(video_folder, "视频文件夹"):
            return None
        if not os.path.isfile(watermark_image):
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error("水印图片不存在", watermark_image,
                          parent=self.main, position=InfoBarPosition.TOP)
            return None

        return WatermarkWorker(
            self.main.ffmpeg_path, self.main.ctrl, self.main.settings,
            video_folder, watermark_image, output_folder,
            position, opacity, scale,
        )
