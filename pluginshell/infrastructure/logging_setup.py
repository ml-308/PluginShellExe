"""日志：滚动文件 + （有控制台时）标准输出。

窗口版 exe 没有 stdout，因此 StreamHandler 只在 stdout 可用时挂载，
不会出现 "NoneType has no attribute write" 之类的启动崩溃。
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "pluginshell"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging(logs_dir: Path, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if logger.handlers:
        return logger

    formatter = logging.Formatter(_FORMAT)

    # 文件日志是"锦上添花"：目录不可写时绝不能把应用带崩（只读安装位置、
    # 受限沙箱、企业终端都常见）。这种情况下退化为仅标准输出。
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            logs_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as exc:
        if sys.stdout is not None:
            print(f"[logging] 日志目录不可写，仅输出到控制台: {exc}", file=sys.stdout)

    if sys.stdout is not None:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def get_logger(suffix: str = "") -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{suffix}" if suffix else LOGGER_NAME)
