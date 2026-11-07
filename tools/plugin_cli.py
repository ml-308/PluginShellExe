"""无 GUI 的插件管理命令（走应用层用例，与 GUI 完全同一套逻辑）。

    python tools/plugin_cli.py path
    python tools/plugin_cli.py list [--category lab]
    python tools/plugin_cli.py install <插件文件夹>
    python tools/plugin_cli.py enable|disable|uninstall <插件ID>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from pluginshell import APP_NAME, APP_VERSION, PROTOCOL_API  # noqa: E402
from pluginshell.application.plugin_service import PluginService  # noqa: E402
from pluginshell.infrastructure.config import AppConfig  # noqa: E402
from pluginshell.infrastructure.paths import AppPaths  # noqa: E402
from pluginshell.infrastructure.runtime_factory import create_kernel  # noqa: E402


def build_service(plugins: str | None) -> tuple[PluginService, Path, str]:
    paths = AppPaths.discover()
    config = AppConfig.load(paths)
    directory, source = paths.resolve_plugins_dir(plugins or config.plugins_dir)
    kernel = create_kernel(paths, directory)
    service = PluginService(kernel, auto_adopt=config.auto_adopt)
    service.boot()
    return service, directory, source


def print_list(service: PluginService, directory: Path, source: str, category: str | None) -> None:
    print(f"{APP_NAME} {APP_VERSION}  protocol={PROTOCOL_API}")
    print(f"插件目录: {directory}  ({source})")
    plugins = [
        item for item in service.list_plugins() if not category or item.category_id == category
    ]
    counts = service.counts()
    print(
        f"已安装 {counts['installed']} / 已启用 {counts['enabled']}"
        + (f" / 分类筛选 {category}" if category else "")
    )
    print("-" * 96)
    for item in plugins:
        print(
            f"{item.id:<38} v{item.version:<8} [{item.category_label}/{item.category_id}] "
            f"{item.state.label:<8} 依赖={list(item.dependencies) or '—'}"
        )
        if item.message:
            print(f"    ! {item.message}")
    print("-" * 96)
    categories = service.categories(enabled_only=False)
    print("分类:", ", ".join(f"{c.label}({c.id})" for c in categories) or "（无）")
    print("内容贡献:", counts["contributions"])
    print("已注册服务:", ", ".join(service.snapshot()["services"]) or "（无）")


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} 插件管理命令")
    parser.add_argument("--plugins", metavar="DIR", help="覆盖插件目录")
    sub = parser.add_subparsers(dest="command", required=True)
    list_parser = sub.add_parser("list", help="列出插件与状态")
    list_parser.add_argument("--category", help="按分类 ID 筛选")
    install_parser = sub.add_parser("install", help="安装文件夹形式的插件")
    install_parser.add_argument("path")
    for name in ("enable", "disable", "uninstall"):
        sub.add_parser(name, help=f"{name} 插件").add_argument("plugin_id")
    sub.add_parser("path", help="打印插件目录与来源")

    args = parser.parse_args()
    service, directory, source = build_service(args.plugins)
    try:
        if args.command == "path":
            print(directory)
            print(f"来源: {source}")
            return 0
        if args.command == "list":
            print_list(service, directory, source, args.category)
            return 0
        if args.command == "install":
            result = service.install(Path(args.path))
        elif args.command == "enable":
            result = service.enable(args.plugin_id)
        elif args.command == "disable":
            result = service.disable(args.plugin_id)
        else:
            result = service.uninstall(args.plugin_id)
        print(("OK: " if result.ok else "ERROR: ") + result.message)
        return 0 if result.ok else 1
    finally:
        service.shutdown()


if __name__ == "__main__":
    sys.exit(main())
