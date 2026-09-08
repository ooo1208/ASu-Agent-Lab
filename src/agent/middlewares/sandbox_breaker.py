"""
沙箱熔断中间件。

before_model 检查最近消息中的沙箱相关错误，连续失败 ≥ 阈值时
跳转到 end 并注入通知消息，防止无限恢复循环。

与 SandboxHealthMiddleware 配合：
- SandboxHealthMiddleware：主动 ping → 自动恢复
- SandboxCircuitBreakerMiddleware：恢复失败次数超限 → 熔断
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

THRESHOLD = 2

CIRCUIT_BREAKER_MARKER = "SandboxCircuitBreaker"

_SANDBOX_ERROR_KEYWORDS = [
    "SandboxBackendProxy",
    "sandbox",
    "SandboxError",
    "ConnectionError",
    "ConnectionRefusedError",
    "TimeoutError",
    "execute",
    "沙箱",
    "不可达",
    "连接",
    "超时",
]


def _looks_like_sandbox_error(text: str) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in _SANDBOX_ERROR_KEYWORDS)


def _count_consecutive_sandbox_errors(
    messages: Sequence[BaseMessage],
) -> int:
    """从消息列表末尾向前统计连续沙箱错误的 ToolMessage 数量。"""
    count = 0
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            content = getattr(msg, "content", "")
            if isinstance(content, list):
                content = " ".join(
                    b.get("text", "") if isinstance(b, dict) else str(b)
                    for b in content
                )
            status = getattr(msg, "status", None)
            if status == "error" and _looks_like_sandbox_error(str(content)):
                count += 1
                continue
            break
        elif isinstance(msg, AIMessage):
            content = getattr(msg, "content", "")
            text = content if isinstance(content, str) else str(content)
            if CIRCUIT_BREAKER_MARKER in text:
                return 0
        elif getattr(msg, "type", "") in {"human", "system"}:
            break
    return count


class SandboxCircuitBreakerMiddleware(AgentMiddleware):
    """连续沙箱错误超过阈值 → 熔断，跳转到 end。"""

    state_schema = AgentState

    def __init__(self, threshold: int = THRESHOLD) -> None:
        super().__init__()
        self.threshold = threshold

    @hook_config(can_jump_to=["end"])
    def before_model(
        self, state: AgentState, runtime: Runtime,
    ) -> dict[str, Any] | None:
        messages = state.get("messages", [])
        if not messages:
            return None

        count = _count_consecutive_sandbox_errors(messages)
        if count < self.threshold:
            return None

        logger.warning(
            "沙箱熔断: 连续 %d 次沙箱错误超过阈值 %d", count, self.threshold,
        )
        content = (
            f"{CIRCUIT_BREAKER_MARKER}: 连续 {count} 次沙箱操作失败，已触发熔断保护。"
            "请检查沙箱服务状态后重试，或联系管理员。"
        )
        return {"jump_to": "end", "messages": [AIMessage(content=content)]}

    @hook_config(can_jump_to=["end"])
    async def abefore_model(
        self, state: AgentState, runtime: Runtime,
    ) -> dict[str, Any] | None:
        return self.before_model(state, runtime)
