# 第 03 章：MCP 协议与工具封装

本章把 Java ERP 的业务接口转换为模型可调用的工具。工具描述是使用说明，输入 Schema、服务鉴权和后端事务才是执行边界。

## 代码入口

- [FastMCP 服务与共享 HTTP 客户端](../../src/mcp_server/server_main.py)
- [订单创建和部分更新工具](../../src/mcp_server/tools/order_tools.py)
- [供应商](../../src/mcp_server/tools/suppliers_tools.py)、[零件](../../src/mcp_server/tools/parts_tools.py)、[库存](../../src/mcp_server/tools/inventory_tools.py)
- [Agent 侧 MCP 加载](../../src/agent/tools/mcp_client.py)
- [54 条 REST 路径清单](../../erp-service/src/test/resources/endpoint-manifest.json)

## 学习重点

比较工具参数的 snake_case 与 ERP JSON 的 camelCase。`order_update` 只发送调用者提供的字段，不能为了满足创建订单的字段集合，自动替换订单号、时间或明细。金额使用十进制字符串，幂等键由 MCP 传到 HTTP Header；相同操作的可靠重试还需要第 02 章的数据库幂等记录。

目前暴露八个采购 MCP 工具，不是把 ERP 的 54 条路由全部变成工具。保留这一层选择可以缩小模型的操作面；金融研究工具在第 10 章独立提供。

## 复现实验

先运行无需外部服务的协议测试：

```powershell
uv run --frozen pytest tests/lab/test_mcp_orders.py -q
```

测试通过真实 FastMCP Client 调用工具，使用受控 HTTP Transport 检查最终请求：只更新备注时不得生成 `orderNumber`；大数金额不能先损失为 float；`Idempotency-Key` 应被保留。

需要验证跨进程 Java 与 MCP 时，先打包 JAR，再运行专门验收：

```powershell
mvn -f erp-service/pom.xml package
$env:RUN_REAL_ERP_MCP = '1'
uv run --frozen pytest tests/lab/test_real_erp_mcp.py -q
Remove-Item Env:RUN_REAL_ERP_MCP
```

该测试自己启动临时 H2 数据库、Java ERP 和 HTTP MCP 进程，使用合成种子，不需要模型。对应 [测试源码](../../tests/lab/test_real_erp_mcp.py) 明确区分工具发现、请求协议与业务结果。

## 依赖与边界

本地协议测试需要 Python 项目依赖；跨进程验收还需要 Java 与已打包 JAR。MCP 本身不等于审批服务，采购写工具的人工中断在第 08 章。超时后不能仅因为客户端没有收到响应就换一个幂等键重试；应先核对状态。
