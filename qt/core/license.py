"""授权验证对话框 + 启动前检查（委托给 _license_core.pyd）。"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBoxBase,
    PushButton,
    SubtitleLabel,
)

try:
    import _license_core  # type: ignore
except ImportError:
    _license_core = None  # 开发环境未编译 .pyd 时允许降级


class LicenseDialog(MessageBoxBase):
    """首次启动的授权验证对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.authorized = False
        self._machine_id = _license_core.get_machine_id() if _license_core else "DEV-MODE"

        self.titleLabel = SubtitleLabel("软件授权验证", self)
        tip = BodyLabel(
            "首次使用需要授权码，请将下方机器码发送给管理员获取。",
            self,
        )

        self.mid_edit = LineEdit(self)
        self.mid_edit.setText(self._machine_id)
        self.mid_edit.setReadOnly(True)

        copy_btn = PushButton("复制机器码", self, FluentIcon.COPY)
        copy_btn.clicked.connect(self._copy_mid)

        self.code_edit = LineEdit(self)
        self.code_edit.setPlaceholderText("在此粘贴授权码")
        self.code_edit.setClearButtonEnabled(True)

        self.tip_label = BodyLabel("", self)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(tip)
        self.viewLayout.addWidget(BodyLabel("本机机器码:", self))
        self.viewLayout.addWidget(self.mid_edit)
        self.viewLayout.addWidget(copy_btn)
        self.viewLayout.addWidget(BodyLabel("授权码:", self))
        self.viewLayout.addWidget(self.code_edit)
        self.viewLayout.addWidget(self.tip_label)

        self.yesButton.setText("验证授权")
        self.cancelButton.setText("退出")
        self.widget.setMinimumWidth(460)

        self.yesButton.clicked.disconnect()
        self.yesButton.clicked.connect(self._verify)

    def _copy_mid(self):
        QApplication.clipboard().setText(self._machine_id)
        InfoBar.success(
            "已复制", "机器码已复制到剪贴板", parent=self,
            position=InfoBarPosition.TOP,
        )

    def _verify(self):
        code = self.code_edit.text().strip()
        if not code:
            self.tip_label.setText("请输入授权码")
            self.tip_label.setStyleSheet("color: #c42b1c;")
            return
        if _license_core is None:
            self.tip_label.setText("本机未编译 _license_core.pyd，开发模式跳过验证")
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


def check_license(parent) -> bool:
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
