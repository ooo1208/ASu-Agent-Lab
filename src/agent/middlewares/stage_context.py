"""Refresh durable milestones on every model request without mutating chat history."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.config import get_config

from asu_lab.context import TaskContextStore


def trusted_task_identity(config: Mapping) -> tuple[str, str]:
    """Require explicit authenticated ownership before constructing any user-bound tools."""
    configurable = config.get("configurable")
    if not isinstance(configurable, Mapping):
        raise ValueError("Agent config requires authenticated user_id and thread_id.")
    values = []
    for key in ("user_id", "thread_id"):
        value = configurable.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise ValueError(f"Agent config requires a non-empty {key} of at most 256 characters.")
        if value != value.strip():
            raise ValueError(f"Agent {key} must not contain leading or trailing whitespace.")
        values.append(value)
    return values[0], values[1]


class StageContextMiddleware(AgentMiddleware):
    """One instance per authenticated graph; shares owner/thread with the milestone tool.

    The dynamic context is added only to the outgoing model request, preserving
    DeepAgents' filesystem/skills instructions and leaving checkpoint messages intact.
    """

    def __init__(self, store: TaskContextStore, user_id: str, thread_id: str):
        self.user_id, self.thread_id = trusted_task_identity({"configurable": {"user_id": user_id, "thread_id": thread_id}})
        self.store = store

    def _validate_runtime(self, runtime) -> None:
        context = getattr(runtime, "context", None)
        actual_user = context.get("user_id") if isinstance(context, Mapping) else getattr(context, "user_id", None)
        if actual_user != self.user_id:
            raise ValueError("Runtime user identity does not match this request-bound Agent graph.")
        # A compiled graph must not be reused for another conversation. Nested
        # DeepAgents retain the parent's thread id through LangGraph config.
        try:
            configurable = get_config().get("configurable", {})
        except RuntimeError:
            configurable = {}
        if configurable.get("thread_id") is not None and configurable["thread_id"] != self.thread_id:
            raise ValueError("Runtime thread identity does not match this request-bound Agent graph.")
        if configurable.get("user_id") is not None and configurable["user_id"] != self.user_id:
            raise ValueError("Runtime user identity does not match this request-bound Agent graph.")

    def before_agent(self, state, runtime):
        self._validate_runtime(runtime)
        return None

    async def abefore_agent(self, state, runtime):
        return self.before_agent(state, runtime)

    @staticmethod
    def _with_context(request, context_text: str):
        existing = request.system_message
        if existing is None:
            message = SystemMessage(content=context_text)
        elif isinstance(existing.content, str):
            message = existing.model_copy(update={"content": existing.content + "\n\n" + context_text})
        else:
            message = existing.model_copy(update={"content": [*existing.content, {"type": "text", "text": context_text}]})
        return request.override(system_message=message)

    def wrap_model_call(self, request, handler):
        self._validate_runtime(request.runtime)
        context_text = self.store.prompt(self.user_id, self.thread_id)
        return handler(self._with_context(request, context_text))

    async def awrap_model_call(self, request, handler):
        self._validate_runtime(request.runtime)
        context_text = await asyncio.to_thread(self.store.prompt, self.user_id, self.thread_id)
        return await handler(self._with_context(request, context_text))
