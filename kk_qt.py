"""kk-mix Qt 版本入口（PySide6 + PySide6-Fluent-Widgets）。

运行：uv run python kk_qt.py
代码按功能模块拆分在 qt/ 目录下，结构说明见 README.md / AGENTS.md。
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from qfluentwidgets import Theme, setTheme

from qt.core.license import check_license
from qt.main_window import MainWindow


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    setTheme(Theme.AUTO)

    window = MainWindow()

    # parent=None 使授权对话框作为独立顶层窗口，在任务栏显示图标
    if not check_license():
        sys.exit(0)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
