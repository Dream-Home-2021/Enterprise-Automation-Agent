"""
Redis 连接工厂（单例），供 langgraph-checkpoint-redis 使用。
"""

import os
from redis import asyncio as aioredis
from utils.log import get_logger

logger = get_logger(__name__)

_redis_client: aioredis.Redis | None = None


def get_redis_url() -> str:
    """获取 Redis 连接 URL，优先环境变量，默认 localhost。"""
    return os.getenv("AGENT_REDIS_URL", "redis://localhost:6380/0")


def get_redis() -> aioredis.Redis:
    """获取 Redis 客户端（单例，懒初始化）。"""
    global _redis_client
    if _redis_client is None:
        url = get_redis_url()
        logger.info("Connecting to Redis: %s", url)
        _redis_client = aioredis.from_url(url, decode_responses=False)
    return _redis_client


async def close_redis():
    """关闭 Redis 连接。"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed")