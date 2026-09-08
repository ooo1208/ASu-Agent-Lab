# 第 02 章：Java ERP 与业务一致性

本章为对公开材料进行比对后推测的学习顺序，不是官方原始章节。

Agent 的写操作需要一个能明确校验参数、保留状态并拒绝重复副作用的业务系统。本章独立实现 Spring Boot ERP，提供 54 条 REST 路由和 8 个 MCP 工具所需契约。

- 入口：[ERP 使用与接口契约](../../erp-service/README.md)、[54 条路径清单](../../erp-service/src/test/resources/endpoint-manifest.json)。
- 八张关系业务表，金额使用 DECIMAL，数据库外键、唯一键和 CHECK 约束。
- 订单部分更新保留未提供字段；库存竞争避免超卖；幂等键与请求体共同校验，重启后仍可重放已确认结果。
- 所有种子为合成数据；默认使用持久化 H2，另提供 MySQL 配置。

验证：12 项 Java 集成测试通过；独立 JAR 真实 HTTP 调用及进程重启后的订单幂等验证通过。详细结果见 `erp-service/VERIFICATION.md`。MySQL 与 Docker 尚未实际运行。

练习：使用相同幂等键重复发送同一个订单，应返回原订单；更换金额但沿用同一幂等键，应返回冲突。不要将全局写锁和内存分页当作高并发生产实现。
