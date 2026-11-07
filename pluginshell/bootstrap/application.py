"""组合根 + 启动编排。

启动顺序（每一步失败都有明确的退出码与用户可见提示）：
    命令行 → 路径 → 配置 → 日志/崩溃钩子 → 单实例 → 插件目录 → 内核 → 用例服务
    → 安装指定插件 → 自检模式 或 GUI 模式
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from .. import APP_NAME, APP_VERSION, ORG_NAME, PROTOCOL_API
from ..application.plugin_service import PluginService
from ..application.self_check import SelfCheckService
from ..domain.errors import ConfigError
from ..infrastructure.config import AppConfig
from ..infrastructure.logging_setup import configure_logging
from ..infrastructure.paths import AppPaths, is_frozen
from ..infrastructure.runtime_factory import create_kernel
from ..infrastructure.single_instance import SingleInstance
from .cli import CommandLine, parse
from .container import Container

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_CONFIG_ERROR = 2
EXIT_PLUGIN_FAILED = 3
EXIT_QT_UNAVAILABLE = 4


def emit(*parts: Any) -> None:
    """窗口版没有 stdout，输出必须可安全丢弃。"""
    if sys.stdout is None:
        return
    try:
        print(*parts, flush=True)
    except Exception:  # noqa: BLE001
        pass


def probe_qt() -> dict[str, Any]:
    try:
        import PySide6

        return {"ok": True, "version": PySide6.__version__}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "version": None, "error": repr(exc)}


class Application:
    def __init__(self, argv: list[str] | None = None):
        self._argv = list(sys.argv[1:] if argv is None else argv)
        self._container = Container()
        self._paths: AppPaths | None = None
        self._service: PluginService | None = None
        self._guard: SingleInstance | None = None
        self._logger: Any = None
        self._source = ""

    # ------------------------------------------------------------------
    def run(self) -> int:
        try:
            command = parse(self._argv)
        except SystemExit as exc:  # --help / 参数错误
            return int(exc.code or 0)

        if command.version:
            emit(f"{APP_NAME} {APP_VERSION} (protocol {PROTOCOL_API})")
            return EXIT_OK

        self._paths = AppPaths.discover()
        self._paths.ensure_writable_dirs()

        try:
            config = AppConfig.load(self._paths)
        except ConfigError as exc:
            self._fatal("配置错误", str(exc))
            return EXIT_CONFIG_ERROR

        level = "DEBUG" if command.verbose else config.log_level
        self._logger = configure_logging(self._paths.logs_dir, level)
        self._install_crash_handler()

        try:
            return self._start(command, config)
        except Exception:  # noqa: BLE001 - 顶层兜底，写日志并给用户一个对话框
            detail = traceback.format_exc()
            self._logger.exception("启动失败")
            self._fatal("启动失败", detail[-1200:])
            return EXIT_RUNTIME_ERROR

    # ------------------------------------------------------------------
    def _start(self, command: CommandLine, config: AppConfig) -> int:
        self._logger.info(
            "%s %s 启动 (frozen=%s, python=%s)",
            APP_NAME, APP_VERSION, is_frozen(), sys.version.split()[0],
        )

        if config.single_instance:
            self._guard = SingleInstance(f"{APP_NAME}.instance", self._paths.data_dir)
            if not self._guard.acquire():
                self._logger.info("已有实例在运行，本次退出")
                self._notify_running()
                return EXIT_OK

        plugins_dir, source = self._paths.resolve_plugins_dir(
            command.plugins or config.plugins_dir
        )
        self._source = source
        self._logger.info("插件目录 %s（%s）", plugins_dir, source)

        kernel = create_kernel(self._paths, plugins_dir, log_sink=self._logger.debug)
        service = PluginService(
            kernel, auto_adopt=config.auto_adopt, logger=self._logger.getChild("plugins")
            if hasattr(self._logger, "getChild") else self._logger
        )
        service.boot()
        self._service = service
        self._logger.info("已启用 %d / 已安装 %d", len(kernel.enabled), len(kernel.records))

        for folder in command.install:
            result = service.install(folder)
            self._logger.info("安装 %s -> ok=%s %s", folder, result.ok, result.message)

        if command.check:
            return self._run_check(command)
        return self._run_gui(config)

    # ------------------------------------------------------------------
    def _run_check(self, command: CommandLine) -> int:
        qt = probe_qt()
        gui = {"ok": None, "skipped": True} if command.no_gui_check else self._probe_gui()
        report = SelfCheckService(self._service).build(
            plugins_source=self._source, qt=qt, gui=gui
        )
        destination = (
            Path(command.report)
            if command.report
            else self._paths.data_dir / "last-check.json"
        )
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            emit("报告写入失败:", exc)
            self._shutdown()
            return EXIT_CONFIG_ERROR

        emit(f"{APP_NAME} {APP_VERSION}  protocol={PROTOCOL_API}  frozen={report.frozen}")
        emit(f"插件目录: {report.plugins_dir}  ({report.plugins_source})")
        emit(
            f"已安装 {report.installed} / 已启用 {len(report.enabled)} / "
            f"内容贡献 {len(report.contributions)}"
        )
        emit(f"分类: {[item['id'] for item in report.categories]}")
        emit(f"Qt {report.qt.get('version')}  GUI ok={report.gui.get('ok')}  "
             f"groupboxes={report.gui.get('groupboxes')}")
        emit(f"报告: {destination}")

        self._shutdown()
        if report.failed:
            emit("失败插件:", report.failed)
            return EXIT_PLUGIN_FAILED
        if not report.qt.get("ok") or report.gui.get("ok") is False:
            return EXIT_QT_UNAVAILABLE
        return EXIT_OK

    def _probe_gui(self) -> dict[str, Any]:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication, QGroupBox, QLabel

            from ..presentation.main_window import MainWindow

            app = QApplication.instance() or QApplication([])
            window = MainWindow(self._service, plugins_source=self._source)
            window.show()
            app.processEvents()
            result = {
                "ok": True,
                "groupboxes": len(window.findChildren(QGroupBox)),
                "empty_state_visible": any(
                    "请安装插件" in label.text() for label in window.findChildren(QLabel)
                ),
                "status": window.statusBar().currentMessage(),
            }
            window.close()
            app.processEvents()
            return result
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": repr(exc), "traceback": traceback.format_exc(limit=6)}

    def _run_gui(self, config: AppConfig) -> int:
        from PySide6.QtWidgets import QApplication

        from ..presentation.main_window import MainWindow

        app = QApplication(sys.argv[:1])
        app.setApplicationName(APP_NAME)
        app.setApplicationVersion(APP_VERSION)
        app.setOrganizationName(ORG_NAME)

        window = MainWindow(self._service, plugins_source=self._source, config=config)
        window.show()
        try:
            return app.exec()
        finally:
            self._shutdown()

    # ------------------------------------------------------------------
    def _shutdown(self) -> None:
        if self._service is not None:
            try:
                self._service.shutdown()
            except Exception:  # noqa: BLE001
                self._logger.exception("关闭插件运行时失败")
            self._service = None
        if self._guard is not None:
            self._guard.release()
            self._guard = None

    def _install_crash_handler(self) -> None:
        logs_dir = self._paths.logs_dir

        def hook(exc_type, exc, tb) -> None:
            try:
                logs_dir.mkdir(parents=True, exist_ok=True)
                (logs_dir / "crash.log").write_text(
                    "".join(traceback.format_exception(exc_type, exc, tb)), encoding="utf-8"
                )
            except Exception:  # noqa: BLE001
                pass
            sys.__excepthook__(exc_type, exc, tb)

        sys.excepthook = hook

    def _fatal(self, title: str, message: str) -> None:
        emit(f"[{title}] {message}")
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance() or QApplication([])
            QMessageBox.critical(None, title, message)
            del app
        except Exception:  # noqa: BLE001
            pass

    def _notify_running(self) -> None:
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance() or QApplication([])
            QMessageBox.information(
                None, APP_NAME, f"{APP_NAME} 已经在运行，请切换到已打开的窗口。"
            )
            del app
        except Exception:  # noqa: BLE001
            pass


def main(argv: list[str] | None = None) -> int:
    return Application(argv).run()
