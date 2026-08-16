"""
FastAPI 路由 — REST API + SSE 流式聊天。

替代 Gradio UI 的后端接口层。
交叉引用:
  - agent.src.core.workflow_router — 工作流决策路由（main_router / process_router 等）
  - agent.memory.* — 会话管理、记忆提取
  - utils.log — 日志工具
"""

import asyncio
import json
import os
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
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

# ── Pydantic 模型 ──


class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: int = USER_ID
    history: list[dict] = []
    attachments: list[dict] = []


class ResumeRequest(BaseModel):
    session_id: str
    action_id: str
    choice: str
    input_text: str = ""


# ── 序列化辅助 ──


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


# ── 标题生成辅助 ──

_known_message_counts: dict[str, int] = {}


def _should_generate_title(sid: str, history: list) -> bool:
    """判断是否需要生成标题：第一次收到回复时触发。"""
    if not sid or not history:
        return False
    known = _known_message_counts.get(sid, 0)
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


# ── 路由 ──

router = APIRouter(prefix="/api")

_INTERRUPT_TOKEN = "__INTERRUPT__"


@router.get("/init")
async def get_init():
    """
    页面初始化。
    返回会话列表 + 第一个会话的历史。
    """
    sessions = await list_sessions(user_id=USER_ID)
    if not sessions:
        sid = await create_session(user_id=USER_ID)
        return {
            "sessions": [{"id": str(sid), "name": "新会话", "message_count": 0}],
            "current_session_id": str(sid),
            "history": [],
        }
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
    try:
        await delete_checkpoint(session_id)
    except Exception as e:
        logger.warning("Failed to delete checkpoint %s: %s", session_id[:8], e)

    try:
        await db_delete_session(UUID(session_id))
    except Exception as e:
        logger.warning("Failed to delete session %s: %s", session_id[:8], e)

    sessions = await list_sessions(user_id=USER_ID)
    if not sessions:
        sid = await create_session(user_id=USER_ID)
        sessions = await list_sessions(user_id=USER_ID)
        return {
            "session_id": str(sid),
            "sessions": _serialize_sessions(sessions),
            "history": [],
        }
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
    SSE 流式聊天 + 人工中断检测。

    请求体: { message, session_id, user_id, history }
    响应: text/event-stream
      data: {"type":"chunk","content":"..."}
      data: {"type":"human_choice","options":[...],"action_id":"..."}
      data: {"type":"human_review","options":[...],"action_id":"...","prompt":"..."}
      data: {"type":"title","sessions":[...]}
      data: {"type":"done"}
      data: {"type":"error","message":"..."}
    """
    # 从 app.state 取出 (generate_response, system_ref)
    generate_response, system_ref = request.app.state.generate_response

    async def event_generator():
        full_content = ""
        history = payload.history or []
        session_id = payload.session_id
        user_id = payload.user_id

        try:
            async for content, new_history in generate_response(
                payload.message, history, session_id, user_id
            ):
                # 检测人工中断事件（interrupt() 暂停）
                if content == _INTERRUPT_TOKEN:
                    # new_history 现在是 interrupt_value（options_data dict），不是 state
                    pending = new_history if isinstance(new_history, dict) else {}
                    action_type = pending.get("type", "")
                    if action_type == "choice":
                        yield f"data: {json.dumps({'type': 'human_choice', 'options': pending.get('options', []), 'action_id': pending.get('action_id', '')}, ensure_ascii=False)}\n\n"
                    elif action_type == "review":
                        yield f"data: {json.dumps({'type': 'human_review', 'options': pending.get('options', []), 'action_id': pending.get('action_id', ''), 'prompt': pending.get('prompt', '')}, ensure_ascii=False)}\n\n"
                    return  # 流结束，等待 resume

                # 正常 chunk
                current_history = new_history
                if current_history and len(current_history) > 0:
                    last = current_history[-1]
                    if isinstance(last, dict) and last.get("role") == "assistant":
                        new_content = last.get("content", "")
                        if len(new_content) > len(full_content):
                            delta = new_content[len(full_content):]
                            full_content = new_content
                            if delta:
                                yield f"data: {json.dumps({'type': 'chunk', 'content': delta}, ensure_ascii=False)}\n\n"

            # ── 流结束后的副作用 ──

            try:
                await update_message_count(UUID(session_id))
            except Exception as e:
                logger.warning("Failed to update message count: %s", e)

            updated_history = history + [{"role": "assistant", "content": full_content}]
            title = await _try_generate_title(session_id, updated_history)
            if title:
                sessions = await list_sessions(user_id=user_id)
                yield f"data: {json.dumps({'type': 'title', 'sessions': _serialize_sessions(sessions)})}\n\n"

            try:
                asyncio.create_task(profile_extractor.extract_from_conversation(
                    user_id=user_id,
                    session_id=session_id,
                    messages=updated_history,
                ))
            except Exception as e:
                logger.warning("Failed to trigger memory extraction: %s", e)

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


@router.post("/chat/resume")
async def chat_resume(payload: ResumeRequest, request: Request):
    """
    恢复被 interrupt 暂停的工作流（人工选择后回调）。

    请求体: { session_id, action_id, choice, input_text }
    响应: 与 /chat/stream 相同的 SSE 流
    """
    _, system_ref = request.app.state.generate_response
    user_id = payload.user_id if hasattr(payload, 'user_id') else USER_ID

    async def event_generator():
        full_content = ""
        history: list = []

        try:
            resume_data = {
                "choice": payload.choice,
                "input_text": payload.input_text,
            }

            async for content, new_history in system_ref.resume(
                payload.session_id, resume_data, user_id=USER_ID
            ):
                if content == _INTERRUPT_TOKEN:
                    # 又遇到新的中断（比如 HumanChoice 之后又有 HumanReview）
                    pending = new_history if isinstance(new_history, dict) else {}
                    action_type = pending.get("type", "")
                    if action_type == "choice":
                        yield f"data: {json.dumps({'type': 'human_choice', 'options': pending.get('options', []), 'action_id': pending.get('action_id', '')}, ensure_ascii=False)}\n\n"
                    elif action_type == "review":
                        yield f"data: {json.dumps({'type': 'human_review', 'options': pending.get('options', []), 'action_id': pending.get('action_id', ''), 'prompt': pending.get('prompt', '')}, ensure_ascii=False)}\n\n"
                    return

                history = new_history or history
                if history and len(history) > 0:
                    last = history[-1]
                    if isinstance(last, dict) and last.get("role") == "assistant":
                        new_content = last.get("content", "")
                        if len(new_content) > len(full_content):
                            delta = new_content[len(full_content):]
                            full_content = new_content
                            if delta:
                                yield f"data: {json.dumps({'type': 'chunk', 'content': delta}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            logger.exception("Chat resume error for session %s", payload.session_id[:8])
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