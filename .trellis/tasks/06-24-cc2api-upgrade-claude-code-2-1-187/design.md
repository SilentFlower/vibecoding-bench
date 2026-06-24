# cc2api 升级 Claude Code 2.1.187 画像 - 技术设计

## Architecture

本次升级沿用现有版本画像注册表，不引入新的动态版本拼装机制：

```text
version_profile.rs
  -> settings 默认值 / Settings 选项
  -> accounts.canonical_env identity
  -> access policy allowed_claude_code_versions
  -> rewriter UA / beta / billing / CCH
  -> telemetry / GrowthBook shape
```

`2.1.187` 是已抓包验证的内置 profile。默认画像切到 `2.1.187`，但 `2.1.185` 与 `2.1.173` 继续保留为可回滚选项。

## Profile Contract

在 `cc2api/src/service/version_profile.rs` 新增 `PROFILE_2_1_187`：

| 字段 | 值 |
| --- | --- |
| `key` | `2.1.187` |
| `identity.version` | `2.1.187` |
| `identity.version_base` | `2.1.187` |
| `identity.build_time` | `2026-06-23T16:59:46Z` |
| `identity.stainless_package_version` | `0.94.0` |
| `identity.stainless_runtime_version` | `v24.3.0` |
| `access_policy.allowed_claude_code_versions` | `2.1.89-2.1.187` |
| `request.message_beta_tokens` | 复用当前 `MESSAGE_BETA_TOKENS` |
| `request.fable_message_beta_tokens` | 复用当前 `FABLE_MESSAGE_BETA_TOKENS` |
| `billing.cc_version_algorithm` | `Sha256TextPositions` |
| `billing.cch_profile` | `ClaudeCode2172Plus` |
| `telemetry.shape` | 复用 `ClaudeCode2185` |
| `telemetry.growthbook_user_agent` | `Bun/1.4.0` |
| `endpoints.event_logging_path` | `/api/event_logging/v2/batch` |

默认兼容常量改为引用 `PROFILE_2_1_187`：

- `DEFAULT_CLAUDE_CODE_VERSION_PROFILE`
- `DEFAULT_CLAUDE_CODE_VERSION`
- `DEFAULT_CLAUDE_CODE_VERSION_BASE`
- `DEFAULT_CLAUDE_CODE_BUILD_TIME`
- `DEFAULT_ALLOWED_CLAUDE_CODE_VERSIONS`
- `default_profile()`

`all_profiles()` 顺序使用新默认优先：`2.1.187`、`2.1.185`、`2.1.173`。前端 Settings 会优先使用后端返回的 `claude_code_version_profiles`，本地 fallback 同步补 `2.1.187`，避免接口异常时 UI 回落到旧选项。

## Request / Billing / CCH

抓包确认 `2.1.187` 的 `cc_version` 后缀 24/24 命中既有 `Sha256TextPositions` 算法，不改公式。

CCH 24/24 命中 `2.1.172+` 归一化规则。需要把以下分支显式加入 `2.1.187`：

- `cch_attestation_input()` 的 `2.1.172 | 2.1.173 | 2.1.185` 匹配列表。
- `cch_attestation_seed()` 的 `2.1.156 | 2.1.169 | 2.1.172 | 2.1.173 | 2.1.185` 匹配列表。
- 对应单测名称或断言改为覆盖 `2.1.187`。

不要把 Haiku 辅助请求中的 `structured-outputs-2025-12-15` 加入通用 `MESSAGE_BETA_TOKENS`。原因：

- 抓包中 Opus 主请求仍使用 2.1.185 相同 beta。
- `structured-outputs-2025-12-15` 只出现在真实客户端 Haiku 流式辅助请求。
- cc2api 的 Claude Code 客户端模式会合并客户端传入 beta；API mimicry 默认主画像不应伪造该辅助请求形态。

## Telemetry / GrowthBook

`2.1.187` 复用 `TelemetryShape::ClaudeCode2185`：

- event logging 不发送 email。
- `betas` 非空。
- `additional_metadata` 是 base64 JSON。
- env 包含 `shell` 与 `is_running_with_bun`。
- GrowthBook 顶层包含 `forcedVariations={}`、`forcedFeatures=[]`、`url=""`。
- GrowthBook UA 仍为 `Bun/1.4.0`。

实现只需要确保账号 env / 默认 profile 变为 2.1.187 后，上述 shape 中的 `version`、`version_base`、`build_time`、`appVersion` 一起变为 2.1.187。

`TelemetryShape::as_str()` 可继续返回 `claude_code_2_1_185`，表示结构版本；也可以新增更中性的 shape 名称，但本次不要求修改前端展示语义，避免扩大兼容面。

## Settings / Database Consistency

当前代码存在两个启动迁移风险，必须在本次升级一起修复：

1. `upgrade_account_claude_code_profile()` 每次 `migrate()` 都按 `default_profile()` 无条件覆盖所有账号 `canonical_env.version/version_base/build_time`。
2. `upgrade_default_settings()` 会把历史默认 `allowed_claude_code_versions` 值无条件升级到当前默认范围，其中包含 `2.1.89-2.1.173`；管理员切到 `2.1.173` 后重启会被写回新默认范围。

目标行为：

- 启动迁移应先读取 `settings.claude_code_version_profile`。
- 若 setting 是内置 profile key，则按该 profile 同步账号 `canonical_env`。
- 若 setting 缺失，则插入当前默认 `2.1.187`，并按默认 profile 同步账号。
- 若 setting 非法，则不要拼装未知画像；应回退默认 profile 或保留现有 env 并记录错误。为避免启动失败，本次倾向回退默认 profile，并通过测试覆盖合法 profile 不被默认覆盖。
- `allowed_claude_code_versions` 只在其值等于“历史默认值且当前 profile 也是默认 profile”时自动升级到 `2.1.89-2.1.187`。
- 当 `claude_code_version_profile=2.1.173` 时，启动迁移必须保持 `allowed_claude_code_versions=2.1.89-2.1.173`，并把账号 env 同步为 2.1.173。
- 当 `claude_code_version_profile=2.1.185` 时，同理保持 `2.1.89-2.1.185`。
- Settings 保存路径 `apply_claude_code_profile()` 已经在事务内同时更新 settings 和账号 env，保留该行为。

这会让“代码默认升级”与“管理员显式切旧 profile”共存：

```text
新库 / 未选择 profile
  -> 默认 2.1.187

已有库且 profile=2.1.185
  -> 保持 2.1.185，不被重启改成 2.1.187

已有库且 profile=2.1.173
  -> 保持 2.1.173，不被重启改成 2.1.187
```

## Frontend

Settings 已经通过 `claude_code_version_profiles` 从后端渲染选项。本次只需要：

- 默认 ref 从 `2.1.185` 改为 `2.1.187`。
- fallback profile 列表补 `2.1.187`，保留 `2.1.185` 与 `2.1.173`。
- fallback allowed range 从 `2.1.89-2.1.185` 改为 `2.1.89-2.1.187`。
- placeholder 同步改为 `2.1.89-2.1.187`。

不新增路由，不新增营销说明，不改变 `allowed_user_agents` 独立配置。

## Tests

后端重点测试：

- `default_profile_matches_compat_constants` 断言默认 2.1.187、build_time、allowed range。
- `profiles_are_complete_and_unique` 覆盖三个 profile。
- `profile_declares_known_telemetry_differences` 增加 2.1.187，并断言 2.1.187/2.1.185 复用 `ClaudeCode2185`。
- CCH 单测覆盖 `2.1.187` 的 seed 和 `2.1.172+` top-level 归一化。
- `cc_version_suffix_source_uses_last_user_text_block` 增加 2.1.187 断言。
- request header 单测使用默认版本时输出 `claude-cli/2.1.187`、`claude-code/2.1.187`。
- telemetry / GrowthBook 默认 profile 断言 `appVersion=2.1.187` 和 env build_time。
- DB migration 新增回归：
  - 无 profile 的旧库升级到默认 2.1.187。
  - `claude_code_version_profile=2.1.173` 时重启迁移不覆盖成默认。
  - `claude_code_version_profile=2.1.185` 时重启迁移不覆盖成默认。
  - 旧默认 allowed range 只在默认 profile 下升级。

前端验证：

- 如改动 `cc2api/web/src/components/Settings.vue`，运行 `npm run build`。

## Rollback

管理员可在 Settings 中切回 `2.1.185` 或 `2.1.173`。保存后后端事务会同步：

- `settings.claude_code_version_profile`
- `settings.allowed_claude_code_versions`
- 所有账号 `canonical_env.version/version_base/build_time`

代码回滚到旧版本时，旧代码不会理解 `2.1.187` profile；因此上线前应确认回滚策略是同时回滚镜像和显式切回旧 profile，或接受旧代码按其默认迁移重写账号 env。

## Out of Scope

- 不提交完整抓包、token、Cookie、Authorization、邮箱、完整 prompt 或完整响应正文。
- 不改 bootstrap Fable 配置策略。
- 不新增任意版本字符串输入能力。
- 不提供绕过风控或规避封禁建议；本任务只做协议一致性、配置一致性、敏感数据边界和可回滚升级。
