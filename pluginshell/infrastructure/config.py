"""应用配置：内置默认 → 用户配置文件 → 环境变量，后者覆盖前者。

配置文件全部是 JSON，缺字段用默认值，字段类型错误直接报 ConfigError（不做静默兜底，
避免用户以为配置生效了其实没有）。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from ..domain.errors import ConfigError


@dataclass
class AppConfig:
    plugins_dir: str | None = None
    auto_adopt: bool = True
    single_instance: bool = True
    log_level: str = "INFO"
    window_width: int = 1000
    window_height: int = 680

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, paths) -> "AppConfig":
        merged: dict = {}
        for source in (paths.bundled_config, paths.user_config):
            merged.update(_read_json(source))
        env_plugins = os.environ.get("PLUGINSHELL_PLUGINS")
        if env_plugins:
            merged["plugins_dir"] = env_plugins
        env_level = os.environ.get("PLUGINSHELL_LOG_LEVEL")
        if env_level:
            merged["log_level"] = env_level
        return cls.from_mapping(merged)

    @classmethod
    def from_mapping(cls, raw: dict) -> "AppConfig":
        if not isinstance(raw, dict):
            raise ConfigError("配置根节点必须是 JSON 对象")
        allowed = {item.name: item.type for item in fields(cls)}
        values: dict = {}
        for key, value in raw.items():
            if key not in allowed:
                continue  # 未知字段忽略，保证向前兼容
            if key == "plugins_dir":
                if value is not None and not isinstance(value, str):
                    raise ConfigError("plugins_dir 必须是字符串或 null")
            elif key == "log_level":
                if not isinstance(value, str):
                    raise ConfigError("log_level 必须是字符串")
                value = value.upper()
                if value not in ("DEBUG", "INFO", "WARNING", "ERROR"):
                    raise ConfigError(f"log_level 取值非法: {value}")
            elif key in ("auto_adopt", "single_instance"):
                if not isinstance(value, bool):
                    raise ConfigError(f"{key} 必须是布尔值")
            elif key in ("window_width", "window_height"):
                if not isinstance(value, int) or isinstance(value, bool) or value < 320:
                    raise ConfigError(f"{key} 必须是不小于 320 的整数")
            values[key] = value
        return cls(**values)

    def to_dict(self) -> dict:
        return asdict(self)


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ConfigError(f"配置文件不是合法 JSON: {path} ({exc})") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件根节点必须是对象: {path}")
    return data
