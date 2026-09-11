"""批量添加标题文字。对应 kk.py 中的 create_title_tab / batch_title_operation / _title_ffmpeg。"""
from __future__ import annotations

from qt.core.i18n import tr

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QButtonGroup, QColorDialog, QFileDialog, QHBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    DoubleSpinBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PushButton,
    RadioButton,
    SpinBox,
)

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.ffmpeg_helper import probe_resolution_fps
from qt.core.fonts import list_system_fonts, wrap_title_text
from qt.core.paths import VIDEO_EXTS, ensure_dir, list_media

from .base import BaseTab


class TitleWorker(BatchWorker):
    def __init__(self, ffmpeg_path, ctrl: BatchControl, settings: AppSettings,
                 video_folder: str, output_folder: str,
                 font_path: str, title_lines: list[str] | None, fixed_title: str | None,
                 fontsize_val: float, fontsize_unit: str, y_percent: float, font_color: str):
        super().__init__(ffmpeg_path, ctrl, settings)
        self.video_folder = video_folder
        self.output_folder = output_folder
        self.output_dir = output_folder
        self.font_path = font_path
        self.title_lines = title_lines
        self.fixed_title = fixed_title
        self.fontsize_val = fontsize_val
        self.fontsize_unit = fontsize_unit
        self.y_percent = y_percent
        self.font_color = font_color

    def run_batch(self) -> tuple[bool, str]:
        ensure_dir(self.output_folder)
        files = list_media(self.video_folder, VIDEO_EXTS)
        if not files:
            self.log(tr("✗ 文件夹中没有视频文件"))
            return False, tr("无视频文件")

        bar = "=" * 60
        self.log(tr('\n{0}\n开始批量添加标题   视频数: {1}').format(bar, len(files)))
        if self.title_lines:
            self.log(tr("标题来源: TXT 共 {0} 行（不够循环）").format(len(self.title_lines)))
        else:
            self.log(tr("标题: {0}").format(self.fixed_title))
        self.log(tr("字体: {0}").format(os.path.basename(self.font_path)))
        self.log(bar)

        success = 0
        for idx, name in enumerate(files, 1):
            if self.ctrl.wait_if_paused():
                self.log(tr("已手动停止")); break

            in_path = os.path.join(self.video_folder, name)
            out_name = f"title_{idx:03d}_{Path(name).stem}.mp4"
            out_path = os.path.join(self.output_folder, out_name)

            current_title = (
                self.title_lines[(idx - 1) % len(self.title_lines)]
                if self.title_lines else self.fixed_title
            ).replace("%", "")

            self.log(tr('\n[{0}/{1}] 处理: {2}').format(idx, len(files), name))
            self.log(tr("  标题: {0}").format(current_title))

            try:
                ok = self._title_ffmpeg(in_path, out_path, current_title)
            except RuntimeError as e:
                if "__font_error__" in str(e):
                    self.log(tr("✗ 字体加载失败，终止批处理"))
                    return False, tr("字体失效")
                raise

            if ok:
                success += 1
                size_mb = os.path.getsize(out_path) / 1024 / 1024
                self.log(tr("  ✓ 成功: {0} ({1:.1f} MB)").format(out_name, size_mb))
            else:
                self.log(tr("  ✗ 失败: {0}").format(name))

            self.set_progress(idx / len(files) * 100)
            self.set_status(tr("添加标题中 {0}/{1}").format(idx, len(files)))

        self.log(tr('\n{0}\n完成！成功处理 {1}/{2} 个视频\n{3}').format(bar, success, len(files), bar))
        return success > 0, tr("成功 {0}/{1}").format(success, len(files))

    def _title_ffmpeg(self, in_path: str, out_path: str, title_text: str) -> bool:
        try:
            safe_font = self.font_path.replace("\\", "/").replace(":", "\\:")
            ffmpeg_color = "0x" + self.font_color[1:] if self.font_color.startswith("#") else self.font_color

            video_w, video_h, _ = probe_resolution_fps(self.ffmpeg_path, in_path)
            if self.fontsize_unit == "percent":
                fontsize = max(10, int(video_h * self.fontsize_val / 100))
            else:
                fontsize = max(10, int(self.fontsize_val))

            lines = wrap_title_text(title_text, fontsize, video_w)
            line_spacing = fontsize * 1.35
            filters = []
            for i, line in enumerate(lines):
                safe_text = line.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
                y_expr = f"h*{self.y_percent}+{i * line_spacing:.1f}"
                filters.append(
                    f"drawtext=fontfile='{safe_font}'"
                    f":text='{safe_text}'"
                    f":x=(w-text_w)/2"
                    f":y={y_expr}"
                    f":fontsize={fontsize}"
                    f":fontcolor={ffmpeg_color}"
                    f":borderw=3"
                    f":bordercolor=black@0.7"
                    f":shadowx=2:shadowy=2:shadowcolor=black@0.5"
                )
            drawtext = ",".join(filters)

            cmd = [
                self.ffmpeg_path,
                "-i", in_path,
                "-vf", drawtext,
                "-c:v", "libx264",
                "-preset", self.preset(),
                *self.quality_args(),
                "-c:a", "copy",
                "-y", out_path,
            ]
            r = self.run_cmd(cmd, timeout=600)
            if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return True

            stderr_text = r.stderr or ""
            if "Fontconfig error" in stderr_text or "Cannot load default config file" in stderr_text:
                raise RuntimeError("__font_error__")
            tail = stderr_text[-400:]
            if tail:
                self.log(f"    stderr: {tail.strip()}")
            return False
        except RuntimeError:
            raise
        except Exception as e:
            self.log(tr("  ✗ 异常: {0}").format(e))
            return False


class TitleTab(BaseTab):
    NAME = "title"
    TITLE = "批量添加标题"
    ICON = FluentIcon.FONT

    def build_form(self):
        self.video_folder = LineEdit(self)
        self._add_folder_row(0, tr("视频文件夹"), self.video_folder)

        self.output_folder = LineEdit(self)
        self.output_folder.setText(
            os.path.join(os.path.expanduser("~"), "Desktop", tr("视频输出"))
        )
        self._add_folder_row(1, tr("输出文件夹"), self.output_folder, is_output=True,
                             placeholder=tr("留空则使用 源文件夹/title_output"))

        # 字体
        self.font_combo = ComboBox(self)
        self._font_map = list_system_fonts()
        for label in self._font_map:
            self.font_combo.addItem(label)
        if self._font_map:
            names = list(self._font_map.keys())
            default = next((n for n in names if "微软雅黑" in n), None) or names[0]  # i18n: skip（匹配字体名）
            self.font_combo.setCurrentText(default)
        self._add_param_row(2, tr("字体"), self.font_combo,
                            hint=tr("含中文的字体可防止中文乱码"))

        # 字体大小 + 单位
        size_holder = QWidget(self)
        size_row = QHBoxLayout(size_holder)
        size_row.setContentsMargins(0, 0, 0, 0)
        size_row.setSpacing(10)
        self.fontsize = DoubleSpinBox(self)
        self.fontsize.setRange(0.5, 200.0)
        self.fontsize.setValue(5.0)
        self.fontsize.setDecimals(1)
        self.fontsize.setSingleStep(0.5)
        size_row.addWidget(self.fontsize)

        self.size_unit_group = QButtonGroup(self)
        self._size_unit_values = ["percent", "px"]
        rb_pct = RadioButton("%", self); rb_pct.setChecked(True)
        rb_px = RadioButton("px", self)
        self.size_unit_group.addButton(rb_pct, id=0)
        self.size_unit_group.addButton(rb_px, id=1)
        size_row.addWidget(rb_pct); size_row.addWidget(rb_px)
        self.size_unit_hint = BodyLabel(tr("% 视频高度"), self)
        self.size_unit_hint.setStyleSheet("color: #8a8a8a;")
        size_row.addWidget(self.size_unit_hint)
        size_row.addStretch(1)
        self.size_unit_group.idToggled.connect(self._on_size_unit_change)
        self._add_param_row(3, tr("字体大小"), size_holder)

        # Y 位置
        self.y_percent = SpinBox(self)
        self.y_percent.setRange(0, 90)
        self.y_percent.setValue(8)
        self.y_percent.setSuffix(" %")
        self._add_param_row(4, tr("文字高度位置"), self.y_percent,
                            hint=tr("距顶部百分比，默认 8%"))

        # 字体颜色
        color_holder = QWidget(self)
        color_row = QHBoxLayout(color_holder)
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(10)

        self._font_color = "#ffffff"
        self.color_preview = PushButton("  ", self)
        self.color_preview.setFixedSize(32, 28)
        self.color_preview.clicked.connect(self._pick_color)
        self._update_color_preview()
        color_row.addWidget(self.color_preview)

        for label, hex_val in ((tr("白色"), "#ffffff"), (tr("黄色"), "#ffff00"),
                               (tr("红色"), "#ff3333"), (tr("黑色"), "#000000")):
            btn = PushButton(label, self)
            btn.clicked.connect(lambda _=False, h=hex_val: self._set_color(h))
            color_row.addWidget(btn)
        color_row.addStretch(1)
        self._add_param_row(5, tr("字体颜色"), color_holder)

        # 标题来源（固定文字 / TXT）
        mode_holder = QWidget(self)
        mode_row = QHBoxLayout(mode_holder)
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(18)
        self.mode_group = QButtonGroup(self)
        self._mode_values = ["fixed", "txt"]
        rb_fixed = RadioButton(tr("固定文字"), self); rb_fixed.setChecked(True)
        rb_txt = RadioButton(tr("从 TXT 读取"), self)
        self.mode_group.addButton(rb_fixed, id=0)
        self.mode_group.addButton(rb_txt, id=1)
        mode_row.addWidget(rb_fixed); mode_row.addWidget(rb_txt); mode_row.addStretch(1)
        self.mode_group.idToggled.connect(self._on_mode_change)
        self._add_param_row(6, tr("标题来源"), mode_holder)

        # 固定文字
        self.fixed_text = LineEdit(self)
        self.fixed_text.setPlaceholderText(tr("输入固定标题"))
        self.form_layout.addWidget(BodyLabel(tr("标题文字"), self), 7, 0)
        self.form_layout.addWidget(self.fixed_text, 7, 1, 1, 2)

        # TXT 文件
        self.txt_file = LineEdit(self)
        self.txt_file.setPlaceholderText(tr("每行一条标题，视频数超出时从第一行循环"))
        self._add_file_row(8, tr("TXT 文件"), self.txt_file,
                           file_filter=tr("文本文件 (*.txt)"),
                           placeholder=None)

        self._on_mode_change(0, True)  # 默认显示固定文字

    # ─── UI 联动 ───
    def _on_size_unit_change(self, btn_id: int, checked: bool):
        if not checked:
            return
        unit = self._size_unit_values[btn_id]
        if unit == "percent":
            self.size_unit_hint.setText(tr("% 视频高度"))
            if self.fontsize.value() > 50:
                self.fontsize.setValue(5.0)
        else:
            self.size_unit_hint.setText(tr("px 像素"))
            if self.fontsize.value() <= 1.0:
                self.fontsize.setValue(30.0)

    def _on_mode_change(self, btn_id: int, checked: bool):
        if not checked:
            return
        is_fixed = self._mode_values[btn_id] == "fixed"

        def _set_row_visible(row: int, visible: bool):
            for col in range(self.form_layout.columnCount()):
                item = self.form_layout.itemAtPosition(row, col)
                if item and item.widget():
                    item.widget().setVisible(visible)

        _set_row_visible(7, is_fixed)
        _set_row_visible(8, not is_fixed)

    # ─── 颜色选择 ───
    def _pick_color(self):
        initial = QColor(self._font_color)
        color = QColorDialog.getColor(initial, self, tr("选择字体颜色"))
        if color.isValid():
            self._set_color(color.name())

    def _set_color(self, hex_color: str):
        self._font_color = hex_color
        self._update_color_preview()

    def _update_color_preview(self):
        self.color_preview.setStyleSheet(
            f"PushButton {{ background-color: {self._font_color}; "
            f"border: 1px solid rgba(0,0,0,0.2); }}"
        )

    # ─── 构建 worker ───
    def build_worker(self):
        video_folder = self.video_folder.text().strip()
        output_folder = self.output_folder.text().strip()

        if not self._require_folder(video_folder, tr("视频文件夹")) \
           or not self._require_dir_exists(video_folder, tr("视频文件夹")):
            return None

        if not output_folder:
            output_folder = os.path.join(video_folder, "title_output")

        font_label = self.font_combo.currentText().strip()
        font_path = self._font_map.get(font_label)
        if not font_path or not os.path.exists(font_path):
            InfoBar.error(tr("字体不存在"), tr("找不到字体文件：{0}").format(font_label),
                          parent=self.main, position=InfoBarPosition.TOP)
            return None

        fontsize_unit = self._size_unit_values[max(0, self.size_unit_group.checkedId())]
        fontsize_val = self.fontsize.value()
        if fontsize_unit == "percent":
            fontsize_val = max(0.5, min(50.0, fontsize_val))
        else:
            fontsize_val = max(10, int(fontsize_val))

        y_percent = max(0, min(90, self.y_percent.value())) / 100

        text_mode = self._mode_values[max(0, self.mode_group.checkedId())]
        if text_mode == "fixed":
            fixed_title = "".join(ch for ch in self.fixed_text.text() if ch.isprintable()).strip()
            if not fixed_title:
                InfoBar.warning(tr("请输入标题文字"), "",
                                parent=self.main, position=InfoBarPosition.TOP)
                return None
            title_lines = None
        else:
            txt_file = self.txt_file.text().strip()
            if not txt_file or not os.path.exists(txt_file):
                InfoBar.error(tr("TXT 文件不存在"), txt_file or tr("(空)"),
                              parent=self.main, position=InfoBarPosition.TOP)
                return None
            try:
                with open(txt_file, "r", encoding="utf-8") as f:
                    title_lines = [line.strip() for line in f if line.strip()]
            except Exception as e:
                InfoBar.error(tr("读取 TXT 失败"), str(e),
                              parent=self.main, position=InfoBarPosition.TOP)
                return None
            if not title_lines:
                InfoBar.error(tr("TXT 内容为空"), tr("文件中没有有效行"),
                              parent=self.main, position=InfoBarPosition.TOP)
                return None
            fixed_title = None

        return TitleWorker(
            self.main.ffmpeg_path, self.main.ctrl, self.main.settings,
            video_folder, output_folder, font_path,
            title_lines, fixed_title,
            fontsize_val, fontsize_unit, y_percent, self._font_color,
        )
