# ====================================================================
# 文件角色: 本地文件读写与编辑工具集
# 本文件提供五个可被 Agent 调用的 @tool 装饰函数 / 一个辅助类:
#   1. collect_data   —— 读取 CSV 文件（支持编码自动识别）
#   2. create_document—— 把字符串列表写成 Markdown 编号列表文件
#   3. read_document  —— 按行范围读取文件内容（含安全校验 + 行数限制）
#   4. write_document —— 一次性写入整个文件（含路径 / 内容校验）
#   5. edit_document  —— 在指定行号插入文本（批量、排序后插入）
#
# 小白导读:
# - CSV (Comma-Separated Values): 用逗号分隔的纯文本表格，类似 Excel 的 .csv。
# - Encoding (字符编码): 把字符映射为字节的规则，utf-8 是国际通用编码。
# - Annotated[str, "说明"]: 给参数加上文字说明，让 LLM 知道该传什么。
# - Pydantic BaseModel: 用于定义"参数模板"的类，自带类型校验。
#
# 与其他文件的协作:
# - src/config.py        : 导入 WORKING_DIRECTORY 作为文件操作的默认根目录
# - src/tools/validators  : 导入 PathValidator / ContentValidator 做安全校验
# - src/tools/tool_config: 导入 TOOL_CONFIG 读取文件大小 / 行数限制
# - 本文件导出的函数会被 src/tools/factory.py 注册供 Agent 使用
# ====================================================================

import os
from typing import Annotated, List
from pydantic import BaseModel, Field

from langchain_core.tools import tool
import pandas as pd  # pandas: 处理 CSV/Excel/表格数据的事实标准库

from ..logger import setup_logger
from ..config import WORKING_DIRECTORY

# Set up logger
logger = setup_logger()  # 初始化模块级logger，用于记录工具调用的运行日志

# Ensure the working directory exists
if not os.path.exists(WORKING_DIRECTORY):
    os.makedirs(WORKING_DIRECTORY)  # 小白导读: 如果工作目录不存在，自动创建它（首次启动时会执行）
    logger.info(f"Created working directory: {WORKING_DIRECTORY}")

def normalize_path(file_path: str) -> str:
    """
    Normalize file path for cross-platform compatibility.
    把任意路径统一转成绝对路径并清理斜杠 / 点号。

    小白导读: 不同操作系统 (\ vs /)、相对路径 vs 绝对路径，这个函数都帮你标准化。
    类比：把"我家"、"本栋 301"、"xx 路 8 号"统一转成"xx 市 xx 路 8 号"。
    """
    if WORKING_DIRECTORY not in file_path:
        file_path = os.path.join(WORKING_DIRECTORY, file_path)  # 小白导读: 把相对路径拼接到工作目录下
    return os.path.normpath(file_path)  # 小白导读: normpath 清理多余的斜杠、./、.. 等符号

@tool  # 小白导读: @tool 装饰器把这个函数注册为 Agent 可以调用的工具
def collect_data(
    data_path: Annotated[str, "Path to the CSV file"] = './data.csv',
    nrows: Annotated[int | None, "Number of rows to read"] = None,
    usecols: Annotated[list[str] | None, "List of column names to read"] = None,
    skiprows: Annotated[int | None, "Number of rows to skip at the beginning"] = None
) -> Annotated[pd.DataFrame, "The collected data from the CSV file"]:
    """
    Collect data from a CSV file with selective reading options.
    从 CSV 文件采集数据（支持编码识别、跳行、列筛选）。

    小白导读:
    - encoding: 字符编码，utf-8/latin1/... 不同文件可能用不同编码，逐个尝试。
    - nrows: 只读前 N 行；usecols: 只读指定列；skiprows: 跳过开头 N 行。

    假数据示例:
        输入: data_path="sample.csv", nrows=100, usecols=["age", "name"]
        输出: pd.DataFrame(...)
    """
    data_path = normalize_path(data_path)  # 小白导读: 先把相对路径转成绝对路径
    logger.info(f"Attempting to read CSV file: {data_path}")
    encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']  # 小白导读: 常见编码列表，按优先级逐个尝试
    for encoding in encodings:
        try:
            data = pd.read_csv(
                data_path,
                encoding=encoding,
                nrows=nrows,
                usecols=usecols,
                skiprows=skiprows
            )
            logger.info(f"Successfully read CSV file with encoding: {encoding}")
            return data
        except Exception as e:
            logger.warning(f"Error with encoding {encoding}: {e}")
    logger.error("Unable to read file with provided encodings")
    raise ValueError("Unable to read file with provided encodings")

@tool
def create_document(
    points: Annotated[List[str], "List of points to be included in the document"],
    file_name: Annotated[str, "Name of the file to save the document"]
) -> Annotated[str, "Message indicating where the document was saved"]:
    """
    Create and save a text document in Markdown format.
    把 points 列表按编号写入 Markdown 文件（每行一条）。

    假数据示例:
        输入: points=["第一点", "第二点"], file_name="outline.md"
        输出: "Outline saved to /path/to/outline.md"
        文件内容:
            1. 第一点
            2. 第二点
    """
    try:
        file_path = normalize_path(file_name)  # 小白导读: 统一处理路径
        logger.info(f"Creating document: {file_path}")
        with open(file_path, "w", encoding='utf-8') as file:
            for i, point in enumerate(points):  # 小白导读: enumerate 同时拿到索引 i 和元素 point
                file.write(f"{i + 1}. {point}\n")  # 写入"序号. 内容"格式
        logger.info(f"Document created successfully: {file_path}")
        return f"Outline saved to {file_path}"
    except Exception as e:
        logger.error(f"Error while saving outline: {str(e)}")
        return f"Error while saving outline: {str(e)}"

@tool
def read_document(
    file_name: Annotated[str, "Name of the file to read"],
    start: Annotated[int, "Starting line number (use 0 for beginning)"] = 0,
    end: Annotated[int, "Ending line number (use -1 for end of file)"] = -1
) -> Annotated[str, "Content of the document"]:
    """
    Read the specified document with security validation.
    从 start 到 end 行读取文件内容，含安全校验（路径、大小、扩展名）。

    小白导读:
    - PathValidator: 校验路径是否在黑名单、扩展名是否允许、文件大小是否超限。
    - 行数限制: 超过 TOOL_CONFIG.file_ops.max_read_lines 时自动截断并追加提醒文本。

    假数据示例:
        输入: file_name="code.py", start=10, end=20
        输出: "10\n11\n... (第 10 到 20 行内容)"
        输入: file_name="code.py", start=0, end=-1
        输出: (文件全部内容)
    """
    from .validators import PathValidator
    from .tool_config import TOOL_CONFIG

    try:
        file_path = normalize_path(file_name)  # 小白导读: 统一路径
        
        # === VALIDATION === 安全校验门，不通过直接返回错误
        try:
            PathValidator.validate_read(file_path)  # 小白导读: 校验路径黑名单 / 扩展名 / 文件大小
        except (PermissionError, ValueError) as e:
            logger.warning(f"Read validation failed for {file_path}: {e}")
            return f"Error: {e}"

        with open(file_path, "r", encoding='utf-8') as file:
            lines = file.readlines()  # 小白导读: readlines 按行读取，返回字符串列表
        
        # Apply line limit 行数限制：超过配置的最大行数时截断
        max_lines = TOOL_CONFIG.file_ops.max_read_lines  # 小白导读: 从全局配置读最大行数
        if len(lines) > max_lines:
            lines = lines[:max_lines]  # 切片：只保留前 max_lines 行
            truncated_notice = f"\n\n... [TRUNCATED: showing first {max_lines} lines]"  # 提示 Agent 内容被截断
        else:
            truncated_notice = ""
        
        # Handle special values 拼接内容
        if start == 0 and end == -1:
            content = "".join(lines)  # 全部内容直接拼接
        elif end == -1:
            content = "".join(lines[start:])  # 从 start 到结尾
        else:
            content = "".join(lines[start:end])  # 从 start 到 end 之间
            
        return content + truncated_notice
    except Exception as e:
        return f"Error: {str(e)}"

@tool
def write_document(
    content: Annotated[str, "Content to be written to the document"],
    file_name: Annotated[str, "Name of the file to save the document"]
) -> Annotated[str, "Message indicating where the document was saved"]:
    """
    Create and save a Markdown document with validation.
    一次性把 content 写入文件，含路径 / 内容安全校验。

    小白导读:
    - PathValidator: 校验路径 / 扩展名是否合规。
    - ContentValidator: 校验体积、敏感信息、TODO 等残缺标记。

    假数据示例:
        输入: content="# 标题\n正文", file_name="readme.md"
        输出: "Document saved to /path/to/readme.md"
    """
    from .validators import PathValidator, ContentValidator

    try:
        file_path = normalize_path(file_name)
        
        # === PATH VALIDATION === 路径校验
        try:
            PathValidator.validate_write(file_path)
        except PermissionError as e:
            logger.warning(f"Write path validation failed: {e}")
            return f"Error: {e}"

        # === CONTENT VALIDATION === 内容校验
        is_valid, message = ContentValidator.validate_and_log(content, file_path)  # 小白导读: 返回 (是否通过, 警告消息)
        if not is_valid:
            return f"Error: {message}"

        logger.info(f"Writing document: {file_path}")
        with open(file_path, "w", encoding='utf-8') as file:
            file.write(content)  # 小白导读: 一次性写入整个字符串
        logger.info(f"Document written successfully: {file_path}")
        
        result = f"Document saved to {file_path}"
        if message:  # Warnings 有警告时追加到结果里
            result += f" ({message})"
        return result
    except Exception as e:
        logger.error(f"Error while saving document: {str(e)}")
        return f"Error while saving document: {str(e)}"

class LineInsert(BaseModel):
    """edit_document 的插入参数模型"""
    line_number: int = Field(description="Line number to insert at")  # 小白导读: 插入到的目标行号
    text: str = Field(description="Text to insert")  # 小白导读: 要插入的文本内容


@tool
def edit_document(
    file_name: Annotated[str, "Name of the file to edit"],
    inserts: Annotated[List[LineInsert], "List of line insertions"]
) -> Annotated[str, "Message indicating where the document was saved"]:
    """Edit a document by inserting text at specific line numbers.
    在指定行号位置批量插入文本。

    内部逻辑:
      1. 用字典去重：同名 line_number 只保留最后一条
      2. 按行号升序排序后逐个 insert，不会导致行号错乱

    假数据示例:
        输入: file_name="a.md", inserts=[{line_number:2, text:"(插入内容)"}]
        原文件: "1. 首行\n2. 次行\n3. 末行\n"
        结果文件: "1. 首行\n(插入内容)\n2. 次行\n3. 末行\n"
    """
    try:
        file_path = normalize_path(file_name)
        with open(file_path, "r", encoding='utf-8') as file:
            lines = file.readlines()  # 小白导读: 读取所有行

        inserts_dict = {insert.line_number: insert.text for insert in inserts}  # 小白导读: 同 line_number 时后者覆盖前者
        sorted_inserts = sorted(inserts_dict.items())  # 小白导读: 按行号从小到大排序

        for line_number, text in sorted_inserts:
            if 1 <= line_number <= len(lines) + 1:
                lines.insert(line_number - 1, text + "\n")  # 小白导读: list.insert(index, value) 在指定位置插入
        
        with open(file_path, "w", encoding='utf-8') as file:
            file.writelines(lines)  # 小白导读: 把修改后的 lines 写回文件
        
        return f"Document edited and saved to {file_path}"
    except Exception as e:
        return f"Error while editing document: {str(e)}"


logger.info("Document management tools initialized")