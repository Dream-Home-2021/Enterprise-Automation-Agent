# -*- coding: utf-8 -*-

"""
Agent 核心逻辑：创建 ReAct Agent + 流式响应生成器
"""

import os
from typing import AsyncIterator, Tuple

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from tools.math import TOOLS

load_dotenv()


def create_llm():
    """创建 LLM 实例，从 .env 读取配置"""
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "qwen-plus-latest"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        temperature=0.7,
    )


def make_generate_response():
    """
    工厂函数，返回 Gradio 需要的 async generator。
    签名: (message, history) -> AsyncIterator[Tuple[str, list]]
    """
    llm = create_llm()
    agent = create_agent(
        model=llm,
        tools=TOOLS,
        system_prompt="你是一个智能助手，可以使用数学工具和互联网搜索工具来帮助用户。",
    )

    async def generate_response(
        message: str, history: list
    ) -> AsyncIterator[Tuple[str, list]]:
        if not message.strip():
            yield "", history
            return

        # 将用户消息加入历史
        history.append({"role": "user", "content": message})

        assistant_content = ""

        # 使用 messages 模式逐 token 流式输出
        async for token, metadata in agent.astream(
            {"messages": [{"role": "user", "content": message}]},
            stream_mode="messages",
        ):
            node = metadata.get("langgraph_node", "")

            # 只在模型节点输出文本 token（跳过工具调用 token 和工具结果 token）
            if node == "model" and hasattr(token, "content") and token.content:
                assistant_content += token.content
                # 构造临时历史用于逐步显示
                temp_history = list(history)
                if temp_history and temp_history[-1]["role"] == "assistant":
                    temp_history[-1] = {
                        "role": "assistant",
                        "content": assistant_content,
                    }
                else:
                    temp_history.append({
                        "role": "assistant",
                        "content": assistant_content,
                    })
                yield "", temp_history

        # 流结束，确保最终回复写入 history
        if assistant_content:
            if history and history[-1]["role"] == "assistant":
                history[-1]["content"] = assistant_content
            else:
                history.append({"role": "assistant", "content": assistant_content})
        else:
            # 无文本输出（仅工具调用场景），单独 invoke 获取最终回复
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": message}]}
            )
            final_content = result["messages"][-1].content
            history.append({"role": "assistant", "content": final_content})

        yield "", history

    return generate_response