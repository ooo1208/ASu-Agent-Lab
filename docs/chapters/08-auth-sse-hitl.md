# 第 08 章：用户认证、SSE 与人工介入

本章沿“登录身份 → 会话归属 → 工具中断 → 明确恢复”检查一次写操作。页面中的确认按钮必须对应后端可验证的状态，不能只给模型增加一句提示。

## 代码入口

- [live 认证服务](../../src/api_view/auth_service.py)与[认证路由](../../src/api_view/api/auth.py)
- [聊天 SSE、中断与恢复](../../src/api_view/api/chat.py)
- [订单人工补字段工具](../../src/agent/tools/hitl_tools.py)与[审批配置](../../src/agent/subagents/configs/procurement_order.yaml)
- [本地 demo 身份](../../src/asu_lab/local_auth.py)与[演示 API](../../src/asu_lab/app.py)
- [前端中断面板](../../frontend/src/components/InterruptBanner.vue)

## 学习重点

缺字段与最终审批是两种中断：前者要求补充必要参数，后者决定是否执行已准备好的写操作。聊天、历史、证据与评估均从认证依赖取得用户，不允许正文里的 `user_id` 覆盖身份。已取消、拒绝或结果未知的操作不能直接按“成功”继续。

SSE 按 token、工具开始/参数/结果、中断和完成事件向浏览器更新。第 11 章的观测包装器旁路读取同一条流，不启动第二个消费者。客户端取消后保留已观察到的片段，并记录任务未完成。

## 复现实验

```powershell
uv run --frozen pytest tests/lab/test_app_integration.py tests/finance/test_api.py tests/lab/test_observation_context.py -q
```

测试创建两个独立账号，核对跨用户会话、引用和记录不可见；对合成下单发起中断，批准后才调用受控 ERP 边界；拒绝和取消不产生写入；客户端未收到可靠结果时进入待核查状态。这些测试不使用真实模型。

手工体验可以启动第 13 章的 demo，注册账号后输入 `演示下单 1 件`，观察“提出操作”与“批准执行”两个阶段。

## 依赖与边界

demo 的状态机用于复现界面、身份和审批流程，不等于 live Agent 运行。live 使用 JWT、MongoDB checkpoint 和真实工具，中断恢复还需要用户原有上下文。`tests/test_auth_isolation.py` 与 `tests/test_sse_stream.py` 属于需服务的集成测试，不应把默认跳过它们解释为通过；真实模型链路需单独启用并承担调用费用。
