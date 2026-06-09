# cc2api 升级 Claude Code 2.1.169

## Technical Design

本任务修改 cc2api 仓库，Trellis 任务记录保存在 `vibecoding-bench` 仓库。

版本画像集中从 `src/service/version_profile.rs` 更新：

- `DEFAULT_CLAUDE_CODE_VERSION = "2.1.169"`
- `DEFAULT_CLAUDE_CODE_VERSION_BASE = "2.1.169"`
- `DEFAULT_CLAUDE_CODE_BUILD_TIME = "2026-06-08T03:22:12Z"`
- `STAINLESS_PACKAGE_VERSION` 和 `STAINLESS_RUNTIME_VERSION` 保持不变，抓包未观察到结构性变化。

访问策略从 `src/service/access_policy.rs` 更新默认范围为 `2.1.89-2.1.169`。`src/store/db.rs` 中 settings 启动迁移需要额外处理旧默认值：当数据库已有 `allowed_claude_code_versions = 2.1.89-2.1.156` 时升级到新默认；其它用户自定义值保持不变。

CCH seed 选择不能继续只匹配默认版本常量。应把 `2.1.156` 和 `2.1.169` 都纳入同一个 attestation seed profile：

```text
2.1.156, 2.1.169 -> 0x4D659218E32A3268
其它旧版本 -> 0x6E52736AC806831E
```

已有账号升级在启动迁移中执行，直接更新 `accounts.canonical_env` 的三个字段：

- SQLite 使用 `json_set(canonical_env, '$.version', ..., '$.version_base', ..., '$.build_time', ...)`。
- PostgreSQL 使用 `jsonb_set` 链式更新。
- 迁移只修改 `canonical_env` 内版本字段，不改 `canonical_prompt_env`、`canonical_process`、账号凭据或调度字段。

测试覆盖方向：

- identity 默认版本字段。
- access policy 默认范围允许 `2.1.169`。
- CCH seed 对 `2.1.156` 与 `2.1.169` 使用同一新 seed，对旧版本使用 legacy seed。
- SQLite migration 对旧账号 JSON 字段升级且保留其它字段。
- settings 旧默认值升级到新默认，自定义值不覆盖。
- stateful usage SSE buffer 修剪使用 UTF-8 字符边界，覆盖中文字符跨 64KB 截断点的场景。

stateful usage buffer 的修复保持局部化：继续使用 `String` 累积 SSE 文本，但在 `drain(..keep_from)` 前把 `keep_from` 推进到下一个 `is_char_boundary` 为 true 的位置。这样可能多丢弃最多 3 个字节对应的一个字符前缀，但能保证剩余 buffer 仍是合法 UTF-8，且不超过 64KB 限制。

## Rollout / Rollback

升级是启动迁移型变更。回滚代码到旧版本不会自动回滚数据库中的账号 `canonical_env`，但旧版本字段只影响模拟 Claude Code 指纹；如需回滚，可通过管理端或 SQL 把账号版本字段改回 `2.1.156` / `2026-05-28T18:30:33Z`。

允许范围迁移只覆盖旧默认值，不覆盖自定义配置，降低升级时误改用户策略的风险。

SSE buffer 修复只影响内部 usage 采样解析，不改变转发给客户端的上游响应字节。
