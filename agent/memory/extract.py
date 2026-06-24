"""
对话提炼 — LLM 从对话中提取偏好、生成摘要、更新画像。

与 LangGraph Skill 中的 `ToolRuntime` + `Store` 模式保持一致，
通过 `get_config()` 获取当前上下文。
"""

import json
import os
import re
import time
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage

from agent.db import postgres as db
from utils.log import get_logger

logger = get_logger(__name__)

# ── LLM 客户端 ──────────────────────────────────────────────────

_EXTRACTION_LLM = None


def _get_llm():
    global _EXTRACTION_LLM
    if _EXTRACTION_LLM is None:
        _EXTRACTION_LLM = ChatOpenAI(
            model=os.getenv("MEMORY_EXTRACT_MODEL", os.getenv("OPENAI_MODEL", "qwen-plus-latest")),
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
            temperature=0.1,
        )
    return _EXTRACTION_LLM


def _parse_llm_json(content: str) -> Any:
    """解析 LLM 返回的 JSON，自动剥离 markdown 代码块。"""
    content = content.strip()
    # 移除 ```json ... ``` 或 ``` ... ``` 包裹
    if content.startswith("```"):
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        content = content.strip()
    return json.loads(content)


# ── 偏好提取 ──────────────────────────────────────────────────────

EXTRACT_PREFERENCES_PROMPT = """你是一个用户画像分析师。从以下对话中提取用户的偏好、习惯、事实等信息。

返回 JSON 数组，每项包含:
  - "key": 简短标识符（英文小写，下划线分隔）
  - "value": 值（字符串、数字或布尔）
  - "confidence": 置信度 0~1
  - "reason": 提取依据的简要说明

规则:
1. 只提取明确表达或强烈暗示的信息
2. 避免提取一次性/临时性的陈述
3. 如果对话中没有可提取的信息，返回空数组 []
4. 不要重复已有事实（通过已有偏好列表去重）

对话内容:
{messages}

已有偏好（供参考去重）:
{existing_keys}

请只输出 JSON 数组，不要其他内容。"""

# 上下文传入--截取最新20条组成prompt--llm输出规定格式
async def extract_preferences(
    user_id: int,
    messages: list[BaseMessage | dict],
    existing_keys: list[str] | None = None,
) -> list[dict]:
    """从对话中提取用户偏好/事实。

    返回: [{"key": "...", "value": ..., "confidence": 0.8, "reason": "..."}, ...]
    """
    if existing_keys is None:
        existing_keys = []

    # 格式化消息

        # 类型判断dict 
        # 为什么？因为 messages 列表里可能混用两种格式：
        # dict — {"role": "user", "content": "..."}（前端/数据库传过来的）
        # BaseMessage 对象 — HumanMessage(...)（LangGraph 内部的）

        # key属性判断 
        # hasattr(HumanMessage("你好"), "type")   # True，HumanMessage 有 type 属性
        # hasattr({"role": "user"}, "type")        # False，dict 没有 type 属性
        # hasattr("hello", "type")                 # False
    msg_texts = []
    for m in messages:
        if isinstance(m, dict):
            # 取 "role" 的值，取不到就返回 "unknown"
            role = m.get("role", "unknown")
            content = str(m.get("content", ""))[:500]
        else:
            role = m.type if hasattr(m, "type") else "unknown"
            content = str(m.content)[:500]
        msg_texts.append(f"[{role}]: {content}")

    # format传参组装提示词
    prompt = EXTRACT_PREFERENCES_PROMPT.format(
        messages="\n".join(msg_texts[-20:]),  # 最近 20 条
        existing_keys=json.dumps(existing_keys, ensure_ascii=False),
    )

    llm = _get_llm()
    t0 = time.monotonic()
    try:
        resp = await llm.ainvoke([{"role": "user", "content": prompt}])
        content = resp.content.strip()
        # 去除可能的 markdown 代码块标记
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            content = content.rsplit("```", 1)[0]
        extracted = json.loads(content.strip())
        if not isinstance(extracted, list):
            extracted = []
        elapsed = (time.monotonic() - t0) * 1000
        logger.info(
            "Extracted %d preferences from %d messages in %.0fms",
            len(extracted), len(msg_texts), elapsed,
        )
        return extracted
    except Exception as e:
        elapsed = (time.monotonic() - t0) * 1000
        logger.warning("Preference extraction failed after %.0fms: %s", elapsed, e)
        return []


# ── 摘要生成 ──────────────────────────────────────────────────────

SUMMARY_PROMPT = """你是一个对话分析师。为以下对话生成一个简洁的摘要。

返回 JSON:
  - "summary": 2-3 句话的摘要
  - "tags": ["标签1", "标签2"] (最多 5 个标签)

对话内容:
{messages}

请只输出 JSON，不要其他内容。"""


async def generate_summary(messages: list[BaseMessage | dict]) -> dict:
    """生成对话摘要。

    返回: {"summary": "...", "tags": [...]}
    """
    msg_texts = []
    for m in messages:
        if isinstance(m, dict):
            role = m.get("role", "unknown")
            content = str(m.get("content", ""))[:300]
        else:
            role = m.type if hasattr(m, "type") else "unknown"
            content = str(m.content)[:300]
        msg_texts.append(f"[{role}]: {content}")

    prompt = SUMMARY_PROMPT.format(messages="\n".join(msg_texts))

    llm = _get_llm()
    t0 = time.monotonic()
    try:
        resp = await llm.ainvoke([{"role": "user", "content": prompt}])
        content = resp.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            content = content.rsplit("```", 1)[0]
        result = json.loads(content.strip())
        elapsed = (time.monotonic() - t0) * 1000
        logger.info(
            "Summary generated: %d chars, %d tags in %.0fms",
            len(result.get("summary", "")), len(result.get("tags", [])), elapsed,
        )
        return result
    except Exception as e:
        elapsed = (time.monotonic() - t0) * 1000
        logger.warning("Summary generation failed after %.0fms: %s", elapsed, e)
        return {"summary": "", "tags": []}


# ── 画像更新 ──────────────────────────────────────────────────────

# 设计思路
# 新提取的偏好: [{"key":"language","value":"en-US"}, {"key":"theme","value":"dark"}]
#         │
#         ├─→ save_preference() → agent_user_preferences 表
#         │     language = "en-US"     ← 单独存储，可按 key 查
#         │     theme    = "dark"      ← 单独存储，UPSERT 去重
#         │
#         └─→ LLM 合并 → upsert_profile() → agent_user_profile 表
#               {"language":"en-US","theme":"dark","name":"小明"}  ← 聚合存储，一次读全

UPDATE_PROFILE_PROMPT = """你是一个用户画像合并专家。将新提取的偏好合并到现有用户画像中。

现有画像:
{current_profile}

新提取的偏好:
{new_preferences}

合并规则:
1. 新偏好与旧画像冲突时，以新为准（置信度+0.1）
2. 新偏好与旧画像一致时，保留旧值，置信度提升
3. 旧画像中的信息如果没有被新偏好覆盖，保留
4. 输出更新后的完整画像 JSON 对象
5. 使用中文键名，保持简洁

请只输出 JSON 对象，不要其他内容。"""


async def update_profile(
    user_id: int,
    new_preferences: list[dict],
) -> dict:
    """将新提取的偏好合并到用户画像 profile 和 preference 中。

    返回: 更新后的完整画像 dict
    """
    current = await db.get_profile(user_id)
    current_profile = current["profile"] if current else {}

    if not new_preferences:
        return current_profile

    # 先写入偏好表（去重）
    for pref in new_preferences:
        key = pref.get("key")
        value = pref.get("value")
        confidence = pref.get("confidence", 0.5)
        if key:
            # 确保 value 为 JSON 字符串，兼容 bool/int/float 等类型
            if not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False)
            await db.save_preference(user_id, key, value, confidence=confidence)

    # 用 LLM 合并画像
    llm = _get_llm()
    prompt = UPDATE_PROFILE_PROMPT.format(
        current_profile=json.dumps(current_profile, ensure_ascii=False, indent=2),
        new_preferences=json.dumps(new_preferences, ensure_ascii=False, indent=2),
    )

    try:
        resp = await llm.ainvoke([{"role": "user", "content": prompt}])
        content = resp.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            content = content.rsplit("```", 1)[0]
        merged = json.loads(content.strip())

        # 提取版本号
        new_version = (current.get("version", 0) or 0) + 1 if current else 1
        await db.upsert_profile(user_id, merged, version=new_version)
        logger.info("Profile updated to version %d", new_version)
        return merged
    except Exception as e:
        logger.warning("Profile merge failed, falling back to direct merge: %s", e)
        # 合并：新偏好覆盖旧
        for pref in new_preferences:
            key = pref.get("key")
            value = pref.get("value")
            if key:
                current_profile[key] = value
        new_version = (current.get("version", 0) or 0) + 1 if current else 1
        await db.upsert_profile(user_id, current_profile, version=new_version)
        return current_profile