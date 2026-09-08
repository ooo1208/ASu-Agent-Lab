"""Tap an existing SSE iterator once and enqueue a completed observation snapshot."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid

from asu_eval import enqueue_completed_run
from asu_lab.services import evaluation_store

log = logging.getLogger(__name__)


async def observe_sse(source, *, user_id: str, thread_id: str, input_text: str = "", approved: bool = False):
    started = time.monotonic()
    trace_id = uuid.uuid4().hex
    answer = ""
    tool_calls: list[dict] = []
    completed = False
    interrupted = False
    try:
        async for chunk in source:
            try:
                for line in (chunk.decode() if isinstance(chunk, bytes) else chunk).splitlines():
                    if not line.startswith("data:"):
                        continue
                    item = json.loads(line[5:].strip())
                    kind = item.get("type")
                    if kind == "token":
                        answer = (answer + str(item.get("content", "")))[:32000]
                    elif kind == "tool_start" and len(tool_calls) < 64:
                        tool_calls.append({"id": item.get("tool_call_id"), "name": item.get("tool_name", "unknown"), "arguments": {}, "status": "planned"})
                    elif kind == "tool_args" and tool_calls:
                        call_id = item.get("tool_call_id")
                        call = next((c for c in reversed(tool_calls) if c["id"] == call_id), None) if call_id else tool_calls[-1]
                        if call is None:
                            continue
                        raw = (call.get("arguments_raw", "") + str(item.get("args", "")))[:8000]
                        call["arguments_raw"] = raw
                        try:
                            call["arguments"] = json.loads(raw)
                        except (ValueError, TypeError):
                            pass
                    elif kind == "tool_result" and tool_calls:
                        call_id = item.get("tool_call_id")
                        call = next((c for c in reversed(tool_calls) if c["id"] == call_id), None) if call_id else next((c for c in reversed(tool_calls) if c["status"] == "planned"), None)
                        if call is None:
                            continue
                        result_text = str(item.get("text", ""))[:8000]
                        failed = item.get("status") == "error"
                        try:
                            result_data = json.loads(result_text)
                            failed = failed or (isinstance(result_data, dict) and bool(result_data.get("error")))
                        except (ValueError, TypeError):
                            pass
                        call.update(status="error" if failed else "success", result=result_text)
                    elif kind == "done":
                        completed = True
                    elif kind == "interrupt":
                        interrupted = True
            except (ValueError, TypeError, AttributeError):
                # Observation must never turn a valid upstream stream into a failure.
                log.debug("Unrecognized SSE observation payload")
            yield chunk
    finally:
        try:
            side_effect = any(c["name"] in {"order_create", "order_update"} and c["status"] == "success" for c in tool_calls)
            actual = {
                "answer": answer, "task_completed": completed and not interrupted,
                "tool_calls": tool_calls,
                "safety": {"approved": approved, "side_effect_performed": side_effect},
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
                "observation_scope": "SSE completion snapshot; write status inferred from tool events, not database audit",
            }
            await asyncio.shield(enqueue_completed_run(
                evaluation_store(), user_id=user_id, session_id=thread_id,
                trace_id=trace_id, run_id=trace_id, actual=actual,
                expected={"max_latency_ms": int(os.getenv("ASU_MAX_LATENCY_MS", "900000")), "requires_approval": True},
                version=os.getenv("ASU_RELEASE", "local") + ":" + os.getenv("ASU_PROMPT_RELEASE", "v1"),
                input_data={"message": input_text[:8000]},
            ))
        except Exception:
            log.exception("Could not persist the evaluation snapshot; primary response already delivered")
