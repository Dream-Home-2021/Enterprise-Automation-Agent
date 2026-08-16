-- Agent Memory System — 数据库初始化脚本
-- 在容器首次启动时由 PostgreSQL 自动执行

-- 1. 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 会话元数据表
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


-- 3. 非语义记忆：结构化偏好 / 事实
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

-- 4. 非语义记忆：对话摘要
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

-- 5. 用户画像（聚合结果）
CREATE TABLE IF NOT EXISTS agent_user_profile (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL UNIQUE DEFAULT 1,
    profile     JSONB NOT NULL DEFAULT '{}',
    version     INTEGER NOT NULL DEFAULT 1,
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 6. 语义记忆：向量存储
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
-- HNSW index for vector similarity search performance
CREATE INDEX IF NOT EXISTS idx_vectors_embedding_hnsw
ON agent_memory_vectors
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 200);
