"""Read-only MCP smoke check for the synthetic Java ERP dataset."""

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from fastmcp import Client

EXPECTED = {"supplier_query", "part_query", "part_search", "part_by_supplier",
            "order_create", "order_update", "order_search_details", "inventory_warning"}


async def smoke(url=None):
    if url:
        target = url
    else:
        from mcp_server.server_main import mcp
        target = mcp
    async with Client(target) as client:
        names = {tool.name for tool in await client.list_tools()}
        assert EXPECTED <= names, f"Missing tools: {EXPECTED - names}"
        part = await client.call_tool("part_search", {"name": "陶瓷刹车片"})
        assert not part.is_error and isinstance(part.data, list) and part.data, part
        assert part.data[0]["partCode"] == "DEMO-PART-001"
        assert part.data[0]["price"] == "38.50", part.data
        warning = await client.call_tool("inventory_warning", {})
        assert not warning.is_error and isinstance(warning.data, list), warning
        assert {row["partId"] for row in warning.data} == {1, 3}, warning.data
        print(json.dumps({"ok": True, "registered_tools": len(names), "sample_part": part.data[0]["name"],
                          "unit_price": part.data[0]["price"], "warning_part_ids": [row["partId"] for row in warning.data],
                          "data_kind": "synthetic", "mutations": 0}, ensure_ascii=False))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="HTTP MCP URL; omit to use in-process MCP against ERP_API_BASE_URL")
    asyncio.run(smoke(parser.parse_args().url))
