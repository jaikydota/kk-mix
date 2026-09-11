"""所有功能 Tab 的基类。

约定：
  - NAME / TITLE / ICON 为类属性，被 MainWindow 注册时读取；TITLE 保持中文，显示时 tr()
  - build_form()   子类实现，往 self.form_layout 填控件
  - build_worker() 子类实现，校验参数并返回 BatchWorker；非法时返回 None 并弹提示
"""
from __future__ import annotations

from qt.core.i18n import tr

import os
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    DoubleSpinBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    RadioButton,
    SpinBox,
    StrongBodyLabel,
)

from qt.core.batch_worker import BatchWorker

if TYPE_CHECKING:
    from qt.main_window import MainWindow


class BaseTab(QWidget):
    NAME: str = "base"
    TITLE: str = "功能"
    ICON = FluentIcon.APPLICATION

    def __init__(self, main_window: "MainWindow"):
        super().__init__(main_window)
        self.main = main_window
        # Fluent 导航要求每个子界面 objectName 唯一
        self.setObjectName(f"{self.NAME}_interface")
        self._build_ui()

    # ─── UI 组装 ───
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(18)

        header = StrongBodyLabel(tr(self.TITLE), self)
        header.setStyleSheet("font-size: 22px; font-weight: 600;")
        outer.addWidget(header)

        self.form_card = QWidget(self)
        self.form_layout = QGridLayout(self.form_card)
        self.form_layout.setContentsMargins(8, 8, 8, 8)
        self.form_layout.setHorizontalSpacing(14)
        self.form_layout.setVerticalSpacing(14)
        self.build_form()
        outer.addWidget(self.form_card)

        self.start_btn = PrimaryPushButton(tr("开始批量处理"), self, FluentIcon.PLAY)
        self.start_btn.setFixedHeight(42)
        self.start_btn.clicked.connect(self._on_start)
        outer.addWidget(self.start_btn)

        outer.addStretch(1)

    # ─── 表单状态快照（语言切换重建窗口时保持用户已填内容） ───
    # 顺序固定，两次构建的控件树完全一致，因此可按序号一一对应
    _STATE_TYPES = (LineEdit, PlainTextEdit, ComboBox, SpinBox, DoubleSpinBox, CheckBox, RadioButton)

    def _state_widgets(self) -> list:
        widgets = []
        for cls in self._STATE_TYPES:
            widgets.extend(self.findChildren(cls))
        return widgets

    def capture_state(self) -> dict:
        """收集当前表单的全部输入值。"""
        values = []
        for w in self._state_widgets():
            if isinstance(w, (CheckBox, RadioButton)):
                values.append(w.isChecked())
            elif isinstance(w, ComboBox):
                values.append(w.currentIndex())
            elif isinstance(w, (SpinBox, DoubleSpinBox)):
                values.append(w.value())
            elif isinstance(w, PlainTextEdit):
                values.append(w.toPlainText())
            else:
                values.append(w.text())
        return {"rows": len(getattr(self, "rows", []) or []), "values": values}

    def restore_state(self, state: dict) -> None:
        """把快照写回重建后的表单；结构不一致时静默跳过。"""
        if not state:
            return
        # 动态行（转场拼接等）需先补足行数，否则控件数量对不上
        rows = getattr(self, "rows", None)
        if rows is not None and hasattr(self, "_add_row"):
            while len(self.rows) < state.get("rows", 0):
                self._add_row()

        widgets = self._state_widgets()
        values = state.get("values", [])
        if len(widgets) != len(values):
            return
        for w, v in zip(widgets, values):
            try:
                if isinstance(w, (CheckBox, RadioButton)):
                    w.setChecked(bool(v))
                elif isinstance(w, ComboBox):
                    if 0 <= v < w.count():
                        w.setCurrentIndex(v)
                elif isinstance(w, (SpinBox, DoubleSpinBox)):
                    w.setValue(v)
                elif isinstance(w, PlainTextEdit):
                    w.setPlainText(v)
                else:
                    w.setText(v)
            except Exception:
                pass

    # ─── 子类覆写 ───
    def build_form(self) -> None:
        raise NotImplementedError

    def build_worker(self) -> BatchWorker | None:
        raise NotImplementedError

    # ─── 事件 ───
    def _on_start(self):
        if self.main.current_worker and self.main.current_worker.isRunning():
            InfoBar.warning(
                tr("有任务进行中"),
                tr("请等待当前任务结束或点击停止。"),
                parent=self.main,
                position=InfoBarPosition.TOP,
            )
            return
        worker = self.build_worker()
        if worker is None:
            return
        self.main.run_worker(worker, trigger_btn=self.start_btn)

    # ─── 辅助：快速搭表单 ───
    def _add_folder_row(
        self,
        row: int,
        label: str,
        line_edit: LineEdit,
        is_output: bool = False,
        placeholder: str | None = None,
    ):
        """添加一行 [Label] [LineEdit] [浏览按钮]。"""
        if placeholder:
            line_edit.setPlaceholderText(placeholder)
        self.form_layout.addWidget(BodyLabel(label, self), row, 0)
        self.form_layout.addWidget(line_edit, row, 1)
        btn = PushButton(tr("浏览"), self, FluentIcon.FOLDER)
        btn.clicked.connect(lambda: self._browse_folder(line_edit, is_output))
        self.form_layout.addWidget(btn, row, 2)
        self.form_layout.setColumnStretch(1, 1)

    def _add_file_row(
        self,
        row: int,
        label: str,
        line_edit: LineEdit,
        file_filter: str,
        placeholder: str | None = None,
    ):
        """添加一行 [Label] [LineEdit] [浏览文件按钮]。"""
        if placeholder:
            line_edit.setPlaceholderText(placeholder)
        self.form_layout.addWidget(BodyLabel(label, self), row, 0)
        self.form_layout.addWidget(line_edit, row, 1)
        btn = PushButton(tr("浏览"), self, FluentIcon.DOCUMENT)
        btn.clicked.connect(lambda: self._browse_file(line_edit, file_filter))
        self.form_layout.addWidget(btn, row, 2)
        self.form_layout.setColumnStretch(1, 1)

    def _add_param_row(
        self,
        row: int,
        label: str,
        widget: QWidget,
        hint: str | None = None,
    ):
        """添加一行 [Label] [控件] [灰色提示]。"""
        self.form_layout.addWidget(BodyLabel(label, self), row, 0)

        holder = QWidget(self)
        h = QHBoxLayout(holder)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        h.addWidget(widget)
        if hint:
            hint_label = BodyLabel(hint, self)
            hint_label.setStyleSheet("color: #8a8a8a;")
            h.addWidget(hint_label)
        h.addStretch(1)
        self.form_layout.addWidget(holder, row, 1, 1, 2)

    def _browse_folder(self, line_edit: LineEdit, is_output: bool):
        title = tr("选择输出文件夹") if is_output else tr("选择文件夹")
        start = line_edit.text() or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, title, start)
        if folder:
            line_edit.setText(folder.replace("/", os.sep))

    def _browse_file(self, line_edit: LineEdit, file_filter: str):
        start = line_edit.text() or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, tr("选择文件"), start, file_filter)
        if path:
            line_edit.setText(path.replace("/", os.sep))

    # ─── 公用参数校验 ───
    def _require_folder(self, path: str, label: str) -> bool:
        if not path:
            InfoBar.warning(
                tr("参数不完整"),
                tr("请选择{0}").format(label),
                parent=self.main,
                position=InfoBarPosition.TOP,
            )
            return False
        return True

    def _require_dir_exists(self, path: str, label: str) -> bool:
        if not os.path.isdir(path):
            InfoBar.error(
                tr("路径无效"),
                tr("{0}不存在：{1}").format(label, path),
                parent=self.main,
                position=InfoBarPosition.TOP,
            )
            return False
        return True
