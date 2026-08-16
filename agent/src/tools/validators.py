# ====================================================================
# 文件角色：本模块是"文件操作的安全门卫"，提供两个校验器：
#   1. PathValidator   —— 校验文件路径是否安全（是否在黑名单目录、扩展名是否合法、文件大小是否超限）
#   2. ContentValidator —— 校验写入内容是否合规（体积、残缺标记、敏感信息、空内容）
#
# 小白导读（给初学者的阅读指南）：
#   • 路径 / 扩展名 / 文件大小：就像进小区要刷卡、不能带超大行李一样，是基础安全防线。
#   • 敏感数据检测：用正则表达式（一种"文本模式匹配"的写法）扫描内容，防止把 API Key、密码等意外写入文件。
#   • 正则（re）：可以理解为"用特殊语法描述一类字符串的规则"，例如 r"sk-[a-z]{32,}" 能匹配所有以 sk- 开头、至少 32 个小写字母的字符串。
#   • 类方法（@classmethod）：属于类而不是实例的方法，调用时用 cls 代替 self，适合"工具型"函数。
#   • 合作文件：本模块被 src/tools/ 下的文件读写工具调用；配置来自 tool_config.py 的 TOOL_CONFIG；日志来自 src/logger.py。
#
# 阅读顺序建议：先读 PathValidator（路径校验），再读 ContentValidator（内容校验），最后看 validate_and_log（汇总入口）。
# ====================================================================

"""Path and content validators for file operations.

This module provides:
- PathValidator: Validate file paths for security
- ContentValidator: Validate content before writing
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

from ..logger import setup_logger
from .tool_config import TOOL_CONFIG  # 小白导读: TOOL_CONFIG 是一个全局配置对象，像"设置面板"一样集中管理所有开关和阈值

logger = setup_logger()  # 小白导读: setup_logger() 返回一个 Logger 对象，用于把信息/警告/错误输出到控制台或文件


class PathValidator:
    """Validate file paths for security.

    Checks:
    - Path is not in blocked directories
    - File extension is in allowed list
    - File size is within limits
    """

    @classmethod
    def check_path(cls, file_path: str) -> None:
        """Ensure path is not in blocked directories.

        Args:
            file_path: Path to validate.

        Raises:
            PermissionError: If path is in a blocked directory.
        """
        try:
            resolved = Path(file_path).resolve()  # 小白导读: resolve() 把相对路径转成绝对路径，并去掉 .. 等符号，防止"路径穿越攻击"
        except (OSError, ValueError) as e:
            raise PermissionError(f"Invalid path: {file_path}") from e  # 小白导读: "from e" 保留原始异常链，方便调试时追溯根因

        for blocked in TOOL_CONFIG.file_ops.blocked_paths:  # 小白导读: blocked_paths 是配置里列出的"禁止访问的目录"，如 ["/etc", "/sys"]
            try:
                blocked_resolved = Path(os.path.expanduser(blocked)).resolve()  # 小白导读: expanduser() 把 ~ 展开成用户主目录，如 ~ → /home/alice
            except (OSError, ValueError):
                # Skip invalid blocked paths
                continue  # 小白导读: 如果黑名单里某条路径本身写错了，跳过它而不是崩溃——防御性编程

            if str(resolved).startswith(str(blocked_resolved)):  # 小白导读: startswith 判断"目标路径是否以黑名单开头"，即是否在黑名单目录内部
                raise PermissionError(
                    f"Access denied: {file_path} is in blocked path '{blocked}'"
                )

    @classmethod
    def check_extension(cls, file_path: str) -> None:
        """Ensure file extension is allowed.

        Args:
            file_path: Path to validate.

        Raises:
            PermissionError: If extension is not in allowed list.
        """
        ext = Path(file_path).suffix.lower()  # 小白导读: suffix 取扩展名（如 ".py"），lower() 统一转小写避免大小写绕过
        allowed = TOOL_CONFIG.file_ops.allowed_extensions  # 小白导读: allowed_extensions 是配置里允许的扩展名列表，如 [".py", ".txt", ".md"]

        # Allow files without extension
        if not ext:
            return  # 小白导读: 没有扩展名的文件（如 Makefile）默认放行，避免误杀

        if ext not in allowed:
            raise PermissionError(
                f"File type '{ext}' not allowed. Allowed: {', '.join(allowed)}"
            )

    @classmethod
    def check_file_size(cls, file_path: str) -> None:
        """Ensure file is within size limit for reading.

        Args:
            file_path: Path to check.

        Raises:
            ValueError: If file exceeds max_read_bytes.
        """
        if not os.path.exists(file_path):
            return  # 小白导读: 文件不存在时跳过，避免 FileNotFoundError；写入新文件时本来就没有旧文件

        size = os.path.getsize(file_path)  # 小白导读: getsize() 返回文件字节数，1 MB = 1024 * 1024 字节
        max_size = TOOL_CONFIG.file_ops.max_read_bytes  # 小白导读: max_read_bytes 是配置里"允许读取的最大字节数"，防止一次性读入超大文件撑爆内存

        if size > max_size:
            raise ValueError(
                f"File too large: {size:,} bytes (max: {max_size:,} bytes = {max_size // 1024 // 1024}MB)"
            )

    @classmethod
    def validate_read(cls, file_path: str) -> None:
        """Run all read validations.

        Args:
            file_path: Path to validate.

        Raises:
            PermissionError: If path or extension is not allowed.
            ValueError: If file is too large.
        """
        cls.check_path(file_path)      # 第一步：检查路径是否在黑名单
        cls.check_extension(file_path) # 第二步：检查扩展名是否合法
        cls.check_file_size(file_path) # 第三步：检查文件大小是否超限

    @classmethod
    def validate_write(cls, file_path: str) -> None:
        """Run all write validations for path.

        Args:
            file_path: Path to validate.

        Raises:
            PermissionError: If path or extension is not allowed.
        """
        cls.check_path(file_path)      # 写入前也要检查路径黑名单
        cls.check_extension(file_path) # 写入前也要检查扩展名
        # 注意：写入时不检查文件大小，因为此时文件可能还不存在或正在被创建


class ContentValidator:
    """Validate content before writing.

    Checks for:
    - Content size limits
    - Incomplete content markers (TODO, FIXME, etc.)
    - Potential sensitive data (API keys, passwords)
    """

    # Minimum content length to avoid "very short" warning
    MIN_CONTENT_LENGTH = 10  # 小白导读: 内容少于 10 个字符会被警告"内容过短"

    # Markers that suggest incomplete content
    INCOMPLETE_MARKERS = ["TODO", "FIXME", "XXX", "TBD", "HACK", "（待補）", "..."]  # 小白导读: 这些标记说明代码还没写完，像便利贴一样提醒开发者回头补

    # Patterns for detecting sensitive data
    SENSITIVE_PATTERNS = [
        (r"['\"]sk-[a-zA-Z0-9]{32,}['\"]", "OpenAI API key"),  # 小白导读: sk- 开头、至少 32 位字母数字，是 OpenAI 的典型 Key 格式
        (r"['\"]AKIA[A-Z0-9]{16}['\"]", "AWS access key"),      # 小白导读: AKIA 开头、16 位大写字母数字，是 AWS 的 Access Key
        (r"password\s*=\s*['\"][^'\"]+['\"]", "Hardcoded password"),  # 小白导读: 形如 password="xxx" 的硬编码密码
        (r"['\"][a-f0-9]{32}['\"]", "Potential API key/hash"),  # 小白导读: 32 位十六进制字符串，可能是 MD5 或某种 Token
    ]

    @classmethod
    def validate_content(
        cls,
        content: str,
        file_path: str,
    ) -> Tuple[bool, List[str]]:
        """Validate content before writing.

        Args:
            content: Content to validate.
            file_path: Target file path (for context).

        Returns:
            Tuple of (is_valid, warnings).
            is_valid is False only if content exceeds size limits.
            warnings are non-blocking issues found.

        假数据示例:
            输入: content="TODO: write docs", file_path="readme.md"
            输出: (True, ["Found incomplete marker: 'TODO'"])
        """
        warnings = []

        # Check size limit
        content_bytes = len(content.encode('utf-8'))  # 小白导读: encode('utf-8') 把字符串转成字节，中文一个字占 3 字节
        max_bytes = TOOL_CONFIG.file_ops.max_write_bytes  # 小白导读: max_write_bytes 是配置里"允许写入的最大字节数"

        if content_bytes > max_bytes:
            return False, [
                f"Content too large: {content_bytes:,} bytes "
                f"(max: {max_bytes:,} bytes)"
            ]  # 小白导读: 体积超限时直接返回 False，表示"禁止写入"

        # Skip further validation if disabled
        if not TOOL_CONFIG.enable_write_validation:  # 小白导读: enable_write_validation 是总开关，False 时跳过所有检查以提升性能
            return True, []

        # Check for incomplete markers
        for marker in cls.INCOMPLETE_MARKERS:
            if marker in content:
                warnings.append(f"Found incomplete marker: '{marker}'")
                break  # Only report first marker 小白导读: 只报告第一个匹配，避免警告刷屏

        # Check for sensitive data patterns
        for pattern, description in cls.SENSITIVE_PATTERNS:
            if re.search(pattern, content):  # 小白导读: re.search 在字符串中搜索正则匹配，找到即返回 Match 对象
                warnings.append(f"Potential {description} detected - review before commit")
                break  # Only report first match 小白导读: 同样只报告第一个匹配，保持输出简洁

        # Check for empty or nearly empty content
        stripped = content.strip()  # 小白导读: strip() 去掉首尾空白字符（空格、换行、制表符）
        if not stripped:
            warnings.append("Content is empty")  # 小白导读: 纯空白内容会被警告
        elif len(stripped) < cls.MIN_CONTENT_LENGTH:
            warnings.append("Content is very short - verify completeness")  # 小白导读: 内容过短可能是误操作

        return True, warnings

    @classmethod
    def validate_and_log(
        cls,
        content: str,
        file_path: str,
    ) -> Tuple[bool, str]:
        """Validate content and return formatted result.

        Args:
            content: Content to validate.
            file_path: Target file path.

        Returns:
            Tuple of (is_valid, message).

        假数据示例:
            输入: content="password=\"secret123\"", file_path="config.py"
            输出: (True, "Warnings: Potential Hardcoded password detected - review before commit")
        """
        is_valid, warnings = cls.validate_content(content, file_path)  # 小白导读: 先调用核心校验逻辑，拿到结果和警告列表

        if not is_valid:
            error_msg = f"Validation failed: {warnings[0]}"  # 小白导读: 取第一条错误信息（通常只有体积超限这一条）
            logger.error(error_msg)  # 小白导读: logger.error 输出错误级别日志，红色高亮
            return False, error_msg

        if warnings:
            warning_msg = f"Warnings: {'; '.join(warnings)}"  # 小白导读: 用分号拼接多条警告，一条消息返回
            logger.warning(f"Write validation for {file_path}: {warning_msg}")  # 小白导读: logger.warning 输出警告级别日志，黄色高亮
            return True, warning_msg

        return True, ""  # 小白导读: 无警告时返回空字符串，调用方可以判断 "if message:" 来处理
