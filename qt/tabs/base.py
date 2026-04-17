"""所有功能 Tab 的基类。

约定：
  - NAME / TITLE / ICON 为类属性，被 MainWindow 注册时读取
  - build_form()   子类实现，往 self.form_layout 填控件
  - build_worker() 子类实现，校验参数并返回 BatchWorker；非法时返回 None 并弹提示
"""
from __future__ import annotations

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
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    PushButton,
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

        header = StrongBodyLabel(self.TITLE, self)
        header.setStyleSheet("font-size: 22px; font-weight: 600;")
        outer.addWidget(header)

        self.form_card = CardWidget(self)
        self.form_layout = QGridLayout(self.form_card)
        self.form_layout.setContentsMargins(24, 24, 24, 24)
        self.form_layout.setHorizontalSpacing(14)
        self.form_layout.setVerticalSpacing(14)
        self.build_form()
        outer.addWidget(self.form_card)

        self.start_btn = PrimaryPushButton("开始批量处理", self, FluentIcon.PLAY)
        self.start_btn.setFixedHeight(42)
        self.start_btn.clicked.connect(self._on_start)
        outer.addWidget(self.start_btn)

        outer.addStretch(1)

    # ─── 子类覆写 ───
    def build_form(self) -> None:
        raise NotImplementedError

    def build_worker(self) -> BatchWorker | None:
        raise NotImplementedError

    # ─── 事件 ───
    def _on_start(self):
        if self.main.current_worker and self.main.current_worker.isRunning():
            InfoBar.warning(
                "有任务进行中",
                "请等待当前任务结束或点击停止。",
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
        btn = PushButton("浏览", self, FluentIcon.FOLDER)
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
        btn = PushButton("浏览", self, FluentIcon.DOCUMENT)
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
        title = "选择输出文件夹" if is_output else "选择文件夹"
        start = line_edit.text() or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, title, start)
        if folder:
            line_edit.setText(folder.replace("/", os.sep))

    def _browse_file(self, line_edit: LineEdit, file_filter: str):
        start = line_edit.text() or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", start, file_filter)
        if path:
            line_edit.setText(path.replace("/", os.sep))

    # ─── 公用参数校验 ───
    def _require_folder(self, path: str, label: str) -> bool:
        if not path:
            InfoBar.warning(
                "参数不完整",
                f"请选择{label}",
                parent=self.main,
                position=InfoBarPosition.TOP,
            )
            return False
        return True

    def _require_dir_exists(self, path: str, label: str) -> bool:
        if not os.path.isdir(path):
            InfoBar.error(
                "路径无效",
                f"{label}不存在：{path}",
                parent=self.main,
                position=InfoBarPosition.TOP,
            )
            return False
        return True
