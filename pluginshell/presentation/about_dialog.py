"""关于对话框：版本、协议、运行形态、路径与许可。"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from .. import APP_NAME, APP_VERSION, PROTOCOL_API


class AboutDialog(QDialog):
    def __init__(self, service, plugins_source: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"关于 {APP_NAME}")
        self.resize(560, 360)

        layout = QVBoxLayout(self)
        heading = QLabel(f"{APP_NAME}  {APP_VERSION}", self)
        font = heading.font()
        font.setPointSize(16)
        font.setBold(True)
        heading.setFont(font)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)

        subtitle = QLabel("原生插件宿主 · 无 Web 技术 · MIT License", self)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        form = QFormLayout()
        form.addRow("插件协议", QLabel(PROTOCOL_API, self))
        form.addRow("运行形态", QLabel("单文件 exe（PyInstaller）" if getattr(sys, "frozen", False) else "源码模式", self))
        form.addRow("Python", QLabel(sys.version.split()[0], self))
        form.addRow("插件目录", QLabel(str(service.plugins_dir), self))
        form.addRow("目录来源", QLabel(plugins_source or "—", self))
        counts = service.counts()
        form.addRow(
            "插件统计",
            QLabel(
                f"已安装 {counts['installed']} · 已启用 {counts['enabled']} · "
                f"内容贡献 {counts['contributions']}",
                self,
            ),
        )
        layout.addLayout(form)
        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
