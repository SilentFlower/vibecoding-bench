# brainstorm: cc2api 2.1.173 抓包差异分析

## Goal

拉取三次 Claude Code `2.1.173` 完整抓包，并与旧版 `3075` / `3078` / `3085` / `3088` 抓包做结构化对比，判断 `/root/project/cc2api` 升级到 `2.1.173` 时是否只需要改版本号，还是还需要同步 `cc_version`、CCH、遥测、请求头顺序、Fable `[1m]` 与未指定 `[1m]` 的画像差异。

在抓包评估确认 `2.1.173` 没有引入新的 CCH、header、telemetry、bootstrap 或 Fable 主请求画像变化后，继续把 `/root/project/cc2api` 的默认 Claude Code 画像完整升级到 `2.1.173`。

## Background / Known Context

- 用户指定需要拉取的新抓包 run id：`bca74ce4196b`、`6e65bb7cb888`、`7445da8ab9af`。
- 用户准备升级 `/root/project/cc2api` 内 Claude Code 版本号到 `2.1.173`。
- 旧样本已在本地存在：
  - `data/flows/pingguo-1/3075/a773a0d683a6`
  - `data/flows/pingguo-1/3078/715232eae9e8`
  - `data/flows/pingguo-1/3085/03373b8d8c65`
  - `data/flows/pingguo-1/3088/09383cec8ea7`
- 既有 `2.1.172` 任务已记录：CCH seed 没变，变化点在输入规范化；Fable `[1m]` 与无 `[1m]` 需要分别看 beta 顺序、body `model/fallbacks/max_tokens` 和 telemetry。
- `cc2api` 协议升级规范要求：升级前必须用真实抓包分别复算 `cc_version`、CCH、`anthropic-beta` 顺序、bootstrap response 和遥测差异。

## Requirements

- 从远程 vibecoding-bench 数据目录拉取三条新抓包到本地 `data/flows/**/<run_id>/`，保留原目录层级。
- 校验每条新抓包至少包含 `capture_index.json`、`http_capture.jsonl`、`stats.jsonl` 和 `.flow` 文件；若缺失必须记录。
- 建立安全摘要，不把 token、Authorization、Cookie、账号邮箱、完整 prompt、完整响应正文或 `.flow` 原文写入任务文档。
- 对比新旧抓包的 `/v1/messages` 主请求：
  - `cc_version` 版本号与后缀是否仍符合既有算法；
  - CCH seed 与输入规范化是否沿用 `2.1.172` 规则；
  - header 名集合、大小写、顺序和值是否变化；
  - `anthropic-beta` 列表和顺序是否变化；
  - body 顶层字段、`model`、`max_tokens`、`fallbacks`、thinking/profile 字段是否变化。
- 对比 telemetry 相关请求：
  - endpoint 是否变化；
  - headers 是否变化；
  - `env.version`、`version_base`、`build_time`、`model`、`preNormalizedModel`、`betas`、`flags` 等非敏感字段是否变化。
- 明确指定 `[1m]` 和未指定 `[1m]` 的 Fable 样本差异，重点看 `context-1m-2025-08-07`、`model` 归一化、fallback 和 telemetry metadata。
- 输出一份结论：`cc2api` 升级 `2.1.173` 时的必改项、可暂不改项、需要追加样本验证的项。
- 按评估结论修改 `/root/project/cc2api`：
  - 默认 Claude Code 版本、基础版本和 build time 升级到 `2.1.173`。
  - 默认允许 Claude Code 版本范围扩到 `2.1.89-2.1.173`。
  - CCH seed 和输入规范化把 `2.1.173` 纳入 `2.1.172` 同款规则。
  - 测试、Web 默认设置和 README 同步目标版本。
  - 不改变账号 `allow_1m_models` 的现有语义：只控制客户端传入的 `context-1m-2025-08-07` 是否透传，不给 Fable 自动注入 1M beta。

## Acceptance Criteria

- [ ] 三条新抓包已拉到本地，并列出本地路径和文件完整性。
- [ ] 产出安全对比报告，覆盖新旧样本矩阵、请求头、beta、body、telemetry、bootstrap、`cc_version` 和 CCH。
- [ ] 对 `cc_version` 后缀给出命中/不命中数量与原因判断。
- [ ] 对 CCH 给出按 `2.1.172` 规则复算的命中/不命中数量；不命中时给出下一步假设。
- [ ] 明确 Fable `[1m]` 和未指定 `[1m]` 的 wire/profile 差异。
- [ ] 给出 `/root/project/cc2api` 升级 `2.1.173` 的修改建议清单。
- [ ] `/root/project/cc2api` 已按建议升级到 `2.1.173`，并通过格式化与定向测试。
- [ ] 未向 git 添加完整抓包、token、prompt 或响应正文。

## Out of Scope

- 不改变 Fable `[1m]` 在 `2.1.173` 下的主请求画像；账号 `allow_1m_models` 仍只做 `context-1m` 透传白名单。
- 不提交完整 `http_capture.jsonl`、`.flow`、账号 profile 或敏感请求/响应正文。
- 不做远程部署或镜像发布。

## Research References

- `.trellis/spec/cc2api/claude-code-profile-upgrade.md`
- `.trellis/tasks/archive/2026-06/06-11-cc2api-claude-code-2172-upgrade/research/cch-2172-recheck.md`
- `.trellis/tasks/archive/2026-06/06-11-cc2api-claude-code-2172-upgrade/research/wire-telemetry-2172-diff.md`
- `research/cc2api-2-1-173-capture-diff.md`
- `research/capture-diff-summary.json`

## Notes

- 旧样本 `3075/3078/3085/3088` 的具体语义需要从 `capture_index.json` 和 run metadata 中复核，不能仅凭目录号推断。
