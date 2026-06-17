"""
PostgreSQL 数据库连接池管理

负责：
  - AsyncPG 连接池初始化/关闭
  - 表结构自动创建（users, observations, sessions）
  - 连接池单例获取
"""

import os
from typing import Optional

import asyncpg
from dotenv import load_dotenv

load_dotenv()

# 全局连接池单例
_pool: Optional[asyncpg.Pool] = None


async def init_db_pool() -> asyncpg.Pool:
    """
    初始化 AsyncPG 连接池
    """
    global _pool

    if _pool is not None:
        return _pool

    postgres_url = os.getenv("POSTGRES_URL", "")
    if not postgres_url:
        raise ValueError("POSTGRES_URL environment variable is not set.")

    # asyncpg 需要去除 sqlalchemy 前缀
    dsn = postgres_url.replace("postgresql+asyncpg://", "postgresql://")

    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=2,
        max_size=int(os.getenv("POSTGRES_POOL_SIZE", "10")),
    )

    # 初始化表结构
    await _create_tables(_pool)
    print("[db] Connection pool created and tables initialized.")

    return _pool


async def close_db_pool():
    """关闭连接池"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        print("[db] Connection pool closed.")


async def get_pool() -> asyncpg.Pool:
    """获取连接池单例"""
    global _pool
    if _pool is None:
        await init_db_pool()
    return _pool


# ---------------------------------------------------------------------------
# 表结构初始化
# ---------------------------------------------------------------------------

async def _create_tables(pool: asyncpg.Pool):
    """创建核心表结构"""
    async with pool.acquire() as conn:
        # 启用 pgvector 扩展
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        # 用户表
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username        VARCHAR(50) PRIMARY KEY,
                role            VARCHAR(20) NOT NULL DEFAULT 'visitor',
                politeness      FLOAT NOT NULL DEFAULT 50.0,
                trust           FLOAT NOT NULL DEFAULT 50.0,
                rationality     FLOAT NOT NULL DEFAULT 50.0,
                empathy         FLOAT NOT NULL DEFAULT 50.0,
                current_emotion VARCHAR(20) NOT NULL DEFAULT 'normal',
                last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)

        # 长期记忆观察日记表（带 PGVector 向量列）
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_observations (
                id          SERIAL PRIMARY KEY,
                username    VARCHAR(50) NOT NULL REFERENCES users(username),
                content     TEXT NOT NULL,
                embedding   vector(1536),
                session_id  VARCHAR(100),
                created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)

        # 为全文检索添加 TSVector 列
        await conn.execute("""
            ALTER TABLE user_observations
            ADD COLUMN IF NOT EXISTS content_tsv tsvector;
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_observations_tsv
            ON user_observations USING GIN (content_tsv);
        """)

        # 为向量检索创建 HNSW 索引
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_observations_embedding
            ON user_observations
            USING hnsw (embedding vector_cosine_ops);
        """)

        # 用户观察索引
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_observations_username
            ON user_observations (username, created_at DESC);
        """)

        # 初始化默认用户
        await conn.execute("""
            INSERT INTO users (username, role, politeness, trust, rationality, empathy)
            VALUES
                ('main', 'admin', 80, 80, 80, 80),
                ('guest', 'visitor', 50, 50, 50, 50)
            ON CONFLICT (username) DO NOTHING;
        """)
