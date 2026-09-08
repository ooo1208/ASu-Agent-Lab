"""Offline regression through the actual live chat serializer and registered SSE observer."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessageChunk, ToolMessage

from asu_lab import services
from asu_lab.observability import observe_sse


class OnePassAgentStream:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.iterations = 0
        self.delivered = 0

    def __aiter__(self):
        self.iterations += 1
        assert self.iterations == 1, "The real chat/observation chain consumed the agent stream twice"
        return self

    async def __anext__(self):
        try:
            chunk = next(self.chunks)
        except StopIteration:
            raise StopAsyncIteration
        self.delivered += 1
        return chunk


def tool_chunk(call_id, name, arguments, index, *, message_id="model-turn-1"):
    return AIMessageChunk(content="", id=message_id,
                          tool_call_chunks=[{"id": call_id, "name": name, "args": arguments, "index": index}])


def message_event(token, namespace=()):
    return {"type": "messages", "data": (token, {"tags": []}), "ns": namespace}


@pytest.mark.asyncio
@pytest.mark.parametrize("continuation_ids", [True, False], ids=["provider-id", "message-index-fallback"])
async def test_real_live_chat_preserves_parallel_ids_args_results_and_observes_once(lab_client, monkeypatch, tmp_path, continuation_ids):
    # Import the actual production router; no graph, model, MongoDB or sandbox is initialized.
    from api_view.api import chat
    from api_view.auth_service import AuthenticatedUser
    from agent.core.schema import ChatRequest

    assert chat.observe_sse is observe_sse, "The live router must register the real observation adapter"
    events = [
        message_event(tool_chunk("provider-A", "part_search", '{"name":"陶瓷', 0)),
        message_event(tool_chunk("provider-B", "order_create", '{"order_detail":[{"partId":3,', 1)),
        message_event(tool_chunk("provider-A" if continuation_ids else None, None, '刹车片"}', 0)),
        message_event(tool_chunk("provider-B" if continuation_ids else None, None, '"quantity":2,"unitPrice":"89.90"}]}', 1)),
        # A finishes while B is still open. A LIFO pop would attach A's result to B.
        message_event(ToolMessage(content='[{"id":1,"name":"陶瓷刹车片","price":"38.50"}]', tool_call_id="provider-A", name="part_search")),
        message_event(ToolMessage(content='{"error":"synthetic write denied"}', tool_call_id="provider-B", name="order_create", status="error")),
        message_event(AIMessageChunk(content="已查到合成零件，写入被拒绝。", id="model-final")),
    ]
    source = OnePassAgentStream(events)
    calls, saved, encoded = [], [], []

    class OfflineAgent:
        def astream(self, **kwargs):
            calls.append(kwargs)
            assert len(calls) == 1, "The graph must only run once"
            return source

    async def get_agent(user_id, config):
        return OfflineAgent()

    async def get_display(thread_id, user_id):
        return []

    async def save_display(thread_id, rows, user_id):
        saved.append((thread_id, deepcopy(rows), user_id))

    claims = []
    loader = SimpleNamespace(
        claim_thread=lambda thread_id, user_id: claims.append((thread_id, user_id)),
        create_config=lambda thread_id, user_id: {"configurable": {"thread_id": thread_id, "user_id": user_id}},
        get_agent_for_user=get_agent, get_display_messages=get_display, save_display_messages=save_display,
    )
    monkeypatch.setattr(chat, "agent_loader", loader)
    monkeypatch.setattr(chat, "DEBUG_LOG_DIR", str(tmp_path))
    real_encode = chat.create_sse_message

    def capture_sse(data):
        frame = real_encode(data)
        encoded.append(frame)
        return frame

    monkeypatch.setattr(chat, "create_sse_message", capture_sse)
    user_id = "live-correlation-" + str(continuation_ids)
    thread_id = "parallel-live-thread"
    response = await chat.chat_stream(ChatRequest(message="查询并尝试模拟采购", thread_id=thread_id),
                                     current_user=AuthenticatedUser(user_id, "synthetic-user", "合成用户"))
    output = [chunk async for chunk in response.body_iterator]
    assert output == encoded, "The observer must forward the actual SSE bytes unchanged"
    assert source.iterations == 1 and source.delivered == len(events)
    assert len(calls) == 1 and calls[0]["version"] == "v2"
    assert calls[0]["subgraphs"] is True
    assert claims == [(thread_id, user_id)]
    frames = [json.loads(chunk.removeprefix("data: ").strip()) for chunk in output]
    assert not [frame for frame in frames if frame["type"] == "error"]
    assert [frame["tool_call_id"] for frame in frames if frame["type"] == "tool_start"] == ["provider-A", "provider-B"]
    arguments = {"provider-A": "", "provider-B": ""}
    for frame in frames:
        if frame["type"] == "tool_args":
            arguments[frame["tool_call_id"]] += frame["args"]
    assert json.loads(arguments["provider-A"]) == {"name": "陶瓷刹车片"}
    assert json.loads(arguments["provider-B"]) == {"order_detail": [{"partId": 3, "quantity": 2, "unitPrice": "89.90"}]}
    results = {frame["tool_call_id"]: frame for frame in frames if frame["type"] == "tool_result"}
    assert json.loads(results["provider-A"]["text"])[0]["id"] == 1
    assert json.loads(results["provider-B"]["text"])["error"] == "synthetic write denied"
    assert results["provider-B"]["status"] == "error"
    assert [frame["tool_call_id"] for frame in frames if frame["type"] == "tool_end"] == ["provider-A", "provider-B"]
    assert [frame["content"] for frame in frames if frame["type"] == "token"] == ["已查到合成零件，写入被拒绝。"]
    assert len(saved) == 1
    display = {row["id"]: row for row in saved[0][1] if row["role"] == "tool"}
    assert display["provider-A"]["args"] == arguments["provider-A"]
    assert display["provider-B"]["args"] == arguments["provider-B"]
    assert display["provider-A"]["text"] == results["provider-A"]["text"]
    assert display["provider-B"]["text"] == results["provider-B"]["text"]
    jobs = services.evaluation_store().list_jobs(user_id)
    assert len(jobs) == 1, "One source completion must enqueue exactly one evaluation job"
    snapshot = services.evaluation_store().get_job(user_id, jobs[0]["id"])["payload"]["actual"]
    observed = {call["id"]: call for call in snapshot["tool_calls"]}
    assert observed["provider-A"]["arguments"] == json.loads(arguments["provider-A"])
    assert observed["provider-B"]["arguments"] == json.loads(arguments["provider-B"])
    assert observed["provider-A"]["result"] == results["provider-A"]["text"]
    assert observed["provider-B"]["result"] == results["provider-B"]["text"]
    assert observed["provider-A"]["status"] == "success"
    assert observed["provider-B"]["status"] == "error"
    assert snapshot["task_completed"] is True
    assert snapshot["safety"]["side_effect_performed"] is False
