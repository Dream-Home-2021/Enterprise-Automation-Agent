"""
Supervisor Graph

意图识别 + 路由。判断用户意图，路由到 Chat Agent 或直接回复。
使用 RedisSaver 检查点持久化会话状态。

遵循 LangGraph Skill 模式：
- 通过 `config.configurable` 获取 user_id
- supervisor 节点为 async，可异步加载用户画像
- 使用 `get_config()` 在子工具中传播 config
- 编译时注入 `checkpointer`（由上层决定，不在本模块创建）
"""

import os
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

from agent.agents.chat_agent import call_chat_agent
from agent.memory.long_term import load_profile_inject, load_relevant_memories
from utils.log import get_logger

logger = get_logger(__name__)

_SUPERVISOR_TOOLS = [call_chat_agent]

# 通过环境变量控制向量检索开关和条数
_MEMORY_VECTOR_TOP_K = int(os.getenv("MEMORY_VECTOR_TOP_K", "5"))


def _create_supervisor_llm():
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "qwen-plus-latest"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        temperature=0.1,
    )


# --- 节点函数 ---


async def supervisor(state: MessagesState, config):
    """
    Supervisor 节点：判断用户意图，决定路由方向。

    通过 config.configurable 获取 user_id，异步加载用户画像注入 system prompt。
    LangGraph 1.x 支持 async 节点函数。
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
        logger.warning("Failed to load user profile: %s", e)
        profile_text = ""

    # 向量 RAG 检索：从语义记忆中检索与当前用户消息相关的历史记录
    if _MEMORY_VECTOR_TOP_K > 0 and state.get("messages"):
        last_msg = state["messages"][-1]
        query_text = getattr(last_msg, "content", None) or (last_msg.get("content") if isinstance(last_msg, dict) else None)
        if query_text and isinstance(query_text, str):
            try:
                relevant = await load_relevant_memories(
                    user_id=user_id,
                    query=query_text,
                    top_k=_MEMORY_VECTOR_TOP_K,
                )
                if relevant:
                    profile_text = profile_text + "\n\n" + relevant if profile_text else relevant
            except Exception as e:
                logger.warning("Vector memory retrieval failed: %s", e)

    system = (
        "你是 Zammad Agent 系统的监督者，负责判断用户意图并路由到正确的子 Agent。\n\n"
        "你有以下工具可用：\n"
        "- call_chat_agent：当用户需要查询工单、创建工单、更新工单或搜索用户时调用\n\n"
        "判断规则：\n"
        "- 如果用户只是打招呼、闲聊，直接回复（不调工具）\n"
        "- 如果用户需要查询/操作工单或用户，调用 call_chat_agent\n"
        "- 如果用户问的不确定，也调用 call_chat_agent 让它处理"
    )

    if profile_text:
        system += f"\n\n{profile_text}"

    messages = [{"role": "system", "content": system}] + list(state["messages"])
    model = _create_supervisor_llm().bind_tools(_SUPERVISOR_TOOLS)
    return {"messages": [model.invoke(messages)]}



def should_continue(state: MessagesState) -> str:
    """条件边：有 tool_calls 则进 tools 节点，否则结束。"""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "continue"
    return "end"


# --- 构建图 ---


def build_supervisor(checkpointer=None) -> StateGraph:
    """
    构建 Supervisor Graph。

    Args:
        checkpointer: 可选的检查点实例（RedisSaver / MemorySaver），
                      由上层决定，本模块不负责创建。
    """
    builder = StateGraph(MessagesState)

    builder.add_node("supervisor", supervisor)
    builder.add_node("tools", ToolNode(_SUPERVISOR_TOOLS))

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges("supervisor", should_continue, {"continue": "tools", "end": END})
    builder.add_edge("tools", "supervisor")

    return builder.compile(checkpointer=checkpointer, name="supervisor")


_supervisor_graph = None


def get_supervisor(checkpointer=None):
    """获取 Supervisor Graph 单例。"""
    global _supervisor_graph
    if _supervisor_graph is None:
        _supervisor_graph = build_supervisor(checkpointer=checkpointer)
    return _supervisor_graph