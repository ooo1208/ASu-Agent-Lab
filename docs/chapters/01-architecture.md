# 第 01 章：项目架构与来源

## 目标

将业务系统、模型编排、沙箱执行和评估服务分开，避免把一个长 Prompt 当作完整 Agent 系统。

```text
Vue 工作台
  └─ FastAPI / JWT / SSE
       ├─ DeepAgents 主 Agent → 采购订单 / 异步分析 / 财务研究 / 复核
       ├─ MCP → Java ERP → H2（演示）或 MySQL
       ├─ MongoDB → checkpoint / 用户记忆 / Skills
       ├─ OpenSandbox → 文件与工具执行
       ├─ EvidenceStore → 文档片段 / 引用 / 财务计算
       └─ EvaluationJob → Worker → ScoreOutbox → Langfuse（可选）
```

## 阅读顺序

先看 SOURCES.md 和 CHAPTERS.md；第二章从确定性业务接口开始，再逐层加入模型和工具。外部服务不可用时，最终集成版本提供明确标注的本地演示；演示输出不能被视为真实模型评测结果。

## 验证

本章只创建目录与来源说明，不启动外部服务。后续章节的测试证据将记录在 docs/VALIDATION.md。
