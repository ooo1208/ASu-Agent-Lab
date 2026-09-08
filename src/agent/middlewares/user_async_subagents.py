"""User-bound AsyncSubAgent middleware.

DeepAgents' stock async launcher sends only a task description. This wrapper
replaces its start/update tools so Agent Protocol receives a signed binding to
the current user's private sandbox without exposing sandbox selection to the
model or browser.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from deepagents.middleware.async_subagents import (
    AsyncSubAgent,
    AsyncSubAgentMiddleware,
    AsyncTask,
    StartAsyncTaskSchema,
    UpdateAsyncTaskSchema,
    _resolve_tracked_task,
)
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.types import Command
from langgraph_sdk import get_client, get_sync_client

from agent.backends.sandbox_proxy import SandboxBackendProxy
from agent.core.async_sandbox_claims import create_async_sandbox_claim
from agent.stores.async_task_store import save_task

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_config(*, user_id: str, sandbox_id: str, task_id: str) -> dict:
    return {
        "configurable": {
            "task_id": task_id,
            "sandbox_claim": create_async_sandbox_claim(
                user_id=user_id,
                sandbox_id=sandbox_id,
                task_id=task_id,
            ),
        }
    }


def _persist_task(task: AsyncTask, *, user_id: str, sandbox_id: str) -> None:
    save_task({**task, "user_id": user_id, "sandbox_id": sandbox_id})


def create_user_async_subagent_middleware(
    *,
    user_id: str,
    sandbox_backend: SandboxBackendProxy,
    url: str,
    graph_id: str,
) -> AsyncSubAgentMiddleware:
    """Build standard async task tools with user-private sandbox propagation."""
    spec: AsyncSubAgent = {
        "name": "procurement-analyst",
        "description": (
            "耗时采购分析专家。负责供应商比价、物料行情分析、采购策略建议、"
            "市场调研、成本评估和报告生成。后台运行，适合长任务。"
        ),
        "graph_id": graph_id,
        "url": url,
    }
    middleware = AsyncSubAgentMiddleware(async_subagents=[spec])
    sync_client = get_sync_client(url=url, headers={"x-auth-scheme": "langsmith"})
    async_client = get_client(url=url, headers={"x-auth-scheme": "langsmith"})

    def start_async_task(
        description: str,
        subagent_type: str,
        runtime: ToolRuntime,
    ) -> str | Command:
        if subagent_type != spec["name"]:
            return f"Unknown async subagent type: {subagent_type}"
        try:
            thread = sync_client.threads.create(metadata={"user_id": user_id})
            task_id = thread["thread_id"]
            # Resolve once per run so a hot-swapped proxy supplies the current
            # sandbox while claim, metadata, and persistence stay consistent.
            current_sandbox_id = sandbox_backend.id
            run = sync_client.runs.create(
                thread_id=task_id,
                assistant_id=graph_id,
                input={"messages": [{"role": "user", "content": description}]},
                config=_run_config(
                    user_id=user_id,
                    sandbox_id=current_sandbox_id,
                    task_id=task_id,
                ),
                metadata={"user_id": user_id, "sandbox_id": current_sandbox_id},
            )
        except Exception as exc:
            logger.warning("Failed to launch user-bound async task", exc_info=True)
            return f"Failed to launch async subagent: {exc}"

        now = _now()
        task: AsyncTask = {
            "task_id": task_id,
            "agent_name": spec["name"],
            "thread_id": task_id,
            "run_id": run["run_id"],
            "status": "running",
            "created_at": now,
            "last_checked_at": now,
            "last_updated_at": now,
        }
        _persist_task(task, user_id=user_id, sandbox_id=current_sandbox_id)
        return Command(update={
            "messages": [ToolMessage(
                f"Launched async subagent. task_id: {task_id}",
                tool_call_id=runtime.tool_call_id,
            )],
            "async_tasks": {task_id: task},
        })

    async def astart_async_task(
        description: str,
        subagent_type: str,
        runtime: ToolRuntime,
    ) -> str | Command:
        if subagent_type != spec["name"]:
            return f"Unknown async subagent type: {subagent_type}"
        try:
            thread = await async_client.threads.create(metadata={"user_id": user_id})
            task_id = thread["thread_id"]
            current_sandbox_id = sandbox_backend.id
            run = await async_client.runs.create(
                thread_id=task_id,
                assistant_id=graph_id,
                input={"messages": [{"role": "user", "content": description}]},
                config=_run_config(
                    user_id=user_id,
                    sandbox_id=current_sandbox_id,
                    task_id=task_id,
                ),
                metadata={"user_id": user_id, "sandbox_id": current_sandbox_id},
            )
        except Exception as exc:
            logger.warning("Failed to launch user-bound async task", exc_info=True)
            return f"Failed to launch async subagent: {exc}"

        now = _now()
        task: AsyncTask = {
            "task_id": task_id,
            "agent_name": spec["name"],
            "thread_id": task_id,
            "run_id": run["run_id"],
            "status": "running",
            "created_at": now,
            "last_checked_at": now,
            "last_updated_at": now,
        }
        _persist_task(task, user_id=user_id, sandbox_id=current_sandbox_id)
        return Command(update={
            "messages": [ToolMessage(
                f"Launched async subagent. task_id: {task_id}",
                tool_call_id=runtime.tool_call_id,
            )],
            "async_tasks": {task_id: task},
        })

    def update_async_task(
        task_id: str,
        message: str,
        runtime: ToolRuntime,
    ) -> str | Command:
        tracked = _resolve_tracked_task(task_id, runtime)
        if isinstance(tracked, str):
            return tracked
        try:
            current_sandbox_id = sandbox_backend.id
            run = sync_client.runs.create(
                thread_id=tracked["thread_id"],
                assistant_id=graph_id,
                input={"messages": [{"role": "user", "content": message}]},
                config=_run_config(
                    user_id=user_id,
                    sandbox_id=current_sandbox_id,
                    task_id=tracked["task_id"],
                ),
                metadata={"user_id": user_id, "sandbox_id": current_sandbox_id},
                multitask_strategy="interrupt",
            )
        except Exception as exc:
            return f"Failed to update async subagent: {exc}"
        task: AsyncTask = {
            **tracked,
            "run_id": run["run_id"],
            "status": "running",
            "last_updated_at": _now(),
        }
        _persist_task(task, user_id=user_id, sandbox_id=current_sandbox_id)
        return Command(update={
            "messages": [ToolMessage(
                f"Updated async subagent. task_id: {tracked['task_id']}",
                tool_call_id=runtime.tool_call_id,
            )],
            "async_tasks": {tracked["task_id"]: task},
        })

    async def aupdate_async_task(
        task_id: str,
        message: str,
        runtime: ToolRuntime,
    ) -> str | Command:
        tracked = _resolve_tracked_task(task_id, runtime)
        if isinstance(tracked, str):
            return tracked
        try:
            current_sandbox_id = sandbox_backend.id
            run = await async_client.runs.create(
                thread_id=tracked["thread_id"],
                assistant_id=graph_id,
                input={"messages": [{"role": "user", "content": message}]},
                config=_run_config(
                    user_id=user_id,
                    sandbox_id=current_sandbox_id,
                    task_id=tracked["task_id"],
                ),
                metadata={"user_id": user_id, "sandbox_id": current_sandbox_id},
                multitask_strategy="interrupt",
            )
        except Exception as exc:
            return f"Failed to update async subagent: {exc}"
        task: AsyncTask = {
            **tracked,
            "run_id": run["run_id"],
            "status": "running",
            "last_updated_at": _now(),
        }
        _persist_task(task, user_id=user_id, sandbox_id=current_sandbox_id)
        return Command(update={
            "messages": [ToolMessage(
                f"Updated async subagent. task_id: {tracked['task_id']}",
                tool_call_id=runtime.tool_call_id,
            )],
            "async_tasks": {tracked["task_id"]: task},
        })

    replacement_tools = {
        "start_async_task": StructuredTool.from_function(
            name="start_async_task",
            func=start_async_task,
            coroutine=astart_async_task,
            description=next(
                tool.description for tool in middleware.tools
                if tool.name == "start_async_task"
            ),
            infer_schema=False,
            args_schema=StartAsyncTaskSchema,
        ),
        "update_async_task": StructuredTool.from_function(
            name="update_async_task",
            func=update_async_task,
            coroutine=aupdate_async_task,
            description=next(
                tool.description for tool in middleware.tools
                if tool.name == "update_async_task"
            ),
            infer_schema=False,
            args_schema=UpdateAsyncTaskSchema,
        ),
    }
    middleware.tools = [replacement_tools.get(tool.name, tool) for tool in middleware.tools]
    return middleware
