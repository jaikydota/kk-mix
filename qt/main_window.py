"""主窗口：左侧 NavigationInterface + 右侧 QStackedWidget + 底部日志/进度/控制面板。"""
from __future__ import annotations

from qt.core.i18n import tr

import os

from PySide6.QtCore import QEvent, Qt
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
    InfoBarIcon,
    InfoBarPosition,
    NavigationInterface,
    NavigationItemPosition,
    ProgressBar,
    PushButton,
    SingleDirectionScrollArea,
    TextEdit,
    TransparentToolButton,
)

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.ffmpeg_helper import find_ffmpeg
from qt.core import i18n
from qt.core.paths import APP_NAME, VERSION, resource_path, settings_path

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
from qt.tabs.subtitle_concat import SubtitleConcatTab
from qt.tabs.title import TitleTab
from qt.tabs.volume import VolumeTab
from qt.tabs.watermark import WatermarkTab


class MainWindow(QMainWindow):
    _instance: "MainWindow | None" = None   # 语言切换重建后的当前窗口

    def __init__(self):
        super().__init__()
        self.ctrl = BatchControl()
        self.current_worker: BatchWorker | None = None
        self._trigger_btn: PushButton | None = None
        self._log_mode = "normal"

        self.settings = AppSettings.load(settings_path())

        self.ffmpeg_path = find_ffmpeg()

        self.setWindowTitle(f"{tr(APP_NAME)} {VERSION}")
        self.resize(1180, 880)
        icon_path = resource_path(os.path.join("assets", "logo.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._build_ui()
        self._register_tabs()

        if not self.ffmpeg_path:
            InfoBar.error(
                tr("未找到 FFmpeg"),
                tr("请把 ffmpeg.exe 放在程序目录或加入系统 PATH。"),
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
        self.nav.setExpandWidth(180)
        self.stack = QStackedWidget(self)

        # 导航项一多（15 个功能页 + 3 个底部项），qfluentwidgets 会把 nav 的
        # minimumHeight 顶到 ~870px，主窗口就再也缩不小了。这里包一层滚动区：
        # nav 保留自身高度，窗口变矮时滚动显示，而不是把导航项压到互相重叠。
        # 用 SingleDirectionScrollArea 而非 QScrollArea：它的滚动条是悬浮式的，
        # 不占用视口宽度，也不会在导航栏旁边杵一条灰色长条。
        self.nav_scroll = SingleDirectionScrollArea(orient=Qt.Vertical)
        self.nav_scroll.setParent(self)
        self.nav_scroll.setWidget(self.nav)
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.nav_scroll.viewport().setStyleSheet("background: transparent;")
        self.nav.installEventFilter(self)

        body_layout.addWidget(self.nav_scroll)
        self._sync_nav_width()

        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: rgba(0,0,0,0.10);")
        sep.setFixedWidth(1)
        body_layout.addWidget(sep)

        body_layout.addWidget(self.stack, 1)

        self.bottom_panel = self._build_bottom_panel()

        self.splitter = QSplitter(Qt.Vertical, self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(body)
        self.splitter.addWidget(self.bottom_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([620, 220])

        root.addWidget(self.splitter)

    def _sync_nav_width(self):
        """滚动区宽度跟随导航栏的展开/收起（滚动条悬浮，不需要额外留宽）。"""
        self.nav_scroll.setFixedWidth(self.nav.width())

    def eventFilter(self, obj, event):
        if obj is self.nav and event.type() == QEvent.Type.Resize:
            self._sync_nav_width()
        return super().eventFilter(obj, event)

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

        self.status_label = BodyLabel(tr("就绪"), self)
        self.status_label.setMinimumWidth(160)

        self.progress = ProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.pause_btn = PushButton(tr("暂停"), self, FluentIcon.PAUSE)
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._on_pause_resume)

        self.stop_btn = PushButton(tr("停止"), self, FluentIcon.CLOSE)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)

        self.clear_btn = PushButton(tr("清空日志"), self, FluentIcon.DELETE)
        self.clear_btn.clicked.connect(lambda: self.log_view.clear())

        self.export_btn = PushButton(tr("导出日志"), self, FluentIcon.SAVE)
        self.export_btn.clicked.connect(self._export_log)

        # 日志区折叠 / 最大化：把竖向空间让给上面的表单
        self.log_collapse_btn = TransparentToolButton(FluentIcon.DOWN, self)
        self.log_collapse_btn.clicked.connect(self._toggle_log_collapsed)
        self.log_max_btn = TransparentToolButton(FluentIcon.FULL_SCREEN, self)
        self.log_max_btn.clicked.connect(self._toggle_log_maximized)

        top.addWidget(self.status_label)
        top.addWidget(self.progress, 1)
        top.addWidget(self.pause_btn)
        top.addWidget(self.stop_btn)
        top.addWidget(self.clear_btn)
        top.addWidget(self.export_btn)
        top.addWidget(self.log_collapse_btn)
        top.addWidget(self.log_max_btn)
        v.addLayout(top)

        self.log_view = TextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText(tr("操作日志会显示在这里…"))
        v.addWidget(self.log_view, 1)

        return panel

    # ─────────────────── 日志区折叠 / 最大化 ───────────────────
    def _toggle_log_collapsed(self):
        self._set_log_mode("normal" if self._log_mode == "collapsed" else "collapsed")

    def _toggle_log_maximized(self):
        self._set_log_mode("normal" if self._log_mode == "maximized" else "maximized")

    def _set_log_mode(self, mode: str):
        """mode: collapsed / normal / maximized。"""
        self._log_mode = mode
        self.log_view.setVisible(mode != "collapsed")

        total = self.splitter.height() or (self.height() - 40)
        if mode == "collapsed":
            bar_h = self.bottom_panel.minimumSizeHint().height()
            self.splitter.setSizes([max(total - bar_h, 1), bar_h])
        elif mode == "maximized":
            self.splitter.setSizes([max(int(total * 0.12), 80), int(total * 0.88)])
        else:
            self.splitter.setSizes([int(total * 0.72), max(int(total * 0.28), 160)])

        collapsed = mode == "collapsed"
        self.log_collapse_btn.setIcon(FluentIcon.UP if collapsed else FluentIcon.DOWN)
        self.log_collapse_btn.setToolTip(tr("展开日志") if collapsed else tr("折叠日志"))
        maximized = mode == "maximized"
        self.log_max_btn.setIcon(FluentIcon.MINIMIZE if maximized else FluentIcon.FULL_SCREEN)
        self.log_max_btn.setToolTip(tr("还原日志") if maximized else tr("最大化日志"))
        self.log_max_btn.setEnabled(not collapsed)

    # ─────────────────── 注册 Tab ───────────────────
    def _register_tabs(self):
        """在此集中注册所有 Tab。后续迁移只需往这里 append。"""
        tabs: list[BaseTab] = [
            MergeTab(self),
            ConcatTab(self),
            SubtitleConcatTab(self),
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

        # 功能页与「语言 / 设置 / 关于」之间用横线分隔，避免中间一大段空白
        self.nav.addSeparator(position=NavigationItemPosition.BOTTOM)

        other = "en" if i18n.current() == "zh" else "zh"
        self.nav.addItem(
            routeKey="language",
            icon=FluentIcon.LANGUAGE,
            text=i18n.LANGUAGE_NAMES[other],
            onClick=self._toggle_language,
            position=NavigationItemPosition.BOTTOM,
            selectable=False,
        )
        self.nav.addItem(
            routeKey="settings",
            icon=FluentIcon.SETTING,
            text=tr("全局设置"),
            onClick=self._open_settings,
            position=NavigationItemPosition.BOTTOM,
            selectable=False,
        )
        self.nav.addItem(
            routeKey="about",
            icon=FluentIcon.INFO,
            text=tr("关于"),
            onClick=self._show_about,
            position=NavigationItemPosition.BOTTOM,
            selectable=False,
        )

        self._sync_nav_width()
        self._set_log_mode(self._log_mode)

        if self.stack.count() > 0:
            first_tab = self.stack.widget(0)
            self.stack.setCurrentIndex(0)
            if isinstance(first_tab, BaseTab):
                self.nav.setCurrentItem(first_tab.NAME)

    def _add_tab(self, tab: BaseTab):
        self.stack.addWidget(tab)
        self.nav.addItem(
            routeKey=tab.NAME,
            icon=tab.ICON,
            text=tr(tab.TITLE),
            onClick=lambda *_, t=tab: self.stack.setCurrentWidget(t),
        )

    def _toggle_language(self, *_):
        """中英文切换：保存设置后重建主窗口，表单内容 / 当前页 / 日志均保留。"""
        if self.current_worker and self.current_worker.isRunning():
            InfoBar.warning(
                tr("有任务进行中"), tr("请等待当前任务结束后再切换语言。"),
                parent=self, position=InfoBarPosition.TOP,
            )
            return
        new_lang = "en" if i18n.current() == "zh" else "zh"
        self.settings.language = new_lang
        try:
            self.settings.save(settings_path())
        except Exception as e:
            self.log(tr("[设置] 保存失败: {0}").format(e))

        # 先在旧语言下取快照，再切语言重建
        states = {
            t.NAME: t.capture_state()
            for t in (self.stack.widget(i) for i in range(self.stack.count()))
            if isinstance(t, BaseTab)
        }
        current_index = self.stack.currentIndex()
        i18n.set_language(new_lang)

        win = MainWindow()
        win.setGeometry(self.geometry())
        win.log_view.setHtml(self.log_view.toHtml())
        win._set_log_mode(self._log_mode)
        for i in range(win.stack.count()):
            tab = win.stack.widget(i)
            if isinstance(tab, BaseTab) and tab.NAME in states:
                tab.restore_state(states[tab.NAME])
        if 0 <= current_index < win.stack.count():
            win.stack.setCurrentIndex(current_index)
            restored = win.stack.widget(current_index)
            if isinstance(restored, BaseTab):
                win.nav.setCurrentItem(restored.NAME)
        win.show()
        MainWindow._instance = win   # 持有引用，防止被回收
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.close()

    def _open_settings(self, *_):
        from qt.settings_window import SettingsDialog
        SettingsDialog(self).exec()

    def _show_about(self, *_):
        InfoBar.info(
            f"{tr(APP_NAME)} {VERSION}", tr("基于 FFmpeg 的批量视频混剪工具（MIT 开源）"),
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
                tr("提示"), tr("操作日志为空，无需导出。"),
                parent=self, position=InfoBarPosition.TOP,
            )
            return
        folder = QFileDialog.getExistingDirectory(self, tr("选择日志导出文件夹"))
        if not folder:
            return
        name = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{VERSION}.log"
        path = os.path.join(folder, name)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.log(tr("[日志] 已导出到：{0}").format(path))
        except Exception as e:
            InfoBar.error(
                tr("导出失败"), str(e),
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
        self.pause_btn.setText(tr("暂停"))
        self.stop_btn.setEnabled(True)
        if trigger_btn is not None:
            trigger_btn.setEnabled(False)
        self.set_status(tr("启动中…"))
        worker.start()

    def _on_worker_finished(self, success: bool, summary: str):
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        if self._trigger_btn is not None:
            self._trigger_btn.setEnabled(True)
        self.set_status(tr("完成") if success else tr("结束（含失败）"))

        out_dir = ""
        if self.current_worker:
            out_dir = self.current_worker.output_dir or ""

        has_dir = out_dir and os.path.isdir(out_dir)

        if success:
            bar = InfoBar.new(
                InfoBarIcon.SUCCESS, tr("处理完成"), summary,
                Qt.Orientation.Horizontal,
                isClosable=True, parent=self,
                position=InfoBarPosition.TOP, duration=8000,
            )
        else:
            bar = InfoBar.new(
                InfoBarIcon.WARNING, tr("处理结束"), summary,
                Qt.Orientation.Horizontal,
                isClosable=True, parent=self,
                position=InfoBarPosition.TOP, duration=8000,
            )

        if has_dir:
            open_btn = PushButton(tr("打开文件夹"), bar, FluentIcon.FOLDER)
            open_btn.setFixedHeight(30)
            open_btn.clicked.connect(
                lambda *_, d=out_dir: os.startfile(d)  # noqa: S606
            )
            bar.addWidget(open_btn)

        self.current_worker = None

    def _on_pause_resume(self):
        if not self.current_worker:
            return
        self.ctrl.paused = not self.ctrl.paused
        self.pause_btn.setText(tr("继续") if self.ctrl.paused else tr("暂停"))
        self.set_status(tr("已暂停") if self.ctrl.paused else tr("运行中"))

    def _on_stop(self):
        if not self.current_worker:
            return
        self.ctrl.stopped = True
        self.ctrl.paused = False
        self.set_status(tr("正在停止…"))

    def closeEvent(self, event):
        if self.current_worker and self.current_worker.isRunning():
            self.ctrl.stopped = True
            self.current_worker.wait(3000)
        super().closeEvent(event)
