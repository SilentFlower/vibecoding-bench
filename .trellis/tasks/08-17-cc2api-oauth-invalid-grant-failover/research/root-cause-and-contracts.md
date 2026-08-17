# 根因与实现契约研究

## 线上证据

- 2026-08-17 线上 `/v1/messages` 请求在 OAuth Token 预解析阶段收到 `HTTP 400 invalid_grant`。
- cc2api 日志在同一会话内反复选择同一个 OAuth 账号，且明确为 `sticky=false`；账号保持 active，所以后续请求继续参与评分选号。
- new-api 当时只有一个启用的同组渠道，失败重试表现为同渠道重复请求。渠道层不是本任务修复位置。
- 线上 cc2api 镜像 revision 为 `c1300ea`，与本地任务基线一致。

## 代码根因

- `cc2api/src/service/gateway.rs:1485-1544`
  - `/v1/messages` 已有基于 `exclude_ids` 的账号循环。
- `cc2api/src/service/gateway.rs:1786-1792`
  - `resolve_upstream_token()` 失败后直接返回，未停用账号、未排除账号、未继续循环。
- `cc2api/src/service/account.rs:1572-1632`
  - OAuth refresh 失败只更新 `auth_error`；若 AT 已过期则返回普通 `ServiceUnavailable`。
- `cc2api/src/model/account.rs:253-264`
  - 可调度判断只检查 `status` 和 `rate_limit_reset_at`，不会因非空 `auth_error` 排除账号。
- `cc2api/src/service/gateway.rs:1908-1945`、`2540-2596`
  - 上游 401 恢复失败已有停用、排除和切号逻辑，说明账号级认证永久失败应由 Gateway 改变调度状态。
- `cc2api/src/service/gateway.rs:1313-1392`
  - `count_tokens` 也有账号循环，但 Token 预解析失败当前直接返回 502。
- `cc2api/src/service/oauth.rs:142-193`
  - OAuth 非 2xx 当前被压成带完整正文的 `AppError::Internal`，上层无法结构化区分 `invalid_grant` 与临时错误。

## 既有规范

来源：`.trellis/spec/cc2api/backend/service-architecture.md`。

- 非粘性请求遇到账号级 admission 失败时，应释放当前账号资源、排除该账号并重新选号。
- 粘性请求不能绕过明确的本轮账号排除。
- `resolve_upstream_token` 允许刷新临时失败时使用仍有效 AT 的兼容 fallback。
- OAuth 凭据解析和错误输出不得记录 AT、RT、Authorization、真实邮箱/UUID 映射。

来源：`.trellis/spec/cc2api/backend/testing-quality.md`。

- 账号调度变更必须补 service/store/Gateway 回归测试，明确并发、队列和降级条件。
- Gateway 本地错误必须保持 Anthropic/OpenAI 可解析的 error object。
- fixture、日志和 spec 禁止包含真实 OAuth token、Cookie、完整响应正文或真实账号映射。
- 修改 Rust `src/` 后必须运行 `cargo fmt --check` 和全量 `cargo test`。

## 收敛决定

- 永久凭据错误仅包含有明确账号级证据的 `invalid_grant` 和缺失 refresh token。
- OAuth 429、5xx、网络/超时、解析失败及其他未明确分类的 4xx 均保持临时错误，不能误停账号。
- 永久错误不得 fallback 到旧 AT；临时错误继续保持旧 AT fallback。
- 账号停用由 Gateway 调用现有 `disable_for_auth_failure()` 完成；后台 usage、telemetry 或管理端解析不因一次调用自行改变账号状态。
- `/v1/messages` 与 `/v1/messages/count_tokens` 必须保持相同永久错误语义。
- 不改 schema、setting、管理 API、前端或 new-api 配置。
