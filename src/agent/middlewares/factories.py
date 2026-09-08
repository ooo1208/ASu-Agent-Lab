"""
子 Agent 中间件配置。

提供标准中间件的工厂函数，在创建 Agent 时注入。
"""

from deepagents.middleware.summarization import (
    create_summarization_tool_middleware,
)
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)


def create_analyst_middleware(model, backend) -> list:
    """
    为 procurement-analyst 子 Agent 创建中间件列表。

    包含:
    - SummarizationToolMiddleware: 阶段完成后主动压缩上下文
    - ModelCallLimitMiddleware: 防止无限循环（最多 50 次模型调用）
    - ToolCallLimitMiddleware: 防止工具调用爆炸（最多 200 次）

    Args:
        model: 用于摘要生成的模型（建议用小模型如 deepseek-v4-flash）
        backend: 文件系统后端（用于摘要持久化）

    Returns:
        中间件实例列表
    """
    return [
        create_summarization_tool_middleware(model, backend),
        ModelCallLimitMiddleware(run_limit=50),
        ToolCallLimitMiddleware(run_limit=200),
    ]


def create_order_middleware() -> list:
    """
    为 procurement-order 子 Agent 创建中间件列表。

    订单操作通常是简单 API 调用，不需要摘要工具，
    只需调用限制防止异常循环。

    Returns:
        中间件实例列表
    """
    return [
        ModelCallLimitMiddleware(run_limit=20),
        ToolCallLimitMiddleware(run_limit=50),
    ]
