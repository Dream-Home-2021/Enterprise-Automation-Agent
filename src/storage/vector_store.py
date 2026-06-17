"""
PGVector 操作流 — 长期日记向量检索与 RAG 匹配

功能：
  - 向量写入（Embedding + PGVector）
  - 混合检索（PGVector + TSVector）
  - 元数据预过滤（WHERE username = :current_user）
  - Reranker 精排（bge-reranker）
"""

import os
from typing import Optional

import asyncpg
import numpy as np
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Embedding 工具
# ---------------------------------------------------------------------------

async def get_embedding(text: str) -> list[float]:
    """
    将文本转化为 Embedding 向量（OpenAI API）
    """
    from langchain_openai import OpenAIEmbeddings

    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    embeddings = OpenAIEmbeddings(model=model)
    vector = await embeddings.aembed_query(text)
    return vector


# ---------------------------------------------------------------------------
# 写入观察日记
# ---------------------------------------------------------------------------

async def insert_observation(
    username: str,
    content: str,
    embedding: list[float],
    session_id: str = "",
) -> int:
    """
    将一条观察日记写入 user_observations 表

    Args:
        username: 用户标识
        content: 观察日记文本（~100字）
        embedding: 向量表示
        session_id: 关联会话 ID

    Returns:
        新记录 ID
    """
    from src.storage.connection import get_pool

    pool = await get_pool()
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO user_observations (username, content, embedding, session_id, content_tsv)
            VALUES ($1, $2, $3::vector, $4, to_tsvector('simple', $2))
            RETURNING id
        """, username, content, embedding_str, session_id)

        return row["id"]


# ---------------------------------------------------------------------------
# 混合检索 + Reranker
# ---------------------------------------------------------------------------

async def hybrid_search_observations(
    username: str,
    query_text: str,
    query_embedding: list[float],
    top_k: int = 10,
    final_k: int = 2,
) -> list[dict]:
    """
    混合检索：PGVector 向量检索 + TSVector 全文检索

    流程：
      1. 硬性 SQL 过滤 WHERE username = :current_user
      2. 同时启动向量检索和全文检索
      3. 合并 Top-K 候选
      4. Reranker 精排取 Top-final_k

    Args:
        username: 用户标识（硬隔离过滤）
        query_text: 查询文本（用于全文检索和 reranker）
        query_embedding: 查询向量（用于向量检索）
        top_k: 初筛候选数量
        final_k: 最终返回数量

    Returns:
        排序后的观察日记列表
    """
    from src.storage.connection import get_pool

    pool = await get_pool()
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    async with pool.acquire() as conn:
        # 混合检索 SQL — 向量相似度 + 全文匹配 加权排序
        rows = await conn.fetch("""
            WITH vector_results AS (
                SELECT id, content, username,
                       1 - (embedding <=> $3::vector) AS vec_score
                FROM user_observations
                WHERE username = $1
                ORDER BY embedding <=> $3::vector
                LIMIT $2
            ),
            text_results AS (
                SELECT id, content, username,
                       ts_rank(content_tsv, plainto_tsquery('simple', $4)) AS text_score
                FROM user_observations
                WHERE username = $1
                  AND content_tsv @@ plainto_tsquery('simple', $4)
                ORDER BY text_score DESC
                LIMIT $2
            ),
            merged AS (
                SELECT DISTINCT ON (id) id, content,
                       COALESCE(vec_score, 0) * 0.6 + COALESCE(text_score, 0) * 0.4 AS score
                FROM (
                    SELECT * FROM vector_results
                    UNION ALL
                    SELECT * FROM text_results
                ) combined
                ORDER BY id, score DESC
            )
            SELECT id, content, score
            FROM merged
            ORDER BY score DESC
            LIMIT $2
        """, username, top_k, embedding_str, query_text)

        candidates = [{"id": r["id"], "content": r["content"], "score": float(r["score"])} for r in rows]

    # Reranker 精排
    if candidates:
        reranked = await _rerank(query_text, candidates)
        return reranked[:final_k]

    return candidates[:final_k]


async def _rerank(query: str, candidates: list[dict]) -> list[dict]:
    """
    使用 cross-encoder reranker 对候选进行精排

    如果 reranker 模型不可用，退化为原始分数排序
    """
    try:
        from sentence_transformers import CrossEncoder

        model_name = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
        model = CrossEncoder(model_name)

        pairs = [(query, c["content"]) for c in candidates]
        scores = model.predict(pairs)

        # 将 reranker 分数合并
        for i, candidate in enumerate(candidates):
            candidate["rerank_score"] = float(scores[i])

        # 按 reranker 分数降序
        candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
        print(f"[reranker] Reranked {len(candidates)} candidates with {model_name}")

    except (ImportError, Exception) as e:
        print(f"[reranker] Fallback to original scores: {e}")

    return candidates


# ---------------------------------------------------------------------------
# 会话初始化时召回长期记忆
# ---------------------------------------------------------------------------

async def recall_long_term_memory(username: str, context: str) -> list[str]:
    """
    新会话开始时，根据用户上下文召回 Top-2 历史观察日记

    Args:
        username: 用户标识
        context: 当前会话上下文/第一条消息

    Returns:
        观察日记文本列表
    """
    embedding = await get_embedding(context)
    results = await hybrid_search_observations(
        username=username,
        query_text=context,
        query_embedding=embedding,
        top_k=10,
        final_k=2,
    )
    return [r["content"] for r in results]
