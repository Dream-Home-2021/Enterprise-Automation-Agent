"""
会话管理 — 会话 CRUD + LLM 自动标题生成。
通过 `get_config()` 获取 user_id 上下文。
"""

from uuid import UUID

from agent.db import postgres as db
from agent.src.config import AGENT_MODELS
from agent.src.llm.factory import ProviderFactory
from utils.log import get_logger

logger = get_logger(__name__)

_TITLE_LLM = None
_TITLE_AGENT_NAME = "session_title_agent"


def _get_llm():
    """从 agent_models.yaml chat_agent 配置创建 LLM 实例（规范化配置源）。"""
    global _TITLE_LLM
    if _TITLE_LLM is None:
        provider_name = AGENT_MODELS.get_provider(_TITLE_AGENT_NAME)
        model_config = AGENT_MODELS.get_model_config(_TITLE_AGENT_NAME).copy()

        provider = ProviderFactory().create_provider(provider_name)
        model_class = provider.get_model_class()

        # 标题生成更确定性，覆盖 temperature
        model_config["temperature"] = 0.3

        # 补充供应商专属参数（base_url、api_key、headers 等）
        if hasattr(provider, "get_extra_kwargs"):
            model_config.update(provider.get_extra_kwargs())

        _TITLE_LLM = model_class(**model_config)
    return _TITLE_LLM


TITLE_PROMPT = """根据用户的第一条消息，生成一个简短的会话标题（5-15 字）。

用户消息: {message}

要求：
- 5-15 个汉字
- 准确概括用户意图
- 不要加标点
- 直接输出标题

标题："""


async def create_session(user_id: int = 1) -> UUID:
    """创建新会话，返回 session_id。"""
    return await db.create_session(user_id=user_id)


async def generate_session_title(session_id: UUID, first_message: str) -> str:
    """根据第一条消息生成会话标题并更新。"""
    llm = _get_llm()
    try:
        resp = await llm.ainvoke([
            {"role": "user", "content": TITLE_PROMPT.format(message=first_message[:200])}
        ])
        title = resp.content.strip().strip('"').strip("'").strip("标题：").strip()
        if not title or len(title) > 30:
            title = first_message[:20] + "..."
    except Exception as e:
        logger.warning("Title generation failed: %s", e)
        title = first_message[:20] + "..."

    await db.update_session_name(session_id, title)
    logger.info("Session %s title: %s", session_id, title)
    return title


async def list_sessions(user_id: int = 1) -> list[dict]:
    """列出用户所有会话。"""
    return await db.list_sessions(user_id=user_id)


async def delete_session(session_id: UUID):
    """删除会话及关联数据。"""
    await db.delete_session(session_id)


async def update_message_count(session_id: UUID, delta: int = 1):
    """递增会话消息数。"""
    await db.update_session_message_count(session_id, delta=delta)