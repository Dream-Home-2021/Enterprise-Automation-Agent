import os
import platform
from typing import Annotated
import subprocess

# LangChain 的 @tool 装饰器：把函数注册成 Agent 可调用的工具
from langchain_core.tools import tool

from ..logger import setup_logger
from ..config import WORKING_DIRECTORY, CONDA_ENV



# 初始化日志器：所有工具调用都会留下日志，方便调试和审计
logger = setup_logger()

# 确保存储目录存在：如果工作目录不存在就自动创建
if not os.path.exists(WORKING_DIRECTORY):
    os.makedirs(WORKING_DIRECTORY)
    logger.info(f"Created storage directory: {WORKING_DIRECTORY}")


def get_platform_specific_command(command: str) -> tuple:
    """ conda run
    """
    # 构造 conda run 命令：在指定环境中执行用户命令
    conda_command = f"conda run -n {CONDA_ENV} {command}"

    system = platform.system().lower()
    if system == "windows":
        return (conda_command, True, None)
    else:
        return (conda_command, True, "/bin/bash")


@tool
def execute_code(
    input_code: Annotated[str, "要执行的 Python 代码。"],
    codefile_name: Annotated[str, "Python 代码文件名或完整路径。"] = 'code.py',
    timeout: Annotated[int | None, "执行超时时间（秒）。None 表示无限制。"] = None,
    memory_mb: Annotated[int | None, "内存限制（MB，仅 Linux）。None 表示无限制。"] = None,
    progress_timeout: Annotated[int | None, "无输出 N 秒后超时。适用于 ML/DL。"] = None,

) -> Annotated[dict, "包含输出和文件路径的执行结果"]:
    """

    Args:
        input_code: 要执行的 Python 代码。
        codefile_name: 保存代码的文件名（默认：code.py）。
        timeout: 固定超时秒数。None 表示无限制。
        memory_mb: 内存限制（仅 Linux）。None 表示无限制。
        progress_timeout: 无 stdout 输出 N 秒后超时（适用于长时间 ML/DL 任务）。

    Returns:
        包含结果状态、输出/错误、文件路径的字典。
    """
    from .tool_config import TOOL_CONFIG
    from .security import SecurityScanner, ResourceLimiter



    logger.info("Tool invoked: execute_code, input_code:", input_code[:50])


    code_file_path = None
    try:

        if TOOL_CONFIG.enable_security_scan:
            scan_result = SecurityScanner().scan_code(input_code)
            if not scan_result.is_safe:
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


        if os.path.isabs(codefile_name):
            code_file_path = codefile_name
        else:
            if WORKING_DIRECTORY not in codefile_name:
                code_file_path = os.path.join(WORKING_DIRECTORY, codefile_name)
            else:
                code_file_path = codefile_name

        # 标准化路径：处理 .. 和多余的斜杠，如 /a/b/../c -> /a/c
        code_file_path = os.path.normpath(code_file_path)

        logger.info(f"Code will be written to file: {code_file_path}")


        with open(code_file_path, 'w', encoding='utf-8') as code_file:
            code_file.write(input_code)

        logger.info(f"Code has been written to file: {code_file_path}")

        python_cmd = f"python {codefile_name}"
        full_command, shell, executable = get_platform_specific_command(python_cmd)

        logger.info(f"Executing command: {full_command}")

        # ===== 带资源限制执行 =====

        limiter = ResourceLimiter(
            timeout=timeout,
            memory_mb=memory_mb,
            progress_timeout=progress_timeout,
        )

        try:
            result = limiter.execute(
                command=full_command,
                cwd=WORKING_DIRECTORY,
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

        output = result.output
        error_output = result.stderr

        if result.returncode == 0:
            logger.info("Code executed successfully")
            return {
                "result": "Code executed successfully",
                "output": output + "\n\nIf you have completed all tasks, respond with FINAL ANSWER.",

                "file_path": code_file_path
            }
        else:
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

@tool
def execute_command(
    command: Annotated[str, "要执行的命令。"]
) -> Annotated[str, "命令的输出。"]:
    """
    """
    logger.info(f"Tool invoked: execute_command, command:", command[:50])

    try:
        full_command, shell, executable = get_platform_specific_command(command)
        result = subprocess.run(
            full_command,
            shell=shell,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            executable=executable,
            cwd=WORKING_DIRECTORY
        )
        logger.info("Command executed successfully")
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Error executing command: {e.stderr}")
        return f"Error: {e.stderr}"

logger.info("Module initialized successfully")

@tool
def list_directory(directory: Annotated[str, "要列出内容的目录路径。"]
) -> Annotated[str, "目录内容"]:
    """
    """

    logger.info(f"Tool invoked: list_directory, directory: {directory}")

    try:
        if not directory:
            directory = WORKING_DIRECTORY
        logger.info(f"Listing contents of directory: {directory}")
        # os.listdir 返回目录下的文件和文件夹列表
        contents = os.listdir(directory)
        return f"Directory contents:\n" + "\n".join(contents)
    except Exception as e:
        return f"Error: {str(e)}"
