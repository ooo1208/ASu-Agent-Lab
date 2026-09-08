import os

# Java 后端 API 地址（可从环境变量读取）
JAVA_API_BASE_URL = os.getenv("ERP_API_BASE_URL", "http://127.0.0.1:8080/api")

# MCP 服务监听配置
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
MCP_PATH = "/mcp"

# Independent synthetic quote pages. Use a sandbox-reachable base URL when copying Skills.
QUOTE_HOST = os.getenv("QUOTE_HOST", "127.0.0.1")
QUOTE_PORT = int(os.getenv("QUOTE_PORT", "8086"))
QUOTE_BASE_URL = os.getenv("QUOTE_BASE_URL", f"http://127.0.0.1:{QUOTE_PORT}").rstrip("/")
