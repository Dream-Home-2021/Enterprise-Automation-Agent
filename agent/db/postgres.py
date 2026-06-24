"""
PostgreSQL 连接池 + DDL（5 张表）+ 读写方法。

表清单：
  - agent_sessions              — 会话元数据
  - agent_user_preferences      — 非语义记忆：结构化偏好 / 事实
  - agent_conversation_summaries— 非语义记忆：对话摘要
  - agent_user_profile          — 用户画像（聚合结果）
  - agent_memory_vectors        — 语义记忆：向量存储
"""

import json
import os
from typing import Any
from uuid import UUID

import asyncpg

from utils.log import get_logger

logger = get_logger(__name__)

_pool: asyncpg.Pool | None = None

# ── DDL ──────────────────────────────────────────────────────────
# status  会话激活状态 active
# message_count 会话内消息总数
# created_at 会话创建时间
# updated_at 最后聊天时间
# user_id 当前用户
# id  uuid-会话标识
DDL_SESSIONS = """
CREATE TABLE IF NOT EXISTS agent_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         INTEGER NOT NULL DEFAULT 1,
    name            VARCHAR(200) NOT NULL DEFAULT '新会话',
    status          VARCHAR(20) NOT NULL DEFAULT 'active',
    message_count   INTEGER NOT NULL DEFAULT 0,  
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON agent_sessions(user_id, updated_at DESC);
"""

DDL_PREFERENCES = """
CREATE TABLE IF NOT EXISTS agent_user_preferences (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL DEFAULT 1,
    key         VARCHAR(200) NOT NULL,
    value       JSONB NOT NULL,
    source      VARCHAR(50) DEFAULT 'conversation',
    confidence  REAL DEFAULT 0.5,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, key)
);
"""

# 外键约束 SUMMARIES向量数据受agent_sessions(id)控制
# ON DELETE CASCADE：当 agent_sessions 里某行被删除时，SUMMARIES 行也会被自动删除
DDL_SUMMARIES = """
CREATE TABLE IF NOT EXISTS agent_conversation_summaries (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL DEFAULT 1,
    session_id      UUID NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    summary         TEXT NOT NULL,
    tags            TEXT[] DEFAULT '{}',
    message_count   INTEGER DEFAULT 0,
    start_offset    INTEGER DEFAULT 0,
    end_offset      INTEGER DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_summaries_user_time ON agent_conversation_summaries(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_summaries_session  ON agent_conversation_summaries(session_id);
"""

DDL_PROFILE = """
CREATE TABLE IF NOT EXISTS agent_user_profile (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL UNIQUE DEFAULT 1,
    profile     JSONB NOT NULL DEFAULT '{}',
    version     INTEGER NOT NULL DEFAULT 1,
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
"""
# 外键约束 vector向量数据受agent_sessions(id)控制
# ON DELETE CASCADE：当 agent_sessions 里某行被删除时，vectors 行也会被自动删除
# (B-Tree)索引
DDL_VECTORS = """
CREATE TABLE IF NOT EXISTS agent_memory_vectors (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL DEFAULT 1,
    session_id  UUID REFERENCES agent_sessions(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    embedding   vector(1024) NOT NULL,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vectors_user ON agent_memory_vectors(user_id);
"""
# 两种检索方式，公用同一个表
# (HNSW)索引
DDL_VECTORS_HNSW = """
CREATE INDEX IF NOT EXISTS idx_vectors_embedding_hnsw
ON agent_memory_vectors
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 200);
"""

ALL_DDLS = [DDL_SESSIONS, DDL_PREFERENCES, DDL_SUMMARIES, DDL_PROFILE, DDL_VECTORS, DDL_VECTORS_HNSW]


# ── 连接池 ────────────────────────────────────────────────────────


def get_database_url() -> str:
    """获取数据库 URL，优先环境变量，默认 localhost。"""
    return os.getenv("AGENT_DATABASE_URL", "postgresql+asyncpg://agent:agent@localhost:5433/agent_memory")


def _parse_dsn(url: str) -> dict:
    """从 asyncpg URL 中解析连接参数。"""
    raw = url.replace("postgresql+asyncpg://", "").replace("postgresql://", "")
    user_pass, rest = raw.split("@", 1)
    user, _, password = user_pass.partition(":")
    host_port, dbname = rest.split("/", 1)
    host, _, port = host_port.partition(":")
    return {
        "user": user,
        "password": password,
        "host": host,
        "port": int(port) if port else 5432,
        "database": dbname,
    }


async def get_pool() -> asyncpg.Pool:
    """获取连接池（单例，懒初始化）。"""
    global _pool
    if _pool is None:
        url = get_database_url()
        dsn = _parse_dsn(url)
        logger.info("Connecting to PostgreSQL: %s@%s:%s/%s", dsn["user"], dsn["host"], dsn["port"], dsn["database"])
        _pool = await asyncpg.create_pool(
            **dsn,
            min_size=2,
            max_size=int(os.getenv("AGENT_DB_POOL_SIZE", "10")),
        )
    return _pool


async def init_db():
    """执行 DDL 创建 / 迁移 5 张表。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        for ddl in ALL_DDLS:
            await conn.execute(ddl)
    logger.info("Database tables initialized (5/5)")


async def close_pool():
    """关闭连接池。"""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


# ── 会话 CRUD ────────────────────────────────────────────────────
""" user_id表示用户标识  UUID表示会话标识  目前系统里只有一个用户（user_id=1）"""
#   uuid=d3e8596f-da98-4567-913a-7a16f09b1147
#   user_id=1  name=新会话  status=active
#   message_count=3  created=2026-06-21 12:42:13.845427  updated=2026-06-21 12:42:13.854320

#   uuid=1e1dc709-cd2f-4848-85a3-46d907706a5f
#   user_id=1  name=新会话  status=active
#   message_count=3  created=2026-06-21 12:40:39.279223  updated=2026-06-21 12:40:39.289657

async def create_session(user_id: int = 1) -> UUID:
    """创建新会话，返回 session_id。"""
    # 获取 PostgreSQL 连接池
    pool = await get_pool()
    # 从池子借一个连接，用完自动归还
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO agent_sessions (user_id) VALUES ($1) RETURNING id",
            user_id,
        )
        # 取出返回的 UUID
        sid: UUID = row["id"]
        logger.info("Session created: %s (user_id=%s)", sid, user_id)
        return sid


async def list_sessions(user_id: int = 1, limit: int = 50) -> list[dict]:
    """列出用户的所有会话，按 updated_at 降序。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # updated_at DESC 降序排列
        # fetch 返回所有行
        rows = await conn.fetch(
            """SELECT id, name, status, message_count, created_at, updated_at, last_message_at
               FROM agent_sessions
               WHERE user_id = $1
               ORDER BY updated_at DESC
               LIMIT $2""",
            user_id, limit,
        )
        return [dict(r) for r in rows]


async def get_session(session_id: UUID) -> dict | None:
    """获取单个会话信息，有UUID找到对应会话"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # fetchrow返回第一行
        row = await conn.fetchrow(
            "SELECT * FROM agent_sessions WHERE id = $1", session_id,
        )
        return dict(row) if row else None


async def update_session_name(session_id: UUID, name: str):
    """更新会话名称。"""
    pool = await get_pool()
    # $1 和 $2 是 asyncpg 的参数占位符，对应后面传入的参数顺序 name， session_id
    async with pool.acquire() as conn:
        # 更新， execute 不返回数据
        await conn.execute(
            "UPDATE agent_sessions SET name = $1, updated_at = NOW() WHERE id = $2",
            name, session_id,
        )


async def update_session_message_count(session_id: UUID, delta: int = 1):
    """递增会话消息数。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE agent_sessions
               SET message_count = message_count + $1, updated_at = NOW(), last_message_at = NOW()
               WHERE id = $2""",
            delta, session_id,
        )


# ON DELETE CASCADE：当 agent_sessions 里某行被删除时，所有引用了这行 id 的 summaries 和 vectors 行也会被自动删除
async def delete_session(session_id: UUID):
    """删除会话（CASCADE 会级联删除 summaries 和 vectors）。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM agent_sessions WHERE id = $1", session_id)
    logger.info("Session deleted: %s", session_id)


# ── 偏好 / 事实 CRUD ─────────────────────────────────────────────
# 执行"有就更新，没有就插入"的逻辑时：PostgreSQL 特有的语法

# INSERT INTO 表 (列1, 列2, 值)
# VALUES (...)
# ON CONFLICT (唯一约束列)
# DO UPDATE SET 列2 = EXCLUDED.列2
# ---                ^^^^^^^^
# ---                指这次想插入的新值
# EXCLUDED 代表本次 INSERT 试图写入但触发冲突的那行数据。
# PS : 每个 user_id + key 组合只有一条记录，重复写入会覆盖旧值。比如用户先设 language=zh-CN，再设 language=en-US，最终只保留 en-US

#   id=1  user_id=999  key=language
#   value="zh-CN"  source=explicit  confidence=1.0
#   updated=2026-06-21 07:53:21.735324

async def save_preference(user_id: int, key: str, value: Any, source: str = "conversation", confidence: float = 0.5):
    """保存或更新用户偏好（UPSERT）。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # auto-serialize dict/list for ::jsonb cast
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        await conn.execute(
            """INSERT INTO agent_user_preferences (user_id, key, value, source, confidence)
               VALUES ($1, $2, $3::jsonb, $4, $5)
               ON CONFLICT (user_id, key)
               DO UPDATE SET value = EXCLUDED.value, source = EXCLUDED.source,
                             confidence = EXCLUDED.confidence, updated_at = NOW()""",
            user_id, key, value, source, confidence,
        )


async def get_preference(user_id: int, key: str) -> Any | None:
    """获取某个偏好值。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value FROM agent_user_preferences WHERE user_id = $1 AND key = $2",
            user_id, key,
        )
        return row["value"] if row else None


async def get_all_preferences(user_id: int) -> list[dict]:
    """获取用户所有偏好。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT key, value, confidence, updated_at FROM agent_user_preferences WHERE user_id = $1 ORDER BY updated_at DESC",
            user_id,
        )
        return [{"key": r["key"], "value": r["value"], "confidence": r["confidence"], "updated_at": r["updated_at"].isoformat()} for r in rows]


async def delete_preference(user_id: int, key: str):
    """删除用户某个偏好。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM agent_user_preferences WHERE user_id = $1 AND key = $2",
            user_id, key,
        )


# ── 摘要 CRUD ─────────────────────────────────────────────────────


async def save_summary(user_id: int, session_id: UUID, summary: str, tags: list[str] | None = None,
                       message_count: int = 0, start_offset: int = 0, end_offset: int = 0):
    """保存对话摘要。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO agent_conversation_summaries
               (user_id, session_id, summary, tags, message_count, start_offset, end_offset)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            user_id, session_id, summary, tags or [], message_count, start_offset, end_offset,
        )


async def get_recent_summaries(user_id: int, limit: int = 5) -> list[dict]:
    """获取最近的对话摘要（跨会话）。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT summary, tags, message_count, created_at
               FROM agent_conversation_summaries
               WHERE user_id = $1
               ORDER BY created_at DESC
               LIMIT $2""",
            user_id, limit,
        )
        return [dict(r) for r in rows]


async def get_session_summaries(session_id: UUID) -> list[dict]:
    """获取某个会话的所有摘要。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM agent_conversation_summaries WHERE session_id = $1 ORDER BY created_at ASC",
            session_id,
        )
        return [dict(r) for r in rows]


async def summary_exists_for_session(session_id: UUID) -> bool:
    """检查会话是否已有摘要（幂等性校验）。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM agent_conversation_summaries WHERE session_id = $1 LIMIT 1",
            session_id,
        )
        return row is not None


# ── 画像 CRUD ─────────────────────────────────────────────────────
#   id=1  user_id=999  version=4
#   profile={"name": "TestUser", "role": "superadmin", "interests": ["LOL"]}
#   updated=2026-06-22 00:54:54.768119

async def upsert_profile(user_id: int, profile_data: dict, version: int | None = None):
    """更新用户画像。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # auto-serialize dict for ::jsonb cast
        if isinstance(profile_data, dict):
            profile_data = json.dumps(profile_data, ensure_ascii=False)
        if version is not None:
            await conn.execute(
                """INSERT INTO agent_user_profile (user_id, profile, version)
                   VALUES ($1, $2::jsonb, $3)
                   ON CONFLICT (user_id)
                   DO UPDATE SET profile = EXCLUDED.profile, version = EXCLUDED.version, updated_at = NOW()""",
                user_id, profile_data, version,
            )
        else:
            await conn.execute(
                """INSERT INTO agent_user_profile (user_id, profile)
                   VALUES ($1, $2::jsonb)
                   ON CONFLICT (user_id)
                   DO UPDATE SET profile = EXCLUDED.profile, version = agent_user_profile.version + 1, updated_at = NOW()""",
                user_id, profile_data,
            )


async def get_profile(user_id: int) -> dict | None:
    """获取用户画像。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT profile, version, updated_at FROM agent_user_profile WHERE user_id = $1",
            user_id,
        )
        if row:
            return {
                "profile": row["profile"],
                "version": row["version"],
                "updated_at": row["updated_at"].isoformat(),
            }
        return None


# ── 向量存储 ──────────────────────────────────────────────────────
# 长期记忆
# ├── Profile Store（语义）
# │   └── PostgreSQL
# │
# └── Vector Store（情景） --向量

async def save_memory_vector(user_id: int, session_id: UUID, content: str,
                             embedding: list[float], metadata: dict | None = None):
    """保存记忆向量。"""
    pool = await get_pool()
    # pgvector 需要字符串格式: "[1.0,2.0,...]"
    emb_str = "[" + ",".join(str(v) for v in embedding) + "]"
    meta_str = json.dumps(metadata or {})
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO agent_memory_vectors (user_id, session_id, content, embedding, metadata)
               VALUES ($1, $2, $3, $4::vector, $5::jsonb)""",
            user_id, session_id, content, emb_str, meta_str,
        )


async def search_memory_vectors(user_id: int, query_embedding: list[float], top_k: int = 5) -> list[dict]:
    """语义检索：余弦相似度搜索。"""
    # pgvector 需要字符串格式: "[1.0,2.0,...]"
    emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT content, metadata, 1 - (embedding <=> $1::vector) AS score, created_at
               FROM agent_memory_vectors
               WHERE user_id = $2
               ORDER BY embedding <=> $1::vector
               LIMIT $3""",
            emb_str, user_id, top_k,
        )
        return [dict(r) for r in rows]