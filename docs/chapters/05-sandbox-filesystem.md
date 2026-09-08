# 第 05 章：OpenSandbox 与虚拟文件系统

本章把“任务有一个沙箱”拆成用户映射、生命周期、代理引用、文件路由与执行结果五个问题。

## 代码入口

- [沙箱生命周期管理](../../src/agent/backends/sandbox_manager.py)与[稳定代理](../../src/agent/backends/sandbox_proxy.py)
- [OpenSandbox 适配](../../src/agent/backends/custom_opensandbox.py)
- [执行结果分类](../../src/agent/backends/execution_outcome.py)
- [预构建环境检查](../../src/agent/backends/sandbox_setup.py)
- [主图 CompositeBackend 路由](../../src/agent/graphs/main_agent.py)
- [本地 live 基础设施](../../docker/compose.live-infra.yml)与[沙箱镜像](../../docker/sandbox-image/Dockerfile)

## 学习重点

沙箱实例会失效，Agent 手中的稳定代理不应跟着失效。恢复时替换代理指向的后端，避免所有工具继续握着旧实例。`CompositeBackend` 将一般文件操作交给用户沙箱，将 `/memories/` 和 `/persisted-skills/` 路由到持久 Store。

沙箱连接失败与执行后丢失响应不同。当前将连接建立/连接池阶段错误标成 `not_dispatched`，其他未知错误保守标成 `outcome_unknown`；后者提醒先查文件、任务或业务记录，不能把超时当作未执行。分类和提示不等于通用命令已经具备端到端幂等性。

## 复现实验

```powershell
uv run --frozen pytest tests/test_sandbox_prebuilt_environment.py tests/test_async_sandbox_binding.py -q
uv run --frozen python -c "import httpx; from agent.backends.execution_outcome import execution_error_message; print(execution_error_message(httpx.ConnectTimeout('demo'))); print(execution_error_message(httpx.ReadTimeout('demo')))"
```

第一组测试验证已有依赖的镜像只做快速检查，不每次联网装包；还验证稳定代理替换后，异步任务绑定的是新沙箱。第二个命令应分别打印未派发和结果未知提示，不会真的连接沙箱。

## 依赖与边界

上述测试使用受控后端，不证明真实 Docker 容器恢复已经验收。实际沙箱需要 Docker、OpenSandbox 服务、专用镜像，以及容器内可访问的 ERP/报价页地址。不能把沙箱内的 `127.0.0.1` 当作宿主机。当前没有通用命令账本，也不对所有 shell 副作用提供 exactly-once 保证；ERP 写入的可靠性由业务幂等层另外承担。
