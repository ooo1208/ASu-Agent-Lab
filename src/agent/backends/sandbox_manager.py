"""
沙箱管理器 — Per-User 沙箱生命周期管理 + 预热机制。

每个用户维护一个独立的 OpenSandbox，同一个用户的多条对话线程共享。
启动时预热一个沙箱，第一个用户连接时直接认领，无需等待创建。

沙箱 ID 通过 MongoDB 持久化，重启后可重连到已有沙箱。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from pymongo import MongoClient

from agent.backends.sandbox_proxy import SandboxBackendProxy

logger = logging.getLogger(__name__)

SANDBOX_COLLECTION = "sandbox_registry"

# ---- 全局状态 ----

SANDBOX_BACKENDS: dict[str, SandboxBackendProxy] = {}

_warm_reserve: SandboxBackendProxy | None = None
_warm_task: asyncio.Task | None = None
_warm_lock = asyncio.Lock()
_user_locks: dict[str, asyncio.Lock] = {}
_user_locks_guard = asyncio.Lock()

_mongo_client: MongoClient | None = None
_collection = None


def _get_sandbox_config():
    """Delay heavyweight config/checkpointer construction until sandbox I/O is needed."""
    from agent.core.config import SANDBOX_CONFIG
    return SANDBOX_CONFIG


def _sandbox_collection():
    if _mongo_client is None:
        raise RuntimeError("沙箱管理器未初始化，请先调用 initialize()")
    from agent.core.config import MONGODB_DB_NAME
    return _mongo_client[MONGODB_DB_NAME][SANDBOX_COLLECTION]


def _kill_sandbox_by_id(sandbox_id: str) -> None:
    """Terminate an OpenSandbox instance using the SDK's instance API."""
    from opensandbox import SandboxSync

    sandbox = SandboxSync.connect(
        sandbox_id,
        connection_config=_get_sandbox_config(),
    )
    sandbox.kill()


def _assert_sandbox_healthy(backend) -> None:
    """Raise when a health command fails, including backends that return an error result."""
    result = backend.execute("echo ok")
    if result.exit_code != 0:
        raise RuntimeError(
            f"Sandbox health command failed with exit code {result.exit_code}: "
            f"{result.output[:300]}"
        )


# ---- 公开 API ----


async def initialize(mongo_client: MongoClient) -> None:
    """启动时初始化 MongoDB 连接。"""
    global _mongo_client, _collection
    _mongo_client = mongo_client
    _collection = _sandbox_collection()
    _collection.create_index("user_id", unique=True)
    logger.info("沙箱管理器已初始化")


async def pre_warm() -> None:
    """启动时预热沙箱，首个用户连接时直接认领。失败不阻塞启动。"""
    global _warm_reserve
    logger.info("正在预热沙箱...")
    try:
        from agent.backends.sandbox_setup import setup_sandbox
        sandbox_backend = await asyncio.to_thread(setup_sandbox, _get_sandbox_config())
        _warm_reserve = SandboxBackendProxy(sandbox_backend)
        logger.info("预热沙箱就绪: %s", sandbox_backend.id)
    except Exception:
        logger.warning("预热沙箱失败，将在第一个用户连接时创建", exc_info=True)
        _warm_reserve = None


def start_pre_warm() -> asyncio.Task:
    """Schedule one tracked warm-up task and return it."""
    global _warm_task
    if _warm_task is None or _warm_task.done():
        _warm_task = asyncio.create_task(pre_warm())
    return _warm_task


async def ensure_sandbox_for_user(user_id: str) -> SandboxBackendProxy:
    """
    获取或创建某个用户的沙箱（五态生命周期）。

    0. _warm_reserve 有货 → 认领分配给 user
    1. 内存缓存命中 → ping 健康检查 → 失败则重建
    2. MongoDB 有 sandbox_id → connect(id) → 失败则重建
    3. 无任何记录 → 创建新沙箱
    """
    normalized_user_id = str(user_id).strip()
    if not normalized_user_id:
        raise ValueError("user_id must not be empty")

    async with await _lock_for_user(normalized_user_id):
        return await _ensure_sandbox_for_user(normalized_user_id)


async def _lock_for_user(user_id: str) -> asyncio.Lock:
    """Return the process-local lifecycle lock for one stable user ID."""
    async with _user_locks_guard:
        return _user_locks.setdefault(user_id, asyncio.Lock())


async def _ensure_sandbox_for_user(user_id: str) -> SandboxBackendProxy:
    """实现 ensure_sandbox_for_user 的已串行化生命周期逻辑。"""
    global _warm_reserve

    # 状态 1: 内存缓存命中
    proxy = SANDBOX_BACKENDS.get(user_id)
    if proxy is not None:
        try:
            await asyncio.to_thread(_assert_sandbox_healthy, proxy)
            logger.info("用户 %s 命中沙箱缓存: %s", user_id, proxy.id)
            return proxy
        except Exception:
            logger.warning("用户 %s 的沙箱 %s 不可达，重建中...", user_id, proxy.id)
            return await _recreate_sandbox(user_id, proxy)

    # 状态 2: MongoDB 重连
    doc = _sandbox_collection().find_one({"user_id": user_id})
    if doc and doc.get("sandbox_id"):
        sandbox_id = doc["sandbox_id"]
        logger.info("用户 %s 尝试重连沙箱: %s", user_id, sandbox_id)
        try:
            from agent.backends.sandbox_setup import setup_sandbox
            sandbox_backend = await asyncio.to_thread(
                setup_sandbox, _get_sandbox_config(), sandbox_id=sandbox_id,
            )
        except Exception:
            logger.warning("重连沙箱 %s 失败，将创建新沙箱", sandbox_id)
            return await _create_sandbox_for_user(user_id)

        try:
            await asyncio.to_thread(_assert_sandbox_healthy, sandbox_backend)
        except Exception:
            logger.warning("已连接的沙箱 %s 不可达，创建新沙箱", sandbox_id)
            return await _recreate_sandbox(user_id, None)

        proxy = SandboxBackendProxy(sandbox_backend)
        SANDBOX_BACKENDS[user_id] = proxy
        # setup_sandbox() intentionally falls back to a new sandbox when an
        # existing ID has expired. Detect that fallback and persist the actual
        # replacement ID instead of leaving a stale registry entry.
        replacement_id = sandbox_backend.id
        _sandbox_collection().update_one(
            {"user_id": user_id},
            {"$set": {
                "sandbox_id": replacement_id,
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        if replacement_id != sandbox_id:
            logger.info(
                "用户 %s 的过期沙箱已由 setup_sandbox 替换: %s -> %s",
                user_id, sandbox_id, replacement_id,
            )
        return proxy

    # Only a genuinely new user may claim the reserve. Existing users above
    # must reconnect their persisted sandbox rather than overwrite the binding.
    warm_task = _warm_task
    if warm_task is not None and not warm_task.done():
        try:
            await asyncio.shield(warm_task)
        except Exception:
            pass

    # 状态 0: 认领预热沙箱
    async with _warm_lock:
        if _warm_reserve is not None:
            proxy = _warm_reserve
            _warm_reserve = None
            sandbox_id = proxy.id

            SANDBOX_BACKENDS[user_id] = proxy
            _sandbox_collection().update_one(
                {"user_id": user_id},
                {"$set": {
                    "sandbox_id": sandbox_id,
                    "updated_at": datetime.now(timezone.utc),
                    "created_at": datetime.now(timezone.utc),
                }},
                upsert=True,
            )
            logger.info("用户 %s 认领了预热沙箱: %s", user_id, sandbox_id)
            asyncio.create_task(_replenish_warm())
            return proxy

    # 状态 3: 无记录，创建新沙箱
    return await _create_sandbox_for_user(user_id)


async def ping_user_sandbox(user_id: str) -> bool:
    """公开的沙箱健康检查，供中间件调用。"""
    proxy = SANDBOX_BACKENDS.get(user_id)
    if proxy is None:
        return False
    try:
        await asyncio.to_thread(_assert_sandbox_healthy, proxy)
        return True
    except Exception:
        return False


async def recreate_user_sandbox(user_id: str) -> SandboxBackendProxy:
    """
    公开的沙箱重建方法，供 SandboxHealthMiddleware 在检测到沙箱不可用时调用。

    创建新沙箱（含 skills 播种 + venv），替换 proxy 内的 backend，
    删除旧沙箱，更新 MongoDB 绑定。不包含 AGENTS.md 上传，由调用方负责。
    """
    normalized_user_id = str(user_id).strip()
    if not normalized_user_id:
        raise ValueError("user_id must not be empty")
    async with await _lock_for_user(normalized_user_id):
        proxy = SANDBOX_BACKENDS.get(normalized_user_id)
        return await _recreate_sandbox(normalized_user_id, proxy)


async def cleanup_user(user_id: str) -> None:
    """销毁某用户的沙箱。"""
    proxy = SANDBOX_BACKENDS.pop(user_id, None)
    if proxy is not None:
        try:
            await asyncio.to_thread(_kill_sandbox_by_id, proxy.id)
        except Exception:
            logger.warning("删除沙箱 %s 失败", proxy.id, exc_info=True)

    _sandbox_collection().delete_one({"user_id": user_id})
    logger.info("用户 %s 沙箱已清理", user_id)


async def shutdown() -> None:
    """释放进程资源，但保留已分配用户沙箱，供下次启动重连。"""
    global _warm_reserve, _warm_task, _mongo_client
    logger.info("正在清理所有沙箱...")

    if _warm_reserve is not None:
        try:
            await asyncio.to_thread(_kill_sandbox_by_id, _warm_reserve.id)
        except Exception:
            pass
    _warm_reserve = None
    _warm_task = None

    SANDBOX_BACKENDS.clear()
    _user_locks.clear()

    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None

    logger.info("沙箱管理器已关闭")


# ---- 内部函数 ----


async def _create_sandbox_for_user(user_id: str) -> SandboxBackendProxy:
    """创建新沙箱并绑定到用户。"""
    from agent.backends.sandbox_setup import setup_sandbox

    logger.info("为用户 %s 创建新沙箱...", user_id)
    sandbox_backend = await asyncio.to_thread(setup_sandbox, _get_sandbox_config())
    sandbox_id = sandbox_backend.id

    proxy = SandboxBackendProxy(sandbox_backend)
    SANDBOX_BACKENDS[user_id] = proxy

    _sandbox_collection().update_one(
        {"user_id": user_id},
        {"$set": {
            "sandbox_id": sandbox_id,
            "updated_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )

    logger.info("用户 %s 沙箱创建完成: %s", user_id, sandbox_id)
    return proxy


async def _recreate_sandbox(
    user_id: str, existing_proxy: SandboxBackendProxy | None,
) -> SandboxBackendProxy:
    """重建沙箱（原沙箱不可达时）。"""
    from agent.backends.sandbox_setup import setup_sandbox

    logger.info("为用户 %s 重建沙箱...", user_id)
    sandbox_backend = await asyncio.to_thread(setup_sandbox, _get_sandbox_config())
    sandbox_id = sandbox_backend.id

    if existing_proxy is not None:
        existing_proxy.replace_backend(sandbox_backend)
    else:
        existing_proxy = SandboxBackendProxy(sandbox_backend)
        SANDBOX_BACKENDS[user_id] = existing_proxy

    # 尝试删除旧沙箱
    old_doc = _sandbox_collection().find_one({"user_id": user_id})
    if old_doc and old_doc.get("sandbox_id"):
        old_id = old_doc["sandbox_id"]
        try:
            await asyncio.to_thread(_kill_sandbox_by_id, old_id)
        except Exception:
            pass

    _sandbox_collection().update_one(
        {"user_id": user_id},
        {"$set": {
            "sandbox_id": sandbox_id,
            "updated_at": datetime.now(timezone.utc),
        }, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )

    logger.info("用户 %s 沙箱重建完成: %s", user_id, sandbox_id)
    return existing_proxy


async def _replenish_warm() -> None:
    """后台补充预热沙箱（被认领后异步触发）。"""
    global _warm_reserve
    if _warm_reserve is not None:
        return

    try:
        from agent.backends.sandbox_setup import setup_sandbox
        sandbox_backend = await asyncio.to_thread(setup_sandbox, _get_sandbox_config())
        async with _warm_lock:
            if _warm_reserve is None:
                _warm_reserve = SandboxBackendProxy(sandbox_backend)
                logger.info("后台补充预热沙箱就绪: %s", sandbox_backend.id)
    except Exception:
        logger.warning("后台补充预热沙箱失败", exc_info=True)
