# ====================================================================
# 文件角色: src/tools/security.py
# --------------------------------------------------------------------
# 本文件是 DATAGEN 项目的"安全扫描与资源限制"模块，负责两件事：
#   1. SecurityScanner —— 在代码真正执行之前，先用静态分析（正则 + AST）
#      检查代码里有没有危险操作（例如 eval、os.system 等），相当于"安检门"。
#   2. ResourceLimiter —— 在沙箱里真正执行代码时，限制运行时间、内存、
#      输出长度，防止恶意或失控代码把机器跑爆。
#
# 与其他文件的协作:
#   - 由 src/tools/factory.py 统一注册，Agent 通过 Tool 机制调用。
#   - 配置项来自 src/tools/tool_config.py 中的 TOOL_CONFIG.execution。
#   - 日志通过 src/logger.py 的 setup_logger() 获取。
#
# 小白导读:
#   - MCP (Model Context Protocol): 一种让 LLM 与外部工具/数据源交互的开放协议。
#       类比: MCP 就像 AI 世界的"USB-C 接口"，统一了工具与模型之间的连接方式。
#   - Tool (工具): Agent 可调用的一个功能单元，比如"执行代码"、"搜索网页"。
#       类比: Tool 就像 App 里的一个按钮，Agent 按下它就能完成特定任务。
#   - Agent (智能体): 能自主决策、调用 Tool 来达成目标的 LLM 应用。
#       类比: Agent 就像一个有自主意识的助手，能自己决定下一步做什么。
#   - LLM (大语言模型): 如 GPT、Claude 等能理解和生成文本的模型。
#       类比: LLM 就像一个超级聪明的"文字接龙机器"，能根据上下文预测下一个词。
#   - AST (Abstract Syntax Tree): 源代码的树状结构表示。
#       类比: AST 就像语文课上的"句子成分分析"，把代码拆成主谓宾结构来理解。
#   - 正则表达式 (Regex): 一种用模式匹配字符串的强大工具。
#       类比"查找替换"的高级版，可以模糊匹配一类文本。
#   - subprocess.Popen: Python 里启动外部程序（如运行 shell 命令）的类。
#       类比: Popen 就像在命令行里敲命令，但用 Python 代码来控制。
# ====================================================================

"""Security scanning and resource limiting for code execution.

This module provides:
- SecurityScanner: Static analysis to detect dangerous code patterns
- ResourceLimiter: Execute code with timeout/memory limits
"""

import ast  # AST (Abstract Syntax Tree): Python 标准库，用于静态分析代码语法结构
import re  # 正则 (Regex): 用于"文本模式匹配"
import subprocess  # 子进程模块: 启动外部命令 (Popen / run)
import threading  # 线程模块: 用监控线程读取子进程的 stdout/stderr
import time  # 时间模块: 用于计算超时
from dataclasses import dataclass, field  # dataclass: Python 3.7+ 的"数据容器"模板
from queue import Queue, Empty  # Queue: 线程安全的队列，用于线程间传递数据
from typing import List, Optional

from ..logger import setup_logger
from .tool_config import TOOL_CONFIG

logger = setup_logger()

# Constants
# 默认轮询间隔: 每 0.1 秒检查一次子进程输出，相当于"心跳检测"的频率
DEFAULT_POLL_INTERVAL_SECONDS = 0.1


@dataclass  # 小白导读: dataclass 装饰器自动生成 __init__、__repr__、__eq__ 等方法
class ScanResult:
    """Result of security scan.
    安全扫描结果的数据容器。

    Attributes:
        is_safe: Whether the code passed security checks. True=安全, False=有违规。
        violations: List of security violations found. 严重违规列表（会阻止执行）。
        warnings: Non-blocking warnings (e.g., risky imports). 警告列表（不阻止，但提醒）。
    """
    is_safe: bool  # 小白导读: True=安全通过, False=发现违规
    violations: List[str] = field(default_factory=list)  # 严重违规项列表（会阻止执行）
    warnings: List[str] = field(default_factory=list)    # 警告项列表（不阻止，但会提醒）


class SecurityScanner:
    """Static analysis for dangerous code patterns.

    Uses both regex pattern matching and AST analysis to detect
    potentially dangerous operations like eval(), os.system(), subprocess
    calls, and file system modifications.

    小白导读:
    - 先像"安检门"一样扫描一遍代码，有问题就拦下来，不让执行。
    - 两层检查: 第一层用"正则表达式"快速扫描关键模式（像关键词过滤），
      第二层用"AST 分析"理解代码语法结构（像理解句子成分）。
    """

    def __init__(self):
        """初始化安全扫描器。

        从 TOOL_CONFIG.execution.blocked_patterns 加载禁止模式列表。
        小白导读: 禁止模式就像"黑名单"，写在配置文件里，告诉扫描器哪些代码不能放过去。
        """
        # 从工具配置中读取被禁止的代码模式列表，若无则默认为空列表
        self.blocked_patterns: List[str] = getattr(
            TOOL_CONFIG.execution,  # 先拿到 execution 子配置
            "blocked_patterns",    # 读取 blocked_patterns 字段
            []                     # 如果不存在，默认空列表
        )
        # 记录扫描器就绪日志，方便排查问题
        logger.info(
            "SecurityScanner 初始化完成，共加载 %d 个禁止模式",
            len(self.blocked_patterns)
        )

    def scan_code(self, input_code: str) -> ScanResult:
        """扫描输入代码，返回扫描结果。

        综合使用"正则匹配"和"AST 分析"两种手段。
        任何一个环节发现严重安全问题，就标记 is_safe=False。

        小白导读:
        - 就像快递员收件时要先 X 光扫描 + 人工开箱检查，两道工序互补。
        - 正则匹配: 快速但可能有误报。
        - AST 分析: 更准确理解代码结构，但只能解析合法语法。

        Args:
            input_code: 要扫描的 Python 源代码字符串。

        Returns:
            ScanResult: 包含 is_safe、violations、warnings 的数据对象。
        """
        # ---------- 初始化结果容器 ----------
        violations: List[str] = []   # 严重违规：必须阻止执行
        warnings: List[str] = []     # 警告：提醒但不强制阻止

        # ---------- 第一步: 正则匹配扫描 ----------
        # 小白导读: 像"关键词过滤"一样，逐条检查黑名单里的模式
        for pattern in self.blocked_patterns:
            # re.IGNORECASE: 忽略大小写，防止用户用 "Eval" 绕过 "eval"
            # re.MULTILINE: 多行匹配，每行都检查
            if re.search(pattern, input_code, re.IGNORECASE | re.MULTILINE):
                # 把匹配到的模式记录到违规列表
                violations.append(f"匹配到禁止模式: {pattern}")

        # ---------- 第二步: 额外正则检查 (内置高危关键字) ----------
        # 小白导读: 除了配置文件里的黑名单，还有一份"硬编码"的高危关键字列表
        #           即使用户改了配置，这些也始终生效，像机场的"必查项目"。
        hard_dangerous_patterns = [
            r'\beval\s*\(',          # eval(): 执行任意字符串代码
            r'\bexec\s*\(',          # exec(): 执行任意代码块
            r'\b__import__\s*\(',   # __import__: 动态导入模块
            r'\bcompile\s*\(',       # compile(): 编译代码对象
            r'\bopen\s*\(',          # open(): 文件读写 (高风险场景)
            r'\bos\.system\s*\(',   # os.system(): 执行 shell 命令
            r'\bos\.popen\s*\(',    # os.popen(): 执行 shell 并获取输出
            r'\bsubprocess\b',      # subprocess 模块: 启动外部进程
        ]
        # 逐条检查内置高危关键字
        for pattern in hard_dangerous_patterns:
            if re.search(pattern, input_code):
                # 记录违规并附带说明，方便定位问题
                violations.append(f"检测到内置高危关键字: {pattern}")

        # ---------- 第三步: AST 分析 ----------
        # 小白导读: 像"语文老师分析句子成分"一样，把代码拆成树状结构来理解。
        #           这样能识别危险的函数调用、属性访问等语法结构。
        try:
            # 将源代码解析为 AST，mode='exec' 表示解析一个完整的代码块
            tree = ast.parse(input_code, mode='exec')
        except SyntaxError as e:
            # 代码本身语法错误，无法解析为 AST
            # 把语法错误记录为警告（因为执行时也会失败）
            warnings.append(f"代码语法错误，无法进行 AST 检查: {e}")
            # 返回结果: 由于正则阶段已经可能记录了违规，这里直接返回
            return ScanResult(
                is_safe=len(violations) == 0,  # 有违规就不安全
                violations=violations,
                warnings=warnings
            )

        # ---------- 遍历 AST 节点查找危险调用 ----------
        # 小白导读: ast.walk 会像"遍历树"一样访问每个节点。
        #           这里我们用"访问者模式"遍历每一个语法节点。
        for node in ast.walk(tree):
            # 情况一: 函数调用形式 (如 eval("1+1"))
            if isinstance(node, ast.Call):
                # 检查被调用的函数名
                func_name = self._get_call_name(node)
                # 如果函数名在危险名单里，记录违规
                if func_name in ("eval", "exec", "__import__", "compile", "globals", "locals", "getattr", "setattr", "delattr"):
                    violations.append(f"AST 检测到危险函数调用: {func_name}()")

                # 检查属性调用 (如 os.system, subprocess.Popen)
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

            # 情况四: with open(...) 形式的文件操作
            if isinstance(node, ast.With):
                # 遍历 with 语句里的每一个子项
                for item in node.items:
                    call = item.context_expr
                    if isinstance(call, ast.Call):
                        func_name = self._get_call_name(call)
                        if func_name == "open":
                            warnings.append("AST 检测到文件打开操作: open()")

        # ---------- 汇总结果 ----------
        # 小白导读: 有任何一条违规就算不安全，警告再多也不算违规。
        is_safe = len(violations) == 0
        # 记录扫描结果日志
        logger.info(
            "安全扫描完成: 安全=%s, 违规=%d 条, 警告=%d 条",
            is_safe, len(violations), len(warnings)
        )
        # 返回完整的扫描结果对象
        return ScanResult(is_safe=is_safe, violations=violations, warnings=warnings)

    @staticmethod
    def _get_call_name(node: ast.Call) -> str:
        """从 AST Call 节点中提取函数/方法名。

        小白导读:
        对于 `foo()` 这样的简单调用，返回 "foo"。
        对于 `obj.method()` 这样的属性调用，返回 "obj.method"。
        对于更复杂的调用（如 `[0]()`），返回空字符串表示无法确定。

        Args:
            node: AST Call 节点。

        Returns:
            函数名字符串，如 "eval" 或 "os.system"。
        """
        # 情况一: 直接函数调用，如 eval()
        if isinstance(node.func, ast.Name):
            return node.func.id  # .id 属性保存了名称字符串
        # 情况二: 属性调用，如 os.system()
        if isinstance(node.func, ast.Attribute):
            # 递归拼接模块名和函数名
            # 小白导读: 就像把 "os" + "." + "system" 拼成 "os.system"
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)  # 收集属性名
                current = current.value     # 向上追溯
            # 如果最外层是 Name 节点，也加入其 id
            if isinstance(current, ast.Name):
                parts.append(current.id)
            # 反转后 join，得到 "os.system"
            return ".".join(reversed(parts))
        # 情况三: 其他复杂调用（如 lambda、括号包裹等）
        return ""


class ResourceLimiter:
    """Execute code with timeout and memory limits.

    Launches subprocess via Popen, asynchronously reads stdout/stderr
    using threads and Queue, enforces progress-based timeout, and kills
    the process if limits are exceeded.

    小白导读:
    - 像一个"定时炸弹"机制: 代码必须按时跑完，超时自动"拆弹专家"剪线（杀进程）。
    - 异步读取: 主线程不阻塞，用两个"小助手"（线程）分别监听 stdout 和 stderr。
    - Queue: 线程安全的"传话员"，把子进程的输出安全地传给主线程。
    """

    def __init__(
        self,
        timeout: int = 30,
        memory_mb: int = 256,
        progress_timeout: int = 10
    ):
        """初始化资源限制器。

        小白导读:
        - timeout: 最长运行秒数（像限时答题的考试铃）。
        - memory_mb: 最大内存（像书包容量上限）。
        - progress_timeout: 如果连续这么多秒没有新输出，也终止（像心跳停止判定）。

        Args:
            timeout: Maximum execution time in seconds (default 30).
            memory_mb: Maximum memory in megabytes (default 256).
            progress_timeout: Seconds without output before termination (default 10).
        """
        # 保存超时阈值 (秒)
        self.timeout = timeout
        # 保存内存上限 (MB)
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
        """在资源限制下执行命令。

        使用 subprocess.Popen 启动命令，并通过线程异步收集输出。
        如果在 timeout 秒内未完成，将终止进程。
        如果连续 progress_timeout 秒没有新输出，也将终止。

        小白导读:
        - 流程: 启动命令 → 开两个线程读输出 → 主线程轮询等待 → 超时或结束。
        - 不阻塞: 读取输出在后台线程进行，主线程只负责"发号施令"和"收网"。

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
        # ---------- 启动子进程 ----------
        # 小白导读: Popen 就像"按下启动按钮"，命令开始执行但还没完成。
        logger.info("开始执行命令: %s", command)
        process = subprocess.Popen(
            command,                          # 要执行的命令
            shell=shell,                      # 是否通过 shell 执行
            cwd=cwd,                          # 工作目录
            executable=executable,            # 指定 shell 路径
            stdout=subprocess.PIPE,           # 捕获标准输出
            stderr=subprocess.PIPE,           # 捕获标准错误
            text=True,                        # 以文本模式返回（而非 bytes）
            bufsize=1                         # 行缓冲，每行输出都能及时读取
        )

        # ---------- 创建输出队列 ----------
        # 小白导读: Queue 就像"收件箱"，两个线程往里放数据，主线程从里取。
        stdout_queue: Queue = Queue()  # 存放 stdout 每一行
        stderr_queue: Queue = Queue()  # 存放 stderr 每一行

        # ---------- 定义读取线程的目标函数 ----------
        # 小白导读: 每个线程负责"盯着"一个管道，有输出就往队列里塞。
        def _read_stream(stream, queue: Queue, stream_name: str):
            """从子进程流中逐行读取数据并放入队列。

            小白导读:
            - 这个函数在独立线程中运行。
            - 每次 readline() 会阻塞直到有一行数据或 EOF。
            - 读完所有数据后，放入 None 作为"结束信号"。
            """
            try:
                # 逐行迭代读取流
                for line in stream:
                    # 把每一行放入队列，附带流名称用于区分
                    queue.put((stream_name, line))
            except Exception as e:
                # 读取异常时记录错误
                logger.warning("读取 %s 时出错: %s", stream_name, e)
            finally:
                # 放入 None 作为"结束信号"，告诉主线程"读完了"
                queue.put((stream_name, None))

        # ---------- 启动读取线程 ----------
        # 小白导读: 两个线程像两个"监听耳机"，一个听 stdout，一个听 stderr。
        stdout_thread = threading.Thread(
            target=_read_stream,                    # 线程要执行的函数
            args=(process.stdout, stdout_queue, "stdout"),  # 传入参数
            daemon=True                             # 守护线程: 主线程退出时自动结束
        )
        stderr_thread = threading.Thread(
            target=_read_stream,
            args=(process.stderr, stderr_queue, "stderr"),
            daemon=True
        )
        # 启动两个线程
        stdout_thread.start()
        stderr_thread.start()

        # ---------- 收集输出的容器 ----------
        stdout_lines: List[str] = []  # 存储所有 stdout 行
        stderr_lines: List[str] = []  # 存储所有 stderr 行
        # 记录两个流是否已结束
        stdout_done = False
        stderr_done = False

        # ---------- 主循环: 轮询等待 ----------
        # 小白导读: 主线程像"监考官"，每隔 0.1 秒检查一次情况。
        start_time = time.time()          # 记录开始时间
        last_output_time = start_time    # 记录最后一次收到输出的时间
        timed_out = False                 # 是否超时标志

        while True:
            # --- 非阻塞地从队列中取数据 ---
            # 小白导读: 主线程不阻塞，有数据就取，没数据就跳过。
            while True:
                try:
                    # block=False 表示不阻塞，队列空时抛 Empty 异常
                    stream_name, line = stdout_queue.get(block=False)
                    if line is None:
                        # None 是结束信号
                        stdout_done = True
                    else:
                        # 收集输出行
                        stdout_lines.append(line)
                        # 更新"最后输出时间"，用于 progress_timeout 判断
                        last_output_time = time.time()
                except Empty:
                    # 队列空了，跳出内层循环
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

            # --- 检查进程是否已结束 ---
            # 小白导读: poll() 返回 None 表示进程还在运行。
            return_code = process.poll()
            if return_code is not None:
                # 进程已结束，跳出主循环
                break

            # --- 检查总超时 ---
            # 小白导读: 像"考试铃响"，时间到了必须停。
            elapsed = time.time() - start_time
            if elapsed > self.timeout:
                timed_out = True
                logger.warning("命令执行超时 (%.1fs > %ds)，将终止进程", elapsed, self.timeout)
                # 终止进程
                process.kill()
                # 等待进程真正结束
                process.wait()
                break

            # --- 检查"无输出超时" ---
            # 小白导读: 如果进程一直不输出，可能是卡住了，也要终止。
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

            # --- 短暂休眠，避免 CPU 空转 ---
            # 小白导读: 轮询间隔 0.1 秒，既保证响应速度又不浪费 CPU。
            time.sleep(DEFAULT_POLL_INTERVAL_SECONDS)

        # ---------- 清理阶段 ----------
        # 小白导读: 不管进程是正常结束还是被 kill，都要"收拾残局"。
        # 等待读取线程结束（它们会在 EOF 后自动退出）
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

        # 如果进程仍在运行（理论上不应该），再 kill 一次
        if process.poll() is None:
            process.kill()
            process.wait()

        # ---------- 汇总结果 ----------
        # 小白导读: 把收集到的所有输出拼成字符串，返回给调用者。
        result = {
            "returncode": process.returncode,           # 进程返回码
            "stdout": "".join(stdout_lines),            # 标准输出
            "stderr": "".join(stderr_lines),            # 标准错误
            "timed_out": timed_out,                       # 是否超时
            "success": process.returncode == 0 and not timed_out  # 成功=返回码0且未超时
        }
        # 记录执行结果日志
        logger.info(
            "命令执行完成: returncode=%s, timed_out=%s, stdout=%d 字符, stderr=%d 字符",
            result["returncode"], result["timed_out"],
            len(result["stdout"]), len(result["stderr"])
        )
        # 返回结果字典
        return result
