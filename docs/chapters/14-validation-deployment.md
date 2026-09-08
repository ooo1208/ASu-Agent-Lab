# 第 14 章：集成验证与部署

本章把验证拆成不依赖外部服务的回归、真实本地 Java/MCP 协议验收，以及尚需单独配置的外部模型/基础设施验收。测试数量和执行结果以最终验证报告为准。

## 代码入口

- [依赖声明](../../pyproject.toml)、[Python 锁文件](../../uv.lock)、[前端锁文件](../../frontend/package-lock.json)
- [进程启动/停止与预检](../../start_all.py)
- [默认测试选择](../../pytest.ini)与[CI 工作流](../../.github/workflows/quality.yml)
- [本地演示 Compose](../../docker/compose.demo.yml)与[live 基础设施 Compose](../../docker/compose.live-infra.yml)
- [Java 验证记录](../../erp-service/VERIFICATION.md)

## 从本地验证开始

在 Python 3.11+、Node 22 和 Java 21 的环境中，从项目根目录执行：

```powershell
uv sync --locked
uv run --frozen pytest -q
uv run --frozen python -m asu_eval.gate --dataset evals/golden.synthetic.json --predictions evals/predictions.baseline.json --baseline evals/baseline.synthetic.json
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend audit --audit-level=high
mvn -B -ntp -f erp-service/pom.xml test
```

默认 pytest 排除标记为 integration/live 的旧服务测试；`RUN_REAL_ERP_MCP` 控制的跨进程验收也需要显式启用。跳过项不是通过项，合成门禁不是模型 benchmark。CI 执行相应回归与正/反门禁，推送后应检查实际 Actions 结果，不能仅凭存在 YAML 就宣称 CI 已通过。

## 启动器复现实验

```powershell
uv run --frozen python start_all.py --mode demo --check
uv run --frozen python start_all.py --mode demo --stop-after 10
```

预检会检查依赖与端口；第二条启动自己的 API、Worker、前端进程并在就绪后退出。正常服务日志写入 `ASU_DATA_DIR/logs`，默认数据目录为 `.local/asu`。Ctrl+C 只停止本启动器追踪的进程树。不要同时启动两个使用同一端口的实例。

完整 Java → HTTP MCP 实验见 [第 03 章](03-mcp-tools.md)。人工工作台验收见 [第 13 章](13-web-demo.md)。独立异步 Agent Protocol 的启动见 [第 09 章](09-async-analysis.md)。

## 容器与 live 依赖

```powershell
docker compose -f docker/compose.demo.yml config --quiet
docker compose -f docker/compose.demo.yml up --build
```

此 Compose 描述演示 API、Worker、前端、合成 ERP 及持久卷。`config --quiet` 只验证配置，不启动服务；本仓库提供了容器文件，但没有把未执行的 Docker 构建或启动标为验收通过。

live 模式额外需要有效模型密钥、JWT 签名密钥、MongoDB、OpenSandbox/MCP，以及需要时的搜索和 Agent Protocol 服务。`compose.live-infra.yml` 只提供本地基础设施，不是生产编排。模型和 Langfuse 密钥只放在本地环境配置，不提交到 Git。

## 已知部署边界

- Langfuse live、真实模型、多 Agent 业务效果、MySQL 和真实沙箱恢复需独立验收。
- SQLite 作业库与 ERP 全局写锁面向本地/小规模演示，不是多节点高吞吐方案。
- ERP 查询当前有内存筛选/分页，不具备完整生产 RBAC、多仓批次、真实物流或结算。
- 未实现 OCR/向量 RAG、线上 LLM judge、全量 FinQA benchmark 或完整逐 token Trace 树。
- 章节来自对比后的教学重组。对照 [对比矩阵](../COMPARISON.md) 检查本次明确补上的缺口，不将本仓库描述为所有官方内容的完整复刻。
