# ============================================================================
# 文件角色: src/tools/basetool.py
# ----------------------------------------------------------------------------
# 这是整个 Agent 系统的"手和脚"——工具层的核心基文件。
# 它定义了三个可被 Agent 直接调用的工具 (LangChain @tool 装饰器):
#   1. execute_code   —— 在隔离的 Conda 环境中执行 Python 代码
#   2. execute_command—— 在 Conda 环境中执行 shell 命令 (如 pip install)
#   3. list_directory  —— 列出工作目录的文件列表
#
# 小白导读 (关键术语大白话):
#   - MCP (Model Context Protocol): 一种让 AI 模型调用外部工具的"USB-C 接口"标准。
#       类比: 就像手机 App 通过 USB-C 接口充电一样，MCP 是 AI 和外界的统一协议。
#   - Agent (智能体): 一个能自主决策、调用工具完成复杂任务的 AI 循环。
#       类比: 就像一个实习生，你给他任务，他会自己查资料、写代码、改 bug。
#   - LLM (大语言模型): 如 GPT-4、Claude 等，负责"思考"和"决策"的大脑。
#   - Conda: Python 的环境/包管理器，类似 Node.js 的 nvm。
#       它允许你创建隔离的 Python 环境，避免包版本冲突。
#   - Subprocess: Python 里调用系统命令的方式，就像你在终端敲命令。
#   - @tool (LangChain 装饰器): 把一个普通函数"注册"成 Agent 可调用的工具。
#       函数签名和文档字符串就是 Agent 看到的"说明书"。
#   - Annotated[str, "描述"]: 给参数加上类型 + 说明文字，帮助 Agent 理解参数含义。
#
# 与其他文件的协作关系:
#   - src/config.py         : 导入 WORKING_DIRECTORY (工作目录) 和 CONDA_ENV (环境名)
#   - src/tools/security.py  : 安全扫描 (SecurityScanner) 和资源限制 (ResourceLimiter)
#   - src/tools/tool_config: 工具开关配置 (如是否启用安全扫描)
#   - src/logger.py         : 日志初始化
#   - 被 src/tools/factory.py 组装后注册给 Agent 使用
# ============================================================================

import os
import platform  # 检测当前操作系统 (Windows/Linux/macOS)
from typing import Annotated  # 给类型附加元数据（说明文字），供 LangChain 工具描述使用
import subprocess  # 执行系统命令的内置模块

# LangChain 的 @tool 装饰器：把函数注册成 Agent 可调用的工具
from langchain_core.tools import tool

from ..logger import setup_logger
from ..config import WORKING_DIRECTORY, CONDA_ENV
# 小白导读: WORKING_DIRECTORY 是 Agent 存放代码/数据的"工作目录"（类似桌面）
# 小白导读: CONDA_ENV 是 Conda 虚拟环境名，Agent 在其中执行代码以避免污染系统 Python

# 初始化日志器：所有工具调用都会留下日志，方便调试和审计
logger = setup_logger()

# 确保存储目录存在：如果工作目录不存在就自动创建
# 类比: 就像你打开 Word 时如果文件夹不存在，程序帮你建一个
if not os.path.exists(WORKING_DIRECTORY):
    os.makedirs(WORKING_DIRECTORY)
    logger.info(f"Created storage directory: {WORKING_DIRECTORY}")


def get_platform_specific_command(command: str) -> tuple:
    """获取平台特定的命令执行详情，使用 conda run。

    返回 (shell命令, 是否使用shell, 可执行文件路径) 三元组。

    小白导读: conda run -n 环境名 命令 —— 在指定 Conda 环境中执行命令
    类比: 就像"用 Python 3.9 的虚拟环境运行这个脚本"，而不是用系统默认 Python
    """
    # 构造 conda run 命令：在指定环境中执行用户命令
    conda_command = f"conda run -n {CONDA_ENV} {command}"

    # 检测操作系统，决定用什么 shell 来执行命令
    system = platform.system().lower()
    if system == "windows":
        # Windows 下使用 cmd.exe（shell=True 表示通过 shell 执行）
        return (conda_command, True, None)
    else:
        # Linux/macOS 下显式指定 /bin/bash 作为可执行文件
        return (conda_command, True, "/bin/bash")


@tool  # 小白导读: @tool 装饰器把下面函数注册成 Agent 可调用的工具，Agent 会根据文档字符串判断何时使用它
def execute_code(
    input_code: Annotated[str, "要执行的 Python 代码。"],  # Annotated 给参数加说明，Agent 能读懂
    codefile_name: Annotated[str, "Python 代码文件名或完整路径。"] = 'code.py',
    timeout: Annotated[int | None, "执行超时时间（秒）。None 表示无限制。"] = None,
    memory_mb: Annotated[int | None, "内存限制（MB，仅 Linux）。None 表示无限制。"] = None,
    progress_timeout: Annotated[int | None, "无输出 N 秒后超时。适用于 ML/DL。"] = None,
    # 小白导读: progress_timeout 是"进度超时"——如果代码长时间没有新输出就杀掉，
    # 这对训练 ML/DL 模型时防止死循环特别有用
) -> Annotated[dict, "包含输出和文件路径的执行结果"]:
    """
    在指定的 conda 环境中执行 Python 代码并返回结果。

    安全特性：
    - 代码在执行前会扫描危险模式
    - 支持可选的超时和内存限制
    - 输出过长时会被截断

    Args:
        input_code: 要执行的 Python 代码。
        codefile_name: 保存代码的文件名（默认：code.py）。
        timeout: 固定超时秒数。None 表示无限制。
        memory_mb: 内存限制（仅 Linux）。None 表示无限制。
        progress_timeout: 无 stdout 输出 N 秒后超时（适用于长时间 ML/DL 任务）。

    Returns:
        包含结果状态、输出/错误、文件路径的字典。

    假数据示例:
        输入: input_code="print('hello')", codefile_name="test.py"
        输出: {"result": "Code executed successfully", "output": "hello\n\nIf you have...", "file_path": "..."}
    """
    from .tool_config import TOOL_CONFIG  # 延迟导入：工具配置（如是否启用安全扫描）
    from .security import SecurityScanner, ResourceLimiter
    # 小白导读: SecurityScanner 检查代码是否包含危险操作（如删除文件、执行系统命令）
    # 小白导读: ResourceLimiter 限制代码运行时间和内存，防止死循环耗尽资源

    logger.info("Tool invoked: execute_code, input_code:", input_code[:50])


    code_file_path = None  # 代码文件路径，初始化为 None（用于错误处理时返回）
    try:
        # ===== 安全扫描 =====
        # 小白导读: 执行前先做"安检"，防止 Agent 生成危险代码（如格式化硬盘）
        if TOOL_CONFIG.enable_security_scan:
            scan_result = SecurityScanner().scan_code(input_code)
            if not scan_result.is_safe:
                # 扫描不通过：记录警告并返回错误信息
                logger.warning(f"Security scan blocked code: {scan_result.violations}")
                return {
                    "result": "Security violation",
                    "error": f"Code blocked: {'; '.join(scan_result.violations)}",
                    "file_path": None
                }
            if scan_result.warnings:
                # 有警告但不阻止执行（如使用了不推荐的函数）
                logger.info(f"Security scan warnings: {scan_result.warnings}")

        # 确保工作目录存在（exist_ok=True 表示已存在时不报错）
        os.makedirs(WORKING_DIRECTORY, exist_ok=True)

        # 处理文件路径，确保是有效路径
        # 小白导读: 判断用户给的是绝对路径（如 /home/user/code.py）还是相对路径（如 code.py）
        if os.path.isabs(codefile_name):
            code_file_path = codefile_name  # 绝对路径：直接使用
        else:
            if WORKING_DIRECTORY not in codefile_name:
                # 相对路径：拼接到工作目录下
                code_file_path = os.path.join(WORKING_DIRECTORY, codefile_name)
            else:
                code_file_path = codefile_name

        # 标准化路径：处理 .. 和多余的斜杠，如 /a/b/../c -> /a/c
        code_file_path = os.path.normpath(code_file_path)

        logger.info(f"Code will be written to file: {code_file_path}")

        # 将代码写入文件（UTF-8 编码）
        # 小白导读: 先写文件再执行，而不是直接 python -c，因为长代码不适合命令行参数
        with open(code_file_path, 'w', encoding='utf-8') as code_file:
            code_file.write(input_code)

        logger.info(f"Code has been written to file: {code_file_path}")

        # 获取平台特定命令
        python_cmd = f"python {codefile_name}"
        full_command, shell, executable = get_platform_specific_command(python_cmd)

        logger.info(f"Executing command: {full_command}")

        # ===== 带资源限制执行 =====
        # 小白导读: ResourceLimiter 是"保镖"，监控代码运行时间和内存，超限就杀掉
        limiter = ResourceLimiter(
            timeout=timeout,
            memory_mb=memory_mb,
            progress_timeout=progress_timeout,
        )

        try:
            # 在指定工作目录下执行命令
            result = limiter.execute(
                command=full_command,
                cwd=WORKING_DIRECTORY,  # cwd = current working directory，代码执行时的工作目录
                shell=shell,
                executable=executable,
            )
        except TimeoutError as e:
            # 超时处理：代码跑太久被强制终止
            logger.error(f"Execution timeout: {e}")
            return {
                "result": "Timeout",
                "error": str(e),
                "file_path": code_file_path
            }

        # 捕获标准输出和标准错误
        output = result.output
        error_output = result.stderr

        if result.returncode == 0:
            # returncode=0 表示执行成功（Unix 惯例：0=成功，非0=失败）
            logger.info("Code executed successfully")
            return {
                "result": "Code executed successfully",
                "output": output + "\n\nIf you have completed all tasks, respond with FINAL ANSWER.",
                # 小白导读: 末尾的 "FINAL ANSWER" 提示告诉 Agent "任务完成了，输出最终答案"
                "file_path": code_file_path
            }
        else:
            # 执行失败：返回错误信息
            logger.error(f"Code execution failed: {error_output}")
            return {
                "result": "Failed to execute",
                "error": error_output,
                "file_path": code_file_path
            }
    except Exception as e:
        # 兜底错误处理：捕获所有未预料的异常，确保函数不崩溃
        logger.exception("An error occurred while executing code")
        return {
            "result": "Error occurred",
            "error": str(e),
            "file_path": code_file_path if 'code_file_path' in locals() else "Unknown"
        }

@tool  # 第二个工具：执行 shell 命令（如 pip install、ls、mkdir 等）
def execute_command(
    command: Annotated[str, "要执行的命令。"]
) -> Annotated[str, "命令的输出。"]:
    """
    在指定的 Conda 环境中执行命令并返回其输出。

    此函数会激活 Conda 环境，执行给定命令，
    并返回输出或执行过程中遇到的任何错误。
    请使用 pip install 安装包。

    假数据示例:
        输入: command="pip install numpy"
        输出: "Successfully installed numpy-1.24.0 ..."
    """
    logger.info(f"Tool invoked: execute_command, command:", command[:50])

    try:
        # 获取平台特定命令（同样用 conda run 包装）
        full_command, shell, executable = get_platform_specific_command(command)

        # logger.info(f"Executing command: {command}")

        # 执行命令并捕获输出
        # 小白导读: subprocess.run 是 Python 调用系统命令的标准方式
        # check=True 表示命令失败时抛出 CalledProcessError 异常
        # stdout=subprocess.PIPE 表示捕获输出（不打印到屏幕）
        result = subprocess.run(
            full_command,
            shell=shell,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,  # 以字符串形式返回输出（而非字节）
            executable=executable,
            cwd=WORKING_DIRECTORY
        )
        logger.info("Command executed successfully")
        return result.stdout
    except subprocess.CalledProcessError as e:
        # 命令执行失败（返回非零退出码）
        logger.error(f"Error executing command: {e.stderr}")
        return f"Error: {e.stderr}"

logger.info("Module initialized successfully")

@tool  # 第三个工具：列出目录内容（类似 ls 或 dir 命令）
def list_directory(directory: Annotated[str, "要列出内容的目录路径。"]
) -> Annotated[str, "目录内容"]:
    """列出指定目录的内容。

    假数据示例:
        输入: directory="/path/to/workdir"
        输出: "Directory contents:\nfile1.py\nfile2.csv\nsubdir"
    """

    logger.info(f"Tool invoked: list_directory, directory: {directory}")

    try:
        # 如果用户没给目录，默认列出工作目录
        if not directory:
            directory = WORKING_DIRECTORY
        logger.info(f"Listing contents of directory: {directory}")
        # os.listdir 返回目录下的文件和文件夹列表
        contents = os.listdir(directory)
        return f"Directory contents:\n" + "\n".join(contents)
    except Exception as e:
        return f"Error: {str(e)}"
