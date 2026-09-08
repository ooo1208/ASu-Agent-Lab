"""
DeepAgent Chat API - FastAPI 主应用

提供基于 DeepAgent 的 AI 对话系统后端 API
"""

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_view.web_config import API_TITLE, API_VERSION, API_DESCRIPTION
from api_view.api import auth, chat, history, tasks
from api_view.agent_loader import agent_loader
from api_view.auth_service import initialize_auth, get_current_user
from asu_eval.api import create_router
from asu_finance import create_finance_router
from asu_lab.services import evidence_store, evaluation_store
from asu_lab.settings import validate_live_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理

    在应用启动时初始化 Agent，在应用关闭时清理资源
    """
    # ============================================================
    # 应用启动时执行
    # ============================================================
    print("=" * 50)
    print("正在启动 DeepAgent Chat API...")
    print("=" * 50)

    # 初始化认证集合和 Agent
    validate_live_settings()
    initialize_auth()
    await agent_loader.initialize()

    print("=" * 50)
    print("DeepAgent Chat API 启动成功!")
    print("=" * 50)

    try:
        yield
    finally:
        # ============================================================
        # 应用关闭时执行
        # ============================================================
        print("=" * 50)
        print("正在关闭 DeepAgent Chat API...")
        await agent_loader.shutdown()
        print("=" * 50)


# 创建 FastAPI 应用
app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    lifespan=lifespan,
)

# ============================================================
# CORS 中间件配置
# ============================================================
# 允许跨域请求，方便前端开发
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 注册路由
# ============================================================
# 对话相关接口
app.include_router(chat.router, prefix="/api", tags=["对话"])
# 历史记录相关接口
app.include_router(history.router, prefix="/api", tags=["历史记录"])
# 用户认证接口
app.include_router(auth.router, prefix="/api", tags=["用户认证"])
# 异步任务状态与结果
app.include_router(tasks.router, prefix="/api", tags=["异步任务"])
app.include_router(create_finance_router(evidence_store(), get_current_user), prefix="/api")
app.include_router(create_router(evaluation_store(), get_current_user), prefix="/api")


@app.get("/api/lab/status")
def lab_status():
    return {"mode": "live", "model_calls_enabled": True, "prompt_release": os.getenv("ASU_PROMPT_RELEASE", "v1")}


# ============================================================
# 根路径
# ============================================================
@app.get("/", tags=["首页"])
async def root():
    """
    根路径

    返回 API 基本信息
    """
    return {
        "name": API_TITLE,
        "version": API_VERSION,
        "description": "基于 DeepAgent 的 AI 对话系统 API",
        "docs": "/docs",
        "redoc": "/redoc"
    }


# ============================================================
# 健康检查
# ============================================================
@app.get("/health", tags=["系统"])
async def health_check():
    """
    健康检查接口

    用于检查服务是否正常运行
    """
    return {
        "status": "healthy",
        "service": API_TITLE,
        "version": API_VERSION
    }


# ============================================================
# 启动命令
# ============================================================
# uvicorn api_view.web_main:app --reload --host 0.0.0.0 --port 8000
