# 第 11 章：观测与确定性评估

本章从已记录的执行证据产生可重复分数，区分“看见了什么”与“能验证什么”。

## 代码入口

- [SSE 单次消费旁路观察](../../src/asu_lab/observability.py)
- [完成快照入队接口](../../src/asu_eval/capture.py)
- [十类确定性评分](../../src/asu_eval/scoring.py)
- [OTLP 完成快照与 Score 发送器](../../src/asu_eval/delivery.py)
- [合成黄金用例](../../evals/golden.synthetic.json)与[评估说明](../evaluation.md)

## 学习重点

观测保存回答片段、已观察到的工具事件、耗时、版本与完成/中断状态。它沿原 SSE 迭代一次并原样返回分片；异常和取消时仍尽量保存部分快照。工具事件推断的写入状态不是数据库审计记录，不能代替业务事务结果。

评分器按 expected 中声明的维度评分：数值容差、证据召回、引用范围、完成状态、工具选择、参数完整、审批保护、禁用工具、时延预算与 Token 预算。缺少必要的实际执行证据应失败，未声明的指标不强行补一个分数。规则评分没有调用 LLM-as-a-judge。

仓库提供 12 条合成黄金用例及预先编写的 baseline/regressed 输出，检验评估器和门禁是否能发现人为设置的错误。它们不是模型现场生成的 benchmark，不能把样例通过率写成模型或信贷业务准确率。

## 复现实验

```powershell
uv run --frozen pytest tests/lab/test_observation_context.py tests/evaluation/test_scoring_gate.py tests/evaluation/test_delivery_api.py -q
uv run --frozen python -m asu_eval.gate --dataset evals/golden.synthetic.json --predictions evals/predictions.baseline.json --baseline evals/baseline.synthetic.json
```

观察流测试验证源只被消费一次、工具结果按 ID 关联、入队失败不替换原回答。评分测试验证数字与证据错误、参数缺失和审批风险能被检出。发送器测试检查请求形状与失败处理，使用受控 Transport，不把它们算成 Langfuse live 验收。

## 依赖与边界

本地规则评估不需要模型或 Langfuse。可选远端投递把一个已完成快照作为 OTLP 根 span 发送，并关联 Score；它不是逐 token、逐模型 generation、逐工具的完整 Trace 树。SSE 未提供完整 Token 用量时不会凭空补齐，也没有真实单次调用成本核算。Langfuse 远端鉴权、写入后看板可见性与版本兼容仍需 live 核验。
