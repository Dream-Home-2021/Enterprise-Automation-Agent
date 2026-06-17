"""
消息链滚动截断器 (Context Window Truncation)

职责：
  - 每次呼叫 LLM 节点前执行滚动修剪
  - 默认保留最新 12 条消息（约 3-4 轮完整对话）
  - System Prompt 和实体元数据享有截断豁免权
  - 被切除消息的核心语义已由异步浓缩模块留存至向量库
"""

import os
from dotenv import load_dotenv

load_dotenv()

MAX_MESSAGES = int(os.getenv("MAX_SHORT_TERM_MESSAGES", "12"))


async def context_truncation_node(state: dict) -> dict:
    """
    消息链截断节点

    保留策略：
      1. 首部 System Prompt 永久保留（豁免截断）
      2. 实体元数据（active_file_path 等）不在消息链中，不受影响
      3. 用户/助手消息仅保留最新 MAX_MESSAGES 条
      4. 被切除消息语义已在异步管道中存入向量库

    Returns:
        截断后的 messages 列表
    """
    messages = state.get("messages", [])

    if len(messages) <= MAX_MESSAGES:
        return {}  # 无需截断

    # 分离系统消息和对话消息
    system_msgs = [m for m in messages if m.get("role") == "system"]
    conversation_msgs = [m for m in messages if m.get("role") != "system"]

    # 保留最新 N 条对话消息
    if len(conversation_msgs) > MAX_MESSAGES:
        conversation_msgs = conversation_msgs[-MAX_MESSAGES:]

    # 重组
    truncated = system_msgs + conversation_msgs

    removed_count = len(messages) - len(truncated)
    if removed_count > 0:
        print(f"[truncator] Trimmed {removed_count} messages, keeping {len(truncated)}.")

    return {
        "messages": truncated,
    }


def truncate_messages(messages: list[dict], max_count: int = MAX_MESSAGES) -> list[dict]:
    """
    工具函数 — 直接截断消息列表（非节点版）

    Args:
        messages: 原始消息列表
        max_count: 最大保留数

    Returns:
        截断后的消息列表
    """
    system_msgs = [m for m in messages if m.get("role") == "system"]
    conversation_msgs = [m for m in messages if m.get("role") != "system"]

    if len(conversation_msgs) > max_count:
        conversation_msgs = conversation_msgs[-max_count:]

    return system_msgs + conversation_msgs
