# 第 07 章：上下文、里程碑与 Prompt 版本

本章把会话裁剪与关键约束分开处理。近期对话保留交互细节，结构化约束和里程碑单独持久化，每次模型调用重新读取当前任务阶段。

## 代码入口

- [TaskContextStore 和里程碑工具](../../src/asu_lab/context.py)
- [每次模型请求的阶段注入](../../src/agent/middlewares/stage_context.py)
- [版本化 Prompt 加载器](../../src/asu_lab/prompts.py)与[v1 文本](../../src/asu_lab/prompts/v1/)
- [已有摘要中间件](../../src/agent/middlewares/tools_summarization.py)
- [接入主图与金融子图](../../src/agent/graphs/main_agent.py)

## 学习重点

任务阶段为 `collect → validate → execute → review`。这些阶段是可更新的任务提示，不是不可回退的审批状态机。`record_task_milestone` 绑定用户与会话，合并最新明确约束，最多保留 12 条里程碑；约束和单条摘要有大小上限。

`StageContextMiddleware` 在每个 model request 前读取最新数据，仅覆盖该次请求的 SystemMessage，不把动态提示写进 checkpoint 对话消息。已有角色、Skills 和文件系统规则保留。写入 `approved: true` 的任务数据不会授予采购操作权限。

`ASU_PROMPT_RELEASE=v1` 选择本地版本。实际加载文字带内容摘要标识，未知版本直接报错，不悄悄换用另一份文本。当前并未接入 Langfuse 云端 Prompt 的 production 标签、缓存或远端回退。

## 复现实验

```powershell
uv run --frozen pytest tests/test_finance_agent_wiring.py tests/lab/test_observation_context.py -q
uv run --frozen python -c "from asu_lab.prompts import load_prompt; print(load_prompt('main')[1])"
```

图测试让测试模型第一轮调用里程碑工具，第二轮应收到 `validate` 阶段和新约束；输出消息中不应出现被持久化的动态系统上下文。重启 Store 后约束应仍在，其他用户与其他会话读取不到。

## 依赖与边界

持久上下文使用本地 SQLite，测试不用模型服务。既有长对话摘要在 live 时需要模型。当前没有完成窗口长度的真实模型对照实验，也没有测得 Token 成本、证据召回率或任务完成率提升；保留预算和版本记录，为后续实验提供可重复条件。
