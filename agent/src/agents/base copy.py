# ============================================================
# 文件角色: src/agents/base.py — 所有 Agent 的公共父类（抽象基类）
# 小白导读:
#   - ABC (Abstract Base Class): 抽象基类，规定子类必须实现某些方法，否则不能实例化。
#   - Agent: 一个能自主决策、调用工具完成任务的 AI 角色。
#   - LLM: Large Language Model，大语言模型，如 GPT-4、Claude。
#   - MCP: Model Context Protocol，一种让 AI 调用外部工具的协议标准。
#   - Tool: AI 可调用的外部函数，类比"工人手里的扳手"。
#   - State: 工作流的状态对象，所有 Agent 共享的"记忆"。
#   - AgentConfigLoader: 从外部配置文件加载 Agent 提示词和工具配置的加载器。
# 协作关系:
#   - 被 code_agent.py / hypothesis_agent.py / note_agent.py 等具体 Agent 继承。
#   - 依赖 core/agent_config_loader.py 加载外部配置。
#   - 依赖 core/language_models.py 管理 LLM 模型。
# ============================================================

from __future__ import annotations  # 允许在类型注解中使用类名字符串（前向引用），兼容旧版 Python
"""支持外部配置的 Agent 抽象基类。

本模块为所有 Agent 提供公共创建逻辑，集成 AgentConfigLoader
加载外部系统提示词，并保留硬编码提示词作为向后兼容回退。
"""

import os  # 操作系统接口，用于文件路径等（本文件未直接使用，但子类可能用到）
from abc import ABC, abstractmethod  # ABC=抽象基类工具，abstractmethod=抽象方法装饰器
from typing import Any, TYPE_CHECKING  # Any=任意类型；TYPE_CHECKING=True 时只做类型检查不实际导入

from langchain_openai import ChatOpenAI  # LangChain 对 OpenAI 聊天模型的封装
from langchain.agents import create_agent  # LangChain 提供的创建 Agent 的工厂函数

from ..logger import setup_logger  # 从上级目录导入日志工具
from ..config import WORKING_DIRECTORY  # 项目的工作目录路径

if TYPE_CHECKING:  # 下面的导入仅给类型检查器（如 mypy/IDE）看，运行时不会真正执行
    from ..core.language_models import LanguageModelManager  # 语言模型管理器类型提示
    from ..core.agent_config_loader import AgentConfigLoader  # 配置加载器类型提示

logger = setup_logger()  # 创建本模块的日志记录器，用于打印运行日志


class BaseAgent(ABC):
    """所有 Agent 的抽象基类。

    同时支持外部配置（通过 AgentConfigLoader）和硬编码系统提示词。

    Attributes:
        agent_name: 用于配置查找的 Agent 名称。
        language_model_manager: 语言模型配置管理器。
        team_members: 团队成员角色列表，用于协作。
        working_directory: Agent 数据存储目录。
        response_format: 可选的结构化输出格式。
    """

    # 系统提示词前缀：表示该提示词是完整的，无需再拼接
    # 小白导读: 如果外部配置的提示词以这个开头，说明提示词已经写好了，不用再加工
    SYSTEM_PROMPT_PREFIX = "SYSTEM_PROMPT:"

    # 类级别的共享配置加载器（所有子类共用一个实例，节省内存）
    # 小白导读: None 表示还没创建；创建后会被赋值成 AgentConfigLoader 对象
    _config_loader: AgentConfigLoader | None = None

    @classmethod
    def get_config_loader(cls) -> AgentConfigLoader:
        """获取或创建共享的 AgentConfigLoader 实例。
        小白导读: 单例模式——只创建一次，之后复用。
        假数据示例:
            返回: AgentConfigLoader() 实例
        """
        if cls._config_loader is None:  # 如果还没创建过
            from ..core.agent_config_loader import AgentConfigLoader  # 延迟导入，避免循环依赖
            cls._config_loader = AgentConfigLoader()  # 创建唯一实例
        return cls._config_loader  # 返回共享实例

    def __init__(
        self,
        agent_name: str,  # Agent 的名字，如 "code_agent"
        language_model_manager: LanguageModelManager,  # 管理 LLM 的提供者（OpenAI/Anthropic 等）
        team_members: list[str],  # 团队其他成员名字列表
        working_directory: str = WORKING_DIRECTORY,  # 工作目录，默认用全局配置
        response_format: Any = None  # 输出格式模板（Pydantic 模型），None 表示不限制
    ) -> None:
        self.agent_name = agent_name  # 保存 Agent 名字
        self.language_model_manager = language_model_manager  # 保存模型管理器
        self.team_members = team_members  # 保存团队成员列表
        self.working_directory = working_directory  # 保存工作目录
        self.response_format = response_format  # 保存输出格式

        self.model = self._create_model()  # 创建 LLM 模型实例
        role_prompt = self._load_system_prompt()  # 加载系统提示词（外部配置优先，没有则用硬编码）
        tools = self._load_all_tools()  # 加载所有可用工具

        agent_config = self.language_model_manager.get_agent_config(self.agent_name)  # 获取本 Agent 的配置
        self.max_iterations = agent_config.get('max_iterations', 15)  # 最大迭代次数，默认 15

        # 创建底层 LangChain Agent，把模型、工具、提示词都组装起来
        self.agent = self._create_base_agent(
            self.model,
            tools,
            role_prompt,
            team_members,
            response_format,
            max_iterations=self.max_iterations,
        )

    def _load_all_tools(self) -> list[Any]:
        """按优先级从各种来源加载所有工具。
        小白导读: 工具加载优先级: 外部配置 > 硬编码 > 技能(Skills) > MCP 工具
        假数据示例:
            返回: [execute_code, execute_command, list_directory, ...]
        """
        tools: list[Any] = []  # 先建一个空列表
        config_tools = self._load_tools_from_config()  # 尝试从外部配置加载工具
        if config_tools:  # 如果配置里有工具
            tools.extend(config_tools)  # 加入列表
        else:  # 否则用子类硬编码的工具
            hardcoded_tools = self._get_tools()  # 调用子类实现的方法
            if hardcoded_tools:  # 如果有硬编码工具
                tools.extend(hardcoded_tools)  # 加入列表
        try:
            loader = self.get_config_loader()  # 获取配置加载器
            metadata = loader.load_metadata(self.agent_name)  # 加载元数据
            if metadata.skills:  # 如果配置了"技能"
                from ..tools.skills import LookupSkill  # 导入技能查询工具
                tools.append(LookupSkill())  # 加入技能工具
        except Exception as e:  # 任何错误都不应中断流程
            logger.warning(f"Failed to check skills: {e}")  # 打印警告日志
        mcp_tools = self._load_mcp_tools()  # 加载 MCP 外部工具
        if mcp_tools:  # 如果有 MCP 工具
            tools.extend(mcp_tools)  # 加入列表
        return tools  # 返回完整工具列表

    def _load_tools_from_config(self) -> list[Any]:
        """从外部配置文件加载工具列表。"""
        try:
            loader = self.get_config_loader()  # 获取配置加载器
            metadata = loader.load_metadata(self.agent_name)  # 加载元数据
            if not metadata.tools:  # 如果没配置工具
                return []  # 返回空列表
            from ..tools.factory import ToolFactory  # 导入工具工厂
            return ToolFactory.get_tools(metadata.tools)  # 通过工厂创建工具实例
        except Exception as e:  # 出错时
            return []  # 返回空列表，不中断流程

    def _load_mcp_tools(self) -> list[Any]:
        """从 MCP 配置加载外部工具。
        小白导读: MCP 工具是通过网络服务提供的远程工具，类比"请外援帮忙"。
        """
        try:
            loader = self.get_config_loader()  # 获取配置加载器
            mcp_config = loader.load_mcp_config(self.agent_name)  # 加载 MCP 配置
            server_names = list(mcp_config.get("servers", {}).keys())  # 获取服务器名称列表
            if not server_names:  # 如果没配置服务器
                return []  # 返回空列表
            from ..tools.factory import ToolFactory  # 导入工具工厂
            return ToolFactory.get_mcp_tools(server_names)  # 通过工厂创建 MCP 工具
        except Exception as e:  # 出错时
            return []  # 返回空列表

    def _create_base_agent(self, model, tools, role_prompt, team_members, response_format=None, max_iterations=15):
        """创建底层 LangChain Agent 实例。
        小白导读: 把模型、工具、提示词打包成一个能自主决策的 Agent。
        """
        tool_names = ", ".join([tool.name for tool in tools])  # 拼出所有工具的名字字符串
        team_members_str = ", ".join(team_members)  # 拼出团队成员名字字符串
        if role_prompt.startswith(self.SYSTEM_PROMPT_PREFIX):  # 如果提示词已标记为"完整"
            system_prompt = role_prompt[len(self.SYSTEM_PROMPT_PREFIX):]  # 直接去掉前缀使用
        else:  # 否则需要拼接成完整提示词
            system_prompt = (
                f"You have access to the following tools: {tool_names}. "  # 告诉 AI 有哪些工具
                f"Your specific role: {role_prompt}\n"  # 告诉 AI 它的角色
                f"Work autonomously. "  # 告诉 AI 要自主工作
                f"You are {self.agent_name} of team: {team_members_str}.\n"  # 告诉 AI 它在哪个团队
            )
        # 调用 LangChain 的 create_agent 创建真正的 Agent 对象
        agent = create_agent(model=model, tools=tools, system_prompt=system_prompt, response_format=response_format)
        if hasattr(agent, "max_iterations"):  # 如果 Agent 支持设置最大迭代次数
            agent.max_iterations = max_iterations  # 设置迭代上限，防止无限循环
        return agent  # 返回创建好的 Agent

    def _create_model(self) -> ChatOpenAI:
        """创建 LLM 模型实例。
        小白导读: 根据配置选择不同的模型提供商（OpenAI/Anthropic 等）。
        假数据示例:
            返回: ChatOpenAI(model="gpt-4", timeout=60)
        """
        provider = self.language_model_manager.get_provider(self.agent_name)  # 获取模型提供商
        model_class = provider.get_model_class()  # 获取模型类（如 ChatOpenAI）
        config = self.language_model_manager.get_model_config(self.agent_name).copy()  # 复制模型配置
        if "timeout" not in config:  # 如果配置里没设超时
            config["timeout"] = 60  # 默认 60 秒超时
        # 如果 Provider 提供了额外参数（如 OpenRouter 的 base_url / api_key），一并注入
        if hasattr(provider, "get_extra_kwargs"):
            config.update(provider.get_extra_kwargs())
        return model_class(**config)  # 用配置实例化模型

    def invoke(self, state: Any) -> Any:
        """调用 Agent 执行任务。
        小白导读: 给 Agent 一个状态对象，它会自动决策并返回结果。
        假数据示例:
            输入: state = {"messages": ["请分析数据"]}
            返回: {"messages": [..., "分析结果是..."], "code_artifacts": {...}}
        """
        config = {"recursion_limit": self.max_iterations}  # 设置递归限制，防止无限循环
        return self.agent.invoke(state, config=config)  # 调用底层 LangChain Agent

    def _load_system_prompt(self) -> str:
        """加载系统提示词，优先外部配置，回退到硬编码。"""
        try:
            loader = self.get_config_loader()  # 获取配置加载器
            return loader.load_system_prompt(self.agent_name)  # 从外部配置加载
        except FileNotFoundError:  # 如果配置文件不存在
            return self._get_system_prompt()  # 回退到子类的硬编码提示词
        except Exception:  # 其他任何错误
            return self._get_system_prompt()  # 回退到子类的硬编码提示词

    def _get_system_prompt(self) -> str:
        """子类可覆盖的默认系统提示词（硬编码回退）。"""
        return ""  # 默认返回空字符串

    @abstractmethod  # 装饰器：子类必须实现这个方法
    def _get_tools(self) -> list[Any]:
        """子类必须实现，返回该 Agent 使用的工具列表。"""
        pass  # 抽象方法，什么都不做

    def get_state_updates(self, state, output) -> dict[str, Any]:
        """从 Agent 输出中提取需要更新到全局状态的数据。子类可覆盖。"""
        return {}  # 默认不更新任何状态
