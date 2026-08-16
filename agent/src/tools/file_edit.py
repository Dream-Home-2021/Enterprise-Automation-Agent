# ============================================================================
# 文件角色: 本文件是"文档/文件操作工具集"的实现层，为 Agent (智能体) 提供读写 CSV、
#       Markdown 文档、按行插入等基础能力。它属于工具层 (Tools Layer)，被
#       Agent 通过 MCP/Tool Calling 方式调用。
#
# 小白导读:
#   - MCP: Model Context Protocol，是 AI 模型与外部工具/数据源交互的开放协议。
#          类比: 就像 USB 接口之于硬件设备，MCP 是 AI 软件的"标准接口"。
#   - Tool: 工具，AI Agent 可调用的一个函数。类比: 手机 App 里的一个按钮，
#           Agent 点按钮就执行对应操作。
#   - Agent: 智能体，能够自主决策、调用工具完成任务的 AI 程序。
#             类比: 一个有自己的"大脑(LLM)"和"手脚(Tool)"的虚拟员工。
#   - LLM: Large Language Model，大语言模型，Agent 的"大脑"。
#   - Tool Calling: LLM 选择并调用工具的过程，类似程序员调用函数库。
#   - Annotated: Python 类型标注的增强版，用来给工具参数加描述，帮助 LLM 理解参数用途。
#   - Pydantic: 一个数据校验框架，确保输入数据符合预期格式。
#
# 阅读指南:
#   1. 先看 normalize_path(): 理解"工作目录"的概念——所有文件操作都在 WORKING_DIRECTORY 下进行。
#   2. 再看 @tool 装饰的四个工具函数 (collect_data / create_document / read_document / write_document / edit_document)，
#      它们是本文件的核心能力。
#   3. 最后看 LineInsert 数据类，理解"按行插入"的输入结构。
#
# 文件协作:
#   - 导入自 ..config (WORKING_DIRECTORY)  → 全局配置
#   - 导入自 ..logger (setup_logger)       → 日志系统
#   - 延迟导入 .validators (PathValidator, ContentValidator)  → 安全校验
#   - 延迟导入 .tool_config (TOOL_CONFIG)  → 工具运行时配置
#   - 被 tools/factory.py 注册为可被 Agent 调用的 Tool
# ============================================================================

import os  # 操作系统接口，用于路径拼接、文件存在性检查
from typing import Annotated, List  # Annotated: 类型注解增强；List: 列表类型
from pydantic import BaseModel, Field  # BaseModel: 数据模型基类；Field: 字段元数据

from langchain_core.tools import tool  # @tool 装饰器：将普通函数注册为 LangChain Tool，供 Agent 调用
import pandas as pd  # 数据处理库，用于读取 CSV 文件

from ..logger import setup_logger  # 从父级包导入日志初始化函数
from ..config import WORKING_DIRECTORY  # 全局工作目录路径（所有文件操作都被限制在此目录下）

# Set up logger 初始化日志系统，后续所有操作都会记录日志
logger = setup_logger()

# Ensure the working directory exists 确保工作目录存在，若不存在则自动创建
# 类比: 就像你写作业前先把书桌准备好
if not os.path.exists(WORKING_DIRECTORY):  # 检查工作目录路径是否已经存在
    os.makedirs(WORKING_DIRECTORY)  # 递归创建目录（包括中间缺失的父目录）
    logger.info(f"Created working directory: {WORKING_DIRECTORY}")  # 记录创建日志

def normalize_path(file_path: str) -> str:
    """
    规范化文件路径，确保跨平台兼容性。

    如果 file_path 不在 WORKING_DIRECTORY 下，则自动拼接工作目录。
    最终通过 os.path.normpath 清理多余的斜杠与相对路径符号（如 ./  ../）。

    小白导读: 这个函数是"守门员"，所有文件操作都要先经过它处理路径。

    假数据示例:
        输入: file_path="data.csv"
         normalize_path → "D:/GameDownload/DATAGEN/workspace/data.csv"
        输入: file_path="D:/GameDownload/DATAGEN/workspace/data.csv"
        输出: "D:/GameDownload/DATAGEN/workspace/data.csv" (原样返回)
    """
    # 如果路径中没有工作目录前缀，说明是相对路径，自动补全为绝对路径
    if WORKING_DIRECTORY not in file_path:
        file_path = os.path.join(WORKING_DIRECTORY, file_path)  # 拼接工作目录与相对路径
    return os.path.normpath(file_path)  # 规范化路径（处理斜杠、去除冗余部分）

@tool  # LangChain 工具装饰器，将函数注册为 Agent 可调用的工具
def collect_data(
    data_path: Annotated[str, "Path to the CSV file"] = './data.csv',  # CSV 文件路径，默认为当前目录下 data.csv
    nrows: Annotated[int | None, "Number of rows to read"] = None,  # 读取行数限制（None 表示全部）
    usecols: Annotated[list[str] | None, "List of column names to read"] = None,  # 指定要读取的列名列表
    skiprows: Annotated[int | None, "Number of rows to skip at the beginning"] = None  # 跳过开头若干行
) -> Annotated[pd.DataFrame, "The collected data from the CSV file"]:  # 返回值类型为 pandas DataFrame
    """
    Collect data from a CSV file with selective reading options.
    从 CSV 文件中采集数据，支持选择性读取（指定列数、列名、跳行）。

    小白导读: CSV 就像 Excel 表格的纯文本版，用逗号分隔每一列。
    pandas 是 Python 最常用的数据分析库，DataFrame 相当于内存中的一张二维表格。

    假数据示例:
        输入: data_path="sample.csv", nrows=10, usecols=["name", "age"], skiprows=None
        输出: 一个 pandas DataFrame 对象，包含 name 和 age 两列共 10 行数据
    """
    data_path = normalize_path(data_path)  # 规范化路径：确保路径在工作目录下
    logger.info(f"Attempting to read CSV file: {data_path}")  # 记录尝试读取的日志

    # 常见文本编码列表，按尝试顺序排列；不同系统保存 CSV 时可能使用不同编码
    # utf-8-sig 优先（兼容 Excel 生成的带 BOM 的 UTF-8 文件）
    # gbk / gb2312 覆盖国内 Windows 下 Office 保存的中文 CSV
    encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'latin1', 'iso-8859-1', 'cp1252']

    # 遍历各种编码尝试读取，直到成功为止
    for encoding in encodings:
        try:
            data = pd.read_csv(  # pandas 读取 CSV 的核心函数
                data_path,  # 文件路径
                encoding=encoding,  # 当前尝试的编码
                nrows=nrows,  # 限制读取行数（None 表示全部）
                usecols=usecols,  # 仅读取指定列（None 表示所有列）
                skiprows=skiprows  # 跳过开头的行数
            )
            logger.info(f"Successfully read CSV file with encoding: {encoding}")  # 成功日志
            return data  # 返回读取到的 DataFrame
        except Exception as e:
            # 当前编码失败，记录警告并尝试下一个编码
            logger.warning(f"Error with encoding {encoding}: {e}")

    # 所有编码都失败，抛出值错误
    logger.error("Unable to read file with provided encodings")  # 记录错误日志
    raise ValueError("Unable to read file with provided encodings")  # 抛出异常让 Agent 知道失败原因

@tool  # 工具装饰器：将此函数暴露给 Agent 调用
def create_document(
    points: Annotated[List[str], "List of points to be included in the document"],  # 文档要点列表
    file_name: Annotated[str, "Name of the file to save the document"]  # 保存的文件名
) -> Annotated[str, "Message indicating where the document was saved"]:  # 返回保存路径消息
    """
    Create and save a text document in Markdown format.
    创建并保存一个 Markdown 格式的文本文档。

    此函数接收一个字符串列表，将每个字符串作为一条编号条目写入 Markdown 文件。

    小白导读: Markdown 是一种轻量级标记语言，用纯文本就能写出格式化的文档。
             例如 "# 标题" 会被渲染为大号标题。

    假数据示例:
        输入: points=["第一章 引言", "第二章 方法", "第三章 结果"], file_name="outline.md"
        输出: 文件 outline.md 内容为:
            1. 第一章 引言
            2. 第二章 方法
            3. 第三章 结果
        返回值: "Outline saved to D:/GameDownload/DATAGEN/workspace/outline.md"
    """
    try:
        file_path = normalize_path(file_name)  # 规范化文件路径
        logger.info(f"Creating document: {file_path}")  # 记录创建日志

        # 以写入模式打开文件（"w" 会覆盖已有文件），指定 UTF-8 编码
        with open(file_path, "w", encoding='utf-8') as file:
            for i, point in enumerate(points):  # enumerate 同时获取索引和值
                file.write(f"{i + 1}. {point}\n")  # 写入编号条目并换行

        logger.info(f"Document created successfully: {file_path}")  # 成功日志
        return f"Outline saved to {file_path}"  # 返回成功消息
    except Exception as e:
        # 捕获所有异常（如权限错误、磁盘满等），记录并返回错误消息
        logger.error(f"Error while saving outline: {str(e)}")  # 记录错误日志
        return f"Error while saving outline: {str(e)}"  # 返回错误消息给 Agent

@tool  # 工具装饰器：注册为 Agent 可调用的读取工具
def read_document(
    file_name: Annotated[str, "Name of the file to read"],  # 要读取的文件名
    start: Annotated[int, "Starting line number (use 0 for beginning)"] = 0,  # 起始行号（0 表示从头）
    end: Annotated[int, "Ending line number (use -1 for end of file)"] = -1  # 结束行号（-1 表示到末尾）
) -> Annotated[str, "Content of the document"]:  # 返回文档内容字符串
    """
    Read the specified document with security validation.
    读取指定文档，附带安全校验。

    安全特性:
    - 路径校验 (blocked paths check): 禁止读取系统敏感路径
    - 文件大小校验: 防止读取过大的文件耗尽内存
    - 行数限制: 截断超长文件，避免一次性返回过多内容

    小白导读: 这些安全检查就像小区门禁——不是谁都能进，也不是什么都能拿。

    假数据示例:
        假设 file.md 内容为:
            Line 1: Hello
            Line 2: World
            Line 3: Goodbye
        输入: file_name="file.md", start=1, end=3
        输出: "Line 2: World\nLine 3: Goodbye\n"
    """
    from .validators import PathValidator  # 延迟导入路径校验器（避免循环依赖）
    from .tool_config import TOOL_CONFIG  # 延迟导入工具配置（获取最大读取行数）

    try:
        file_path = normalize_path(file_name)  # 规范化路径

        # === VALIDATION === 路径安全校验阶段
        try:
            PathValidator.validate_read(file_path)  # 校验是否允许读取该路径
        except (PermissionError, ValueError) as e:
            # 校验失败（如路径被禁止、文件不存在），记录警告并返回错误消息
            logger.warning(f"Read validation failed for {file_path}: {e}")
            return f"Error: {e}"

        # 以只读模式打开文件，读取所有行到列表中
        with open(file_path, "r", encoding='utf-8') as file:
            lines = file.readlines()  # readlines() 返回每行作为元素的列表

        # Apply line limit 应用行数限制：防止文件过大导致 Agent 上下文溢出
        max_lines = TOOL_CONFIG.file_ops.max_read_lines  # 从配置中获取最大允许读取行数
        if len(lines) > max_lines:
            lines = lines[:max_lines]  # 截取前 max_lines 行
            truncated_notice = f"\n\n... [TRUNCATED: showing first {max_lines} lines]"  # 截断提示
        else:
            truncated_notice = ""  # 未超出限制则无需提示

        # Handle special values 根据 start 和 end 参数提取指定范围的行
        if start == 0 and end == -1:
            content = "".join(lines)  # 从头到尾：返回全部内容
        elif end == -1:
            content = "".join(lines[start:])  # end 为 -1 时：从 start 到末尾
        else:
            content = "".join(lines[start:end])  # 指定起止范围

        return content + truncated_notice  # 返回内容并附加截断提示（如有）
    except Exception as e:
        return f"Error: {str(e)}"  # 捕获所有异常并返回错误消息

@tool  # 工具装饰器：注册写入工具
def write_document(
    content: Annotated[str, "Content to be written to the document"],  # 要写入的文档内容
    file_name: Annotated[str, "Name of the file to save the document"]  # 保存的文件名
) -> Annotated[str, "Message indicating where the document was saved"]:  # 返回保存结果消息
    """
    Create and save a Markdown document with validation.
    创建并保存 Markdown 文档，附带安全校验。

    安全特性:
    - 路径校验 (blocked paths check): 禁止写入系统敏感路径
    - 内容大小校验: 防止写入过大的内容耗尽磁盘
    - 内容质量警告 (TODO/FIXME detection): 检测并警告包含 TODO/FIXME 的占位内容

    小白导读: TODO/FIXME 是程序员在代码中留下的"待办事项"标记。
             如果文档中包含这些标记，说明内容可能还不完整。

    假数据示例:
        输入: content="# 周报\n本周完成了模块A的开发。", file_name="weekly.md"
        输出: 文件 weekly.md 被写入上述内容
        返回值: "Document saved to D:/GameDownload/DATAGEN/workspace/weekly.md"
    """
    from .validators import PathValidator, ContentValidator  # 延迟导入路径与内容校验器

    try:
        file_path = normalize_path(file_name)  # 规范化路径

        # === PATH VALIDATION === 路径安全校验
        try:
            PathValidator.validate_write(file_path)  # 校验是否允许写入该路径
        except PermissionError as e:
            logger.warning(f"Write path validation failed: {e}")  # 记录警告
            return f"Error: {e}"  # 返回错误消息

        # === CONTENT VALIDATION === 内容质量校验
        is_valid, message = ContentValidator.validate_and_log(content, file_path)  # 校验内容并记录日志
        if not is_valid:
            return f"Error: {message}"  # 内容校验失败则返回错误

        logger.info(f"Writing document: {file_path}")  # 记录写入日志
        with open(file_path, "w", encoding='utf-8') as file:  # 以写入模式打开文件
            file.write(content)  # 将内容写入文件
        logger.info(f"Document written successfully: {file_path}")  # 成功日志

        result = f"Document saved to {file_path}"  # 构造成功消息
        if message:  # Warnings 如果存在警告信息（如检测到 TODO/FIXME），附加到结果中
            result += f" ({message})"
        return result
    except Exception as e:
        logger.error(f"Error while saving document: {str(e)}")  # 记录错误日志
        return f"Error while saving document: {str(e)}"  # 返回错误消息

class LineInsert(BaseModel):
    """
    单行插入操作的数据模型。

    小白导读: Pydantic 的 BaseModel 就像一个"模板"，确保每个 LineInsert 对象
             都包含 line_number 和 text 两个字段，且类型正确。

    假数据示例:
        LineInsert(line_number=3, text="这是新插入的第三行")
    """
    line_number: int = Field(description="Line number to insert at")  # 要插入的行号（1-based）
    text: str = Field(description="Text to insert")  # 要插入的文本内容


@tool  # 工具装饰器：注册按行插入工具
def edit_document(
    file_name: Annotated[str, "Name of the file to edit"],  # 要编辑的文件名
    inserts: Annotated[List[LineInsert], "List of line insertions"]  # 插入操作列表
) -> Annotated[str, "Message indicating where the document was saved"]:  # 返回编辑结果
    """
    Edit a document by inserting text at specific line numbers.
    通过在指定行号插入文本来编辑文档。

    注意: 行号从 1 开始计数（1-based），插入后后续行号会自动顺延。

    小白导读: 这个函数就像在 Word 文档里"在某行前面插入一行"。
             如果同时插入多行，会按行号从小到大依次插入。

    假数据示例:
        假设 original.txt 内容为:
            Line A
            Line B
            Line C
        输入: file_name="original.txt",
              inserts=[LineInsert(line_number=2, text="Line B.5"),
                       LineInsert(line_number=4, text="Line C.5")]
        输出: 文件内容变为:
            Line A
            Line B.5
            Line B
            Line C.5
            Line C
        返回值: "Document edited and saved to D:/GameDownload/DATAGEN/workspace/original.txt"
    """
    try:
        file_path = normalize_path(file_name)  # 规范化路径

        # 读取文件所有行
        with open(file_path, "r", encoding='utf-8') as file:
            lines = file.readlines()  # 每行作为列表的一个元素

        # 将 LineInsert 列表转换为字典（以 line_number 为键），再按键排序
        # 排序确保从前往后插入，避免行号错乱
        inserts_dict = {insert.line_number: insert.text for insert in inserts}  # 字典推导式
        sorted_inserts = sorted(inserts_dict.items())  # 按行号升序排序

        # 依次插入每一行
        for line_number, text in sorted_inserts:
            # 检查行号是否在有效范围内（1 到 len(lines)+1 之间）
            if 1 <= line_number <= len(lines) + 1:
                lines.insert(line_number - 1, text + "\n")  # list.insert 在指定索引前插入元素

        # 写回文件
        with open(file_path, "w", encoding='utf-8') as file:
            file.writelines(lines)  # 将整个行列表写回文件

        return f"Document edited and saved to {file_path}"  # 返回成功消息
    except Exception as e:
        return f"Error while editing document: {str(e)}"  # 捕获异常并返回错误消息


# 模块加载完成日志，表示所有工具函数已注册完毕
logger.info("Document management tools initialized")
