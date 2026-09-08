# ERP_OPENCLAW 可选容器配置

从仓库根目录使用显式配置文件：

```powershell
# 不调用大模型的合成演示：Java ERP + API + Worker + 前端
 docker compose -f docker/compose.demo.yml up --build -d

# 仅供 live 模式使用的 MongoDB + OpenSandbox 基础设施
 docker compose -f docker/compose.live-infra.yml up --build -d
```

`docker-compose.yml` 是 live 基础设施的兼容入口，通过 `include` 复用 `compose.live-infra.yml`，需要 Docker Compose 2.20 或更高版本。两个明确配置文件可以直接使用，不依赖此兼容入口。

| 文件 | 用途 |
|---|---|
| `compose.demo.yml` | 本地演示完整编排；前端 5173，API 8090，ERP 8080；持久化评估与业务数据 |
| `compose.live-infra.yml` | 单独启动 MongoDB 27017 与 OpenSandbox 8100，供宿主机 live Python 进程连接 |
| `Dockerfile.python` | uv 锁文件构建的 API/Worker 共用镜像 |
| `Dockerfile.frontend` / `nginx.demo.conf` | 前端生产构建和支持 SSE 的 `/api` 代理 |
| `sandbox-image/Dockerfile` | 为 live 沙箱预装 Skills 需要的 Python 库，输出 `asu-agent-sandbox:v1` |
| `opensandbox.toml` | 本机 Docker runtime、网络与资源限制 |

live 配置默认 MongoDB 只绑定宿主 `127.0.0.1`，连接字符串为 `mongodb://127.0.0.1:27017`，数据库 `asu_agent`，与根目录 `.env.example` 一致。此配置不包含公网数据库的认证/TLS部署方案。

OpenSandbox 必须访问正在运行的 Docker daemon，并挂载 Docker socket 来创建沙箱容器；仅安装 Python 包不能替代 Docker 引擎。本地配置使用仅绑定回环端口的开发服务。实际沙箱网络、镜像拉取、宿主报价页面可达性仍需在目标 Docker 环境验收。

live Python 服务由根目录启动器负责：

```powershell
.venv/Scripts/python.exe start_all.py --mode live --erp
```

启动器依次拉起 MCP、**Agent Protocol（默认 2024）**、Web API、独立 Worker 和前端；Agent Protocol 对应 `ASYNC_AGENT_PROTOCOL_URL`，缺少它时异步子 Agent 无法执行。模型 key、JWT 密钥和基础设施连接需要另行配置。

常用操作（将配置文件换成实际使用的那个）：

```powershell
docker compose -f docker/compose.demo.yml ps
docker compose -f docker/compose.demo.yml logs -f
docker compose -f docker/compose.demo.yml down
```

`down` 保留命名卷；`down -v` 会删除卷内数据。完整命令、配置字段和能力边界见 [运行与部署](../docs/运行与部署.md)。本次环境没有可用 Docker 引擎，因此没有宣称完成容器构建或 live 端到端运行。
