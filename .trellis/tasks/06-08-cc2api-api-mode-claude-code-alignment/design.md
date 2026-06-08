# cc2api API 模式对齐 Claude Code 请求画像设计

## Technical Design

API 模式需要从“短 prompt 注入”升级为“OAuth mimicry”链路。设计边界是 `/v1/messages` 的 API 客户端请求：真实 Claude Code 客户端继续走现有 `ClientType::ClaudeCode` 分支。

system 改写参考 sub2api：

- system[0]：billing attribution block，文本形态为 `x-anthropic-billing-header: cc_version=<version>.<fp>; cc_entrypoint=cli; cch=00000;`，不带 cache_control。
- system[1]：`You are Claude Code, Anthropic's official CLI for Claude.`，不带 cache_control。
- system[2]：工具无关的 Claude Code-like 中性扩充提示，带 ephemeral cache_control 作为稳定 system 断点。
- 原始 API system 迁移到 messages 开头，使用 user instruction + assistant ack 保留语义，避免仍留在 system 里破坏 Claude Code-like 画像。

CCH 顺序必须保持为：

1. 构造或重写 billing block 时只写 `cch=00000`。
2. 完成 system、metadata、message cache、TTL、tools、body sanitize 等全部会改变 body 字节的动作。
3. 序列化最终 body。
4. 对带占位符的最终 body 字节做 xxHash64，替换为 5 位十六进制 cch。

当前 Claude Code 模式已经符合这个原则：`rewrite_system_prompt` 会把已有 cch 重置为占位符，`rewrite_body_inner` 在消息改写、缓存断点和 TTL 改写后序列化并调用 `compute_cch_attestation`。signature retry 修改 body 后会调用 `refresh_cch_attestation` 重新计算。

API 模式需要额外处理一个现有差异：gateway 层会从改写后的 body 中清理 `_session_id` 并重新序列化。实现时必须避免“先签 CCH、后删 `_session_id`”：

- 推荐做法：API 模式不再把 `_session_id` 写入将发往上游的 body，session id 通过返回值或独立上下文传给 header/telemetry。
- 兼容做法：保留 `_session_id` 临时字段，但把 API mimicry 的 CCH 签名延后到 `clean_session_id_from_body` 和最终序列化之后。

无论采用哪种做法，测试必须验证签名输入就是最终上游 body。

message cache 断点策略对 API 模式单独处理：API 模式只要全局设置不是 `off`，统一使用 sub2api 风格的稳定断点算法，即清理 `messages` 内已有断点后，只给最后一条 message 和倒数第二个 `role=user` message 的最后可缓存 block 打断点。这个算法避免复用 Claude Code 并行 tool 专用的 rolling/lookback 选择器，减少 API 长历史里断点位置持续漂移。

全局设置额外提供 `sub2api` 模式，允许真实 Claude Code 客户端显式切到同一算法做线上对照。该模式只接管 `messages` 断点，不主动清理 system/tools 断点；`auto` / `rolling` / `stateful` 的 Claude Code 专用逻辑保持不变。

headers 应继续由 `rewrite_headers` 统一产出。API 模式应尽量使用 Claude Code 画像的固定 header 集合与顺序，且 `X-Claude-Code-Session-Id` 与 body `metadata.user_id.session_id` 对齐。

## Compatibility

- API 模式不能删除客户端已有 tools；只在缺失时补 `tools=[]`。
- `tool_choice` 是否保留需要谨慎：如果真实 Claude Code 主请求不会发送该字段，可以规范化为缺省；但不能破坏依赖工具强制选择的兼容请求。
- Haiku 标题、小探测、无 system/tools 请求需要保持轻量兼容，可按模型或请求形态旁路 system mimicry。
- TTL 改写不创建新的 cache_control，message cache 策略才负责新增断点。

## Non-Goals

- 不把真实 Claude Code 抓包中的项目级编码规范 prompt 默认注入 API 模式。
- 不改变真实 Claude Code 客户端模式的 system prompt 内容来源。
- 不让 API 模式复用 Claude Code 并行 tool 专用的 rolling/lookback/stateful 选择器。

## Rollout / Rollback

优先通过全局设置或现有 API 模式开关启用，不改变真实 Claude Code 客户端模式默认行为。若线上出现 API 模式行为污染，可回滚到原短 banner 注入或关闭 API mimicry。
