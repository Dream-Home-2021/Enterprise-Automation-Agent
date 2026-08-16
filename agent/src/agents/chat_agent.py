# ============================================================
# 文件角色: src/agents/chat_agent.py — 工单操作 Agent
# 小白导读:
#   - ChatAgent: 一个能处理 Zammad 工单的 AI 角色，类比"客服专员"。
#   - 它可以查询、创建、更新工单，搜索用户等。
# 协作关系:
#   - 继承 BaseAgent，获得所有基础能力。
#   - 被 AgentFactory 按名字创建。
#   - call_chat_agent 被 Supervisor 作为工具调用。
# ============================================================

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from langchain.tools import tool
from langgraph.config import get_config

from .base import BaseAgent
from ..config import WORKING_DIRECTORY
from ..logger import setup_logger

if TYPE_CHECKING:
    from ..core.language_models import LanguageModelManager

# 工具导入（从项目根目录 tools/chat/）
from tools.chat.ticket import list_tickets, get_ticket, create_ticket, update_ticket
from tools.chat.user import search_users, get_user

logger = setup_logger()


class ChatAgent(BaseAgent):
    """负责处理 Zammad 工单操作的 Agent。
    小白导读: 这个 Agent 会查询、创建、更新工单，搜索用户等客服操作。
    """

    def __init__(
        self,
        language_model_manager: LanguageModelManager,
        team_members: list[str],
        working_directory: str = WORKING_DIRECTORY,
    ) -> None:
        # 调用父类构造函数
        super().__init__(
            agent_name="chat_agent",  # 本 Agent 的名字
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory,
        )

    def _get_tools(self) -> list[Any]:
        """返回本 Agent 可用的工单操作工具列表。
        小白导读: 包含工单 CRUD（增删改查）和用户搜索工具。
        假数据示例:
            输出: [list_tickets, get_ticket, create_ticket, update_ticket, search_users, get_user]
        """
        return [
            list_tickets,    # 列出/搜索工单
            get_ticket,      # 获取工单详情
            create_ticket,   # 创建新工单
            update_ticket,   # 更新工单状态/优先级
            search_users,    # 搜索用户
            get_user,        # 获取用户详情
        ]

    def _get_system_prompt(self) -> str:
        """返回 Chat Agent 的系统提示词。
        小白导读: 定义 Agent 的角色和可用操作，引导 LLM 行为。
        """
        return (
            "你是一个 Zammad 工单系统的客服助手。你可以：\n"
            "1. 查询/搜索工单（list_tickets / get_ticket）\n"
            "2. 创建新工单（create_ticket）\n"
            "3. 更新工单状态/优先级（update_ticket）\n"
            "4. 搜索用户（search_users / get_user）\n\n"
            "根据用户的需求，选择最合适的工具。注意：\n"
            "- 创建工单时必须从对话中提取标题和内容\n"
            "- 更新工单前先确认工单 ID\n"
            "- 工具调用结果会返回给你，基于结果回复用户"
        )

    def get_state_updates(self, state: Any, output: Any) -> dict[str, Any]:
        """从 Agent 输出中提取回复文本，更新到全局状态。
        小白导读: 兼容多种输出格式（字符串、对象），统一提取回复文本。
        假数据示例:
            输入: output = "工单 #123 已创建成功"
            返回: {"chat_response": "工单 #123 已创建成功"}
        """
        if isinstance(output, str):  # 如果输出是纯字符串
            result_text = output  # 直接使用
        elif hasattr(output, "content"):  # 如果有 content 属性（如 AIMessage）
            result_text = str(output.content)  # 提取该属性
        elif hasattr(output, "output"):  # 如果有 output 属性（AgentFinish）
            result_text = str(output.output)  # 提取该属性
        else:  # 其他情况
            result_text = str(output)  # 强制转成字符串
        return {"chat_response": result_text}  # 返回更新字典


# ============================================================
# 单例模式
# ============================================================

_chat_agent_instance: ChatAgent | None = None


def get_chat_agent(
    language_model_manager: LanguageModelManager | None = None,
    team_members: list[str] | None = None,
) -> ChatAgent:
    """获取 ChatAgent 单例。

    小白导读: 确保全局只有一个 ChatAgent 实例，避免重复创建。
    首次调用时必须传入 language_model_manager 和 team_members。
    """
    global _chat_agent_instance
    if _chat_agent_instance is None:
        if language_model_manager is None or team_members is None:
            raise ValueError(
                "首次调用 get_chat_agent() 时必须提供 language_model_manager 和 team_members"
            )
        _chat_agent_instance = ChatAgent(
            language_model_manager=language_model_manager,
            team_members=team_members,
        )
    return _chat_agent_instance


# ============================================================
# 工具包装：供 Supervisor 调用
# ============================================================

@tool(
    "call_chat_agent",
    description=(
        "调用工单助手处理工单/用户相关查询。"
        "当用户需要查询、创建或更新工单、搜索用户时使用。"
        "传入完整的用户问题。"
    ),
)
async def call_chat_agent(query: str) -> str:
    """将 ChatAgent 包装为 tool，供 Supervisor 调用。

    使用 `get_config()` 获取当前运行的 config（含 thread_id, user_id），
    传播给子图，确保子图在同一个检查点线程下工作。
    """
    # 通过 get_config() 获取当前运行的配置（LangGraph 自动注入）
    current_config = get_config()
    if current_config:
        logger.info(
            "call_chat_agent propagating config: thread_id=%s",
            current_config.get("configurable", {}).get("thread_id"),
        )

    instance = get_chat_agent()
    # 使用 agent.ainvoke() 异步调用（Runnable 原生支持 async）
    result = await instance.agent.ainvoke(
        {"messages": [{"role": "user", "content": query}]},
        config={"recursion_limit": instance.max_iterations},
    )

    # 兼容多种输出格式
    if isinstance(result, dict):
        content = result.get("output", "") or result.get("content", "") or str(result)
    elif hasattr(result, "content"):
        content = str(result.content)
    else:
        content = str(result)

    logger.info("chat_agent result: %d chars", len(content))
    return content