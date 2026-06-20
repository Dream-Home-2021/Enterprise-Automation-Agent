"""
Supervisor Graph

意图识别 + 路由。判断用户意图，路由到 Chat Agent 或直接回复。
"""

import os

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

from agent.agents.chat_agent import call_chat_agent
from utils.log import get_logger

logger = get_logger(__name__)

_SUPERVISOR_TOOLS = [call_chat_agent]


def _create_supervisor_llm():
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "qwen-plus-latest"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        temperature=0.1,
    )


# --- 节点函数 ---

def supervisor(state: MessagesState, config):
    """Supervisor 节点：判断用户意图，决定路由方向。"""
    system = (
        "你是 Zammad Agent 系统的监督者，负责判断用户意图并路由到正确的子 Agent。\n\n"
        "你有以下工具可用：\n"
        "- call_chat_agent：当用户需要查询工单、创建工单、更新工单或搜索用户时调用\n\n"
        "判断规则：\n"
        "- 如果用户只是打招呼、闲聊，直接回复（不调工具）\n"
        "- 如果用户需要查询/操作工单或用户，调用 call_chat_agent\n"
        "- 如果用户问的不确定，也调用 call_chat_agent 让它处理"
    )
    messages = [{"role": "system", "content": system}] + list(state["messages"])
    model = _create_supervisor_llm().bind_tools(_SUPERVISOR_TOOLS)
    return {"messages": [model.invoke(messages)]}


def should_continue(state: MessagesState) -> str:
    """条件边：有 tool_calls 则进 tools 节点，否则结束。"""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "end"


# --- 构建图 ---

def build_supervisor() -> StateGraph:
    builder = StateGraph(MessagesState)

    builder.add_node("supervisor", supervisor)
    builder.add_node("tools", ToolNode(_SUPERVISOR_TOOLS))

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges("supervisor", should_continue, {"continue": "tools", "end": END})
    builder.add_edge("tools", "supervisor")

    return builder.compile(name="supervisor")


_supervisor_graph = None


def get_supervisor():
    global _supervisor_graph
    if _supervisor_graph is None:
        _supervisor_graph = build_supervisor()
    return _supervisor_graph