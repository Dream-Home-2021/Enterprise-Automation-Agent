import os
from typing import Any
from uuid import UUID

from agent.db import postgres as db
from utils.log import get_logger

logger = get_logger(__name__)


# ── 读取（被 graph 节点使用） ──────────────────────────────────────


async def load_user_memory(user_id: int = 1) -> dict[str, Any]:
    """加载用户所有长期记忆。

    返回:
        {
            "profile": {...},       # 用户画像
            "preferences": [...],   # 偏好列表
            "summaries": [...],     # 最近摘要
        }
    """
    profile = await db.get_profile(user_id)
    preferences = await db.get_all_preferences(user_id)
    summaries = await db.get_recent_summaries(user_id, limit=5)

    return {
        "profile": profile["profile"] if profile else {},
        "preferences": preferences,
        "summaries": summaries,
    }


async def load_profile_inject(user_id: int = 1) -> str:
    """加载用户画像并格式化为可注入 system prompt 的文本。

    返回格式:
        === 用户画像 ===
        - 偏好: 喜欢简洁回答 (置信度 0.8)
        - 事实: 在 IT 部门工作 (置信度 0.7)
        === 近期对话摘要 ===
        - [2025-06-20] 用户询问了工单系统配置...
        ====================
    """
    memory = await load_user_memory(user_id)
    parts = ["=== 用户画像 ==="]

    # 1. 结构化画像
    profile = memory.get("profile", {})
    if profile:
        for key, val in profile.items():
            parts.append(f"- {key}: {val}")

    # 2. 偏好
    for pref in memory.get("preferences", []):
        key = pref["key"]
        val = pref["value"]
        conf = pref.get("confidence", 0.5)
        parts.append(f"- {key}: {val} (置信度 {conf})")

    # 3. 近期摘要
    summaries = memory.get("summaries", [])
    if summaries:
        parts.append("=== 近期对话摘要 ===")
        for s in summaries:
            date_str = s.get("created_at", "")[:10] if s.get("created_at") else ""
            summary_text = s.get("summary", "")[:120]
            parts.append(f"- [{date_str}] {summary_text}")

    parts.append("====================")
    return "\n".join(parts)


# ── 写入（被 profile.py 调用） ────────────────────────────────────


async def save_conversation_memory(
    user_id: int,
    session_id: str | UUID,
    summary_text: str,
    tags: list[str] | None = None,
    message_count: int = 0,
):
    """保存对话摘要到长期存储。

    Args:
        user_id: 用户 ID
        session_id: 会话 UUID（字符串或 UUID 对象）
        summary_text: 摘要文本
        tags: 标签列表
        message_count: 消息总数
    """
    if isinstance(session_id, str):
        session_uuid = UUID(session_id)
    else:
        session_uuid = session_id

    await db.save_summary(
        user_id=user_id,
        session_id=session_uuid,
        summary=summary_text,
        tags=tags or [],
        message_count=message_count,
        start_offset=0,
        end_offset=message_count,
    )
    logger.info("Summary saved for session %s (%d msgs)", str(session_uuid)[:8], message_count)


# ── 向量 RAG 检索（被 supervisor graph 使用） ─────────────────────


async def load_relevant_memories(
    user_id: int,
    query: str,
    top_k: int = 5,
) -> str:
    """根据用户查询，从向量记忆中检索最相关的历史记录。

    语义检索流程：
    1. 用 OpenAI embedding API 将 query 向量化
    2. 用余弦相似度搜索 agent_memory_vectors 表
    3. 格式化为文本块返回

    Args:
        user_id: 用户 ID
        query: 用户当前消息文本
        top_k: 返回条数

    Returns:
        格式化后的相关记忆文本，或空字符串。
    """
    if not query or not query.strip():
        return ""

    query_embedding = await _get_embedding(query)
    if not query_embedding:
        return ""

    try:
        results = await db.search_memory_vectors(
            user_id=user_id,
            query_embedding=query_embedding,
            top_k=top_k,
        )
    except Exception as e:
        logger.warning("Vector memory search failed: %s", e)
        return ""

    if not results:
        return ""

    parts = ["=== 相关历史记忆 ==="]
    for r in results:
        score = r.get("score", 0)
        content = r.get("content", "")[:200]
        parts.append(f"- [{score:.2f}] {content}")
    parts.append("======================")

    text = "\n".join(parts)
    logger.info("Vector search: %d results for query (top score=%.2f)", len(results), results[0].get("score", 0))
    return text


async def _get_embedding(text: str) -> list[float] | None:
    """用 OpenAI embedding API 生成文本向量。

    Returns:
        embedding 向量列表，失败返回 None。
    """
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )
        response = client.embeddings.create(
            model="text-embedding-v3",
            input=text[:500],
        )
        return response.data[0].embedding
    except Exception as e:
        logger.warning("Embedding generation failed: %s", e)
        return None