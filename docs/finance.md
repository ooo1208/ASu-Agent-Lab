# 财务文档证据与确定性计算

本模块补上“财务分析 Agent”中需要实际执行的证据和计算链路：导入文档 → 检索原文 → Decimal 计算 → 独立核查引用和数字。实现位于 `src/asu_finance/`，默认离线可运行，不需要向量数据库、云账号或大模型密钥。

这是本仓库新增的实现。示例是合成教学数据，不是官方课程原始代码，不代表真实信贷项目业绩；本模块不输出授信额度、贷款审批结论或投资建议。

## 1. 本地运行

在仓库环境中安装项目后，从项目根目录执行：

```powershell
python examples/finance/demo.py
python -m asu_finance --db .data/finance.sqlite3 --user demo ingest examples/finance/synthetic_report.md
python -m asu_finance --db .data/finance.sqlite3 --user demo search "营业收入"
python -m asu_finance program "subtract(120, 100), divide(#0, 100), multiply(#1, const_100)"
python -m pytest tests/finance -q
```

第一个脚本在临时数据库中完成全链路，输出收入增长率 `20`、单位 `percent`、计算过程、原始引用和核验结果。`requires_semantic_review: true` 表示仍需核对单位、报表期间、公司主体和语义支持；规则通过不等于专业结论通过。

CLI 是本地管理入口，`--user` 用于选择本地所有者。在 HTTP 和 Agent 工具中，用户身份由经过验证的认证依赖绑定，不能让模型或请求正文指定。

## 2. 文档与引用

```python
from pathlib import Path
from asu_finance import EvidenceStore

store = EvidenceStore(".data/finance.sqlite3")
path = Path("examples/finance/synthetic_financials.csv")
document = store.ingest("trusted-user-id", path.name, path.read_bytes(), namespace="research")
hits = store.search("trusted-user-id", "revenue", namespace="research")
source = store.get_citation("trusted-user-id", hits[0]["citation_id"], namespace="research")
```

| 格式 | 定位信息 | 处理规则 |
|---|---|---|
| UTF-8 TXT / Markdown | 文档名、起止行、片段 ID | 按最多 12 行、4000 字符切块；长行拆分仍保留原行号 |
| UTF-8 CSV | 文档名、真实起止行、表格行号、列名、原始单元格 | 每个数据行附带表头，支持带换行的 CSV 单元格 |
| 文本 PDF | 文档名、从 1 开始的页码、页内文本行、片段 ID | 可选 `pypdf`；不包含 OCR，扫描件或加密文档给出明确错误 |
| 外部 FinQA JSON | example_id、split、`text_n` / `table_n`、表头和单元格 | 使用 JSON 内证据键，不伪造 PDF 页码；gold 标签不进入检索 |

每个片段可通过 `citation_id` 回查完整文本和元数据。查询、引用回查、删除都同时过滤 `user_id` 和 `namespace`，对不存在和无权访问的引用返回相同结果。删除文档时同步删除 FTS 索引，避免已经删除的证据继续被检索。

SQLite 使用 FTS5 词法检索，英文按词召回，中文补充双字词召回。它不是 embedding、混合检索或重排模型，也不具备同义改写的语义召回能力。问题很抽象时，Agent 应改写为文档中的实体、指标和年份；后续可在保持相同引用与权限接口的基础上增加向量检索。

文档上限 10 MiB；提取后的文本同样限制为 10 MiB、最多 10000 片段；PDF 最多 500 页。大规模生产导入、OCR、恶意 PDF 隔离和后台任务队列属于后续部署扩展。本地 SQLite 文件应放在受权限保护的位置；同一台机器上的数据库文件访问权限不由应用内用户过滤替代。

## 3. Decimal 工具

```python
from asu_finance import calculate, evaluate_program

calculate("add", {"a": "0.1", "b": "0.2"})  # result: "0.3"
calculate("gross_margin", {"revenue": "120", "cost": "72"})  # 40 percent
evaluate_program("subtract(120,100), divide(#0,100), multiply(#1,const_100)")
```

| operation | 必须提供的参数 | 单位 |
|---|---|---|
| add / subtract / multiply | a, b | number |
| divide | a, b | ratio |
| ratio | numerator, denominator | ratio |
| change_rate | old, new | percent；分母使用 abs(old) |
| debt_ratio | liabilities, assets | percent |
| current_ratio | current_assets, current_liabilities | ratio |
| gross_margin | revenue, cost | percent |
| net_margin | net_profit, revenue | percent |
| return_on_equity | net_profit, equity | percent |

数字通过十进制字符串传入，避免先经过二进制 float；API 拒绝浮点 JSON 值。输出保留公式、输入、结果和单位，除法使用 50 位有效数字精度。`percent` 中 `20` 表示 20%，不是 0.20。输入的币种、金额尺度和统计期间需要由调用者对齐；ROE 使用传入的 equity，如果业务口径要求平均净资产，应先计算该值。

程序解释器只允许平坦的 `add`、`subtract`、`multiply`、`divide`，支持数字、`const_100` / `const_m1` 和前序结果 `#0`。不会执行 Python `eval`。完整 FinQA 还含有其他运算；`table_*`、嵌套表达式、幂运算和未知操作会明确拒绝，不冒充完整官方程序执行器。

## 4. FinQA 外部数据适配

字段结构参考 [FinQA 官方数据说明](https://github.com/czyssrs/FinQA#dataset)。适配器读取用户自行取得的 `train.json`、`dev.json`、`test.json`、`private_test.json`，不在安装、测试或启动时自动下载全量数据。官方公开 `private_test` 不提供答案和 gold references；本适配器在 private_test 模式下始终丢弃这些标签。

```powershell
# 合成格式样例，不是原始 FinQA 数据
python -m asu_finance --user demo --namespace finqa import-finqa examples/finance/synthetic_finqa.json --split train
python -m asu_finance --user demo --namespace finqa:train search revenue

# 已自行取得的本地文件
python -m asu_finance --user demo --namespace finqa import-finqa C:/datasets/FinQA/train.json
```

```python
from asu_finance.finqa import load_finqa, import_finqa

examples = load_finqa("C:/datasets/FinQA/dev.json")
public_input = examples[0].to_dict()  # 默认不包含 answer / program / gold_evidence
offline_labels = examples[0].to_dict(include_labels=True)  # 仅供离线评估端使用
mapping = import_finqa(store, "trusted-user-id", examples, namespace="finqa")
```

导入结果附带 `example_id`，供评估端关联标签；检索库只保存 pre_text、表格、post_text。question、答案、程序和 gold supporting facts 都不会追加到报告文本中。每个 split 自动使用独立命名空间，例如 `finqa:train`，防止默认混搜训练与测试证据。重复导入会产生新文档，应保存导入映射并删除旧文档后再替换；当前不对跨样本的相同报告做自动去重。

## 5. 接入主 Agent / Researcher / Reviewer

```python
from asu_finance import create_finance_tools
from asu_finance.tools import finance_functions

# 必须在已验证用户身份后创建，不能缓存成全局所有用户共用的一组工具。
tools = create_finance_tools(store, authenticated_user.user_id, namespace="research")
# 传给 create_deep_agent 或绑定到 researcher / reviewer 的工具列表。
# 无 LangChain 时可调用同名纯函数。
functions = finance_functions(store, authenticated_user.user_id, namespace="research")
```

提供五个工具：`search_financial_evidence`、`get_financial_citation`、`calculate_financial_metric`、`run_financial_arithmetic`、`review_financial_claim`。工厂可按请求绑定可信用户，模型工具参数中没有 `user_id`。

Researcher 应返回带引用的事实、明确单位和年份的计算输入，以及工具计算结果。Reviewer 重新回查引用，核验算式、数字是否在原文出现，再人工或模型检查币种、期间、公司主体、来源可靠性和结论支持程度。当前确定性 reviewer 只检查引用访问、字面数字覆盖和算术，无法独立证明财报真实性或推导贷款审批决策。

## 6. 挂载 FastAPI

```python
from asu_finance import create_finance_router

# existing_auth 必须校验 JWT / 会话，返回有 user_id 的对象、字典或可信字符串。
app.include_router(create_finance_router(store, auth_dependency=existing_auth))
```

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | /finance/documents | JSON 导入；filename, content, encoding, namespace |
| GET | /finance/search?q=revenue | 检索；支持 namespace 和 limit |
| GET | /finance/citations/{citation_id} | 回查证据 |
| DELETE | /finance/documents/{document_id} | 删除自己命名空间内的文档 |
| POST | /finance/calculate | operation + 十进制字符串 values |
| POST | /finance/program | 白名单算术 program |
| POST | /finance/review | operation、values、reported_value、citation_ids、namespace |

文本导入示例正文：

```json
{"filename":"report.txt","content":"revenue 120","encoding":"utf-8","namespace":"research"}
```

PDF 使用 `encoding: "base64"` 和 Base64 文件内容，不需要额外 multipart 依赖。API 不接受服务端路径，也不在正文接受 `user_id`；正文多余字段直接返回 422。无权访问和不存在的引用均返回 404。FastAPI 和 LangChain 仅在对应适配器被导入时需要，基础 evidence / calculator / FinQA / CLI 模块使用 Python 标准库，PDF 额外使用 `pypdf`。

## 7. 验证范围

`tests/finance/` 覆盖持久化、中文和英文召回、跨用户/namespace 隔离、CSV 多行锚点、PDF 页码、删除后索引清理、Decimal 精度、除零、任意程序拒绝、FinQA 表头归一化和标签不泄漏、认证路由及模型工具身份绑定。样例输出不计为真实模型准确率或金融业务效果指标。
