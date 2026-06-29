# 技术设计

## 设计原则

- `src/service/version_profile.rs` 继续作为唯一 Claude Code 版本画像注册表，禁止在 rewriter、telemetry 或 handler 中散落 `2.1.195` 特判。
- 本次升级以抓包 `23594999fa77` 的脱敏摘要为依据；只把字段差异、hash 复算结果和结构结论写入仓库。
- 默认升级到 `2.1.195`，但保留旧 profile 以便运维回滚。
- 所有 body 改写仍必须发生在 CCH 和 `cc_version` 计算之前。

## 画像差异

| 项 | 当前 2.1.187 | 目标 2.1.195 | 处理 |
|---|---|---|---|
| default profile | `2.1.187` | `2.1.195` | 修改默认常量 |
| allowed range | `2.1.89-2.1.187` | `2.1.89-2.1.195` | profile access policy 与 settings migration 同步 |
| build time | `2026-06-23T16:59:46Z` | `2026-06-26T01:00:56Z` | profile identity |
| Stainless package | `0.94.0` | `0.94.0` | 不变 |
| runtime version | `v24.3.0` | `v26.3.0` | 默认 runtime 常量改为目标值 |
| GrowthBook UA | `Bun/1.4.0` | `Bun/1.4.0` | 不变 |
| telemetry shape | `ClaudeCode2185` | `ClaudeCode2185` 兼容 | 可复用 |
| CCH seed/profile | `2.1.172+` | `2.1.172+` | 白名单扩展到 2.1.195 |
| message beta | 现有集合 | 抓包未见变化 | 不变 |

## 代码边界

### `cc2api/src/service/version_profile.rs`

- 新增 `PROFILE_2_1_195`。
- `DEFAULT_CLAUDE_CODE_VERSION_PROFILE` 指向 `2.1.195`。
- 默认版本、基础版本、build time、allowed range 通过新 profile 透出。
- `CLAUDE_CODE_PROFILES` 加入 `2.1.195`，保留 `2.1.187` / `2.1.185` / `2.1.173`。
- `STAINLESS_RUNTIME_VERSION` 改为 `v26.3.0`。
- 更新 profile 完整性和差异测试。

### `cc2api/src/service/rewriter.rs`

- `cch_attestation_input` 的 `2.1.172+` 白名单加入 `2.1.195`。
- `cch_attestation_seed` 的新 seed 白名单加入 `2.1.195`。
- 补充 `2.1.195` 的 CCH 输入规范化和 seed 单测。
- 现有 `compute_cc_version_suffix` 算法不变；新增 `2.1.195` 样本断言。

### `cc2api/src/service/oauth.rs`

- 通过 `STAINLESS_RUNTIME_VERSION` 自动使用 `v26.3.0`。
- `TokenTester` 当前使用 `MESSAGE_BETA_TOKENS`，抓包中的 Haiku 非流探测 beta 比通用集合更窄；这不是本次默认 profile 升级的必改项，但实现时应评估是否已有专用 Haiku probe beta 常量可复用，避免 token test 指纹偏宽。

### `cc2api/src/store/db.rs` / `settings_store.rs`

- 启动迁移应在默认 profile 为 `2.1.195` 时把旧默认 `allowed_claude_code_versions` 升到新默认。
- 启动迁移应把已有账号 `canonical_env.version/version_base/build_time` 更新为当前默认 profile。
- settings profile 切换事务已有统一更新逻辑，新增 profile 后需要测试覆盖 `2.1.195`。

### `cc2api/src/handler/router.rs`

- `claude_code_version_profiles` API 由 `all_profiles()` 自动输出新增 profile。
- settings 保存 `claude_code_version_profile=2.1.195` 时，应强制覆盖 `allowed_claude_code_versions=2.1.89-2.1.195`，并 reload access policy。

### `cc2api/web/src/components/Settings.vue`

- 默认 ref 和 fallback profile 列表改为 `2.1.195`。
- `allowedClaudeCodeVersions` 默认改为 `2.1.89-2.1.195`。
- 保持后端返回 profiles 时以前端解析结果为准，fallback 仅用于后端不可用或字段缺失。

## 验证策略

- 单测先覆盖画像注册和迁移行为，再覆盖 wire 输出。
- CCH 测试至少验证：
  - `cch_attestation_seed("2.1.195") == 0x4D659218E32A3268`
  - `cch_attestation_input(..., "2.1.195")` 与 `2.1.187` 同规则
  - 抓包摘要中的 `cc_version=2.1.195.113` / `2.1.195.aff` 后缀来源能复算
- 请求 header 测试覆盖 `X-Stainless-Runtime-Version=v26.3.0`。
- settings 测试覆盖从旧默认升级到新默认、profile-only payload reload、已有账号 canonical env 更新。
- 前端构建验证 Settings 类型和 fallback 列表没有破坏。

## 风险与回滚

- 风险：只改默认版本但漏改 runtime version，会继续暴露 `v24.3.0` 与 `2.1.195` 组合，不符合抓包。
- 风险：CCH 白名单漏 `2.1.195` 会回退 legacy seed/full body，抓包复算 0/30 命中。
- 风险：settings / DB 迁移漏掉会导致远程已有账号仍发送旧 canonical env。
- 回滚：切回 `claude_code_version_profile=2.1.187`，settings 事务会回写 `allowed_claude_code_versions` 和账号 env；必要时重新部署旧镜像。
