# 实施计划

## 1. 代码实现

- [ ] 在 `orchestrator/main.py` 为账号表补充 OAuth 后台刷新状态列及幂等迁移。
- [ ] 实现 scope 归一化和脱敏错误摘要的最小内部 helper，签名和字段以现有 credentials 结构为准。
- [ ] 修改后台 Node refresh probe：只使用已有 scopes，无有效 scope 时省略 `scope`，成功后保留/更新 scopes。
- [ ] 修改 worker 401 强刷：应用相同 scope 与写回规则，不改变锁、等待和退出码语义。
- [ ] 修改 `OAuthRefreshScheduler`：真实尝试后写 success/failed 状态，单账号失败继续扫描。
- [ ] 账号列表 API 返回新增安全字段；不新增 token 或原始响应字段。

## 2. 自动化验证

- [ ] 扩展 `orchestrator/test_main.py`，覆盖 5-scope、缺失/空/重复 scope、成功写回和失败脱敏。
- [ ] 覆盖调度器单账号失败不阻断后续账号及绑定账号不走本地刷新。
- [ ] 运行 `python3 -m unittest orchestrator.test_main`。
- [ ] 运行 `bash -n images/worker/entrypoint.sh`。
- [ ] 运行相关 Compose 配置检查。

## 3. 规范与质量检查

- [ ] 更新 OAuth refresh spec，明确 refresh 只能沿用已有 scope、缺失时省略。
- [ ] 通过 `trellis-check-all` 全范围检查，根据结果修复并复检。

## 4. 发布与远程验证

- [ ] 按项目发布流程提交/push，等待 orchestrator/worker 镜像构建完成。
- [ ] 检查远程连接数与当前运行任务，选择低风险窗口。
- [ ] 远程 pull 新镜像并 force-recreate orchestrator；不得只 restart。
- [ ] 验证容器镜像、服务健康、账号 API 新状态字段和调度器持续运行。
- [ ] 不主动修改生产 token 过期时间；等待自然临期或使用非生产 fixture 验证不再产生 `invalid_scope`。

## 风险点

- OAuth refresh token 会轮换，禁止用生产 RT 做并行试刷。
- orchestrator 与 worker 任一漏部署都会保留一条旧 scope 路径。
- 错误摘要必须防止 token endpoint 原始响应携带敏感信息。
- 账号表写状态不能在持有 `_db_lock` 时执行 Docker/OAuth 网络 IO。

## 回滚点

- 代码回滚到上一个镜像 tag并 force-recreate。
- 新增 SQLite 列保留，不执行破坏性 schema 回滚。
