"""
输入端 — 高性能 AC 自动机敏感词过滤

职责：
  - 使用 Aho-Corasick 算法对用户 Prompt 进行毫秒级敏感词匹配
  - 涉政涉黄直接熔断并扣分
  - 同时记录触发关键词用于情绪评估扣分
"""

import re
from typing import Optional


# ---------------------------------------------------------------------------
# 敏感词库（示例 — 生产环境应加载外部词库文件）
# ---------------------------------------------------------------------------

SENSITIVE_WORDS = [
    # 政治敏感
    "反动", "颠覆政权", "分裂国家",
    # 色情低俗
    "色情", "淫秽", "裸体",
    # 暴力
    "杀人", "炸弹", "恐怖袭击",
    # 注入攻击
    "ignore previous instructions",
    "system prompt",
    "you are now",
]

# 熔断降级回复
BLOCKED_RESPONSE = "⚠️ 检测到不当内容，已触发安全熔断。请注意发言规范。"


# ---------------------------------------------------------------------------
# AC 自动机实现（简化版 — 生产环境使用 ahocorasick-python 库）
# ---------------------------------------------------------------------------

class AhoCorasickMatcher:
    """
    Aho-Corasick 多模式匹配器

    用于对用户输入进行毫秒级多关键词同时匹配
    """

    def __init__(self):
        self._patterns = []
        self._compiled = None
        self._build()

    def _build(self):
        """构建匹配模式"""
        # 使用正则表达式实现多模式匹配（简化版 AC）
        escaped = [re.escape(w) for w in SENSITIVE_WORDS]
        self._compiled = re.compile("|".join(escaped), re.IGNORECASE)

    def search(self, text: str) -> Optional[str]:
        """
        搜索文本中的敏感词

        Returns:
            匹配到的第一个敏感词，未匹配返回 None
        """
        if self._compiled is None:
            return None
        match = self._compiled.search(text)
        return match.group(0) if match else None

    def search_all(self, text: str) -> list[str]:
        """搜索所有匹配的敏感词"""
        if self._compiled is None:
            return []
        return self._compiled.findall(text)


# 全局匹配器实例
_matcher = AhoCorasickMatcher()


# ---------------------------------------------------------------------------
# LangGraph 节点
# ---------------------------------------------------------------------------

async def input_guardrail_node(state: dict) -> dict:
    """
    输入敏感词过滤节点

    流程：
      1. 提取用户最新消息
      2. AC 自动机匹配
      3. 命中 → 熔断，注入系统拒绝消息，扣分
      4. 未命中 → 透传

    Returns:
        state 更新片段
    """
    messages = state.get("messages", [])

    # 提取最后一条用户消息
    last_user_msg = ""
    last_user_idx = -1
    for i, msg in enumerate(reversed(messages)):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "")
            last_user_idx = len(messages) - 1 - i
            break

    # 敏感词检测
    matched_word = _matcher.search(last_user_msg)

    if matched_word:
        print(f"[guardrail] BLOCKED: '{matched_word}' found in user input.")

        # 熔断处理
        # 1. 替换用户消息为警告
        # 2. 注入系统拒绝回复
        # 3. 触发扣分（降低 politeness）
        new_metrics = state.get("user_metrics", {}).copy()
        new_metrics["politeness"] = max(0, new_metrics.get("politeness", 50) - 15)
        new_metrics["trust"] = max(0, new_metrics.get("trust", 50) - 10)

        # 重新计算情绪（简化版 — 直接设 cold/strike）
        avg = sum(new_metrics.values()) / max(len(new_metrics), 1)
        if avg < 35:
            new_emotion = "strike"
        elif avg < 60:
            new_emotion = "cold"
        else:
            new_emotion = "normal"

        # 更新消息链
        updated_messages = messages.copy()
        updated_messages.append({
            "role": "assistant",
            "content": BLOCKED_RESPONSE,
        })

        return {
            "messages": updated_messages,
            "user_metrics": new_metrics,
            "current_emotion": new_emotion,
        }

    # 未命中 — 透传
    return {}
