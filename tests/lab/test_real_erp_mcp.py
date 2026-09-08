"""Cross-process Java ERP + HTTP FastMCP acceptance, with an isolated synthetic database.

Run after ``mvn -f erp-service/pom.xml package`` with RUN_REAL_ERP_MCP=1.
No model, external database, existing ERP instance, or production credentials are used.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import uuid

import httpx
import pytest
from fastmcp import Client
from bs4 import BeautifulSoup


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REAL_ERP_MCP") != "1",
    reason="Set RUN_REAL_ERP_MCP=1 to start isolated Java ERP and HTTP MCP processes",
)
ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_ready(url, process, log, *, health=False):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail(f"Test service exited with {process.returncode}: {log.read_text(encoding='utf-8', errors='replace')[-5000:]}")
        try:
            response = httpx.get(url, timeout=1, trust_env=False)
            if health and response.status_code == 200 and response.json().get("status") == "UP":
                return
            if not health and response.status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.15)
    pytest.fail(f"Timed out waiting for {url}; see {log}")


@pytest.fixture(scope="module")
def real_services(tmp_path_factory):
    jar = Path(os.getenv("ERP_TEST_JAR", str(ROOT / "erp-service/target/erp-service-1.0.0.jar")))
    if not jar.is_file():
        pytest.fail("Build erp-service first: mvn -f erp-service/pom.xml package")
    java = os.getenv("JAVA_BIN") or shutil.which("java")
    if not java:
        pytest.fail("A JDK 17+ java command or JAVA_BIN environment variable is required")
    folder = tmp_path_factory.mktemp("real-java-erp-mcp")
    erp_port, mcp_port = _free_port(), _free_port()
    while erp_port == mcp_port:
        mcp_port = _free_port()
    key = "synthetic-test-" + uuid.uuid4().hex
    erp_url, mcp_url = f"http://127.0.0.1:{erp_port}", f"http://127.0.0.1:{mcp_port}/mcp"
    env = os.environ.copy()
    env.update({"ERP_API_KEY": key, "ERP_API_BASE_URL": erp_url + "/api", "MCP_HOST": "127.0.0.1", "MCP_PORT": str(mcp_port), "PYTHONIOENCODING": "utf-8"})
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    processes, streams = [], []
    try:
        java_log = folder / "java.log"
        streams.append(java_log.open("wb"))
        database = (folder / "database").as_posix()
        java_process = subprocess.Popen(
            [java, "-jar", str(jar.resolve()), f"--server.port={erp_port}", "--server.address=127.0.0.1",
             "--spring.profiles.active=", "--erp.seed-enabled=true", f"--erp.api-key={key}",
             f"--spring.datasource.url=jdbc:h2:file:{database};MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_ON_EXIT=FALSE",
             "--spring.datasource.driver-class-name=org.h2.Driver", "--spring.datasource.username=sa", "--spring.datasource.password="],
            cwd=ROOT, env=env, stdout=streams[-1], stderr=subprocess.STDOUT, creationflags=flags,
        )
        processes.append(java_process)
        _wait_ready(erp_url + "/actuator/health", java_process, java_log, health=True)
        mcp_log = folder / "mcp.log"
        streams.append(mcp_log.open("wb"))
        mcp_process = subprocess.Popen(
            [sys.executable, "src/mcp_server/server_main.py"], cwd=ROOT, env=env,
            stdout=streams[-1], stderr=subprocess.STDOUT, creationflags=flags,
        )
        processes.append(mcp_process)
        _wait_ready(mcp_url, mcp_process, mcp_log)
        yield {"mcp_url": mcp_url, "erp_url": erp_url, "headers": {"X-API-Key": key}}
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for stream in streams:
            stream.close()


@pytest.mark.asyncio
async def test_all_eight_tools_are_served_over_http(real_services):
    async with Client(real_services["mcp_url"]) as client:
        names = {tool.name for tool in await client.list_tools()}
    assert names == {"supplier_query", "part_query", "part_search", "part_by_supplier", "order_create", "order_update", "order_search_details", "inventory_warning"}


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,args,expected_count", [
    ("supplier_query", {"name": "示例"}, 3),
    ("part_query", {"supplier_id": 1, "current": 1, "size": 10}, 2),
    ("part_search", {"name": "陶瓷刹车片"}, 1),
    ("part_by_supplier", {"supplier_id": 3}, 1),
    ("order_search_details", {"part_name": "刹车", "start_date": "2026-01-01", "end_date": "2026-01-31"}, 1),
    ("inventory_warning", {}, 2),
])
async def test_six_read_tools_return_real_relational_business_data(real_services, tool, args, expected_count):
    async with Client(real_services["mcp_url"]) as client:
        result = await client.call_tool(tool, args)
    assert not result.is_error
    assert isinstance(result.data, list)
    assert len(result.data) == expected_count
    assert all(isinstance(row, dict) and "id" in row for row in result.data), result.data
    if tool in {"part_query", "part_search", "part_by_supplier"}:
        assert isinstance(result.data[0]["price"], str), "Decimal prices must remain exact strings over MCP"
        assert "supplier" in result.data[0]
    if tool == "order_search_details":
        assert result.data[0]["partDetail"]["id"] == 1
        assert result.data[0]["supplier"]["id"] == 1
    if tool == "inventory_warning":
        assert {row["partId"] for row in result.data} == {1, 3}


@pytest.mark.asyncio
async def test_create_update_and_idempotency_through_real_mcp(real_services):
    key = "mcp-create-" + uuid.uuid4().hex
    async with Client(real_services["mcp_url"]) as client:
        args = {"order_detail": [{"partId": 1, "quantity": 3, "unitPrice": "0.10"}], "idempotency_key": key}
        created = (await client.call_tool("order_create", args)).data
        replayed = (await client.call_tool("order_create", args)).data
        assert "error" not in created, created
        assert created["id"] == replayed["id"]
        assert created["orderNumber"] == replayed["orderNumber"]
        assert created["orderTime"] == replayed["orderTime"]
        assert Decimal(created["totalAmount"]) == Decimal("0.30")
        changed = (await client.call_tool("order_update", {"order_id": created["id"], "remark": "MCP-only header update", "idempotency_key": key + "-update"})).data
        assert changed["orderNumber"] == created["orderNumber"]
        assert changed["orderTime"] == created["orderTime"]
        assert changed["orderDetail"] == created["orderDetail"]
        assert changed["totalAmount"] == created["totalAmount"]
        conflict = (await client.call_tool("order_create", {**args, "remark": "different request"})).data
        assert "error" in conflict and "409" in conflict["error"]
    response = httpx.get(real_services["erp_url"] + "/api/orders/page", params={"orderNumber": created["orderNumber"]}, headers=real_services["headers"], trust_env=False)
    assert response.json()["data"]["total"] == 1


@pytest.mark.asyncio
async def test_max_precision_amount_round_trip_without_binary_float(real_services):
    amount = "1234567890123456.78"
    async with Client(real_services["mcp_url"]) as client:
        result = await client.call_tool("order_create", {"total_amount": amount,
            "order_detail": [{"partId": 2, "quantity": 1, "unitPrice": amount}],
            "idempotency_key": "precise-" + uuid.uuid4().hex})
    assert not result.is_error
    assert "error" not in result.data, result.data
    assert result.data["totalAmount"] == amount
    assert result.data["orderDetail"][0]["unitPrice"] == amount
    assert result.data["orderDetail"][0]["subtotal"] == amount


def test_direct_erp_request_without_service_key_is_denied(real_services):
    response = httpx.get(real_services["erp_url"] + "/api/parts/page", trust_env=False)
    assert response.status_code == 401
    assert response.json()["code"] == 401


def test_all_nine_quote_pages_are_fetchable_and_match_erp_entities(real_services, tmp_path):
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    path = tmp_path / "quotes.log"
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with path.open("wb") as log:
        process = subprocess.Popen([sys.executable, "src/mcp_server/quote_server.py", "--host", "127.0.0.1", "--port", str(port), "--base-url", base],
                                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        try:
            _wait_ready(base + "/", process, path)
            catalog = httpx.get(base + "/quotes.json", trust_env=False).json()
            mapping = httpx.get(base + "/mapping.json", trust_env=False).json()
            assert catalog["data_kind"] == "synthetic"
            assert len(catalog["quotes"]) == len(mapping["mappings"]) == 9
            assert all(row["url"].startswith(base + "/") for row in mapping["mappings"])
            for quote in catalog["quotes"]:
                response = httpx.get(base + "/" + quote["page"], trust_env=False)
                assert response.status_code == 200
                text = BeautifulSoup(response.text, "html.parser").select_one("main").get_text(" ", strip=True)
                assert "合成" in text and quote["part_name"] in text and quote["supplier"] in text
                assert quote["unit_price"] in text
                part = httpx.get(real_services["erp_url"] + f"/api/parts/get/{quote['part_id']}", headers=real_services["headers"], trust_env=False).json()["data"]
                supplier = httpx.get(real_services["erp_url"] + f"/api/suppliers/get/{quote['supplier_id']}", headers=real_services["headers"], trust_env=False).json()["data"]
                assert part["name"] == quote["part_name"] and supplier["name"] == quote["supplier"]
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
