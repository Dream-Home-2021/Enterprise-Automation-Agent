"""
MCP Server 注册与工具映射 (Function Calling)

职责：
  - 注册可被 Data Agent 调用的工具函数
  - 定义工具的输入/输出 Schema
  - 通过 MCP 标准协议暴露给客户端
"""

import json
from typing import Any


# ---------------------------------------------------------------------------
# 工具定义
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "execute_python",
        "description": "在隔离 Docker 沙箱中执行 Python 代码（pandas, numpy 等），用于数据分析。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "要执行的 Python 代码",
                },
                "file_path": {
                    "type": "string",
                    "description": "需要读取的数据文件路径",
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "read_file",
        "description": "读取沙箱内指定文件的内容（仅读操作，需审批）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "list_files",
        "description": "列出沙箱工作目录下的文件。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "目录路径，默认 /workspace",
                    "default": "/workspace",
                },
            },
        },
    },
]


def get_tools() -> list[dict]:
    """返回所有注册工具的 Schema"""
    return TOOLS


async def handle_tool_call(tool_name: str, arguments: dict) -> dict:
    """
    工具调用分发器

    Args:
        tool_name: 工具名称
        arguments: 工具参数

    Returns:
        执行结果
    """
    if tool_name == "execute_python":
        from src.mcp.client import execute_in_sandbox
        return await execute_in_sandbox(
            code=arguments.get("code", ""),
            file_path=arguments.get("file_path", ""),
        )

    elif tool_name == "read_file":
        from src.mcp.client import read_file_from_sandbox
        return await read_file_from_sandbox(
            file_path=arguments.get("file_path", ""),
        )

    elif tool_name == "list_files":
        from src.mcp.client import list_sandbox_files
        return await list_sandbox_files(
            directory=arguments.get("directory", "/workspace"),
        )

    else:
        return {"error": f"Unknown tool: {tool_name}"}
