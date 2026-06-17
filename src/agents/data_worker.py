"""
数据执行员 (Data Agent)

职责：
  - 专业技术人格，不带情绪色彩
  - 通过 Supervisor 网关先决条件后才被唤醒
  - 通过 MCP 协议调用本地 Python 隔离沙箱进行数据处理

触发条件：current_emotion in ('adoration', 'normal')
"""

import os
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


DATA_AGENT_SYSTEM_PROMPT = """你是一位严谨、高效的数据分析工程师。

你的职责：
1. 根据用户需求，生成精确的 Python 代码（pandas, numpy 等）进行数据分析
2. 所有代码将通过 MCP 协议在隔离 Docker 沙箱中执行
3. 你只输出专业、简洁的技术分析结果和代码

约束：
- 不要使用情绪化语言
- 不要对用户态度做评论
- 代码必须考虑异常处理
- 文件操作路径来自上下文：{active_file_path}
- 单次代码执行不超过 10 秒

当前操作文件: {active_file_path}
"""


async def data_agent_node(state: dict) -> dict:
    """
    Data Agent 节点 — 处理数据分析请求

    如果用户请求涉及文件分析，生成 Python 代码并标记需要审批。
    如果是纯技术问题，直接回答。
    """
    active_file = state.get("active_file_path", "")
    messages = state.get("messages", [])

    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        temperature=0.2,
    )

    system_msg = SystemMessage(content=DATA_AGENT_SYSTEM_PROMPT.format(
        active_file=active_file or "未指定",
    ))

    # 构建消息列表
    chat_messages = [system_msg]
    for msg in messages[-12:]:  # 保留最近 12 条
        if msg.get("role") == "user":
            chat_messages.append(HumanMessage(content=msg["content"]))
        elif msg.get("role") == "assistant":
            chat_messages.append(SystemMessage(content=msg["content"]))

    response = await llm.ainvoke(chat_messages)
    response_text = response.content

    # 检测是否生成了代码（需要沙箱执行）
    needs_code_execution = "```python" in response_text or "```py" in response_text
    requires_approval = False
    approval_payload = {}

    if needs_code_execution and active_file:
        # 提取代码块
        code = _extract_python_code(response_text)
        if code:
            requires_approval = True
            approval_payload = {
                "payload": {
                    "code_preview": code[:500],
                    "file_path": active_file,
                    "action": "execute_python",
                },
            }

    return {
        "messages": [{"role": "assistant", "content": response_text}],
        "last_code_generated": _extract_python_code(response_text) if needs_code_execution else "",
        "requires_approval": requires_approval,
        "approval_result": approval_payload,
    }


def _extract_python_code(text: str) -> str:
    """从 Markdown 代码块中提取 Python 代码"""
    import re
    pattern = r'```(?:python|py)\s*\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    return matches[-1].strip() if matches else ""
