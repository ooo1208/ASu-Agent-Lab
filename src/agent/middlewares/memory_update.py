"""
自动记忆更新中间件。

在每轮 Agent 回复完成后（aafter_agent 钩子），自动提取对话中涉及的
供应商名称和查询摘要，更新 StoreBackend 中的用户偏好文件。

Agent 无需手动维护 recent_suppliers / recent_queries —— 系统自动处理。

使用方式:
    from agent.middlewares.memory_update import MemoryUpdateMiddleware
    middleware = MemoryUpdateMiddleware(model=SUMMARY_MODEL)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)

# 触发自动更新的 ERP 业务关键词（中文）
_TRIGGER_KEYWORDS = [
    "供应商", "物料", "采购", "订单", "价格", "分析", "对比",
    "比价", "报价", "评估", "筛选", "推荐", "行情", "预算",
    "库存", "交货", "交期", "质量", "成本", "报价", "招标",
    "supplier", "part", "order", "price", "analysis",
]

# 跳过更新的无意义消息模式
_SKIP_PATTERNS = [
    "你好", "在吗", "嗨", "hello", "hi", "hey",
    "你能做什么", "你有哪些功能", "你是谁",
    "我之前的偏好", "我的偏好", "我的记忆",
]


def _is_meaningful_erp_exchange(messages: List[BaseMessage]) -> Optional[str]:
    """检查最后一条用户消息是否为有意义的 ERP 交互。

    Returns:
        用户消息文本（有意义时），或 None（应跳过）。
    """
    # 从后往前找最后一条用户消息
    last_user_msg = None
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", None)
        if msg_type == "human":
            last_user_msg = msg
            break

    if last_user_msg is None:
        return None

    content = last_user_msg.content
    if isinstance(content, list):
        content = " ".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    content = str(content).strip()

    if not content:
        return None

    # 跳过无意义消息
    content_lower = content.lower().replace(" ", "")
    for pattern in _SKIP_PATTERNS:
        if pattern.lower().replace(" ", "") in content_lower:
            return None

    # 检查是否包含 ERP 关键词
    has_erp_keyword = any(
        kw.lower() in content_lower for kw in _TRIGGER_KEYWORDS
    )
    if not has_erp_keyword:
        # 兜底：检查是否委派了子 Agent（messages 中有 task 工具调用）
        has_subagent_call = False
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.get("name") == "task":
                        has_subagent_call = True
                        break
            if has_subagent_call:
                break
        if not has_subagent_call:
            return None

    return content


def _extract_ai_summary(messages: List[BaseMessage]) -> str:
    """提取最后一条 AI 消息的前 300 字符作为摘要。"""
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "ai":
            content = msg.content
            if isinstance(content, list):
                content = " ".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            return str(content)[:300]
    return ""


async def _extract_entities(
    model: BaseChatModel, user_message: str, ai_summary: str
) -> Dict[str, Any]:
    """使用 LLM 从对话中提取供应商和查询摘要。

    Returns:
        {"suppliers": [...], "query": "..."} 或 {"suppliers": [], "query": ""}
    """
    prompt = f"""Extract procurement-related entities from this conversation.

Rules:
1. "suppliers": Company/supplier names mentioned. Include both Chinese and English names. Empty list if none.
2. "query": One-line summary of the user's procurement need. Empty string if not procurement-related.

User message: {user_message}

Assistant response summary: {ai_summary}

Return ONLY a JSON object, no other text:
{{"suppliers": ["CompanyA", "CompanyB"], "query": "brief summary"}}"""

    try:
        # Tag this helper LLM call so the Web SSE bridge can suppress its tokens.
        # It is internal bookkeeping, not part of the assistant's user response.
        response = await model.ainvoke(
            prompt,
            config={"tags": ["internal-memory-update"]},
        )

        # 从回复中提取 JSON
        text = response.content
        if isinstance(text, list):
            text = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in text
            )
        text = str(text).strip()

        # 提取 JSON 块
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            result = json.loads(text[start:end + 1])
            return {
                "suppliers": result.get("suppliers", []),
                "query": result.get("query", ""),
            }
    except Exception:
        logger.warning("MemoryUpdateMiddleware: LLM 提取失败，跳过本次更新", exc_info=True)

    return {"suppliers": [], "query": ""}


def _create_file_value(content_str: str) -> dict:
    """创建 StoreBackend 兼容的文件值（与 deepagents.backends.utils.create_file_data 一致）。"""
    lines = content_str.split("\n")
    now = datetime.now(timezone.utc).isoformat()
    return {
        "content": lines,
        "created_at": now,
        "modified_at": now,
    }


class MemoryUpdateMiddleware(AgentMiddleware):
    """在 Agent 回复后自动更新用户记忆文件中的 recent_suppliers / recent_queries。

    不依赖 Agent 自觉——中间件自动提取、合并、写回。
    """

    def __init__(self, model: BaseChatModel) -> None:
        super().__init__()
        self.model = model

    # ---- 同步钩子（不执行操作）----
    def after_agent(
        self, state: Dict[str, Any], runtime: Any
    ) -> Optional[Dict[str, Any]]:
        return None

    # ---- 异步钩子（核心逻辑）----
    async def aafter_agent(
        self, state: Dict[str, Any], runtime: Any
    ) -> Optional[Dict[str, Any]]:
        """Agent 回复完成后触发：提取实体并更新记忆。"""
        try:
            # 1. 获取 user_id
            ctx = getattr(runtime, "context", None)
            if ctx is None:
                return None
            user_id = getattr(ctx, "user_id", None)
            if not user_id:
                return None

            # 2. 获取消息列表
            messages: List[BaseMessage] = state.get("messages", [])
            if not messages:
                return None

            # 3. 判断是否需要更新
            user_message = _is_meaningful_erp_exchange(messages)
            if user_message is None:
                return None

            # 4. 提取 AI 摘要
            ai_summary = _extract_ai_summary(messages)

            # 5. LLM 提取实体
            extracted = await _extract_entities(self.model, user_message, ai_summary)
            suppliers = extracted.get("suppliers", [])
            query = extracted.get("query", "")

            if not suppliers and not query:
                return None

            logger.info(
                f"MemoryUpdateMiddleware: user={user_id}, "
                f"suppliers={suppliers}, query={query[:50]}"
            )

            # 6. 从 store 读取当前偏好文件
            store = getattr(runtime, "store", None)
            if store is None:
                logger.warning("MemoryUpdateMiddleware: runtime.store 不可用")
                return None

            namespace = (user_id,)
            key = f"/{user_id}/preferences.md"

            try:
                item = await store.aget(namespace, key)
            except Exception:
                item = None

            # 7. 解析现有内容或创建默认
            current_lines: List[str] = []
            if item is not None and hasattr(item, "value"):
                value = item.value
                if isinstance(value, dict):
                    content = value.get("content", [])
                    if isinstance(content, list):
                        current_lines = [str(line) for line in content]
                    elif isinstance(content, str):
                        current_lines = content.split("\n")
                elif isinstance(value, str):
                    current_lines = value.split("\n")

            updated_content = _merge_preferences(
                current_lines, suppliers, query
            )

            # 8. 写回 store
            file_value = _create_file_value(updated_content)
            await store.aput(namespace, key, file_value)

            logger.info(
                f"MemoryUpdateMiddleware: 已更新 {user_id} 的记忆 "
                f"(suppliers={len(suppliers)}, query={'yes' if query else 'no'})"
            )

        except Exception:
            logger.warning("MemoryUpdateMiddleware: 更新失败", exc_info=True)

        return None


def _merge_preferences(
    current_lines: List[str], new_suppliers: List[str], new_query: str
) -> str:
    """将新的 suppliers/query 合并到现有偏好内容中。

    策略：先移除旧 recent_suppliers / recent_queries 区块，再在末尾追加合并后的版本。
    """
    # 1. 解析旧的 suppliers 和 queries
    existing_suppliers: List[str] = []
    existing_queries: List[str] = []

    def _parse_list_items(lines: List[str], start_idx: int) -> tuple:
        """从 start_idx 行（recent_xxx: 标题行）解析列表项。"""
        items: List[str] = []
        title_line = lines[start_idx].strip()

        # 检查 inline 格式: recent_suppliers: [a, b]
        colon_pos = title_line.find(":")
        if colon_pos != -1:
            inline = title_line[colon_pos + 1:].strip()
            if inline.startswith("[") and inline.endswith("]"):
                inner = inline[1:-1].strip()
                if inner:
                    return [s.strip().strip("'").strip('"') for s in inner.split(",") if s.strip()], 1

        # 多行格式: 从下一行开始收集 - xxx 项
        count = 1
        for j in range(start_idx + 1, len(lines)):
            stripped = lines[j].strip()
            if stripped.startswith("- "):
                items.append(stripped[2:].strip().strip("'").strip('"'))
                count += 1
            elif stripped and not lines[j].startswith(" "):
                break  # 遇到下一个顶级字段
            else:
                count += 1  # 空行或注释，仍属于当前区块
        return items, count

    # 2. 找出旧区块的位置和值
    suppliers_start = -1
    suppliers_len = 0
    queries_start = -1
    queries_len = 0

    for i, line in enumerate(current_lines):
        stripped = line.strip()
        if stripped.startswith("recent_suppliers:"):
            suppliers_start = i
            existing_suppliers, suppliers_len = _parse_list_items(current_lines, i)
        elif stripped.startswith("recent_queries:"):
            queries_start = i
            existing_queries, queries_len = _parse_list_items(current_lines, i)

    # 3. 从原内容中移除旧区块（从后往前移，避免索引偏移）
    clean_lines = list(current_lines)
    # 按起始位置降序排列，从后往前删除
    removals = []
    if suppliers_start >= 0:
        removals.append((suppliers_start, suppliers_len))
    if queries_start >= 0:
        removals.append((queries_start, queries_len))
    removals.sort(key=lambda x: x[0], reverse=True)

    for start, length in removals:
        del clean_lines[start:start + length]

    # 4. 合并新值和旧值
    merged_suppliers = list(new_suppliers)
    for s in existing_suppliers:
        if s not in merged_suppliers:
            merged_suppliers.append(s)
    merged_suppliers = merged_suppliers[:10]

    merged_queries = [new_query] if new_query else []
    for q in existing_queries:
        if q.strip() not in [m.strip() for m in merged_queries]:
            merged_queries.append(q)
    merged_queries = merged_queries[:5]

    # 5. 追加合并后的区块
    result_lines = list(clean_lines)

    # 确保末尾有空行分隔
    if result_lines and result_lines[-1].strip():
        result_lines.append("")

    result_lines.append("recent_suppliers:")
    if merged_suppliers:
        for s in merged_suppliers:
            result_lines.append(f"  - {s}")
    else:
        result_lines[-1] = "recent_suppliers: []"

    result_lines.append("recent_queries:")
    if merged_queries:
        for q in merged_queries:
            result_lines.append(f"  - {q}")
    else:
        result_lines[-1] = "recent_queries: []"

    return "\n".join(result_lines).strip() + "\n"
