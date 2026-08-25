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
    checkpointer = await make_checkpointer()
    return builder.compile(
        name=name,
        checkpointer=checkpointer,
    )
