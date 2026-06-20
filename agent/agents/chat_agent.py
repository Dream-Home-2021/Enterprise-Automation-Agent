"""
Chat Agent Graph

StateGraph 实现的工单操作 Agent。
节点：assistant → tools（条件边）→ assistant（循环）
"""

from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

from agent.tools.chat.ticket import list_tickets, get_ticket, create_ticket, update_ticket
from agent.tools.chat.user import search_users, get_user
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

def assistant(state: MessagesState, config):
    """LLM 节点：决定调用哪个工具或直接回复。"""
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
    messages = [{"role": "system", "content": system}] + list(state["messages"])
    model = _create_chat_llm().bind_tools(_CHAT_TOOLS)
    return {"messages": [model.invoke(messages)]}


def should_continue(state: MessagesState) -> str:
    """条件边：有 tool_calls 则进 tools 节点，否则结束。"""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "end"


# --- 构建图 ---

def build_chat_agent() -> StateGraph:
    builder = StateGraph(MessagesState)

    builder.add_node("assistant", assistant)
    builder.add_node("tools", ToolNode(_CHAT_TOOLS))

    builder.add_edge(START, "assistant")
    builder.add_conditional_edges("assistant", should_continue, {"continue": "tools", "end": END})
    builder.add_edge("tools", "assistant")

    return builder.compile(name="chat-agent")


_chat_agent_graph = None


def get_chat_agent():
    global _chat_agent_graph
    if _chat_agent_graph is None:
        _chat_agent_graph = build_chat_agent()
    return _chat_agent_graph


# --- 工具包装：供 Supervisor 调用 ---

@tool("call_chat_agent", description="调用工单助手处理工单/用户相关查询。当用户需要查询、创建或更新工单、搜索用户时使用。传入完整的用户问题。")
async def call_chat_agent(query: str) -> str:
    """将 Chat Agent 包装为 tool，供 Supervisor 调用。"""
    agent = get_chat_agent()
    result = await agent.ainvoke({
        "messages": [{"role": "user", "content": query}]
    })
    content = result["messages"][-1].content
    logger.info("chat_agent result: %d chars", len(content))
    return content