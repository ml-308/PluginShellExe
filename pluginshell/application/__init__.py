"""应用层：用例编排。不 import Qt，可被 CLI / 测试 / 将来的其它 UI 复用。"""
from .plugin_service import PluginService
from .self_check import SelfCheckService

__all__ = ["PluginService", "SelfCheckService"]
