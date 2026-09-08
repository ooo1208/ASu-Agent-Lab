"""Per-user sandbox health check and automatic recovery middleware."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware

from agent.backends.sandbox_proxy import SandboxBackendProxy

logger = logging.getLogger(__name__)


class SandboxHealthMiddleware(AgentMiddleware):
    """Ping one user's sandbox before each agent step and hot-swap on recovery."""

    def __init__(
        self,
        *,
        sandbox_backend: SandboxBackendProxy,
        user_id: str,
        agents_md_content: bytes,
    ) -> None:
        super().__init__()
        self._backend = sandbox_backend
        self._user_id = user_id
        self._agents_md = agents_md_content

    def before_agent(self, state: dict[str, Any], runtime: Any) -> None:
        return None

    async def abefore_agent(self, state: dict[str, Any], runtime: Any) -> None:
        if await self._check():
            return None

        logger.warning(
            "User sandbox is unhealthy; triggering automatic recovery. user_id=%s",
            self._user_id,
        )
        await self._recover()
        return None

    async def _check(self) -> bool:
        try:
            result = await asyncio.to_thread(self._backend.execute, "echo ok")
            return result.exit_code == 0
        except Exception:
            return False

    async def _recover(self) -> None:
        from agent.backends.sandbox_manager import recreate_user_sandbox

        # recreate_user_sandbox() keeps the existing proxy stable whenever one
        # exists, so the graph/backend factory and all sandbox-bound tools keep
        # their references after a replacement.
        recovered = await recreate_user_sandbox(self._user_id)
        if recovered is not self._backend:
            self._backend.replace_backend(recovered)

        await asyncio.to_thread(
            self._backend.upload_files,
            [("/AGENTS.md", self._agents_md)],
        )
        logger.info("User sandbox automatic recovery completed: user_id=%s", self._user_id)
