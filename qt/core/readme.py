"""首次启动「使用前必看」对话框。

规则（与 Tkinter 版保持一致）：
  ① 阅读时间 ≥ READ_SECONDS 秒
  ② 滚动文本到最底部（yScrollBar 到达 ≥98%）
两个条件同时满足后，「确认」按钮才变为可点击。
确认后写标志文件，之后启动不再弹出。
"""
from __future__ import annotations

import os

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QPlainTextEdit,
    QScrollBar, QSizePolicy, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, PrimaryPushButton, PushButton, StrongBodyLabel, TextEdit,
    isDarkTheme,
)

from qt.core.paths import resource_path

# 标志文件（与 kk.py 原版一致，同路径）
_README_FLAG = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "vek", ".vek_readme_read"
)
READ_SECONDS = 10


def check_readme(parent: QWidget | None = None) -> bool:
    """若未读过则弹出对话框，返回 False 表示用户选择退出程序。"""
    if os.path.exists(_README_FLAG):
        return True

    readme_path = resource_path(os.path.join("docs", "使用前必看.txt"))
    try:
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return True  # 文件缺失则直接跳过

    dlg = ReadmeDialog(content, parent)
    result = dlg.exec()

    if result == QDialog.DialogCode.Accepted:
        os.makedirs(os.path.dirname(_README_FLAG), exist_ok=True)
        try:
            open(_README_FLAG, "w").close()
        except Exception:
            pass
        return True
    return False


class ReadmeDialog(QDialog):
    """阅读协议对话框：倒计时 + 滚动到底部，双条件满足才可确认。"""

    def __init__(self, content: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("使用前必看 — 请仔细阅读后方可使用")
        self.setMinimumSize(580, 480)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.MSWindowsFixedSizeDialogHint
            | Qt.WindowType.CustomizeWindowHint
        )
        icon_path = resource_path(os.path.join("assets", "logo.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._time_ok = False
        self._scroll_ok = False
        self._seconds_left = READ_SECONDS
        self._confirmed = False

        self._build_ui(content)
        self._start_countdown()

    # ─────────────────────────────────────────── UI ───────────────────────────
    def _build_ui(self, content: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = StrongBodyLabel("使用前必看", self)
        title.setStyleSheet("font-size:15px;font-weight:bold;")
        layout.addWidget(title)

        hint = BodyLabel(
            "请完整阅读以下内容，满足以下两个条件后方可进入使用：\n"
            "① 阅读时间不少于 10 秒    ② 滚动文本到最底部",
            self,
        )
        hint.setStyleSheet("color:#e67e00;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 文本区
        self._text = TextEdit(self)
        self._text.setReadOnly(True)
        self._text.setPlainText(content)
        self._text.setMinimumHeight(260)
        self._text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._text)

        # 监听滚动
        self._text.verticalScrollBar().valueChanged.connect(self._on_scroll)

        # 状态标签
        self._status = BodyLabel(f"⏳ 请阅读内容，还需等待 {READ_SECONDS} 秒…", self)
        self._status.setStyleSheet("color:#c0392b;")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        # 按钮行
        self._btn_confirm = PrimaryPushButton("✓  我已阅读，进入使用", self)
        self._btn_confirm.setEnabled(False)
        self._btn_confirm.clicked.connect(self._on_confirm)

        btn_quit = PushButton("退  出", self)
        btn_quit.clicked.connect(self.reject)

        from PySide6.QtWidgets import QHBoxLayout
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_confirm)
        btn_row.addWidget(btn_quit)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    # ─────────────────────────────────────────── 逻辑 ─────────────────────────
    def _start_countdown(self) -> None:
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _tick(self) -> None:
        if self._seconds_left > 0:
            self._seconds_left -= 1
            self._update_hint()
        else:
            self._timer.stop()
            self._time_ok = True
            self._check_enable()
            if not self._scroll_ok:
                self._status.setText("⬇ 计时完成！请继续滚动文本到最底部")
                self._status.setStyleSheet("color:#e67e00;")

    def _on_scroll(self, _value: int = 0) -> None:
        if self._scroll_ok:
            return
        bar: QScrollBar = self._text.verticalScrollBar()
        if bar.maximum() == 0:
            # 内容不足以滚动，直接视为已到底
            self._scroll_ok = True
        else:
            ratio = bar.value() / bar.maximum()
            if ratio >= 0.98:
                self._scroll_ok = True
        if self._scroll_ok:
            self._check_enable()
            if not (self._time_ok and self._scroll_ok):
                self._update_hint()

    def _check_enable(self) -> None:
        if self._time_ok and self._scroll_ok:
            self._btn_confirm.setEnabled(True)
            self._status.setText("✅ 条件已满足，点击「我已阅读，进入使用」继续")
            self._status.setStyleSheet("color:green;")

    def _update_hint(self) -> None:
        if self._time_ok and self._scroll_ok:
            return
        parts: list[str] = []
        if not self._time_ok:
            parts.append(f"还需等待 {self._seconds_left} 秒")
        if not self._scroll_ok:
            parts.append("⬇ 请继续向下滚动文本到底部")
        self._status.setText("⏳ " + "，".join(parts) + "…")
        self._status.setStyleSheet("color:#c0392b;")

    def _on_confirm(self) -> None:
        self._timer.stop()
        self.accept()

    def closeEvent(self, event):  # noqa: N802
        # 禁止直接关闭窗口（必须点「退出」或「我已阅读」）
        event.ignore()
