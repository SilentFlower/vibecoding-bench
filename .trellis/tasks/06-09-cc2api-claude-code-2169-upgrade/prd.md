# cc2api 升级 Claude Code 2.1.169

## Goal

将 cc2api 的 Claude Code 默认指纹从 `2.1.156` 升级到 `2.1.169`，并让新旧账号、访问策略、计费头和遥测画像都使用同一套 2.1.169 版本信息，避免客户端升级后被默认版本范围或 CCH seed 逻辑拦截。

## Background / Known Context

- `vibecoding-bench` 新抓包 `data/flows/pingguo-1/2873/10f2065adf44` 已确认来自 Claude Code `2.1.169`。
- `cch` 算法与 `2.1.156` 一致，仍为 `xxhash64(final_json_body_with_cch_00000, seed=0x4D659218E32A3268) & 0xFFFFF`。
- `cc_version` 后缀算法与 `2.1.156` 一致，仍为 `sha256("59cf53e54c78" + text[4] + text[7] + text[20] + version)[0:3]`，索引按 JS 字符串索引语义。
- `2.1.169` 遥测 env 中 `version/version_base` 为 `2.1.169`，`build_time` 为 `2026-06-08T03:22:12Z`，`node_version` 仍为 `v24.3.0`。
- cc2api 当前默认允许范围是 `2.1.89-2.1.156`，当前默认 identity 是 `2.1.156` / `2026-05-28T18:30:33Z`。
- 现有账号的 `canonical_env` 存在持久化版本字段；只改默认常量不会升级已有账号。
- 运行日志暴露出一次 `src/service/gateway.rs:2020` panic：stateful usage SSE buffer 用字节偏移调用 `String::drain`，当偏移落在中文或 emoji 等多字节 UTF-8 字符中间时会触发 `is_char_boundary` 断言。

## Requirements

- 默认 Claude Code 版本切到 `2.1.169`，包括 `version`、`version_base`、默认 User-Agent 生成和 telemetry 画像。
- 默认 Claude Code build time 切到 `2026-06-08T03:22:12Z`。
- 默认允许范围放宽到 `2.1.89-2.1.169`，包括后端默认设置、管理端默认文案和 README。
- `2.1.169` 必须沿用 `2.1.156` 的 CCH attestation seed `0x4D659218E32A3268`；旧版本继续保留 legacy seed。
- 服务启动迁移要升级已有账号的 `canonical_env.version`、`canonical_env.version_base` 和 `canonical_env.build_time` 到 2.1.169 画像，同时保留账号已有的 device、平台、shell、process、OAuth 等其它字段。
- settings 表中已有旧默认 `allowed_claude_code_versions=2.1.89-2.1.156` 的安装应自动升级为 `2.1.89-2.1.169`；用户手工改过的非旧默认值不应被无条件覆盖。
- stateful usage SSE buffer 超过 64KB 时，应按 UTF-8 字符边界截断，不能因为中文、emoji 等多字节字符跨过截断点导致 tokio worker panic。
- 相关单元测试、文档和 UI 默认值需要同步更新。

## Acceptance Criteria

- [ ] 新账号生成的 `canonical_env.version` / `version_base` / `build_time` 分别为 `2.1.169` / `2.1.169` / `2026-06-08T03:22:12Z`。
- [ ] 旧账号在服务启动迁移后，`canonical_env` 的三个版本字段升级到 2.1.169 画像，其它字段不被清空或重置。
- [ ] `allowed_claude_code_versions` 默认值和 UI 快捷值为 `2.1.89-2.1.169`，`claude-code/2.1.169` 和 `claude-cli/2.1.169` 可通过默认访问策略。
- [ ] `billing_mode=rewrite` 对 `2.1.169` 计算 CCH 时使用 `0x4D659218E32A3268`，不会落回 legacy seed。
- [ ] 大 SSE 响应文本中存在中文或 emoji 并跨过 stateful usage buffer 截断点时，不再触发 `String::drain` char boundary panic。
- [ ] 现有测试更新后通过，至少覆盖版本默认值、访问策略默认范围、CCH seed 选择和账号迁移逻辑。
- [ ] README 说明与实现保持一致。

## Out of Scope

- 不重新逆向 Claude Code 2.1.169；本任务复用已完成抓包验证结论。
- 不改变 message body 结构、cache-control 策略、system prompt 注入策略或账号调度策略。
- 不部署远程 cc2api，除非后续单独要求。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
