# 配套学习工程

推荐按“携程助手 → RAG → Text2SQL → 本 ERP 综合工程”推进，评估练习贯穿全过程。三个基础仓库各有六章文档、顺序提交和 `chapter-NN` 标签；[Agent-Learning](https://github.com/ooo1208/Agent-Learning) 汇总资料并提供锁定提交版本的下载与离线验证入口。

| 基础仓库 | 核心练习 | 本工程对应部分 |
|---|---|---|
| [agent_ctrip_assistant](https://github.com/ooo1208/agent_ctrip_assistant) | 工具调用、审批、状态恢复 | 第 04、08、09 章的 Agent、人工介入与任务状态 |
| [RAG](https://github.com/ooo1208/RAG) | 文档入库、检索、引用、可选向量与生成接口 | 第 10 章的文档证据；后续可作为独立知识工具接入 |
| [Text2SQL](https://github.com/ooo1208/Text2SQL) | 采购查询、指标口径、只读限制 | 第 02、03 章的业务数据与 MCP；后续可作为只读分析工具接入 |
| [评估练习](https://github.com/ooo1208/Agent-Learning/blob/main/docs/evaluation.md) | 失败例、评分、回归门禁 | 第 10—12 章的证据、观测、Worker、Outbox 和反馈 |

这些是独立原创教学工程；当前没有自动将 RAG、Text2SQL 连接到本 ERP，也没有把多模态进阶任务标为已实现。现有 ERP 的业务接口、依赖与验收范围继续以本仓库文档为准。

可以用本 ERP 和独立 RAG 作为两个最终作品，携程用于建立基础，Text2SQL 用于深化数据工具能力。模块整合后，应增加接口契约、权限和失败场景的验证，并留下真实实验记录。
