"""极简依赖容器：只做"注册工厂 / 取实例"，够用且零依赖。

不引入第三方 DI 框架，避免为一个桌面小应用增加打包体积与启动开销。
"""
from __future__ import annotations

from typing import Any, Callable


class Container:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[["Container"], Any]] = {}
        self._singletons: dict[str, Any] = {}
        self._is_singleton: dict[str, bool] = {}

    def register(
        self, key: str, factory: Callable[["Container"], Any] | Any, singleton: bool = False
    ) -> None:
        if callable(factory):
            self._factories[key] = factory
        else:
            self._singletons[key] = factory
            self._is_singleton[key] = True
        self._is_singleton.setdefault(key, singleton)

    def resolve(self, key: str) -> Any:
        if key in self._singletons:
            return self._singletons[key]
        factory = self._factories.get(key)
        if factory is None:
            raise KeyError(f"未注册的依赖: {key}")
        instance = factory(self)
        if self._is_singleton.get(key):
            self._singletons[key] = instance
        return instance

    def __contains__(self, key: str) -> bool:
        return key in self._factories or key in self._singletons
