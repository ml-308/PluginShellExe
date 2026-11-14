"""PluginShellExe 应用包。

分层（依赖方向严格单向，上层依赖下层，下层不认识上层）：

    bootstrap/       组合根：解析参数 → 单实例 → 配置 → 日志 → 装配 → 启动
    presentation/    表现层：PySide6 视图，只消费 application 的 DTO，不碰内核
    application/     应用层：用例编排（安装/启用/禁用/卸载/自检），不依赖 Qt
    domain/          领域层：纯数据模型与错误，无 IO、无 UI、无框架
    infrastructure/  基础设施：路径、配置、日志、单实例、运行时驱动
    kernel/ + sdk/   插件运行时与插件契约（Py 插件必须由 CPython 承载）
"""
APP_NAME = "PluginShellExe"
APP_VERSION = "1.2.0"
PROTOCOL_API = "1.0"
ORG_NAME = "ml-308"

__version__ = APP_VERSION
