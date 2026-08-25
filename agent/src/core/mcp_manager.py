from __future__ import annotations
import logging
import asyncio
import os
import yaml
import re
import anyio
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

"""
本模块提供 MCP 服务器连接管理和工具暴露给 Agent 的功能。
使用官方 MCP Python SDK 通过 stdio 传输与真实服务器通信。

充电/传数据"——MCP 就是那个标准接口，stdio 就是那根线。

参考：https://modelcontextprotocol.io/
"""

# 相对导入：从当前包的 logger 模块导入 setup_logger 函数
from ..logger import setup_logger

# 创建本模块专属的日志记录器
logger = setup_logger()
# 压制嘈杂的系统日志记录器：asyncio 和 anyio 的日志太频繁，设为 CRITICAL 级别

logging.getLogger("asyncio").setLevel(logging.CRITICAL)
logging.getLogger("anyio").setLevel(logging.CRITICAL)



MCP_SERVER_STOP_TIMEOUT = 5
CONNECTION_TIMEOUT = 30


@dataclass
class MCPServerConfig:
    """MCP 

    Attributes:
    """
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    description: str = ""


@dataclass
class MCPResource:
    """MCP 

    Attributes:
    """
    uri: str
    name: str
    mime_type: str = "text/plain"
    description: str = ""


@dataclass
class MCPTool:
    """MCP 

    Attributes:
    """
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    server_name: str = ""


@dataclass
class MCPServerConnection:
    """ MCP 

    Attributes:
    """
    name: str
    session: Any
    client_context: Any
    session_context: Any
    loop: Any = None


class MCPManager:
    """ MCP 

    Attributes:
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        """ MCP 

        Args:
            config_path: MCP 配置文件路径。
        """
        if config_path is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            config_dir = os.getenv('CONFIG_DIRECTORY', 'config')
            # 拼接出完整的配置文件路径
            config_path = os.path.join(config_dir, "mcp.yaml")

        self.config_path = Path(config_path)
        # _config：缓存的配置字典，初始为 None（惰性加载）
        self._config: Optional[Dict[str, Any]] = None
        self._servers: Dict[str, MCPServerConfig] = {}
        # _connections：服务器名 → 活动连接的字典
        self._connections: Dict[str, MCPServerConnection] = {}
        self._connection_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._mcp_stderr_file = None


        try:
            loop = asyncio.get_event_loop()
            def silent_exception_handler(loop, context):
                msg = context.get("message", "")
                # 忽略异步生成器和 cancel scope 相关的噪音错误
                if "asynchronous generator" in msg or "cancel scope" in msg:
                    return
                loop.default_exception_handler(context)
            loop.set_exception_handler(silent_exception_handler)
        except Exception:
            pass

    def _get_lock(self, server_name: str) -> asyncio.Lock:
        """

        Args:
            server_name: 服务器名称。

        Returns:
            该服务器的异步锁。
        """
        if server_name not in self._connection_locks:
            self._connection_locks[server_name] = asyncio.Lock()
        return self._connection_locks[server_name]

    @property
    def config(self) -> Dict[str, Any]:
        """ MCP 

        Returns:
            配置字典。
        """
        if self._config is None:
            self._config = self._load_config()
        return self._config

    def get_server_config(self, name: str) -> Optional[MCPServerConfig]:
        """ MCP 

        Args:
            name: 服务器名称。

        Returns:
            MCPServerConfig 或 None（未找到时）。
        """
        # 先查缓存
        if name in self._servers:
            return self._servers[name]

        # 从配置文件的 "servers" 键下查找
        servers = self.config.get("servers", {})
        if name not in servers:
            logger.warning(f"MCP server not found: {name}")
            return None

        server_config = servers[name]
        mcp_config = MCPServerConfig(
            name=name,
            command=server_config.get("command", ""),
            args=server_config.get("args", []),
            env=server_config.get("env", {}),
            description=server_config.get("description", ""),
        )
        self._servers[name] = mcp_config
        return mcp_config

    def get_enabled_servers(self, agent_name: str) -> List[MCPServerConfig]:
        """ Agent  MCP 

        Args:
            agent_name: Agent 名称。

        Returns:
            启用的 MCPServerConfig 列表。
        """

        from .agent_config_loader import get_agent_config_loader

        # 获取 Agent 配置加载器单例
        loader = get_agent_config_loader()
        # 加载该 Agent 的 MCP 配置
        mcp_config = loader.load_mcp_config(agent_name)

        servers = []
        for name in mcp_config.get("servers", {}).keys():
            config = self.get_server_config(name)
            if config:
                servers.append(config)

        return servers

    async def connect(self, server_name: str) -> bool:
        """ stdio  MCP 

        Args:
            server_name: 要连接的服务器名称。

        Returns:
            True 表示连接成功，False 表示失败。
        """
        async with self._global_lock:
            if server_name not in self._connection_locks:
                self._connection_locks[server_name] = asyncio.Lock()
        """带锁连接到 MCP 服务器。"""
        # 获取该服务器的专用锁
        async with self._get_lock(server_name):
            if server_name in self._connections:
                conn = self._connections[server_name]
                if conn.session:
                    # 已经连接好了，直接返回成功
                    return True
                else:
                    # 清理断开的连接（会话已失效）
                    await self._close_server_connection(server_name)

            config = self.get_server_config(server_name)
            if not config:
                logger.error(f"Configuration not found for MCP server: {server_name}")
                return False

            try:
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client


                env = os.environ.copy()
                for key, value in config.env.items():
                    env[key] = value

                # 构建 stdio 传输的参数
                server_params = StdioServerParameters(
                    command=config.command,
                    args=config.args,
                    env=env
                )

                logger.info(f"Connecting to MCP server: {server_name}...")


                if self._mcp_stderr_file is None:
                    try:
                        # 确保 logs 目录存在
                        os.makedirs("logs", exist_ok=True)
                        # 打开日志文件，追加模式
                        self._mcp_stderr_file = open("logs/mcp_servers.log", "a", encoding="utf-8")
                    except Exception:
                        self._mcp_stderr_file = sys.stderr

                # 使用上下文管理器但手动处理以保持流存活

                client_context = stdio_client(server_params, errlog=self._mcp_stderr_file)
                read_stream, write_stream = await client_context.__aenter__()

                session_context = ClientSession(read_stream, write_stream)
                # 进入会话上下文
                session = await session_context.__aenter__()
                await session.initialize()

                self._connections[server_name] = MCPServerConnection(
                    name=server_name,
                    client_context=client_context,
                    session_context=session_context,
                    session=session,
                    loop=asyncio.get_running_loop()
                )
                logger.info(f"Successfully connected to {server_name}")
                return True
            except Exception as e:
                logger.error(f"Failed to connect to {server_name}: {str(e)}", exc_info=True)
                return False

    async def _close_server_connection(self, server_name: str) -> None:
        """

        Args:
            server_name: 要关闭的服务器名称。
        """
        conn = self._connections.pop(server_name, None)
        if conn:
            try:
                if conn.session_context:
                    try:
                        await conn.session_context.__aexit__(None, None, None)
                    except (anyio.ClosedResourceError, RuntimeError, Exception) as e:
                        logger.debug(f"Non-fatal error closing session context for {server_name}: {e}")

                if conn.client_context:
                    try:
                        # 调用 __aexit__ 退出客户端上下文
                        await conn.client_context.__aexit__(None, None, None)
                    except (anyio.ClosedResourceError, RuntimeError, Exception) as e:
                        logger.debug(f"Non-fatal error closing client context for {server_name}: {e}")
            except Exception as e:
                logger.debug(f"Error during cleanup of {server_name}: {e}")

    async def disconnect(self, server_name: str) -> None:
        """ MCP 

        Args:
            server_name: 要断开的服务器名称。
        """
        # 获取该服务器的锁，确保关闭时没有其他操作在进行
        async with self._get_lock(server_name):
            await self._close_server_connection(server_name)
            logger.info(f"Disconnected from MCP server: {server_name}")

    async def close_all(self) -> None:
        """ MCP 
        """
        server_names = list(self._connections.keys())
        # 逐个断开
        for name in server_names:
            await self.disconnect(name)
        logger.info("All MCP connections closed")

    async def _get_or_create_connection(
        self, server_name: str
    ) -> Optional[MCPServerConnection]:
        """

        Args:
            server_name: 服务器名称。

        Returns:
            有效的连接对象，或 None（连接失败时）。
        """
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if server_name in self._connections:
            conn = self._connections[server_name]
            if conn.loop is current_loop and conn.session:
                return conn
            else:
                # 连接已过期或属于不同事件循环，需要重新连接
                logger.debug(f"Detected stale or loop-mismatched connection for {server_name}. Reconnecting...")
                await self.disconnect(server_name)

        # 没有有效连接，创建新连接
        success = await self.connect(server_name)
        if not success:
            return None

        return self._connections.get(server_name)

    async def discover_tools(self, server_name: str) -> List[MCPTool]:
        """ MCP 

        Args:
            server_name: MCP 服务器名称。

        Returns:
            从服务器发现的 MCPTool 对象列表。
        """
        # 最多尝试 2 次
        for attempt in range(2):
            # 获取或创建连接
            conn = await self._get_or_create_connection(server_name)
            if not conn:
                logger.error(f"Cannot discover tools: not connected to {server_name}")
                return []

            try:
                # 调用 MCP 的 list_tools 方法获取工具列表
                tools_response = await conn.session.list_tools()

                # 将 MCP SDK 返回的工具对象转换成我们自己的 MCPTool 对象
                tools = []
                for tool in tools_response.tools:
                    tools.append(MCPTool(
                        name=tool.name,
                        description=tool.description or "",
                        input_schema=tool.inputSchema if hasattr(tool, 'inputSchema') else {},
                        server_name=server_name,
                    ))
                logger.info(f"Discovered {len(tools)} tools from {server_name}")
                return tools
            except Exception as e:
                # 记录警告日志，准备重试
                logger.warning(f"Failed to discover tools from {server_name} (attempt {attempt+1}/2): {e}")
                # 重试前强制断开连接，确保干净状态
                await self.disconnect(server_name)
                if attempt == 1:
                    logger.error(f"Max retries reached for tool discovery on {server_name}")
                    return []

    async def list_resources(self, server_name: str) -> List[MCPResource]:
        """ MCP 

        Args:
            server_name: MCP 服务器名称。

        Returns:
            MCPResource 对象列表。
        """
        conn = await self._get_or_create_connection(server_name)
        if not conn:
            logger.error(f"Cannot list resources: not connected to {server_name}")
            return []

        try:
            resources_response = await conn.session.list_resources()
            resources = []
            for resource in resources_response.resources:
                resources.append(MCPResource(
                    uri=str(resource.uri),
                    name=resource.name or str(resource.uri),
                    mime_type=resource.mimeType if hasattr(resource, 'mimeType') else "text/plain",
                    description=resource.description if hasattr(resource, 'description') else "",
                ))
            logger.info(f"Found {len(resources)} resources from {server_name}")
            return resources
        except Exception as e:
            logger.error(f"Failed to list resources from {server_name}: {e}")
            return []

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any] = None) -> Any:
        """

        Args:
            server_name: MCP 服务器名称。
            tool_name: 工具名称。
            arguments: 工具参数字典。

        Returns:
            工具执行结果字符串。
        """
        if arguments is None:
            arguments = {}

        for attempt in range(3):
            try:
                conn = await self._get_or_create_connection(server_name)
                if not conn or not conn.session:
                    raise Exception(f"Failed to establish or retrieve valid connection for {server_name}")

                from mcp import types as mcp_types
                result = await conn.session.call_tool(tool_name, arguments)

                contents = []
                for content in result.content:
                    text = ""
                    if isinstance(content, mcp_types.TextContent):
                        text = content.text
                    elif hasattr(content, 'text'):
                        text = content.text
                    elif hasattr(content, 'data'):
                        contents.append(f"[Binary data: {len(content.data)} bytes]")
                        continue
                    else:
                        text = str(content)


                    if "Secure MCP Filesystem Server running on stdio" in text:
                        continue
                    if "Client does not support MCP Roots" in text:
                        continue

                    if text:
                        contents.append(text)

                # 用换行符连接所有文本内容
                return "\n".join(contents)

            except Exception as e:
                error_msg = str(e) or e.__class__.__name__
                logger.warning(f"Tool call failed (attempt {attempt+1}/3) for {server_name}.{tool_name}: {error_msg}")
                if attempt < 2:
                    # 重试前强制清除会话
                    await self.disconnect(server_name)

                    backoff = 1.0 if server_name != "filesystem" else 1.5
                    await asyncio.sleep(backoff)
                else:
                    # 已重试 2 次（共 3 次），放弃并抛出异常
                    logger.error(f"Max retries reached for tool {tool_name} on {server_name}")
                    raise e

    async def read_resource(self, server_name: str, uri: str) -> str:
        """ MCP 

        Args:
            server_name: MCP 服务器名称。
            uri: 要读取的资源 URI。

        Returns:
            资源内容字符串。
        """
        conn = await self._get_or_create_connection(server_name)
        if not conn:
            return f"Error: Not connected to MCP server {server_name}"

        try:
            from mcp import types as mcp_types

            # 调用 MCP 的 read_resource 方法
            result = await conn.session.read_resource(uri)

            contents = []
            for content in result.contents:
                if isinstance(content, mcp_types.TextContent):
                    contents.append(content.text)
                elif hasattr(content, 'text'):
                    contents.append(content.text)
                else:
                    contents.append(str(content))

            return "\n".join(contents)

        except Exception as e:
            error_msg = f"Error reading resource {uri}: {e}"
            logger.error(error_msg)
            return error_msg

    def get_tools_for_agent(self, agent_name: str) -> List[MCPTool]:
        """ Agent  MCP 

        Args:
            agent_name: Agent 名称。

        Returns:
            MCPTool 对象列表。
        """
        servers = self.get_enabled_servers(agent_name)
        if not servers:
            return []

        async def _gather_tools():
            all_tools = []
            for server in servers:
                tools = await self.discover_tools(server.name)
                all_tools.extend(tools)
            return all_tools

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if self._main_loop and self._main_loop.is_running():
                # 使用专用后台循环

                from concurrent.futures import Future
                def _run():
                    return asyncio.run_coroutine_threadsafe(_gather_tools(), self._main_loop).result(timeout=60)

                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    return executor.submit(_run).result()

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _gather_tools())
                    return future.result(timeout=60)
            else:
                return asyncio.run(_gather_tools())
        except Exception as e:
            logger.warning(f"Failed to get tools for {agent_name}: {e}")
            return []

    def _load_config(self) -> Dict[str, Any]:
        """ YAML  MCP 

            servers:
              filesystem:
                command: npx
                args: ["-y", "@mcp/filesystem-server"]
              web_search:
                command: python
                args: ["-m", "web_search_server"]

        Returns:
            配置字典。
        """
        # 检查配置文件是否存在
        if not self.config_path.exists():
            logger.warning(f"MCP config not found: {self.config_path}")
            return {"servers": {}, "defaults": []}

        try:
            # 读取 YAML 文件内容
            content = self.config_path.read_text(encoding="utf-8")
            # 解析 YAML 字符串为 Python 字典
            config = yaml.safe_load(content)
            # 展开配置中的环境变量
            return self._expand_env_vars(config)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse MCP config: {e}")
            return {"servers": {}, "defaults": []}

    def _expand_env_vars(self, obj: Any) -> Any:
        """

        Args:
            obj: 配置对象。

        Returns:
            展开环境变量后的对象。
        """
        if isinstance(obj, dict):
            # 字典：递归处理每个值
            return {k: self._expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            # 列表：递归处理每个元素
            return [self._expand_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            pattern = re.compile(r"\$\{([^}]+)\}")
            def replace(match):
                var_name = match.group(1)
                return os.environ.get(var_name, match.group(0))
            return pattern.sub(replace, obj)
        # 其他类型（数字、布尔值等）直接返回
        return obj


# 单例：模块级别的全局变量，存储唯一的 MCPManager 实例

_default_manager: Optional[MCPManager] = None


def get_mcp_manager() -> MCPManager:
    """ MCPManager 

    Returns:
        MCPManager 实例。
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = MCPManager()
    return _default_manager


def reset_mcp_manager() -> None:
    """ MCPManager 
    """
    global _default_manager
    if _default_manager is not None:
        # 尝试清理连接
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and not loop.is_running():
                loop.run_until_complete(_default_manager.close_all())
            elif not loop:
                asyncio.run(_default_manager.close_all())
        except Exception:
            # 清理失败也没关系，静默忽略
            pass
    _default_manager = None
