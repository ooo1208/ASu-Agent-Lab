# 第 06 章：Skills 与长期记忆持久化

对话 checkpoint、用户偏好和动态 Skills 是不同的数据。对话可以恢复，并不表示放在内存 Store 里的技能也能跨进程恢复。

## 代码入口

- [本地 Skills](../../src/skills/)与[技能分配工具](../../src/agent/tools/assign_skill.py)
- [本地技能同步](../../src/agent/middlewares/skills_sync.py)
- [用户技能恢复](../../src/agent/middlewares/user_skills_restore.py)
- [MongoDB Store](../../src/agent/stores/mongodb_store.py)
- [用户偏好更新](../../src/agent/middlewares/memory_update.py)
- [命名空间配置](../../src/agent/core/config.py)

## 学习重点

静态 Skills 提供可读操作指南和脚本，动态分配的技能需要保存后才能在新沙箱中恢复。用户技能命名空间为 `("users", user_id, "skills")`，相同技能名不能让不同用户覆盖彼此内容。恢复逻辑需要遍历所有分页结果，不能因为 Store 的默认页面较小而漏掉文件。

主图的记忆路由绑定可信请求用户，金融子 Agent 不继承写文件和技能分配能力。偏好摘要只是对话的辅助信息，不是采购写操作授权。

## 复现实验

```powershell
uv run --frozen pytest tests/test_user_skill_isolation.py tests/test_mongodb_store_namespace.py -q
```

测试为 Alice、Bob 保存同名不同内容的技能，分别恢复后应只看到自己的版本；再写入超过 Store 默认分页数量的文件，确认完整恢复。命名空间测试还检查 `("a/b", "c")` 与 `("a", "b/c")` 不会因字符串拼接而发生碰撞。

## 依赖与边界

这里的回归测试用内存测试 Store 和假沙箱验证隔离算法，不需要 MongoDB；实际跨进程持久化需要 live MongoDB。仓库保留了持久 Store 实现，但没有用这些测试宣称真实 MongoDB 集群容灾、备份恢复或权限配置已经验收。用户能够保存的 Skills 也不自动成为可信系统指令；运行权限仍由工具和沙箱边界限制。
