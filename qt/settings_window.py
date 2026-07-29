"""全局设置窗口。对应原 settings_window.py 的功能。

用法：
    from qt.settings_window import SettingsDialog
    dlg = SettingsDialog(main_window)
    dlg.exec()
"""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
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
    InfoBar,
    InfoBarPosition,
    MessageBoxBase,
    PushButton,
    SpinBox,
    StrongBodyLabel,
    SubtitleLabel,
)

try:
    import _license_core  # type: ignore
except ImportError:
    _license_core = None

from qt.core.app_settings import AppSettings
from qt.core.paths import settings_path


def _section(title: str, parent: QWidget) -> tuple[CardWidget, QGridLayout]:
    """创建一张卡片，并返回内部 GridLayout。"""
    card = CardWidget(parent)
    root = QVBoxLayout(card)
    root.setContentsMargins(18, 14, 18, 16)
    root.setSpacing(8)

    header = StrongBodyLabel(title, card)
    root.addWidget(header)

    grid_holder = QWidget(card)
    grid = QGridLayout(grid_holder)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(8)
    root.addWidget(grid_holder)

    return card, grid


class SettingsDialog(MessageBoxBase):
    """Qt 版全局设置对话框。"""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main = main_window
        self.settings: AppSettings = main_window.settings

        # 标题
        self.title_label = SubtitleLabel("全局设置", self)

        # 所有卡片放进 ScrollArea 避免溢出
        body = QFrame(self)
        body_v = QVBoxLayout(body)
        body_v.setContentsMargins(0, 0, 0, 0)
        body_v.setSpacing(12)

        self._build_debug_card(body_v)
        self._build_perf_card(body_v)
        self._build_license_card(body_v)

        self.viewLayout.addWidget(self.title_label)
        self.viewLayout.addWidget(body)

        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")
        self.widget.setMinimumWidth(560)
        self.widget.setMaximumWidth(640)

        self.yesButton.clicked.disconnect()
        self.yesButton.clicked.connect(self._on_save)

        self._refresh_bitrate_state()

    # ─── 各 section ───
    def _build_debug_card(self, layout: QVBoxLayout):
        card, g = _section("调试选项", self)
        self.verbose_log = CheckBox("打印详细日志", card)
        self.verbose_log.setChecked(self.settings.verbose_log)
        g.addWidget(self.verbose_log, 0, 0)
        layout.addWidget(card)

    def _build_perf_card(self, layout: QVBoxLayout):
        card, g = _section("性能与稳定性", self)

        g.addWidget(BodyLabel("并行线程数:", card), 0, 0)
        self.thread_count = SpinBox(card)
        self.thread_count.setRange(1, 16)
        self.thread_count.setValue(self.settings.thread_count)
        g.addWidget(self.thread_count, 0, 1)
        hint = BodyLabel("同时处理文件数（建议 1-4）", card)
        hint.setStyleSheet("color: #8a8a8a;")
        g.addWidget(hint, 0, 2)

        self.speed_priority = CheckBox("极速模式（ultrafast，编码更快，清晰度略降）", card)
        self.speed_priority.setChecked(self.settings.speed_priority)
        g.addWidget(self.speed_priority, 1, 0, 1, 3)

        self.compress_video = CheckBox("启用压缩（指定码率，否则使用 CRF 23）", card)
        self.compress_video.setChecked(self.settings.compress_video)
        self.compress_video.toggled.connect(self._refresh_bitrate_state)
        g.addWidget(self.compress_video, 2, 0, 1, 3)

        bitrate_holder = QWidget(card)
        br_layout = QHBoxLayout(bitrate_holder)
        br_layout.setContentsMargins(0, 0, 0, 0)
        br_layout.setSpacing(8)
        br_layout.addWidget(BodyLabel("码率:", card))
        self.bitrate = ComboBox(card)
        self.bitrate.addItems(["1M", "2M", "3M", "5M", "8M", "10M"])
        self.bitrate.setCurrentText(self.settings.bitrate if self.settings.bitrate else "2M")
        br_layout.addWidget(self.bitrate)
        br_hint = BodyLabel("最大 50M，越大画质越好", card)
        br_hint.setStyleSheet("color: #8a8a8a;")
        br_layout.addWidget(br_hint)
        br_layout.addStretch(1)
        g.addWidget(bitrate_holder, 3, 0, 1, 3)
        self.bitrate_holder = bitrate_holder

        g.setColumnStretch(2, 1)
        layout.addWidget(card)

    def _refresh_bitrate_state(self, *_):
        enabled = self.compress_video.isChecked()
        self.bitrate.setEnabled(enabled)

    def _build_license_card(self, layout: QVBoxLayout):
        card, g = _section("授权信息", self)
        if _license_core is None:
            g.addWidget(BodyLabel("当前为开发模式（未编译 _license_core.pyd）", card), 0, 0)
            layout.addWidget(card)
            return

        try:
            mid = _license_core.get_machine_id()
        except Exception:
            mid = "N/A"

        mid_row = QWidget(card)
        mid_h = QHBoxLayout(mid_row)
        mid_h.setContentsMargins(0, 0, 0, 0)
        mid_h.setSpacing(8)
        mid_label = BodyLabel(f"本机机器码：{mid}", card)
        mid_h.addWidget(mid_label)
        copy_btn = PushButton("复制", card)
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(mid))
        mid_h.addWidget(copy_btn)
        mid_h.addStretch(1)
        g.addWidget(mid_row, 0, 0)

        try:
            saved = _license_core.load_license()
            if saved:
                ok, msg = _license_core.verify_auth_code(saved)
                if ok:
                    info = _license_core.get_license_info() or {}
                    expire_str = info.get("expire_date", "未知")
                    expire_dt = datetime.strptime(expire_str, "%Y-%m-%d %H:%M:%S")
                    days_left = (expire_dt - datetime.now()).days
                    g.addWidget(BodyLabel(f"到期时间：{expire_str}", card), 1, 0)
                    color = "#107c10" if days_left > 7 else ("#e67e00" if days_left > 0 else "#c42b1c")
                    remain_label = BodyLabel(f"剩余天数：{days_left} 天", card)
                    remain_label.setStyleSheet(f"color: {color}; font-weight: 600;")
                    g.addWidget(remain_label, 2, 0)
                else:
                    err_label = BodyLabel(f"授权状态：{msg}", card)
                    err_label.setStyleSheet("color: #c42b1c;")
                    g.addWidget(err_label, 1, 0)
            else:
                g.addWidget(BodyLabel("授权状态：未激活", card), 1, 0)
        except Exception:
            g.addWidget(BodyLabel("无法读取授权信息", card), 1, 0)

        layout.addWidget(card)

    # ─── 保存 ───
    def _on_save(self):
        self.settings.verbose_log = self.verbose_log.isChecked()
        self.settings.thread_count = self.thread_count.value()
        self.settings.speed_priority = self.speed_priority.isChecked()
        self.settings.compress_video = self.compress_video.isChecked()
        self.settings.bitrate = self.bitrate.currentText().strip().upper() or "2M"

        try:
            self.settings.save(settings_path())
            self.main.log("[设置] 已保存到 settings.json")
        except Exception as e:
            InfoBar.error("保存失败", str(e), parent=self,
                          position=InfoBarPosition.TOP)
            return

        self.accept()
