"""领域模型：跨越层边界的只读 DTO。

表现层只认这些类型，不直接接触内核的 Manifest / Contribution / KernelError，
因此 UI 可以被替换（改成 WinForms/C++/命令行）而应用层与领域层无需改动。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class PluginState(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    FAILED = "failed"

    @property
    def label(self) -> str:
        return {"enabled": "已启用", "disabled": "已禁用", "failed": "加载失败"}[self.value]


@dataclass(frozen=True)
class CategoryView:
    id: str
    label: str
    order: int = 100
    count: int = 0


@dataclass(frozen=True)
class PluginView:
    id: str
    name: str
    version: str
    state: PluginState
    category_id: str
    category_label: str
    description: str = ""
    message: str = ""
    dependencies: dict[str, str] = field(default_factory=dict)
    requires_services: tuple[str, ...] = ()

    @property
    def dependency_text(self) -> str:
        if not self.dependencies:
            return "—"
        return ", ".join(f"{key} ({value})" for key, value in self.dependencies.items())


@dataclass(frozen=True)
class ContributionView:
    id: str
    title: str
    owner: str
    category_id: str
    order: int
    factory: Callable[[Any], Any]

    def create_widget(self, parent: Any) -> Any:
        return self.factory(parent)


@dataclass(frozen=True)
class OperationResult:
    ok: bool
    message: str = ""


@dataclass
class SelfCheckReport:
    app: str
    version: str
    protocol: str
    frozen: bool
    python: str
    executable: str
    plugins_dir: str
    plugins_source: str
    installed: int
    enabled: list[str]
    contributions: list[dict[str, Any]]
    categories: list[dict[str, Any]]
    services: list[str]
    failed: list[str]
    qt: dict[str, Any]
    gui: dict[str, Any]
    logs: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return bool(self.qt.get("ok")) and self.gui.get("ok") is not False and not self.failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "app": self.app,
            "version": self.version,
            "protocol": self.protocol,
            "frozen": self.frozen,
            "python": self.python,
            "executable": self.executable,
            "plugins_dir": self.plugins_dir,
            "plugins_source": self.plugins_source,
            "installed": self.installed,
            "enabled": self.enabled,
            "contributions": self.contributions,
            "categories": self.categories,
            "services": self.services,
            "failed": self.failed,
            "qt": self.qt,
            "gui": self.gui,
            "logs": self.logs,
        }
