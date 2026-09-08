import pytest
from fastmcp import Client

from tests.conftest import MCP_URL


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_mcp_tools_are_registered_and_read_tools_work() -> None:
    async with Client(MCP_URL) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools}
        result = await client.call_tool("part_search", {"name": "陶瓷刹车片"})

    expected = {
        "supplier_query",
        "part_query",
        "part_search",
        "part_by_supplier",
        "order_create",
        "order_update",
        "order_search_details",
        "inventory_warning",
    }
    assert expected <= names
    assert not result.is_error
    assert len(result.data) == 1
    assert result.data[0]["name"] == "陶瓷刹车片"
    assert result.data[0]["partCode"] == "DEMO-PART-001"
    assert result.data[0]["price"] == "38.50"
