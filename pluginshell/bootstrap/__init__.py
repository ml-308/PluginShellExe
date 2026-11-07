"""组合根：解析命令行、加载配置、初始化日志、装配依赖、启动应用。

这是唯一允许"知道所有层"的地方；其余模块只依赖自己的下层。
"""
from .application import Application, main

__all__ = ["Application", "main"]
