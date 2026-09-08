"""Integration tests for the current synthetic ERP contract.

Requires Java ERP at ERP_API_BASE_URL. HTTP adapter checks also require
ERP_MCP_URL. Write cases create their own synthetic orders and are opt-in.
"""

from decimal import Decimal
import json
import os
import uuid

from fastmcp import Client
from langchain_mcp_adapters.client import MultiServerMCPClient
import pytest

from mcp_server.server_main import mcp

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]
requires_erp_writes = pytest.mark.skipif(
    os.getenv("RUN_ERP_WRITE_TESTS") != "1",
    reason="Set RUN_ERP_WRITE_TESTS=1 to create isolated synthetic acceptance orders",
)


async def _call(name, arguments):
    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments)
    assert not result.is_error
    assert not (isinstance(result.data, dict) and "error" in result.data), result.data
    return result.data


@pytest.mark.parametrize("name,arguments,expected_count", [
    ("supplier_query", {"name": "示例"}, 3),
    ("part_query", {"current": 1, "size": 10, "category": "制动类"}, 2),
    ("part_search", {"name": "陶瓷刹车片"}, 1),
    ("part_by_supplier", {"supplier_id": 3}, 1),
    ("order_search_details", {"part_name": "刹车", "start_date": "2026-01-01", "end_date": "2026-01-31"}, 1),
    ("inventory_warning", {}, 2),
])
async def test_synthetic_read_tool_contract(name, arguments, expected_count):
    rows = await _call(name, arguments)
    assert isinstance(rows, list) and len(rows) == expected_count, rows
    assert all(isinstance(row, dict) and "id" in row for row in rows)
    if name in {"part_query", "part_search", "part_by_supplier"}:
        assert isinstance(rows[0]["price"], str)
        assert "supplier" in rows[0]


@requires_erp_writes
async def test_mcp_order_create():
    key = "legacy-contract-create-" + uuid.uuid4().hex
    args = {"order_detail": [{"partId": 1, "quantity": 3, "unitPrice": "38.50"}],
            "order_number": "SYNTHETIC-TEST-" + uuid.uuid4().hex, "status": 1,
            "remark": "合成验收订单", "idempotency_key": key}
    created = await _call("order_create", args)
    replay = await _call("order_create", args)
    assert created["id"] == replay["id"]
    assert Decimal(created["totalAmount"]) == Decimal("115.50")
    assert created["orderDetail"][0]["partId"] == 1


@requires_erp_writes
async def test_mcp_order_update():
    created = await _call("order_create", {
        "order_detail": [{"partId": 3, "quantity": 2, "unitPrice": "89.90"}],
        "idempotency_key": "legacy-contract-update-create-" + uuid.uuid4().hex,
    })
    updated = await _call("order_update", {"order_id": created["id"], "remark": "只改合成验收备注",
                                            "idempotency_key": "legacy-contract-update-" + uuid.uuid4().hex})
    assert updated["orderNumber"] == created["orderNumber"]
    assert updated["orderTime"] == created["orderTime"]
    assert updated["orderDetail"] == created["orderDetail"]
    assert updated["totalAmount"] == created["totalAmount"]


async def test_agent_adapter_inventory_warning():
    adapter = MultiServerMCPClient({"erp": {"url": os.getenv("ERP_MCP_URL", "http://127.0.0.1:8000/mcp"), "transport": "streamable_http"}})
    tools = await adapter.get_tools(server_name="erp")
    inventory = next(tool for tool in tools if tool.name == "inventory_warning")
    result = await inventory.ainvoke({})
    # The adapter returns LangChain content blocks; parse its actual JSON text.
    if isinstance(result, list) and all(isinstance(block, dict) and block.get("type") == "text" for block in result):
        rows = json.loads("".join(block["text"] for block in result))
    elif isinstance(result, str):
        rows = json.loads(result)
    else:
        rows = result
    assert isinstance(rows, list)
    assert {row["partId"] for row in rows} == {1, 3}
