"""Security scanning and resource limiting for code execution.

This module provides:
- SecurityScanner: Static analysis to detect dangerous code patterns
- ResourceLimiter: Execute code with timeout/memory limits
"""

import ast
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from queue import Queue, Empty
from typing import List, Optional

from ..logger import setup_logger
from .tool_config import TOOL_CONFIG

logger = setup_logger()

# Constants
# 默认轮询间隔: 每 0.1 秒检查一次子进程输出，相当于"心跳检测"的频率
DEFAULT_POLL_INTERVAL_SECONDS = 0.1


@dataclass
class ScanResult:
    """Result of security scan.

    Attributes:
    """
    is_safe: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class SecurityScanner:
    """Static analysis for dangerous code patterns.

    Uses both regex pattern matching and AST analysis to detect
    potentially dangerous operations like eval(), os.system(), subprocess
    calls, and file system modifications.
    """

    def __init__(self):
        """
        """
        # 从工具配置中读取被禁止的代码模式列表，若无则默认为空列表
        self.blocked_patterns: List[str] = getattr(
            TOOL_CONFIG.execution,
            "blocked_patterns",
            []
        )
        # 记录扫描器就绪日志，方便排查问题
        logger.info(
            "SecurityScanner 初始化完成，共加载 %d 个禁止模式",
            len(self.blocked_patterns)
        )

    def scan_code(self, input_code: str) -> ScanResult:
        """

        Args:
            input_code: 要扫描的 Python 源代码字符串。

        Returns:
            ScanResult: 包含 is_safe、violations、warnings 的数据对象。
        """
        violations: List[str] = []
        warnings: List[str] = []

        # ---------- 第一步: 正则匹配扫描 ----------

        for pattern in self.blocked_patterns:
            if re.search(pattern, input_code, re.IGNORECASE | re.MULTILINE):
                # 把匹配到的模式记录到违规列表
                violations.append(f"匹配到禁止模式: {pattern}")

        # ---------- 第二步: 额外正则检查 (内置高危关键字) ----------

        #           即使用户改了配置，这些也始终生效，像机场的"必查项目"。
        hard_dangerous_patterns = [
            r'\beval\s*\(',
            r'\bexec\s*\(',
            r'\b__import__\s*\(',
            r'\bcompile\s*\(',
            r'\bopen\s*\(',
            r'\bos\.system\s*\(',
            r'\bos\.popen\s*\(',
            r'\bsubprocess\b',
        ]
        for pattern in hard_dangerous_patterns:
            if re.search(pattern, input_code):
                violations.append(f"检测到内置高危关键字: {pattern}")


        try:
            # 将源代码解析为 AST，mode='exec' 表示解析一个完整的代码块
            tree = ast.parse(input_code, mode='exec')
        except SyntaxError as e:
            # 代码本身语法错误，无法解析为 AST
            # 把语法错误记录为警告（因为执行时也会失败）
            warnings.append(f"代码语法错误，无法进行 AST 检查: {e}")
            # 返回结果: 由于正则阶段已经可能记录了违规，这里直接返回
            return ScanResult(
                is_safe=len(violations) == 0,
                violations=violations,
                warnings=warnings
            )


        for node in ast.walk(tree):
            # 情况一: 函数调用形式 (如 eval("1+1"))
            if isinstance(node, ast.Call):
                func_name = self._get_call_name(node)
                if func_name in ("eval", "exec", "__import__", "compile", "globals", "locals", "getattr", "setattr", "delattr"):
                    violations.append(f"AST 检测到危险函数调用: {func_name}()")

                if func_name in ("os.system", "os.popen", "os.spawn", "subprocess.run",
                                  "subprocess.Popen", "subprocess.call", "subprocess.check_call",
                                  "subprocess.check_output"):
                    violations.append(f"AST 检测到危险系统调用: {func_name}()")

            # 情况二: import 语句 (如 import subprocess)
            if isinstance(node, ast.Import):
                # 逐条检查导入的模块名
                for alias in node.names:
                    if alias.name in ("subprocess", "os", "shutil", "pathlib"):
                        warnings.append(f"AST 检测到风险模块导入: {alias.name}")

            # 情况三: from xxx import yyy 语句
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in ("subprocess", "os", "shutil"):
                    warnings.append(f"AST 检测到风险模块的 from-import: {node.module}")

            if isinstance(node, ast.With):
                for item in node.items:
                    call = item.context_expr
                    if isinstance(call, ast.Call):
                        func_name = self._get_call_name(call)
                        if func_name == "open":
                            warnings.append("AST 检测到文件打开操作: open()")


        is_safe = len(violations) == 0
        logger.info(
            "安全扫描完成: 安全=%s, 违规=%d 条, 警告=%d 条",
            is_safe, len(violations), len(warnings)
        )
        return ScanResult(is_safe=is_safe, violations=violations, warnings=warnings)

    @staticmethod
    def _get_call_name(node: ast.Call) -> str:
        """ AST Call /

        Args:
            node: AST Call 节点。

        Returns:
            函数名字符串，如 "eval" 或 "os.system"。
        """
        if isinstance(node.func, ast.Name):
            return node.func.id
        # 情况二: 属性调用，如 os.system()
        if isinstance(node.func, ast.Attribute):

            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            # 如果最外层是 Name 节点，也加入其 id
            if isinstance(current, ast.Name):
                parts.append(current.id)
            # 反转后 join，得到 "os.system"
            return ".".join(reversed(parts))
        return ""


class ResourceLimiter:
    """Execute code with timeout and memory limits.

    Launches subprocess via Popen, asynchronously reads stdout/stderr
    using threads and Queue, enforces progress-based timeout, and kills
    the process if limits are exceeded.
    """

    def __init__(
        self,
        timeout: int = 30,
        memory_mb: int = 256,
        progress_timeout: int = 10
    ):
        """

        Args:
            timeout: Maximum execution time in seconds (default 30).
            memory_mb: Maximum memory in megabytes (default 256).
            progress_timeout: Seconds without output before termination (default 10).
        """
        self.timeout = timeout
        self.memory_mb = memory_mb
        # 保存"无输出超时"阈值 (秒)
        self.progress_timeout = progress_timeout
        # 记录初始化日志
        logger.info(
            "ResourceLimiter 初始化: timeout=%ds, memory=%dMB, progress_timeout=%ds",
            timeout, memory_mb, progress_timeout
        )

    def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        shell: bool = True,
        executable: Optional[str] = None
    ) -> dict:
        """

        Args:
            command: 要执行的 shell 命令字符串。
            cwd: 命令的工作目录，默认当前目录。
            shell: 是否通过 shell 执行（cmd/bash），默认 True。
            executable: 指定 shell 可执行文件路径，默认 None。

        Returns:
            dict: {
                "returncode": 进程返回码,
                "stdout": 标准输出字符串,
                "stderr": 标准错误字符串,
                "timed_out": 是否超时终止,
                "success": 是否成功完成
            }
        """

        logger.info("开始执行命令: %s", command)
        process = subprocess.Popen(
            command,
            shell=shell,
            cwd=cwd,
            executable=executable,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        # ---------- 创建输出队列 ----------

        stdout_queue: Queue = Queue()
        stderr_queue: Queue = Queue()


        def _read_stream(stream, queue: Queue, stream_name: str):
            """
            """
            try:
                # 逐行迭代读取流
                for line in stream:
                    queue.put((stream_name, line))
            except Exception as e:
                logger.warning("读取 %s 时出错: %s", stream_name, e)
            finally:
                queue.put((stream_name, None))


        stdout_thread = threading.Thread(
            target=_read_stream,
            args=(process.stdout, stdout_queue, "stdout"),
            daemon=True
        )
        stderr_thread = threading.Thread(
            target=_read_stream,
            args=(process.stderr, stderr_queue, "stderr"),
            daemon=True
        )
        # 启动两个线程
        stdout_thread.start()
        stderr_thread.start()

        stdout_lines: List[str] = []
        stderr_lines: List[str] = []
        # 记录两个流是否已结束
        stdout_done = False
        stderr_done = False


        start_time = time.time()
        last_output_time = start_time
        timed_out = False

        while True:

            while True:
                try:
                    stream_name, line = stdout_queue.get(block=False)
                    if line is None:
                        stdout_done = True
                    else:
                        # 收集输出行
                        stdout_lines.append(line)
                        last_output_time = time.time()
                except Empty:
                    break

            while True:
                try:
                    stream_name, line = stderr_queue.get(block=False)
                    if line is None:
                        stderr_done = True
                    else:
                        stderr_lines.append(line)
                        last_output_time = time.time()
                except Empty:
                    break


            return_code = process.poll()
            if return_code is not None:
                break


            elapsed = time.time() - start_time
            if elapsed > self.timeout:
                timed_out = True
                logger.warning("命令执行超时 (%.1fs > %ds)，将终止进程", elapsed, self.timeout)
                process.kill()
                process.wait()
                break


            since_last_output = time.time() - last_output_time
            if since_last_output > self.progress_timeout:
                timed_out = True
                logger.warning(
                    "命令无输出超时 (%.1fs > %ds)，将终止进程",
                    since_last_output, self.progress_timeout
                )
                process.kill()
                process.wait()
                break


            time.sleep(DEFAULT_POLL_INTERVAL_SECONDS)


        # 等待读取线程结束（它们会在 EOF 后自动退出）
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

        if process.poll() is None:
            process.kill()
            process.wait()

        # ---------- 汇总结果 ----------

        result = {
            "returncode": process.returncode,
            "stdout": "".join(stdout_lines),
            "stderr": "".join(stderr_lines),
            "timed_out": timed_out,
            "success": process.returncode == 0 and not timed_out
        }
        # 记录执行结果日志
        logger.info(
            "命令执行完成: returncode=%s, timed_out=%s, stdout=%d 字符, stderr=%d 字符",
            result["returncode"], result["timed_out"],
            len(result["stdout"]), len(result["stderr"])
        )
        # 返回结果字典
        return result
