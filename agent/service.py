"""
Agent 核心逻辑：创建 ReAct Agent + 流式响应生成器
"""
import os
from typing import Any, AsyncIterator, Tuple

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from tools.math import TOOLS
from utils.log import get_logger

load_dotenv()
logger = get_logger(__name__)


def _create_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "qwen-plus-latest"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        temperature=0.7,
    )


def _log_stream_event(chunk: Any, metadata: dict) -> None:
    """记录流式事件日志：模型文本 / 工具调用 / 工具结果。"""
    node = metadata.get("langgraph_node", "unknown")

    if node == "model":
        # 模型流式文本
        if getattr(chunk, "content", None):
            logger.info("model: %s", chunk.content[:80])
        # 工具调用请求（可能和文本同 chunk，不用 elif）
        if getattr(chunk, "tool_calls", None):
            for tc in chunk.tool_calls:
                logger.info("tool_call: %s %s", tc.get("name", "?"), tc.get("args", {}))
    elif node == "tools" and getattr(chunk, "content", None):
        logger.info("tool_result [%s]: %s", getattr(chunk, "name", "?"), chunk.content[:120])


def make_generate_response():
    """
    工厂函数，返回 Gradio 需要的 async generator。
    签名: (message, history) -> AsyncIterator[Tuple[str, list]]
    """
    llm = _create_llm()
    agent = create_agent(
        model=llm,
        tools=TOOLS,
        system_prompt="你是一个智能助手，可以使用数学工具和互联网搜索工具来帮助用户。",
    )
    logger.info("Agent created with %d tools", len(TOOLS))

    async def generate_response(
        message: str, history: list
    ) -> AsyncIterator[Tuple[str, list]]:
        msg = message.strip()
        if not msg:
            yield "", history
            return

        history.append({"role": "user", "content": msg})
        content = ""
        inputs = {"messages": [{"role": "user", "content": msg}]}

        async for chunk, metadata in agent.astream(inputs, stream_mode="messages"):
            _log_stream_event(chunk, metadata)

            if metadata.get("langgraph_node") == "model" and getattr(chunk, "content", None):
                content += chunk.content
                yield "", [*history, {"role": "assistant", "content": content}]

        # 纯工具调用场景下 content 为空，重新 invoke 获取回复
        if not content:
            logger.info("No text streamed, fallback to ainvoke")
            result = await agent.ainvoke(inputs)
            content = result["messages"][-1].content

        history.append({"role": "assistant", "content": content})
        logger.info("Responded: %d chars", len(content))
        yield "", history

    return generate_response