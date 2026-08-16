"""
HTML UI 版应用入口 — FastAPI + Uvicorn 替代 Gradio。

启动流程:
  1. 初始化 PostgreSQL 连接池 + 建表
  2. 创建带 RedisSaver 检查点的 Graph
  3. 启动 FastAPI / Uvicorn 服务
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from agent.src.core.api_routes import router
from agent.db.postgres import init_db, close_pool
from agent.db.redis import close_redis
from agent.src.system import make_generate_response
from agent.memory.profile import start_background_extractor, stop_background_extractor
from utils.log import get_logger

logger = get_logger("main_html")

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(_BASE, "static")
IMAGES_DIR = os.path.join(_BASE, "images")
FRONTEND_DIST = os.path.join(_BASE, "frontend", "dist")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    # 启动
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database ready")

    logger.info("Creating agent service...")
    generate_response, system_ref = await make_generate_response()
    app.state.generate_response = (generate_response, system_ref)
    logger.info("Agent service ready")

    logger.info("Starting background memory extractor...")
    await start_background_extractor()
    logger.info("Background extractor started")

    yield

    # 关闭
    logger.info("Shutting down...")
    await stop_background_extractor()
    await close_pool()
    await close_redis()
    logger.info("Shutdown complete")


app = FastAPI(title="My Agent", lifespan=lifespan)

# 挂载 API 路由
app.include_router(router)

# 挂载静态文件：优先使用 Vue 构建产物，其次后备回旧 static/
#
# 构建产物 index.html 中的资源引用是绝对路径 "/assets/*"（Vite 默认 base），
# 所以必须同时把 dist/assets 挂载到 /assets，否则浏览器拿不到 JS/CSS，页面空白。
if os.path.exists(FRONTEND_DIST):
    assets_dir = os.path.join(FRONTEND_DIST, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")
    app.mount("/static", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
elif os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 挂载 images 目录
if os.path.exists(IMAGES_DIR):
    app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")


@app.get("/")
async def index():
    """返回主页面 — 优先 Vue 构建产物。"""
    if os.path.exists(FRONTEND_DIST):
        index_path = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "index.html not found"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main.app_html:app",
        host=os.getenv("APP_HOST", "localhost"),
        port=int(os.getenv("APP_PORT", "7860")),
        reload=False,
    )