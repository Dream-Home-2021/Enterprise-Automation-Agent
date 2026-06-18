# -*- coding: utf-8 -*-

"""
基础数学工具 + DashScope 联网搜索工具
"""

import os
from langchain.tools import tool
from dashscope import Generation


@tool
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


@tool
def subtract(a: int, b: int) -> int:
    """Subtract b from a."""
    return a - b


@tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers together."""
    return a * b


@tool
def divide(a: int, b: int) -> float:
    """Divide a by b."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


@tool
def dashscope_search(query: str) -> str:
    """
    使用夸克搜索 API 搜索互联网信息。
    """
    response = Generation.call(
        model=os.getenv("OPENAI_MODEL", "qwen-plus-latest"),
        prompt=query,
        enable_search=True,
        result_format='message'
    )

    if response.status_code == 200:
        return response.output.choices[0].message.content
    else:
        return (
            "Search failed with status code: "
            f"{response.status_code}, message: {response.message}"
        )


# 工具列表
TOOLS = [add, subtract, multiply, divide, dashscope_search]