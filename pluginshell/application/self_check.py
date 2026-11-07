"""自检用例：汇总内核状态、Qt 与离屏 GUI 探测结果，产出可序列化报告。

GUI 探测由调用方（bootstrap）注入，避免应用层依赖 Qt。
"""
from __future__ import annotations

import sys
from typing import Any

from .. import APP_NAME, APP_VERSION, PROTOCOL_API
from ..domain.models import SelfCheckReport
from .plugin_service import PluginService


class SelfCheckService:
    def __init__(self, service: PluginService):
        self._service = service

    def build(
        self,
        *,
        plugins_source: str,
        qt: dict[str, Any],
        gui: dict[str, Any],
    ) -> SelfCheckReport:
        snapshot = self._service.snapshot()
        return SelfCheckReport(
            app=APP_NAME,
            version=APP_VERSION,
            protocol=PROTOCOL_API,
            frozen=bool(getattr(sys, "frozen", False)),
            python=sys.version.split()[0],
            executable=str(sys.executable),
            plugins_dir=snapshot["plugins_dir"],
            plugins_source=plugins_source,
            installed=snapshot["installed"],
            enabled=snapshot["enabled"],
            contributions=snapshot["contributions"],
            categories=snapshot["categories"],
            services=snapshot["services"],
            failed=snapshot["failed"],
            qt=qt,
            gui=gui,
            logs=snapshot["logs"],
        )
