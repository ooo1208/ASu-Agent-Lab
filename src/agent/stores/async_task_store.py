"""Persistent user-scoped metadata for asynchronous subagent tasks."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import re
from threading import Lock
from typing import Any

from pymongo import ASCENDING, MongoClient

from api_view.web_config import MONGODB_DB_NAME, MONGODB_URI


TASK_COLLECTION = "async_tasks"
_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000, connect=False)
_collection = _client[MONGODB_DB_NAME][TASK_COLLECTION]
_indexes_ready = False
_index_lock = Lock()


def _ensure_indexes():
    global _indexes_ready
    if not _indexes_ready:
        with _index_lock:
            if not _indexes_ready:
                _collection.create_index([("user_id", ASCENDING), ("created_at", -1)])
                _collection.create_index("task_id", unique=True)
                _indexes_ready = True


def _now() -> datetime:
    return datetime.now(UTC)


def save_task(task: dict[str, Any]) -> None:
    _ensure_indexes()
    now = _now()
    document = {**task, "created_at": task.get("created_at", now), "updated_at": now}
    _collection.update_one(
        {"task_id": document["task_id"], "user_id": document["user_id"]},
        {"$set": document},
        upsert=True,
    )


def update_task(task_id: str, user_id: str, **fields: Any) -> None:
    fields["updated_at"] = _now()
    _collection.update_one({"task_id": task_id, "user_id": user_id}, {"$set": fields})


def list_tasks(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = _collection.find({"user_id": user_id}).sort("created_at", -1).limit(limit)
    return [{key: value for key, value in row.items() if key != "_id"} for row in rows]


def find_legacy_task_ids(user_id: str, limit: int = 100) -> list[str]:
    """Find task IDs created before async_tasks persistence was introduced."""
    messages = _client[MONGODB_DB_NAME]["session_display_messages"].find(
        {"user_id": user_id}, {"message": 1}
    ).sort("updated_at", -1).limit(limit)
    pattern = re.compile(
        r"(?:task_id|任务\s*ID)[\"'`\s]*[:：]?[\"'`\s]*"
        r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        re.IGNORECASE,
    )
    found: list[str] = []
    for row in messages:
        text = json.dumps(row.get("message", {}), ensure_ascii=False, default=str)
        for task_id in pattern.findall(text):
            if task_id not in found:
                found.append(task_id)
    return found
