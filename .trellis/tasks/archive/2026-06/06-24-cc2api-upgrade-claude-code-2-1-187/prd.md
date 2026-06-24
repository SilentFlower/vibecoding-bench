# cc2api 升级 Claude Code 2.1.187 画像

## Goal

基于 `vibecoding-bench` 抓包 run `c7e324fbb199`，将 `cc2api` 的 Claude Code 协议画像升级到 `2.1.187`，并保持现有版本画像切换能力可控：默认画像、账号 canonical env、访问策略、请求 header/body/billing、telemetry/GrowthBook、Settings 选项和测试都必须与真实抓包差异一致。

## Confirmed Facts

- 抓包目录已拉到本地 gitignored 路径：`data/flows/6-23/4144/c7e324fbb199/`。
- 抓包包含 74 条 flow：25 条 `/v1/messages?beta=true`，36 条 `/api/event_logging/v2/batch`，其余为 bootstrap、GrowthBook、OAuth settings、MCP、triggers 和 registry 请求。
- 除 `HEAD /` 返回 404 外，其余 73 条均为 200。
- `2.1.187` identity 为 `version=2.1.187`、`version_base=2.1.187`、`build_time=2026-06-23T16:59:46Z`。
- Stainless 仍为 `X-Stainless-Package-Version=0.94.0`、`X-Stainless-Runtime=node`、`X-Stainless-Runtime-Version=v24.3.0`。
- GrowthBook UA 仍为 `Bun/1.4.0`；event logging UA 为 `claude-code/2.1.187`；messages UA 为 `claude-cli/2.1.187 (external, cli)`。
- 24 条带 billing 的 messages 中，`cc_version` 后缀 24/24 命中既有算法，CCH 24/24 命中 `2.1.172+` 归一化规则。
- `2.1.187` telemetry/GrowthBook payload shape 与当前 `ClaudeCode2185` 一致，只需要替换 identity。
- Haiku 辅助流式请求出现 `structured-outputs-2025-12-15`，但 Opus 主请求 beta 与 2.1.185 一致；该 token 不应进入通用主请求 beta 常量。
- 当前 `cc2api/src/store/db.rs` 启动迁移会无条件按默认 profile 覆盖账号 env，并会把历史默认 allowed range 改成当前默认；这会破坏管理员显式选择旧 profile 后的重启一致性。

## Requirements

- 从远端 `vibecoding-bench.env` 指向的抓包目录拉取并分析 `data/flows/6-23/4144/c7e324fbb199`。
- 只在任务 research 中保存脱敏协议摘要，不提交完整 `http_capture.jsonl`、`.flow`、token、Cookie、Authorization、邮箱、完整 prompt 或完整响应正文。
- 对比当前 `cc2api` 的 `2.1.185` / `2.1.173` profile，确认 `2.1.187` 的 identity、access policy、request beta、CCH、`cc_version`、bootstrap、telemetry/GrowthBook 和 endpoint header 是否变化。
- 如抓包确认 `2.1.187` 可支持，新增或更新 `cc2api` 内置 profile，使默认画像升级到 `2.1.187`，同时保留可切回旧 profile 的能力。
- 修正任何会导致 settings、账号 `canonical_env`、header、body、telemetry 混用不同版本画像的路径。
- 启动迁移必须尊重 `settings.claude_code_version_profile`：缺失时升级到默认 `2.1.187`；已显式选择 `2.1.185` / `2.1.173` 时不得重启写回默认画像。
- 版本切换不得改写 `allowed_user_agents`；`allowed_claude_code_versions` 由内置 profile 控制。
- 覆盖后端单测；如改动 Settings 前端，则覆盖前端构建验证。

## Acceptance Criteria

- [ ] `research/cc2api-2-1-187-capture-summary.md` 记录脱敏抓包摘要和 2.1.185 对比结论。
- [ ] `cc2api` 新增/更新 `2.1.187` 画像，`DEFAULT_CLAUDE_CODE_VERSION_PROFILE` 指向目标默认版本。
- [ ] 默认 `allowed_claude_code_versions` 覆盖 `2.1.187`，Settings 选项展示目标版本。
- [ ] 请求重写按 `2.1.187` 输出正确 UA、Stainless header、`anthropic-beta`、`cc_version` 和 CCH。
- [ ] 自动 telemetry / GrowthBook 使用与 `2.1.187` 抓包一致的 UA、env 和 payload shape。
- [ ] 启动迁移和运行时 profile 切换不会把账号 `canonical_env` 写成与 settings 不一致的版本。
- [ ] 显式选择旧 profile 后重启迁移保持旧 profile 的账号 env 和 allowed range，不被默认 `2.1.187` 覆盖。
- [ ] `cargo fmt --check`、`cargo test`、`cargo test cch` 通过；如改动 `cc2api/web`，`npm run build` 通过。

## Notes

- 本任务是复杂跨层任务，需要补 `design.md` 和 `implement.md` 后再进入实现。
- 原始抓包已拉到本地 gitignored 路径：`data/flows/6-23/4144/c7e324fbb199/`。
- 不提供绕过风控或规避封禁建议；本任务只处理协议一致性、配置一致性和敏感数据边界。

## Open Questions

- 当前无阻塞问题；规划审阅通过后可进入实现。
