"""命令行参数。窗口版与控制台版共用同一套参数。"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

from .. import APP_NAME, APP_VERSION, PROTOCOL_API


@dataclass(frozen=True)
class CommandLine:
    plugins: str | None = None
    install: tuple[str, ...] = ()
    check: bool = False
    report: str | None = None
    no_gui_check: bool = False
    verbose: bool = False
    version: bool = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description=(
            f"{APP_NAME} {APP_VERSION} —— 单文件插件宿主，"
            f"兼容 PluginShell 插件协议 {PROTOCOL_API}（原生 Qt，无 Web 技术）"
        ),
    )
    parser.add_argument("--plugins", metavar="DIR", help="覆盖插件目录")
    parser.add_argument(
        "--install", metavar="DIR", action="append", default=[], help="启动/自检前安装插件文件夹，可重复"
    )
    parser.add_argument("--check", action="store_true", help="无界面自检并写报告后退出")
    parser.add_argument("--report", metavar="FILE", help="自检报告输出路径")
    parser.add_argument("--no-gui-check", action="store_true", help="自检时跳过离屏 GUI 探测")
    parser.add_argument("--verbose", action="store_true", help="输出 DEBUG 级日志")
    parser.add_argument("--version", action="store_true", help="打印版本后退出")
    return parser


def parse(argv: list[str]) -> CommandLine:
    namespace = build_parser().parse_args(argv)
    return CommandLine(
        plugins=namespace.plugins,
        install=tuple(namespace.install or ()),
        check=namespace.check,
        report=namespace.report,
        no_gui_check=namespace.no_gui_check,
        verbose=namespace.verbose,
        version=namespace.version,
    )
