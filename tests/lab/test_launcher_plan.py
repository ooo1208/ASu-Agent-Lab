import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("asu_start_all", ROOT / "start_all.py")
launcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)


def arguments(**changes):
    options = dict(mode="demo", python=sys.executable, erp=False, erp_jar=None, quotes=False,
                   api_port=18091, protocol_port=12024, no_worker=False, no_frontend=True,
                   frontend_port=15173, delivery="offline")
    options.update(changes)
    return argparse.Namespace(**options)


def test_demo_plan_shares_durable_db_and_starts_no_model_services(tmp_path):
    environment = {"ASU_DATA_DIR": str(tmp_path)}
    plan = launcher.plans(arguments(), environment)
    assert [service.name for service in plan] == ["api", "worker"]
    assert "asu_lab.app:create_app" in plan[0].command
    assert "--factory" in plan[0].command
    assert plan[0].port == 18091
    assert environment["API_PROXY_TARGET"] == "http://127.0.0.1:18091"
    assert str(tmp_path / "evaluation.sqlite3") in plan[1].command
    assert plan[1].command[-1] == "offline"


def test_live_plan_starts_async_protocol_before_web_api(tmp_path):
    environment = {"ASU_DATA_DIR": str(tmp_path), "DEEPSEEK_API_KEY": "synthetic-unused-key",
                   "JWT_SECRET_KEY": "synthetic-unused-secret" * 3, "MCP_PORT": "18000"}
    plan = launcher.plans(arguments(mode="live"), environment)
    assert [service.name for service in plan] == ["mcp", "agent-protocol", "api", "worker"]
    assert "langgraph_cli" in plan[1].command
    assert "dev" in plan[1].command
    assert "--no-browser" in plan[1].command
    assert plan[1].health_url == "http://127.0.0.1:12024/ok"
    assert environment["ASYNC_AGENT_PROTOCOL_URL"] == "http://127.0.0.1:12024"
    assert environment["ERP_MCP_URL"] == "http://127.0.0.1:18000/mcp"
    assert "api_view.web_main:app" in plan[2].command
