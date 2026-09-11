"""授权验证对话框 + 启动前检查（委托给 _license_core.pyd）。

使用独立 QDialog（非 MessageBoxBase）——因为调用时主窗口尚未 show()，
内嵌遮罩型对话框无法正常渲染。
"""
from __future__ import annotations

from qt.core.i18n import tr

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QVBoxLayout

from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
)

from qt.core.paths import resource_path

try:
    import _license_core  # type: ignore
except ImportError:
    _license_core = None  # 开发环境未编译 .pyd 时允许降级


class LicenseDialog(QDialog):
    """首次启动的授权验证对话框（独立窗口）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.authorized = False
        self._machine_id = _license_core.get_machine_id() if _license_core else "DEV-MODE"

        self.setWindowTitle(tr("软件授权验证"))
        self.setMinimumWidth(480)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.CustomizeWindowHint
        )
        icon_path = resource_path(os.path.join("assets", "logo.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        title = StrongBodyLabel(tr("软件授权验证"), self)
        title.setStyleSheet("font-size:15px;font-weight:bold;")
        layout.addWidget(title)

        tip = BodyLabel(
            tr("首次使用需要授权码，请将下方机器码发送给管理员获取。"),
            self,
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        layout.addWidget(BodyLabel(tr("本机机器码:"), self))
        self.mid_edit = LineEdit(self)
        self.mid_edit.setText(self._machine_id)
        self.mid_edit.setReadOnly(True)
        layout.addWidget(self.mid_edit)

        copy_btn = PushButton(tr("复制机器码"), self, FluentIcon.COPY)
        copy_btn.clicked.connect(self._copy_mid)
        layout.addWidget(copy_btn)

        layout.addWidget(BodyLabel(tr("授权码:"), self))
        self.code_edit = LineEdit(self)
        self.code_edit.setPlaceholderText(tr("在此粘贴授权码"))
        self.code_edit.setClearButtonEnabled(True)
        layout.addWidget(self.code_edit)

        self.tip_label = BodyLabel("", self)
        layout.addWidget(self.tip_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()
        verify_btn = PrimaryPushButton(tr("验证授权"), self)
        verify_btn.clicked.connect(self._verify)
        btn_row.addWidget(verify_btn)
        cancel_btn = PushButton(tr("退出"), self)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _copy_mid(self):
        QApplication.clipboard().setText(self._machine_id)
        self.tip_label.setText(tr("✅ 机器码已复制到剪贴板"))
        self.tip_label.setStyleSheet("color: #107c10;")

    def _verify(self):
        code = self.code_edit.text().strip()
        if not code:
            self.tip_label.setText(tr("请输入授权码"))
            self.tip_label.setStyleSheet("color: #c42b1c;")
            return
        if _license_core is None:
            self.tip_label.setText(tr("本机未编译 _license_core.pyd，开发模式跳过验证"))
            self.tip_label.setStyleSheet("color: #8a8a8a;")
            self.authorized = True
            self.accept()
            return
        ok, msg = _license_core.verify_auth_code(code)
        if ok:
            _license_core.save_license(code)
            self.authorized = True
            self.tip_label.setText(msg)
            self.tip_label.setStyleSheet("color: #107c10;")
            self.accept()
        else:
            self.tip_label.setText(msg)
            self.tip_label.setStyleSheet("color: #c42b1c;")


def check_license(parent=None) -> bool:
    """已有有效授权直接放行；否则弹窗验证。"""
    if _license_core is None:
        return True  # 开发模式兜底
    saved = _license_core.load_license()
    if saved:
        ok, _ = _license_core.verify_auth_code(saved)
        if ok:
            return True
    dlg = LicenseDialog(parent)
    dlg.exec()
    return dlg.authorized
