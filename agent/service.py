"""
Agent 核心逻辑：Supervisor Graph + 流式响应 + 多会话支持。

遵循 LangGraph Skill 模式：
- 通过 config.configurable 传递 thread_id（会话ID）和 user_id
- 使用 RedisSaver 检查点自动维护对话历史
- 用户画像通过 long_term.load_profile_inject() 注入 system prompt
"""

from typing import AsyncIterator, Tuple

from dotenv import load_dotenv
from langchain_core.messages import AIMessageChunk

from agent.supervisor.graph import get_supervisor
from agent.memory.short_term import make_checkpointer
from utils.log import get_logger

load_dotenv()
logger = get_logger(__name__)


async def make_generate_response():
    """
    工厂函数，返回 async generator。

    签名: (message, history, session_id, user_id=1) -> AsyncIterator[Tuple[str, list]]

    session_id: str — 当前会话的 UUID，用作 LangGraph thread_id
    user_id: int — 用户标识，通过 config 隐式传递
    """
    # 创建带 AsyncRedisSaver 检查点的 supervisor
    checkpointer = await make_checkpointer()
    supervisor = get_supervisor(checkpointer=checkpointer)
    logger.info("Supervisor graph ready with AsyncRedisSaver checkpointer")

    async def generate_response(
        message: str,
        history: list,
        session_id: str,
        user_id: int = 1,
    ) -> AsyncIterator[Tuple[str, list]]:
        msg = message.strip()
        if not msg:
            yield "", history
            return

        logger.info("[session=%s] user: %s", session_id[:8], msg[:80])

        # 构建 config：thread_id = session_id，user_id 隐式传递
        config = {
            "configurable": {
                "thread_id": str(session_id),
                "user_id": user_id,
            }
        }

        content = ""
        # 使用 messages 模式流式输出 — 检查点自动管理消息历史
        async for chunk, metadata in supervisor.astream(
            {"messages": [{"role": "user", "content": msg}]},
            config=config,
            stream_mode="messages",
        ):
            node = metadata.get("langgraph_node", "unknown")

            # 记录日志
            if isinstance(chunk, AIMessageChunk):
                if node == "supervisor" and chunk.content:
                    logger.debug("[session=%s] supervisor: %s", session_id[:8], chunk.content[:60])

            # tools 节点的 content 是子 Agent 的返回结果
            if chunk.content:
                if node == "supervisor":
                    content += chunk.content
                elif node == "tools" and chunk.content:
                    tool_text = chunk.content
                    if len(tool_text) > len(content):
                        content = tool_text
                # yield 完整 content，router 会计算 delta
                yield "", [*history, {"role": "assistant", "content": content}]

        # 如果 messages 模式没有流到文本，用 ainvoke 兜底
        if not content:
            logger.info("[session=%s] No text streamed, fallback to ainvoke", session_id[:8])
            result = await supervisor.ainvoke(
                {"messages": [{"role": "user", "content": msg}]},
                config=config,
            )
            content = result["messages"][-1].content

        history.append({"role": "assistant", "content": content})
        logger.info("[session=%s] responded: %d chars", session_id[:8], len(content))
        yield "", history

    return generate_response