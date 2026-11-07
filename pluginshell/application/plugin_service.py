"""插件用例服务：表现层唯一的入口。

职责：
* 把内核的异常（KernelError）统一翻译成 OperationResult，UI 不需要 try/except；
* 把内核对象转换成领域 DTO，UI 不认识 Manifest / Contribution / Kernel；
* 承载"宿主策略"：首次运行自动采用目录中的插件。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from ..domain.models import (
    CategoryView,
    ContributionView,
    OperationResult,
    PluginState,
    PluginView,
)

_STATE_MAP = {
    "enabled": PluginState.ENABLED,
    "disabled": PluginState.DISABLED,
    "failed": PluginState.FAILED,
}


class PluginService:
    def __init__(self, kernel: Any, auto_adopt: bool = True, logger: logging.Logger | None = None):
        self._kernel = kernel
        self._auto_adopt = auto_adopt
        self._log = logger or logging.getLogger("pluginshell.application")
        self._booted = False

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def boot(self) -> None:
        state_path = getattr(self._kernel, "state_path", None)
        had_state = bool(state_path and state_path.exists())
        self._kernel.bootstrap()
        if self._auto_adopt and not had_state and self._kernel.records and not self._kernel.enabled:
            for plugin_id in sorted(self._kernel.records):
                try:
                    self._kernel.enable(plugin_id)
                except Exception as exc:  # noqa: BLE001 - 单个插件失败不影响其余
                    self._log.warning("自动启用 %s 失败（已隔离）: %s", plugin_id, exc)
            self._log.info("首次采用插件目录：已启用 %d 个插件", len(self._kernel.enabled))
        self._booted = True

    def shutdown(self) -> None:
        if self._booted:
            self._kernel.shutdown()
            self._booted = False

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    @property
    def plugins_dir(self) -> Path:
        return Path(self._kernel.plugins_dir)

    def counts(self) -> dict[str, int]:
        return {
            "installed": len(self._kernel.records),
            "enabled": len(self._kernel.enabled),
            "contributions": len(self._kernel.extensions.contributions("main.content")),
            "categories": len(self._kernel.categories(enabled_only=True)),
        }

    def list_plugins(self) -> list[PluginView]:
        views: list[PluginView] = []
        for plugin_id, record in sorted(self._kernel.records.items()):
            manifest = record.manifest
            views.append(
                PluginView(
                    id=plugin_id,
                    name=manifest.name,
                    version=manifest.version,
                    state=_STATE_MAP.get(record.state, PluginState.DISABLED),
                    category_id=manifest.category.id,
                    category_label=manifest.category.label,
                    description=manifest.description,
                    message=record.message,
                    dependencies=dict(manifest.dependencies),
                    requires_services=tuple(manifest.requires_services),
                )
            )
        return views

    def categories(self, enabled_only: bool = True) -> list[CategoryView]:
        contributions = self._kernel.extensions.contributions("main.content")
        counts: dict[str, int] = {}
        for item in contributions:
            counts[self._category_of(item)] = counts.get(self._category_of(item), 0) + 1
        return [
            CategoryView(
                id=category.id,
                label=category.label,
                order=category.order,
                count=counts.get(category.id, 0),
            )
            for category in self._kernel.categories(enabled_only=enabled_only)
        ]

    def contributions(self, category_id: str | None = None) -> list[ContributionView]:
        views: list[ContributionView] = []
        for item in self._kernel.extensions.contributions("main.content"):
            category = self._category_of(item)
            if category_id and category != category_id:
                continue
            payload = item.payload
            factory = payload.get("factory")
            if not callable(factory):
                continue
            views.append(
                ContributionView(
                    id=str(payload.get("id") or item.token),
                    title=str(payload.get("title") or item.owner),
                    owner=item.owner,
                    category_id=category,
                    order=int(payload.get("order", 100)),
                    factory=factory,
                )
            )
        views.sort(key=lambda view: (view.order, view.id))
        return views

    def logs(self, limit: int = 200) -> list[str]:
        return list(self._kernel.logs[-limit:])

    def snapshot(self) -> dict:
        """诊断快照（供自检与问题排查）。"""
        return self._kernel.describe()

    def on_changed(self, callback: Callable[[], None]) -> str:
        return self._kernel.on_changed(callback)

    def off_changed(self, token: str) -> bool:
        return self._kernel.off_changed(token)

    def on_content_changed(self, callback: Callable[[], None]) -> str:
        """扩展点内容变化（插件运行期动态贡献/撤回）时触发。"""
        return self._kernel.extensions.on_changed(callback)

    def off_content_changed(self, token: str) -> bool:
        return self._kernel.extensions.off_changed(token)

    # ------------------------------------------------------------------
    # 命令
    # ------------------------------------------------------------------
    def install(self, folder: str | Path) -> OperationResult:
        return self._guard(lambda: self._kernel.install(Path(folder)), f"安装 {folder}")

    def enable(self, plugin_id: str) -> OperationResult:
        return self._guard(lambda: self._kernel.enable(plugin_id), f"启用 {plugin_id}")

    def disable(self, plugin_id: str) -> OperationResult:
        return self._guard(lambda: self._kernel.disable(plugin_id), f"禁用 {plugin_id}")

    def uninstall(self, plugin_id: str) -> OperationResult:
        return self._guard(lambda: self._kernel.uninstall(plugin_id), f"卸载 {plugin_id}")

    # ------------------------------------------------------------------
    def _category_of(self, contribution) -> str:
        declared = contribution.payload.get("category")
        if declared:
            return str(declared)
        record = self._kernel.records.get(contribution.owner)
        return record.manifest.category.id if record else "general"

    def _guard(self, action: Callable[[], Any], label: str) -> OperationResult:
        from kernel.errors import KernelError

        try:
            result = action()
            if isinstance(result, OperationResult):
                return result
            ok = bool(getattr(result, "ok", True))
            message = str(getattr(result, "message", "") or "")
            if not ok:
                self._log.warning("%s -> %s", label, message)
            return OperationResult(ok=ok, message=message)
        except KernelError as exc:
            self._log.warning("%s 被拒绝: %s", label, exc)
            return OperationResult(ok=False, message=str(exc))
        except Exception as exc:  # noqa: BLE001 - 用例层兜底，绝不让异常穿透到 UI
            self._log.exception("%s 异常（已隔离）", label)
            return OperationResult(ok=False, message=f"操作异常（已隔离）: {exc!r}")
