"""
异步记忆浓缩管道 (Async Pipeline)

核心规则：
  - 禁止在同步流式对话中写入长期记忆
  - 会话闲置 5 分钟无输入时异步触发
  - 调用轻量大模型压缩生成 ~100 字《用户客观行为观察日记》
  - 向量化后追加写入 user_observations 表

时间消气机制：
  - 每次会话装载时比对时间差
  - 间隔超 24 小时 → 评分自动向初始均值回弹 10%
"""

import os
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# 闲置阈值（秒）
IDLE_THRESHOLD = int(os.getenv("IDLE_THRESHOLD_MINUTES", "5")) * 60

# 消气回弹周期
DECAY_HOURS = 24
DECAY_RATE = 0.10  # 10% 向初始均值回弹


# ---------------------------------------------------------------------------
# 异步浓缩管道
# ---------------------------------------------------------------------------

OBSERVATION_PROMPT = """请根据以下对话记录，生成一段约 100 字的客观行为观察日记。

要求：
- 客观描述用户的行为模式、语气变化、请求类型
- 关注用户的情绪表达、礼貌程度、理性/非理性倾向
- 不要评判对错，只记录事实
- 语言简洁、专业

对话记录：
{messages}

请仅输出观察日记正文（约 100 字）："""


async def trigger_memory_consolidation(
    username: str,
    messages: list[dict],
    session_id: str = "",
):
    """
    触发异步记忆浓缩 — 在会话闲置后调用

    Args:
        username: 用户标识
        messages: 该 Session 的消息列表
        session_id: 会话 ID
    """
    if not messages:
        return

    try:
        # 1. 调用轻量大模型生成观察日记
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            temperature=0.3,
        )

        # 格式化消息
        msg_text = "\n".join(
            f"[{m.get('role', '?')}] {m.get('content', '')}"
            for m in messages[-20:]  # 取最近 20 条
        )

        prompt = OBSERVATION_PROMPT.format(messages=msg_text)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        observation_text = response.content.strip()

        print(f"[memory] Generated observation for {username}: {observation_text[:50]}...")

        # 2. 向量化
        from src.storage.vector_store import get_embedding, insert_observation

        embedding = await get_embedding(observation_text)

        # 3. 写入数据库
        obs_id = await insert_observation(
            username=username,
            content=observation_text,
            embedding=embedding,
            session_id=session_id,
        )

        print(f"[memory] Observation #{obs_id} saved for {username}.")

    except Exception as e:
        print(f"[memory] Consolidation failed for {username}: {e}")


# ---------------------------------------------------------------------------
# 闲置检测调度器
# ---------------------------------------------------------------------------

class IdleScheduler:
    """
    会话闲置检测器

    跟踪每个 session 的最后活跃时间，
    超阈值后异步触发记忆浓缩。
    """

    def __init__(self):
        self._last_active: dict[str, datetime] = {}
        self._pending_messages: dict[str, list[dict]] = {}
        self._scheduled: set[str] = set()

    def update_activity(self, session_id: str, messages: list[dict]):
        """更新会话活跃时间"""
        self._last_active[session_id] = datetime.now(timezone.utc)
        self._pending_messages[session_id] = messages

    async def check_and_consolidate(self, session_id: str):
        """检查是否闲置并触发浓缩"""
        if session_id in self._scheduled:
            return  # 已调度，跳过

        last_active = self._last_active.get(session_id)
        if not last_active:
            return

        idle_seconds = (datetime.now(timezone.utc) - last_active).total_seconds()

        if idle_seconds >= IDLE_THRESHOLD:
            self._scheduled.add(session_id)
            messages = self._pending_messages.get(session_id, [])
            username = session_id.split("_")[0] if "_" in session_id else "main"

            # 异步触发，不阻塞主流程
            asyncio.create_task(
                trigger_memory_consolidation(username, messages, session_id)
            )
            print(f"[idle] Session {session_id} idle for {idle_seconds:.0f}s, consolidation triggered.")


# 全局调度器实例
idle_scheduler = IdleScheduler()


# ---------------------------------------------------------------------------
# 时间消气机制 (Time-based Decay)
# ---------------------------------------------------------------------------

async def apply_time_decay(username: str) -> dict:
    """
    时间消气 — 会话装载时比对时间差

    若间隔超 24 小时，量化评分向初始均值回弹 10%

    Returns:
        更新后的 metrics
    """
    from src.storage.connection import get_pool
    from src.agents.supervisor import USER_PROFILES

    pool = await get_pool()
    profile = USER_PROFILES.get(username, USER_PROFILES["guest"])
    initial = profile["initial_metrics"]

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT politeness, trust, rationality, empathy, last_updated_at
            FROM users
            WHERE username = $1
        """, username)

        if not row:
            return initial

        last_updated = row["last_updated_at"]
        now = datetime.now(timezone.utc)

        # 兼容 naive datetime
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=timezone.utc)

        hours_passed = (now - last_updated).total_seconds() / 3600

        if hours_passed < DECAY_HOURS:
            # 未超阈值，返回当前值
            return {
                "politeness": float(row["politeness"]),
                "trust": float(row["trust"]),
                "rationality": float(row["rationality"]),
                "empathy": float(row["empathy"]),
            }

        # 超过 24 小时，向初始均值回弹 10%
        current = {
            "politeness": float(row["politeness"]),
            "trust": float(row["trust"]),
            "rationality": float(row["rationality"]),
            "empathy": float(row["empathy"]),
        }

        decayed = {}
        for key in current:
            initial_val = initial[key]
            current_val = current[key]
            # 向初始值方向移动 10%
            decayed[key] = current_val + (initial_val - current_val) * DECAY_RATE
            decayed[key] = round(max(0, min(100, decayed[key])), 1)

        # 更新数据库
        await conn.execute("""
            UPDATE users
            SET politeness = $1, trust = $2, rationality = $3, empathy = $4,
                last_updated_at = NOW()
            WHERE username = $5
        """, decayed["politeness"], decayed["trust"],
            decayed["rationality"], decayed["empathy"], username)

        print(f"[decay] {username}: {hours_passed:.1f}h passed, scores decayed 10% toward initial.")

        return decayed


async def persist_metrics(username: str, metrics: dict, emotion: str):
    """持久化当前评分和情绪到用户表"""
    from src.storage.connection import get_pool

    pool = await get_pool()

    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users
            SET politeness = $1, trust = $2, rationality = $3, empathy = $4,
                current_emotion = $5, last_updated_at = NOW()
            WHERE username = $6
        """, metrics.get("politeness", 50), metrics.get("trust", 50),
            metrics.get("rationality", 50), metrics.get("empathy", 50),
            emotion, username)
