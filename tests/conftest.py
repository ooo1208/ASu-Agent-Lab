import os
import time
import uuid

import pytest


BASE_URL = os.getenv("ERP_WEB_URL", "http://127.0.0.1:8090")
JAVA_URL = os.getenv("ERP_JAVA_URL", "http://127.0.0.1:8080/api")
MCP_URL = os.getenv("ERP_MCP_URL", "http://127.0.0.1:8000/mcp")
RUN_LIVE_LLM_TESTS = os.getenv("RUN_LIVE_LLM_TESTS", "0") == "1"


def unique_credentials() -> dict[str, str]:
    suffix = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    return {
        "username": f"qa_auto_{suffix}",
        "password": "QaTest!2026",
        "display_name": "自动化验收用户",
    }


def require_live_llm() -> None:
    if not RUN_LIVE_LLM_TESTS:
        pytest.skip("设置 RUN_LIVE_LLM_TESTS=1 后运行真实模型链路测试")
