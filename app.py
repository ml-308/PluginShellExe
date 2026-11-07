"""应用入口（极薄）：确保包可导入，然后把控制权交给组合根。

真正的装配逻辑在 pluginshell/bootstrap/application.py，
这里不写任何业务、不碰 Qt、不解析参数。
"""
from __future__ import annotations

import sys
from pathlib import Path


def _ensure_import_path() -> None:
    """源码模式下把项目根加入 sys.path；冻结模式由 PyInstaller 负责。"""
    if getattr(sys, "frozen", False):
        return
    root = str(Path(__file__).resolve().parent)
    if root not in sys.path:
        sys.path.insert(0, root)


def main(argv: list[str] | None = None) -> int:
    _ensure_import_path()
    from pluginshell.bootstrap import main as bootstrap_main

    return bootstrap_main(argv)


if __name__ == "__main__":
    sys.exit(main())
