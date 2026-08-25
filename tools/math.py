from langchain.tools import tool
from dashscope import Generation

from utils.log import get_logger

logger = get_logger(__name__)

# DashScope Generation.call 使用模型名（不支持 -latest 后缀）
_DASHSCOPE_MODEL = "qwen-plus"


@tool
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    result = a + b
    logger.debug("add(%d, %d) = %d", a, b, result)
    return result


@tool
def subtract(a: int, b: int) -> int:
    """Subtract b from a."""
    result = a - b
    logger.debug("subtract(%d, %d) = %d", a, b, result)
    return result


@tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers together."""
    result = a * b
    logger.debug("multiply(%d, %d) = %d", a, b, result)
    return result


@tool
def divide(a: int, b: int) -> float:
    """Divide a by b."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    result = a / b
    logger.debug("divide(%d, %d) = %.2f", a, b, result)
    return result


@tool
def dashscope_search(query: str) -> str:
    """使用夸克搜索 API 搜索互联网信息。"""
    logger.info("search: %s", query[:80])
    response = Generation.call(
        model=_DASHSCOPE_MODEL,
        prompt=query,
        enable_search=True,
        result_format="message",
    )
    if response.status_code == 200:
        content = response.output.choices[0].message.content
        logger.info("search OK: %d chars", len(content))
        return content

    logger.warning("search failed: %s", response.message)
    return f"搜索失败 (HTTP {response.status_code}): {response.message}"


TOOLS = [add, subtract, multiply, divide, dashscope_search]