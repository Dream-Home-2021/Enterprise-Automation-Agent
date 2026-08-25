from __future__ import annotations

from typing import Any, TYPE_CHECKING

from langchain.tools import tool
from langgraph.config import get_config

from .base import BaseAgent
from ..config import WORKING_DIRECTORY
from ..logger import setup_logger

if TYPE_CHECKING:
    from ..core.language_models import LanguageModelManager

from tools.chat.ticket import list_tickets, get_ticket, create_ticket, update_ticket
from tools.chat.user import search_users, get_user

logger = setup_logger()


class ChatAgent(BaseAgent):
    """ Zammad  Agent
    """

    def __init__(
        self,
        language_model_manager: LanguageModelManager,
        team_members: list[str],
        working_directory: str = WORKING_DIRECTORY,
    ) -> None:
        super().__init__(
            agent_name="chat_agent",
            language_model_manager=language_model_manager,
            team_members=team_members,
            working_directory=working_directory,
        )

    def _get_tools(self) -> list[Any]:
        """ Agent 
        """
        return [
            list_tickets,
            get_ticket,
            create_ticket,
            update_ticket,
            search_users,
            get_user,
        ]

    def _get_system_prompt(self) -> str:
        """ Chat Agent 
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
        """ Agent 
        """
        if isinstance(output, str):
            result_text = output
        elif hasattr(output, "content"):
            result_text = str(output.content)
        elif hasattr(output, "output"):
            result_text = str(output.output)
        else:
            result_text = str(output)
        return {"chat_response": result_text}



_chat_agent_instance: ChatAgent | None = None


def get_chat_agent(
    language_model_manager: LanguageModelManager | None = None,
    team_members: list[str] | None = None,
) -> ChatAgent:
    """ ChatAgent 
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
    """ ChatAgent  tool Supervisor 
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

    if isinstance(result, dict):
        content = result.get("output", "") or result.get("content", "") or str(result)
    elif hasattr(result, "content"):
        content = str(result.content)
    else:
        content = str(result)

    logger.info("chat_agent result: %d chars", len(content))
    return content