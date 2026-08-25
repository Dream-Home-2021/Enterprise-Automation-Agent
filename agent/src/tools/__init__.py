from .basetool import execute_code, execute_command, list_directory

# ─── 从 fileEdit 子模块导入文件操作类工具函数 ───

#           create_document 创建新文档；read_document 读取已有文档；
#           edit_document 按行插入编辑文档；collect_data 从 CSV 采集数据。
from .FileEdit import create_document, read_document, edit_document, collect_data


from .internet import google_search, scrape_webpages


from .skills import LookupSkill


from .mcp_tools import create_mcp_tool_adapter, create_mcp_tool_adapters


from .security import SecurityScanner, ResourceLimiter

# ─── 从 validators 子模块导入路径与内容校验器 ───

from .validators import PathValidator, ContentValidator

# ─── 从 tool_config 子模块导入全局配置单例 ───

from .tool_config import TOOL_CONFIG


#           即可拿到对应的工具实例。它还支持从 MCP 服务器动态加载远程工具。
from .factory import ToolFactory


# 当外部使用 `from src.tools import *` 时，只会导入这里列出的名字。
#   外部调用: from src.tools import google_search
#   等价于:   from src.tools.internet import google_search
#   返回值示例: google_search("天气") → [{"title": "...", "url": "...", "snippet": "..."}, ...]
#
#   外部调用: from src.tools import ToolFactory
#   用法:     tool = ToolFactory.get_tool("execute_code")
#   返回值示例: tool → <execute_code 工具实例>
__all__ = [
    "execute_code",
    "execute_command",
    "list_directory",

    "create_document",
    "read_document",
    "edit_document",
    "collect_data",

    "google_search",
    "scrape_webpages",

    "LookupSkill",

    # ── MCP 工具适配 ──
    "create_mcp_tool_adapter",
    "create_mcp_tool_adapters",

    "SecurityScanner",
    "ResourceLimiter",

    # ── 校验器 ──
    "PathValidator",
    "ContentValidator",

    # ── 配置 ──
    "TOOL_CONFIG",

    # ── 工厂 ──
    "ToolFactory",
]
