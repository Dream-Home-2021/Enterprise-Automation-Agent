# ============================================================================
# 📦 本文件是 `src/tools/` 包的入口模块（初始化文件）
#
# 【文件角色】
#   当外部代码写 `from src.tools import xxx` 时，Python 会先执行这个 __init__.py，
#   把子模块里的函数/类"搬运"到顶层命名空间，让调用方可以一行代码直接使用工具，
#   而不需要记住具体子模块路径。
#
# 【小白导读】
#   - 包（Package）：一个含有 __init__.py 的文件夹，类比"工具箱"。
#   - 模块（Package 里的 .py 文件）：类比"工具箱里的某个抽屉"。
#   - __all__：告诉别人"这个工具箱对外提供哪些工具"，类比工具箱外壳上贴的清单。
#   - MCP（Model Context Protocol）：一种让 AI 模型调用外部工具的标准化协议，
#     类比"AI 与外部世界对话的通用语言"。本包里的工具最终会注册到 MCP 服务器上。
#   - Tool（工具）：Agent 可调用的最小功能单元，类比"工人手里的螺丝刀"。
#   - Agent（智能体）：能自主决策、调用工具完成任务的 AI 实体，类比"一个实习生"。
#   - LLM（大语言模型）：Agent 的"大脑"，负责理解任务、生成计划。
#   - LangChain：一个流行的 AI 应用开发框架，提供工具注册、Agent 编排等能力。
#     类比"乐高积木"——让你快速搭建 AI 应用。
#   - Factory（工厂）：一种设计模式，统一生产/管理对象，你不需要自己 new 一个工具，
#     直接找 factory 要即可。类比"4S 店"——你提需求，它交付成品。
#
# 【与其他文件的协作】
#   - src/tools/basetool.py    → 提供代码执行、命令执行、目录列表类工具
#   - src/tools/fileEdit.py   → 提供文件读写、文档创建类工具（含安全校验）
#   - src/tools/internet.py    → 提供网页搜索、网页抓取类工具
#   - src/tools/skills.py     → 提供技能查找工具（LookupSkill）
#   - src/tools/mcp_tools.py  → 把 MCP 服务器提供的工具适配为 LangChain 工具
#   - src/tools/security.py    → 提供安全扫描（SecurityScanner）和资源限制（ResourceLimiter）
#   - src/tools/validators.py  → 提供路径校验（PathValidator）和内容校验（ContentValidator）
#   - src/tools/tool_config.py→ 统一管理工具的安全配置（超时、内存、黑名单等）
#   - src/tools/factory.py    → 根据配置把上面这些工具打包成统一接口（ToolFactory）
#   - src/core/mcp_manager.py → 管理 MCP 服务器连接，供 mcp_tools 调用远程工具
#   - src/agents/*.py          → 各 Agent 通过 ToolFactory.get_tool(s) 获取工具
#
# 【模块内部分层】
#   1. 工具函数层（basetool / fileEdit / internet / skills）
#      —— 实际执行具体操作的函数，用 @tool 装饰器注册为 LangChain Tool。
#   2. 安全校验层（security / validators / tool_config）
#      —— 在工具执行前检查路径、内容、代码安全性，防止恶意操作。
#   3. 适配层（mcp_tools）
#      —— 把 MCP 协议的工具翻译成 LangChain 能识别的格式。
#   4. 工厂层（factory）
#      —— 统一管理所有工具的注册、查找、配置，是外部获取工具的唯一入口。
# ============================================================================

# ─── 从 basetool 子模块导入核心工具函数 ───
# 小白导读: execute_code 让 Agent 能在沙箱里运行 Python 代码；
#           execute_command 让 Agent 能执行系统命令；
#           list_directory 让 Agent 能查看目录内容。
from .basetool import execute_code, execute_command, list_directory

# ─── 从 fileEdit 子模块导入文件操作类工具函数 ───
# 小白导读: 这组函数让 Agent 能像人一样读写本地文件，是"文档工人"的核心技能。
#           create_document 创建新文档；read_document 读取已有文档；
#           edit_document 按行插入编辑文档；collect_data 从 CSV 采集数据。
from .FileEdit import create_document, read_document, edit_document, collect_data

# ─── 从 internet 子模块导入网络搜索类工具函数 ───
# 小白导读: 这组函数让 Agent 能上网查资料，是"信息研究员"的核心技能。
#           google_search 通过 Google 搜索关键词；scrape_webpages 抓取网页正文。
from .internet import google_search, scrape_webpages

# ─── 从 skills 子模块导入技能查找工具 ───
# 小白导读: LookupSkill 让 Agent 能根据技能名称查找对应的操作指南内容，
#           类似于"翻查实验手册"来获取某项任务的详细步骤。
from .skills import LookupSkill

# ─── 从 mcp_tools 子模块导入 MCP 工具适配函数 ───
# 小白导读: create_mcp_tool_adapter / create_mcp_tool_adapters 把 MCP 服务器
#           提供的工具"翻译"成 LangChain 框架能识别的格式，实现即插即用。
from .mcp_tools import create_mcp_tool_adapter, create_mcp_tool_adapters

# ─── 从 security 子模块导入安全扫描与资源限制类 ───
# 小白导读: SecurityScanner 在代码执行前用正则+AST 检查危险操作（如 eval、os.system）；
#           ResourceLimiter 在沙箱执行时限制运行时间、内存、输出长度。
from .security import SecurityScanner, ResourceLimiter

# ─── 从 validators 子模块导入路径与内容校验器 ───
# 小白导读: PathValidator 校验文件路径/扩展名/大小是否合法（防路径穿越攻击）；
#           ContentValidator 校验写入内容是否合规（体积、敏感信息、占位标记）。
from .validators import PathValidator, ContentValidator

# ─── 从 tool_config 子模块导入全局配置单例 ───
# 小白导读: TOOL_CONFIG 是整个工具层的安全配置中心，统一管理超时、内存、
#           黑名单路径、危险代码模式等参数。其他模块通过它读取限制值。
from .tool_config import TOOL_CONFIG

# ─── 从 factory 子模块导入工具工厂 ───
# 小白导读: ToolFactory 是外部获取工具的唯一入口，通过 ToolFactory.get_tool("名字")
#           即可拿到对应的工具实例。它还支持从 MCP 服务器动态加载远程工具。
from .factory import ToolFactory

# 小白导读: __all__ 列表定义了"对外公开的工具清单"。
# 当外部使用 `from src.tools import *` 时，只会导入这里列出的名字。
# 假数据示例:
#   外部调用: from src.tools import google_search
#   等价于:   from src.tools.internet import google_search
#   返回值示例: google_search("天气") → [{"title": "...", "url": "...", "snippet": "..."}, ...]
#
#   外部调用: from src.tools import ToolFactory
#   用法:     tool = ToolFactory.get_tool("execute_code")
#   返回值示例: tool → <execute_code 工具实例>
__all__ = [
    # ── 基础执行工具 ──
    "execute_code",       # 执行 Python 代码（沙箱环境）
    "execute_command",    # 执行系统 Shell 命令
    "list_directory",     # 列出目录下的文件和子目录

    # ── 文件操作工具 ──
    "create_document",    # 创建新文档/文件
    "read_document",      # 读取已有文档/文件内容
    "edit_document",      # 按行插入修改已有文档/文件
    "collect_data",       # 从 CSV 文件采集数据（返回 DataFrame）

    # ── 网络搜索工具 ──
    "google_search",      # 通过 Google 搜索引擎查询关键词
    "scrape_webpages",    # 抓取指定 URL 的网页内容并提取正文

    # ── 技能查找工具 ──
    "LookupSkill",        # 根据技能名称查找对应的操作指南内容

    # ── MCP 工具适配 ──
    "create_mcp_tool_adapter",   # 创建单个 MCP 工具的 LangChain 适配器
    "create_mcp_tool_adapters",  # 批量创建 MCP 工具的 LangChain 适配器

    # ── 安全校验类 ──
    "SecurityScanner",    # 静态分析代码中的危险模式（正则 + AST）
    "ResourceLimiter",    # 带超时/内存/输出限制的代码执行器

    # ── 校验器 ──
    "PathValidator",      # 校验文件路径安全性（黑名单、扩展名、大小）
    "ContentValidator",   # 校验写入内容合规性（体积、敏感信息、占位符）

    # ── 配置 ──
    "TOOL_CONFIG",        # 全局工具配置单例（超时、内存、黑名单等）

    # ── 工厂 ──
    "ToolFactory",        # 工具工厂：按名称注册/检索/管理工具实例
]
