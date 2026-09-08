"""
主 Agent 入口模块。

使用 DeepAgents `create_deep_agent` 将所有组件串联为一个可运行的
ERP 采购智能助手。采用 Graph Factory 模式：启动时预计算可复用组件，
每次请求基于 per-user 沙箱轻量创建 agent graph，实现用户级沙箱隔离。

使用方式:
    from agent.graphs.main_agent import precompute_agent_context, create_main_agent

    # 启动时
    precomputed = await precompute_agent_context()

    # 每次请求
    agent_graph = await create_main_agent(
        config,
        sandbox_backend=user_sandbox,
        precomputed=precomputed,
    )
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StoreBackend
from deepagents.backends.protocol import SandboxBackendProtocol
from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)
from langchain_core.runnables import RunnableConfig

from agent.core.config import (
    AGENTS_MD_FILENAME,
    get_checkpointer,
    DOWNLOAD_DIR,
    LOCAL_AGENTS_MD,
    MAIN_MODEL,
    STORE,
    SUMMARY_MODEL,
    user_skills_namespace,
)
from agent.memory.prompts import system_prompt
from agent.middlewares.factories import create_order_middleware
from agent.middlewares.context_injection import ContextInjectionMiddleware
from agent.middlewares.memory_update import MemoryUpdateMiddleware
from agent.middlewares.sandbox_breaker import SandboxCircuitBreakerMiddleware
from agent.middlewares.sandbox_health import SandboxHealthMiddleware
from agent.middlewares.skills_sync import SkillsSyncMiddleware
from agent.middlewares.stage_context import StageContextMiddleware, trusted_task_identity
from agent.middlewares.tools_summarization import build_summarization_middleware
from agent.middlewares.user_async_subagents import create_user_async_subagent_middleware
from agent.middlewares.user_skills_restore import UserSkillsRestoreMiddleware
from agent.core.schema import ProcurementContext
from agent.subagents.loader import load_subagent_configs, resolve_subagent_tools
from agent.tools.assign_skill import create_assign_skill_tool
from agent.tools.chart_generator import create_generate_chart_tool
from agent.tools.download_sandbox_file import create_download_tool
from agent.tools.hitl_tools import request_order_info
from agent.tools.mcp_client import load_mcp_tools
from agent.tools.web_search import web_search
from asu_finance import create_finance_tools
from asu_lab.context import create_milestone_tool
from asu_lab.prompts import load_prompt
from asu_lab.services import evidence_store, task_context_store

ASYNC_ANALYST_GRAPH_ID = "procurement_analyst_async"
ASYNC_ANALYST_URL = os.environ.get(
    "ASYNC_AGENT_PROTOCOL_URL",
    "http://127.0.0.1:2024",
)

ASYNC_ANALYST_INSTRUCTIONS = """
## 异步采购分析任务

当用户提出耗时的采购业务分析、供应商比价、采购行情调研、采购成本评估或采购报告生成任务时，
必须使用 `start_async_task` 启动 `procurement-analyst` 后台任务。

严禁使用同步 `task` 工具启动 `procurement-analyst`。
`task` 工具用于 `procurement-order` 等同步订单任务，以及 `finance-researcher`、`finance-reviewer` 财务研究与独立复核。
财务文档与比率分析交给 finance-researcher 后再交 finance-reviewer，不转给采购异步分析员。

启动任务后必须立即把完整 task_id 返回给用户，并停止本轮回答。
不要立刻调用 `check_async_task`。只有用户明确询问进度、结果、取消或补充要求时，
才调用 `check_async_task`、`list_async_tasks`、
`cancel_async_task` 或 `update_async_task`。
"""


def _setup_logging() -> None:
    env = os.environ.get("APP_ENV", "development")
    if env == "production":
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            filename="erp_agent.log",
            filemode="a",
        )
    else:
        logging.basicConfig(
            level=logging.ERROR,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stdout,
        )

_setup_logging()
logger = logging.getLogger(__name__)


FINANCE_ROLES = {"finance-researcher": "researcher", "finance-reviewer": "reviewer"}


def _versioned_prompt(name: str) -> str:
    text, version = load_prompt(name)
    return f"[ASu prompt {name} {version}]\n{text}"


def _build_finance_subagents(raw_configs, tools, contexts, user_id, thread_id):
    """Resolve exact names from the finance-only pool; no substring/write-tool expansion."""
    configs = {item["name"]: item for item in raw_configs if item.get("name") in FINANCE_ROLES}
    missing = set(FINANCE_ROLES) - set(configs)
    if missing:
        raise ValueError(f"Missing financial subagent configuration: {', '.join(sorted(missing))}")
    tool_index = {item.name: item for item in tools}
    subagents = []
    for name, prompt_name in FINANCE_ROLES.items():
        config = configs[name]
        if config.get("prompt_name") != prompt_name:
            raise ValueError(f"Unexpected versioned prompt for {name}")
        selected = []
        for tool_name in dict.fromkeys(config["tools"]):
            if tool_name not in tool_index:
                raise ValueError(f"{name} requests an unavailable financial tool: {tool_name}")
            selected.append(tool_index[tool_name])
        # Plain DeepAgents SubAgent specs inherit FilesystemMiddleware, including
        # the parent's sandbox execute tool. Compile these read-only roles
        # explicitly so they cannot acquire shell or procurement write tools.
        runnable = create_agent(
            model=MAIN_MODEL,
            system_prompt=_versioned_prompt(prompt_name) + "\n" + config["system_prompt"],
            tools=selected,
            middleware=[StageContextMiddleware(contexts, user_id, thread_id),
                        ModelCallLimitMiddleware(run_limit=20), ToolCallLimitMiddleware(run_limit=60)],
            context_schema=ProcurementContext,
            name=name,
        )
        subagents.append({
            "name": name,
            "description": config["description"].replace("\n", " ").strip(),
            "runnable": runnable,
        })
    return subagents


# ============================================================
# PrecomputedContext — 启动时预计算的可复用组件
# ============================================================

@dataclass
class PrecomputedContext:
    """Phase 2/3/5 预计算结果的不可变容器。

    仅包含不依赖 sandbox_backend 的组件（MCP 工具、图表工具、YAML 配置）。
    sandbox 依赖的工具（assign_skill、download_sandbox_file）和 backend 依赖的
    中间件在 create_main_agent() 中按请求动态创建。
    """
    all_mcp_tools: list = field(default_factory=list)
    analyst_mcp_tools: list = field(default_factory=list)
    order_mcp_tools: list = field(default_factory=list)
    chart_mcp_tools: list = field(default_factory=list)
    extra_mcp_tools: list = field(default_factory=list)
    generate_visualization: object = None
    raw_subagent_configs: list = field(default_factory=list)


async def precompute_agent_context() -> PrecomputedContext:
    """Phase 2/3/5 预计算，启动时执行一次，所有请求复用。"""
    logger.info("=== 预计算 Agent 上下文（Phase 2/3/5）===")

    # Phase 2: MCP 工具加载
    logger.info("Phase 2: 加载 MCP 工具...")
    try:
        all_mcp_tools, analyst_mcp_tools, order_mcp_tools, chart_mcp_tools = (
            await load_mcp_tools()
        )
    except Exception:
        logger.exception("MCP 工具加载失败")
        raise RuntimeError("MCP 工具加载失败，无法预计算")

    # Phase 3: 可视化工具合并
    logger.info("Phase 3: 合并可视化工具 (26→1)...")
    generate_visualization, extra_mcp_tools = create_generate_chart_tool(
        chart_mcp_tools
    )
    if extra_mcp_tools:
        logger.info(f"  保留独立工具: {[t.name for t in extra_mcp_tools]}")

    # Phase 5: 子 Agent YAML 配置加载
    logger.info("Phase 5: 加载子 Agent YAML 配置...")
    raw_configs = load_subagent_configs()
    if not raw_configs:
        logger.warning("  未找到任何子 Agent 配置")
    else:
        logger.info(f"  已加载 {len(raw_configs)} 个子 Agent 配置")

    logger.info("=== 预计算完成 ===")
    return PrecomputedContext(
        all_mcp_tools=all_mcp_tools,
        analyst_mcp_tools=analyst_mcp_tools,
        order_mcp_tools=order_mcp_tools,
        chart_mcp_tools=chart_mcp_tools,
        extra_mcp_tools=extra_mcp_tools,
        generate_visualization=generate_visualization,
        raw_subagent_configs=raw_configs,
    )


# ============================================================
# create_main_agent — 每次请求基于 per-user 沙箱创建 agent graph
# ============================================================

async def create_main_agent(
    config: RunnableConfig,
    *,
    sandbox_backend: SandboxBackendProtocol,
    precomputed: PrecomputedContext,
):
    """创建 ERP 采购智能助手的 per-request graph factory。

    每次请求调用，使用预计算的 MCP 工具/YAML 配置 + 外部传入的 per-user 沙箱，
    轻量创建 agent graph。SandboxBackendProxy 保证沙箱热替换不丢引用。

    Args:
        config: LangGraph RunnableConfig，含 thread_id + user_id。
        sandbox_backend: per-user 沙箱后端（SandboxBackendProxy）。
        precomputed: 启动时预计算的 MCP 工具/YAML 配置。
    """
    user_id, thread_id = trusted_task_identity(config)
    skills_namespace = user_skills_namespace(user_id)
    contexts = task_context_store()
    financial_tools = create_finance_tools(evidence_store(), user_id)
    milestone_tool = create_milestone_tool(contexts, user_id, thread_id)
    logger.info(f"=== 为用户 {user_id} 创建 Agent Graph ===")

    # ---- Phase 1: CompositeBackend factory ----
    # 每次请求重建 CompositeBackend（StoreBackend 依赖 runtime），
    # 内部 sandbox_backend 是 SandboxBackendProxy（热替换不丢引用）。
    def backend_factory(runtime):
        return CompositeBackend(
            default=sandbox_backend,
            routes={
                "/memories/": StoreBackend(  # langgraph 框架的store来存数据
                    runtime=runtime,
                    namespace=lambda rt: (user_id,),
                ),
                "/persisted-skills/": StoreBackend(
                    runtime=runtime,
                    namespace=lambda rt: skills_namespace,
                ),
            },
        )

    # ---- Phase 1.4: 上传 AGENTS.md 到沙箱 ----
    logger.info("Phase 1.4: 上传 AGENTS.md 到沙箱...")
    ag_md_content = LOCAL_AGENTS_MD.read_text(encoding="utf-8")
    sandbox_backend.upload_files([("/AGENTS.md", ag_md_content.encode("utf-8"))])

    # ---- Phase 2/3/5: 使用预计算结果 ----
    logger.info("Phase 2-5: 使用预计算的 MCP 工具 + 图表工具 + YAML 配置...")
    generate_visualization = precomputed.generate_visualization
    extra_mcp_tools = precomputed.extra_mcp_tools

    # ---- Phase 3.6: 创建 sandbox 依赖工具（per-request）----
    logger.info("Phase 3.6: 创建 sandbox 依赖工具...")
    assign_skill = create_assign_skill_tool(
        sandbox_backend,
        store=STORE,
        skills_namespace=skills_namespace,
    )
    download_sandbox_file = create_download_tool(sandbox_backend, DOWNLOAD_DIR)

    # ---- Phase 4: 构建工具池 ----
    logger.info("Phase 4: 构建工具池...")
    available_tools = (
        list(precomputed.analyst_mcp_tools)
        + list(precomputed.order_mcp_tools)
        + list(extra_mcp_tools)
        + [generate_visualization]
        + [web_search]
        + [request_order_info]
        + [assign_skill]
        + [download_sandbox_file]
    )
    logger.info(f"  工具池: {len(available_tools)} 个工具")

    # ---- Phase 6: 子 Agent 中间件（analyst 依赖 backend_factory）----
    logger.info("Phase 6: 创建子 Agent 中间件...")
    extra_middleware = {
        "procurement-order": create_order_middleware(),
    }

    # ---- Phase 7: 子 Agent 工具解析 ----
    logger.info("Phase 7: 解析子 Agent 工具名称...")
    sync_subagent_configs = [
        c for c in precomputed.raw_subagent_configs
        if c.get("name") != "procurement-analyst" and c.get("name") not in FINANCE_ROLES
    ]
    sync_subagents = resolve_subagent_tools(
        sync_subagent_configs,
        available_tools,
        extra_middleware=extra_middleware,
    )
    subagents = sync_subagents + _build_finance_subagents(
        precomputed.raw_subagent_configs, financial_tools, contexts, user_id, thread_id,
    )
    logger.info(f"  已解析 {len(subagents)} 个子 Agent")

    # ---- Phase 8: 主 Agent 中间件栈 ----
    logger.info("Phase 8: 构建主 Agent 中间件栈...")
    main_middleware = [
        # Refresh durable constraints/milestones for every actual model request.
        StageContextMiddleware(contexts, user_id, thread_id),
        # 1. 沙箱健康守护：每次 agent step 前 ping → 失败自动恢复
        SandboxHealthMiddleware(
            sandbox_backend=sandbox_backend,
            user_id=user_id,
            agents_md_content=ag_md_content.encode("utf-8"),
        ),
        # 2. 用户上下文注入
        ContextInjectionMiddleware(),
        # 3. 技能同步（本地 → 沙箱）
        SkillsSyncMiddleware(sandbox_backend),
        # 4. 持久化技能恢复（StoreBackend → 沙箱）
        UserSkillsRestoreMiddleware(sandbox_backend, skills_namespace),
        # 5. 对话摘要 + compact_conversation 工具
        build_summarization_middleware(backend_factory, SUMMARY_MODEL),
        # 6. 用户记忆更新
        MemoryUpdateMiddleware(model=SUMMARY_MODEL),
        # 7. 沙箱熔断：连续沙箱错误 ≥ 阈值 → jump_to=end
        SandboxCircuitBreakerMiddleware(),
        # 8. 异步分析任务：由后端签名并绑定当前用户私有沙箱
        create_user_async_subagent_middleware(
            user_id=user_id,
            sandbox_backend=sandbox_backend,
            url=ASYNC_ANALYST_URL,
            graph_id=ASYNC_ANALYST_GRAPH_ID,
        ),
        # 10. 调用限制
        ModelCallLimitMiddleware(run_limit=50),
        # 11. 工具调用限制
        ToolCallLimitMiddleware(run_limit=200),
    ]

    # ---- Phase 9: create_deep_agent ----
    logger.info("Phase 9: 创建 Deep Agent...")
    agent_graph = create_deep_agent(
        model=MAIN_MODEL,
        system_prompt=system_prompt + "\n\n" + ASYNC_ANALYST_INSTRUCTIONS + "\n\n" + _versioned_prompt("main"),
        skills=["/skills/main/"],
        memory=[AGENTS_MD_FILENAME],
        tools=[web_search, assign_skill, download_sandbox_file, milestone_tool],
        subagents=subagents,
        middleware=main_middleware,
        backend=backend_factory,
        store=STORE,
        checkpointer=get_checkpointer(),
        context_schema=ProcurementContext,
    )

    logger.info(f"=== 用户 {user_id} Agent Graph 创建完成 ===")
    return agent_graph
