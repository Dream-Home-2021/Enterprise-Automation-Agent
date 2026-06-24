"""
短期记忆 — AsyncRedisSaver 检查点封装。

提供 `make_checkpointer()` 和 `compile_with_checkpointer()` 工具函数，
让 Supervisor Graph 和 Chat Agent Graph 编译时传入 checkpointer。

注意：必须用 AsyncRedisSaver，因为 LangGraph 1.x 的 AsyncPregelLoop
调用的是 aget_tuple()，而同步的 RedisSaver 没有实现 aget_tuple。
"""

from langgraph.graph import StateGraph
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from agent.db.redis import get_redis_url
from utils.log import get_logger

logger = get_logger(__name__)


async def make_checkpointer() -> AsyncRedisSaver:
    """创建 AsyncRedisSaver 检查点实例并完成 setup。"""
    redis_url = get_redis_url()
    logger.info("Creating AsyncRedisSaver checkpointer: %s", redis_url)
    checkpointer = AsyncRedisSaver(redis_url=redis_url)
    await checkpointer.setup()
    return checkpointer


async def compile_with_checkpointer(builder: StateGraph, name: str = "agent") -> StateGraph:
    """
    编译 StateGraph 并注入 AsyncRedisSaver checkpointer。

    用法:
        graph = await compile_with_checkpointer(builder, name="supervisor")
    """
    checkpointer = await make_checkpointer()
    return builder.compile(
        name=name,
        checkpointer=checkpointer,
    )
