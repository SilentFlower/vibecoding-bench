# 修复 cc2api OAuth 永久失效账号自动停用与切号

## Goal

当 cc2api 在请求转发前刷新 OAuth access token，并收到账号级永久凭据错误时，立即停用异常账号并在同一请求内切换到下一个可用账号，避免失效 refresh token 持续被调度、请求反复返回 503。

## Background

- 线上故障发生在 `/v1/messages` 请求的 Token 预解析阶段：OAuth token endpoint 返回 `HTTP 400 invalid_grant`，表示 refresh token 已过期或被撤销。
- `GatewayService` 已有账号排除重试循环，但 `resolve_upstream_token()` 失败后当前直接返回错误，没有把账号加入 `exclude_ids`：`cc2api/src/service/gateway.rs:1786-1792`。
- `refresh_oauth_account()` 当前只写 `auth_error` 并返回 `ServiceUnavailable`，不会修改账号 `status`：`cc2api/src/service/account.rs:1614-1630`。
- `Account::is_schedulable()` 只检查 `status` 和 `rate_limit_reset_at`，不检查 `auth_error`，所以异常账号仍会继续参与评分选号：`cc2api/src/model/account.rs:253-264`。
- 上游已经返回 401 的恢复路径会调用 `disable_for_auth_failure()` 并换号，但 Token 预解析失败发生在上游请求之前，绕过了该逻辑：`cc2api/src/service/gateway.rs:1908-1945`、`2540-2596`。
- 同一缺陷也存在于 `/v1/messages/count_tokens`：Token 预解析失败当前直接返回 502，没有继续账号循环：`cc2api/src/service/gateway.rs:1342-1354`。
- 线上 cc2api 镜像 revision 与本地 `c1300ea` 一致，根因可以直接由当前代码复现。
- new-api 当时只有一个启用的 `cop` 渠道，因此渠道级重试只能 `80->80`；本任务修复 cc2api 内部账号池，不通过禁用整个 new-api 渠道规避单账号故障。

## Requirements

### R1. 结构化区分永久凭据错误与临时刷新错误

- OAuth 刷新失败必须保留机器可判定的错误类别，Gateway 不得依赖完整错误字符串或原始响应正文猜测是否应停号。
- `invalid_grant` 必须归类为账号级永久凭据错误。
- 账号缺少 refresh token 时必须进入同一永久凭据错误语义。
- 网络错误、超时、OAuth endpoint `429`、`5xx`、响应解析失败以及未明确列入永久错误的 OAuth 错误码必须保持临时错误，不得自动停用账号。
- 永久错误只保留固定类别、HTTP 状态和短错误码等脱敏摘要，不记录 AT、RT、Authorization、Cookie、代理密码或完整 OAuth 响应正文。
- 永久错误不得使用“当前 AT 尚未过期”的 fallback；临时错误继续允许沿用仍有效的 AT，保持现有兼容行为。

### R2. 永久错误自动停用账号

- Gateway Token 预解析遇到永久凭据错误时，必须调用现有 `disable_for_auth_failure()`，原子写入：
  - `status=disabled`
  - `auth_error=<脱敏原因>`
  - `disable_reason=<同一脱敏原因>`
  - 清空账号级限流时间
- 停用原因必须能让管理员判断需要重新授权，但不得包含凭据或完整上游正文。
- 数据库更新失败不得被静默忽略；不能在账号仍为 active 时假装已经完成切号保护。

### R3. 当前请求排除异常账号并切号

- `/v1/messages` 和 `/v1/messages/count_tokens` 都必须在永久凭据错误后：释放当前账号槽位、把账号 ID 加入本轮 `exclude_ids`，然后继续选择下一个账号。
- sticky 与非 sticky 请求都必须遵守本轮排除；失效账号不得因旧会话绑定再次被选中。
- 同一请求内每个永久失效账号最多探测一次，不能形成同账号循环，也不能重复增加该账号的 RPM。
- 下一个账号可用时，原请求应正常完成，调用方不应看到前一个账号的 `invalid_grant`。
- 所有允许账号都永久失效或不可用时，返回可解析的通用 503，不泄漏账号名、账号 ID、OAuth 错误正文或凭据。
- 临时刷新错误保持现有失败语义，不跨多个账号放大 OAuth endpoint 故障。

### R4. 保持既有边界

- 不调整账号优先级、综合评分、并发槽位、RPM admission、429 冷却或普通 401 恢复规则。
- 不新增 setting、数据库 migration、管理 API 字段或前端页面。
- 不修改 new-api 渠道组、重试次数或自动禁用配置。
- 不对生产账号执行 RT 撤销、OAuth 刷新或其他破坏性验证。

### R5. 回归测试

- OAuth 层覆盖 `invalid_grant` 的结构化分类和脱敏摘要。
- AccountService 覆盖永久错误不回退旧 AT、临时错误仍可回退有效 AT、缺失 RT 的永久错误语义。
- Gateway 覆盖 `/v1/messages` 在首账号 `invalid_grant` 后停用并切到第二账号。
- Gateway 覆盖 sticky 会话不能绕过本轮永久错误排除。
- Gateway 覆盖 `/v1/messages/count_tokens` 的同等停用与切号行为。
- 覆盖所有账号永久失效时返回通用 503，且每个账号最多探测一次。
- 覆盖临时 OAuth 429/5xx/网络失败不会自动停用账号。

## Acceptance Criteria

- [ ] AC1：首选 OAuth 账号刷新返回 `invalid_grant` 时，该账号原子变为 `disabled`，`auth_error` 与 `disable_reason` 只包含脱敏原因，限流状态被清空。
- [ ] AC2：同一个 `/v1/messages` 请求自动排除失效账号并由下一可用账号成功完成；失效账号在本轮只尝试一次。
- [ ] AC3：已有 sticky 绑定指向失效账号时仍能完成停用与切号，后续请求不再调度该账号。
- [ ] AC4：`/v1/messages/count_tokens` 具备相同的永久错误停用与切号行为。
- [ ] AC5：所有候选账号均永久失效时返回 Anthropic 可解析的通用 503，响应和日志不泄漏凭据、完整 OAuth 正文或生产账号映射。
- [ ] AC6：临时刷新错误和仍有效 AT fallback 行为不回归；429、5xx、网络错误不会把账号改为 disabled。
- [ ] AC7：不新增数据库列、setting、管理 API 或前端变更，new-api 配置保持不变。
- [ ] AC8：`cd cc2api && cargo fmt --check`、相关定向测试和全量 `cargo test` 通过。

## Out Of Scope

- 自动修复或重新授权已经失效的 refresh token。
- 修改 vibecoding-bench 养号调度或 worker OAuth 恢复逻辑。
- 启用 new-api 全局渠道自动禁用，或为 `cop` 组新增备用渠道。
- 部署、重启生产服务或使用真实生产凭据做故障注入。
