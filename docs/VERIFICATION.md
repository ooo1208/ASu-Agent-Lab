# 验收记录

日期：2026-09-08。Windows 本地，Python 3.11、Java 21、Node 24；GitHub CI 另使用 Linux / Node 22。所有业务数据均为本次生成的合成数据，未读取或上传个人简历、模型密钥、数据库或真实客户数据。

## 自动检查

| 检查 | 实际结果 | 范围 |
|---|---|---|
| `.venv/Scripts/python.exe -m pytest tests -q` | 105 passed, 11 skipped, 13 deselected | 财务证据/计算、权限、阶段 Prompt、真实 DeepAgents 图接线（脚本模型）、SSE、审批、任务上下文、持久评估与启动计划 |
| `mvn -f erp-service/pom.xml package` / `test` | 12 项通过，JAR 构建成功 | 54 路由注册、关系约束、部分更新、金额、库存竞争、并发幂等 |
| `RUN_REAL_ERP_MCP=1 pytest tests/lab/test_real_erp_mcp.py tests/lab/test_mcp_orders.py -q` | 13 项通过 | 独立 Java 与 HTTP FastMCP 进程、8 工具、9 报价页、精确金额、幂等、API Key |
| 显式启用集成与写入测试后运行 `tests/test_mcp_integration.py tests/test_all_tools.py` | 10 项通过 | 专用合成 Java/MCP 实例，只写测试自建订单 |
| `scripts/run_mcp_smoke.py` 的内存与 HTTP 模式 | 均通过；mutations=0 | 8 工具注册、只读零件与库存查询 |
| `npm run build` | 成功 | Vite 8.2.2，主 JS 约 276 kB，gzip 约 109 kB |
| `npm audit --audit-level=high` | 0 vulnerabilities | 运行时及开发依赖；只是当时 audit 数据库结果 |
| 黄金基线门禁 | exit 0，passed=true | 12 个预写合成用例 |
| 故意回退的候选输出 | exit 1，passed=false | 数值、引用与越权写入回退被阻断 |
| `start_all.py --no-frontend --api-port 18091 --stop-after 1` | exit 0，退出后端口释放 | API + 独立 Worker 真实启动、数据库一致、进程清理 |

Python 有一条第三方 Starlette/httpx 迁移提示，不影响本次测试结果。默认 pytest 排除 `integration` / `live`；跨进程 ERP 测试还需显式 `RUN_REAL_ERP_MCP=1`。前表列出了另外实际开启的测试，不能把默认跳过等同于已经运行。

精确金额案例：`1234567890123456.78` 经过 FastMCP 输入、Java ERP、HTTP JSON 与工具输出后保持原值。Java 独立 JAR 还验证了重启后同一幂等键返回原订单且没有重复写入。更详细过程见 [ERP 验收](../erp-service/VERIFICATION.md)。

## 浏览器实际操作

使用本地合成账号，经 `http://127.0.0.1:5173` 验证：

1. 注册、登录，看到明确的“本地合成演示，不调用大模型”。
2. 点击填入合成财报，再显式导入；建立 1 个证据片段。
3. 搜索“营业收入”，返回原文和引用 ID；回查显示第 1–10 行。
4. 输入 old=100、new=120，得到 20% 和原始公式。
5. 创建合成评估，独立 Worker 将任务从等待更新为已完成；离线 Outbox 保留待发送状态。
6. 保存人工反馈并加入 `reviewed-v1`，黄金集包含对应修正标准与来源关联。
7. 输入“演示下单 2 件”，显示待审批明细。重新打开会话仍能恢复待审批操作，批准后 Java ERP 返回新订单，合计 77.00 元。

验收修复了新会话首次中断未保留 thread_id 导致按钮无效的问题。重复审批只写一次、拒绝零写入、交错工具关联及取消后的观察记录由独立回归测试覆盖。

## 未作通过声明的项目

- 真实模型与多 Agent 的任务完成率、延迟或成本 benchmark。
- Langfuse 云端账号实际接收；当前测试校验 OTLP/Score 请求协议及重试语义。
- Docker 镜像构建/Compose 启动、OpenSandbox 真容器热恢复、MySQL 连接。
- 真实银行数据、授信决策效果、生产 RBAC、多节点高并发和灾备。

Docker/YAML 文件已做本地语法与引用检查；这不等同于容器执行。章节标签表示实际源码整理顺序，不是原课程的历史提交。后续 GitHub Actions 结果以 [运行记录](https://github.com/ooo1208/ERP_OPENCLAW/actions/workflows/quality.yml) 为准。
