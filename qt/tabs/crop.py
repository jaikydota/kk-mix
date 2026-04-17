"""批量裁剪比例。对应 kk.py 中的 batch_crop_operation / _crop_ffmpeg / _crop_image。"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QWidget
from qfluentwidgets import ComboBox, FluentIcon, LineEdit, RadioButton

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.ffmpeg_helper import probe_resolution_fps
from qt.core.paths import IMAGE_EXTS, VIDEO_EXTS, ensure_dir, list_media

from .base import BaseTab


_RATIOS = ["9:16", "16:9", "1:1", "4:3", "3:4", "4:5", "21:9"]


class CropWorker(BatchWorker):
    def __init__(self, ffmpeg_path, ctrl: BatchControl, settings: AppSettings,
                 source_folder: str, output_folder: str, ratio_str: str, is_image: bool):
        super().__init__(ffmpeg_path, ctrl, settings)
        self.source_folder = source_folder
        self.output_folder = output_folder
        self.output_dir = output_folder
        self.ratio_str = ratio_str
        self.is_image = is_image
        self.rw, self.rh = [int(x) for x in ratio_str.split(":")]

    def run_batch(self) -> tuple[bool, str]:
        if not self.output_folder:
            self.output_folder = os.path.join(self.source_folder, "crop_output")
        ensure_dir(self.output_folder)

        exts = IMAGE_EXTS if self.is_image else VIDEO_EXTS
        files = list_media(self.source_folder, exts)
        type_label = "图片" if self.is_image else "视频"
        if not files:
            self.log(f"✗ 文件夹中没有{type_label}文件")
            return False, f"无{type_label}文件"

        bar = "=" * 60
        self.log(f"\n{bar}\n开始批量裁剪{type_label}比例   {type_label}数: {len(files)}   目标比例: {self.ratio_str}\n{bar}")

        success = 0
        ratio_token = self.ratio_str.replace(":", "x")
        for idx, name in enumerate(files, 1):
            if self.ctrl.wait_if_paused():
                self.log("已手动停止"); break

            in_path = os.path.join(self.source_folder, name)
            if self.is_image:
                ext = Path(name).suffix.lower()
                out_name = f"crop_{ratio_token}_{idx:03d}_{Path(name).stem}{ext}"
                out_path = os.path.join(self.output_folder, out_name)
                ok = self._crop_image(in_path, out_path)
            else:
                out_name = f"crop_{ratio_token}_{idx:03d}_{Path(name).stem}.mp4"
                out_path = os.path.join(self.output_folder, out_name)
                ok = self._crop_video(in_path, out_path)

            self.log(f"\n[{idx}/{len(files)}] 处理: {name}")
            if ok:
                success += 1
                self.log(f"  ✓ 成功: {out_name}")
            else:
                self.log(f"  ✗ 失败: {name}")

            self.set_progress(idx / len(files) * 100)
            self.set_status(f"裁剪{type_label}中 {idx}/{len(files)}")

        self.log(f"\n{bar}\n完成！成功处理 {success}/{len(files)} 个{type_label}\n输出目录: {self.output_folder}\n{bar}")
        return success > 0, f"成功 {success}/{len(files)}"

    def _crop_video(self, in_path: str, out_path: str) -> bool:
        try:
            src_w, src_h, _ = probe_resolution_fps(self.ffmpeg_path, in_path)
            src_ratio = src_w / src_h
            target_ratio = self.rw / self.rh

            if abs(src_ratio - target_ratio) < 0.001:
                crop_filter = f"crop={src_w}:{src_h}:0:0"
            elif src_ratio > target_ratio:
                new_w = int(src_h * self.rw / self.rh)
                new_w -= new_w % 2
                x = (src_w - new_w) // 2
                crop_filter = f"crop={new_w}:{src_h}:{x}:0"
            else:
                new_h = int(src_w * self.rh / self.rw)
                new_h -= new_h % 2
                y = (src_h - new_h) // 2
                crop_filter = f"crop={src_w}:{new_h}:0:{y}"

            cmd = [
                self.ffmpeg_path, "-i", in_path,
                "-vf", crop_filter,
                "-c:v", "libx264",
                "-preset", self.preset(),
                *self.quality_args(),
                "-c:a", "copy",
                "-y", out_path,
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

    def _crop_image(self, in_path: str, out_path: str) -> bool:
        try:
            from PIL import Image
            with Image.open(in_path) as img:
                src_w, src_h = img.size
                src_ratio = src_w / src_h
                target_ratio = self.rw / self.rh

                if abs(src_ratio - target_ratio) < 0.001:
                    crop_box = (0, 0, src_w, src_h)
                elif src_ratio > target_ratio:
                    new_w = int(src_h * self.rw / self.rh)
                    x = (src_w - new_w) // 2
                    crop_box = (x, 0, x + new_w, src_h)
                else:
                    new_h = int(src_w * self.rh / self.rw)
                    y = (src_h - new_h) // 2
                    crop_box = (0, y, src_w, y + new_h)

                cropped = img.crop(crop_box)
                if img.mode == "RGBA" and Path(out_path).suffix.lower() in (".jpg", ".jpeg", ".bmp"):
                    cropped = cropped.convert("RGB")
                cropped.save(out_path, quality=95)
            return True
        except Exception as e:
            self.log(f"  ✗ 异常: {e}")
            return False


class CropTab(BaseTab):
    NAME = "crop"
    TITLE = "批量裁剪比例"
    ICON = FluentIcon.CLIPPING_TOOL

    def build_form(self):
        # 媒体类型单选
        self.mode_group = QButtonGroup(self)
        self._mode_values = ["video", "image"]
        holder = QWidget(self)
        h = QHBoxLayout(holder)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(18)
        rb_v = RadioButton("视频", self); rb_v.setChecked(True)
        rb_i = RadioButton("图片", self)
        self.mode_group.addButton(rb_v, id=0)
        self.mode_group.addButton(rb_i, id=1)
        h.addWidget(rb_v); h.addWidget(rb_i); h.addStretch(1)
        self._add_param_row(0, "媒体类型", holder)

        self.source_folder = LineEdit(self)
        self._add_folder_row(1, "源文件夹", self.source_folder)

        self.output_folder = LineEdit(self)
        self._add_folder_row(2, "输出文件夹", self.output_folder, is_output=True,
                             placeholder="留空则使用 源文件夹/crop_output")

        self.ratio = ComboBox(self)
        self.ratio.addItems(_RATIOS)
        self.ratio.setCurrentText("9:16")
        self._add_param_row(3, "目标比例", self.ratio, hint="居中裁剪，不会拉伸")

    def build_worker(self):
        source = self.source_folder.text().strip()
        output = self.output_folder.text().strip()
        ratio_str = self.ratio.currentText().strip()
        is_image = self._mode_values[max(0, self.mode_group.checkedId())] == "image"

        if not self._require_folder(source, "源文件夹") \
           or not self._require_dir_exists(source, "源文件夹"):
            return None

        if ":" not in ratio_str:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error("比例格式错误", ratio_str,
                          parent=self.main, position=InfoBarPosition.TOP)
            return None

        return CropWorker(
            self.main.ffmpeg_path, self.main.ctrl, self.main.settings,
            source, output, ratio_str, is_image,
        )
