# ====================================================================
# 文件角色：本文件是"工具工厂"（ToolFactory），负责统一注册、查找、
# 提供各种工具实例给 Agent 使用。它是工具层的入口。
#
# 小白导读（给初学者的阅读指南）：
# - 工具（Tool）：一个可以被 Agent 调用的功能单元，类比"手边工具箱里
#   的某个工具"，比如搜索引擎、代码执行器、文件读写器。
# - 工厂（Factory）：一种设计模式，统一生产/管理对象，你不需要自己
#   new 一个工具，直接找工厂要即可。
# - MCP（Model Context Protocol）：一种标准协议，让 AI 模型能对接外部
#   服务器提供的工具，类比"USB 接口"让不同设备都能插上就用。
# - Agent（智能体）：一个能自主决策、调用工具完成任务的 AI 程序。
# - LLM（大语言模型）：如 GPT、Claude 等，是 Agent 的"大脑"。
# - LangChain：一个流行的 AI 应用开发框架，提供工具、Agent 等抽象。
# - 注册表（Registry）：一个字典，把工具名字映射到工具实例，类比
#   "电话簿"——通过名字找到对应的号码（工具）。
#
# 与其他文件的协作关系：
# - .basetool：提供基础工具（execute_code、execute_command、list_directory）
# - .fileEdit：提供文档读写工具（create/read/edit_document、collect_data）
# - .internet：提供网络搜索工具（google_search、scrape_webpages）
# - .mcp_tools：提供从 MCP 服务器动态加载工具的能力
# - .tool_config：提供工具的配置项（超时、内存限制等）
# - ..logger：提供日志记录功能
# - 上层 Agent（如 code_agent、search_agent 等）通过 ToolFactory.get_tool(s)
#   获取需要的工具，然后调用它们完成任务。
# ====================================================================

from typing import Any, Dict, List, Optional
from langchain.tools import BaseTool  # BaseTool 是所有 LangChain 工具的基类，自定义工具都要继承它

from .basetool import execute_code, execute_command, list_directory  # 导入基础工具：执行代码、执行命令、列出目录
from .FileEdit import create_document, read_document, edit_document, collect_data  # 导入文件编辑工具
from .internet import google_search, scrape_webpages  # 导入网络搜索工具
from ..logger import setup_logger  # 导入日志记录器

from langchain_community.tools import WikipediaQueryRun  # LangChain 社区提供的维基百科查询工具
from langchain_community.utilities import WikipediaAPIWrapper  # 维基百科 API 的封装器
from langchain_community.agent_toolkits.load_tools import load_tools  # 用于加载社区预置工具（如 arxiv）

logger = setup_logger()  # 初始化全局日志记录器，用于记录警告和错误信息

# === 初始化复杂工具 ===
# 小白导读: WikipediaQueryRun 是 LangChain 封装的维基百科搜索工具，
# 底层通过 WikipediaAPIWrapper 调用维基百科的公开 API 获取词条内容。
try:
    api_wrapper = WikipediaAPIWrapper(wiki_client=None)  # 创建维基百科 API 客户端（None 表示使用默认的 requests 客户端）
    wikipedia = WikipediaQueryRun(api_wrapper=api_wrapper)  # 将 API 包装成 LangChain 可识别的工具对象
except Exception as e:
    # 如果维基百科工具初始化失败（如网络问题），记录警告并设为 None，不影响其他工具使用
    logger.warning(f"Failed to initialize Wikipedia tool: {e}")
    wikipedia = None

# 小白导读: Arxiv 是一个著名的学术论文预印本平台，load_tools 可以
# 从 LangChain 社区加载预置的 arxiv 搜索工具，用于检索学术论文。
# 注意：arxiv 包与 feedparser 6.x/Python 3.10 存在兼容性问题，
# 如果安装失败则跳过，不影响其他工具。
try:
    arxiv_tools = load_tools(["arxiv"])  # 加载 arxiv 工具列表，返回一个工具列表
    arxiv = arxiv_tools[0] if arxiv_tools else None  # 取第一个工具，如果列表为空则为 None
except Exception as e:
    logger.warning(f"Failed to initialize Arxiv tool: {e}")
    arxiv = None


class ToolFactory:
    """工具工厂：按名称注册和检索工具实例。"""

    # 小白导读: _registry 是"注册表"，一个字典（dict），键是工具名字（字符串），
    # 值是对应的工具实例。这是整个工厂的核心数据结构。
    # 类比：就像一个电话簿，通过名字（键）找到对应的工具（值）。
    # 工具名称 → 实例的注册表
    _registry = {
        "execute_code": execute_code,       # 执行代码工具：在沙箱中运行 Python 代码
        "execute_command": execute_command, # 执行命令工具：在系统 shell 中执行命令
        "list_directory": list_directory,   # 列出目录工具：查看文件夹内容
        "create_document": create_document, # 创建文档工具：新建一个文件
        "read_document": read_document,     # 读取文档工具：读取文件内容
        "edit_document": edit_document,     # 编辑文档工具：修改文件内容
        "collect_data": collect_data,       # 收集数据采集工具：从指定来源采集数据
        "google_search": google_search,     # Google 搜索工具：搜索互联网内容
        "scrape_webpages": scrape_webpages, # 网页抓取工具：抓取网页正文内容
        "wikipedia": wikipedia,             # 维基百科工具：查询维基百科词条
        "arxiv": arxiv,                     # Arxiv 工具：搜索学术论文
    }

    @classmethod
    def get_tool(cls, tool_name: str) -> Optional[BaseTool]:
        """按名称获取工具实例。

        Args:
            tool_name: 要检索的工具名称。

        Returns:
            工具实例，或 None（未找到时）。

        小白导读: 这是工厂最核心的方法——你告诉它工具名字，它返回工具实例。
        如果找不到对应名字的工具，会记录警告并返回 None。

        假数据示例:
            输入: tool_name = "google_search"
            输出: <google_search 工具实例>
            输入: tool_name = "nonexistent_tool"
            输出: None (同时日志记录警告)
        """
        tool = cls._registry.get(tool_name)  # 从注册表中按名字查找工具
        if not tool:
            logger.warning(f"Tool not found in registry: {tool_name}")  # 找不到时记录警告日志
            return None
        return tool

    @classmethod
    def get_tools(cls, tool_names: List[str]) -> List[BaseTool]:
        """按名称列表获取工具实例列表。

        Args:
            tool_names: 要检索的工具名称列表。

        Returns:
            工具实例列表。缺失的工具会记录警告。

        小白导读: 一次性获取多个工具，传入工具名字列表，返回工具实例列表。
        如果某个名字找不到，会自动跳过（不会报错）。

        假数据示例:
            输入: tool_names = ["google_search", "wikipedia", "nonexistent"]
            输出: [<google_search 实例>, <wikipedia 实例>]  # nonexistent 被跳过
        """
        tools = []
        for name in tool_names:  # 逐个遍历工具名字
            tool = cls.get_tool(name)  # 复用 get_tool 方法查找每个工具
            if tool:
                tools.append(tool)  # 找到的工具加入结果列表
        return tools

    @classmethod
    def list_available_tools(cls) -> List[str]:
        """列出注册表中所有可用的工具名称。

        小白导读: 返回所有已注册工具的名字列表，方便查看当前有哪些工具可用。

        假数据示例:
            输入: 无
            输出: ["execute_code", "execute_command", "list_directory", ...]
        """
        return list(cls._registry.keys())  # 将字典的所有键转为列表返回

    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """获取当前工具配置。

        Returns:
            包含所有限制和设置的字典。

        小白导读: 从 tool_config 模块读取当前工具的配置信息（如超时时间、内存限制等），
        以字典形式返回，方便上层查看和使用。

        假数据示例:
            输入: 无
            输出: {"execution": {"timeout_seconds": 30, ...}, "file_ops": {...}, ...}
        """
        from .tool_config import TOOL_CONFIG  # 延迟导入工具配置单例，避免循环依赖
        return TOOL_CONFIG.to_dict()  # 将配置对象转为字典返回

    @classmethod
    def get_limits(cls) -> Dict[str, Any]:
        """获取当前执行和文件操作限制。

        Returns:
            包含超时、内存、文件大小限制的字典。

        小白导读: 返回工具执行时的各种限制参数，包括执行超时、内存上限、
        文件读写大小限制、是否启用安全扫描等。这些限制防止工具滥用。

        假数据示例:
            输入: 无
            输出: {
                "execution": {
                    "timeout_seconds": 60,
                    "max_memory_mb": 512,
                    "max_output_chars": 10000,
                    "progress_timeout_seconds": 30,
                },
                "file_operations": {
                    "max_read_bytes": 1048576,
                    "max_read_lines": 1000,
                    "max_write_bytes": 1048576,
                },
                "security_scan_enabled": True,
                "write_validation_enabled": True,
            }
        """
        from .tool_config import TOOL_CONFIG  # 延迟导入工具配置单例
        return {
            "execution": {
                "timeout_seconds": TOOL_CONFIG.execution.timeout_seconds,           # 代码执行超时时间（秒）
                "max_memory_mb": TOOL_CONFIG.execution.max_memory_mb,               # 执行时最大内存限制（MB）
                "max_output_chars": TOOL_CONFIG.execution.max_output_chars,         # 输出最大字符数限制
                "progress_timeout_seconds": TOOL_CONFIG.execution.progress_timeout_seconds,  # 进度更新超时时间
            },
            "file_operations": {
                "max_read_bytes": TOOL_CONFIG.file_ops.max_read_bytes,       # 单次读取文件最大字节数
                "max_read_lines": TOOL_CONFIG.file_ops.max_read_lines,       # 单次读取文件最大行数
                "max_write_bytes": TOOL_CONFIG.file_ops.max_write_bytes,     # 单次写入文件最大字节数
            },
            "security_scan_enabled": TOOL_CONFIG.enable_security_scan,         # 是否启用安全扫描
            "write_validation_enabled": TOOL_CONFIG.enable_write_validation,   # 是否启用写入验证
        }

    @classmethod
    async def get_mcp_tools_async(
        cls, server_names: List[str]
    ) -> List[BaseTool]:
        """异步从 MCP 服务器获取 LangChain 工具。

        Args:
            server_names: 要获取工具的 MCP 服务器名称列表。

        Returns:
            来自 MCP 服务器的 LangChain 工具实例列表。

        小白导读: MCP（Model Context Protocol）是一种标准协议，让 AI 能对接
        外部服务器提供的工具。这个方法异步地从指定 MCP 服务器获取工具列表。
        类比：就像从网络上下载一个"插件包"，里面包含多个工具。

        假数据示例:
            输入: server_names = ["my_server"]
            输出: [<MCP 工具1>, <MCP 工具2>, ...]  # 从 MCP 服务器获取的工具列表
        """
        from .mcp_tools import get_mcp_tools_async  # 延迟导入异步 MCP 工具获取函数
        return await get_mcp_tools_async(server_names)  # 异步等待 MCP 服务器返回工具列表

    @classmethod
    def get_mcp_tools(cls, server_names: List[str]) -> List[BaseTool]:
        """同步从 MCP 服务器获取 LangChain 工具。

        这是同步上下文的便利包装器。

        Args:
            server_names: 要获取工具的 MCP 服务器名称列表。

        Returns:
            来自 MCP 服务器的 LangChain 工具实例列表。

        小白导读: 与 get_mcp_tools_async 功能相同，但使用同步方式获取。
        适用于不支持异步的场景。同步方法会阻塞当前线程直到结果返回。

        假数据示例:
            输入: server_names = ["my_server"]
            输出: [<MCP 工具1>, <MCP 工具2>, ...]
        """
        from .mcp_tools import get_mcp_tools_sync  # 延迟导入同步 MCP 工具获取函数
        return get_mcp_tools_sync(server_names)  # 同步调用获取 MCP 服务器工具列表
