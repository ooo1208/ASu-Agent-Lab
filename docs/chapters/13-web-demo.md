# 第 13 章：Web 工作台与本地演示

本章把已经实现的 API 接成可以操作的三页工作区：聊天、证据工作台、评估中心。

## 代码入口

- [Vue 顶层导航](../../frontend/src/App.vue)与[证据/评估工作台](../../frontend/src/components/LabWorkspace.vue)
- [前端认证请求](../../frontend/src/api/client.js)
- [本地 demo API](../../src/asu_lab/app.py)与[真实 Agent Web 入口](../../src/api_view/web_main.py)
- [共享数据路径](../../src/asu_lab/settings.py)与[启动器](../../start_all.py)

## 学习重点

证据页先选择文件或填入合成文本，只有点击导入才上传；检索结果展示文档、页/行与引用 ID。评估页提交 actual/expected 快照，先显示等待/执行状态，后台完成后再展示分数；离线未发送的 Outbox 不显示为已同步。反馈与加入黄金集是两个明确操作。

demo 横条明确标出“本地合成演示，不调用大模型”。它可以操作真实本地证据库、Decimal 工具、评估作业和配置的合成 ERP，但其聊天路由不是模型推理。live 使用另一套应用入口与外部依赖，不能因为界面相同就混淆两种运行模式。

## 复现实验

从项目根目录准备依赖后：

```powershell
uv sync --locked
npm --prefix frontend ci
uv run --frozen python start_all.py --mode demo
```

打开 `http://127.0.0.1:5173`，注册个人账号，然后依次操作：

1. 在证据页点击“填入合成财报样例”，确认尚未入库，再点击导入。
2. 搜索“营业收入”，回查片段，计算 100 → 120 的增长率。
3. 在评估页提交“差错样例”，等后台评分后查看数字与引用失败项。
4. 填写反馈、核对标准答案、加入 `reviewed-v1`，查看黄金集。

要体验真实本地 Java 合成订单，先打包 ERP，再用 `--erp` 启动；未启动 ERP 时，订单执行应提示服务问题，而不是返回虚假的成功。

```powershell
mvn -f erp-service/pom.xml package
uv run --frozen python start_all.py --mode demo --erp
```

## 验证与依赖边界

```powershell
npm --prefix frontend run build
uv run --frozen pytest tests/lab/test_app_integration.py tests/finance/test_api.py tests/evaluation/test_delivery_api.py -q
```

前端需要 Node，Python 端需要项目依赖；`--erp` 额外需要 Java。演示默认不要求 MongoDB、Docker、OpenSandbox、模型密钥或 Langfuse。页面每 5 秒刷新任务，关闭 Worker 后 pending 状态会持续保留，这与“正在评测”不同。构建通过验证源码可编译；完整人工浏览验收与外部模型验收仍应分别记录。
