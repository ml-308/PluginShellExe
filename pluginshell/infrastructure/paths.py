"""应用路径：区分「只读资源」「exe 所在目录」「用户数据目录」。

同时负责插件目录的解析策略（这是宿主策略，不属于插件运行时）。
"""
from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .. import APP_NAME


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _is_writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


@dataclass(frozen=True)
class AppPaths:
    resource_root: Path  # 只读资源根（onefile 下为 _MEIPASS）
    exe_dir: Path  # 用户可见目录
    data_dir: Path  # %LOCALAPPDATA%\PluginShellExe

    @classmethod
    def discover(cls) -> "AppPaths":
        bundled = getattr(sys, "_MEIPASS", None)
        resource_root = Path(bundled) if bundled else Path(__file__).resolve().parents[2]
        exe_dir = (
            Path(sys.executable).resolve().parent if is_frozen() else Path(__file__).resolve().parents[2]
        )

        # 数据目录优先级：显式覆盖 > %LOCALAPPDATA% > 可回退位置
        override = os.environ.get("PLUGINSHELL_DATA_DIR")
        if override:
            candidates = [Path(override).expanduser().resolve()]
        else:
            raw = os.environ.get("LOCALAPPDATA")
            candidates = [(Path(raw) if raw else Path.home() / "AppData" / "Local") / APP_NAME]
        candidates += [exe_dir / "data", Path(tempfile.gettempdir()) / APP_NAME]

        data_dir = candidates[0]
        for candidate in candidates:
            if _is_writable(candidate):
                data_dir = candidate
                break
        return cls(resource_root=resource_root, exe_dir=exe_dir, data_dir=data_dir)

    # ------------------------------------------------------------------
    @property
    def bundled_config(self) -> Path:
        return self.resource_root / "config" / "default.json"

    @property
    def user_config(self) -> Path:
        return self.data_dir / "config.json"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def py_shell_plugins(self) -> Path:
        raw = os.environ.get("LOCALAPPDATA")
        base = Path(raw) if raw else Path.home() / "AppData" / "Local"
        return base / "PluginShell" / "plugins"

    def ensure_writable_dirs(self) -> None:
        for directory in (self.data_dir, self.logs_dir):
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass  # 只读环境下降级：日志与报告各自兜底，不让启动失败

    # ------------------------------------------------------------------
    @staticmethod
    def _has_plugins(directory: Path) -> bool:
        if not directory.is_dir():
            return False
        try:
            return any(
                child.is_dir() and (child / "manifest.json").is_file()
                for child in directory.iterdir()
            )
        except OSError:
            return False

    def resolve_plugins_dir(self, override: str | None) -> tuple[Path, str]:
        """--plugins > 环境变量 > exe 同级(有插件) > py 版目录(有插件) > 默认。"""
        if override:
            return Path(override).expanduser().resolve(), "--plugins 参数"
        env = os.environ.get("PLUGINSHELL_PLUGINS")
        if env:
            return Path(env).expanduser().resolve(), "环境变量 PLUGINSHELL_PLUGINS"

        side = self.exe_dir / "plugins"
        if self._has_plugins(side):
            return side, "exe 同级 plugins/"
        if self._has_plugins(self.py_shell_plugins):
            return self.py_shell_plugins, "复用 PluginShell(py 版)插件目录"
        try:
            side.mkdir(parents=True, exist_ok=True)
            return side, "exe 同级 plugins/（默认）"
        except OSError:
            fallback = self.data_dir / "plugins"
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback, "%LOCALAPPDATA%\\PluginShellExe\\plugins"
