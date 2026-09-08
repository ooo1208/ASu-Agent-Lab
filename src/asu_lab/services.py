"""Shared durable stores for the web process and the independent worker."""

from functools import lru_cache
from asu_lab.settings import database_path


@lru_cache
def evaluation_store():
    from asu_eval import EvaluationStore
    return EvaluationStore(database_path("evaluation"))


@lru_cache
def evidence_store():
    from asu_finance import EvidenceStore
    return EvidenceStore(database_path("evidence"))


@lru_cache
def task_context_store():
    from asu_lab.context import TaskContextStore
    return TaskContextStore(database_path("context"))
