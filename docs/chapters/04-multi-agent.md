# 第 04 章：DeepAgents 与 YAML 多 Agent

本章沿实际调用链理解“主 Agent 选择任务 → 专家工具执行 → 返回研究或操作结果”。角色配置要与可调用工具一致，不能只给同一个全权限 Agent 换名字。

## 代码入口

- [每请求主图工厂](../../src/agent/graphs/main_agent.py)
- [YAML 配置加载与采购工具解析](../../src/agent/subagents/loader.py)
- [采购订单角色](../../src/agent/subagents/configs/procurement_order.yaml)
- [财务研究角色](../../src/agent/subagents/configs/finance_researcher.yaml)、[独立复核角色](../../src/agent/subagents/configs/finance_reviewer.yaml)
- [真实图接线测试](../../tests/test_finance_agent_wiring.py)

## 学习重点

启动时可以预加载 MCP 与 YAML；每个请求仍需绑定已经认证的 `user_id` 和 `thread_id`，重新创建私有工具和中间件。缺失身份不回退到默认用户，已有图也不能换一个用户或会话继续使用。

采购订单角色保留 HITL 写操作中断。耗时采购分析走独立 Agent Protocol 任务。财务研究由 `finance-researcher` 检索和计算，再交 `finance-reviewer` 回查引用、复算、判断证据缺口。这一先后关系由版本化主 Prompt 指导，不是一个强制固定研究/复核顺序的业务状态机。

普通 DeepAgents 子 Agent 会继承文件系统和可能的沙箱 `execute` 工具。因此金融两角色先通过 LangChain `create_agent` 编译，再以 DeepAgents `CompiledSubAgent` 接入。它们只拿到按精确名称选择的金融工具，没有 shell、采购写工具或继续委派的 `task` 工具。

## 复现实验

```powershell
uv run --frozen pytest tests/test_finance_agent_wiring.py -q
```

重点观察 `test_real_deepagents_task_inherits_trusted_context_into_compiled_finance_role`：它实际运行 DeepAgents `task`、金融子图和本地检索工具，模型使用预先写好的测试响应，无联网模型调用。另一个测试把其他用户的引用交给 reviewer，应该得到“不可用”，而非原文。

## 依赖与边界

测试不需要 MongoDB、OpenSandbox 或模型密钥。live 主图需要这些外部依赖及可用 MCP；当前没有据此给出真实模型的工具选择准确率。金融默认读取当前用户的 `default` 文档分组，其他分组需要调用方明确绑定后再创建工具。采购通用 YAML 的原有子串工具匹配仍存在，不能把金融角色的精确白名单描述为所有角色都完成了同样的权限改造。
