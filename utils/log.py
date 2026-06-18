"""
统一日志模块。

用法:
    from utils.log import get_logger
    logger = get_logger(__name__)

日志写入:
  1. stdout (开发用，有颜色)   — INFO 及以上
  2. logs/agent.log (生产用)   — INFO 及以上，按日轮转保留 7 天
"""
import logging
import logging.handlers
import os
import sys

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "agent.log")
_LOG_LEVEL = logging.INFO

# 格式化器（统一风格）
_STDOUT_FMT = logging.Formatter(
    "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
_FILE_FMT = logging.Formatter(
    "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_initialized = set()  # 已配置过 logger name 集合


def get_logger(name: str) -> logging.Logger:
    """返回带 stdout + 文件 handlers 的 Logger（全局唯一）。"""
    logger = logging.getLogger(name)

    if name in _initialized:
        return logger

    logger.setLevel(_LOG_LEVEL)
    logger.propagate = False  # 防止重复输出到 root logger

    # 1) stdout handler
    stdout = logging.StreamHandler(sys.stdout)
    stdout.setLevel(_LOG_LEVEL)
    stdout.setFormatter(_STDOUT_FMT)
    logger.addHandler(stdout)

    # 2) 文件 handler（按日轮转，保留 7 天）
    os.makedirs(_LOG_DIR, exist_ok=True)
    fh = logging.handlers.TimedRotatingFileHandler(
        _LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    fh.setLevel(_LOG_LEVEL)
    fh.setFormatter(_FILE_FMT)
    logger.addHandler(fh)

    _initialized.add(name)
    return logger