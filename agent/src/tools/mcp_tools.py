# ====================================================================
# 文件角色: MCP (Model Context Protocol) 工具的 LangChain 适配器层
#
# 本文件负责把 MCP 服务器提供的"工具"包装成 LangChain 框架能识别的"工具"，
# 让 AI Agent 可以像调用本地函数一样调用远程 MCP 服务器上的工具。
#
# 小白导读:
# - MCP (Model Context Protocol): 一种标准协议，让 AI 模型能调用外部工具/数据源。
#   类比: MCP 就像 AI 世界的"USB接口"，统一了各种外部工具的接入方式。
# - Tool (工具): AI Agent 可以调用的一个功能单元，比如读文件、搜索网页、执行命令。
#   类比: Tool 就像手机 App 里的一个"功能按钮"，点击就能执行特定任务。
# - Agent (智能体): 能自主决策、调用工具完成复杂任务的 AI 系统。
#   类比: Agent 就像一个"项目管家"，自己决定用什么工具、按什么顺序完成任务。
# - LLM (大语言模型): 驱动 Agent 思考和决策的 AI 核心大脑。
#   类比: LLM 就像 Agent 的"大脑"，负责理解任务、制定计划、生成回复。
# - LangChain: 一个流行的 AI Agent 开发框架，提供了工具、链、Agent 等抽象。
#   类比: LangChain 就像 AI 开发的"乐高积木"，让你快速搭建 AI 应用。
#
# 阅读顺序建议:
# 1. 先看 _create_args_schema() 理解 JSON Schema 如何变成 Python 类型
# 2. 再看 MCPToolAdapter 类，理解适配器的核心机制
# 3. 然后看 create_mcp_tool_adapter() 和 create_mcp_tool_adapters()
# 4. 最后看 get_mcp_tools_async() 和 get_mcp_tools_sync()
#
# 与其他文件的协作:
# - src/core/mcp_manager.py: 管理 MCP 服务器的连接和工具发现，本文件依赖它来调用工具
# - src/tools/factory.py: 工具工厂，会使用本文件创建的适配器来注册 MCP 工具
# - src/agents/*.py: 各种 Agent 会通过 LangChain 的工具系统使用本文件创建的适配器
# ====================================================================

"""LangChain tool adapters for MCP (Model Context Protocol) tools.

This module provides adapters that wrap MCP tools as LangChain tools,
enabling seamless integration between MCP servers and LangChain agents.

Example:
    from src.tools.mcp_tools import create_mcp_tool_adapters
    from src.core.mcp_manager import get_mcp_manager

    manager = get_mcp_manager()
    mcp_tools = await manager.discover_tools("filesystem")
    langchain_tools = create_mcp_tool_adapters(mcp_tools, "filesystem")
"""

from __future__ import annotations  # 启用 PEP 563 延迟类型注解求值，让类型提示支持前向引用

import asyncio  # 异步 I/O 库，用于处理事件循环和协程
import json  # JSON 序列化/反序列化（本文件未直接使用，但保留以备扩展）
from typing import Any, Dict, List, Optional, Type  # 类型注解工具

from langchain.tools import BaseTool  # LangChain 的基类工具，所有工具必须继承它
from pydantic import BaseModel, Field, create_model  # 数据验证和模型创建库

from ..logger import setup_logger  # 导入项目统一的日志配置


logger = setup_logger()  # 初始化模块级日志记录器


def _create_args_schema(
    tool_name: str,
    input_schema: Dict[str, Any]
) -> Type[BaseModel]:
    """Create a Pydantic model from JSON schema for tool arguments.

    根据 MCP 工具输入的 JSON Schema 动态创建一个 Pydantic 数据模型，
    用于参数验证和类型检查。

    小白导读:
    - JSON Schema: 一种描述 JSON 数据结构的规范，定义字段名、类型、是否必填等
    - Pydantic: Python 数据验证库，能自动检查输入数据是否符合模型定义
    - create_model(): Pydynamic 提供的工厂函数，可以在运行时动态生成一个类。

    Args:
        tool_name: Name of the tool (used for model naming). 工具名称，用于生成模型类名。
        input_schema: JSON schema for the tool's input. 工具输入参数的 JSON Schema 定义。

    Returns:
        A Pydantic BaseModel class representing the schema. 动态生成的 Pydantic 模型类。

    假数据示例:
        # 输入:
        # tool_name = "read_file"
        # input_schema = {
        #     "properties": {
        #         "path": {"type": "string", "description": "文件路径"},
        #         "limit": {"type": "integer", "description": "读取行数"}
        #     },
        #     "required": ["path"]
        # }
        # 输出: 一个类似以下的 Pydantic 模型类
        # class Read_FileArgs(BaseModel):
        #     path: str
        #     limit: Optional[int] = None
    """
    properties = input_schema.get("properties", {})  # 提取属性定义，默认为空字典
    required = set(input_schema.get("required", []))  # 提取必填字段集合，默认为空集合

    field_definitions = {}  # 存储字段定义的字典，用于动态创建模型
    for prop_name, prop_schema in properties.items():  # 遍历每个属性
        prop_type = prop_schema.get("type", "string")  # 获取属性类型，默认为字符串
        description = prop_schema.get("description", "")  # 获取属性描述，默认为空字符串
        default = ... if prop_name in required else None  # 必填字段用 ... (Ellipsis) 表示，可选字段默认 None

        # Map JSON schema types to Python types
        # JSON Schema 类型到 Python 类型的映射表
        type_mapping = {
            "string": str,      # 字符串 -> str
            "integer": int,     # 整数 -> int
            "number": float,    # 数字 -> float
            "boolean": bool,    # 布尔 -> bool
            "array": list,      # 数组 -> list
            "object": dict,     # 对象 -> dict
        }
        python_type = type_mapping.get(prop_type, str)  # 查找对应 Python 类型，未知类型默认为 str

        # Handle optional types
        # 如果不是必填字段，包装为 Optional 类型（即允许为 None）
        if prop_name not in required:
            python_type = Optional[python_type]

        field_definitions[prop_name] = (
            python_type,
            Field(default=default, description=description)  # 使用 Pydantic Field 定义字段
        )

    # Create a dynamic Pydantic model
    # 根据工具名称生成模型类名，将连字符替换为下划线并转为驼峰式标题
    model_name = f"{tool_name.replace('-', '_').title()}Args"
    if not field_definitions:
        # Empty schema - create a simple model
        # 空 schema 时创建一个没有字段的简单模型
        return create_model(model_name)

    return create_model(model_name, **field_definitions)  # 动态创建 Pydantic 模型类


class MCPToolAdapter(BaseTool):
    """Adapter that wraps an MCP tool as a LangChain tool.

    将 MCP 工具包装为 LangChain 能识别的工具类型，处理两种协议之间的翻译工作。
    这是整个适配层的核心类，所有对 MCP 工具的调用都通过此类进行。

    小白导读:
    - BaseTool: LangChain 框架中所有工具的基类，继承它就能让 Agent 使用你的工具
    - 适配器模式: 一种设计模式，将一个类的接口转换成另一个接口，让原本不兼容的类可以一起工作
      类比: 适配器就像"电源转换器"，把不同标准的插头转换成你能用的标准

    This adapter handles the translation between LangChain's tool interface
    and MCP's tool calling protocol.

    Attributes:
        name: Tool name. 工具名称（带前缀，避免冲突）。
        description: Tool description. 工具描述信息。
        mcp_server: Name of the MCP server providing this tool. 提供此工具的 MCP 服务器名称。
        mcp_tool_name: Original tool name on the MCP server. 工具在 MCP 服务器上的原始名称。
        args_schema: Pydantic model for argument validation. 用于参数验证的 Pydantic 模型。
    """

    name: str = Field(..., description="Tool name")  # 工具名称，必填
    description: str = Field(..., description="Tool description")  # 工具描述，必填
    mcp_server: str = Field(..., description="MCP server name")  # MCP 服务器名称，必填
    mcp_tool_name: str = Field(..., description="Original MCP tool name")  # 原始 MCP 工具名，必填
    args_schema: Type[BaseModel] = Field(..., description="Arguments schema")  # 参数 schema，必填

    def _run(self, **kwargs: Any) -> str:
        """Synchronous execution - wraps async call.

        同步执行方法 - 将异步调用包装为同步调用。
        LangChain 的 Agent 在调用工具时会执行此方法。
        由于 MCP 调用本质是异步的（网络请求），这里需要特殊处理事件循环。

        小白导读:
        - 事件循环 (Event Loop): asyncio 的核心，负责调度和执行异步任务
          类比: 事件循环就像一个"任务调度员"，按顺序处理排队的异步任务
        - 协程 (Coroutine): 用 async def 定义的函数，可以暂停和恢复执行
          类比: 协程就像"可暂停的视频"，可以在等待时暂停，等条件满足再继续

        Args:
            **kwargs: Tool arguments. 工具的关键字参数。

        Returns:
            Tool execution result as string. 工具执行结果（字符串形式）。
        """
        try:
            from ..core.mcp_manager import get_mcp_manager  # 延迟导入避免循环依赖
            manager = get_mcp_manager()  # 获取 MCP 管理器单例

            if manager._main_loop and manager._main_loop.is_running():
                # Use the dedicated background loop
                # 如果管理器有正在运行的主事件循环，使用它来执行异步任务
                # 这是最常见的情况：在已有事件循环的线程中调用
                def _run_async():
                    # 在后台事件循环中运行异步任务，并等待结果（最多 120 秒）
                    return asyncio.run_coroutine_threadsafe(self._arun(**kwargs), manager._main_loop).result(timeout=120)

                import concurrent.futures  # 线程池执行器，用于跨线程调度
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    return executor.submit(_run_async).result()  # 提交任务并等待结果

            try:
                loop = asyncio.get_running_loop()  # 尝试获取当前线程的事件循环
            except RuntimeError:
                loop = None  # 如果没有运行的事件循环会抛出 RuntimeError

            if loop and loop.is_running():
                # If we're already in a running event loop, we must run the
                # async tool call in a separate thread to avoid nested loops.
                # 如果已经在运行的事件循环中，必须在单独线程中执行以避免嵌套循环
                # 嵌套事件循环会导致 RuntimeError: This event loop is already running
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,  # 在新线程中启动新的事件循环来运行异步任务
                        self._arun(**kwargs)
                    )
                    return future.result(timeout=120)  # 等待结果，超时 120 秒
            else:
                # No running event loop in this thread, safe to use asyncio.run
                # 当前线程没有运行的事件循环，可以安全地使用 asyncio.run
                return asyncio.run(self._arun(**kwargs))
        except Exception as e:
            error_msg = f"Error executing MCP tool {self.name}: {e}"  # 构造错误消息
            logger.error(error_msg)  # 记录错误日志
            return error_msg  # 返回错误消息而不是抛出异常，避免中断 Agent 执行

    async def _arun(self, **kwargs: Any) -> str:
        """Asynchronous execution via MCP manager.

        异步执行方法 - 实际调用 MCP 工具的核心逻辑。
        这个方法由 _run() 间接调用，负责与 MCP 服务器通信。

        Args:
            **kwargs: Tool arguments. 工具的关键字参数。

        Returns:
            Tool execution result as string. 工具执行结果（字符串形式）。
        """
        from ..core.mcp_manager import get_mcp_manager  # 延迟导入避免循环依赖

        manager = get_mcp_manager()  # 获取 MCP 管理器单例
        result = await manager.call_tool(  # 通过管理器调用远程 MCP 工具
            self.mcp_server,      # 目标 MCP 服务器名称
            self.mcp_tool_name,   # 要调用的工具名称
            kwargs                # 传递给工具的参数
        )
        return result  # 返回调用结果


def create_mcp_tool_adapter(
    tool_name: str,
    tool_description: str,
    input_schema: Dict[str, Any],
    server_name: str,
) -> MCPToolAdapter:
    """Create a LangChain tool adapter from MCP tool info.

    根据 MCP 工具信息创建一个 LangChain 工具适配器实例。
    这是创建单个适配器的主要入口函数。

    Args:
        tool_name: Name of the MCP tool. MCP 工具的名称。
        tool_description: Description of the tool. 工具的描述信息。
        input_schema: JSON schema for tool input. 工具输入的 JSON Schema。
        server_name: Name of the MCP server. 所属 MCP 服务器的名称。

    Returns:
        MCPToolAdapter instance. 配置好的适配器实例。

    假数据示例:
        # 输入:
        # tool_name = "read_file"
        # tool_description = "读取本地文件内容"
        # input_schema = {"properties": {"path": {"type": "string"}}, "required": ["path"]}
        # server_name = "filesystem"
        # 输出: MCPToolAdapter 实例
        #   name = "mcp_filesystem_read_file"
        #   description = "[MCP:filesystem] 读取本地文件内容"
        #   mcp_server = "filesystem"
        #   mcp_tool_name = "read_file"
    """
    args_schema = _create_args_schema(tool_name, input_schema)  # 动态创建参数验证模型

    # Create a prefixed name to avoid conflicts
    # 创建带前缀的工具名，避免不同服务器的工具名冲突
    # 例如: "filesystem" 服务器的 "read_file" 会变成 "mcp_filesystem_read_file"
    prefixed_name = f"mcp_{server_name}_{tool_name}"

    return MCPToolAdapter(
        name=prefixed_name,
        description=f"[MCP:{server_name}] {tool_description}",  # 添加服务器前缀便于识别
        mcp_server=server_name,
        mcp_tool_name=tool_name,
        args_schema=args_schema,
    )


def create_mcp_tool_adapters(
    mcp_tools: List[Any],
    server_name: str,
) -> List[MCPToolAdapter]:
    """Create LangChain tool adapters from a list of MCP tools.

    批量创建 LangChain 工具适配器。
    遍历 MCP 工具列表，为每个工具创建一个适配器。

    Args:
        mcp_tools: List of MCPTool objects. MCP 工具对象列表。
        server_name: Name of the MCP server. 这些工具所属的 MCP 服务器名称。

    Returns:
        List of MCPToolAdapter instances. 成功创建的适配器列表。

    假数据示例:
        # 输入:
        # mcp_tools = [MCPTool(name="read_file", ...), MCPTool(name="write_file", ...)]
        # server_name = "filesystem"
        # 输出: [MCPToolAdapter(name="mcp_filesystem_read_file", ...),
        #        MCPToolAdapter(name="mcp_filesystem_write_file", ...)]
    """
    adapters = []  # 存储成功创建的适配器
    for tool in mcp_tools:  # 遍历每个 MCP 工具
        try:
            adapter = create_mcp_tool_adapter(  # 为每个工具创建适配器
                tool_name=tool.name,
                tool_description=tool.description,
                input_schema=tool.input_schema,
                server_name=server_name,
            )
            adapters.append(adapter)  # 添加到结果列表
            logger.debug(f"Created adapter for MCP tool: {tool.name}")  # 记录调试日志
        except Exception as e:
            # 单个工具创建失败不应影响其他工具，记录警告并继续
            logger.warning(f"Failed to create adapter for {tool.name}: {e}")

    return adapters  # 返回所有成功创建的适配器


async def get_mcp_tools_async(server_names: List[str]) -> List[MCPToolAdapter]:
    """Asynchronously get LangChain tools from MCP servers.

    异步从多个 MCP 服务器获取工具并创建对应的 LangChain 适配器。
    这是异步环境（如 async Agent）中获取 MCP 工具的主要入口。

    小白导读:
    - discover_tools: MCP 管理器的方法，连接服务器并列出其提供的所有工具
      类比: discover_tools 就像"扫描"一个服务器，看看它有哪些功能

    Args:
        server_names: List of MCP server names to get tools from. 要获取工具的服务器名称列表。

    Returns:
        List of MCPToolAdapter instances. 所有成功加载的适配器列表。

    假数据示例:
        # 输入: server_names = ["filesystem", "web_search"]
        # 输出: [MCPToolAdapter(name="mcp_filesystem_read_file", ...),
        #        MCPToolAdapter(name="mcp_filesystem_write_file", ...),
        #        MCPToolAdapter(name="mcp_web_search_google", ...)]
    """
    from ..core.mcp_manager import get_mcp_manager  # 延迟导入避免循环依赖

    manager = get_mcp_manager()  # 获取 MCP 管理器单例
    all_tools = []  # 存储所有服务器加载的工具

    for server_name in server_names:  # 遍历每个服务器
        try:
            mcp_tools = await manager.discover_tools(server_name)  # 发现该服务器上的所有工具
            adapters = create_mcp_tool_adapters(mcp_tools, server_name)  # 批量创建适配器
            all_tools.extend(adapters)  # 添加到总列表
            logger.info(
                f"Loaded {len(adapters)} tools from MCP server: {server_name}"  # 记录加载数量
            )
        except Exception as e:
            # 单个服务器加载失败不应影响其他服务器，记录警告并继续
            logger.warning(
                f"Failed to load tools from {server_name}: {e}"
            )

    return all_tools  # 返回所有加载的工具


def get_mcp_tools_sync(server_names: List[str]) -> List[MCPToolAdapter]:
    """Synchronously get LangChain tools from MCP servers.

    同步环境（如普通函数或非 async Agent）中获取 MCP 工具的便捷方法。
    内部调用 get_mcp_tools_async()，处理事件循环的创建和管理。

    这是同步上下文中获取 MCP 工具的主要入口，处理了各种复杂的事件循环场景。

    小白导读:
    - 为什么需要同步包装？ 因为 MCP 调用需要网络 I/O（异步），但很多 Agent 框架是同步执行的
    - asyncio.run(): 创建新的事件循环并运行异步任务
    - run_coroutine_threadsafe(): 在已有事件循环的线程中安全地提交异步任务

    Args:
        server_names: List of MCP server names to get tools from. 要获取工具的服务器名称列表。

    Returns:
        List of MCPToolAdapter instances. 所有成功加载的适配器列表，失败时返回空列表。

    假数据示例:
        # 输入: server_names = ["filesystem"]
        # 输出: [MCPToolAdapter(name="mcp_filesystem_read_file", ...)]
    """
    try:
        from ..core.mcp_manager import get_mcp_manager  # 延迟导入避免循环依赖
        manager = get_mcp_manager()  # 获取 MCP 管理器单例

        if manager._main_loop and manager._main_loop.is_running():
            # 如果管理器有正在运行的主事件循环，使用它来执行异步任务
            def _get_async():
                # 在后台事件循环中运行异步任务，并等待结果（最多 120 秒）
                return asyncio.run_coroutine_threadsafe(get_mcp_tools_async(server_names), manager._main_loop).result(timeout=120)

            import concurrent.futures  # 线程池执行器
            with concurrent.futures.ThreadPoolExecutor() as executor:
                return executor.submit(_get_async).result()  # 提交任务并等待结果

        try:
            loop = asyncio.get_running_loop()  # 尝试获取当前线程的事件循环
        except RuntimeError:
            loop = None  # 没有运行的事件循环

        if loop and loop.is_running():
            # 已经在事件循环中，在单独线程中执行以避免嵌套循环
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,  # 在新线程中启动新的事件循环
                    get_mcp_tools_async(server_names)
                )
                return future.result(timeout=120)  # 等待结果，超时 120 秒
        else:
            # 当前线程没有运行的事件循环，可以安全地使用 asyncio.run
            return asyncio.run(get_mcp_tools_async(server_names))
    except Exception as e:
        logger.error(f"Failed to get MCP tools: {e}")  # 记录错误日志
        return []  # 失败时返回空列表，避免中断 Agent 执行
