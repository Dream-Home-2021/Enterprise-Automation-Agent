"""
用户画像构建器 — 长期记忆提取调度器。

混合策略：
1. 即时提取（extract_from_conversation）：对话结束后立即提取偏好 + 合并画像
2. 批量提取（batch_process_pending）：后台定时批量生成摘要 + 向量存储

所有提取操作 try/except，失败仅记录日志，不抛异常（错误隔离）。
"""

import asyncio
import os
import time
from typing import Any

from agent.memory.long_term import load_user_memory
from agent.memory.extract import extract_preferences, generate_summary, update_profile
from agent.db import postgres as db
from agent.memory.history import load_conversation_history
from utils.log import get_logger

logger = get_logger(__name__)

_CONFIG = {
    "interval_mins": int(os.getenv("MEMORY_BATCH_INTERVAL_MINUTES", "15")),
    "extract_interval": int(os.getenv("MEMORY_EXTRACT_INTERVAL", "10")),
}

_background_task: asyncio.Task | None = None


# ── 即时提取 ─────────────────────────────────────────────────────────


async def extract_from_conversation(
    user_id: int,
    session_id: str,
    messages: list[dict],
) -> dict[str, Any]:
    """对话结束后即时提取偏好并合并到画像。

    异步触发（fire-and-forget），不阻塞调用方。
    偏好提取 + 画像合并同步执行，不包含摘要和向量（由后台批量处理）。

    Args:
        user_id: 用户 ID
        session_id: 会话 ID
        messages: 完整消息列表

    Returns:
        {"preferences_extracted": int, "profile_updated": bool, "elapsed_ms": float}
    """
    t0 = time.monotonic()
    result = {"preferences_extracted": 0, "profile_updated": False, "elapsed_ms": 0.0}

    try:
        message_count = len(messages)
        if message_count < 2:
            logger.debug("Extraction skipped: too few messages (%d)", message_count)
            result["elapsed_ms"] = (time.monotonic() - t0) * 1000
            return result

        # 1. 获取已有偏好 key，避免重复提取
        existing_prefs = await db.get_all_preferences(user_id)
        existing_keys = [p["key"] for p in existing_prefs]

        # 2. LLM 提取偏好
        new_prefs = await extract_preferences(user_id, messages, existing_keys=existing_keys)
        result["preferences_extracted"] = len(new_prefs)

        # 3. 合并到画像
        if new_prefs:
            await update_profile(user_id, new_prefs)
            result["profile_updated"] = True

        elapsed = (time.monotonic() - t0) * 1000
        result["elapsed_ms"] = elapsed
        logger.info(
            "Extraction [prefs] for session %s: %d items in %.0fms (profile_updated=%s)",
            session_id[:8], len(new_prefs), elapsed, result["profile_updated"],
        )
        return result

    except Exception as e:
        elapsed = (time.monotonic() - t0) * 1000
        result["elapsed_ms"] = elapsed
        logger.warning(
            "Extraction [prefs] failed for session %s after %.0fms: %s",
            session_id[:8], elapsed, e,
        )
        return result


# ── 后台批量处理 ──────────────────────────────────────────────────────


async def get_pending_sessions(interval_mins: int = 15) -> list[dict]:
    """查询需要批量处理的会话。

    条件：
    - message_count > 0
    - updated_at 在 30 分钟内（活跃会话）
    - 没有对应的摘要（无 `agent_conversation_summaries` 行）

        [{"session_id": UUID, "user_id": int, "message_count": int}, ...]
    """
    try:
        pool = await db.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT s.id AS session_id, s.user_id, s.message_count
                   FROM agent_sessions s
                   WHERE s.message_count > 0
                     AND s.updated_at >= NOW() - INTERVAL '30 minutes'
                   ORDER BY s.updated_at DESC
                   LIMIT 50"""
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("get_pending_sessions failed: %s", e)
        return []


async def batch_process_pending(interval_mins: int = 15):
# 双轨设计
        # Summary 轨（非语义）是为了应对【确定性的系统检索】
        # Vector 轨（语义）是为了应对【模糊、长尾的聊天回忆】

    """批量处理待办会话的摘要生成 + 向量化存储。

    1. 查待办会话
    2. 读取 Redis checkpoint 消息
    3. 生成摘要 → 写入 agent_conversation_summaries
    4. 向量化用户消息 → 写入 agent_memory_vectors
    """
    t_start = time.monotonic()
    sessions = await get_pending_sessions(interval_mins)
    # print(sessions)
    if not sessions:
        logger.debug("Batch extraction: no pending sessions")
        return

    logger.info("Batch extraction: processing %d pending sessions", len(sessions))
    processed = 0
    # 遍历出uuid和用户，来获取检查点内的对应会话中的上下文 生成摘要
    for sess in sessions:
        # print(sess)
        t0 = time.monotonic()
        session_id = str(sess["session_id"])
        user_id = sess["user_id"]

        try:
            # 1. 读取 Redis 中的完整消息
            messages = await load_conversation_history(session_id)
            if not messages or len(messages) < 2:
                continue

            # 2. 生成摘要

            # 只要符合 Summary，就一定要进 Vector。 Summary 保证了 Agent 知道“我是谁、我在哪、我的规矩是什么”（绝对清醒）；
            # Vector 保证了 Agent 记得“我们以前在什么场景下聊过什么”（极具人情味）。
            summary_result = await generate_summary(messages)
            if summary_result and summary_result.get("summary"):
                from uuid import UUID
                session_uuid = UUID(session_id)
                await db.save_summary(
                    user_id=user_id,
                    session_id=session_uuid,
                    summary=summary_result["summary"],
                    tags=summary_result.get("tags", []),
                    message_count=len(messages),
                    start_offset=0,
                    end_offset=len(messages),
                )

            # 3. 向量化用户消息
            await _save_vectors_async(user_id, session_id, messages)

            elapsed = (time.monotonic() - t0) * 1000
            logger.info("Batch extraction [session %s]: done in %.0fms", session_id[:8], elapsed)
            processed += 1

        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            logger.warning(
                "Batch extraction failed for session %s after %.0fms: %s",
                session_id[:8], elapsed, e,
            )

    total_elapsed = (time.monotonic() - t_start) * 1000
    logger.info(
        "Batch extraction complete: %d/%d sessions in %.0fms",
        processed, len(sessions), total_elapsed,
    )


async def _save_vectors_async(user_id: int, session_id: str, messages: list):
    """将对话中的用户消息向量化并存储到 agent_memory_vectors。

    使用 OpenAI embedding API 批量生成向量。
    """
    from uuid import UUID

    # 只用用户消息做向量（每条消息一个向量）
    # 最左边的 m 表示"把符合条件的 m 本身放入新列表"，相当于 append(m)
    user_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
    if not user_msgs:
        return

    # 将human的消息遍历提取出上下文
    texts = []
    for m in user_msgs:
        content = str(m.get("content", "")).strip()
        if len(content) >= 5:
            texts.append(content[:500])

    if not texts:
        return

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )

        # DashScope text-embedding-v3 单次批量上限 10 条，分批处理
        BATCH_SIZE = 10
        all_embeddings: list[list[float]] = []
        for batch_start in range(0, len(texts), BATCH_SIZE):
            batch = texts[batch_start : batch_start + BATCH_SIZE]
            response = client.embeddings.create(
                model="text-embedding-v3",
                input=batch,
            )
            all_embeddings.extend(item.embedding for item in response.data)

        # 关联绑定
        # 为了防止两条summary和vector轨道的数据完全割裂，在向量数据库的 Metadata（元数据） 中做关联绑定。
        session_uuid = UUID(session_id) if session_id else None
        for i, (text, emb) in enumerate(zip(texts, all_embeddings)):
            metadata = {"source": "conversation", "index": i}
            await db.save_memory_vector(
                user_id=user_id,
                session_id=session_uuid,
                content=text,
                embedding=emb,
                metadata=metadata,
            )

        logger.info("Saved %d memory vectors for session %s", len(texts), session_id[:8])
    except Exception as e:
        logger.warning("Vector saving skipped for session %s: %s", session_id[:8], e)


# ── 后台定时任务管理 ─────────────────────────────────────────────────


async def start_background_extractor():
    """启动后台定时提取任务。

    由 app_html.py 的 lifespan 在 startup 时调用。
    每 interval_mins 分钟执行一次 batch_process_pending。
    """
    global _background_task

    if _background_task is not None and not _background_task.done():
        logger.warning("Background extractor already running")
        return

    async def _loop():
        interval = _CONFIG["interval_mins"] * 15
        logger.info("Background extractor started (interval=%d min)", _CONFIG["interval_mins"])
        while True:
            try:
                await asyncio.sleep(interval)
                await batch_process_pending(_CONFIG["interval_mins"])
            except asyncio.CancelledError:
                logger.info("Background extractor cancelled")
                break
            except Exception as e:
                logger.error("Background extractor error: %s", e)

    _background_task = asyncio.create_task(_loop())
    logger.info("Background extractor task created")


async def stop_background_extractor():
    """优雅停止后台提取任务。

    由 app_html.py 的 lifespan 在 shutdown 时调用。
    """
    global _background_task
    if _background_task is not None and not _background_task.done():
        _background_task.cancel()
        try:
            await _background_task
        except asyncio.CancelledError:
            pass
        _background_task = None
        logger.info("Background extractor stopped")