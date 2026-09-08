"""Enqueue a completed snapshot beside the SSE path; never consume its iterator."""

import asyncio
import logging
from typing import Any

from .store import EvaluationStore

logger = logging.getLogger(__name__)


def capture_completed_run(store: EvaluationStore, *, user_id: str, session_id: str, trace_id: str,
                          actual: dict[str, Any], expected: dict[str, Any], version: str,
                          run_id: str | None = None, input_data: Any = None) -> str:
    """Return only after the snapshot is committed; duplicates reuse the same job ID."""
    return store.enqueue(user_id=user_id, session_id=session_id, trace_id=trace_id, actual=actual,
                         expected=expected, version=version, run_id=run_id, input_data=input_data)


async def enqueue_completed_run(store: EvaluationStore, **kwargs: Any) -> str | None:
    """Fail open for the chat path. Enqueue failure is logged, not represented as success.

    Await from a completion hook or an application-owned background task. Starting an
    untracked task and exiting the process can lose a snapshot before it is committed.
    """
    try:
        return await asyncio.to_thread(capture_completed_run, store, **kwargs)
    except Exception as exc:
        logger.warning("evaluation enqueue failed (%s)", type(exc).__name__)
        return None
