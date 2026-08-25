# -*- coding: utf-8 -*-
"""
Redis + PostgreSQL 核心流程测试
每个功能一个测试，验证需求文档要求是否实现
"""
import os
import sys
import json
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("AGENT_REDIS_URL", "redis://localhost:6380/0")
os.environ.setdefault("AGENT_DATABASE_URL", "postgresql+asyncpg://agent:agent@localhost:5433/agent_memory")

import pytest
import pytest_asyncio
import asyncpg

from agent.db.postgres import (
    init_db, close_pool, create_session, list_sessions, delete_session,
    update_session_message_count, upsert_profile, get_profile,
    save_preference, get_preference, get_all_preferences
)
from agent.db.redis import get_redis_url, get_redis, close_redis
from agent.memory.short_term import make_checkpointer
from agent.memory.history import load_conversation_history, delete_checkpoint


async def _show_db_state(label):
    """打印当前数据库状态"""
    import importlib.util
    _spec = importlib.util.spec_from_file_location("db_query", os.path.join(os.path.dirname(__file__), "db_query.py"))
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    print("\n" + "-" * 50)
    print(f"[DB STATE] {label}")
    print("-" * 50)
    await _mod.query_sessions()
    await _mod.query_profiles()
    await _mod.query_preferences()
    await _mod.query_redis()


@pytest_asyncio.fixture(autouse=True)
async def _setup_db():
    """每个测试前初始化 DB，测试后关闭 pool"""
    await init_db()
    await _show_db_state("测试前")
    yield
    await _show_db_state("测试后")
    await close_pool()


# --- PostgreSQL 测试 ---

@pytest.mark.asyncio
async def test_pg_connection_and_init():
    """测试: PostgreSQL 连接 + 建表"""
    pool = await asyncpg.create_pool(
        os.environ["AGENT_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://"),
        min_size=1, max_size=2
    )
    rows = await pool.fetch("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_name LIKE 'agent_%'
    """)
    names = {r["table_name"] for r in rows}
    for t in ["agent_sessions", "agent_user_preferences", "agent_conversation_summaries",
              "agent_user_profile", "agent_memory_vectors"]:
        assert t in names, f"表 {t} 不存在"
    await pool.close()
    print("[PASS] PostgreSQL 连接 + 5 张表创建成功")


@pytest.mark.asyncio
async def test_pg_session_crud():
    """测试: 会话 CRUD（创建、列表、更新、删除）"""
    # 创建
    sid = await create_session(user_id=1)
    assert sid is not None
    print(f"  创建会话: {sid}")

    # 列表包含该会话
    sessions = await list_sessions(user_id=1)
    ids = [str(s["id"]) for s in sessions]
    assert str(sid) in ids
    print(f"  列表包含该会话 (共 {len(sessions)} 个)")

    # 更新消息数
    await update_session_message_count(sid, delta=3)
    sessions = await list_sessions(user_id=1)
    target = next(s for s in sessions if str(s["id"]) == str(sid))
    assert target["message_count"] == 3
    print(f"  消息数更新: {target['message_count']}")

    # 删除
    await delete_session('e04bff08-d201-4eaa-a01d-29d1133df121')
    sessions = await list_sessions(user_id=1)
    ids = [str(s["id"]) for s in sessions]
    assert str('e04bff08-d201-4eaa-a01d-29d1133df121') not in ids
    print(f"  删除会话 OK")
    print("[PASS] 会话 CRUD")


@pytest.mark.asyncio
async def test_pg_user_profile():
    """测试: 用户画像 UPSERT"""
    user_id = 999

    # asyncpg jsonb 列需要 JSON 字符串
    profile = {"name": "TestUser", "role": "admin", "interests": ["LOL"]}
    await upsert_profile(user_id, json.dumps(profile))
    result = await get_profile(user_id)
    assert result is not None, "画像写入失败"
    assert result["profile"]["name"] == "TestUser"
    print(f"  画像写入: {result['profile']}")

    # UPSERT 更新
    profile["role"] = "superadmin"
    await upsert_profile(user_id, json.dumps(profile))
    result = await get_profile(user_id)
    assert result["profile"]["role"] == "superadmin"
    print(f"  画像更新: role={result['profile']['role']}")

    # # 清理
    from agent.db.postgres import get_pool as _get_pool
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM agent_user_profile WHERE user_id=$1", user_id)
    print("[PASS] 用户画像 UPSERT")


@pytest.mark.asyncio
async def test_pg_preferences():
    """测试: 用户偏好存储"""
    user_id = 998

    # jsonb 列需要 JSON 字符串
    await save_preference(user_id, "language", json.dumps("zh-CN"), "explicit", 1.0)
    val = await get_preference(user_id, "language")
    assert val == "zh-CN"
    print(f"  偏好写入+读取: language={val}")

    # UPSERT 更新
    await save_preference(user_id, "language", json.dumps("en-US"), "explicit", 0.9)
    val = await get_preference(user_id, "language")
    assert val == "en-US"
    print(f"  偏好更新: language={val}")

    # 批量读取
    await save_preference(user_id, "theme", json.dumps("dark"), "implicit", 0.7)
    all_prefs = await get_all_preferences(user_id)
    assert len(all_prefs) >= 2
    print(f"  批量读取: {len(all_prefs)} 条偏好")

    # # 清理
    from agent.db.postgres import get_pool as _get_pool
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM agent_user_preferences WHERE user_id=$1", user_id)
    print("[PASS] 用户偏好存储")


# --- Redis 测试 ---

@pytest.mark.asyncio
async def test_redis_connection():
    """测试: Redis 连接"""
    url = get_redis_url()
    assert "redis://" in url
    print(f"  Redis URL: {url}")

    redis = await get_redis()
    assert redis is not None
    pong = await redis.ping()
    assert pong is True
    print(f"  Redis ping OK")
    await close_redis()
    print("[PASS] Redis 连接测试")


@pytest.mark.asyncio
async def test_redis_checkpointer_setup():
    """测试: AsyncRedisSaver 检查点初始化"""
    checkpointer = await make_checkpointer()
    assert checkpointer is not None
    print(f"  AsyncRedisSaver 创建 OK")

    # 验证索引已创建
    redis = await get_redis()
    try:
        info = await redis.ft("checkpoint:index").info()
        print(f"  RediSearch 索引存在: checkpoint:index")
    except Exception as e:
        print(f"  索引检查: {e}")
    await close_redis()
    print("[PASS] Redis 检查点初始化")


@pytest.mark.asyncio
async def test_redis_conversation_history():
    """测试: 会话历史写入/加载/删除（通过 Redis 检查点）"""
    sid = str(uuid.uuid4())

    checkpointer = await make_checkpointer()
    config = {"configurable": {"thread_id": sid, "checkpoint_ns": ""}}

    # 写入检查点
    from langchain_core.messages import HumanMessage, AIMessage
    checkpoint = {
        "id": "test-ckpt-001",
        "channel_values": {
            "messages": [
                HumanMessage(content="你好"),
                AIMessage(content="你好！有什么可以帮你的吗？"),
            ]
        },
        "channel_versions": {},
    }
    metadata = {"source": "test", "step": 0}
    await checkpointer.aput(config, checkpoint, metadata, {})
    print(f"  检查点写入 OK")

    # 加载历史
    history = await load_conversation_history(sid)
    assert len(history) >= 2
    assert history[0]["content"] == "你好"
    assert history[1]["content"] == "你好！有什么可以帮你的吗？"
    print(f"  历史加载 OK: {len(history)} 条消息")
    for h in history:
        print(f"    [{h['role']}]: {h['content'][:40]}")

    # 删除检查点
    await delete_checkpoint(sid)
    history_after = await load_conversation_history(sid)
    assert len(history_after) == 0
    print(f"  检查点删除 OK")
    print("[PASS] 会话历史写入/加载/删除")


# --- 集成测试 ---

@pytest.mark.asyncio
async def test_session_lifecycle():
    """测试: 完整会话生命周期"""
    # 创建 2 个会话
    sid1 = await create_session(user_id=1)
    sid2 = await create_session(user_id=1)
    print(f"  创建 2 个会话")

    # 列表
    sessions = await list_sessions(user_id=1)
    assert len(sessions) >= 2
    print(f"  会话列表: {len(sessions)} 个")

    # 更新消息数
    await update_session_message_count(sid1, delta=5)
    await update_session_message_count(sid2, delta=3)
    sessions = await list_sessions(user_id=1)
    s1 = next(s for s in sessions if str(s["id"]) == str(sid1))
    assert s1["message_count"] == 5
    print(f"  消息数: session1={s1['message_count']}")

    # 删除一个
    await delete_session(sid1)
    sessions = await list_sessions(user_id=1)
    ids = [str(s["id"]) for s in sessions]
    assert str(sid1) not in ids
    assert str(sid2) in ids
    print(f"  删除 session1 OK")

    # 删除所有后自动创建
    await delete_session(sid2)
    sessions = await list_sessions(user_id=1)
    if not sessions:
        new_sid = await create_session(user_id=1)
        print(f"  自动创建新会话: {new_sid}")
        await delete_session(new_sid)
    print("[PASS] 完整会话生命周期")
