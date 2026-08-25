import os
from typing import Annotated, List
from pydantic import BaseModel, Field

from langchain_core.tools import tool
import pandas as pd

from ..logger import setup_logger
from ..config import WORKING_DIRECTORY

logger = setup_logger()

# Ensure the working directory exists 确保工作目录存在，若不存在则自动创建
if not os.path.exists(WORKING_DIRECTORY):
    os.makedirs(WORKING_DIRECTORY)
    logger.info(f"Created working directory: {WORKING_DIRECTORY}")

def normalize_path(file_path: str) -> str:
    """
    """
    if WORKING_DIRECTORY not in file_path:
        file_path = os.path.join(WORKING_DIRECTORY, file_path)
    return os.path.normpath(file_path)

@tool
def collect_data(
    data_path: Annotated[str, "Path to the CSV file"] = './data.csv',
    nrows: Annotated[int | None, "Number of rows to read"] = None,
    usecols: Annotated[list[str] | None, "List of column names to read"] = None,
    skiprows: Annotated[int | None, "Number of rows to skip at the beginning"] = None
) -> Annotated[pd.DataFrame, "The collected data from the CSV file"]:
    """
    Collect data from a CSV file with selective reading options.
    """
    data_path = normalize_path(data_path)
    logger.info(f"Attempting to read CSV file: {data_path}")

    # 常见文本编码列表，按尝试顺序排列；不同系统保存 CSV 时可能使用不同编码
    # utf-8-sig 优先（兼容 Excel 生成的带 BOM 的 UTF-8 文件）
    # gbk / gb2312 覆盖国内 Windows 下 Office 保存的中文 CSV
    encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'latin1', 'iso-8859-1', 'cp1252']

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
            # 当前编码失败，记录警告并尝试下一个编码
            logger.warning(f"Error with encoding {encoding}: {e}")

    # 所有编码都失败，抛出值错误
    logger.error("Unable to read file with provided encodings")
    raise ValueError("Unable to read file with provided encodings")

@tool
def create_document(
    points: Annotated[List[str], "List of points to be included in the document"],
    file_name: Annotated[str, "Name of the file to save the document"]
) -> Annotated[str, "Message indicating where the document was saved"]:
    """
    Create and save a text document in Markdown format.
    """
    try:
        file_path = normalize_path(file_name)
        logger.info(f"Creating document: {file_path}")

        with open(file_path, "w", encoding='utf-8') as file:
            for i, point in enumerate(points):
                file.write(f"{i + 1}. {point}\n")

        logger.info(f"Document created successfully: {file_path}")
        return f"Outline saved to {file_path}"
    except Exception as e:
        # 捕获所有异常（如权限错误、磁盘满等），记录并返回错误消息
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
    """
    from .validators import PathValidator
    from .tool_config import TOOL_CONFIG

    try:
        file_path = normalize_path(file_name)

        try:
            PathValidator.validate_read(file_path)
        except (PermissionError, ValueError) as e:
            logger.warning(f"Read validation failed for {file_path}: {e}")
            return f"Error: {e}"

        # 以只读模式打开文件，读取所有行到列表中
        with open(file_path, "r", encoding='utf-8') as file:
            lines = file.readlines()

        max_lines = TOOL_CONFIG.file_ops.max_read_lines
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            truncated_notice = f"\n\n... [TRUNCATED: showing first {max_lines} lines]"
        else:
            truncated_notice = ""

        # Handle special values 根据 start 和 end 参数提取指定范围的行
        if start == 0 and end == -1:
            content = "".join(lines)
        elif end == -1:
            content = "".join(lines[start:])
        else:
            content = "".join(lines[start:end])

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
    """
    from .validators import PathValidator, ContentValidator

    try:
        file_path = normalize_path(file_name)

        try:
            PathValidator.validate_write(file_path)
        except PermissionError as e:
            logger.warning(f"Write path validation failed: {e}")
            return f"Error: {e}"

        # === CONTENT VALIDATION === 内容质量校验
        is_valid, message = ContentValidator.validate_and_log(content, file_path)
        if not is_valid:
            return f"Error: {message}"

        logger.info(f"Writing document: {file_path}")
        with open(file_path, "w", encoding='utf-8') as file:
            file.write(content)
        logger.info(f"Document written successfully: {file_path}")

        result = f"Document saved to {file_path}"
        if message:  # Warnings 如果存在警告信息（如检测到 TODO/FIXME），附加到结果中
            result += f" ({message})"
        return result
    except Exception as e:
        logger.error(f"Error while saving document: {str(e)}")
        return f"Error while saving document: {str(e)}"

class LineInsert(BaseModel):
    """
    """
    line_number: int = Field(description="Line number to insert at")
    text: str = Field(description="Text to insert")


@tool
def edit_document(
    file_name: Annotated[str, "Name of the file to edit"],
    inserts: Annotated[List[LineInsert], "List of line insertions"]
) -> Annotated[str, "Message indicating where the document was saved"]:
    """
    Edit a document by inserting text at specific line numbers.
    """
    try:
        file_path = normalize_path(file_name)

        with open(file_path, "r", encoding='utf-8') as file:
            lines = file.readlines()

        inserts_dict = {insert.line_number: insert.text for insert in inserts}
        sorted_inserts = sorted(inserts_dict.items())

        for line_number, text in sorted_inserts:
            # 检查行号是否在有效范围内（1 到 len(lines)+1 之间）
            if 1 <= line_number <= len(lines) + 1:
                lines.insert(line_number - 1, text + "\n")

        with open(file_path, "w", encoding='utf-8') as file:
            file.writelines(lines)

        return f"Document edited and saved to {file_path}"
    except Exception as e:
        return f"Error while editing document: {str(e)}"


logger.info("Document management tools initialized")
