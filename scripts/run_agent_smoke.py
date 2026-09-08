import asyncio
import json
from typing import AsyncIterator

from langgraph.types import Command

from api_view.agent_loader import agent_loader


def extract_content_from_token(token) -> str:
    """
    从 token 中提取文本内容。
    处理 token.content 可能是字符串、列表或其他类型的情况。
    """
    if not hasattr(token, 'content'):
        return ""

    content = token.content

    # 如果 content 是字符串，直接返回
    if isinstance(content, str):
        return content

    # 如果 content 是列表，尝试提取其中的文本
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict):
                # 尝试从字典中提取文本
                if 'text' in item:
                    text_parts.append(item['text'])
                elif 'content' in item:
                    text_parts.append(str(item['content']))
                else:
                    # 将整个字典转换为字符串
                    text_parts.append(str(item))
            else:
                # 其他类型转换为字符串
                text_parts.append(str(item))
        return ''.join(text_parts)

    # 其他类型转换为字符串
    return str(content) if content is not None else ""


async def stream_agent_response(user_input: str) -> str:
    """流式处理代理响应，支持 Human-in-the-Loop 中断恢复。

    当子 Agent 调用 order_create / order_update 时，流程暂停，
    展示订单信息等待人工确认。确认后继续执行。
    """
    config = agent_loader.create_config(
        "test-thread-001", user_id="manual-test-user"
    )
    context = {"user_id": "manual-test-user", "username": "manual-test-user"}
    await agent_loader.initialize()
    agent = await agent_loader.get_agent_for_user("manual-test-user", config)

    current_input = {"messages": [{"role": "user", "content": user_input}]}
    collected_response = ""
    current_source_agent = "主代理"
    current_subagent_id = None
    last_message_source = None
    last_message_type = None
    is_inside_message = False

    print(f"\n{'=' * 50}")
    print(f"用户输入: {user_input}")
    print(f"{'=' * 50}")

    # 中断恢复循环
    while True:
        interrupts_detected = []

        try:
            async for chunk in agent.astream(
                input=current_input,
                config=config,
                context=context,
                stream_mode=["messages", "values"],  # 双模式: messages 显示 + values 检测中断
                subgraphs=True,
                version="v2",
            ):
                chunk_type = chunk.get("type")

                # ---- 消息流（token / tool_call / tool_result）----
                if chunk_type == "messages":
                    token, metadata = chunk["data"]
                    namespace = chunk.get("ns", ())

                    # 判断事件来源
                    is_subagent_event = any(segment.startswith("tools:") for segment in namespace)

                    current_source = None
                    if is_subagent_event:
                        subagent_ns_segment = next((s for s in namespace if s.startswith("tools:")), None)
                        if subagent_ns_segment:
                            current_source = subagent_ns_segment.replace("tools:", "子代理-")
                            current_subagent_id = current_source
                            current_source_agent = "子代理"
                        else:
                            current_source = "未知代理"
                    else:
                        current_source = "主代理"
                        current_subagent_id = None
                        current_source_agent = "主代理"

                    current_message_type = getattr(token, 'type', 'unknown')

                    # 检查是否开始了一条新消息
                    is_new_message = False
                    if (current_source != last_message_source or
                            current_message_type != last_message_type or
                            (not is_inside_message and (
                                hasattr(token, 'type') and
                                token.type in ['AIMessageChunk', 'tool', 'human']
                            ))):
                        is_new_message = True
                        is_inside_message = True

                    if is_new_message and last_message_source is not None:
                        print(f"\n{current_message_type}={'=' * 50}")

                    last_message_source = current_source
                    last_message_type = current_message_type

                    if is_subagent_event:
                        if current_source != current_subagent_id:
                            if current_subagent_id:
                                print()
                            print(f"\n[{current_source}] ", end="", flush=True)
                            current_subagent_id = current_source
                    else:
                        if current_source_agent != "主代理":
                            print()
                            print(f"\n[主代理] ", end="", flush=True)
                            current_source_agent = "主代理"
                            current_subagent_id = None

                    # 处理工具调用
                    if hasattr(token, 'tool_call_chunks') and token.tool_call_chunks:
                        for tool_chunk in token.tool_call_chunks:
                            if tool_chunk.get('name'):
                                source_prefix = (
                                    f"[{current_subagent_id}] " if current_subagent_id
                                    else "[主代理] "
                                )
                                print(f"\n{source_prefix}正在调用工具: {tool_chunk['name']}", end="", flush=True)
                            if tool_chunk.get('args'):
                                args_str = tool_chunk['args']
                                if args_str and args_str.strip() not in ['{', '}', ':']:
                                    print(f" {args_str}", end="", flush=True)

                    # 处理工具执行结果
                    if hasattr(token, 'type') and token.type == "tool":
                        tool_name = getattr(token, 'name', '未知工具')
                        result_content = getattr(token, 'content', '')
                        result_str = str(result_content)[:150] if result_content else "无结果"
                        source_prefix = (
                            f"[{current_subagent_id}] " if current_subagent_id
                            else "[主代理] "
                        )
                        print(f"\n{source_prefix}工具 '{tool_name}' 执行完成，结果: {result_str}...")

                        print(f"\n{current_message_type}={'=' * 50}")
                        is_inside_message = False
                        last_message_source = None
                        last_message_type = None

                    # 处理常规的AI文本内容
                    content_text = extract_content_from_token(token)
                    has_tool_calls = hasattr(token, 'tool_call_chunks') and token.tool_call_chunks
                    if content_text and not has_tool_calls:
                        if hasattr(token, 'type') and token.type == "ai":
                            if not is_inside_message or (
                                    current_source != last_message_source and
                                    last_message_source is not None):
                                print(f"\n[{current_source}] AIMessage: ", end="", flush=True)
                        print(content_text, end="", flush=True)
                        collected_response += content_text

                # ---- 值流（中断检测）----
                elif chunk_type == "values" and chunk.get("interrupts"):
                    interrupts_detected = chunk["interrupts"]

            # 流结束后，如有未结束的消息，添加分隔线
            if is_inside_message:
                print(f"\n{current_message_type}={'=' * 50}")

        except Exception as e:
            print(f"\n[错误] 流式处理时发生异常: {e}")
            import traceback
            traceback.print_exc()
            break

        # ---- 无中断 → 正常完成 ----
        if not interrupts_detected:
            break

        # ---- 处理中断（类型分发）----
        resume_value = await _handle_interrupts(interrupts_detected)

        # 恢复执行
        current_input = Command(resume=resume_value)
        # 重置状态追踪变量
        is_inside_message = False
        last_message_source = None
        last_message_type = None

    print()
    return collected_response


def _print_order_summary(args: dict) -> None:
    """格式化打印订单关键信息，便于人工快速确认。"""
    # 订单头信息
    order_number = args.get("orderNumber", "")
    if order_number:
        print(f"  订单编号: {order_number}")
    total = args.get("totalAmount", "")
    if total:
        print(f"  总金额: {total}")
    status_map = {1: "待审核", 2: "已审核", 3: "采购中", 4: "已入库", 5: "已取消"}
    status = args.get("status")
    if status is not None:
        print(f"  状态: {status_map.get(status, status)}")
    expected = args.get("expectedDeliveryDate", "")
    if expected:
        print(f"  预计交货: {expected}")
    remark = args.get("remark", "")
    if remark:
        print(f"  备注: {remark}")

    # 订单明细
    details = args.get("orderDetail", [])
    if details:
        print(f"  明细 ({len(details)} 项):")
        for i, item in enumerate(details, 1):
            part_id = item.get("partId", "?")
            qty = item.get("quantity", "?")
            price = item.get("unitPrice", "?")
            subtotal = item.get("subtotal", "")
            info = f"    {i}. 物料ID={part_id}, 数量={qty}, 单价={price}"
            if subtotal:
                info += f", 小计={subtotal}"
            print(info)


async def _handle_interrupts(interrupts_detected: list) -> dict:
    """处理中断，按类型分发到不同的处理函数。

    Returns:
        Command.resume 所需的 dict:
        - HITL 审批 → {"decisions": [{"type": "approve"|"reject"}]}
        - 数据补充 → {"supplement": "人工输入的内容"}
    """
    for interrupt in interrupts_detected:
        interrupt_value = interrupt.value

        if "action_requests" in interrupt_value:
            # ---- 第 2 层：HITL 审批中断（interrupt_on 配置）----
            return _handle_hitl_interrupt(interrupt_value)

        elif interrupt_value.get("type") == "order_info_request":
            # ---- 第 1 层：数据补充中断（request_order_info 工具）----
            return _handle_order_info_interrupt(interrupt_value)

    return {}


def _handle_hitl_interrupt(interrupt_value: dict) -> dict:
    """处理 HITL 审批中断：展示订单信息，收集 approve/reject 决策。"""
    decisions = []
    print(f"\n{'=' * 60}")
    print("⚠  需要人工确认以下操作：")

    action_requests = interrupt_value.get("action_requests", [])
    review_configs = interrupt_value.get("review_configs", [])
    config_map = {cfg["action_name"]: cfg for cfg in review_configs}

    for action in action_requests:
        tool_name = action["name"]
        tool_args = action.get("args", {})
        allowed = config_map.get(
            tool_name, {}
        ).get("allowed_decisions", ["approve", "reject"])

        print(f"\n操作类型: {tool_name}")
        print(f"订单信息:")
        _print_order_summary(tool_args)
        print(f"\n(完整参数: {json.dumps(tool_args, indent=2, ensure_ascii=False)})")
        print(f"\n允许的操作: {', '.join(allowed)}")

        while True:
            decision = input(
                f"请输入 {'/'.join(allowed)}: "
            ).strip().lower()
            if decision in allowed:
                decisions.append({"type": decision})
                break
            print(f"无效输入，请输入: {', '.join(allowed)}")

    print(f"{'=' * 60}\n")
    return {"decisions": decisions}


def _handle_order_info_interrupt(interrupt_value: dict) -> dict:
    """处理数据补充中断：展示缺失字段，收集人工补充信息。"""
    print(f"\n{'=' * 60}")
    print("⚠  订单数据不完整，请补充以下信息：")
    print(f"\n缺少字段: {interrupt_value['missing_fields']}")
    print(f"\n已收集数据:")
    print(f"  {interrupt_value['collected_data']}")
    print()

    supplement = input("请输入补充信息（Agent 将自动解析）: ").strip()
    print(f"{'=' * 60}\n")
    return {"supplement": supplement}


async def main():
    """主交互循环。"""
    print("Deep Agent 流式交互测试 (支持 Human-in-the-Loop)")
    print("说明: 输入您的问题，代理将流式地回复。")
    print("      涉及订单创建/修改时会要求人工确认。")
    print("      输入 '退出' 或 'quit' 结束程序。")
    print("-" * 50)

    while True:
        try:
            # 获取用户输入
            user_input = input("\n请输入您的问题: ").strip()

            if not user_input:
                print("输入不能为空，请重新输入。")
                continue

            if user_input.lower() in ['退出', 'quit', 'exit']:
                print("感谢使用，再见！")
                break

            # 流式处理并获取响应（内含中断恢复循环）
            final_response = await stream_agent_response(user_input)

        except KeyboardInterrupt:
            print("\n\n检测到中断，程序退出。")
            break
        except Exception as e:
            print(f"\n[错误] 交互过程中发生异常: {e}")


# 运行主程序
if __name__ == "__main__":
    asyncio.run(main())
