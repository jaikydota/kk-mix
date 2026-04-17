"""主窗口：左侧 NavigationInterface + 右侧 QStackedWidget + 底部日志/进度/控制面板。"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    NavigationInterface,
    NavigationItemPosition,
    ProgressBar,
    PushButton,
    TextEdit,
)

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.ffmpeg_helper import find_ffmpeg
from qt.core.paths import APP_TITLE, resource_path, settings_path

from qt.tabs.base import BaseTab
from qt.tabs.compress import CompressTab
from qt.tabs.concat import ConcatTab
from qt.tabs.convert import ConvertTab
from qt.tabs.crop import CropTab
from qt.tabs.extract import ExtractTab
from qt.tabs.merge import MergeTab
from qt.tabs.music import MusicTab
from qt.tabs.pip import PipTab
from qt.tabs.rotate import RotateTab
from qt.tabs.speed import SpeedTab
from qt.tabs.split import SplitTab
from qt.tabs.title import TitleTab
from qt.tabs.volume import VolumeTab
from qt.tabs.watermark import WatermarkTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ctrl = BatchControl()
        self.current_worker: BatchWorker | None = None
        self._trigger_btn: PushButton | None = None

        self.settings = AppSettings.load(settings_path())

        self.ffmpeg_path = find_ffmpeg()

        self.setWindowTitle(APP_TITLE)
        self.resize(1180, 820)
        icon_path = resource_path(os.path.join("assets", "logo.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._build_ui()
        self._register_tabs()

        if not self.ffmpeg_path:
            InfoBar.error(
                "未找到 FFmpeg",
                "请把 ffmpeg.exe 放在程序目录或加入系统 PATH。",
                parent=self, duration=-1,
                position=InfoBarPosition.TOP,
            )

    # ─────────────────── UI 搭建 ───────────────────
    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QWidget(self)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.nav = NavigationInterface(self, showMenuButton=True)
        self.stack = QStackedWidget(self)
        body_layout.addWidget(self.nav)
        body_layout.addWidget(self.stack, 1)

        bottom = self._build_bottom_panel()

        splitter = QSplitter(Qt.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(body)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([560, 220])

        root.addWidget(splitter)

    def _build_bottom_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("bottomPanel")
        panel.setStyleSheet(
            "#bottomPanel { border-top: 1px solid rgba(0,0,0,0.08); }"
        )

        v = QVBoxLayout(panel)
        v.setContentsMargins(16, 10, 16, 12)
        v.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)

        self.status_label = BodyLabel("就绪", self)
        self.status_label.setMinimumWidth(160)

        self.progress = ProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.pause_btn = PushButton("暂停", self, FluentIcon.PAUSE)
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._on_pause_resume)

        self.stop_btn = PushButton("停止", self, FluentIcon.CLOSE)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)

        self.clear_btn = PushButton("清空日志", self, FluentIcon.DELETE)
        self.clear_btn.clicked.connect(lambda: self.log_view.clear())

        self.export_btn = PushButton("导出日志", self, FluentIcon.SAVE)
        self.export_btn.clicked.connect(self._export_log)

        top.addWidget(self.status_label)
        top.addWidget(self.progress, 1)
        top.addWidget(self.pause_btn)
        top.addWidget(self.stop_btn)
        top.addWidget(self.clear_btn)
        top.addWidget(self.export_btn)
        v.addLayout(top)

        self.log_view = TextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("操作日志会显示在这里…")
        v.addWidget(self.log_view, 1)

        return panel

    # ─────────────────── 注册 Tab ───────────────────
    def _register_tabs(self):
        """在此集中注册所有 Tab。后续迁移只需往这里 append。"""
        tabs: list[BaseTab] = [
            MergeTab(self),
            ConcatTab(self),
            SplitTab(self),
            PipTab(self),
            SpeedTab(self),
            RotateTab(self),
            WatermarkTab(self),
            VolumeTab(self),
            TitleTab(self),
            MusicTab(self),
            CropTab(self),
            CompressTab(self),
            ConvertTab(self),
            ExtractTab(self),
        ]
        for tab in tabs:
            self._add_tab(tab)

        self.nav.addItem(
            routeKey="settings",
            icon=FluentIcon.SETTING,
            text="全局设置",
            onClick=self._open_settings,
            position=NavigationItemPosition.BOTTOM,
            selectable=False,
        )
        self.nav.addItem(
            routeKey="about",
            icon=FluentIcon.INFO,
            text="关于",
            onClick=self._show_about,
            position=NavigationItemPosition.BOTTOM,
            selectable=False,
        )

        if self.stack.count() > 0:
            self.stack.setCurrentIndex(0)

    def _add_tab(self, tab: BaseTab):
        self.stack.addWidget(tab)
        self.nav.addItem(
            routeKey=tab.NAME,
            icon=tab.ICON,
            text=tab.TITLE,
            onClick=lambda *_, t=tab: self.stack.setCurrentWidget(t),
        )

    def _open_settings(self, *_):
        from qt.settings_window import SettingsDialog
        SettingsDialog(self).exec()

    def _show_about(self, *_):
        InfoBar.info(
            APP_TITLE, "Qt + Fluent 重构版本。",
            parent=self, position=InfoBarPosition.TOP_RIGHT, duration=3000,
        )

    # ─────────────────── 日志/进度/状态 ───────────────────
    def log(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{ts}] {msg}")

    def set_progress(self, v: float):
        self.progress.setValue(int(round(v)))

    def set_status(self, msg: str):
        self.status_label.setText(msg)

    def _export_log(self):
        from PySide6.QtWidgets import QFileDialog
        from datetime import datetime
        from qt.core.paths import VERSION

        text = self.log_view.toPlainText().strip()
        if not text:
            InfoBar.info(
                "提示", "操作日志为空，无需导出。",
                parent=self, position=InfoBarPosition.TOP,
            )
            return
        folder = QFileDialog.getExistingDirectory(self, "选择日志导出文件夹")
        if not folder:
            return
        name = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{VERSION}.log"
        path = os.path.join(folder, name)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.log(f"[日志] 已导出到：{path}")
        except Exception as e:
            InfoBar.error(
                "导出失败", str(e),
                parent=self, position=InfoBarPosition.TOP,
            )

    # ─────────────────── Worker 调度 ───────────────────
    def run_worker(self, worker: BatchWorker, trigger_btn: PushButton | None = None):
        self.ctrl.reset()
        self.current_worker = worker
        self._trigger_btn = trigger_btn

        worker.log_signal.connect(self.log)
        worker.progress_signal.connect(self.set_progress)
        worker.status_signal.connect(self.set_status)
        worker.finished_signal.connect(self._on_worker_finished)

        self.progress.setValue(0)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setText("暂停")
        self.stop_btn.setEnabled(True)
        if trigger_btn is not None:
            trigger_btn.setEnabled(False)
        self.set_status("启动中…")
        worker.start()

    def _on_worker_finished(self, success: bool, summary: str):
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        if self._trigger_btn is not None:
            self._trigger_btn.setEnabled(True)
        self.set_status("完成" if success else "结束（含失败）")

        if success:
            InfoBar.success(
                "处理完成", summary, parent=self,
                position=InfoBarPosition.TOP_RIGHT, duration=4000,
            )
        else:
            InfoBar.warning(
                "处理结束", summary, parent=self,
                position=InfoBarPosition.TOP_RIGHT, duration=4000,
            )
        self.current_worker = None

    def _on_pause_resume(self):
        if not self.current_worker:
            return
        self.ctrl.paused = not self.ctrl.paused
        self.pause_btn.setText("继续" if self.ctrl.paused else "暂停")
        self.set_status("已暂停" if self.ctrl.paused else "运行中")

    def _on_stop(self):
        if not self.current_worker:
            return
        self.ctrl.stopped = True
        self.ctrl.paused = False
        self.set_status("正在停止…")

    def closeEvent(self, event):
        if self.current_worker and self.current_worker.isRunning():
            self.ctrl.stopped = True
            self.current_worker.wait(3000)
        super().closeEvent(event)
