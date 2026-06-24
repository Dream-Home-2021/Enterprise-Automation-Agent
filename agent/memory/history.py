"""
对话历史加载器 — 从 Redis 检查点恢复会话消息。

使用 AsyncRedisSaver 的 `alist()` 读取指定 thread_id 的检查点状态，
提取 messages 列表供前端恢复 UI 显示。

session_id
    ↓
构建 LangGraph config（thread_id = session_id）
    ↓
获取最新检查点
    ↓
提取 messages
    ↓
过滤 + 转换格式
    ↓
返回前端可用的消息列表

"""

from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langchain_core.messages import BaseMessage

from agent.db.redis import get_redis_url
from utils.log import get_logger

logger = get_logger(__name__)

_checkpointer: AsyncRedisSaver | None = None


async def _get_checkpointer() -> AsyncRedisSaver:
    """获取 AsyncRedisSaver 实例（缓存）。"""
    global _checkpointer
    if _checkpointer is None:
        redis_url = get_redis_url()
        _checkpointer = AsyncRedisSaver(redis_url=redis_url)
        await _checkpointer.setup()
    return _checkpointer


async def load_conversation_history(session_id: str) -> list[dict]:
    """
    从 Redis 检查点恢复指定会话的消息历史。

    Args:
        session_id: 会话 UUID，对应 LangGraph 的 thread_id

    Returns:
        list[dict]: [{"role": "user"/"assistant", "content": "..."}, ...]
    """
    config = {"configurable": {"thread_id": session_id}}
    checkpointer = await _get_checkpointer()

    try:
        # 使用 alist() 获取最新检查点，limit=1 只取最新的一条
        state = None
        async for checkpoint_tuple in checkpointer.alist(config, limit=1):
            state = checkpoint_tuple
            break
    except Exception as e:
        logger.warning("Failed to list checkpoints for session %s: %s", session_id[:8], e)
        return []

    if state is None:
        logger.info("No checkpoint found for session %s", session_id[:8])
        return []

    # 从 checkpoint 提取 messages 检查点的结构：
                # checkpoint = {
                #     "id": "xxx",
                #     "channel_values": {
                #         "messages": [HumanMessage("你好"), AIMessage("你好！"), ...],

    try:
        checkpoint = state.checkpoint
        channel_values = checkpoint.get("channel_values", {}) if isinstance(checkpoint, dict) else {}
        messages = channel_values.get("messages", [])
    except Exception as e:
        logger.warning("Failed to extract messages for session %s: %s", session_id[:8], e)
        return []

    # 转换为前端可显示的格式
            #     {"role": "user", "content": "你好"},
            #     {"role": "assistant", "content": "你好！有什么可以帮你？"},
            #     {"role": "user", "content": "介绍一下 LangGraph"},
            #     {"role": "assistant", "content": "LangGraph 是..."}

    history = []
    for msg in messages:
        if isinstance(msg, BaseMessage):
            if msg.type in ("system", "tool"):
                continue
            role = "user" if msg.type == "human" else "assistant"
            content = msg.content or ""
            if content:
                history.append({"role": role, "content": content})

    logger.info("Loaded %d messages from checkpoint for session %s", len(history), session_id[:8])
    return history


async def delete_checkpoint(session_id: str):
    """删除指定会话的 Redis 检查点。"""
    checkpointer = await _get_checkpointer()
    try:
        await checkpointer.adelete_thread(session_id)
        logger.info("Deleted checkpoint for session %s", session_id[:8])
    except Exception as e:
        logger.warning("Failed to delete checkpoint for session %s: %s", session_id[:8], e)