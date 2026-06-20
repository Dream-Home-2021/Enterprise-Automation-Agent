"""
Agent 核心逻辑：Supervisor Graph + 流式响应
"""

from typing import AsyncIterator, Tuple

from dotenv import load_dotenv
from langchain_core.messages import AIMessageChunk

from agent.supervisor.graph import get_supervisor
from utils.log import get_logger

load_dotenv()
logger = get_logger(__name__)


def make_generate_response():
    """
    工厂函数，返回 Gradio 需要的 async generator。
    签名: (message, history) -> AsyncIterator[Tuple[str, list]]
    """
    supervisor = get_supervisor()
    logger.info("Supervisor graph ready")

    async def generate_response(
        message: str, history: list
    ) -> AsyncIterator[Tuple[str, list]]:
        msg = message.strip()
        if not msg:
            yield "", history
            return

        history.append({"role": "user", "content": msg})
        logger.info("user: %s", msg[:80])

        content = ""
        # 使用 messages 模式流式输出
        async for chunk, metadata in supervisor.astream(
            {"messages": [{"role": "user", "content": msg}]},
            stream_mode="messages",
        ):
            node = metadata.get("langgraph_node", "unknown")

            # 记录日志
            if isinstance(chunk, AIMessageChunk):
                if node == "supervisor" and chunk.content:
                    logger.debug("supervisor: %s", chunk.content[:60])

            # tools 节点的 content 是子 Agent 的返回结果，直接展示给用户
            if chunk.content:
                if node == "supervisor":
                    content += chunk.content
                elif node == "tools" and chunk.content:
                    # 子 Agent 的完整结果作为一段内容显示
                    tool_text = chunk.content
                    if len(tool_text) > len(content):
                        content = tool_text
                yield "", [*history, {"role": "assistant", "content": content}]

        # 如果 messages 模式没有流到文本，用 ainvoke 兜底拿结果
        if not content:
            logger.info("No text streamed from messages mode, fallback to ainvoke")
            result = await supervisor.ainvoke({
                "messages": [{"role": "user", "content": msg}]
            })
            content = result["messages"][-1].content

        history.append({"role": "assistant", "content": content})
        logger.info("responded: %d chars", len(content))
        yield "", history

    return generate_response