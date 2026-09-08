# 公开版本对比与本仓库补充范围

本表依据 2026-09-07 的公开源码静态对比记录，以及当前 ASu Agent Lab 的实际实现整理。公开仓库后续可能变化；“未见”表示当时核查的目录和主调用链没有发现，不是证明整个历史都不存在。没有确认所有仓库的学员身份，也不能从文件相同推断谁先复制谁。

本仓库直接复用的 MIT 基础版本、固定 commit 和独立新增范围见 [SOURCES.md](../SOURCES.md)。其他工程用于核对行为与发现缺口，不表示把无明确许可的源码整包移植进来。章节是推测顺序与本次补充，不是官方逐章目录；没有证据可以宣称所有官方内容已补齐。

## 参考版本分别提供了什么

| 参考仓库 | 对比发现 | 本仓库的处理 |
|---|---|---|
| [KagaribiDev/procurepilot](https://github.com/KagaribiDev/procurepilot) | 采购 Agent、YAML、沙箱、Skills、用户隔离、持久 Store 和独立异步分析已有较完整主干 | 保留主干与 MIT 许可，再补金融证据、评估和具体可靠性问题 |
| [KagaribiDev/java-erp](https://github.com/KagaribiDev/java-erp) | 有配套 ERP 和报价演示页；部分更新存在清空未提供明细的路径 | 独立实现兼容目标的 Java ERP，按实际提供字段更新，不复制未明确许可的原工程 |
| [chenqianlei51525/ERP_OPENCLAW](https://github.com/chenqianlei51525/ERP_OPENCLAW)、[junjun0228/ERP_OPENCLAW](https://github.com/junjun0228/ERP_OPENCLAW) | 有相同底座文件；所查基础版存在内存 Store 或较少生命周期模块 | 用于检查 checkpoint 与长期 Store 区别，不退回较弱的内存持久化方案 |
| [Running-hue/procureflow-agent](https://github.com/Running-hue/procureflow-agent) | Python ERP、54 路径契约和订单更新测试值得参考；主聊天身份仍有固定值 | 吸收接口与部分更新语义，保留 Java；实际用户由认证绑定 |
| [Ckingleeee/ERP_OPENCLAW](https://github.com/Ckingleeee/ERP_OPENCLAW) | 信用卡权益运营改造；有 10 条黄金例、轨迹采集和沙箱错误分类 | 独立补充合成评估、单次 SSE 观测与结果未知处理；不把信用卡权益运营称作企业授信尽调 |
| [hxlwd/leman](https://github.com/hxlwd/leman) | 从采购改成学习助手，包含文档摄取、检索与引用 | 借鉴证据回查目标，新增本地 FTS 文档证据链，没有照搬或宣称完成其向量/RAG 服务 |
| [Gitee gaoyanzhi/purchase_ai](https://gitee.com/gaoyanzhi/purchase_ai) | 独立采购工作流，涉及澄清、供应商、三单匹配及 Langfuse 观测；所查版本使用模拟数据 | 用于核对业务流程范围；本仓库没有因此宣称具备三单匹配、真实 ERP/SRM 生产接入 |
| [doneyli/langfuse-llm-certification-finance](https://github.com/doneyli/langfuse-llm-certification-finance) | 人工审核、数据回流、Prompt 再认证思路可借鉴；实际使用 FinanceBench 等，非目标 FinQA 同版 | 独立实现本地反馈、黄金集和发布门禁，保持数据集与项目身份区分 |
| [Cris-z123/coding-foreman](https://github.com/Cris-z123/coding-foreman) | 注释提及 `finqa_deepagent_observability`，没有找到可核验的原项目链接 | 只作为追踪线索，不将它当成已找到完整 FinQA + Langfuse 课程源码 |

## 缺口 → 实现 → 验证边界

“有测试”表示仓库中提供了相应验证代码；测试是否在指定环境运行通过，以实际验证报告为准。

| 对比发现的缺口或风险 | 本仓库现有实现 | 可复核入口 | 仍未实现或未验证的边界 |
|---|---|---|---|
| 订单部分更新把未提供的明细删除，客户端自动生成新编号/时间 | Java 更新保留省略字段，显式新明细才替换；MCP 只传实际字段 | [ERP 服务](../erp-service/src/main/java/dev/asu/erp/ErpService.java)、[订单 MCP](../src/mcp_server/tools/order_tools.py)、[测试](../tests/lab/test_mcp_orders.py) | 路径覆盖不是所有参数组合覆盖；不迁移原 Java 项目数据库 |
| 写入重试可能重复订单或丢失首次结果 | 事务内保存幂等键、请求指纹和响应；跨进程 Java/MCP 验收覆盖真实 HTTP | [Java 集成测试](../erp-service/src/test/java/dev/asu/erp/ErpIntegrationTest.java)、[HTTP MCP 验收](../tests/lab/test_real_erp_mcp.py) | 键为 ERP 数据库内服务级作用域；没有通用 shell 副作用幂等账本 |
| 金额通过 float 传递损失精度 | Java `BigDecimal`/数据库 DECIMAL、MCP 十进制字符串、金融 Decimal 工具 | [金额协议测试](../tests/lab/test_mcp_orders.py)、[计算器](../src/asu_finance/calculator.py) | 币种、量纲、报表期间不是自动推断或自动校验 |
| 有 checkpoint，但偏好/Skills 仍在内存或全局命名空间 | 保留 MongoDB Store；技能按 `users/user_id/skills` 隔离；记忆路由绑定用户 | [技能恢复](../src/agent/middlewares/user_skills_restore.py)、[隔离测试](../tests/test_user_skill_isolation.py) | 测试替身验证隔离算法；真实 MongoDB 集群、备份/容灾未验收 |
| 请求参数或固定用户名被当作真实身份 | Graph 工厂要求可信 user/thread；API 使用认证依赖；金融工具关闭模型自填 user_id | [阶段中间件](../src/agent/middlewares/stage_context.py)、[API 测试](../tests/finance/test_api.py) | ERP API Key 是服务身份，不是完整企业人员 RBAC/租户系统 |
| 沙箱恢复后仍持有旧引用；超时被当成未执行 | 保留稳定后端代理，区分 `not_dispatched` / `outcome_unknown`，提示核对状态 | [代理](../src/agent/backends/sandbox_proxy.py)、[错误分类](../src/agent/backends/execution_outcome.py) | 真正 Docker 沙箱失效/热替换未做 live 验收；不能保证未知命令自动安全重放 |
| 长任务关键约束只在容易裁剪的对话中 | 持久阶段、结构化约束、12 条近期里程碑；每次模型 request 重读并追加阶段指令 | [上下文](../src/asu_lab/context.py)、[图测试](../tests/test_finance_agent_wiring.py) | 未做真实模型窗口策略、Token 成本或任务完成率对照实验 |
| Prompt 只有静态散落文本，没有明确发布身份 | main/researcher/reviewer 使用本地 v1 文本和内容摘要标识 | [Prompt 加载器](../src/asu_lab/prompts.py) | 未接 Langfuse Prompt production 标签、远端缓存和自动热切换 |
| 采购角色更名成金融角色，缺少真实财务工具与证据 | 研究/独立复核两子图，绑定当前用户文档和 Decimal 工具 | [金融 YAML](../src/agent/subagents/configs/finance_researcher.yaml)、[主图](../src/agent/graphs/main_agent.py) | 先研究再复核由 Prompt 指导，非硬编码顺序状态机；不是授信规则引擎 |
| 普通子 Agent 自动继承沙箱 execute，角色说明不足以限制能力 | 金融角色作为 `CompiledSubAgent`，只注册精确选择的金融工具 | [真实 DeepAgents 接线测试](../tests/test_finance_agent_wiring.py) | 主采购 Agent 仍保留其沙箱能力；不是全平台统一细粒度授权引擎 |
| 文档结论缺少可回查来源 | TXT/MD 行号、CSV 表头/行号、PDF 页码、引用 ID、按用户/分组过滤 | [证据库](../src/asu_finance/evidence.py)、[证据测试](../tests/finance/test_evidence.py) | **FTS5 词法检索，不是向量 RAG**；没有 OCR、embedding、reranker 或语义召回率数据 |
| 没有可用的 FinQA 数据适配，或把 FinanceBench 混称 FinQA | 外部 FinQA JSON 读取、表格证据归一化、split 隔离、标签与检索分离 | [FinQA 适配](../src/asu_finance/finqa.py)、[测试](../tests/finance/test_finqa.py) | 不自动下载全量数据；附带数据均合成；**FinanceBench 不是 FinQA**；不实现完整官方算术语言 |
| 小规模评估缺少可运行可靠队列 | 独立 EvaluationWorker、租约、fencing token、原子结果/Outbox、重试 | [队列](../src/asu_eval/store.py)、[Worker 测试](../tests/evaluation/test_durable_worker.py) | SQLite 面向本地/小规模，未做多节点生产压测；离线模式故意保留待投递记录 |
| 只有回答文本，没有明确的执行观测证据 | 单次迭代 SSE，保留已见 token/工具事件，完成或取消时入队快照 | [观测包装](../src/asu_lab/observability.py)、[流测试](../tests/lab/test_observation_context.py) | 写入状态来自工具事件推断，不等于数据库审计；没有完整 Token 用量/成本采集 |
| Langfuse 分数与 Trace 缺少可靠关联 | 稳定用户作用域 Trace/Span ID、OTLP 完成快照、Score REST 投递、先 Trace 后分数 | [发送器](../src/asu_eval/delivery.py)、[契约测试](../tests/evaluation/test_delivery_api.py) | **OTLP 是完成快照根 span，不是完整逐 token / generation / tool Trace 树；Langfuse live 未验证** |
| 人工反馈不能沉淀，回归缺少发布门禁 | 反馈、核对后的标准答案、明确提升到黄金集、逐用例/指标门禁 | [评估 API](../src/asu_eval/api.py)、[门禁](../src/asu_eval/gate.py) | 本地闭环，不是 Langfuse 云端 AnnotationQueue/Dataset 同步；无线上抽样 LLM judge |
| 黄金例被包装为实测模型成绩 | **12 条合成黄金例**，提供通过/回退两套预写输出，CI 检查正确退出码 | [golden](../evals/golden.synthetic.json)、[baseline](../evals/predictions.baseline.json)、[regressed](../evals/predictions.regressed.json) | **没有真实 LLM benchmark**；不能据此宣称任务完成率、幻觉率或授信准确率改善 |
| 前端只展示聊天，无法实际操作证据与评估 | 三页工作台、显式导入、引用回查、计算、队列详情、反馈/黄金集 | [Vue 工作台](../frontend/src/components/LabWorkspace.vue)、[demo API](../src/asu_lab/app.py) | demo 聊天是合成流程，横条明确不调用模型；前端构建不能替代浏览验收 |
| 多服务依赖散落，没有统一启动与检验入口 | 启动器预检、进程树回收、数据目录约定、CI、demo/live Compose | [启动器](../start_all.py)、[CI](../.github/workflows/quality.yml)、[第 14 章](chapters/14-validation-deployment.md) | Docker、MySQL、OpenSandbox 和云端模型需单独运行验收；不是生产高可用部署 |

## 尚未纳入本次补充的业务能力

银行外部征信、企业工商与诉讼数据、真实财报授权接入、授信政策与风险定价、专家审核工作流、监管留痕、贷后监控和生产级权限治理均未实现。采购侧也没有实现真实发票/收货/采购单三单匹配、多仓批次、支付结算与物流供应商集成。

保留这些边界可以明确下一步要验证或新增什么。现在可以复现的是采购协议与本地业务一致性、用户隔离、财务证据与计算、真实图接线的无网络测试、合成工作台和持久评估闭环，不能把它们直接等同于真实银行上线系统。
