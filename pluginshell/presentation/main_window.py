"""主窗口：空状态、分类导航、main.content 渲染。

只调用 PluginService 的用例与 DTO，不 import kernel、不读 manifest。
"""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, update_check
from ..domain.models import ContributionView
from .about_dialog import AboutDialog
from .plugin_manager_dialog import PluginManagerDialog
from .theme import CONTENT_MARGIN, CONTENT_SPACING, NAV_MAX_WIDTH, make_title

ALL_CATEGORIES = "__all__"


class MainWindow(QMainWindow):
    def __init__(self, service, plugins_source: str = "", config=None):
        super().__init__()
        self.service = service
        self.plugins_source = plugins_source
        self._active_category = ALL_CATEGORIES
        self._pending = False

        self.setWindowTitle(f"{APP_NAME} · 单文件插件宿主")
        if config is not None:
            self.resize(config.window_width, config.window_height)
        else:
            self.resize(1000, 680)

        central = QWidget(self)
        root_layout = QHBoxLayout(central)

        self._nav = QListWidget(central)
        self._nav.setMaximumWidth(NAV_MAX_WIDTH)
        self._nav.currentItemChanged.connect(self._on_category_changed)
        root_layout.addWidget(self._nav)

        self._host = QWidget(central)
        self._host_layout = QVBoxLayout(self._host)
        self._host_layout.setContentsMargins(
            CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN
        )
        self._host_layout.setSpacing(CONTENT_SPACING)
        scroll = QScrollArea(central)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._host)
        root_layout.addWidget(scroll, 1)
        self.setCentralWidget(central)

        toolbar = self.addToolBar("主机")
        for text, slot in (
            ("插件管理…", self._open_manager),
            ("刷新", self._render),
            ("打开插件目录", self._open_plugins_dir),
            ("检查更新…", self._check_update),
            ("关于", self._open_about),
        ):
            action = QAction(text, self)
            action.triggered.connect(slot)
            toolbar.addAction(action)

        self.statusBar().showMessage("就绪")
        self._kernel_token = service.on_changed(self._schedule_render)
        self._content_token = service.on_content_changed(self._schedule_render)
        self._render()

    # ------------------------------------------------------------------
    def _rebuild_navigation(self) -> None:
        categories = self.service.categories(enabled_only=True)
        total = self.service.counts()["contributions"]

        self._nav.blockSignals(True)
        self._nav.clear()
        all_item = QListWidgetItem(f"全部  ({total})")
        all_item.setData(Qt.ItemDataRole.UserRole, ALL_CATEGORIES)
        self._nav.addItem(all_item)
        for category in categories:
            item = QListWidgetItem(f"{category.label}  ({category.count})")
            item.setData(Qt.ItemDataRole.UserRole, category.id)
            self._nav.addItem(item)

        target_row = 0
        if self._active_category != ALL_CATEGORIES:
            for row in range(self._nav.count()):
                if self._nav.item(row).data(Qt.ItemDataRole.UserRole) == self._active_category:
                    target_row = row
                    break
            else:
                self._active_category = ALL_CATEGORIES
        self._nav.setCurrentRow(target_row)
        self._nav.blockSignals(False)

    def _check_update(self) -> None:
        update_check.check_now(self)

    def _on_category_changed(self, current, _previous) -> None:
        if current is None:
            return
        self._active_category = current.data(Qt.ItemDataRole.UserRole) or ALL_CATEGORIES
        self._render_content()

    # ------------------------------------------------------------------
    def _schedule_render(self) -> None:
        if self._pending:
            return
        self._pending = True
        QTimer.singleShot(0, self._deferred_render)

    def _deferred_render(self) -> None:
        self._pending = False
        self._render()

    def _render(self) -> None:
        self._rebuild_navigation()
        self._render_content()

    def _clear_host(self) -> None:
        while self._host_layout.count():
            item = self._host_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _empty_state(self) -> QWidget:
        widget = QWidget(self._host)
        layout = QVBoxLayout(widget)

        hint = QLabel("当前宿主没有任何业务内容；所有内容都必须由插件提供。", widget)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail = QLabel(f"插件目录：{self.service.plugins_dir}", widget)
        detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail.setWordWrap(True)
        button = QPushButton("打开插件管理…", widget)
        button.setMaximumWidth(220)
        button.clicked.connect(self._open_manager)

        layout.addStretch(1)
        layout.addWidget(make_title(widget, "请安装插件"))
        layout.addSpacing(10)
        layout.addWidget(hint)
        layout.addSpacing(6)
        layout.addWidget(detail)
        layout.addSpacing(18)
        layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return widget

    def _render_content(self) -> None:
        self._clear_host()
        category = None if self._active_category == ALL_CATEGORIES else self._active_category
        contributions = self.service.contributions(category)

        if not self.service.contributions(None):
            self._host_layout.addWidget(self._empty_state())
            self.statusBar().showMessage(f"空壳状态 · 插件目录 {self.service.plugins_dir}")
            return

        if not contributions:
            label = QLabel("该分类暂无内容", self._host)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._host_layout.addWidget(label)
        else:
            for contribution in contributions:
                self._host_layout.addWidget(self._build_panel(contribution))

        self._host_layout.addStretch(1)
        counts = self.service.counts()
        self.statusBar().showMessage(
            f"已安装 {counts['installed']} · 已启用 {counts['enabled']} · "
            f"分类 {counts['categories']} · 当前显示 {len(contributions)}/"
            f"{counts['contributions']} 个内容贡献 · 插件目录 {self.service.plugins_dir}"
        )

    def _build_panel(self, contribution: ContributionView) -> QWidget:
        box = QGroupBox(contribution.title, self._host)
        layout = QVBoxLayout(box)
        try:
            widget = contribution.create_widget(box)
            if widget is None:
                raise RuntimeError("内容工厂未返回 QWidget")
            layout.addWidget(widget)
        except Exception as exc:  # noqa: BLE001 - 单个插件渲染失败不能拖垮宿主
            layout.addWidget(QLabel(f"[插件内容渲染失败，已隔离] {exc!r}", box))
        return box

    # ------------------------------------------------------------------
    def _open_manager(self) -> None:
        PluginManagerDialog(self.service, self).exec()
        self._schedule_render()

    def _open_about(self) -> None:
        AboutDialog(self.service, self.plugins_source, self).exec()

    def _open_plugins_dir(self) -> None:
        directory = self.service.plugins_dir
        directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def closeEvent(self, event) -> None:
        self.service.off_changed(self._kernel_token)
        self.service.off_content_changed(self._content_token)
        event.accept()
