import json
from contextlib import asynccontextmanager
from decimal import Decimal

import httpx
import pytest
from fastmcp import Client, FastMCP

from mcp_server.tools.order_tools import register_order_tools


@pytest.fixture
def order_server():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"code": 200, "data": {"id": 17}})

    @asynccontextmanager
    async def lifespan(server):
        async with httpx.AsyncClient(base_url="http://erp.test/api", transport=httpx.MockTransport(handler)) as client:
            yield {"http_client": client}

    server = FastMCP("Order integration contract", lifespan=lifespan)
    register_order_tools(server)
    return server, requests


@pytest.mark.asyncio
async def test_partial_mcp_update_preserves_omitted_order_fields(order_server):
    server, requests = order_server
    async with Client(server) as client:
        result = await client.call_tool("order_update", {"order_id": 17, "remark": "delivery date pending", "idempotency_key": "update-17-v1"})
    assert not result.is_error
    assert len(requests) == 1
    assert requests[0].method == "PUT"
    assert json.loads(requests[0].content) == {"remark": "delivery date pending"}
    assert requests[0].headers["Idempotency-Key"] == "update-17-v1"


@pytest.mark.asyncio
async def test_mcp_amount_survives_schema_validation_without_float_precision_loss(order_server):
    server, requests = order_server
    amount = "1234567890123456.78"
    async with Client(server) as client:
        result = await client.call_tool("order_update", {"order_id": 17, "total_amount": amount,
                                                         "order_detail": [{"partId": 1, "quantity": 1, "unitPrice": amount}]})
    assert not result.is_error
    body = json.loads(requests[0].content)
    assert isinstance(body["totalAmount"], str), "total_amount must not be coerced to binary float by the MCP schema"
    assert Decimal(body["totalAmount"]) == Decimal(amount)
    assert body["orderDetail"][0]["unitPrice"] == amount
    assert "orderNumber" not in body
    assert "orderTime" not in body
