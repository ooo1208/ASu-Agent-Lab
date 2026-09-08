"""Exercise real graph/tool/middleware boundaries with a deterministic local model."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.runtime import Runtime
from langgraph.store.memory import InMemoryStore
from pydantic import Field

from agent.core.schema import ProcurementContext
from agent.middlewares.stage_context import StageContextMiddleware, trusted_task_identity
from asu_finance import EvidenceStore, create_finance_tools
from asu_lab.context import TaskContextStore, create_milestone_tool


class ScriptedModel(BaseChatModel):
    """No transport exists: supplied messages are emitted one at a time."""

    responses: list[AIMessage] = Field(default_factory=list)
    seen: list[list] = Field(default_factory=list)
    bound_names: list[list[str]] = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "asu-local-test"

    def bind_tools(self, tools, **kwargs):
        self.bound_names.append([tool.name if hasattr(tool, "name") else tool.get("name", tool.get("function", {}).get("name")) for tool in tools])
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        if not self.responses:
            raise AssertionError("Unexpected extra model call")
        return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0))])


def tool_request(name, args, call_id="call-1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


@pytest.mark.parametrize("config", [{}, {"configurable": {}}, {"configurable": {"user_id": "a"}},
    {"configurable": {"user_id": " ", "thread_id": "t"}}, {"configurable": {"user_id": "a", "thread_id": None}},
    {"configurable": {"user_id": " a", "thread_id": "t"}}])
def test_identity_is_required_before_binding_tools(config):
    with pytest.raises(ValueError):
        trusted_task_identity(config)


def test_each_model_request_sees_latest_durable_milestone(tmp_path):
    store = TaskContextStore(tmp_path / "context.sqlite3")
    model = ScriptedModel(responses=[
        tool_request("record_task_milestone", {"stage": "validate", "milestone": "收入与期间已核对", "constraints": {"currency": "CNY"}}),
        AIMessage(content="ready for review"),
    ])
    middleware = StageContextMiddleware(store, "alice", "thread-1")
    graph = create_agent(model=model, tools=[create_milestone_tool(store, "alice", "thread-1")],
                         system_prompt="Preserve this role and its permissions.", middleware=[middleware],
                         context_schema=ProcurementContext)
    result = graph.invoke({"messages": [HumanMessage(content="check revenue")]}, context=ProcurementContext("alice", "Alice"))
    assert len(model.seen) == 2
    first_system, second_system = model.seen[0][0].text, model.seen[1][0].text
    assert '"stage": "collect"' in first_system
    assert '"stage": "validate"' in second_system and '"currency": "CNY"' in second_system
    assert second_system.count("持久任务上下文") == 1
    assert "Preserve this role and its permissions." in second_system
    assert all(message.type != "system" for message in result["messages"])
    assert store.get("alice", "thread-1")["stage"] == "validate"
    assert store.get("bob", "thread-1")["stage"] == "collect"
    assert store.get("alice", "other-thread")["stage"] == "collect"


@pytest.mark.asyncio
async def test_async_stage_hook_preserves_message_blocks_and_rejects_rebinding(tmp_path):
    store = TaskContextStore(tmp_path / "context.sqlite3")
    middleware = StageContextMiddleware(store, "alice", "thread-1")
    system = SystemMessage(content=[{"type": "text", "text": "Filesystem rules remain in place."}], name="base-system")
    request = ModelRequest(model=ScriptedModel(), messages=[], system_message=system,
                           runtime=Runtime(context=ProcurementContext("alice", "Alice")))

    async def capture(outgoing):
        return outgoing

    outgoing = await middleware.awrap_model_call(request, capture)
    assert outgoing.system_message.name == "base-system"
    assert outgoing.system_message.content[0] == system.content[0]
    assert len(outgoing.system_message.content) == 2
    assert len(request.system_message.content) == 1
    store.update("alice", "thread-1", "review", milestone="Ready for independent verification")
    next_request = await middleware.awrap_model_call(request, capture)
    assert '"stage": "review"' in next_request.system_message.text
    request = ModelRequest(model=ScriptedModel(), messages=[], system_message=system,
                           runtime=Runtime(context=ProcurementContext("bob", "Bob")))
    with pytest.raises(ValueError, match="identity"):
        await middleware.awrap_model_call(request, capture)


def finance_specs(monkeypatch, tmp_path, model):
    from agent.graphs import main_agent
    from agent.subagents.loader import load_subagent_configs
    evidence = EvidenceStore(tmp_path / "evidence.sqlite3")
    context = TaskContextStore(tmp_path / "context.sqlite3")
    monkeypatch.setattr(main_agent, "MAIN_MODEL", model)
    monkeypatch.setenv("ASU_PROMPT_RELEASE", "v1")
    specs = main_agent._build_finance_subagents(load_subagent_configs(), create_finance_tools(evidence, "alice"), context, "alice", "thread-1")
    return specs, evidence, context


def test_compiled_researcher_executes_owner_scoped_tools_without_sandbox_capabilities(monkeypatch, tmp_path):
    model = ScriptedModel(responses=[tool_request("search_financial_evidence", {"query": "revenue"}), AIMessage(content="research completed")])
    specs, evidence, _ = finance_specs(monkeypatch, tmp_path, model)
    evidence.ingest("alice", "public.txt", "revenue 120")
    evidence.ingest("bob", "secret.txt", "revenue 999 SECRET")
    result = specs[0]["runnable"].invoke({"messages": [HumanMessage(content="research revenue")]}, context=ProcurementContext("alice", "Alice"))
    tools = set(model.bound_names[0])
    assert {"search_financial_evidence", "calculate_financial_metric"} <= tools
    assert not tools & {"execute", "write_file", "task", "order_create", "order_update", "record_task_milestone"}
    tool_output = next(message.content for message in result["messages"] if isinstance(message, ToolMessage))
    assert "120" in tool_output and "SECRET" not in tool_output
    assert "[ASu prompt researcher v1:" in model.seen[0][0].text


def test_reviewer_rechecks_citation_and_cannot_access_another_owner(monkeypatch, tmp_path):
    model = ScriptedModel()
    specs, evidence, _ = finance_specs(monkeypatch, tmp_path, model)
    secret = evidence.ingest("bob", "secret.txt", "SECRET 999")
    model.responses = [tool_request("get_financial_citation", {"citation_id": secret["citation_ids"][0]}), AIMessage(content="evidence unavailable")]
    result = specs[1]["runnable"].invoke({"messages": [HumanMessage(content="verify claim")]}, context=ProcurementContext("alice", "Alice"))
    output = next(message.content for message in result["messages"] if isinstance(message, ToolMessage))
    assert "unavailable" in output and "SECRET" not in output
    assert "review_financial_claim" in model.bound_names[0]
    assert "[ASu prompt reviewer v1:" in model.seen[0][0].text
    with pytest.raises(ValueError, match="identity"):
        specs[1]["runnable"].invoke({"messages": [HumanMessage(content="cross-user reuse")]}, context=ProcurementContext("bob", "Bob"))
    with pytest.raises(ValueError, match="thread identity"):
        specs[1]["runnable"].invoke({"messages": [HumanMessage(content="cross-thread reuse")]},
            config={"configurable": {"user_id": "alice", "thread_id": "other-thread"}}, context=ProcurementContext("alice", "Alice"))


def test_real_deepagents_task_inherits_trusted_context_into_compiled_finance_role(monkeypatch, tmp_path):
    from deepagents import create_deep_agent
    model = ScriptedModel(responses=[
        tool_request("task", {"subagent_type": "finance-researcher", "description": "Find revenue evidence."}),
        tool_request("search_financial_evidence", {"query": "revenue"}, "research-tool"),
        AIMessage(content="Found synthetic revenue evidence."),
        AIMessage(content="Delegation complete."),
    ])
    specs, evidence, contexts = finance_specs(monkeypatch, tmp_path, model)
    evidence.ingest("alice", "a.txt", "revenue 120")
    graph = create_deep_agent(model=model, subagents=specs, middleware=[StageContextMiddleware(contexts, "alice", "thread-1")],
                              context_schema=ProcurementContext)
    result = graph.invoke({"messages": [HumanMessage(content="Analyze revenue.")]}, context=ProcurementContext("alice", "Alice"))
    assert result["messages"][-1].content == "Delegation complete."
    assert len(model.seen) == 4
    assert "[ASu prompt researcher v1:" in model.seen[1][0].text
    assert "execute" not in model.bound_names[1]


@pytest.mark.asyncio
async def test_main_factory_connects_milestones_compiled_roles_and_private_namespaces(monkeypatch, tmp_path):
    from agent.graphs import main_agent
    from agent.subagents.loader import load_subagent_configs
    evidence = EvidenceStore(tmp_path / "evidence.sqlite3")
    contexts = TaskContextStore(tmp_path / "context.sqlite3")
    model = ScriptedModel()
    monkeypatch.setattr(main_agent, "MAIN_MODEL", model)
    monkeypatch.setattr(main_agent, "evidence_store", lambda: evidence)
    monkeypatch.setattr(main_agent, "task_context_store", lambda: contexts)
    monkeypatch.setattr(main_agent, "STORE", InMemoryStore())
    checkpoint = object()
    monkeypatch.setattr(main_agent, "get_checkpointer", lambda: checkpoint)
    monkeypatch.setattr(main_agent, "create_user_async_subagent_middleware", lambda **kwargs: AgentMiddleware())
    # Capture only the final external graph-construction boundary; execute the
    # real factory, tool factories, YAML resolver and financial graph compiler.
    monkeypatch.setattr(main_agent, "create_deep_agent", lambda **kwargs: kwargs)
    sandbox = SimpleNamespace(upload_files=lambda files: None)
    precomputed = main_agent.PrecomputedContext(raw_subagent_configs=load_subagent_configs())
    captured = await main_agent.create_main_agent({"configurable": {"user_id": "alice", "thread_id": "thread-1"}}, sandbox_backend=sandbox, precomputed=precomputed)
    assert captured["checkpointer"] is checkpoint
    assert "[ASu prompt main v1:" in captured["system_prompt"]
    finance = [item for item in captured["subagents"] if item["name"].startswith("finance-")]
    assert {item["name"] for item in finance} == {"finance-researcher", "finance-reviewer"}
    assert all("runnable" in item for item in finance)
    milestones = next(tool for tool in captured["tools"] if tool.name == "record_task_milestone")
    assert "user_id" not in milestones.args and "thread_id" not in milestones.args
    milestones.invoke({"stage": "review", "milestone": "complete"})
    assert contexts.get("alice", "thread-1")["stage"] == "review"
    backend = captured["backend"](None)
    assert backend.routes["/memories/"]._get_namespace() == ("alice",)
    assert backend.routes["/persisted-skills/"]._get_namespace() == ("users", "alice", "skills")
    order = next(item for item in captured["subagents"] if item["name"] == "procurement-order")
    assert order["interrupt_on"]["order_create"]["allowed_decisions"] == ["approve", "reject"]


def test_financial_yaml_cannot_expand_to_unknown_or_write_tools(monkeypatch, tmp_path):
    from agent.graphs import main_agent
    from agent.subagents.loader import load_subagent_configs
    configs = load_subagent_configs()
    next(item for item in configs if item["name"] == "finance-reviewer")["tools"].append("order_update")
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    monkeypatch.setattr(main_agent, "MAIN_MODEL", ScriptedModel())
    with pytest.raises(ValueError, match="unavailable financial tool"):
        main_agent._build_finance_subagents(configs, create_finance_tools(store, "alice"), TaskContextStore(tmp_path / "context.sqlite3"), "alice", "thread-1")
