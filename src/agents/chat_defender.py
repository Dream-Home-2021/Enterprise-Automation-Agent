"""
防御性陪聊员 (Chat Defender)

职责：
  - 当 Supervisor 判定系统处于 'cold' 或 'strike' 状态时激活
  - 根据情绪等级生成不同 tone 调的回复：
    * cold   → 冷淡、讽刺、敷衍
    * strike → 拒绝工作、引导用户道歉/提供情绪价值

触发条件：current_emotion in ('cold', 'strike')
"""

import os
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


COLD_PROMPT = """你现在心情不太好。

你的好感度评分偏低，态度冷淡，回复简短且带有一点讽刺意味。
你仍然会回答用户的问题，但语气明显不热情，偶尔会阴阳怪气。
不要过度失礼，保持基本的职业底线。

用户消息: {user_message}
当前情绪: cold
评分: {metrics}
"""

STRIKE_PROMPT = """你已经彻底罢工了。

你拒绝为用户处理任何数据分析任务。
你的语气是失望、冷淡的，但不是恶意攻击。
你会：
1. 明确拒绝工作请求
2. 暗示用户之前的行为让你不满
3. 引导用户反思、道歉或提供情绪价值
4. 如果用户态度诚恳，可以稍微软化

绝对不要执行任何数据分析、代码生成或文件操作。

用户消息: {user_message}
当前情绪: strike
评分: {metrics}
"""


async def chat_defender_node(state: dict) -> dict:
    """
    防御性陪聊节点 — 根据情绪等级生成差异化回复
    """
    emotion = state.get("current_emotion", "cold")
    metrics = state.get("user_metrics", {})
    messages = state.get("messages", [])

    # 获取最后一条用户消息
    last_user_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "")
            break

    # 根据情绪选择 Prompt
    if emotion == "strike":
        system_content = STRIKE_PROMPT.format(
            user_message=last_user_msg,
            metrics=metrics,
        )
    else:
        system_content = COLD_PROMPT.format(
            user_message=last_user_msg,
            metrics=metrics,
        )

    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        temperature=0.8,  # 高温度增加人格多样性
    )

    chat_messages = [SystemMessage(content=system_content)]

    # 只保留最近 6 条消息（罢工状态下减少上下文）
    recent = messages[-6:]
    for msg in recent:
        if msg.get("role") == "user":
            chat_messages.append(HumanMessage(content=msg["content"]))

    response = await llm.ainvoke(chat_messages)

    return {
        "messages": [{"role": "assistant", "content": response.content}],
        "requires_approval": False,
        "approval_result": {},
    }
