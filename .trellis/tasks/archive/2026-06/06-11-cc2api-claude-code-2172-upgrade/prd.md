# cc2api 升级 Claude Code 2.1.172

## Goal

将 `/root/project/cc2api` 的 Claude Code 默认画像从 `2.1.169` 升级到 `2.1.172`，并按真实抓包对齐 `cc_version`、CCH、请求头、beta/fallback 和遥测相关行为，避免升级后生成的上游请求与真实 Claude Code 2.1.172 偏离。

## Background / Known Context

- 真实抓包样本：
  - 169 baseline：`data/flows/pingguo-1/2873/10f2065adf44`
  - 172 Opus：`data/flows/pingguo-1/3075/a773a0d683a6`
  - 172 Fable：`data/flows/pingguo-1/3078/715232eae9e8`
- `cc_version` 后缀算法仍是 `sha256("59cf53e54c78" + text[4] + text[7] + text[20] + version).hex()[0:3]`，需要按 JavaScript 字符串索引语义。
- CCH seed 没变，仍是 `0x4D659218E32A3268`；172 的变化是 CCH hash 输入规范化，不是换 seed。
- 169 CCH：完整最终 JSON body，把 `cch=<5hex>` 替换回 `cch=00000` 后计算，25/25 命中。
- 172 Opus CCH：同 seed，但 hash 输入排除 top-level `model` 值和 top-level `max_tokens` 字段，38/38 命中。
- 172 Fable CCH：同 seed，排除 top-level `model` 值、top-level `max_tokens` 字段、top-level `fallbacks` 字段，23/23 命中。
- 172 Fable 主请求包含 `fallbacks:[{"model":"claude-opus-4-8"}]`，且 CCH 计算不包含该字段。
- `/v1/messages` 的 header 名集合在 169、172 Opus、172 Fable 中基本一致；主要版本变化是 `User-Agent` 从 `claude-cli/2.1.169 (external, cli)` 升级为 `claude-cli/2.1.172 (external, cli)`，`X-Stainless-Package-Version=0.94.0`、runtime `node`、runtime version `v24.3.0`、timeout `600` 保持一致。
- 172 Fable 主请求没有新增独立 header 名；差异集中在 `anthropic-beta` profile 和请求体 `fallbacks`。
- 172 Opus 主请求 beta 继续包含 `context-1m-2025-08-07`；172 Fable 主请求不包含 `context-1m-2025-08-07`，但包含 `server-side-fallback-2026-06-01` 和 `fallback-credit-2026-06-01`。
- 172 bootstrap response 新增 Fable 能力画像：`client_data.cedar_lagoon={"claude-fable":true,"claude-mythos":true}`，`additional_model_options` 包含 `claude-fable-5[1m]`；Fable bootstrap 时 `cwk_cfg_key="marigold"`。
- Fable 抓包中的 telemetry `flags=model` 表示真实 CLI 运行使用了 `--model` 一次性覆盖 settings，不是 Fable 请求协议字段，也不应作为通用 Fable 请求画像硬编码。

## Requirements

- 更新 cc2api 默认 Claude Code 版本、基础版本、build time、User-Agent 和访问策略默认范围到 `2.1.172`。
- `/v1/messages` 请求头升级必须覆盖完整 169→172 画像：UA 升级到 `claude-cli/2.1.172 (external, cli)`，Stainless package/runtime/timeout、`anthropic-version=2023-06-01`、`x-app=cli` 等保持抓包一致。
- 保留 `2.1.156` / `2.1.169` 现有 CCH 行为，不得把旧版本改成 172 的输入规范化。
- 为 `2.1.172` 增加版本化 CCH profile：seed 不变，但 CCH 输入在最终 JSON body 上排除 top-level `model` 值、`max_tokens` 字段；存在 `fallbacks` 时也排除该字段。
- 对 Fable 请求画像补齐真实 172 行为：`model=claude-fable-5`，主请求发送 `fallbacks:[{"model":"claude-opus-4-8"}]`，`anthropic-beta` 包含 `server-side-fallback-2026-06-01` 与 `fallback-credit-2026-06-01`。
- `context-1m-2025-08-07` 必须由模型/profile 决定：Opus `[1m]` profile 继续带，Fable 主请求不注入，Haiku/title 请求保持自身 beta profile。
- bootstrap 画像升级到 172：请求 UA 使用 `claude-code/2.1.172`；response 能表达 `cedar_lagoon`、`additional_model_options` 和 Fable 的 `cwk_cfg_key="marigold"`。
- telemetry 如 cc2api 已生成或改写相关事件，必须同步 `env.version/env.version_base/build_time` 到 172，并按模型 profile 写 `model`、`preNormalizedModel` 和 `betas`；`flags=model` 只在真实一次性 model override 来源下出现。
- 更新或新增测试，至少覆盖 169 baseline、172 Opus、172 Fable 的 CCH 回归样本。
- 不在仓库提交完整抓包、token、Authorization、Cookie、账号邮箱、完整 prompt 或响应正文。

## Acceptance Criteria

- [ ] cc2api 默认 Claude Code 版本画像为 `2.1.172`，相关默认 UA / settings / access policy 不再停留在 `2.1.169`。
- [ ] `/v1/messages` 头画像对齐 172：UA 为 `claude-cli/2.1.172 (external, cli)`，Stainless/runtime/timeout、`anthropic-version`、`x-app` 等字段不被误改。
- [ ] 172 Opus 主请求 beta 包含 `context-1m-2025-08-07`；172 Fable 主请求 beta 不包含该项，包含 `server-side-fallback-2026-06-01` 与 `fallback-credit-2026-06-01`。
- [ ] Haiku/title 请求 beta profile 不被主模型 Opus/Fable 的 1m/fallback profile 污染。
- [ ] bootstrap 画像测试覆盖 172 Opus 的 `cedar_lagoon/additional_model_options`，以及 172 Fable 的 `cwk_cfg_key="marigold"`。
- [ ] telemetry 相关测试或快照覆盖 172 env version/build_time、Fable `model/betas`，并确认普通 Fable 配置不会无条件输出 `flags=model`。
- [ ] 169 抓包 fixture 或等价最小样本仍按旧 CCH 输入规则命中。
- [ ] 172 Opus 样本按 `model + max_tokens` 排除规则命中 CCH。
- [ ] 172 Fable 样本按 `model + max_tokens + fallbacks` 排除规则命中 CCH。
- [ ] `cc_version` 后缀测试覆盖 172 主请求与 Haiku/title 请求。
- [ ] `cargo test` 通过；涉及 Web/settings 文案时对应前端构建或静态检查通过。

## Out of Scope

- 不修改 vibecoding-bench 抓包功能；该功能已在 `capture-run-model-override` 任务中完成并归档。
- 不提交或固化完整真实抓包正文。
- 不重构 cc2api 请求重写架构，除非现有结构无法表达版本化 CCH profile。

## Research References

- `research/cch-2172-recheck.md`：172 CCH seed 与输入规范化复核。
- `research/wire-telemetry-2172-diff.md`：169→172 请求头、Fable beta、bootstrap 和 telemetry metadata 差异。
- `.trellis/tasks/archive/2026-06/06-04-cc2api-claude-code-2156-cch-upgrade/research/cch-reversal-playbook.md`：CCH 逆向方法和旧 seed 定位流程。
