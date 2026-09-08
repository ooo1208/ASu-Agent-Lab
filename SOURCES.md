# 来源与实现边界

## 直接复用

- 来源：[KagaribiDev/procurepilot](https://github.com/KagaribiDev/procurepilot)
- 固定版本：`012b51ed6c1e9f80133a4add5ec170b817b9465e`
- 许可：MIT，原文保留于根目录 LICENSE 和 third_party/procurepilot-LICENSE.txt。
- 范围：采购 Agent、MCP 适配、沙箱与 Skills、持久化、多用户 API 和 Vue 前端的基础实现。
- 未导入上游图片与数据库整包，样例数据使用本仓库合成数据。

## 行为与方案参考

以下仓库用于交叉验证功能和发现缺口。没有将它们全部作为代码复制来源；新增模块按接口行为独立实现。

| 参考 | 本仓库吸收的方向 |
|---|---|
| [chenqianlei51525/ERP_OPENCLAW](https://github.com/chenqianlei51525/ERP_OPENCLAW) | 比较基础采购结构、内存 Store 与持久 Store 差异 |
| [Running-hue/procureflow-agent](https://github.com/Running-hue/procureflow-agent) | ERP REST 路径契约、订单部分更新、业务测试 |
| [Ckingleeee/ERP_OPENCLAW](https://github.com/Ckingleeee/ERP_OPENCLAW) | 黄金用例、真实工具轨迹、执行结果未知时的处理 |
| [hxlwd/leman](https://github.com/hxlwd/leman) | 文档检索、证据回查与引用 |
| [gaoyanzhi/purchase_ai](https://gitee.com/gaoyanzhi/purchase_ai) | 工作流边界与 Langfuse 观测 |
| [doneyli/langfuse-llm-certification-finance](https://github.com/doneyli/langfuse-llm-certification-finance) | 评估标准、人工审核回流、发布门禁 |

Java ERP、财务证据与评估新增模块由本次整合独立实现。FinQA 外部数据需使用者自行取得并核对数据许可；仓库只附合成示例，不将采购演示或合成财务数据描述为真实银行业务。

## 章节依据

- [码士 Harness 多智能体采购课程](https://www.mashibing.com/course/2959)
- [Langfuse 智能体评估课程](https://www.mashibing.com/course/2956)
- [公开 Harness 课程视频](https://www.bilibili.com/video/BV1Cs7h6MEsX/)
- [公开财务分析与评估视频](https://www.bilibili.com/video/BV1aZub6bE3W/)

公开线索支持采购业务、DeepAgents、MCP、沙箱、Skills、上下文、人工介入、异步 Agent、Langfuse 等主题。具体拆分顺序是本仓库的教学编排；文档证据检索、ERP 修复、离线演示、可靠评分投递和回归测试包含本次补充，不能标成官方原章节。
