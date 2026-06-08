# cc2api 增加 Anthropic cache_control TTL 改写设置

## Goal

给 cc2api 增加一个系统设置,用于控制转发 Anthropic `/v1/messages` 请求时是否统一改写已有 `cache_control.type == "ephemeral"` 的 `ttl`。该设置用于排查和稳定 Claude Code 侧 Anthropic prompt cache 命中行为,支持保持原样、强制 `5m`、强制 `1h` 三种模式。

## Background / Known Context

- 用户在 Claude Code 里通过 cc2api 使用 Anthropic,近期关注缓存命中和缓存诊断相关行为。
- Anthropic 扩展缓存 TTL 依赖请求头中的 beta token,但请求体里的已有 `cache_control.ttl` 也会影响实际缓存生命周期。
- sub2api 中 `forceEphemeralCacheControlTTL` 的 TTL 改写只修改已有 `cache_control`,不会新增缓存断点。
- sub2api 里另有 tools/messages 的 cache breakpoint 注入逻辑,它会新增 `cache_control`;这不是本任务要仿照的行为。
- cc2api 现有设置通过 `settings` 表、`/admin/settings` 接口、`Settings.vue` 设置页维护,网关在内存 `RwLock` 缓存热路径配置。

## Requirements

- 新增系统设置 `cache_control_ttl_rewrite`,默认值为 `off`。
- 新增系统设置 `message_cache_control_rewrite`,默认值为 `off`。
- 设置可选值必须限定为:
  - `off`: 不改写请求体中的 `cache_control.ttl`。
  - `5m`: 将已有 ephemeral cache_control 的 `ttl` 改写为 `5m`。
  - `1h`: 将已有 ephemeral cache_control 的 `ttl` 改写为 `1h`。
- `message_cache_control_rewrite` 可选值必须限定为:
  - `off`: 保持客户端原始 `messages[].content[].cache_control`。
  - `stable`: 清理 `messages[].content[].cache_control`,再按稳定规则重新放置 message 缓存断点。
- TTL 改写仅作用于 Anthropic `/v1/messages` 请求体。
- TTL 改写仅处理已经存在的 `cache_control` 对象,且仅在 `type == "ephemeral"` 时生效。
- TTL 改写必须覆盖与 sub2api 对齐的现有位置:
  - 顶层 `cache_control`。
  - `system[]` 内 block 的 `cache_control`。
  - `messages[].content[]` 内 block 的 `cache_control`。
  - `tools[]` 内 tool 的 `cache_control`。
- 如果目标位置已有 ephemeral `cache_control` 但没有 `ttl`,选择 `5m` 或 `1h` 时应补上对应 `ttl`。
- 如果目标位置已有 ephemeral `cache_control.ttl` 且值不同,选择 `5m` 或 `1h` 时应覆盖为目标值。
- 如果 `cache_control.type` 不是 `ephemeral`,不得修改。
- `message_cache_control_rewrite=stable` 仅作用于 Claude Code 客户端模式,不改变纯 API 模式现有剥离策略。
- `message_cache_control_rewrite=stable` 必须保留 `system[]` 和 `tools[]` 的缓存断点,只重排 `messages[].content[]` 的缓存断点。
- `message_cache_control_rewrite=stable` 必须按以下规则重打 message 断点:
  - 最后一条 message 的最后一个 content block。
  - 当 messages 数量大于等于 4 时,再打倒数第二个 user turn 的最后一个 content block。
- `message_cache_control_rewrite=stable` 不得在 `thinking` 或 `redacted_thinking` block 上新增 `cache_control`。
- 设置更新后必须无需重启即可影响后续请求。
- 设置页需要提供可读的三选一控件,保存时写入 `cache_control_ttl_rewrite`。
- 管理接口必须拒绝非法枚举值。

## Constraints

- 不新增任何新的 `cache_control` 对象,不新增缓存断点。
- `message_cache_control_rewrite=stable` 是唯一允许新增 message 断点的显式设置;默认关闭。
- 不照搬 sub2api 的 tools/messages 自动注入断点逻辑。
- 不改变 header 透传/排序逻辑。
- 不改变 CCH attestation 的校验语义;message 断点稳定化和 TTL 改写必须发生在重新计算 CCH 之前。
- 默认行为必须保持兼容,未配置或旧数据库升级后等价于 `off`。
- 仅按 sub2api 当前 TTL 改写范围扫描一层 `messages[].content[]`;不递归改写 `tool_result.content` 内层块。

## Acceptance Criteria

- [ ] 新安装或旧库缺少设置项时,`/admin/settings` 返回 `cache_control_ttl_rewrite: "off"`。
- [ ] `PUT /admin/settings` 接受 `off`、`5m`、`1h`,拒绝其他值。
- [ ] `PUT /admin/settings` 对 `message_cache_control_rewrite` 接受 `off`、`stable`,拒绝其他值。
- [ ] 设置为 `off` 时,`/v1/messages` 请求体内所有 `cache_control.ttl` 保持原样。
- [ ] 设置为 `5m` 时,仅已有 ephemeral `cache_control` 的 `ttl` 被写为 `5m`,不会增加新的 `cache_control`。
- [ ] 设置为 `1h` 时,仅已有 ephemeral `cache_control` 的 `ttl` 被写为 `1h`,不会增加新的 `cache_control`。
- [ ] 非 ephemeral `cache_control` 保持原样。
- [ ] `message_cache_control_rewrite=stable` 时,历史 message 断点被清理,最后一条 message 和倒数第二个 user turn 被稳定重打断点。
- [ ] `message_cache_control_rewrite=stable` 与 `cache_control_ttl_rewrite` 同时开启时,新打 message 断点的 ttl 最终按 TTL 设置取值,且 CCH 在最终 body 上重新计算。
- [ ] API 模式下已有 `strip_cache_control` 行为不被意外扩大或破坏。
- [ ] 前端设置页可加载、展示并保存新设置。
- [ ] 后端相关单元测试覆盖枚举解析、设置校验、body 改写范围和不新增断点。

## Notes

- 参考记录见 `research/sub2api-cache-ttl.md`。
