# 第 10 章：文档证据与财务工具

本章补上采购底座没有提供的财务证据链：导入原文 → 检索片段 → Decimal 计算 → 引用回查与独立复核。

## 代码入口

- [SQLite FTS5 证据库](../../src/asu_finance/evidence.py)
- [Decimal 计算与白名单算术解释器](../../src/asu_finance/calculator.py)
- [FinQA 外部 JSON 适配](../../src/asu_finance/finqa.py)
- [确定性复核](../../src/asu_finance/review.py)、[用户绑定工具](../../src/asu_finance/tools.py)、[HTTP 路由](../../src/asu_finance/api.py)
- [合成样例](../../examples/finance/)与[完整模块说明](../finance.md)

## 学习重点

TXT/Markdown 保留行号，CSV 每个数据行带表头，文本 PDF 保留页码。每个引用 ID 都可按用户与资料分组回查原文。财务计算拒绝 float、除零和任意程序；百分比结果 `20` 代表 20%，输入单位与期间仍需人工或 reviewer 核对。

检索是 FTS5 词法检索，中文补充双字词，不是 embedding、向量 RAG、混合检索或重排。`review_financial_claim` 只检查引用访问、字面数字是否出现及算术，不证明财报真实性或业务结论正确。

FinQA 适配只导入用户自行取得的官方 JSON。`train/dev/test/private_test` 分开保存，答案、program 和 gold references 不进入检索文本；private_test 不伪造标签。仓库自带文件是合成格式样例，不是原始 FinQA、FinanceBench 或真实银行数据。

## 复现实验

```powershell
uv run --frozen python examples/finance/demo.py
uv run --frozen python -m asu_finance --db .local/chapter10.sqlite3 --user learner ingest examples/finance/synthetic_report.md
uv run --frozen python -m asu_finance --db .local/chapter10.sqlite3 --user learner search "营业收入"
uv run --frozen python -m asu_finance program "subtract(120,100), divide(#0,100), multiply(#1,const_100)"
uv run --frozen pytest tests/finance -q
```

应得到 20% 增长率、原文片段与计算记录；换一个用户检索相同数据库，不应看到原用户的文档。测试还验证 CSV 多行锚点、真实生成 PDF 的页码、跨用户引用拒绝和 FinQA 标签隔离。

## 依赖与边界

基础功能使用 Python 标准库与支持 FTS5 的 SQLite，PDF 需要 `pypdf`。扫描件 OCR、语义向量检索、完整 FinQA 运算语言、全量数据评测与真实授信风险规则尚未实现。金融 Agent 接线在第 04/07 章；没有真实模型的研究/复核准确率结论。
