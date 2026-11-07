"""插件管理对话框：列出 / 安装 / 启用 / 禁用 / 卸载，按分类筛选。

所有操作都走 PluginService，结果统一为 OperationResult，异常不会冒到界面。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

ALL_CATEGORIES = "__all__"


class PluginManagerDialog(QDialog):
    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("插件管理")
        self.resize(940, 620)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"插件目录：{service.plugins_dir}", self))

        top = QHBoxLayout()
        top.addWidget(QLabel("分类筛选："))
        self._filter = QComboBox(self)
        self._filter.currentIndexChanged.connect(lambda _: self._refresh())
        top.addWidget(self._filter, 1)
        refresh_button = QPushButton("刷新", self)
        refresh_button.clicked.connect(self._refresh)
        top.addWidget(refresh_button)
        layout.addLayout(top)

        self._table = QTableWidget(0, 6, self)
        self._table.setHorizontalHeaderLabels(
            ["插件 ID", "名称", "分类", "版本", "状态", "依赖 / 说明"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table, 3)

        buttons = QHBoxLayout()
        actions = (
            ("安装文件夹…", self._install),
            ("启用", self._enable),
            ("禁用", self._disable),
            ("卸载", self._uninstall),
            ("关闭", self.accept),
        )
        for text, slot in actions:
            button = QPushButton(text, self)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        layout.addWidget(QLabel("运行时日志（依赖缺失、加载失败、回滚记录）：", self))
        self._log = QPlainTextEdit(self)
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(300)
        layout.addWidget(self._log, 1)

        self._refresh()

    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        current = self._filter.currentData() or ALL_CATEGORIES
        categories = self.service.categories(enabled_only=False)

        self._filter.blockSignals(True)
        self._filter.clear()
        self._filter.addItem("全部分类", ALL_CATEGORIES)
        for category in categories:
            self._filter.addItem(f"{category.label} ({category.id})", category.id)
        index = self._filter.findData(current)
        self._filter.setCurrentIndex(index if index >= 0 else 0)
        self._filter.blockSignals(False)

        selected = self._filter.currentData() or ALL_CATEGORIES
        plugins = self.service.list_plugins()
        self._table.setRowCount(0)
        for plugin in plugins:
            if selected != ALL_CATEGORIES and plugin.category_id != selected:
                continue
            row = self._table.rowCount()
            self._table.insertRow(row)
            detail = plugin.message or plugin.description or plugin.dependency_text
            values = [
                plugin.id,
                plugin.name,
                f"{plugin.category_label} [{plugin.category_id}]",
                plugin.version,
                plugin.state.label,
                f"{plugin.dependency_text} · {detail}",
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, plugin.id)
                self._table.setItem(row, column, item)
        self._table.resizeColumnsToContents()
        self._log.setPlainText("\n".join(self.service.logs(120)))

    def _selected_id(self) -> str | None:
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在列表中选择一个插件")
            return None
        item = self._table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _report(self, result) -> None:
        if result is not None and not result.ok:
            QMessageBox.warning(self, "插件操作未成功", result.message)
        self._refresh()

    # ------------------------------------------------------------------
    def _install(self) -> None:
        start = str(self.service.plugins_dir.parent)
        directory = QFileDialog.getExistingDirectory(
            self, "选择插件文件夹（必须含 manifest.json）", start
        )
        if directory:
            self._report(self.service.install(Path(directory)))

    def _enable(self) -> None:
        plugin_id = self._selected_id()
        if plugin_id:
            self._report(self.service.enable(plugin_id))

    def _disable(self) -> None:
        plugin_id = self._selected_id()
        if plugin_id:
            self._report(self.service.disable(plugin_id))

    def _uninstall(self) -> None:
        plugin_id = self._selected_id()
        if not plugin_id:
            return
        answer = QMessageBox.question(
            self,
            "确认卸载",
            f"确定卸载插件 {plugin_id} 吗？其目录与全部运行时副作用都会被清理。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._report(self.service.uninstall(plugin_id))
