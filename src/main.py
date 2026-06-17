"""
Dynamic Emotional Agent System
FastAPI 异步服务启动入口 (ASGI)
"""

import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Lifespan — 启动/关闭时的资源管理
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：初始化数据库连接池、懒加载图编译"""
    from src.storage.connection import init_db_pool, close_db_pool
    from src.agents.graph import get_compiled_graph

    # 启动阶段
    await init_db_pool()
    print("[startup] Database pool initialized.")
    yield
    # 关闭阶段
    await close_db_pool()
    print("[shutdown] Database pool closed.")


app = FastAPI(
    title="Dynamic Emotional Agent System",
    description="具备动态情感感知与安全沙箱数据分析能力的 Multi-Agent 系统",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """聊天请求体"""
    username: str = "main"
    message: str
    session_id: str | None = None
    active_file_path: str | None = None


class ChatResponse(BaseModel):
    """非流式聊天响应"""
    session_id: str
    username: str
    current_emotion: str
    response: str
    requires_approval: bool = False
    approval_payload: dict | None = None


class ApprovalRequest(BaseModel):
    """高危操作审批请求"""
    session_id: str
    status: str  # approved / rejected / modified
    user_feedback: str = ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "dynamic-emotional-agent"}


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    非流式聊天接口（同步等待完整响应）
    """
    from src.agents.graph import get_compiled_graph
    from src.agents.state import GlobalAgentState

    try:
        graph = await get_compiled_graph()

        # 构建初始状态
        initial_state: GlobalAgentState = {
            "username": request.username,
            "role": "admin" if request.username == "main" else "visitor",
            "user_metrics": {
                "politeness": 50,
                "trust": 50,
                "rationality": 50,
                "empathy": 50,
            },
            "current_emotion": "normal",
            "long_term_insights": [],
            "messages": [{"role": "user", "content": request.message}],
            "active_file_path": request.active_file_path or "",
            "last_code_generated": "",
            "requires_approval": False,
            "approval_result": {},
        }

        config = {"configurable": {"thread_id": request.session_id or "default"}}
        result = await graph.ainvoke(initial_state, config=config)

        # 提取最后一条 AI 回复
        ai_messages = [m for m in result.get("messages", []) if m.get("role") == "assistant"]
        last_response = ai_messages[-1]["content"] if ai_messages else "..."

        return ChatResponse(
            session_id=request.session_id or "default",
            username=request.username,
            current_emotion=result.get("current_emotion", "normal"),
            response=last_response,
            requires_approval=result.get("requires_approval", False),
            approval_payload=result.get("approval_result"),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """
    流式 SSE 聊天接口 — 逐 token 推送给前端
    """
    from src.agents.graph import get_compiled_graph
    from src.guardrails.output_stream_buffer import OutputStreamBuffer

    async def event_generator():
        buffer = OutputStreamBuffer(window_size=6)

        try:
            graph = await get_compiled_graph()

            initial_state: GlobalAgentState = {
                "username": request.username,
                "role": "admin" if request.username == "main" else "visitor",
                "user_metrics": {
                    "politeness": 50,
                    "trust": 50,
                    "rationality": 50,
                    "empathy": 50,
                },
                "current_emotion": "normal",
                "long_term_insights": [],
                "messages": [{"role": "user", "content": request.message}],
                "active_file_path": request.active_file_path or "",
                "last_code_generated": "",
                "requires_approval": False,
                "approval_result": {},
            }

            config = {"configurable": {"thread_id": request.session_id or "default"}}

            async for event in graph.astream(initial_state, config=config):
                # 逐节点输出事件
                for node_name, node_output in event.items():
                    # 检查是否需要高危拦截
                    if node_output.get("requires_approval"):
                        import json
                        yield {
                            "event": "approval_required",
                            "data": json.dumps({
                                "session_id": request.session_id,
                                "emotional_state": node_output.get("current_emotion"),
                                "high_risk_action": node_output.get("approval_result"),
                            }),
                        }
                        return

                    # 流式文本通过 output buffer 过滤
                    messages = node_output.get("messages", [])
                    for msg in messages:
                        if msg.get("role") == "assistant":
                            content = msg.get("content", "")
                            filtered = buffer.process(content)
                            if filtered:
                                yield {
                                    "event": "token",
                                    "data": filtered,
                                }

                    # 推送情绪状态
                    emotion = node_output.get("current_emotion")
                    if emotion:
                        import json
                        yield {
                            "event": "emotion_update",
                            "data": json.dumps({"emotion": emotion}),
                        }

            yield {"event": "done", "data": ""}

        except Exception as e:
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())


@app.post("/approval")
async def approval_endpoint(request: ApprovalRequest):
    """
    高危操作审批回调 — 用户决策后通过此接口唤醒挂起的图执行
    """
    # TODO: 通过 LangGraph interrupt/resume 机制恢复挂起的图
    return {
        "status": "received",
        "session_id": request.session_id,
        "decision": request.status,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=True,
    )
