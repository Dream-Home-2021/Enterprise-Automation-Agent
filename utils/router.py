"""
FastAPI 路由 — REST API + SSE 流式聊天。

替代 Gradio UI 的后端接口层。。。
"""

import asyncio
import json
import os
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.memory.history import load_conversation_history, delete_checkpoint
from agent.memory import profile as profile_extractor
from agent.memory.session import (
    create_session,
    list_sessions,
    generate_session_title,
    update_message_count,
    delete_session as db_delete_session,
)
from utils.log import get_logger

logger = get_logger(__name__)

USER_ID = int(os.getenv("AGENT_USER_ID", "1"))

# ── Pydantic 模型 ───────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: int = USER_ID
    history: list[dict] = []


# ── 序列化辅助 ──────────────────────────────────────────────────────


def _serialize_session(s: dict) -> dict:
    return {
        "id": str(s["id"]),
        "name": s["name"],
        "message_count": s.get("message_count", 0),
        "created_at": s["created_at"].isoformat() if hasattr(s["created_at"], "isoformat") else str(s["created_at"]),
        "updated_at": s["updated_at"].isoformat() if hasattr(s["updated_at"], "isoformat") else str(s["updated_at"]),
    }


def _serialize_sessions(sessions: list[dict]) -> list[dict]:
    return [_serialize_session(s) for s in sessions]


# ── 标题生成辅助 ────────────────────────────────────────────────────

_known_message_counts: dict[str, int] = {}


def _should_generate_title(sid: str, history: list) -> bool:
    """判断是否需要生成标题：第一次收到回复时触发。"""
    if not sid or not history:
        return False
    known = _known_message_counts.get(sid, 0)
    # 如果之前消息数为 0（第一次），且当前历史至少有 2 条（用户消息 + 助手回复），则触发标题生成
    if known == 0 and len(history) >= 2:
        _known_message_counts[sid] = len(history)
        return True
    _known_message_counts[sid] = len(history)
    return False


async def _try_generate_title(session_id: str, history: list) -> str | None:
    """如果条件满足，生成标题并返回新的会话名称。"""
    if not _should_generate_title(session_id, history):
        return None
    first_msg = ""
    # 遍历历史，找到第一条用户消息的内容，作为生成标题的素材
    for m in history:
        if isinstance(m, dict) and m.get("role") == "user":
            first_msg = m["content"]
            break
    if not first_msg:
        return None
    try:
        return await generate_session_title(UUID(session_id), first_msg)
    except Exception as e:
        logger.warning("Title gen failed: %s", e)
        return None


# ── 路由 ────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api")


@router.get("/init")
async def get_init():
    """
    页面初始化。
    返回会话列表 + 第一个会话的历史。
    """
    sessions = await list_sessions(user_id=USER_ID)
    # 如果没有任何会话，自动创建一个新会话， 历史为空。
    if not sessions:
        sid = await create_session(user_id=USER_ID)
        return {
            "sessions": [{"id": str(sid), "name": "新会话", "message_count": 0}],
            "current_session_id": str(sid),
            "history": [],
        }
    # 如果有会话，取第一个会话，加载它的聊天历史
    first = sessions[0]
    first_sid = str(first["id"])
    history = await load_conversation_history(first_sid)
    return {
        "sessions": _serialize_sessions(sessions),
        "current_session_id": first_sid,
        "history": history,
    }


@router.post("/sessions")
async def new_session():
    """创建新会话。"""
    sid = await create_session(user_id=USER_ID)
    sessions = await list_sessions(user_id=USER_ID)
    return {
        "session_id": str(sid),
        "sessions": _serialize_sessions(sessions),
    }


@router.get("/sessions/{session_id}/history")
async def get_history(session_id: str):
    """获取指定会话的聊天历史。"""
    history = await load_conversation_history(session_id)
    return {"history": history}


@router.delete("/sessions/{session_id}")
async def delete_session_route(session_id: str):
    """
    删除会话（Redis 检查点 + PostgreSQL 行）。
    如果删除后没有会话了，自动创建一个新的。
    """
    # 删除会话：同时清理 Redis 检查点和 PostgreSQL 数据库行
    try:
        await delete_checkpoint(session_id)
    except Exception as e:
        logger.warning("Failed to delete checkpoint %s: %s", session_id[:8], e)

    try:
        await db_delete_session(UUID(session_id))
    except Exception as e:
        logger.warning("Failed to delete session %s: %s", session_id[:8], e)

    sessions = await list_sessions(user_id=USER_ID)
    # 删除后检查是否还有会话。如果没有，自动创建一个新会话并返回。
    if not sessions:
        sid = await create_session(user_id=USER_ID)
        sessions = await list_sessions(user_id=USER_ID)
        return {
            "session_id": str(sid),
            "sessions": _serialize_sessions(sessions),
            "history": [],
        }
    # 如果还有剩余会话，返回第一个会话的信息和历史。
    first = sessions[0]
    first_sid = str(first["id"])
    history = await load_conversation_history(first_sid)
    return {
        "session_id": first_sid,
        "sessions": _serialize_sessions(sessions),
        "history": history,
    }


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request):
    """
    SSE 流式聊天。

    请求体: { message, session_id, user_id, history }
    响应: text/event-stream
      data: {"type":"chunk","content":"..."}
      data: {"type":"title","sessions":[...]}
      data: {"type":"done"}
      data: {"type":"error","message":"..."}
    """
    # 从 `app.state` 取出函数 
    generate_response = request.app.state.generate_response

    async def event_generator():
        full_content = ""
        history = payload.history or []
        session_id = payload.session_id
        user_id = payload.user_id

        # 参数传入server.py的generate_response函数内， yield流式传输 agent回复的最新的一条信息
        try:
            # ── 流式生成 ──────────────────────────────────────────
            async for result in generate_response(
                payload.message, history, session_id, user_id
            ):
                current_history = result[1]
                if current_history and len(current_history) > 0:
                    last = current_history[-1]
                    if isinstance(last, dict) and last.get("role") == "assistant":
                        new_content = last.get("content", "")
                        if len(new_content) > len(full_content):
                            delta = new_content[len(full_content):]
                            full_content = new_content
                            if delta:
                                yield f"data: {json.dumps({'type': 'chunk', 'content': delta}, ensure_ascii=False)}\n\n"

            # ── 流结束后的副作用 ──────────────────────────────────

            # 1. 更新消息计数
            try:
                await update_message_count(UUID(session_id))
            except Exception as e:
                logger.warning("Failed to update message count: %s", e)

            # 2. 标题生成（如果该生成的话）
            updated_history = history + [{"role": "assistant", "content": full_content}]
            title = await _try_generate_title(session_id, updated_history)
            if title:
                sessions = await list_sessions(user_id=user_id)
                yield f"data: {json.dumps({'type': 'title', 'sessions': _serialize_sessions(sessions)})}\n\n"

            # --- 3. 异步触发长期记忆提取（fire-and-forget，不阻塞响应） ---
            try:
                asyncio.create_task(profile_extractor.extract_from_conversation(
                    user_id=user_id,
                    session_id=session_id,
                    messages=updated_history,
                ))
            except Exception as e:
                logger.warning("Failed to trigger memory extraction: %s", e)

            # 4. 完成
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            logger.exception("Chat stream error for session %s", session_id[:8])
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )