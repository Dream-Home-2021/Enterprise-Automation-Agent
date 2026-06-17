"""
PostgresSaver — 会话级短期状态快照中心

使用 LangGraph 官方 AsyncPostgresSaver 实现 Thread-level Checkpoint，
支持高并发会话线程安全、状态断点恢复与 Time Travel 回滚调试。
"""

import os
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver


# ---------------------------------------------------------------------------
# Checkpointer 工厂
# ---------------------------------------------------------------------------

async def get_checkpointer():
    """
    获取 Checkpointer 实例

    优先使用 AsyncPostgresSaver（生产），
    降级到 MemorySaver（开发/测试）。
    """
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from src.storage.connection import get_pool

        pool = await get_pool()
        checkpointer = AsyncPostgresSaver(conn=pool)
        print("[checkpointer] Using AsyncPostgresSaver (production mode).")
        return checkpointer

    except (ImportError, Exception) as e:
        print(f"[checkpointer] Falling back to MemorySaver: {e}")
        return MemorySaver()


async def setup_checkpointer_tables():
    """
    初始化 Checkpointer 所需的 LangGraph 内部表

    AsyncPostgresSaver 会自动创建以下表：
      - checkpoints
      - checkpoint_writes
      - checkpoint_blobs
    """
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from src.storage.connection import get_pool

        pool = await get_pool()
        checkpointer = AsyncPostgresSaver(conn=pool)
        await checkpointer.setup()
        print("[checkpointer] LangGraph checkpoint tables created.")

    except (ImportError, Exception) as e:
        print(f"[checkpointer] Setup skipped (MemorySaver mode): {e}")
