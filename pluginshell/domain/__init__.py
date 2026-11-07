"""领域层：纯数据模型与错误定义，不依赖 Qt、不依赖文件系统。"""
from .errors import AppError, ConfigError, StartupError
from .models import (
    CategoryView,
    ContributionView,
    OperationResult,
    PluginState,
    PluginView,
    SelfCheckReport,
)

__all__ = [
    "AppError",
    "ConfigError",
    "StartupError",
    "CategoryView",
    "ContributionView",
    "OperationResult",
    "PluginState",
    "PluginView",
    "SelfCheckReport",
]
