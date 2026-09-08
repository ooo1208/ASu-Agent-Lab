"""
运行时上下文注入中间件。

从 runtime.context（ProcurementContext）中提取 user_id / username，
在 Agent 启动时以 SystemMessage 形式注入到对话中。Agent 无需调用工具
即可知道当前用户身份，从而正确读写 /memories/{user_id}/preferences.md。

使用方式:
    from agent.middlewares.context_injection import ContextInjectionMiddleware
    middleware = ContextInjectionMiddleware()
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage

logger = logging.getLogger(__name__)


class ContextInjectionMiddleware(AgentMiddleware):
    """将 runtime.context 中的 user_id/username 注入到对话开头。"""

    def before_agent(
        self, state: Dict[str, Any], runtime: Any
    ) -> Optional[Dict[str, Any]]:
        """同步版本：注入用户上下文 SystemMessage。"""
        ctx = getattr(runtime, "context", None)
        if ctx is None:
            logger.warning("ContextInjectionMiddleware: runtime.context 为 None，跳过上下文注入")
            return None
        user_id = getattr(ctx, "user_id", None)
        if not user_id:
            logger.warning("ContextInjectionMiddleware: runtime.context 中没有 user_id，跳过上下文注入")
            return None
        username = getattr(ctx, "username", None) or user_id

        logger.info(f"ContextInjectionMiddleware: 注入用户上下文 user_id={user_id}, username={username}")

        notice = (
            f"【系统上下文】\n"
            f"当前用户 user_id: {user_id}\n"
            f"当前用户 username: {username}\n"
            f"用户偏好文件路径: /memories/{user_id}/preferences.md\n"
            f"\n请首先使用 read_file 读取上述偏好文件了解用户偏好。"
            f"\n（recent_suppliers 和 recent_queries 由系统自动维护，你无需手动更新）"
        )
        return {"messages": [SystemMessage(content=notice)]}

    async def abefore_agent(
        self, state: Dict[str, Any], runtime: Any
    ) -> Optional[Dict[str, Any]]:
        """异步版本：注入用户上下文 SystemMessage。"""
        # 与同步版本逻辑相同
        return self.before_agent(state, runtime)
