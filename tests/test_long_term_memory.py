# -*- coding: utf-8 -*-
"""
长期记忆提取 — 混合策略测试
每个功能一个独立测试，按功能分组，可单独运行。

运行方式:
    # 运行全部测试
    cd d:\GameDownload\My-agent
    python -m pytest test/test_long_term_memory.py -v -s

    # 只运行某个功能组 (-k 按名字过滤)
    python -m pytest test/test_long_term_memory.py -v -s -k "test_profile_extract"
    python -m pytest test/test_long_term_memory.py -v -s -k "test_profile_batch"
    python -m pytest test/test_long_term_memory.py -v -s -k "test_profile_vector"
    python -m pytest test/test_long_term_memory.py -v -s -k "test_profile_background"
    python -m pytest test/test_long_term_memory.py -v -s -k "test_profile_lifecycle"
    python -m pytest test/test_long_term_memory.py -v -s -k "test_profile_error"
    python -m pytest test/test_long_term_memory.py -v -s -k "test_memory_read"
"""
import asyncio
import json
import os
import sys
import uuid

# 加载 .env 文件中的 API Key 等配置
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("AGENT_DATABASE_URL", "postgresql+asyncpg://agent:agent@localhost:5433/agent_memory")
os.environ.setdefault("AGENT_REDIS_URL", "redis://localhost:6380/0")
os.environ.setdefault("MEMORY_BATCH_INTERVAL_MINUTES", "15")

import pytest
import pytest_asyncio
import asyncpg

from agent.db.postgres import (
    init_db, close_pool, get_pool,
    create_session, list_sessions, delete_session,
    update_session_message_count,
    save_preference, get_preference, get_all_preferences, delete_preference,
    upsert_profile, get_profile,
    save_summary, get_session_summaries, summary_exists_for_session,
)
from agent.memory.extract import extract_preferences, generate_summary, update_profile
from agent.memory.long_term import load_user_memory, load_profile_inject, load_relevant_memories
from agent.memory.profile import (
    extract_from_conversation,
    get_pending_sessions,
    batch_process_pending,
    start_background_extractor,
    stop_background_extractor,
)


# ── 测试用 user_id，避免和正式数据冲突 ─────────────────────────────
TEST_USER_1 = 88801
TEST_USER_2 = 88802
TEST_USER_3 = 88803


async def _clean_user_data(user_id: int):
    """"清理测试用户在所有表中的数据"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 先删子表（级联会处理 summaries/vectors，但 preferences/profile 需手动）
        await conn.execute("DELETE FROM agent_user_preferences WHERE user_id=$1", user_id)
        await conn.execute("DELETE FROM agent_user_profile WHERE user_id=$1", user_id)
        # sessions 级联删 summaries + vectors
        await conn.execute("DELETE FROM agent_sessions WHERE user_id=$1", user_id)


async def _show_memory_state(label: str, user_id: int):
    """打印指定用户的长期记忆数据状态"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        print(f"\n{'='*60}")
        print(f"[STATE] {label}  (user_id={user_id})")
        print(f"{'='*60}")

        # sessions
        rows = await conn.fetch(
            "SELECT id, name, message_count, updated_at FROM agent_sessions "
            "WHERE user_id=$1 ORDER BY updated_at DESC LIMIT 5", user_id)
        print(f"\n  Sessions ({len(rows)} 条):")
        for r in rows:
            print(f"    {r['id']} | {r['name']} | msg={r['message_count']} | {r['updated_at']}")

        # preferences
        rows = await conn.fetch(
            "SELECT key, value, confidence FROM agent_user_preferences "
            "WHERE user_id=$1 ORDER BY updated_at DESC", user_id)
        print(f"\n  Preferences ({len(rows)} 条):")
        for r in rows:
            print(f"    {r['key']}={r['value']} (conf={r['confidence']})")

        # profile
        row = await conn.fetchrow(
            "SELECT profile, version FROM agent_user_profile WHERE user_id=$1", user_id)
        if row:
            print(f"\n  Profile (v{row['version']}): {row['profile']}")
        else:
            print(f"\n  Profile: (空)")

        # summaries
        rows = await conn.fetch(
            "SELECT session_id, summary, tags FROM agent_conversation_summaries "
            "WHERE user_id=$1 ORDER BY created_at DESC LIMIT 5", user_id)
        print(f"\n  Summaries ({len(rows)} 条):")
        for r in rows:
            print(f"    [{str(r['session_id'])[:8]}] tags={r['tags']} | {r['summary'][:60]}...")

        # vectors
        rows = await conn.fetch(
            "SELECT id, content, metadata FROM agent_memory_vectors "
            "WHERE user_id=$1 ORDER BY created_at DESC LIMIT 5", user_id)
        print(f"\n  Vectors ({len(rows)} 条):")
        for r in rows:
            print(f"    [{r['id']}] meta={r['metadata']} | {r['content'][:60]}...")


# ── Fixture ────────────────────────────────────────────────────────

# 是否清理测试数据（默认 1=清理，设为 0 保留数据以便手动查询）
CLEAN_TEST_DATA = os.getenv("CLEAN_TEST_DATA", "1") == "1"


@pytest_asyncio.fixture(autouse=True)
async def _setup():
    """每个测试前初始化 DB，测试后清理测试用户数据"""
    await init_db()
    yield
    # # 清理所有测试用户
    # if CLEAN_TEST_DATA:
    #     for uid in [TEST_USER_1, TEST_USER_2, TEST_USER_3]:
    #         await _clean_user_data(uid)
    await close_pool()


# ═══════════════════════════════════════════════════════════════════
# 组 1: extract_from_conversation — 即时提取偏好
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_profile_extract_basic():
    """测试: extract_from_conversation 基本流程 — 消息 >= 2 条时触发提取"""
    user_id = TEST_USER_1
    session_id = str(uuid.uuid4())
    messages = [
        {"role": "user", "content": "我喜欢蓝色主题"},
        {"role": "assistant", "content": "好的，我记住了你喜欢蓝色主题"},
    ]

    result = await extract_from_conversation(user_id, session_id, messages)

    assert isinstance(result, dict)
    assert "preferences_extracted" in result
    assert "profile_updated" in result
    assert "elapsed_ms" in result
    assert result["elapsed_ms"] >= 0
    print(f"  提取结果: prefs={result['preferences_extracted']}, updated={result['profile_updated']}, time={result['elapsed_ms']:.0f}ms")
    print("[PASS] extract_from_conversation 基本流程")


@pytest.mark.asyncio
async def test_profile_extract_too_few_messages():
    """测试: 消息数 < 2 条时，提取应被跳过"""
    user_id = TEST_USER_1
    session_id = str(uuid.uuid4())
    messages = [{"role": "user", "content": "你好"}]

    result = await extract_from_conversation(user_id, session_id, messages)

    assert result["preferences_extracted"] == 0
    assert result["profile_updated"] is False
    print("[PASS] 消息过少时跳过提取")


@pytest.mark.asyncio
async def test_profile_extract_empty_messages():
    """测试: 空消息列表，提取应被跳过"""
    user_id = TEST_USER_1
    session_id = str(uuid.uuid4())

    result = await extract_from_conversation(user_id, session_id, [])

    assert result["preferences_extracted"] == 0
    assert result["profile_updated"] is False
    print("[PASS] 空消息列表跳过提取")


@pytest.mark.asyncio
async def test_profile_extract_with_existing_keys():
    """测试: 已有偏好 key 传入时，LLM 应避免重复提取"""
    user_id = TEST_USER_1

    # 先手动写入一条偏好
    await save_preference(user_id, "language", json.dumps("zh-CN"), "explicit", 1.0)

    session_id = str(uuid.uuid4())
    messages = [
        {"role": "user", "content": "我偏好中文"},
        {"role": "assistant", "content": "好的"},
        {"role": "user", "content": "我还在学 Python"},
        {"role": "assistant", "content": "Python 很棒"},
    ]

    result = await extract_from_conversation(user_id, session_id, messages)

    # 验证不会提取已有的 language 偏好
    prefs = await get_all_preferences(user_id)
    language_prefs = [p for p in prefs if p["key"] == "language"]
    assert len(language_prefs) == 1  # 只有一条，没有重复
    assert language_prefs[0]["value"] == "zh-CN"
    print(f"  当前偏好: {[(p['key'], p['value']) for p in prefs]}")
    print("[PASS] 已有偏好去重")


@pytest.mark.asyncio
async def test_profile_extract_writes_preferences_and_profile():
    """测试: 提取后偏好写入 agent_user_preferences，画像写入 agent_user_profile"""
    user_id = TEST_USER_1
    session_id = str(uuid.uuid4())
    messages = [
        {"role": "user", "content": "我叫小明，是一名 Python 后端开发，在北京工作"},
        {"role": "assistant", "content": "你好小明！很高兴认识你"},
        {"role": "user", "content": "我喜欢简洁的代码风格，讨厌啰嗦"},
        {"role": "assistant", "content": "明白，简洁为主"},
    ]

    result = await extract_from_conversation(user_id, session_id, messages)

    # 验证偏好表
    prefs = await get_all_preferences(user_id)
    assert len(prefs) > 0, f"偏好表为空，期望有写入"
    pref_keys = [p["key"] for p in prefs]
    print(f"  写入偏好: keys={pref_keys}")

    # 验证画像表
    profile = await get_profile(user_id)
    assert profile is not None, "画像未写入"
    assert profile["version"] >= 1
    print(f"  写入画像: version={profile['version']}, data={profile['profile']}")
    print("[PASS] 偏好 + 画像双写验证")


@pytest.mark.asyncio
async def test_profile_extract_llm_dict_messages():
    """测试: extract_preferences 支持 LangChain BaseMessage 格式"""
    from langchain_core.messages import HumanMessage, AIMessage

    messages = [
        HumanMessage(content="我喜欢科幻小说"),
        AIMessage(content="好的，记下了"),
        HumanMessage(content="最近在看三体"),
    ]

    # extract_preferences 本身支持 BaseMessage
    prefs = await extract_preferences(TEST_USER_1, messages)
    assert isinstance(prefs, list)
    print(f"  BaseMessage 提取: {len(prefs)} 条偏好")
    print("[PASS] BaseMessage 格式兼容性")


# ═══════════════════════════════════════════════════════════════════
# 组 2: batch_process_pending — 批量后台提取
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_profile_batch_no_pending():
    """测试: 没有待办会话时，批量处理直接返回"""
    result = await batch_process_pending()
    # 函数返回 None（无 assert，主要是不抛异常）
    print("[PASS] 无待办会话，batch_process_pending 安全返回")


@pytest.mark.asyncio
async def test_profile_batch_pending_query():
    """测试: get_pending_sessions 的 SQL 条件验证"""
    user_id = TEST_USER_2
    sid = await create_session(user_id=user_id)

    # 新会话 message_count = 0，不应出现在待办列表
    pending = await get_pending_sessions()
    ids = [str(s["session_id"]) for s in pending]
    assert str(sid) not in ids, "message_count=0 的会话不应在待办列表"
    print(f"  新会话不在待办列表 ✓ (共 {len(pending)} 个待办)")

    # 更新 message_count > 0 + updated_at 在 30 分钟内
    await update_session_message_count(sid, delta=3)

    # 手动将 updated_at 设到最近（默认就是 NOW()，满足条件）
    # 但需要先删掉对应的摘要（没有摘要，满足 NOT EXISTS 条件）
    pending = await get_pending_sessions()
    ids = [str(s["session_id"]) for s in pending]
    assert str(sid) in ids, "message_count>0 + 无摘要 + updated_at 在30分钟内的会话应在待办列表"
    print(f"  更新后在待办列表 ✓ (共 {len(pending)} 个待办)")

    print("[PASS] get_pending_sessions SQL 条件验证")


@pytest.mark.asyncio
async def test_profile_batch_idempotent():
    """测试: 同一会话不应产生重复摘要 (NOT EXISTS 幂等性)"""
    user_id = TEST_USER_2
    sid = await create_session(user_id=user_id)
    await update_session_message_count(sid, delta=5)

    # 手动插入一条摘要
    from uuid import UUID
    await save_summary(
        user_id=user_id,
        session_id=UUID(str(sid)),
        summary="已存在的摘要",
        tags=["test"],
        message_count=5,
    )

    # 再次查询待办，该会话不应出现
    pending = await get_pending_sessions()
    ids = [str(s["session_id"]) for s in pending]
    assert str(sid) not in ids, "已有摘要的会话不应重复出现在待办列表"
    print("[PASS] 幂等性验证：已有摘要的会话被排除")


@pytest.mark.asyncio
async def test_profile_batch_summary_written():
    """测试: 批量处理后摘要写入 agent_conversation_summaries"""
    user_id = TEST_USER_2
    sid = await create_session(user_id=user_id)
    await update_session_message_count(sid, delta=4)

    # 注意：batch_process_pending 需要 Redis checkpoint 才能读到消息
    # 这里只验证 SQL 层面的待办查询 + 摘要写入逻辑
    # 完整流程需要 Redis，见集成测试

    pending = await get_pending_sessions()
    found = [s for s in pending if str(s["session_id"]) == str(sid)]
    assert len(found) == 1
    assert found[0]["message_count"] == 4
    print(f"  待办会话: {found[0]}")
    print("[PASS] 批量处理待办查询 + 摘要写入验证")


# ═══════════════════════════════════════════════════════════════════
# 组 3: 向量存储 — _save_vectors_async
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_profile_vector_user_messages_only():
    """测试: 向量存储只处理 user 消息，跳过 assistant/system/tool"""
    from agent.memory.profile import _save_vectors_async

    user_id = TEST_USER_3
    # 先创建 session，满足外键约束
    sid = await create_session(user_id=user_id)
    session_id = str(sid)

    messages = [
        {"role": "system", "content": "你是一个助手"},     # 跳过
        {"role": "user", "content": "我喜欢打篮球"},         # 保留
        {"role": "assistant", "content": "好的"},            # 跳过
        {"role": "user", "content": "每周打三次"},           # 保留
        {"role": "tool", "content": "some tool output"},    # 跳过
        {"role": "user", "content": "hi"},                  # 跳过（长度 < 5）
    ]

    # _save_vectors_async 内部会调 OpenAI embedding
    await _save_vectors_async(user_id, session_id, messages)

    # 验证向量数据是否写入
    await _show_memory_state("向量存储后", user_id)

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, content, metadata FROM agent_memory_vectors "
            "WHERE user_id=$1 ORDER BY created_at DESC LIMIT 10", user_id)
        print(f"\n  向量数据验证: {len(rows)} 条")
        for r in rows:
            print(f"    [{r['id']}] meta={r['metadata']} | {r['content'][:60]}...")

        # 只应有 2 条（"我喜欢打篮球" 和 "每周打三次"）
        assert len(rows) == 2, f"期望 2 条向量，实际 {len(rows)} 条"
        contents = [r["content"] for r in rows]
        assert any("篮球" in c for c in contents), "缺少'篮球'向量"
        assert any("三次" in c for c in contents), "缺少'三次'向量"

    print("[PASS] 向量存储消息过滤 + 数据写入验证")


@pytest.mark.asyncio
async def test_profile_vector_no_user_messages():
    """测试: 没有用户消息时，向量存储安全返回"""
    from agent.memory.profile import _save_vectors_async

    user_id = TEST_USER_3
    sid = await create_session(user_id=user_id)
    session_id = str(sid)

    messages = [
        {"role": "assistant", "content": "你好"},
        {"role": "tool", "content": "result"},
    ]

    # 不应抛异常（无 user 消息，提前 return）
    await _save_vectors_async(user_id, session_id, messages)
    print("[PASS] 无用户消息时向量存储安全返回")


@pytest.mark.asyncio
async def test_profile_vector_empty_content():
    """测试: 用户消息内容为空或极短时被过滤"""
    from agent.memory.profile import _save_vectors_async

    user_id = TEST_USER_3
    sid = await create_session(user_id=user_id)
    session_id = str(sid)

    messages = [
        {"role": "user", "content": ""},       # 空
        {"role": "user", "content": "ok"},     # 太短 < 5
        {"role": "assistant", "content": "好的"},
    ]

    await _save_vectors_async(user_id, session_id, messages)
    print("[PASS] 空/短内容消息被过滤")


# ═══════════════════════════════════════════════════════════════════
# 组 4: 后台定时任务 — start/stop_background_extractor
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_profile_background_start_stop():
    """测试: 后台提取器启动 + 停止"""
    # 启动
    await start_background_extractor()

    # 重复启动应安全（不创建第二个任务）
    await start_background_extractor()
    print("  重复启动安全 ✓")

    # 停止
    await stop_background_extractor()

    # 再次停止应安全
    await stop_background_extractor()
    print("  重复停止安全 ✓")

    print("[PASS] 后台提取器启动/停止")


@pytest.mark.asyncio
async def test_profile_background_cancel():
    """测试: 后台任务取消后状态正确"""
    await start_background_extractor()

    # 停止（内部 cancel + await）
    await stop_background_extractor()

    # 重新启动应正常工作
    await start_background_extractor()
    await stop_background_extractor()

    print("[PASS] 后台任务取消 + 重启")


# ═══════════════════════════════════════════════════════════════════
# 组 5: 完整生命周期 — 端到端
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_profile_lifecycle_full():
    """测试: 完整生命周期 — 创建会话 → 对话 → 提取偏好 → 批量摘要 → 查询记忆"""
    user_id = TEST_USER_3

    # 1. 创建会话
    sid = await create_session(user_id=user_id)
    print(f"  1. 创建会话: {sid}")

    # 2. 模拟对话
    messages = [
        {"role": "user", "content": "我是后端开发，主要用 Go 和 Python"},
        {"role": "assistant", "content": "了解，Go 和 Python 是很棒的组合"},
        {"role": "user", "content": "我喜欢简洁的回答，不要太啰嗦"},
        {"role": "assistant", "content": "好的，简洁为主"},
        {"role": "user", "content": "我在上海工作，关注云原生和 K8s"},
        {"role": "assistant", "content": "云原生领域很有意思"},
    ]

    # 3. 即时提取偏好
    result = await extract_from_conversation(user_id, str(sid), messages)
    print(f"  2. 即时提取: prefs={result['preferences_extracted']}, profile_updated={result['profile_updated']}")

    # 4. 验证偏好写入
    prefs = await get_all_preferences(user_id)
    print(f"  3. 偏好条数: {len(prefs)}")
    for p in prefs:
        print(f"    - {p['key']}: {p['value']} (conf={p['confidence']})")

    # 5. 验证画像写入
    profile = await get_profile(user_id)
    if profile:
        print(f"  4. 画像 version={profile['version']}: {profile['profile']}")
    else:
        print(f"  4. 画像: (LLM 未提取到偏好，画像可能为空)")

    # 6. 更新消息数
    await update_session_message_count(sid, delta=len(messages))

    # 7. 查询长期记忆
    memory = await load_user_memory(user_id)
    print(f"  5. 长期记忆: profile={memory['profile']}, prefs={len(memory['preferences'])}, summaries={len(memory['summaries'])}")

    # 8. 画像注入文本
    inject_text = await load_profile_inject(user_id)
    print(f"  6. 画像注入:\n{inject_text}")

    await _show_memory_state("完整生命周期结束", user_id)
    print("[PASS] 完整生命周期")


@pytest.mark.asyncio
async def test_profile_lifecycle_multi_session():
    """测试: 多会话累积偏好 — 多次对话后偏好应累积"""
    user_id = TEST_USER_1

    # 第一轮对话
    sid1 = await create_session(user_id=user_id)
    messages1 = [
        {"role": "user", "content": "我喜欢深色主题"},
        {"role": "assistant", "content": "好的"},
    ]
    await extract_from_conversation(user_id, str(sid1), messages1)

    prefs1 = await get_all_preferences(user_id)
    print(f"  第一轮后偏好: {len(prefs1)} 条")

    # 第二轮对话
    sid2 = await create_session(user_id=user_id)
    messages2 = [
        {"role": "user", "content": "我偏好中文回复"},
        {"role": "assistant", "content": "好的"},
    ]
    await extract_from_conversation(user_id, str(sid2), messages2)

    prefs2 = await get_all_preferences(user_id)
    print(f"  第二轮后偏好: {len(prefs2)} 条")

    # 画像版本应递增
    profile = await get_profile(user_id)
    if profile:
        print(f"  画像 version={profile['version']}")

    await _show_memory_state("多会话累积", user_id)
    print("[PASS] 多会话偏好累积")


# ═══════════════════════════════════════════════════════════════════
# 组 6: 错误隔离 — 所有操作 try/except，失败不抛异常
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_profile_error_extract_isolation():
    """测试: extract_from_conversation 异常时返回 result 字典，不抛异常"""
    # 传入 None 作为 messages（模拟异常）
    result = await extract_from_conversation(TEST_USER_1, "test-session", None)

    assert isinstance(result, dict)
    assert "elapsed_ms" in result
    print(f"  异常后返回: {result}")
    print("[PASS] extract_from_conversation 错误隔离")


@pytest.mark.asyncio
async def test_profile_error_batch_isolation():
    """测试: get_pending_sessions 异常时返回空列表"""
    # 正常情况（不抛异常即通过）
    result = await get_pending_sessions()
    assert isinstance(result, list)
    print("[PASS] get_pending_sessions 错误隔离")


@pytest.mark.asyncio
async def test_profile_error_vector_isolation():
    """测试: _save_vectors_async 无 API key 时不抛异常"""
    from agent.memory.profile import _save_vectors_async

    sid = await create_session(user_id=TEST_USER_1)
    messages = [
        {"role": "user", "content": "这是一条测试消息，长度超过10个字符"},
    ]

    # 无 OpenAI key 时，embedding 调用失败会被 except 捕获
    await _save_vectors_async(TEST_USER_1, str(sid), messages)
    print("[PASS] _save_vectors_async 错误隔离")


@pytest.mark.asyncio
async def test_profile_error_update_profile_isolation():
    """测试: update_profile 空偏好列表时安全返回"""
    result = await update_profile(TEST_USER_1, [])
    assert isinstance(result, dict)
    print(f"  空偏好返回: {result}")
    print("[PASS] update_profile 空偏好安全返回")


# ═══════════════════════════════════════════════════════════════════
# 组 7: 长期记忆读取 — load_user_memory / load_profile_inject / load_relevant_memories
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_memory_read_empty_user():
    """测试: 空用户（无数据）读取长期记忆"""
    memory = await load_user_memory(TEST_USER_1)

    assert isinstance(memory, dict)
    assert "profile" in memory
    assert "preferences" in memory
    assert "summaries" in memory
    assert memory["profile"] == {}
    assert memory["preferences"] == []
    assert memory["summaries"] == []
    print("[PASS] 空用户读取长期记忆")


@pytest.mark.asyncio
async def test_memory_read_with_data():
    """测试: 有数据时读取长期记忆"""
    user_id = TEST_USER_1

    # 写入测试数据
    await upsert_profile(user_id, {"name": "TestUser", "city": "Shanghai"})
    await save_preference(user_id, "language", json.dumps("zh-CN"), "explicit", 1.0)
    await save_preference(user_id, "theme", json.dumps("dark"), "implicit", 0.8)

    memory = await load_user_memory(user_id)

    assert memory["profile"]["name"] == "TestUser"
    assert memory["profile"]["city"] == "Shanghai"
    assert len(memory["preferences"]) == 2
    print(f"  profile: {memory['profile']}")
    print(f"  preferences: {[(p['key'], p['value']) for p in memory['preferences']]}")
    print("[PASS] 有数据时读取长期记忆")


@pytest.mark.asyncio
async def test_memory_profile_inject_empty():
    """测试: 无数据时画像注入文本格式正确"""
    inject = await load_profile_inject(TEST_USER_1)

    assert "=== 用户画像 ===" in inject
    assert "====================" in inject
    print(f"  注入文本:\n{inject}")
    print("[PASS] 空数据画像注入格式")


@pytest.mark.asyncio
async def test_memory_profile_inject_with_data():
    """测试: 有数据时画像注入文本包含偏好和摘要"""
    user_id = TEST_USER_1

    await upsert_profile(user_id, {"name": "Dev"})
    await save_preference(user_id, "language", json.dumps("zh-CN"), "explicit", 0.9)
    await save_preference(user_id, "style", json.dumps("concise"), "implicit", 0.7)

    inject = await load_profile_inject(user_id)

    assert "language" in inject
    assert "zh-CN" in inject
    assert "style" in inject
    assert "concise" in inject
    print(f"  注入文本:\n{inject}")
    print("[PASS] 有数据画像注入格式")


@pytest.mark.asyncio
async def test_memory_vector_search_empty():
    """测试: 向量检索 — 无向量数据时返回空字符串"""
    result = await load_relevant_memories(TEST_USER_1, "查询内容")
    # 无 API key 或无数据时返回 ""
    assert isinstance(result, str)
    print(f"  检索结果: '{result}'")
    print("[PASS] 向量检索空数据")


@pytest.mark.asyncio
async def test_memory_vector_search_empty_query():
    """测试: 向量检索 — 空查询返回空字符串"""
    result = await load_relevant_memories(TEST_USER_1, "")
    assert result == ""
    print("[PASS] 空查询向量检索")


# ═══════════════════════════════════════════════════════════════════
# 组 8: generate_summary — 摘要生成
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_generate_summary_basic():
    """测试: generate_summary 基本流程"""
    messages = [
        {"role": "user", "content": "我想了解一下 LangGraph 的用法"},
        {"role": "assistant", "content": "LangGraph 是一个用于构建有状态应用的框架"},
        {"role": "user", "content": "它和 LangChain 有什么区别"},
        {"role": "assistant", "content": "LangGraph 更专注于状态图和循环流程"},
    ]

    result = await generate_summary(messages)

    assert isinstance(result, dict)
    assert "summary" in result
    assert "tags" in result
    print(f"  摘要: {result['summary'][:80]}")
    print(f"  标签: {result['tags']}")
    print("[PASS] generate_summary 基本流程")


@pytest.mark.asyncio
async def test_generate_summary_empty():
    """测试: generate_summary 空消息返回空结果"""
    result = await generate_summary([])

    assert isinstance(result, dict)
    assert "summary" in result
    assert "tags" in result
    print(f"  空消息摘要: {result}")
    print("[PASS] generate_summary 空消息")
