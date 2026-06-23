# cc2api 版本特征切换 - 技术设计

## Architecture

新增运行时版本画像 setting 与内置画像注册表：

```text
settings.claude_code_version_profile (profile key)
  -> version_profile.rs ProfileRegistry
  -> AccountService 新账号 canonical env
  -> Settings 保存时批量同步 accounts.canonical_env
  -> Rewriter 使用 profile.request / profile.billing / profile.cch
  -> Telemetry 使用 profile.telemetry / profile.growthbook
  -> AccessPolicy 使用 profile.access_policy.allowed_claude_code_versions
```

版本画像不接受任意字符串。后端只允许选择内置、已抓包验证的 profile key。

## Profile Registry

把“Claude Code 版本特征”设计为一个可扩展注册表，而不是散落全局常量：

```rust
pub struct ClaudeCodeProfile {
    pub key: &'static str,
    pub identity: IdentityProfile,
    pub access_policy: AccessPolicyProfile,
    pub request: RequestProfile,
    pub billing: BillingProfile,
    pub telemetry: TelemetryProfile,
    pub endpoints: EndpointProfile,
}

pub struct IdentityProfile {
    pub version: &'static str,
    pub version_base: &'static str,
    pub build_time: &'static str,
    pub stainless_package_version: &'static str,
    pub stainless_runtime_version: &'static str,
}

pub struct AccessPolicyProfile {
    pub allowed_claude_code_versions: &'static str,
}

pub struct RequestProfile {
    pub message_beta_tokens: &'static str,
    pub fable_message_beta_tokens: &'static str,
    pub count_tokens_beta_tokens: &'static str,
    pub oauth_beta_token: &'static str,
}

pub struct BillingProfile {
    pub cc_version_algorithm: CcVersionAlgorithm,
    pub cch_profile: CchProfile,
}

pub struct TelemetryProfile {
    pub shape: TelemetryShape,
    pub growthbook_user_agent: &'static str,
}
```

实际实现可按 Rust 现有风格调整命名，但必须保留“一个 profile 明确声明所有子画像”的结构。这样新增版本时只需新增一个 profile 条目和测试，不应修改多个模块里的默认常量和分支。

### 首批 profile

| key | version | version_base | build_time | allowed_claude_code_versions | growthbook_ua | telemetry_shape |
| --- | --- | --- | --- | --- | --- | --- |
| `2.1.185` | `2.1.185` | `2.1.185` | `2026-06-20T06:38:30Z` | `2.1.89-2.1.185` | `Bun/1.4.0` | `v2_185` |
| `2.1.173` | `2.1.173` | `2.1.173` | `2026-06-11T01:23:13Z` | `2.1.89-2.1.173` | `Bun/1.3.14` | `v2_173` |

保留现有 `DEFAULT_CLAUDE_CODE_*` 常量作为默认画像兼容层，但新增 `default_profile()` / `profile_for_key()` / `profile_for_version()` 作为运行时选择入口。`growthbook_user_agent()`、`MESSAGE_BETA_TOKENS` 这类原全局 helper/常量要逐步收敛到 profile 字段；为了控制改动量，可以先保留兼容常量并让它们引用默认 profile。

## API Boundary

建议提供这些稳定 helper：

```rust
pub fn default_profile() -> &'static ClaudeCodeProfile;
pub fn profile_for_key(key: &str) -> Result<&'static ClaudeCodeProfile, AppError>;
pub fn profile_for_version(version: &str) -> &'static ClaudeCodeProfile;
pub fn all_profiles() -> &'static [&'static ClaudeCodeProfile];
```

- settings 选择使用 `profile_for_key`，未知 key 直接拒绝。
- 已有账号只存 `canonical_env.version/version_base/build_time`，热路径通过 `profile_for_version(env.version)` 找到完整子画像。
- 如果账号 env 中出现未知版本，热路径使用 default profile 并记录低频警告；settings 保存不允许未知版本。
- `profile_for_version` 必须避免“未验证新版本自动套最新规则”。未知版本只能回退 default 或 legacy 安全分支，不能假装完全支持。

## Endpoint 子画像

把 endpoint 差异保留为 profile 子结构，避免后续新版本出现新 endpoint 时继续扩散：

```text
profile.endpoints.messages
profile.endpoints.event_logging
profile.endpoints.growthbook_eval
profile.endpoints.bootstrap
profile.endpoints.code_triggers
profile.endpoints.mcp_servers
profile.endpoints.count_tokens
```

每个 endpoint profile 至少描述：

- User-Agent 来源：CLI、Code、Bun、axios 或固定值。
- required beta token。
- Content-Type / Accept / Accept-Encoding 集合。
- payload shape 版本（如 telemetry / growthbook）。

首版实现可以先只把当前有差异的 `growthbook_eval` 和 telemetry shape 抽入 profile，其余 endpoint 保持现有 helper，但设计和测试要按 endpoint profile 的方向组织，避免继续扩大常量散落。

## Data Flow

### 读取设置

`GET /admin/settings` 返回：

- `claude_code_version_profile`
- 现有 `allowed_claude_code_versions`
- 现有 `allowed_user_agents`

如果 DB 没有 `claude_code_version_profile`，返回默认 `2.1.185`。

### 保存设置

`PUT /admin/settings` 收到 `claude_code_version_profile` 时：

1. 校验值必须是内置 profile key。
2. 把 `allowed_claude_code_versions` 强制改成目标 profile 的默认范围。
3. 不修改 `allowed_user_agents`，即使请求体带了该 key 也按现有设置保存路径独立处理。
4. 批量更新所有账号 `canonical_env.version/version_base/build_time` 到目标 profile。
5. 写入 settings 并 reload access policy。

实现上应避免先写 setting 后账号同步失败造成混用。优先在 service/store 层提供一个明确的“应用版本画像”操作，内部完成 setting upsert 和账号 env 更新；如果沿用现有 `update_settings` 路径，也必须保证错误返回时不静默留下部分状态。

### 新账号

`AccountService::create_account` 当前调用 `generate_canonical_identity()`，该函数使用编译期默认画像。需要改为：

- 生成身份预设后，用当前 `claude_code_version_profile` 覆盖 env 的 `version/version_base/build_time`。
- 当前 setting 缺失或非法时回退默认 profile，非法值仍应在保存设置时被拒绝，正常 DB 不应存入非法值。

### 请求画像

现有热路径已经通过 `device_profile(account).env.version` 派生：

- `claude_cli_user_agent(version)` / `claude_code_user_agent(version)`
- `compute_cc_version_suffix(..., version)`
- `compute_cch_attestation(..., version)`

因此切换时同步账号 canonical env 后，新 `/v1/messages` 主请求会使用目标版本。仍需补测试证明 `2.1.173` 和 `2.1.185` 都能通过同一链路输出目标版本字段。

### 遥测画像

最近 cc2api commit 证明 telemetry 也有版本差异：

- `def8df5` 升到 `2.1.173` 后，GrowthBook eval 仍使用 `Bun/1.3.14`，event logging 结构仍包含旧字段形态。
- `b2b34ce` 升到 `2.1.185` 时，将 GrowthBook eval UA 改为 `Bun/1.4.0`，并将 `2.1.185` 纳入 CCH 分支。
- `014c0e5` 对齐 `2.1.185` telemetry：event logging 去掉 `email`，`betas` 从空串变为 `MESSAGE_BETA_TOKENS`，`additional_metadata` 变为 base64 JSON，env 补 `shell` 与 `is_running_with_bun`；GrowthBook eval 去掉 `email`，payload 顶层改为 `forcedVariations: {}`、`forcedFeatures: []`、`url: ""`。

因此 `TelemetryService` 不能只读取账号 env 的 version 字符串，还需要按 profile 选择 payload shape：

```text
profile.telemetry_shape == v2_173
  -> event_data.email 保留
  -> event_data.betas 为空串
  -> additional_metadata 为空串
  -> env 使用 build_full_env_json，不额外注入 shell/is_running_with_bun
  -> GrowthBook attributes.email 保留
  -> GrowthBook 顶层 forcedFeatures 为对象 {}
  -> GrowthBook UA = Bun/1.3.14

profile.telemetry_shape == v2_185
  -> event_data.email 不发送
  -> event_data.betas = MESSAGE_BETA_TOKENS
  -> additional_metadata = base64(JSON)
  -> env 额外包含 shell/is_running_with_bun
  -> GrowthBook attributes.email 不发送
  -> GrowthBook 顶层 forcedVariations={} / forcedFeatures=[] / url=""
  -> GrowthBook UA = Bun/1.4.0
```

如果后续新增版本，必须显式选择 telemetry shape，禁止默认套用最新结构。`TelemetryShape` 应使用 enum，而不是 bool 组合，避免新字段出现时旧 profile 被无意打开：

```rust
pub enum TelemetryShape {
    ClaudeCode2173,
    ClaudeCode2185,
}
```

未来新增版本如果只有 build_time/UA 变化，可以复用已有 shape；如果 payload 结构变化，新增 enum variant 和对应测试。

## Contracts

- `allowed_claude_code_versions`：版本切换时强制覆盖为目标 profile 默认范围。
- `allowed_user_agents`：版本切换不覆盖，保留管理员配置。
- `2.1.173` 与 `2.1.185` 均沿用当前 `2.1.172+` CCH 输入规则和 seed。
- GrowthBook UA 必须按 profile 切换：`2.1.173 -> Bun/1.3.14`，`2.1.185 -> Bun/1.4.0`。
- Telemetry payload shape 必须按 profile 切换，不能只同步 env.version。
- 自动 telemetry 不记录 prompt、tool input、响应正文、token、Cookie、Authorization。

## Compatibility

DB migration 需要插入新 setting 默认值：

```text
claude_code_version_profile = 2.1.185
```

已有账号启动迁移继续按当前默认画像写入 `2.1.185`，保持旧部署升级行为。运行时切换由设置保存触发，不依赖重启。

PostgreSQL 与 SQLite 都要支持批量更新 `accounts.canonical_env`：

- SQLite 使用 `json_set(CASE WHEN json_valid(...) THEN ... ELSE '{}' END, ...)`。
- PostgreSQL 使用 `jsonb_set(..., true)`。

## UI

Settings 页面新增“Claude Code 版本特征”选择控件，选项显示版本号和简短说明。选择版本时应提示：

- 保存后会同步所有账号的版本画像。
- 保存后会覆盖 `allowed_claude_code_versions`。
- `allowed_user_agents` 不会被版本切换覆盖。

不新增营销页，不拆出新路由。

前端不维护独立 profile 真相。后端 `GET /admin/settings` 可以先只返回当前 key；如实现成本可控，建议新增 `claude_code_version_profiles` JSON 字段或独立管理 API，返回可选 profile 列表，前端据此渲染选项。若首版写死前端选项，必须在实现计划里列为后续新增版本时要同步的位置，并用测试/构建防止漏改。

## 新增版本流程

未来新增 `2.x.y` 版本时流程固定为：

1. 基于脱敏抓包摘要确认 identity、request header、billing、CCH、`cc_version`、telemetry、bootstrap、GrowthBook、access policy 差异。
2. 在 `version_profile.rs` 新增一个 `ClaudeCodeProfile`。
3. 若 telemetry payload 结构变化，新增 `TelemetryShape` variant；若只是版本字段变化，复用已有 shape。
4. 若 CCH 输入或 seed 变化，新增 `CchProfile` variant；否则复用既有 variant。
5. 增加 profile 单测，断言所有必填字段非空、key 唯一、默认 allowed range 能通过 access policy 解析。
6. 增加至少一组请求重写和 telemetry payload 测试，证明该版本不会落到其他版本 shape。
7. 更新 Settings 选项或后端 profile 列表 API。

## Rollback

管理员可以在 Settings 中切回另一个内置 profile。切换会再次覆盖账号 env 和 `allowed_claude_code_versions`，用于恢复旧画像。

若代码回滚到无运行时 profile 的版本，启动迁移会按旧代码默认画像重写账号 env；settings 表中的未知 key 对旧代码无影响。

## Risks

- 如果只更新 setting 不更新账号 env，热路径仍会使用旧版本。
- 如果新账号仍用编译期默认，切换后新账号会漂回默认画像。
- 如果强制覆盖 `allowed_user_agents`，会违背用户确认的范围。
- 如果允许任意版本字符串，CCH/`cc_version`、build_time 和 telemetry 会出现未验证组合。
