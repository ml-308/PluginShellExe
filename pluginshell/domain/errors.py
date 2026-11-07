"""应用级错误（与插件运行时的 kernel.errors 区分：这里是 App 自身的错误）。"""
from __future__ import annotations


class AppError(Exception):
    """应用层错误的基类。"""


class ConfigError(AppError):
    """配置文件缺失、格式错误或取值非法。"""


class StartupError(AppError):
    """启动阶段失败（单实例、运行时装配等）。"""
