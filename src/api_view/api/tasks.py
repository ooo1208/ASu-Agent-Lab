"""User-facing asynchronous task status API."""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query

from agent.stores.async_task_store import find_legacy_task_ids, list_tasks, save_task, update_task
from api_view.auth_service import AuthenticatedUser, get_current_user


router = APIRouter()
ASYNC_AGENT_URL = os.getenv("ASYNC_AGENT_PROTOCOL_URL", "http://127.0.0.1:2024").rstrip("/")


def _message_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        return "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in message)
    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(message or "")


async def _refresh_task(task: dict[str, Any]) -> dict[str, Any]:
    result = {**task}
    task_id = task["task_id"]
    run_id = task.get("run_id")
    if task.get("status") in {"success", "error", "cancelled", "timeout", "interrupted"} and task.get("result"):
        return result
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if not run_id:
                runs_response = await client.get(f"{ASYNC_AGENT_URL}/threads/{task_id}/runs")
                runs_response.raise_for_status()
                runs_payload = runs_response.json()
                run = runs_payload[0] if isinstance(runs_payload, list) else runs_payload
                run_id = run.get("run_id")
                result["run_id"] = run_id
            if not run_id:
                return result
            response = await client.get(f"{ASYNC_AGENT_URL}/threads/{task_id}/runs/{run_id}")
            response.raise_for_status()
            run = response.json()
            status = run.get("status", task.get("status", "running"))
            result["status"] = status
            if status == "success":
                thread_response = await client.get(f"{ASYNC_AGENT_URL}/threads/{task_id}")
                thread_response.raise_for_status()
                messages = (thread_response.json().get("values") or {}).get("messages") or []
                if messages:
                    result["result"] = _message_text(messages[-1].get("content"))
            elif status == "error":
                result["error"] = str(run.get("error") or "异步任务执行失败")
            update_task(task_id, task["user_id"], status=status, result=result.get("result"), error=result.get("error"))
    except Exception as exc:
        result["status_error"] = str(exc)
    return result


@router.get("/tasks")
async def get_tasks(
    limit: int = Query(50, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
):
    tasks = list_tasks(user.user_id, limit)
    known_ids = {task["task_id"] for task in tasks}
    for task_id in find_legacy_task_ids(user.user_id):
        if task_id not in known_ids:
            legacy = {
                "task_id": task_id,
                "user_id": user.user_id,
                "agent_name": "procurement-analyst",
                "status": "running",
            }
            save_task(legacy)
            tasks.append(legacy)
    tasks = sorted(tasks, key=lambda task: str(task.get("created_at", "")), reverse=True)[:limit]
    return {"tasks": [await _refresh_task(task) for task in tasks]}
