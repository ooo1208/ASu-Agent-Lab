"""
Agent 加载器

使用单例模式按用户加载和管理 DeepAgent 实例。
每个 Agent 实例绑定一个用户专属 OpenSandbox，并使用 MongoDB 持久化状态。
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime

# 将项目根目录添加到 Python 路径
PROJECT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

# 导入配置
from api_view.web_config import (
    MONGODB_URI,
    MONGODB_DB_NAME,
    MONGODB_CHECKPOINT_COLLECTION,
)


class AgentLoader:
    """
    Agent 加载器单例类

    负责管理 Agent 生命周期、MongoDB 连接和会话相关操作。
    每个用户的 Agent 实例按需创建，绑定其专属沙箱。
    checkpointer 由 main_agent 内部统一管理（MongoDBSaver）。
    """

    # 类级别的单例实例
    _instance: Optional['AgentLoader'] = None
    # MongoDB 客户端（用于展示消息存取、会话管理等直接 DB 操作）
    _mongodb_client: Optional[MongoClient] = None
    # 是否已初始化
    _initialized: bool = False
    # 仅为兼容历史记录读取保留每个用户最近创建的 graph；聊天请求本身
    # 会按 RunnableConfig 重新创建 graph，以绑定当次用户沙箱和中间件。
    _agents: Dict[str, tuple[str, Any]] = {}
    _agent_locks: Dict[str, asyncio.Lock] = {}
    _precomputed: Any = None
    _sandbox_manager: Any = None

    def __new__(cls):
        """确保单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self):
        """
        初始化 MongoDB 客户端。用户 Agent 及其沙箱在首个请求时按需创建。

        Agent 通过 main_agent.get_agent_async() 获取，
        内部已集成 MongoDBSaver checkpointer，无需在此重复创建。

        Returns:
            Agent 实例
        """
        if self._initialized:
            return None

        print("[AgentLoader] 开始初始化...")

        try:
            # 创建 MongoDB 客户端（用于展示消息存取、会话管理等直接 DB 操作）
            self._mongodb_client = MongoClient(MONGODB_URI)
            db = self._mongodb_client[MONGODB_DB_NAME]
            db["session_owners"].create_index("thread_id", unique=True)
            db["session_owners"].create_index([("user_id", 1), ("updated_at", -1)])

            from agent.backends import sandbox_manager
            from agent.graphs.main_agent import precompute_agent_context

            await sandbox_manager.initialize(self._mongodb_client)
            self._sandbox_manager = sandbox_manager
            self._precomputed = await precompute_agent_context()
            # 预热不阻塞 API 可用性；失败时首个用户请求会自行创建沙箱。
            sandbox_manager.start_pre_warm()

            self._initialized = True
            print("[AgentLoader] MongoDB、沙箱管理器和 Agent 预计算上下文初始化完成")
        except Exception:
            # Agent 创建失败时清理 MongoClient，防止重试时连接泄漏
            if self._mongodb_client is not None:
                self._mongodb_client.close()
                self._mongodb_client = None
            raise

        return None

    async def shutdown(self) -> None:
        """Release local resources while leaving user sandboxes available to reconnect."""
        if self._sandbox_manager is not None:
            await self._sandbox_manager.shutdown()
        elif self._mongodb_client is not None:
            self._mongodb_client.close()

        self._mongodb_client = None
        self._sandbox_manager = None
        self._precomputed = None
        self._agents.clear()
        self._agent_locks.clear()
        self._initialized = False
        print("[AgentLoader] 资源已释放")

    async def get_agent_for_user(self, user_id: str, config: Dict[str, Any]):
        """Create this request's graph bound to the user's stable sandbox proxy."""
        normalized_user_id = str(user_id).strip()
        if not normalized_user_id:
            raise ValueError("user_id must not be empty")
        if not self._initialized:
            await self.initialize()
        lock = self._agent_locks.setdefault(normalized_user_id, asyncio.Lock())
        async with lock:
            backend = await self._sandbox_manager.ensure_sandbox_for_user(
                normalized_user_id,
            )

            from agent.graphs.main_agent import create_main_agent

            agent = await create_main_agent(
                config,
                sandbox_backend=backend,
                precomputed=self._precomputed,
            )
            self._agents[normalized_user_id] = (backend.id, agent)
            return agent

    @property
    def agent(self):
        """
        获取 Agent 实例

        Returns:
            Agent 实例

        Raises:
            RuntimeError: 如果 Agent 未初始化
        """
        if not self._agents:
            raise RuntimeError("Agent 未初始化，请先调用 initialize() 方法")
        return next(iter(self._agents.values()))[1]

    # checkpointer 已由 main_agent 内部通过 MongoDBSaver 统一管理，
    # 不再在 AgentLoader 中重复创建。Agent 的 astream/aget_state 等
    # 方法直接使用其内部 checkpointer 进行对话状态持久化。

    def create_config(
        self,
        thread_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建 Agent 调用配置

        Args:
            thread_id: 会话 ID，为空则自动生成
            user_id: 用户 ID，用于记忆隔离和上下文注入。
                     为空时使用 'default_user'，多用户场景必须传入。
            **kwargs: 其他可配置的参数

        Returns:
            Dict: Agent 配置字典
        """
        return {
            "configurable": {
                "thread_id": thread_id or str(uuid.uuid4()),
                "user_id": user_id or "anonymous",
                **kwargs
            }
        }

    async def get_state_history(
        self,
        thread_id: str,
        user_id: str,
        limit: int = 50
    ) -> List[Any]:
        """
        获取会话的历史状态

        Args:
            thread_id: 会话 ID
            limit: 返回的最大状态数量

        Returns:
            List[StateSnapshot]: 状态快照列表
        """
        config = self.create_config(thread_id, user_id=user_id)
        agent = await self.get_agent_for_user(user_id, config)
        states = []

        # 使用 agent.get_state_history 获取历史
        async for state in agent.aget_state_history(config):
            states.append(state)
            if len(states) >= limit:
                break

        return states

    async def get_current_messages(self, thread_id: str, user_id: str) -> List[Dict[str, Any]]:
        """
        获取当前会话的消息列表

        Args:
            thread_id: 会话 ID

        Returns:
            List[Dict]: 消息列表
        """
        config = self.create_config(thread_id, user_id=user_id)

        try:
            agent = await self.get_agent_for_user(user_id, config)
            state = await agent.aget_state(config)
            if state and state.values:
                return state.values.get("messages", [])
        except Exception as e:
            print(f"[AgentLoader] 获取消息失败: {e}")

        return []

    def get_all_thread_ids(self) -> List[str]:
        """
        从 MongoDB 获取所有会话的 thread_id

        Returns:
            List[str]: 所有会话 ID 列表
        """
        if self._mongodb_client is None:
            return []

        db = self._mongodb_client[MONGODB_DB_NAME]
        collection = db[MONGODB_CHECKPOINT_COLLECTION]

        # 获取所有唯一的 thread_id（MongoDB 文档中 thread_id 直接存储在顶层字段）
        thread_ids = collection.distinct("thread_id")

        # 过滤掉空值和通配符
        return [tid for tid in thread_ids if tid and tid != "*" and tid != "" and tid is not None]

    def claim_thread(self, thread_id: str, user_id: str) -> None:
        """创建或校验会话归属；禁止其他用户复用同一 thread_id。"""
        if self._mongodb_client is None:
            raise RuntimeError("MongoDB 尚未初始化")
        collection = self._mongodb_client[MONGODB_DB_NAME]["session_owners"]
        now = datetime.now()
        existing = collection.find_one({"thread_id": thread_id})
        if existing:
            if existing.get("user_id") != user_id:
                raise PermissionError("无权访问该会话")
            collection.update_one({"thread_id": thread_id}, {"$set": {"updated_at": now}})
            return
        try:
            collection.insert_one({
                "thread_id": thread_id,
                "user_id": user_id,
                "created_at": now,
                "updated_at": now,
            })
        except DuplicateKeyError:
            existing = collection.find_one({"thread_id": thread_id})
            if not existing or existing.get("user_id") != user_id:
                raise PermissionError("无权访问该会话")

    def assert_thread_owner(self, thread_id: str, user_id: str) -> None:
        if self._mongodb_client is None:
            raise RuntimeError("MongoDB 尚未初始化")
        owner = self._mongodb_client[MONGODB_DB_NAME]["session_owners"].find_one(
            {"thread_id": thread_id, "user_id": user_id}
        )
        if owner is None:
            raise PermissionError("会话不存在或无权访问")

    def get_user_threads(self, user_id: str) -> List[Dict[str, Any]]:
        if self._mongodb_client is None:
            return []
        cursor = self._mongodb_client[MONGODB_DB_NAME]["session_owners"].find(
            {"user_id": user_id}
        ).sort("updated_at", -1)
        return list(cursor)

    def get_session_updated_at(self, thread_id: str) -> datetime:
        """
        获取会话的最后更新时间

        Args:
            thread_id: 会话 ID

        Returns:
            datetime: 最后更新时间
        """
        if self._mongodb_client is None:
            return datetime.now()

        db = self._mongodb_client[MONGODB_DB_NAME]
        collection = db[MONGODB_CHECKPOINT_COLLECTION]

        try:
            # 获取该 thread_id 的最新文档（按 _id 倒序，_id 包含时间戳）
            latest_doc = collection.find_one(
                {"thread_id": thread_id},
                sort=[("_id", -1)]
            )

            if latest_doc:
                # 从 _id 中提取时间戳（MongoDB _id 的前4字节是时间戳）
                if "_id" in latest_doc and hasattr(latest_doc["_id"], 'generation_time'):
                    return latest_doc["_id"].generation_time
                # 如果没有 generation_time 属性，尝试其他方式
                elif "_id" in latest_doc:
                    import bson
                    if isinstance(latest_doc["_id"], bson.objectid.ObjectId):
                        return latest_doc["_id"].generation_time

            return datetime.now()
        except Exception as e:
            print(f"[AgentLoader] 获取会话时间失败: {e}")
            return datetime.now()

    async def delete_session(self, thread_id: str, user_id: str) -> bool:
        """
        删除会话（删除该 thread_id 下的所有 checkpoint）

        Args:
            thread_id: 会话 ID

        Returns:
            bool: 是否删除成功
        """
        if self._mongodb_client is None:
            return False

        db = self._mongodb_client[MONGODB_DB_NAME]
        collection = db[MONGODB_CHECKPOINT_COLLECTION]

        try:
            self.assert_thread_owner(thread_id, user_id)
            # 删除该 thread_id 的所有 checkpoint
            result = collection.delete_many({
                "thread_id": thread_id
            })
            # 同步删除展示消息
            display_collection = db["session_display_messages"]
            display_result = display_collection.delete_many({"thread_id": thread_id})
            db["session_owners"].delete_one({"thread_id": thread_id, "user_id": user_id})
            print(f"[AgentLoader] 已删除会话 {thread_id}，checkpoint {result.deleted_count} 条，展示消息 {display_result.deleted_count} 条")
            return True
        except Exception as e:
            print(f"[AgentLoader] 删除会话失败: {e}")
            return False


    # ============================================================
    # 完整展示消息存取（包含子代理消息，解决 checkpoint 丢失子代理消息的问题）
    # ============================================================

    # 单字段最大字符数（约 500KB），防止单条消息超过 MongoDB 16MB 文档限制
    _MAX_FIELD_LENGTH = 500_000

    @classmethod
    def _truncate_message_fields(cls, msg: Dict[str, Any]) -> Dict[str, Any]:
        """截断消息中的超长文本字段，避免单文档超过 MongoDB 16MB 限制"""
        for field in ("text", "content", "args"):
            if field in msg and isinstance(msg[field], str) and len(msg[field]) > cls._MAX_FIELD_LENGTH:
                msg[field] = msg[field][:cls._MAX_FIELD_LENGTH] + "\n\n...(内容过长已截断)"
        return msg

    async def save_display_messages(
        self, thread_id: str, messages: List[Dict[str, Any]], user_id: str
    ) -> bool:
        """
        将完整的展示消息逐条存入 MongoDB

        改为逐条存储（每条消息一个 MongoDB 文档），彻底解决以下问题：
        1. 单文档 16MB 限制：长对话含大量工具结果时容易超限，导致保存静默失败
        2. 增量更新：后续可扩展为边流式边存储，即使中断也不丢数据

        Args:
            thread_id: 会话 ID
            messages: 完整的展示消息列表

        Returns:
            bool: 是否保存成功
        """
        if self._mongodb_client is None:
            return False

        try:
            db = self._mongodb_client[MONGODB_DB_NAME]
            collection = db["session_display_messages"]
            self.assert_thread_owner(thread_id, user_id)

            # 确保索引存在（幂等操作）
            try:
                collection.create_index([("thread_id", 1), ("index", 1)])
            except Exception:
                pass

            # 删除该线程的旧消息
            collection.delete_many({"thread_id": thread_id})

            # 逐条插入，每条消息独立一个文档
            if messages:
                now = datetime.now()
                docs = []
                for i, msg in enumerate(messages):
                    msg = self._truncate_message_fields(msg)
                    docs.append({
                        "thread_id": thread_id,
                        "user_id": user_id,
                        "index": i,
                        "message": msg,
                        "updated_at": now
                    })
                collection.insert_many(docs)
                db["session_owners"].update_one(
                    {"thread_id": thread_id, "user_id": user_id},
                    {"$set": {"updated_at": now}},
                )
                print(f"[AgentLoader] 已保存 {len(docs)} 条展示消息，thread_id={thread_id}")

            return True
        except Exception as e:
            print(f"[AgentLoader] 保存展示消息失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def get_display_messages(
        self, thread_id: str, user_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        从 MongoDB 逐条读取完整的展示消息

        Args:
            thread_id: 会话 ID

        Returns:
            List[Dict] 或 None: 完整的展示消息列表，不存在时返回 None
        """
        if self._mongodb_client is None:
            return None

        try:
            db = self._mongodb_client[MONGODB_DB_NAME]
            collection = db["session_display_messages"]
            self.assert_thread_owner(thread_id, user_id)

            cursor = collection.find({"thread_id": thread_id, "user_id": user_id}).sort("index", 1)
            docs = list(cursor)

            if not docs:
                return None

            messages = [doc["message"] for doc in docs]
            print(f"[AgentLoader] 已读取 {len(messages)} 条展示消息，thread_id={thread_id}")
            return messages
        except Exception as e:
            print(f"[AgentLoader] 读取展示消息失败: {e}")
            import traceback
            traceback.print_exc()
            return None


# 全局单例实例
agent_loader = AgentLoader()
