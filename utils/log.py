"""
统一日志模块。

用法:
    from utils.log import get_logger
    logger = get_logger(__name__)

日志写入:
  1. stdout (开发用)   — INFO 及以上
  2. logs/agent_YYYYMMDD_HHMMSS.log (每次运行新建)   — INFO 及以上
"""
import logging
import logging.handlers
import os
import sys
import datetime
import atexit

# 存储所有 handlers 用于退出时 flush
_all_handlers = []

# 注册退出时 flush
def _flush_handlers():
    for handler in _all_handlers:
        handler.flush()
        if hasattr(handler, 'close'):
            handler.close()

atexit.register(_flush_handlers)

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "agent.log")
_LOG_LEVEL = logging.INFO

# 自定义格式化器：支持 extra 字段显示
class ExtraFieldsFormatter(logging.Formatter):
    """格式化器：在日志末尾追加 extra 字段（如果存在）"""
    def format(self, record):
        extra_str = ""
        # 标准字段列表（这些是logging内置字段，不属于extra）
        std_fields = {
            'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
            'module', 'lineno', 'funcName', 'created', 'asctime', 'msecs',
            'relativeCreated', 'thread', 'threadName', 'processName', 'process',
            'getMessage', 'message', 'extra_fields',
            'exc_info', 'exc_text', 'stack_info', 'exc'
        }
        for key, val in record.__dict__.items():
            if key not in std_fields and key not in ('', 'message'):
                extra_str += f" {key}={val}"
        record.extra_fields = extra_str.strip()
        return super().format(record)


# 格式化器（统一风格）- 支持 extra 字段显示
_STDOUT_FMT = ExtraFieldsFormatter(
    "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s %(extra_fields)s",
    datefmt="%H:%M:%S",
)
_FILE_FMT = ExtraFieldsFormatter(
    "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s %(extra_fields)s",
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
    stdout.flush = lambda: stdout.stream.flush()  # 确保 flush 可用
    _all_handlers.append(stdout)
    logger.addHandler(stdout)

    # 2) 文件 handler（每次运行新建文件）
    os.makedirs(_LOG_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(_LOG_DIR, f"agent_{timestamp}.log")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(_LOG_LEVEL)
    fh.setFormatter(_FILE_FMT)
    fh.flush = lambda: fh.stream.flush()  # 确保 flush 可用
    _all_handlers.append(fh)
    logger.addHandler(fh)

    _initialized.add(name)
    return logger