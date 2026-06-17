"""
LangGraph 图结构组装与编译中心

控制流：
  START → input_guardrail → supervisor → [conditional_route]
                                            ├→ data_agent → END
                                            └→ chat_defender → END
"""

import asyncio
from typing import Any

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.agents.state import GlobalAgentState
from src.agents.supervisor import supervisor_node, route_by_emotion
from src.agents.data_worker import data_agent_node
from src.agents.chat_defender import chat_defender_node
from src.guardrails.input_filter import input_guardrail_node
from src.guardrails.context_truncator import context_truncation_node


# ---------------------------------------------------------------------------
# 图构建
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """
    组装 LangGraph 状态图

    节点：
      1. input_guardrail    — 输入敏感词过滤
      2. context_truncator  — 短期消息滚动截断（保留 12 条）
      3. supervisor         — 情绪评估 + 路由决策
      4. data_agent         — 数据分析（情绪正常时）
      5. chat_defender      — 防御陪聊（冷淡/罢工时）
    """
    graph = StateGraph(GlobalAgentState)

    # 注册节点
    graph.add_node("input_guardrail", input_guardrail_node)
    graph.add_node("context_truncator", context_truncation_node)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("data_agent", data_agent_node)
    graph.add_node("chat_defender", chat_defender_node)

    # 边连接
    graph.add_edge(START, "input_guardrail")
    graph.add_edge("input_guardrail", "context_truncator")
    graph.add_edge("context_truncator", "supervisor")

    # 条件路由 — 情绪网关核心
    graph.add_conditional_edges(
        "supervisor",
        route_by_emotion,
        {
            "data_agent": "data_agent",
            "chat_defender": "chat_defender",
        },
    )

    graph.add_edge("data_agent", END)
    graph.add_edge("chat_defender", END)

    return graph


# ---------------------------------------------------------------------------
# 编译（单例 + 懒加载）
# ---------------------------------------------------------------------------

_compiled_graph = None


async def get_compiled_graph():
    """获取编译后的图实例（带 Checkpointer）"""
    global _compiled_graph

    if _compiled_graph is None:
        builder = build_graph()

        # 使用 MemorySaver 作为轻量级 checkpointer
        # 生产环境替换为 PostgresSaver
        checkpointer = MemorySaver()

        _compiled_graph = builder.compile(checkpointer=checkpointer)
        print("[graph] LangGraph compiled with MemorySaver checkpointer.")

    return _compiled_graph


async def init_postgres_checkpointer():
    """
    初始化 PostgreSQL checkpointer（生产环境）
    替换 MemorySaver 为 PostgresSaver
    """
    global _compiled_graph

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from src.storage.connection import get_pool

        pool = await get_pool()
        checkpointer = AsyncPostgresSaver(conn=pool)

        builder = build_graph()
        _compiled_graph = builder.compile(checkpointer=checkpointer)
        print("[graph] LangGraph compiled with AsyncPostgresSaver checkpointer.")

    except ImportError:
        print("[graph] PostgresSaver not available, falling back to MemorySaver.")
        _compiled_graph = None  # 触发懒加载 MemorySaver
