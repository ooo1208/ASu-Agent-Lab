"""MongoDB-backed implementation of LangGraph's BaseStore interface."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Iterable

from langgraph.store.base import (
    BaseStore,
    GetOp,
    Item,
    ListNamespacesOp,
    Op,
    PutOp,
    SearchItem,
    SearchOp,
)
from pymongo import ASCENDING, MongoClient


class MongoDBStore(BaseStore):
    """A simple durable key-value Store backed by a MongoDB collection.

    This store intentionally implements exact/filter search only. The current
    agent uses namespace lookup and key-value reads, not semantic search.
    """

    supports_ttl = False

    def __init__(
        self,
        client: MongoClient,
        db_name: str,
        collection_name: str = "store_items",
    ) -> None:
        self.client = client
        self.collection = client[db_name][collection_name]
        self._indexes_initialized = False
        self._index_lock = Lock()

    @staticmethod
    def _namespace_path(namespace: tuple[str, ...] | list[str]) -> str:
        """Encode a namespace as one scalar value suitable for a unique index.

        MongoDB compound indexes over an array namespace are multikey indexes:
        namespaces such as ("users", "A", "skills") and
        ("users", "B", "skills") collide on their shared array elements when
        the document key is equal. A canonical JSON scalar preserves the full
        namespace identity without delimiter ambiguity.
        """
        return json.dumps(list(namespace), ensure_ascii=False, separators=(",", ":"))

    def _ensure_indexes(self) -> None:
        """Migrate legacy multikey identity and create the scalar unique index."""
        if self._indexes_initialized:
            return
        with self._index_lock:
            if self._indexes_initialized:
                return

            # Backfill documents created before namespace_path was introduced.
            for document in self.collection.find(
                {"namespace_path": {"$exists": False}}, {"namespace": 1}
            ):
                self.collection.update_one(
                    {"_id": document["_id"]},
                    {"$set": {
                        "namespace_path": self._namespace_path(document["namespace"]),
                    }},
                )

            indexes = self.collection.index_information()
            if "namespace_key_unique" in indexes:
                self.collection.drop_index("namespace_key_unique")
            self.collection.create_index(
                [("namespace_path", ASCENDING), ("key", ASCENDING)],
                unique=True,
                name="namespace_path_key_unique",
            )
            self._indexes_initialized = True

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _item(document: dict[str, Any]) -> Item:
        return Item(
            namespace=tuple(document["namespace"]),
            key=document["key"],
            value=document["value"],
            created_at=document["created_at"],
            updated_at=document["updated_at"],
        )

    @staticmethod
    def _matches_prefix(namespace: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
        return namespace[: len(prefix)] == prefix

    def _get(self, op: GetOp) -> Item | None:
        self._ensure_indexes()
        document = self.collection.find_one(
            {"namespace_path": self._namespace_path(op.namespace), "key": op.key}
        )
        return self._item(document) if document else None

    def _put(self, op: PutOp) -> None:
        self._ensure_indexes()
        identity = {
            "namespace_path": self._namespace_path(op.namespace),
            "key": op.key,
        }
        if op.value is None:
            self.collection.delete_one(identity)
            return

        now = self._now()
        self.collection.update_one(
            identity,
            {
                "$set": {
                    "namespace": list(op.namespace),
                    "value": op.value,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    def _search(self, op: SearchOp) -> list[SearchItem]:
        self._ensure_indexes()
        documents = self.collection.find().sort("updated_at", -1)
        results: list[SearchItem] = []
        for document in documents:
            namespace = tuple(document["namespace"])
            if not self._matches_prefix(namespace, op.namespace_prefix):
                continue
            if op.filter and any(
                document["value"].get(key) != expected
                for key, expected in op.filter.items()
            ):
                continue
            # Semantic search is not configured; query is intentionally ignored.
            results.append(
                SearchItem(
                    namespace=namespace,
                    key=document["key"],
                    value=document["value"],
                    created_at=document["created_at"],
                    updated_at=document["updated_at"],
                )
            )
        return results[op.offset : op.offset + op.limit]

    def _list_namespaces(self, op: ListNamespacesOp) -> list[tuple[str, ...]]:
        self._ensure_indexes()
        namespaces = {
            tuple(namespace)
            for namespace in self.collection.distinct("namespace")
        }
        for condition in op.match_conditions or ():
            path = tuple(condition.path)
            if condition.match_type == "prefix":
                namespaces = {
                    namespace
                    for namespace in namespaces
                    if self._matches_prefix(namespace, path)
                }
            elif condition.match_type == "suffix":
                namespaces = {
                    namespace
                    for namespace in namespaces
                    if namespace[-len(path) :] == path
                }

        if op.max_depth is not None:
            namespaces = {
                namespace[: op.max_depth]
                for namespace in namespaces
            }
        return sorted(namespaces)[op.offset : op.offset + op.limit]

    def batch(self, ops: Iterable[Op]) -> list[Any]:
        results: list[Any] = []
        for op in ops:
            if isinstance(op, GetOp):
                results.append(self._get(op))
            elif isinstance(op, PutOp):
                self._put(op)
                results.append(None)
            elif isinstance(op, SearchOp):
                results.append(self._search(op))
            elif isinstance(op, ListNamespacesOp):
                results.append(self._list_namespaces(op))
            else:
                raise NotImplementedError(
                    f"Unsupported Store operation: {type(op).__name__}"
                )
        return results

    async def abatch(self, ops: Iterable[Op]) -> list[Any]:
        return await asyncio.to_thread(self.batch, list(ops))
