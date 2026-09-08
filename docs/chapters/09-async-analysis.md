# 第 09 章：独立异步分析与任务管理

耗时采购分析不应占住一次聊天请求。本章把任务创建、后台执行与用户查询拆开，同时把任务身份绑定到当前用户的私有沙箱。

## 代码入口

- [异步采购分析图](../../src/agent/graphs/async_analyst.py)
- [签名的用户/沙箱/任务绑定](../../src/agent/core/async_sandbox_claims.py)
- [用户绑定的异步工具中间件](../../src/agent/middlewares/user_async_subagents.py)
- [任务存储](../../src/agent/stores/async_task_store.py)与[任务 API](../../src/api_view/api/tasks.py)
- [Agent Protocol 配置](../../langgraph.json)与[任务面板](../../frontend/src/components/AsyncTaskPanel.vue)

## 学习重点

主 Agent 启动任务后返回完整 `task_id`，用户再按需查询、补充、取消。后台不相信由模型传来的用户或沙箱 ID，而是校验服务签发的绑定；同一声明不能被挪到另一个任务。

这里的后台采购分析 Agent 与第 12 章的 Evaluation Worker 不同：前者执行模型与业务工具任务，后者消费已记录的快照并评分。demo 中的异步展示也不能当作真实后台模型分析。

## 复现实验

```powershell
uv run --frozen pytest tests/test_async_sandbox_binding.py -q
```

测试确认签名绑定可以正常解码、不能换 task_id 重放，以及沙箱代理切换后新任务使用替换后的沙箱。Client 与持久层使用测试替身，因此不会启动外部任务。

准备好 live 的模型、MongoDB、OpenSandbox 与服务签名配置后，可以单独启动 Agent Protocol：

```powershell
uv run --frozen langgraph dev --host 127.0.0.1 --port 2024
```

主 API 的 `ASYNC_AGENT_PROTOCOL_URL` 应指向这个地址。启动器不会把未启动的 Agent Protocol 自动变成可用服务，需在 live 验收前确认此进程正常。

## 依赖与边界

单元测试证明绑定和工具包装行为，不证明后台模型任务、取消时机或进程重启后的业务恢复已经做过 live 验收。真实执行依赖模型、Agent Protocol、MongoDB、MCP、私有沙箱及必要的搜索服务；上述外部链路没有被本地合成案例替代。
