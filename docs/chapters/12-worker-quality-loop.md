# 第 12 章：Worker、Outbox 与质量闭环

本章让评分离开聊天主链路，并保留失败可恢复、结果可追踪、人工修正可复用的状态。

## 代码入口

- [EvaluationJob、结果、Outbox 和反馈存储](../../src/asu_eval/store.py)
- [独立 Worker](../../src/asu_eval/worker.py)
- [用户隔离的评估 API](../../src/asu_eval/api.py)
- [合成输出入队](../../src/asu_eval/seed.py)与[回归门禁](../../src/asu_eval/gate.py)
- [黄金集与基线](../../evals/)、[CI 配置](../../.github/workflows/quality.yml)

## 学习重点

作业通过 lease 和 fencing token 领取，过期工作进程不能覆盖后续领取者的结果。评分结果与 Outbox 在同一事务中写入；投递失败使用重试和稳定远端 ID，Trace 投递完成后再发关联 Score。当前是可恢复的至少一次投递方案，不声称远端系统具备绝对 exactly-once 语义。

`offline` Worker 正常完成评分，但把远端 Outbox 留在 pending，不会假装已同步。人工反馈需给出经核对的 `corrected_expected`，再明确提升为某个版本的黄金用例。门禁同时检查总分、逐指标/逐用例回退、强制安全检查和数据集/评分器版本一致性。

## 复现实验

```powershell
uv run --frozen python -m asu_eval.seed --db .local/chapter12.sqlite3 --user-id learner
uv run --frozen python -m asu_eval.worker --db .local/chapter12.sqlite3 --delivery offline --once
uv run --frozen pytest tests/evaluation/test_durable_worker.py tests/evaluation/test_delivery_api.py tests/evaluation/test_scoring_gate.py -q
```

Worker 输出中 evaluation_jobs 应出现 complete，score_outbox 仍是 pending，这是离线模式的预期行为。随后验证故意回退的输出不能通过：

```powershell
uv run --frozen python -m asu_eval.gate --dataset evals/golden.synthetic.json --predictions evals/predictions.regressed.json --baseline evals/baseline.synthetic.json
$LASTEXITCODE
```

最后应打印退出码 `1`。`0` 表示门禁通过，`2` 表示配置/数据错误，不能把配置错误当作正确检出了回归。

## 依赖与边界

SQLite 数据库必须与 Web/Worker 指向同一路径；不同文件不会自动同步。API 和 UI 已提供本地反馈/黄金集闭环，但没有实现 Langfuse 云端 AnnotationQueue 的管理界面、云端黄金集同步、线上抽样 LLM judge 或全自动 Prompt 再认证。Langfuse live 投递未核验，默认离线可复现路径不依赖其可用性。
