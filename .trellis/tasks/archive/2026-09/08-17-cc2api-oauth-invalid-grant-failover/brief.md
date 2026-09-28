# Brief — 修复 cc2api OAuth 永久失效账号自动停用与切号

## Goal

- 当请求转发前的 OAuth refresh 返回账号级永久凭据错误时，立即停用异常账号并在同一请求内切换到下一个可用账号，避免失效 RT 持续被调度和请求反复返回 503。

## Scope

- 为 OAuth refresh 增加结构化永久凭据错误类别；`invalid_grant` 和明确缺失 refresh token 进入永久错误，429、5xx、网络/超时、解析失败及其他未明确错误保持临时错误。
- 永久错误写入脱敏 `auth_error`，不允许 fallback 到旧 AT；临时错误继续允许使用仍有效 AT。
- `/v1/messages` 与 `/v1/messages/count_tokens` 遇到永久错误时调用现有 `disable_for_auth_failure()`，排除当前账号、释放资源并继续账号循环。
- 覆盖普通请求、sticky 会话、count_tokens、全部账号失效以及临时错误不误停的回归测试。
- 运行 Rust 格式检查、定向测试和全量 `cargo test`，并补充 cc2api 后端服务架构规范。

## Non-Goals

- 不自动修复或重新授权已经失效的 refresh token。
- 不修改 vibecoding-bench 养号、worker OAuth 恢复链路或生产账号凭据。
- 不新增数据库列、setting、管理 API 字段或前端页面。
- 不修改 new-api 渠道组、重试次数或自动禁用配置。
- 不部署、重启生产服务，也不使用真实 RT 做破坏性故障注入。

## Key Decisions

- 使用结构化错误类别保留永久/临时语义，不在 Gateway 解析完整错误字符串。
- 永久列表保持最小：仅 `invalid_grant` 和缺失 refresh token；缺少明确证据的错误默认不禁用账号。
- 永久错误即使当前 AT 尚未过期也不 fallback；临时错误保留现有兼容 fallback。
- 账号状态只由 Gateway 的请求调度路径改变；usage、telemetry 和管理端解析不会因一次刷新调用自行停号。
- 临时 OAuth endpoint 故障不跨账号重试，避免逐账号放大同一个外部故障。
- messages 与 count_tokens 使用一致的永久错误停用和切号语义。

## Key Context

- 根因入口：`cc2api/src/service/gateway.rs:1786-1792`，Token 预解析失败当前直接返回。
- 刷新入口：`cc2api/src/service/account.rs:1572-1632`，当前只写 `auth_error` 并返回普通 503。
- 调度判断：`cc2api/src/model/account.rs:253-264`，非空 `auth_error` 不影响 active 账号继续入选。
- 可复用停用逻辑：`cc2api/src/service/gateway.rs:1908-1945`、`2540-2596` 与 `AccountService::disable_for_auth_failure()`。
- count_tokens 同类缺陷：`cc2api/src/service/gateway.rs:1313-1392`。
- 错误分类源头：`cc2api/src/service/oauth.rs:142-193`，当前把非 2xx 压成包含完整正文的 `AppError::Internal`。
- 实现与检查上下文已收口到任务 research 和 `testing-quality.md`，JSONL 校验通过。

## Risks / Deferred

- 永久错误分类过宽会批量误停账号，因此实现与测试必须验证最小 allow-list。
- 分类在 AccountService 到 Gateway 之间丢失会让修复失效，必须通过真实 mock token endpoint 跑完整链路。
- sticky 或账号循环处理错误可能造成重复选号或 RPM 重复计数，测试必须断言单请求每账号最多探测一次。
- 回滚代码不会自动恢复已被正确停用的账号；凭据修复后仍需管理员手动启用。
- 生产部署和自然流量验证延后到后续明确授权的发布流程。

## Acceptance

- `invalid_grant` 使首选账号原子变为 disabled，停用原因脱敏且清除限流状态。
- 同一个 `/v1/messages` 请求能切到下一账号成功完成，sticky 绑定不能绕过本轮排除。
- `/v1/messages/count_tokens` 具备相同的停用与切号行为。
- 所有账号永久失效时返回 Anthropic 可解析的通用 503，每个账号只探测一次且不泄漏凭据或完整 OAuth 正文。
- 429、5xx、网络等临时错误不禁用账号，仍有效 AT fallback 不回归。
- 不产生 schema、setting、API、前端或 new-api 配置变更。
- `cargo fmt --check`、定向测试和全量 `cargo test` 全部通过。

## Next Step

- Check-All Full 重检已严格通过且规范已写入；按 `trellis-push` 确认计划完成业务代码、规范与任务进度提交。
