import os
from functools import lru_cache
from datetime import timedelta
from pathlib import Path

import httpx
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.mongodb import MongoDBSaver
from opensandbox.config import ConnectionConfigSync
from pymongo import MongoClient

from agent.core.env_utils import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    ZHIPU_API_KEY,
    ZHIPU_BASE_URL,
)
from agent.stores.mongodb_store import MongoDBStore

# ---------- 模型配置 ----------
# 主 Agent 模型
MAIN_MODEL = ChatOpenAI(
    model=os.getenv("MAIN_MODEL", "deepseek-chat"),
    temperature=float(os.getenv("MODEL_TEMPERATURE", "0.2")),
    openai_api_key=DEEPSEEK_API_KEY or "not-configured",
    openai_api_base=DEEPSEEK_BASE_URL or "https://api.deepseek.com",
    max_tokens=int(os.getenv("MODEL_MAX_OUTPUT_TOKENS", "8192")),
)
# 摘要专用模型（摘要需要稳定输出，temperature 设为较低值）
SUMMARY_MODEL = ChatOpenAI(
    model=os.getenv("SUMMARY_MODEL", os.getenv("MAIN_MODEL", "deepseek-chat")),
    temperature=0.1,
    openai_api_key=DEEPSEEK_API_KEY or "not-configured",
    openai_api_base=DEEPSEEK_BASE_URL or "https://api.deepseek.com",
    max_tokens=int(os.getenv("SUMMARY_MAX_OUTPUT_TOKENS", "2048")),
)

# ---------- 沙箱配置 ----------
# OpenSandbox 沙箱配置连接
SANDBOX_CONFIG = ConnectionConfigSync(
    domain=os.getenv("OPENSANDBOX_URL", "http://127.0.0.1:8100"),
    api_key=os.getenv("OPENSANDBOX_API_KEY") or None,
    use_server_proxy=True,
    request_timeout=timedelta(seconds=60),
    transport=httpx.HTTPTransport(limits=httpx.Limits(max_connections=20)),
)

# ---------- 路径常量 ----------
# config.py 位于 src/agent/core/；显式区分源码根和 Agent 包根，避免模块
# 移动后通过脆弱的字符串拼接产生 src/agent/agent 一类错误路径。
SRC_DIR = Path(__file__).resolve().parents[2]
AGENT_DIR = SRC_DIR / "agent"
# 沙箱内技能根路径
SANDBOX_SKILLS_ROOT = "/skills"
# 沙箱内记忆根路径（用户私有记忆存放处）
SANDBOX_MEMORIES_ROOT = "/memories"
# 沙箱内分析中间文件存放目录
SANDBOX_ANALYSIS_ROOT = "/analysis"
# 沙箱内数据文件存放目录
SANDBOX_DATA_ROOT = "/data"
# 本地技能资源目录（项目内的路径，相对于项目根）
LOCAL_SKILLS_DIR = SRC_DIR / "skills"
# 本地下载目录（从沙箱下载文件的目标路径）
DOWNLOAD_DIR = SRC_DIR / "download"
# 本地子 Agent 配置目录
LOCAL_SUBAGENT_CONFIG_DIR = AGENT_DIR / "subagents"
# 本地的Agent记忆文件
LOCAL_AGENTS_MD = AGENT_DIR / "memory" / "AGENTS.md"

# ---------- 文件名常量 ----------
# 主 Agent 只读指引文件（上传到沙箱 /AGENTS.md）
AGENTS_MD_FILENAME = "/AGENTS.md"
# 用户偏好文件名（在 /memories/{user_id}/ 下）
USER_PREFERENCES_FILENAME = "preferences.md"

# ---------- 用户技能持久化 ----------
# 技能持久化 StoreBackend 路由路径
PERSISTED_SKILLS_ROOT = "/persisted-skills"
# 用户技能按受信任的认证用户 ID 隔离。最终 namespace 结构为：
# ("users", user_id, "skills")。
SKILLS_STORE_NAMESPACE_PREFIX = ("users",)


def user_skills_namespace(user_id: str) -> tuple[str, ...]:
    """Return the private Store namespace for one authenticated user's skills."""
    normalized_user_id = str(user_id).strip()
    if not normalized_user_id:
        raise ValueError("user_id must not be empty")
    return (*SKILLS_STORE_NAMESPACE_PREFIX, normalized_user_id, "skills")
# 子 Agent 名称 → 技能 scope 目录映射
SCOPE_MAP = {
    "main": "main",
    "procurement-analyst": "procurement",
    "procurement-order": "order",
}

# ---------- 中间件参数 ----------

# ---------- MongoDB 配置（用于持久化 Agent 状态、记忆和技能） ----------
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "asu_agent")
MONGODB_CHECKPOINT_COLLECTION = "checkpoints"
MONGODB_STORE_COLLECTION = "store_items"

# ---------- 持久化存储 ----------
_mongodb_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000, connect=False)

# MongoDBStore: 用户偏好和已分配技能的持久化 Store。
STORE = MongoDBStore(
    client=_mongodb_client,
    db_name=MONGODB_DB_NAME,
    collection_name=MONGODB_STORE_COLLECTION,
)

# MongoDBSaver: Agent 对话状态的 MongoDB 持久化 checkpointer。
# 支持 Human-in-the-Loop（interrupt 状态持久化）和跨重启对话恢复。
@lru_cache(maxsize=1)
def get_checkpointer():
    """Create indexes only when the live graph is first initialized."""
    return MongoDBSaver(
        client=_mongodb_client,
        db_name=MONGODB_DB_NAME,
        checkpoint_collection_name=MONGODB_CHECKPOINT_COLLECTION,
    )


