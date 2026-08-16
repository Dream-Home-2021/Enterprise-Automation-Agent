# ====================================================================
# 文件角色: 工具安全与资源限制的统一配置中心 (Centralized Tool Config)
#
# 本文件是整个 DATAGEN 项目中"工具层"的安全守门人。
# 所有工具(读写文件、执行代码、调用外部API等)在运行前，
# 都要参考这里设定的"红线"(limits)和"黑名单"(blocked_patterns)。
#
# ─── 小白导读 (给初学者的阅读指南) ───
# 1. MCP (Model Context Protocol): 一种让 AI 模型安全调用外部工具的协议。
#    类比: 就像手机 App 通过 USB 接口充电一样，MCP 是 AI 和外界的"标准接口"。
# 2. Tool (工具): Agent 可以调用的一个功能单元，比如"读文件"、"执行代码"。
#    类比: 工具就像工匠手里的锤子、螺丝刀，Agent 是工匠，Tool 是手中的家伙。
# 3. Agent (智能体): 一个能自主决策、调用工具完成任务的 AI 系统。
#    类比: Agent 就像一个有自主意识的机器人，能自己决定下一步做什么。
# 4. LLM (Large Language Model): 大语言模型，Agent 的"大脑"。
#    类比: LLM 是 Agent 的大脑，负责思考；Tools 是手脚，负责执行。
# 5. YAML: 一种配置文件格式，用缩进表示层级关系。
#    类比: 就像 Windows 的 .ini 文件，但更简洁易读。
# 6. dataclass: Python 的一种特殊类，主要用于存储数据，自动生成 __init__ 等方法。
#    类比: 就像 C 语言的结构体(struct)，但功能更强大。
# 7. Singleton (单例): 全局只有一个实例的设计模式。
#    类比: 就像一个国家只有一个总统，全局唯一。
#
# ─── 与其他文件的协作关系 ───
# - src/tools/basetool.py: 所有 Tool 的基类，会读取本文件的 TOOL_CONFIG 来校验参数
# - src/tools/factory.py: 工具工厂，创建工具实例时会注入本文件的配置
# - src/agents/*: 各 Agent 在执行任务时，通过工具间接使用本配置
# - config/tool_limits.yaml: 外部配置文件，本文件会尝试加载它覆盖默认值
# ====================================================================

from __future__ import annotations  # 启用 PEP 563: 类型注解延迟求值，让类型提示更灵活
"""Centralized configuration for tool security and resource limits.

This module provides dataclasses for tool limits and a configuration manager
that loads settings from YAML with fallback to defaults.
"""

from dataclasses import dataclass, field  # dataclass: 自动生成 __init__/__repr__ 等魔法方法; field: 自定义字段默认值
from typing import List, Optional  # 类型提示: List 表示列表, Optional 表示值可以是 None
import os  # 操作系统接口: 读取环境变量、拼接路径
import yaml  # YAML 解析库: 读取 .yaml 配置文件
from pathlib import Path  # 面向对象的路径操作 (Python 3.4+ 推荐)

from ..logger import setup_logger  # 从上级目录导入日志工具，用于记录运行日志

logger = setup_logger()  # 初始化全局 logger 实例，后续用 logger.info() 等输出日志

# ─── 默认常量 (Default Constants) ───
# 小白导读: 这些是"兜底"值，当配置文件没提供时使用这些安全值
DEFAULT_MAX_OUTPUT_CHARS = 50000  # 单次工具输出最大字符数，防止输出爆炸导致内存溢出
DEFAULT_MAX_READ_BYTES = 5 * 1024 * 1024  # 5MB: 单次读文件最大字节数，防止读取数 GB 级大文件
DEFAULT_MAX_READ_LINES = 10000  # 单次读文件最大行数，防止输出过长
DEFAULT_MAX_WRITE_BYTES = 10 * 1024 * 1024  # 10MB: 单次写文件最大字节数，防止磁盘被撑爆


@dataclass  # 小白导读: dataclass 装饰器会自动生成 __init__、__repr__、__eq__ 等方法，省去手写样板代码
class ExecutionLimits:
    """Resource limits for code execution.

    小白导读: 这个类定义了"执行代码"时的安全边界。
    类比: 就像给程序运行加上"防护栏"——超时、内存、危险代码模式都要限制。

    Attributes:
        timeout_seconds: Max execution time. None = no limit.
        max_memory_mb: Max memory usage (Linux only). None = no limit.
        max_output_chars: Truncate output if exceeds this limit.
        progress_timeout_seconds: If set, timeout resets on stdout activity.
        blocked_patterns: Code patterns to block (security).
    """

    timeout_seconds: Optional[int] = None  # 执行超时时间(秒)，None 表示不限制
    max_memory_mb: Optional[int] = None  # 最大内存使用(MB)，仅 Linux 生效，None 表示不限制
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS  # 输出字符数上限，超过则截断
    progress_timeout_seconds: Optional[int] = None  # 进度超时: 如果有输出活动则重置计时器
    blocked_patterns: List[str] = field(default_factory=lambda: [  # 小白导读: field(default_factory=...) 让每个实例拥有独立的列表，避免共享引用陷阱
        "os.system",           # 禁止直接执行系统命令 (如 os.system("rm -rf /"))
        "subprocess.call",     # 禁止 subprocess 模块的 call 方法
        "subprocess.run",      # 禁止 subprocess 模块的 run 方法
        "subprocess.Popen",   # 禁止 subprocess 模块的 Popen 方法 (最底层，最危险)
        "shutil.rmtree",       # 禁止递归删除目录 (误删后果严重)
        "eval(",               # 禁止 eval 函数 (可执行任意代码)
        "exec(",               # 禁止 exec 函数 (可执行任意代码块)
        "__import__",          # 禁止动态导入模块 (可绕过安全检查)
    ])
    # 小白导读: 假数据示例
    # blocked_patterns 的默认值是一个包含 9 个危险代码片段的列表
    # 当 Agent 生成的代码中包含这些字符串时，执行会被拦截


@dataclass
class FileOperationLimits:
    """Limits for file read/write operations.

    小白导读: 这个类定义了"文件读写"时的安全边界。
    类比: 就像图书馆的规则——只能借某些书(max_read_lines)、只能在特定区域阅读(allowed_extensions)、
         不能进禁区(blocked_paths)。

    Attributes:
        max_read_bytes: Maximum file size to read.
        max_read_lines: Maximum lines to return.
        max_write_bytes: Maximum content size to write.
        allowed_extensions: Whitelist of allowed file extensions.
        blocked_paths: Paths that cannot be accessed.
    """

    max_read_bytes: int = DEFAULT_MAX_READ_BYTES  # 最大可读字节数，默认 5MB
    max_read_lines: int = DEFAULT_MAX_READ_LINES  # 最大可读行数，默认 10000 行
    max_write_bytes: int = DEFAULT_MAX_WRITE_BYTES  # 最大可写字节数，默认 10MB
    allowed_extensions: List[str] = field(default_factory=lambda: [  # 小白导读: 文件扩展名白名单，只有在列表中的文件类型才被允许读写
        ".py", ".md", ".txt", ".csv", ".json", ".yaml", ".yml",  # 常见文本/配置文件
        ".log", ".png", ".jpg", ".jpeg", ".html", ".css", ".js"   # 日志、图片、前端文件
    ])
    blocked_paths: List[str] = field(default_factory=lambda: [  # 小白导读: 禁止访问的路径列表，防止 Agent 读取系统敏感文件
        "/etc",       # Linux 系统配置目录 (包含密码文件等)
        "/sys",       # Linux 内核参数目录
        "/proc",      # Linux 进程信息目录
        "/root",      # Linux root 用户主目录
        "~/.ssh",     # SSH 密钥目录 (包含私钥!)
        "/var/log"    # 系统日志目录
    ])
    # 小白导读: 假数据示例
    # 如果 Agent 尝试读取 "/etc/passwd"，路径以 "/etc" 开头，就会被 blocked_paths 拦截


class ToolConfig:
    """Central configuration manager for all tools.

    小白导读: 这是整个配置系统的"大管家"。
    它负责: (1) 从 YAML 文件加载配置 (2) 提供默认值兜底 (3) 全局单例访问。
    类比: 就像公司的行政部——统一管理所有规章制度，大家有需求都找它。

    Loads settings from YAML config file with fallback to defaults.
    Provides a singleton-like access pattern via the global TOOL_CONFIG.
    """

    def __init__(
        self,
        execution: Optional[ExecutionLimits] = None,  # 代码执行限制，None 则使用默认值
        file_ops: Optional[FileOperationLimits] = None,  # 文件操作限制，None 则使用默认值
        enable_security_scan: bool = True,  # 是否启用代码安全扫描
        enable_write_validation: bool = True  # 是否启用写入内容校验
    ):
        """Initialize tool configuration.

        小白导读: 构造函数，创建 ToolConfig 实例。
        使用 `or` 模式提供默认值——如果调用者没传，就用安全兜底值。

        Args:
            execution: Execution limits configuration.
            file_ops: File operation limits configuration.
            enable_security_scan: Whether to scan code for dangerous patterns.
            enable_write_validation: Whether to validate content before writing.
        """
        self.execution = execution or ExecutionLimits()  # 小白导读: `or` 模式——如果 execution 为 None/空，则创建默认 ExecutionLimits 实例
        self.file_ops = file_ops or FileOperationLimits()  # 同理，文件操作限制也有默认值
        self.enable_security_scan = enable_security_scan  # 是否扫描危险代码模式
        self.enable_write_validation = enable_write_validation  # 是否校验写入内容

    @classmethod  # 小白导读: @classmethod 表示这是类方法，第一个参数是类本身(cls)，而不是实例(self)
    def load(cls, config_path: str | Path | None = None) -> ToolConfig:
        """Load configuration from YAML file with defaults as fallback.

        小白导读: 这是最核心的类方法——从 YAML 文件加载配置。
        加载策略: 依次尝试多个路径，找到第一个存在的文件就加载。
        如果全部找不到，就用默认值兜底。

        假数据示例:
            假设 config/tool_limits.yaml 内容如下:
            ```yaml
            execution:
              timeout_seconds: 30
              max_output_chars: 10000
            file_operations:
              max_read_bytes: 2097152
            enable_security_scan: true
            ```
            则返回的 ToolConfig 实例会使用这些值覆盖默认值。

            如果文件不存在，则所有值使用默认值:
            timeout_seconds=None, max_output_chars=50000, ...

        Args:
            config_path: Path to YAML config file (relative to project root).

        Returns:
            ToolConfig instance with loaded or default settings.
        """
        if config_path is None:
            # 小白导读: 如果调用者没指定路径，从环境变量读取配置目录，默认为 "config"
            config_dir = os.getenv('CONFIG_DIRECTORY', 'config')
            config_path = os.path.join(config_dir, "tool_limits.yaml")  # 拼接成完整相对路径
        settings = {}  # 初始化空字典，准备存放解析后的配置

        # ─── 多路径查找策略 ───
        # 小白导读: 依次尝试以下路径，找到第一个存在的文件就停止
        # 这种设计让配置可以在不同位置灵活存放
        possible_paths = [
            Path(config_path),  # 路径1: 直接使用传入的路径
            Path(os.getcwd()) / config_path,  # 路径2: 相对于当前工作目录
            Path(__file__).parent.parent.parent.parent / config_path,  # 路径3: 相对于本文件向上4层(项目根目录)
        ]

        for path in possible_paths:
            if path.exists():  # 小白导读: 检查文件是否存在
                try:
                    # 小白导读: 用 yaml.safe_load 安全解析 YAML 文件 (比 yaml.load 安全，防止代码注入)
                    with open(path, 'r', encoding='utf-8') as f:  # 以 UTF-8 编码打开文件
                        settings = yaml.safe_load(f) or {}  # safe_load 返回字典; 如果文件为空则返回 None，用 {} 兜底
                    logger.info(f"Loaded tool limits from {path}")  # 记录成功日志
                    break  # 小白导读: 找到后就跳出循环，不再尝试其他路径
                except Exception as e:
                    # 小白导读: 捕获所有异常(权限错误、YAML语法错误等)，记录警告但继续尝试其他路径
                    logger.warning(f"Failed to load tool limits from {path}: {e}")

        if not settings:
            # 小白导读: 如果所有路径都没找到有效配置，记录调试日志
            logger.debug("Tool limits config not found, using defaults")

        # ─── 解析执行限制配置 ───
        # 小白导读: settings.get("execution", {}) 表示从字典中取 "execution" 键，不存在则返回空字典
        exec_settings = settings.get("execution", {})
        exec_limits = ExecutionLimits(
            timeout_seconds=exec_settings.get("timeout_seconds"),  # None 表示不限制
            max_memory_mb=exec_settings.get("max_memory_mb"),  # None 表示不限制
            max_output_chars=exec_settings.get("max_output_chars", 50000),  # 默认 50000 字符
            progress_timeout_seconds=exec_settings.get("progress_timeout_seconds"),  # None 表示不启用
            blocked_patterns=exec_settings.get("blocked_patterns", ExecutionLimits().blocked_patterns),  # 默认使用类定义的 9 个危险模式
        )

        # ─── 解析文件操作限制配置 ───
        file_settings = settings.get("file_operations", {})
        file_limits = FileOperationLimits(
            max_read_bytes=file_settings.get("max_read_bytes", 5 * 1024 * 1024),  # 默认 5MB
            max_read_lines=file_settings.get("max_read_lines", 10000),  # 默认 10000 行
            max_write_bytes=file_settings.get("max_write_bytes", 10 * 1024 * 1024),  # 默认 10MB
            allowed_extensions=file_settings.get("allowed_extensions", FileOperationLimits().allowed_extensions),  # 默认 14 种扩展名
            blocked_paths=file_settings.get("blocked_paths", FileOperationLimits().blocked_paths),  # 默认 6 个禁区路径
        )

        # 小白导读: 最终构造并返回 ToolConfig 实例
        return cls(
            execution=exec_limits,
            file_ops=file_limits,
            enable_security_scan=settings.get("enable_security_scan", True),  # 默认启用安全扫描
            enable_write_validation=settings.get("enable_write_validation", True),  # 默认启用写入校验
        )

    def to_dict(self) -> dict:
        """Export current configuration as dictionary.

        小白导读: 将当前配置导出为字典，方便序列化保存或调试打印。
        假数据示例:
            返回值形如:
            ```python
            {
                "execution": {
                    "timeout_seconds": None,
                    "max_memory_mb": None,
                    "max_output_chars": 50000,
                    "progress_timeout_seconds": None,
                    "blocked_patterns": ["os.system", "subprocess.call", ...],
                },
                "file_operations": {
                    "max_read_bytes": 5242880,
                    "max_read_lines": 10000,
                    "max_write_bytes": 10485760,
                    "allowed_extensions": [".py", ".md", ...],
                    "blocked_paths": ["/etc", "/sys", ...],
                },
                "enable_security_scan": True,
                "enable_write_validation": True,
            }
            ```
        """
        return {
            "execution": {
                "timeout_seconds": self.execution.timeout_seconds,
                "max_memory_mb": self.execution.max_memory_mb,
                "max_output_chars": self.execution.max_output_chars,
                "progress_timeout_seconds": self.execution.progress_timeout_seconds,
                "blocked_patterns": self.execution.blocked_patterns,
            },
            "file_operations": {
                "max_read_bytes": self.file_ops.max_read_bytes,
                "max_read_lines": self.file_ops.max_read_lines,
                "max_write_bytes": self.file_ops.max_write_bytes,
                "allowed_extensions": self.file_ops.allowed_extensions,
                "blocked_paths": self.file_ops.blocked_paths,
            },
            "enable_security_scan": self.enable_security_scan,
            "enable_write_validation": self.enable_write_validation,
        }


# ─── 全局单例 (Global Singleton) ───
# 小白导读: 模块被导入时自动执行这段代码，创建全局唯一的 TOOL_CONFIG 实例。
# 其他文件只需 `from tool_config import TOOL_CONFIG` 即可使用，无需重复加载。
# 类比: 就像全局只有一个配置管理器，所有工具都共享同一份规则。
try:
    TOOL_CONFIG = ToolConfig.load()  # 小白导读: 尝试从 YAML 文件加载配置，失败则抛异常
except Exception as e:
    # 小白导读: 兜底策略——即使加载失败(文件不存在/权限不足/YAML语法错误)，也用默认值创建实例
    # 这保证了系统不会因为配置问题而完全崩溃
    logger.error(f"Error initializing ToolConfig: {e}, using defaults")
    TOOL_CONFIG = ToolConfig()  # 小白导读: 使用全默认参数创建实例，保证系统可用
