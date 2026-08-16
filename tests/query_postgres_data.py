# -*- coding: utf-8 -*-
"""
PostgreSQL 长期记忆数据查询工具
查询 agent_memory 数据库中所有相关表的数据。

用法:
    # 查看所有表数据
    python test/query_postgres_data.py

    # 按表名查询
    python test/query_postgres_data.py sessions
    python test/query_postgres_data.py preferences
    python test/query_postgres_data.py profile
    python test/query_postgres_data.py summaries
    python test/query_postgres_data.py vectors

    # 按用户查询
    python test/query_postgres_data.py user 1
    python test/query_postgres_data.py user 999

    # 按会话查询
    python test/query_postgres_data.py session <session_id>

    # 查询向量索引信息
    python test/query_postgres_data.py indexes
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("AGENT_DATABASE_URL", "postgresql+asyncpg://agent:agent@localhost:5433/agent_memory")

import asyncpg


def _get_dsn():
    url = os.environ["AGENT_DATABASE_URL"]
    raw = url.replace("postgresql+asyncpg://", "postgresql://")
    return raw


def _pretty(data) -> str:
    """格式化输出 JSON-able 数据"""
    if isinstance(data, (dict, list)):
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return str(data)


async def query_sessions(user_id: int = None):
    """查询 agent_sessions 表"""
    pool = await asyncpg.create_pool(_get_dsn(), min_size=1, max_size=2)
    if user_id is not None:
        rows = await pool.fetch(
            "SELECT * FROM agent_sessions WHERE user_id = $1 ORDER BY updated_at DESC LIMIT 50",
            user_id,
        )
        print(f"\n[SESSIONS] agent_sessions  (user_id={user_id}, {len(rows)} 条):")
    else:
        rows = await pool.fetch(
            "SELECT * FROM agent_sessions ORDER BY updated_at DESC LIMIT 50"
        )
        print(f"\n[SESSIONS] agent_sessions  (全部, {len(rows)} 条):")
    print("-" * 80)
    for r in rows:
        print(f"  id            : {r['id']}")
        print(f"  user_id       : {r['user_id']}")
        print(f"  name          : {r['name']}")
        print(f"  status        : {r['status']}")
        print(f"  message_count : {r['message_count']}")
        print(f"  created_at    : {r['created_at']}")
        print(f"  updated_at    : {r['updated_at']}")
        print(f"  last_msg_at   : {r['last_message_at']}")
        print()
    if not rows:
        print("  (空表)")
    await pool.close()


async def query_preferences(user_id: int = None):
    """查询 agent_user_preferences 表"""
    pool = await asyncpg.create_pool(_get_dsn(), min_size=1, max_size=2)
    if user_id is not None:
        rows = await pool.fetch(
            "SELECT * FROM agent_user_preferences WHERE user_id = $1 ORDER BY updated_at DESC",
            user_id,
        )
        print(f"\n[PREFERENCES] agent_user_preferences  (user_id={user_id}, {len(rows)} 条):")
    else:
        rows = await pool.fetch(
            "SELECT * FROM agent_user_preferences ORDER BY updated_at DESC LIMIT 100"
        )
        print(f"\n[PREFERENCES] agent_user_preferences  (全部, {len(rows)} 条):")
    print("-" * 80)
    for r in rows:
        print(f"  id         : {r['id']}")
        print(f"  user_id    : {r['user_id']}")
        print(f"  key        : {r['key']}")
        print(f"  value      : {r['value']}")
        print(f"  source     : {r['source']}")
        print(f"  confidence : {r['confidence']}")
        print(f"  created_at : {r['created_at']}")
        print(f"  updated_at : {r['updated_at']}")
        print()
    if not rows:
        print("  (空表)")
    await pool.close()


async def query_profile(user_id: int = None):
    """查询 agent_user_profile 表"""
    pool = await asyncpg.create_pool(_get_dsn(), min_size=1, max_size=2)
    if user_id is not None:
        rows = await pool.fetch(
            "SELECT * FROM agent_user_profile WHERE user_id = $1", user_id
        )
        print(f"\n[PROFILE] agent_user_profile  (user_id={user_id}, {len(rows)} 条):")
    else:
        rows = await pool.fetch("SELECT * FROM agent_user_profile ORDER BY updated_at DESC")
        print(f"\n[PROFILE] agent_user_profile  (全部, {len(rows)} 条):")
    print("-" * 80)
    for r in rows:
        print(f"  id         : {r['id']}")
        print(f"  user_id    : {r['user_id']}")
        print(f"  version    : {r['version']}")
        print(f"  profile    : {_pretty(r['profile'])}")
        print(f"  updated_at : {r['updated_at']}")
        print()
    if not rows:
        print("  (空表)")
    await pool.close()


async def query_summaries(user_id: int = None, session_id: str = None):
    """查询 agent_conversation_summaries 表"""
    pool = await asyncpg.create_pool(_get_dsn(), min_size=1, max_size=2)
    if session_id:
        rows = await pool.fetch(
            "SELECT * FROM agent_conversation_summaries WHERE session_id = $1 ORDER BY created_at ASC",
            session_id,
        )
        print(f"\n[SUMMARIES] agent_conversation_summaries  (session_id={session_id}, {len(rows)} 条):")
    elif user_id is not None:
        rows = await pool.fetch(
            "SELECT * FROM agent_conversation_summaries WHERE user_id = $1 ORDER BY created_at DESC LIMIT 50",
            user_id,
        )
        print(f"\n[SUMMARIES] agent_conversation_summaries  (user_id={user_id}, {len(rows)} 条):")
    else:
        rows = await pool.fetch(
            "SELECT * FROM agent_conversation_summaries ORDER BY created_at DESC LIMIT 50"
        )
        print(f"\n[SUMMARIES] agent_conversation_summaries  (全部, {len(rows)} 条):")
    print("-" * 80)
    for r in rows:
        print(f"  id           : {r['id']}")
        print(f"  user_id      : {r['user_id']}")
        print(f"  session_id   : {r['session_id']}")
        print(f"  summary      : {r['summary'][:120]}")
        print(f"  tags         : {r['tags']}")
        print(f"  message_count: {r['message_count']}")
        print(f"  offsets      : [{r['start_offset']}, {r['end_offset']}]")
        print(f"  created_at   : {r['created_at']}")
        print()
    if not rows:
        print("  (空表)")
    await pool.close()


async def query_vectors(user_id: int = None, session_id: str = None):
    """查询 agent_memory_vectors 表"""
    pool = await asyncpg.create_pool(_get_dsn(), min_size=1, max_size=2)
    if session_id:
        rows = await pool.fetch(
            "SELECT id, user_id, session_id, content, metadata, created_at "
            "FROM agent_memory_vectors WHERE session_id = $1 ORDER BY created_at ASC",
            session_id,
        )
        print(f"\n[VECTORS] agent_memory_vectors  (session_id={session_id}, {len(rows)} 条):")
    elif user_id is not None:
        rows = await pool.fetch(
            "SELECT id, user_id, session_id, content, metadata, created_at "
            "FROM agent_memory_vectors WHERE user_id = $1 ORDER BY created_at DESC LIMIT 50",
            user_id,
        )
        print(f"\n[VECTORS] agent_memory_vectors  (user_id={user_id}, {len(rows)} 条):")
    else:
        rows = await pool.fetch(
            "SELECT id, user_id, session_id, content, metadata, created_at "
            "FROM agent_memory_vectors ORDER BY created_at DESC LIMIT 50"
        )
        print(f"\n[VECTORS] agent_memory_vectors  (全部, {len(rows)} 条):")
    print("-" * 80)
    for r in rows:
        print(f"  id         : {r['id']}")
        print(f"  user_id    : {r['user_id']}")
        print(f"  session_id : {r['session_id']}")
        print(f"  content    : {r['content'][:100]}")
        print(f"  metadata   : {_pretty(r['metadata'])}")
        print(f"  created_at : {r['created_at']}")
        print()
    if not rows:
        print("  (空表)")
    await pool.close()


async def query_session_detail(session_id: str):
    """查询指定会话的完整信息（session + summaries + vectors）"""
    pool = await asyncpg.create_pool(_get_dsn(), min_size=1, max_size=2)

    print(f"\n{'='*80}")
    print(f"[SESSION DETAIL] session_id = {session_id}")
    print(f"{'='*80}")

    # 1. session 基本信息
    row = await pool.fetchrow("SELECT * FROM agent_sessions WHERE id = $1", session_id)
    if row:
        print(f"\n  Session:")
        print(f"    user_id       : {row['user_id']}")
        print(f"    name          : {row['name']}")
        print(f"    status        : {row['status']}")
        print(f"    message_count : {row['message_count']}")
        print(f"    created_at    : {row['created_at']}")
        print(f"    updated_at    : {row['updated_at']}")
    else:
        print(f"\n  Session: (不存在)")

    # 2. 摘要
    rows = await pool.fetch(
        "SELECT * FROM agent_conversation_summaries WHERE session_id = $1 ORDER BY created_at ASC",
        session_id,
    )
    print(f"\n  Summaries ({len(rows)} 条):")
    for r in rows:
        print(f"    [{r['id']}] tags={r['tags']} | {r['summary'][:80]}")

    # 3. 向量
    rows = await pool.fetch(
        "SELECT id, content, metadata, created_at FROM agent_memory_vectors "
        "WHERE session_id = $1 ORDER BY created_at ASC",
        session_id,
    )
    print(f"\n  Vectors ({len(rows)} 条):")
    for r in rows:
        print(f"    [{r['id']}] {r['content'][:80]} | meta={_pretty(r['metadata'])}")

    await pool.close()


async def query_user_all(user_id: int):
    """查询指定用户的全部数据"""
    print(f"\n{'#'*80}")
    print(f"# 用户 {user_id} 的全部数据")
    print(f"{'#'*80}")
    await query_sessions(user_id)
    await query_preferences(user_id)
    await query_profile(user_id)
    await query_summaries(user_id)
    await query_vectors(user_id)


async def query_table_counts():
    """查询各表行数统计"""
    pool = await asyncpg.create_pool(_get_dsn(), min_size=1, max_size=2)
    tables = [
        "agent_sessions",
        "agent_user_preferences",
        "agent_user_profile",
        "agent_conversation_summaries",
        "agent_memory_vectors",
    ]
    print("\n[TABLE COUNTS]")
    print("-" * 40)
    for t in tables:
        row = await pool.fetchrow(f"SELECT COUNT(*) AS cnt FROM {t}")
        print(f"  {t:<40} {row['cnt']:>6} 行")
    await pool.close()


async def query_indexes():
    """查询 PGVector 索引信息"""
    pool = await asyncpg.create_pool(_get_dsn(), min_size=1, max_size=2)
    print("\n[INDEXES]")
    print("-" * 80)
    rows = await pool.fetch("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename LIKE 'agent_%'
        ORDER BY tablename, indexname
    """)
    for r in rows:
        print(f"  {r['indexname']}")
        print(f"    {r['indexdef']}")
        print()
    if not rows:
        print("  (无索引)")
    await pool.close()


async def query_all():
    """查询所有表"""
    await query_table_counts()
    await query_sessions()
    await query_preferences()
    await query_profile()
    await query_summaries()
    await query_vectors()


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        asyncio.run(query_all())
    elif args[0] == "sessions":
        uid = int(args[1]) if len(args) > 1 else None
        asyncio.run(query_sessions(uid))
    elif args[0] in ("preferences", "prefs"):
        uid = int(args[1]) if len(args) > 1 else None
        asyncio.run(query_preferences(uid))
    elif args[0] in ("profile",):
        uid = int(args[1]) if len(args) > 1 else None
        asyncio.run(query_profile(uid))
    elif args[0] in ("summaries",):
        if len(args) > 1 and not args[1].isdigit():
            asyncio.run(query_summaries(session_id=args[1]))
        else:
            uid = int(args[1]) if len(args) > 1 else None
            asyncio.run(query_summaries(uid))
    elif args[0] in ("vectors",):
        if len(args) > 1 and not args[1].isdigit():
            asyncio.run(query_vectors(session_id=args[1]))
        else:
            uid = int(args[1]) if len(args) > 1 else None
            asyncio.run(query_vectors(uid))
    elif args[0] == "user" and len(args) > 1:
        asyncio.run(query_user_all(int(args[1])))
    elif args[0] == "session" and len(args) > 1:
        asyncio.run(query_session_detail(args[1]))
    elif args[0] == "indexes":
        asyncio.run(query_indexes())
    elif args[0] == "counts":
        asyncio.run(query_table_counts())
    else:
        print(f"未知命令: {args[0]}")
        print(__doc__)
