# Brief — 修复未绑定账号 OAuth 自动刷新

## Goal

- 修复未绑定 cc2api 的账号在 AT 临期或运行中遇到 401 时，因为 refresh 请求扩大 OAuth scope 而持续 `invalid_scope`、无法轮换 AT/RT 的问题，并让后台刷新失败具备脱敏、可持久查询的诊断状态。

## Scope

- 后台临期刷新和 worker 401 强刷只沿用 `claudeAiOauth.scopes` 中已有的有效 scope；无有效 scope 时省略 `scope` 字段。
- 刷新成功后正确写回 AT、可选新 RT、过期时间和服务端返回的 scope；响应无 scope 时保留原值。
- 为未绑定账号增加后台刷新最后尝试时间、状态和脱敏错误摘要，并通过账号列表 API 返回安全字段。
- 保持现有 10 分钟刷新窗口、Node + sidecar + 账号代理网络、owner/profile/file lock、并发 RT 轮换和 cc2api managed OAuth 边界。
- 增加 orchestrator 与 worker 刷新路径的回归测试、shell 语法检查和 Compose/质量检查。
- 代码验证通过后发布 orchestrator/worker 镜像，部署到 `.deploy/vibecoding-bench.env` 指向的服务器并做低风险验证。

## Non-Goals

- 不在 task 启动前新增强制刷新。
- 不修改 cc2api OAuth 所有权、养号调度、账号并发数、代理配置或风控策略。
- 不替生产账号执行重授权，不通过修改生产凭据过期时间或并行试刷 RT 做破坏性验证。
- 不把 token endpoint 完整响应或任何 AT/RT、Authorization、Cookie、代理密码写入日志、数据库或任务产物。

## Key Context

- 根因已由历史线上日志确认：账号凭据只有 5 个 scope，自定义后台/401 刷新额外请求 `user:design:read`、`user:design:write`，服务端返回 `HTTP 400 invalid_scope`；同类账号曾连续 159 次 `auth_failed`。
- 主要代码入口：`orchestrator/main.py` 的 refresh probe、`OAuthRefreshScheduler`、accounts schema/API；`images/worker/entrypoint.sh` 的 401 强刷；测试位于 `orchestrator/test_main.py`。
- 状态列计划为 `oauth_refresh_last_attempt_at`、`oauth_refresh_last_status`、`oauth_refresh_last_error`，通过 `_ensure_column` 兼容旧 SQLite。
- 外部 Docker/OAuth IO 必须在 `_db_lock` 外；状态写入使用参数化 SQL 和短事务。单账号失败不得终止后续账号扫描。
- orchestrator 与 worker 必须同时发布；只更新一侧会留下另一条错误 scope 路径。远程升级必须 pull 后 force-recreate，不能只 restart。

## Acceptance

- 两条未绑定账号刷新路径不再硬编码或追加 `user:design:*`；5-scope fixture 刷新成功，无 scope 时请求省略该字段。
- 成功写回 AT/RT/expiresAt/scopes 的语义正确，失败状态可查询且不泄漏敏感信息。
- `invalid_scope`、`invalid_grant`、429、重复/空 scope、单账号失败继续扫描、绑定账号不走本地刷新均有回归覆盖。
- `python3 -m unittest orchestrator.test_main`、`bash -n images/worker/entrypoint.sh`、Compose 检查和 Trellis 全量检查通过。
- 发布部署后容器健康、调度器持续运行、账号 API 返回安全状态字段，后续自然刷新不再出现 `invalid_scope`。

## Next Step

- 用户确认本 brief 后运行 `task.py start`，再通过 `trellis-route(target=implement)` 进入实现；完成后进入统一检查、发布和远程验证。
