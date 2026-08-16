# ============================================================================
# mcp_manager.py — MCP 连接管理器（全局单例）
# ----------------------------------------------------------------------------
# 文件角色：
#   本类负责管理与外部 MCP 服务器的连接生命周期。MCP 服务器是独立的
#   子进程，通过 stdio（标准输入输出）与主进程通信。管理器负责启动、
#   连接、发现工具/资源、调用工具、断开连接这一整套流程。
#
# 小白导读（关键术语大白话）：
#   - MCP（Model Context Protocol）：一种"工具接入协议"，让 AI 模型
#     能调用远程/外部服务器提供的工具。类比：MCP 是 AI 世界的"USB 接口"，
#     只要双方都支持 MCP，就能即插即用。
#   - JSON-RPC：MCP 底层使用的通信格式。类比：就像两个人用同一种
#     "暗号"发消息，确保对方能听懂。
#   - Server（服务器）：在这里不是 Web 服务器，而是一个独立运行的
#     子进程，专门提供一组工具函数。类比：像是一个"外挂程序"，
#     主进程通过管道跟它说话。
#   - stdio（Standard Input/Output）：通过操作系统的标准输入输出流
#     来通信。类比：两个人通过"写信"（写管道）和"收信"（读管道）交流。
#   - 异步上下文管理器（async context manager）：Python 异步编程中的
#     一种模式，确保"用完就关"。类比：像借书——拿到书（连接），
#     看完自动还（关闭连接），不会忘。
#   - asyncio.Lock：异步锁，防止多个协程同时操作同一资源。类比：
#     "洗手间门锁"，一次只能进一个人，避免打架。
#   - 单例模式：整个程序只创建一个实例。类比：全校只有一个"网管"。
#   - dataclass：Python 的装饰器，自动生成 __init__ 等方法。
#     类比：一个"模板"，填上字段就能快速创建数据容器。
#   - YAML：一种配置文件格式，用缩进表示层级。类比：类似 JSON 但更简洁。
#
# 与其他文件的协作关系：
#   - 被 src/core/workflow.py 调用，在工作流启动时建立 MCP 连接。
#   - 被 src/tools/ 下的工具模块调用，获取可用工具列表。
#   - 被 src/agents/ 下的 Agent 使用，Agent 通过 MCP 调用外部工具。
#   - 依赖 src/core/agent_config_loader.py 加载 Agent 的 MCP 配置。
#   - 依赖 src/logger.py 设置日志记录器。
#   - 依赖官方 MCP Python SDK（mcp 包）实现底层协议通信。
# ============================================================================

from __future__ import annotations  # 允许在类型注解中使用类名本身（前向引用）
import logging  # Python 标准日志库
import asyncio  # Python 异步IO库，用于管理异步任务和子进程
import os  # 操作系统接口，用于读取环境变量和文件操作
import yaml  # YAML 解析库，用于读取配置文件
import re  # 正则表达式库，用于匹配环境变量模式
import anyio  # 异步IO兼容库，这里主要用它的 ClosedResourceError 异常
from pathlib import Path  # 面向对象的路径操作库
from dataclasses import dataclass, field  # dataclass 装饰器和 field 工厂
from typing import Any, Dict, List, Optional, Tuple  # 类型注解工具

"""
本模块提供 MCP 服务器连接管理和工具暴露给 Agent 的功能。
使用官方 MCP Python SDK 通过 stdio 传输与真实服务器通信。

小白导读: 这整个文件做的事情可以类比为"手机 App 通过 USB 接口
充电/传数据"——MCP 就是那个标准接口，stdio 就是那根线。

参考：https://modelcontextprotocol.io/
"""

# 相对导入：从当前包的 logger 模块导入 setup_logger 函数
from ..logger import setup_logger

# 创建本模块专属的日志记录器
logger = setup_logger()
# 压制嘈杂的系统日志记录器：asyncio 和 anyio 的日志太频繁，设为 CRITICAL 级别
# 小白导读: 就像把"系统悄悄话"的音量调到最小，只保留真正重要的错误信息
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
logging.getLogger("anyio").setLevel(logging.CRITICAL)


# 常量：MCP 服务器停止超时时间（秒）
# 小白导读: 强制关闭前的"宽限期"，类比：考试结束铃响后多给 5 秒收笔
MCP_SERVER_STOP_TIMEOUT = 5
# 常量：连接超时时间（秒）
CONNECTION_TIMEOUT = 30


@dataclass  # 小白导读: dataclass 自动生成 __init__、__repr__ 等方法，省去手写样板代码
class MCPServerConfig:
    """MCP 服务器配置。

    记录单个 MCP 服务器的启动信息。

    Attributes:
        name: 服务器标识符。
        command: 启动服务器的命令。
        args: 命令行参数。
        env: 服务器环境变量。
        description: 人类可读描述。
    """
    name: str  # 服务器名称，如 "filesystem"
    command: str  # 启动命令，如 "npx"
    args: List[str] = field(default_factory=list)  # 命令参数列表，如 ["-y", "@mcp/server"]
    env: Dict[str, str] = field(default_factory=dict)  # 环境变量字典
    description: str = ""  # 人类可读描述


@dataclass
class MCPResource:
    """MCP 服务器暴露的资源。

    小白导读: "资源"是 MCP 协议中的概念，类比：服务器提供的"文件"或"数据"，
    比如一个文件服务器可能暴露多个文件路径作为资源。

    Attributes:
        uri: 资源唯一标识符。
        name: 人类可读名称。
        mime_type: 资源的 MIME 类型。
        description: 可选描述。
    """
    uri: str  # 资源唯一标识符，如 "file:///path/to/file.txt"
    name: str  # 人类可读名称
    mime_type: str = "text/plain"  # MIME 类型，默认纯文本
    description: str = ""  # 可选描述


@dataclass
class MCPTool:
    """MCP 服务器暴露的工具。

    小白导读: "工具"是 MCP 协议中最重要的概念，类比：就像手机 App 里的一个
    "功能按钮"，按下后服务器会执行对应操作并返回结果。
    例如：一个天气服务器可能提供 "get_weather" 工具。

    Attributes:
        name: 工具标识符。
        description: 人类可读描述。
        input_schema: 工具输入的 JSON Schema。
        server_name: 提供此工具的服务器名称。
    """
    name: str  # 工具名称，如 "read_file"
    description: str  # 工具描述，如 "读取指定路径的文件内容"
    input_schema: Dict[str, Any] = field(default_factory=dict)  # 输入参数的 JSON Schema 定义
    server_name: str = ""  # 提供此工具的服务器名称


@dataclass
class MCPServerConnection:
    """到 MCP 服务器的活动连接。

    小白导读: 这个对象代表一条已经建立的"电话线"，包含通信所需的全部组件。

    Attributes:
        name: 服务器名称标识符。
        session: 用于通信的 MCP ClientSession。
        client_context: 传输（如 stdio）的上下文管理器。
        session_context: 会话的上下文管理器。
        loop: 此连接所属的事件循环。
    """
    name: str  # 服务器名称
    session: Any  # mcp.ClientSession，实际通信对象
    client_context: Any  # 传输上下文管理器，管理底层通信管道
    session_context: Any  # 会话上下文管理器，管理会话生命周期
    loop: Any = None  # 此连接所属的事件循环，用于跨循环检测


class MCPManager:
    """管理 MCP 服务器连接和工具暴露。

    负责：
    - 加载 MCP 服务器配置
    - 通过 stdio 传输启动和停止 MCP 服务器
    - 发现服务器上的工具和资源
    - 在已连接的服务器上调用工具
    - 根据配置为 Agent 提供工具

    Attributes:
        config_path: MCP 配置文件路径。
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        """初始化 MCP 管理器。

        如果未指定配置路径，默认从 CONFIG_DIRECTORY 环境变量
        （或 "config" 目录）下的 mcp.yaml 加载。

        Args:
            config_path: MCP 配置文件路径。

        假数据示例:
            manager = MCPManager()  # 使用默认配置路径
            manager = MCPManager(Path("custom/mcp.yaml"))  # 指定配置路径
        """
        # 如果未指定配置路径，尝试从环境变量获取配置目录
        if config_path is None:
            try:
                # 尝试获取当前正在运行的事件循环
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # 如果没有正在运行的事件循环，返回 None
                loop = None

            # 从环境变量读取配置目录，默认 "config"
            config_dir = os.getenv('CONFIG_DIRECTORY', 'config')
            # 拼接出完整的配置文件路径
            config_path = os.path.join(config_dir, "mcp.yaml")

        # 将配置路径转为 Path 对象，方便后续操作
        self.config_path = Path(config_path)
        # _config：缓存的配置字典，初始为 None（惰性加载）
        self._config: Optional[Dict[str, Any]] = None
        # _servers：服务器名 → 服务器配置的字典（缓存）
        self._servers: Dict[str, MCPServerConfig] = {}
        # _connections：服务器名 → 活动连接的字典
        self._connections: Dict[str, MCPServerConnection] = {}
        # _connection_locks：服务器名 → 异步锁的字典，防止并发连接同一服务器
        self._connection_locks: Dict[str, asyncio.Lock] = {}
        # _global_lock：全局锁，用于创建服务器级别的锁
        self._global_lock = asyncio.Lock()
        # _main_loop：主事件循环引用，用于跨线程调度
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        # _mcp_stderr_file：MCP 服务器 stderr 输出的目标文件
        self._mcp_stderr_file = None

        # 设置循环异常处理器，压制嘈杂的 anyio/asyncio 错误
        # 小白导读: 就像给系统装了个"过滤器"，只让真正重要的错误通过
        try:
            loop = asyncio.get_event_loop()
            # 定义一个"安静的"异常处理器
            def silent_exception_handler(loop, context):
                msg = context.get("message", "")
                # 忽略异步生成器和 cancel scope 相关的噪音错误
                if "asynchronous generator" in msg or "cancel scope" in msg:
                    return
                # 其他错误走默认处理流程
                loop.default_exception_handler(context)
            # 设置自定义异常处理器
            loop.set_exception_handler(silent_exception_handler)
        except Exception:
            # 如果设置失败（比如没有事件循环），静默忽略
            pass

    def _get_lock(self, server_name: str) -> asyncio.Lock:
        """获取或创建指定服务器的锁。

        小白导读: 每个服务器有自己的"门锁"，确保同一时间只有一个人在连接它。
        类比：公共厕所的隔间门锁——有人用了别人就得等。

        Args:
            server_name: 服务器名称。

        Returns:
            该服务器的异步锁。
        """
        if server_name not in self._connection_locks:
            # 如果这把锁不存在，创建一把新的
            self._connection_locks[server_name] = asyncio.Lock()
        return self._connection_locks[server_name]

    @property  # @property 把方法变成属性访问，调用时不需要加括号
    def config(self) -> Dict[str, Any]:
        """惰性加载 MCP 配置。

        小白导读: "惰性加载" = 用到时才加载，类比：饿了才做饭，不提前做好放着。
        这样可以避免启动时就读取可能不存在的配置文件。

        Returns:
            配置字典。

        假数据示例:
            mgr.config
            # 返回: {"servers": {"filesystem": {"command": "npx", "args": [...]}}, "defaults": []}
        """
        if self._config is None:
            # 第一次访问时才真正加载配置
            self._config = self._load_config()
        return self._config

    def get_server_config(self, name: str) -> Optional[MCPServerConfig]:
        """获取指定 MCP 服务器的配置。

        先从缓存查找，找不到再从配置文件加载。

        Args:
            name: 服务器名称。

        Returns:
            MCPServerConfig 或 None（未找到时）。

        假数据示例:
            cfg = mgr.get_server_config("filesystem")
            # 返回: MCPServerConfig(name="filesystem", command="npx", args=["-y", "@mcp/server"])
        """
        # 先查缓存
        if name in self._servers:
            return self._servers[name]

        # 从配置文件的 "servers" 键下查找
        servers = self.config.get("servers", {})
        if name not in servers:
            # 找不到就记录警告日志
            logger.warning(f"MCP server not found: {name}")
            return None

        # 找到后构建 MCPServerConfig 对象
        server_config = servers[name]
        mcp_config = MCPServerConfig(
            name=name,
            command=server_config.get("command", ""),
            args=server_config.get("args", []),
            env=server_config.get("env", {}),
            description=server_config.get("description", ""),
        )
        # 缓存起来，下次直接用
        self._servers[name] = mcp_config
        return mcp_config

    def get_enabled_servers(self, agent_name: str) -> List[MCPServerConfig]:
        """获取 Agent 启用的 MCP 服务器列表。

        小白导读: 不同 Agent 可以启用不同的 MCP 服务器。
        类比：不同 App 可能需要不同的"外挂"。

        Args:
            agent_name: Agent 名称。

        Returns:
            启用的 MCPServerConfig 列表。

        假数据示例:
            servers = mgr.get_enabled_servers("code_agent")
            # 返回: [MCPServerConfig("filesystem"), MCPServerConfig("web_search")]
        """
        # 延迟导入避免循环依赖
        # 小白导读: 延迟导入 = "用到才 import"，避免 A 导入 B、B 导入 A 的死循环
        from .agent_config_loader import get_agent_config_loader

        # 获取 Agent 配置加载器单例
        loader = get_agent_config_loader()
        # 加载该 Agent 的 MCP 配置
        mcp_config = loader.load_mcp_config(agent_name)

        # 遍历配置中启用的服务器名，获取对应配置
        servers = []
        for name in mcp_config.get("servers", {}).keys():
            config = self.get_server_config(name)
            if config:
                servers.append(config)

        return servers

    async def connect(self, server_name: str) -> bool:
        """通过 stdio 传输连接到 MCP 服务器。

        小白导读: stdio 传输 = 通过标准输入输出管道通信。
        类比：两个人通过"传纸条"交流，一个写一个读。

        流程：获取锁 → 检查是否已连接 → 启动子进程 → 建立会话 → 初始化

        Args:
            server_name: 要连接的服务器名称。

        Returns:
            True 表示连接成功，False 表示失败。

        假数据示例:
            success = await mgr.connect("filesystem")
            # 成功返回 True，失败返回 False
        """
        # 获取或创建此服务器的锁，确保同一时间只有一个连接操作
        async with self._global_lock:
            if server_name not in self._connection_locks:
                self._connection_locks[server_name] = asyncio.Lock()
        """带锁连接到 MCP 服务器。"""
        # 获取该服务器的专用锁
        async with self._get_lock(server_name):
            # 检查是否已连接且活跃
            if server_name in self._connections:
                conn = self._connections[server_name]
                if conn.session:
                    # 已经连接好了，直接返回成功
                    return True
                else:
                    # 清理断开的连接（会话已失效）
                    await self._close_server_connection(server_name)

            # 获取服务器配置
            config = self.get_server_config(server_name)
            if not config:
                logger.error(f"Configuration not found for MCP server: {server_name}")
                return False

            try:
                # 延迟导入 MCP SDK 的类和函数
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client

                # 复制当前环境变量，并合并服务器的自定义环境变量
                # 小白导读: 类比"继承"——子进程继承父进程的环境，再添加自己的
                env = os.environ.copy()
                for key, value in config.env.items():
                    env[key] = value

                # 构建 stdio 传输的参数
                server_params = StdioServerParameters(
                    command=config.command,  # 启动命令
                    args=config.args,        # 命令参数
                    env=env                  # 环境变量
                )

                logger.info(f"Connecting to MCP server: {server_name}...")

                # 重定向 stderr 避免 MCP 服务器噪声输出到控制台
                # 小白导读: 把子进程的"悄悄话"写到日志文件，不干扰主程序输出
                if self._mcp_stderr_file is None:
                    try:
                        # 确保 logs 目录存在
                        os.makedirs("logs", exist_ok=True)
                        # 打开日志文件，追加模式
                        self._mcp_stderr_file = open("logs/mcp_servers.log", "a", encoding="utf-8")
                    except Exception:
                        # 如果打开失败，回退到标准错误输出
                        self._mcp_stderr_file = sys.stderr

                # 使用上下文管理器但手动处理以保持流存活
                # 小白导读: 手动管理生命周期，类比：自己控制借还书时间
                client_context = stdio_client(server_params, errlog=self._mcp_stderr_file)
                # 进入上下文，获取读写流
                read_stream, write_stream = await client_context.__aenter__()

                # 用读写流创建客户端会话
                session_context = ClientSession(read_stream, write_stream)
                # 进入会话上下文
                session = await session_context.__aenter__()
                # 初始化 MCP 会话（握手、交换能力信息）
                await session.initialize()

                # 将连接信息保存到连接字典
                self._connections[server_name] = MCPServerConnection(
                    name=server_name,
                    client_context=client_context,
                    session_context=session_context,
                    session=session,
                    loop=asyncio.get_running_loop()  # 记录所属的事件循环
                )
                logger.info(f"Successfully connected to {server_name}")
                return True
            except Exception as e:
                # 连接失败，记录错误日志（带完整堆栈）
                logger.error(f"Failed to connect to {server_name}: {str(e)}", exc_info=True)
                return False

    async def _close_server_connection(self, server_name: str) -> None:
        """内部辅助函数：干净地关闭连接。

        小白导读: 关闭连接 = "挂断电话"。需要按顺序关闭会话和传输层。

        Args:
            server_name: 要关闭的服务器名称。
        """
        # 从连接字典中移除并获取连接对象
        conn = self._connections.pop(server_name, None)
        if conn:
            try:
                # 尝试优雅关闭会话和客户端上下文。
                # 捕获 anyio 特定的任务不匹配或关闭资源错误，
                # 这些错误可能在循环切换或任务突然终止时发生。
                if conn.session_context:
                    try:
                        # 调用 __aexit__ 退出会话上下文
                        await conn.session_context.__aexit__(None, None, None)
                    except (anyio.ClosedResourceError, RuntimeError, Exception) as e:
                        # 非致命错误，只记录调试日志
                        logger.debug(f"Non-fatal error closing session context for {server_name}: {e}")

                if conn.client_context:
                    try:
                        # 调用 __aexit__ 退出客户端上下文
                        await conn.client_context.__aexit__(None, None, None)
                    except (anyio.ClosedResourceError, RuntimeError, Exception) as e:
                        logger.debug(f"Non-fatal error closing client context for {server_name}: {e}")
            except Exception as e:
                # 兜底：捕获任何其他未预料的错误
                logger.debug(f"Error during cleanup of {server_name}: {e}")

    async def disconnect(self, server_name: str) -> None:
        """断开与 MCP 服务器的连接。

        Args:
            server_name: 要断开的服务器名称。

        假数据示例:
            await mgr.disconnect("filesystem")  # 断开连接，无返回值
        """
        # 获取该服务器的锁，确保关闭时没有其他操作在进行
        async with self._get_lock(server_name):
            await self._close_server_connection(server_name)
            logger.info(f"Disconnected from MCP server: {server_name}")

    async def close_all(self) -> None:
        """断开与所有 MCP 服务器的连接。

        小白导读: "一键挂断所有电话"，通常在程序退出时调用。

        假数据示例:
            await mgr.close_all()  # 断开所有连接
        """
        # 获取所有已连接服务器的名称列表
        server_names = list(self._connections.keys())
        # 逐个断开
        for name in server_names:
            await self.disconnect(name)
        logger.info("All MCP connections closed")

    async def _get_or_create_connection(
        self, server_name: str
    ) -> Optional[MCPServerConnection]:
        """获取现有连接或创建新连接（带循环感知）。

        小白导读: "循环感知" = 检查连接是否属于当前的事件循环。
        类比：不同线程/循环就像不同的"房间"，A 房间的钥匙开不了 B 房间的门。

        Args:
            server_name: 服务器名称。

        Returns:
            有效的连接对象，或 None（连接失败时）。
        """
        try:
            # 获取当前正在运行的事件循环
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            # 如果没有正在运行的事件循环
            current_loop = None

        if server_name in self._connections:
            conn = self._connections[server_name]
            # 验证连接是否对当前循环有效
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
        """发现 MCP 服务器上的工具（带鲁棒重试）。

        小白导读: "发现工具" = 问服务器"你有哪些功能？"
        类比：就像打开一个新 App，先看看里面有哪些按钮。

        带重试机制：失败后会自动重试一次。

        Args:
            server_name: MCP 服务器名称。

        Returns:
            从服务器发现的 MCPTool 对象列表。

        假数据示例:
            tools = await mgr.discover_tools("filesystem")
            # 返回: [MCPTool("read_file"), MCPTool("write_file"), MCPTool("list_dir")]
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
                    # 已经重试过一次，放弃
                    logger.error(f"Max retries reached for tool discovery on {server_name}")
                    return []

    async def list_resources(self, server_name: str) -> List[MCPResource]:
        """列出 MCP 服务器上的可用资源。

        小白导读: "资源"可以是文件、数据库记录、API 端点等服务器暴露的数据。

        Args:
            server_name: MCP 服务器名称。

        Returns:
            MCPResource 对象列表。

        假数据示例:
            resources = await mgr.list_resources("filesystem")
            # 返回: [MCPResource(uri="file:///tmp/a.txt", name="a.txt")]
        """
        conn = await self._get_or_create_connection(server_name)
        if not conn:
            logger.error(f"Cannot list resources: not connected to {server_name}")
            return []

        try:
            # 调用 MCP 的 list_resources 方法
            resources_response = await conn.session.list_resources()
            # 转换资源对象
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
        """在服务器上调用工具（带鲁棒重试和会话验证）。

        小白导读: 这是最核心的方法！类比：按下 App 里的"按钮"，
        传入参数，等待结果。

        带 3 次重试机制，每次重试前会断开重连。

        Args:
            server_name: MCP 服务器名称。
            tool_name: 工具名称。
            arguments: 工具参数字典。

        Returns:
            工具执行结果字符串。

        假数据示例:
            result = await mgr.call_tool("filesystem", "read_file", {"path": "/tmp/test.txt"})
            # 返回: "Hello, World!"（文件内容）
        """
        if arguments is None:
            arguments = {}

        # 最多尝试 3 次
        for attempt in range(3):
            try:
                # 使用循环感知的连接获取器确保使用绑定到当前事件循环的连接
                conn = await self._get_or_create_connection(server_name)
                if not conn or not conn.session:
                    raise Exception(f"Failed to establish or retrieve valid connection for {server_name}")

                # 调用 MCP 的 call_tool 方法
                from mcp import types as mcp_types
                result = await conn.session.call_tool(tool_name, arguments)

                # 从结果中提取内容
                contents = []
                for content in result.content:
                    text = ""
                    # 根据内容类型提取文本
                    if isinstance(content, mcp_types.TextContent):
                        text = content.text
                    elif hasattr(content, 'text'):
                        text = content.text
                    elif hasattr(content, 'data'):
                        # 二进制数据，只记录大小
                        contents.append(f"[Binary data: {len(content.data)} bytes]")
                        continue
                    else:
                        text = str(content)

                    # 过滤掉常见的 MCP 启动横幅（有时会泄漏到 stdout）
                    # 小白导读: 有些 MCP 服务器启动时会"自言自语"，这些要忽略
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
                    # 对文件系统使用稍长的退避时间以允许操作系统资源清理
                    # 小白导读: 文件系统需要更多时间"擦屁股"，所以多等 0.5 秒
                    backoff = 1.0 if server_name != "filesystem" else 1.5
                    await asyncio.sleep(backoff)
                else:
                    # 已重试 2 次（共 3 次），放弃并抛出异常
                    logger.error(f"Max retries reached for tool {tool_name} on {server_name}")
                    raise e

    async def read_resource(self, server_name: str, uri: str) -> str:
        """从 MCP 服务器读取资源。

        小白导读: 读取服务器暴露的资源内容，类比：打开文件读取内容。

        Args:
            server_name: MCP 服务器名称。
            uri: 要读取的资源 URI。

        Returns:
            资源内容字符串。

        假数据示例:
            content = await mgr.read_resource("filesystem", "file:///tmp/test.txt")
            # 返回: "Hello, World!"
        """
        conn = await self._get_or_create_connection(server_name)
        if not conn:
            return f"Error: Not connected to MCP server {server_name}"

        try:
            from mcp import types as mcp_types

            # 调用 MCP 的 read_resource 方法
            result = await conn.session.read_resource(uri)

            # 提取内容
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
        """获取 Agent 启用的所有 MCP 服务器上的工具（同步包装器）。

        小白导读: 这是给"同步代码"用的入口。异步世界和同步世界之间的"翻译官"。

        这是异步版本的同步包装器。新代码建议直接使用 discover_tools()。

        Args:
            agent_name: Agent 名称。

        Returns:
            MCPTool 对象列表。

        假数据示例:
            tools = mgr.get_tools_for_agent("code_agent")
            # 返回: [MCPTool("read_file"), MCPTool("search_web"), ...]
        """
        # 获取该 Agent 启用的服务器列表
        servers = self.get_enabled_servers(agent_name)
        if not servers:
            return []

        # 定义一个异步函数来收集所有服务器的工具
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
                # 小白导读: 在后台线程的事件循环中运行异步任务，避免阻塞主循环
                from concurrent.futures import Future
                def _run():
                    return asyncio.run_coroutine_threadsafe(_gather_tools(), self._main_loop).result(timeout=60)

                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    return executor.submit(_run).result()

            if loop and loop.is_running():
                # 已在异步上下文中，在单独线程创建新任务
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _gather_tools())
                    return future.result(timeout=60)
            else:
                # 没有事件循环，直接创建新的运行
                return asyncio.run(_gather_tools())
        except Exception as e:
            logger.warning(f"Failed to get tools for {agent_name}: {e}")
            return []

    def _load_config(self) -> Dict[str, Any]:
        """从 YAML 文件加载 MCP 配置。

        小白导读: YAML 配置文件通常长这样：
            servers:
              filesystem:
                command: npx
                args: ["-y", "@mcp/filesystem-server"]
              web_search:
                command: python
                args: ["-m", "web_search_server"]

        Returns:
            配置字典。

        假数据示例:
            config = mgr._load_config()
            # 返回: {"servers": {"filesystem": {"command": "npx", "args": [...]}}}
        """
        # 检查配置文件是否存在
        if not self.config_path.exists():
            logger.warning(f"MCP config not found: {self.config_path}")
            # 返回空配置作为兜底
            return {"servers": {}, "defaults": []}

        try:
            # 读取 YAML 文件内容
            content = self.config_path.read_text(encoding="utf-8")
            # 解析 YAML 字符串为 Python 字典
            config = yaml.safe_load(content)
            # 展开配置中的环境变量
            return self._expand_env_vars(config)
        except yaml.YAMLError as e:
            # YAML 语法错误
            logger.error(f"Failed to parse MCP config: {e}")
            return {"servers": {}, "defaults": []}

    def _expand_env_vars(self, obj: Any) -> Any:
        """递归展开配置中的环境变量。

        小白导读: 配置中可以用 ${ENV_NAME} 引用环境变量。
        类比：就像 Word 里的"宏"，运行时替换成实际值。

        支持嵌套在字典、列表、字符串中的环境变量。

        Args:
            obj: 配置对象。

        Returns:
            展开环境变量后的对象。

        假数据示例:
            # 假设环境变量 API_KEY=abc123
            expanded = mgr._expand_env_vars("${API_KEY}")
            # 返回: "abc123"

            expanded = mgr._expand_env_vars({"key": "${API_KEY}"})
            # 返回: {"key": "abc123"}
        """
        if isinstance(obj, dict):
            # 字典：递归处理每个值
            return {k: self._expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            # 列表：递归处理每个元素
            return [self._expand_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            # 字符串：用正则匹配 ${VAR} 模式并替换
            pattern = re.compile(r"\$\{([^}]+)\}")
            def replace(match):
                var_name = match.group(1)  # 提取变量名
                # 从环境变量中获取值，找不到则保留原样
                return os.environ.get(var_name, match.group(0))
            return pattern.sub(replace, obj)
        # 其他类型（数字、布尔值等）直接返回
        return obj


# 单例：模块级别的全局变量，存储唯一的 MCPManager 实例
# 小白导读: 类比：全校只有一个"网管办公室"，所有请求都找它
_default_manager: Optional[MCPManager] = None


def get_mcp_manager() -> MCPManager:
    """获取默认的 MCPManager 单例。

    单例模式：第一次调用时创建实例，之后每次返回同一个实例。
    类比：全校只有一个"网管"，第一次找他时任命一个，之后都找同一个。

    Returns:
        MCPManager 实例。

    假数据示例:
        mgr = get_mcp_manager()  # 返回全局唯一的 MCPManager
    """
    global _default_manager
    if _default_manager is None:
        # 第一次调用，创建实例
        _default_manager = MCPManager()
    return _default_manager


def reset_mcp_manager() -> None:
    """重置 MCPManager 单例。

    用于测试或需要重新配置时。
    小白导读: "格式化网管办公室"——清空现有实例，下次调用会创建新的。

    假数据示例:
        reset_mcp_manager()  # 重置后，下次 get_mcp_manager() 会创建新实例
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
    # 将单例设为 None，下次 get_mcp_manager() 会创建新实例
    _default_manager = None
