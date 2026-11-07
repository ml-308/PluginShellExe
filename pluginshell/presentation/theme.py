"""界面外观：只用 Qt 原生字体与调色板，不使用样式表（避免任何 Web/CSS 形态）。

同时负责按系统的 DPI 缩放给出合理的尺寸常量。
"""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget

TITLE_POINT_SIZE = 22
NAV_MAX_WIDTH = 210
CONTENT_MARGIN = 12
CONTENT_SPACING = 12


def apply_theme(app: QApplication) -> None:
    font = QFont(app.font())
    if font.pointSize() <= 0:
        font.setPointSize(10)
    app.setFont(font)


def make_title(widget: QWidget, text: str) -> object:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    label = QLabel(text, widget)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    font = label.font()
    font.setPointSize(TITLE_POINT_SIZE)
    font.setBold(True)
    label.setFont(font)
    return label
