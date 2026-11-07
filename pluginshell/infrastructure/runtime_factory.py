"""插件运行时装配：把内核当成一个可替换的"驱动"注入应用层。

应用层只依赖 PluginService 接口，不认识 Kernel 的实现细节；将来若把插件运行时
换成独立进程或另一种实现，只需要改这里。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .paths import AppPaths

STATE_FILE_NAME = ".exe-state.json"


def create_kernel(paths: AppPaths, plugins_dir: Path, log_sink=None) -> Any:
    from kernel import Kernel

    return Kernel(
        plugins_dir=plugins_dir,
        project_root=paths.resource_root,
        state_path=plugins_dir / STATE_FILE_NAME,
        log_sink=log_sink,
    )
