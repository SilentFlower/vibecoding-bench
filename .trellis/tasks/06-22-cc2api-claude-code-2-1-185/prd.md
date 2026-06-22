# 升级 cc2api 到 Claude Code 2.1.185

## Goal

将 `cc2api` 的 Claude Code 协议画像从 `2.1.173` 升级到 `2.1.185`，让默认 User-Agent、账号 canonical env、允许版本范围、CCH / `cc_version` 分支、自动遥测和管理端设置文案与真实 `2.1.185` 抓包一致。

## Background / Known Context

- 用户已通过 `vibecoding-bench` 抓取 run `dac88465b061` 的 Claude Code `2.1.185` 全量 HTTP 流量。
- 抓包中 `/v1/messages?beta=true` 共 13 条，其中 12 条包含 billing header。
- `cc_version` 后缀在 `2.1.185` 上继续命中既有公式：`sha256("59cf53e54c78" + text[4] + text[7] + text[20] + version).hex()[0:3]`，主请求多 text block 仍取首条 user message 的最后一个 text block。
- `cch` 在 `2.1.185` 上继续命中 `2.1.172` / `2.1.173` 规则：seed `0x4D659218E32A3268`，计算前将顶层 `model` 值替换为 `""`，删除顶层 `max_tokens` 和 `fallbacks`。
- 抓包显示默认版本画像为：
  - `version=2.1.185`
  - `version_base=2.1.185`
  - `build_time=2026-06-20T06:38:30Z`
  - `node_version=v24.3.0`
  - `X-Stainless-Package-Version=0.94.0`
- GrowthBook eval / HEAD `/` 使用 `Bun/1.4.0`，当前 `cc2api` 仍为 `Bun/1.3.14`。
- `/api/event_logging/v2/batch` 仍使用 `User-Agent: claude-code/2.1.185`、`anthropic-beta=oauth-2025-04-20`、`x-service-name=claude-code`。
- `cc2api` 当前默认允许版本范围、README 和设置页仍停在 `2.1.89-2.1.173`。

## Requirements

- 将 `cc2api` 默认 Claude Code 版本画像升级到 `2.1.185`，包括 `DEFAULT_CLAUDE_CODE_VERSION`、`DEFAULT_CLAUDE_CODE_VERSION_BASE` 和 `DEFAULT_CLAUDE_CODE_BUILD_TIME`。
- 保持 `STAINLESS_PACKAGE_VERSION=0.94.0`、`STAINLESS_RUNTIME_VERSION=v24.3.0`。
- 将 GrowthBook / HEAD 画像中的 Bun User-Agent 更新为 `Bun/1.4.0`。
- 将 `allowed_claude_code_versions` 默认值、启动迁移旧值、访问策略测试、管理端设置页默认值/文案和 README 升级到允许 `2.1.185`。
- 将 `2.1.185` 纳入 `cch_attestation_seed` 和 `cch_attestation_input` 的 `2.1.172` / `2.1.173` 同族规则。
- 保持 `cc_version` 后缀算法不变，新增或更新测试覆盖 `2.1.185`。
- 保持 `MESSAGE_BETA_TOKENS`、`FABLE_MESSAGE_BETA_TOKENS`、MCP、triggers、OAuth beta token 当前规则不因本任务改变，除非测试发现与抓包不一致。
- 启动迁移必须将已有账号 `canonical_env.version`、`version_base`、`build_time` 更新到 `2.1.185` 画像。
- 不提交完整抓包、真实 token、Cookie、Authorization、邮箱、完整 prompt 或响应正文。

## Acceptance Criteria

- [ ] `cc2api` 源码和文档中面向默认画像的 `2.1.173` 更新为 `2.1.185`。
- [ ] 默认允许 Claude Code 版本范围覆盖 `2.1.185`，老值迁移覆盖 `2.1.89-2.1.173`。
- [ ] `2.1.185` 的 CCH seed 与顶层规范化规则命中抓包样本，相关单测覆盖。
- [ ] `2.1.185` 的 `cc_version` 后缀计算命中抓包样本，相关单测覆盖。
- [ ] 自动遥测 event logging 使用 `claude-code/2.1.185`、`env.version=2.1.185`、`env.version_base=2.1.185`、`env.build_time=2026-06-20T06:38:30Z`。
- [ ] GrowthBook eval 使用 `Bun/1.4.0`。
- [ ] 管理端 Settings 中 allowed Claude Code versions 默认值、按钮和说明文案同步到 `2.1.185`。
- [ ] `cargo fmt --check`、`cargo test`、`cargo test cch` 通过。
- [ ] 如改动 `web/`，`cd cc2api/web && npm run build` 通过。

## Out of Scope

- 不修改 Claude Code `2.1.185` 以外版本的已知兼容行为。
- 不重新设计 CCH、`cc_version`、telemetry 或 bootstrap 架构。
- 不修改真实抓包采集链路。
- 不部署远程 `cc2api`，除非用户后续明确要求。
- 不提交或固化完整抓包内容。

## Research References

- `research/cc2api-2-1-185-capture-summary.md`
