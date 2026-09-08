"""Regression tests for signed async-task sandbox bindings."""

import pytest

from agent.backends.sandbox_proxy import SandboxBackendProxy
from agent.core.async_sandbox_claims import (
    create_async_sandbox_claim,
    decode_async_sandbox_claim,
)
from agent.middlewares.user_async_subagents import (
    create_user_async_subagent_middleware,
)


class _Backend:
    def __init__(self, sandbox_id: str):
        self.id = sandbox_id


def test_async_sandbox_claim_round_trip():
    """A valid task receives its original private-sandbox identity."""
    token = create_async_sandbox_claim(
        user_id="user-1",
        sandbox_id="sandbox-1",
        task_id="task-1",
    )
    assert decode_async_sandbox_claim(token, task_id="task-1") == (
        "user-1",
        "sandbox-1",
    )


def test_async_sandbox_claim_rejects_other_task():
    """A signed claim cannot be replayed for a different async task."""
    token = create_async_sandbox_claim(
        user_id="user-1",
        sandbox_id="sandbox-1",
        task_id="task-1",
    )
    with pytest.raises(ValueError, match="does not match"):
        decode_async_sandbox_claim(token, task_id="task-2")


def test_user_async_middleware_exposes_complete_toolset():
    """Replacing start/update keeps all standard async controls available."""
    middleware = create_user_async_subagent_middleware(
        user_id="user-1",
        sandbox_backend=SandboxBackendProxy(_Backend("sandbox-1")),
        url="http://127.0.0.1:2024",
        graph_id="procurement_analyst_async",
    )
    assert {tool.name for tool in middleware.tools} == {
        "start_async_task",
        "check_async_task",
        "update_async_task",
        "cancel_async_task",
        "list_async_tasks",
    }


def test_start_async_task_uses_hot_swapped_sandbox(monkeypatch):
    """A run created after recovery binds to the proxy's replacement sandbox."""
    import agent.middlewares.user_async_subagents as module

    captured = {}

    class _Threads:
        def create(self, **kwargs):
            return {"thread_id": "task-1"}

    class _Runs:
        def create(self, **kwargs):
            captured["run"] = kwargs
            return {"run_id": "run-1"}

    class _Client:
        threads = _Threads()
        runs = _Runs()

    class _AsyncClient:
        pass

    saved = []
    monkeypatch.setattr(module, "get_sync_client", lambda **kwargs: _Client())
    monkeypatch.setattr(module, "get_client", lambda **kwargs: _AsyncClient())
    monkeypatch.setattr(module, "save_task", lambda task: saved.append(task))

    proxy = SandboxBackendProxy(_Backend("sandbox-old"))
    middleware = create_user_async_subagent_middleware(
        user_id="user-1",
        sandbox_backend=proxy,
        url="http://127.0.0.1:2024",
        graph_id="procurement_analyst_async",
    )
    proxy.replace_backend(_Backend("sandbox-new"))

    start_tool = next(tool for tool in middleware.tools if tool.name == "start_async_task")
    runtime = type("Runtime", (), {"tool_call_id": "tool-call-1"})()
    start_tool.func("analyze inventory", "procurement-analyst", runtime)

    run = captured["run"]
    claim = run["config"]["configurable"]["sandbox_claim"]
    assert decode_async_sandbox_claim(claim, task_id="task-1") == (
        "user-1",
        "sandbox-new",
    )
    assert run["metadata"]["sandbox_id"] == "sandbox-new"
    assert saved[0]["sandbox_id"] == "sandbox-new"
