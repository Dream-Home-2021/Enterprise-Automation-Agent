"""
数据库查询工具 — 查看测试前后数据变化
用法:
  python test/db_query.py              # 查看所有表数据
  python test/db_query.py sessions     # 只查 sessions 表
  python test/db_query.py profiles     # 只查 user_profile 表
  python test/db_query.py prefs       # 只查 user_preferences 表
  python test/db_query.py redis        # 查 Redis 检查点
"""
import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("AGENT_DATABASE_URL", "postgresql+asyncpg://agent:agent@localhost:5433/agent_memory")
os.environ.setdefault("AGENT_REDIS_URL", "redis://localhost:6380/0")

import asyncpg
from agent.db.redis import get_redis


async def query_sessions():
    """查询 agent_sessions 表"""
    pool = await asyncpg.create_pool(
        os.environ["AGENT_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"),
        min_size=1, max_size=2
    )
    rows = await pool.fetch("SELECT * FROM agent_sessions ORDER BY updated_at DESC LIMIT 20")
    print("\n[SESSIONS] agent_sessions:")
    print("-" * 80)
    for r in rows:
        print(f"  id={r['id']}")
        print(f"  user_id={r['user_id']}  name={r['name']}  status={r['status']}")
        print(f"  message_count={r['message_count']}  created={r['created_at']}  updated={r['updated_at']}")
        print()
    if not rows:
        print("  (空表)")
    await pool.close()


async def query_profiles():
    """查询 agent_user_profile 表"""
    pool = await asyncpg.create_pool(
        os.environ["AGENT_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"),
        min_size=1, max_size=2
    )
    rows = await pool.fetch("SELECT * FROM agent_user_profile ORDER BY updated_at DESC LIMIT 10")
    print("\n[PROFILES] agent_user_profile:")
    print("-" * 80)
    for r in rows:
        print(f"  id={r['id']}  user_id={r['user_id']}  version={r['version']}")
        print(f"  profile={r['profile']}")
        print(f"  updated={r['updated_at']}")
        print()
    if not rows:
        print("  (空表)")
    await pool.close()


async def query_preferences():
    """查询 agent_user_preferences 表"""
    pool = await asyncpg.create_pool(
        os.environ["AGENT_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"),
        min_size=1, max_size=2
    )
    rows = await pool.fetch("SELECT * FROM agent_user_preferences ORDER BY updated_at DESC LIMIT 20")
    print("\n[PREFS] agent_user_preferences:")
    print("-" * 80)
    for r in rows:
        print(f"  id={r['id']}  user_id={r['user_id']}  key={r['key']}")
        print(f"  value={r['value']}  source={r['source']}  confidence={r['confidence']}")
        print(f"  updated={r['updated_at']}")
        print()
    if not rows:
        print("  (空表)")
    await pool.close()


async def query_summaries():
    """查询 agent_conversation_summaries 表"""
    pool = await asyncpg.create_pool(
        os.environ["AGENT_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"),
        min_size=1, max_size=2
    )
    rows = await pool.fetch("SELECT * FROM agent_conversation_summaries ORDER BY created_at DESC LIMIT 10")
    print("\n[SUMMARIES] agent_conversation_summaries:")
    print("-" * 80)
    for r in rows:
        print(f"  id={r['id']}  user_id={r['user_id']}  session_id={r['session_id']}")
        print(f"  summary={r['summary'][:80]}...")
        print(f"  tags={r['tags']}  message_count={r['message_count']}")
        print()
    if not rows:
        print("  (空表)")
    await pool.close()


async def query_redis():
    """查询 Redis 检查点"""
    redis = await get_redis()
    print("\n[REDIS] Redis 检查点:")
    print("-" * 80)

    # 搜索 checkpoint: 前缀的键
    cursor = 0
    keys = []
    while True:
        cursor, batch = await redis.scan(cursor, match="checkpoint:*", count=100)
        keys.extend(batch)
        if cursor == 0:
            break

    if not keys:
        print("  (无检查点)")
    else:
        for key in keys[:20]:
            key_str = key.decode() if isinstance(key, bytes) else key
            print(f"  {key_str}")
        if len(keys) > 20:
            print(f"  ... 共 {len(keys)} 个键")

    await redis.aclose()


async def query_all():
    await query_sessions()
    await query_profiles()
    await query_preferences()
    await query_summaries()
    await query_redis()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "sessions":
            asyncio.run(query_sessions())
        elif cmd in ("profiles", "profile"):
            asyncio.run(query_profiles())
        elif cmd in ("prefs", "preferences"):
            asyncio.run(query_preferences())
        elif cmd in ("summaries",):
            asyncio.run(query_summaries())
        elif cmd == "redis":
            asyncio.run(query_redis())
        else:
            print(f"未知命令: {cmd}")
            print("用法: python test/db_query.py [sessions|profiles|prefs|summaries|redis]")
    else:
        asyncio.run(query_all())
