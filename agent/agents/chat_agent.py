"""
Chat Agent Graph

StateGraph 实现的工单操作 Agent。
节点：assistant → tools（条件边）→ assistant（循环）

使用 RedisSaver 检查点，通过 `get_config()` 传播父图 config。
"""

from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langgraph.config import get_config

from tools.chat.ticket import list_tickets, get_ticket, create_ticket, update_ticket
from tools.chat.user import search_users, get_user
from agent.memory.long_term import load_profile_inject
from utils.log import get_logger

logger = get_logger(__name__)

_CHAT_TOOLS = [list_tickets, get_ticket, create_ticket, update_ticket, search_users, get_user]


def _create_chat_llm():
    import os
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "qwen-plus-latest"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        temperature=0.1,
    )


# --- 节点函数 ---


async def assistant(state: MessagesState, config):
    """LLM 节点：决定调用哪个工具或直接回复。

    LangGraph 1.x 原生支持 async 节点。
    异步加载用户画像注入 system prompt。
    """
    configurable = config.get("configurable", {}) if config else {}
    user_id = configurable.get("user_id", 1)

    # 异步加载用户画像
    try:
        if user_id:
            profile_text = await load_profile_inject(user_id=user_id)
        else:
            profile_text = ""
    except Exception as e:
        logger.warning("Failed to load user profile for chat agent: %s", e)
        profile_text = ""

    system = (
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

    if profile_text:
        system += f"\n\n{profile_text}"

    messages = [{"role": "system", "content": system}] + list(state["messages"])
    model = _create_chat_llm().bind_tools(_CHAT_TOOLS)
    return {"messages": [await model.ainvoke(messages)]}


def should_continue(state: MessagesState) -> str:
    """条件边：有 tool_calls 则进 tools 节点，否则结束。"""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "continue"
    return "end"


# --- 构建图 ---


def build_chat_agent(checkpointer=None) -> StateGraph:
    """构建 Chat Agent Graph。"""
    builder = StateGraph(MessagesState)

    builder.add_node("assistant", assistant)
    builder.add_node("tools", ToolNode(_CHAT_TOOLS))

    builder.add_edge(START, "assistant")
    builder.add_conditional_edges("assistant", should_continue, {"continue": "tools", "end": END})
    builder.add_edge("tools", "assistant")

    return builder.compile(checkpointer=checkpointer, name="chat-agent")


_chat_agent_graph = None


def get_chat_agent(checkpointer=None):
    """获取 Chat Agent Graph 单例。"""
    global _chat_agent_graph
    if _chat_agent_graph is None:
        _chat_agent_graph = build_chat_agent(checkpointer=checkpointer)
    return _chat_agent_graph


# --- 工具包装：供 Supervisor 调用 ---

@tool("call_chat_agent", description="调用工单助手处理工单/用户相关查询。当用户需要查询、创建或更新工单、搜索用户时使用。传入完整的用户问题。")
async def call_chat_agent(query: str) -> str:
    """
    将 Chat Agent 包装为 tool，供 Supervisor 调用。

    使用 `get_config()` 获取当前运行的 config（含 thread_id, user_id），
    传播给子图，确保子图在同一个检查点线程下工作。
    """
    # 通过 get_config() 获取当前运行的配置（LangGraph 自动注入）
    current_config = get_config()
    if current_config:
        logger.info("call_chat_agent propagating config: thread_id=%s",
                     current_config.get("configurable", {}).get("thread_id"))

    agent = get_chat_agent()
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": query}]},
        config=current_config,  # 传播 thread_id + user_id
    )
    content = result["messages"][-1].content
    logger.info("chat_agent result: %d chars", len(content))
    return content