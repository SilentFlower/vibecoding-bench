# cc2api API 模式对齐 Claude Code 请求画像

## Goal

让 cc2api 的 API 模式在使用 Anthropic OAuth 账号转发 `/v1/messages` 时，更接近真实 Claude Code 请求画像，重点参考 sub2api 的完整 mimicry 链路，减少第三方识别、缓存断点异常和 billing/cch 不一致风险。

本任务只覆盖 API 模式的 Claude Code-like 请求改写；真实 Claude Code 客户端模式继续保持透传/局部改写，不引入会改变 Claude Code 原生 system prompt 和消息历史语义的行为。

## Background / Known Context

- sub2api 对“非 Claude Code 客户端 + Anthropic OAuth 账号”会执行完整 Claude Code mimicry：重写 system 为 billing block + Claude Code banner + 中性扩充 prompt，原始 system 移入 messages，补齐 metadata、headers、message cache 断点、tools 断点，并在最终 body sanitize 后计算 cch。
- cc2api 当前 API 模式只注入短 banner system、剥离 system/messages cache_control、补 `tools=[]`、强制 `stream=true`，不会给 API 模式生成 billing block/cch，也不会走 message cache 断点修复。
- cc2api 当前 Claude Code 客户端模式在 `billing_mode=rewrite` 时已经是“先把已有 cch 重置为 `cch=00000`，完成 body 改写和序列化后再用 xxHash64 计算并替换”。签名相关重试改写 body 后也会刷新 cch。
- 真实 Claude Code 抓包里的项目/编码规范 system prompt 来自客户端当前上下文；API 模式不应默认注入项目级规范，避免改变模型行为。

## Requirements

- API 模式应支持 sub2api 式 Claude Code mimicry system 形态：生成 billing attribution block、Claude Code banner block、工具无关的中性扩充 prompt block。
- API 模式原始客户端 system 不应丢失，应迁移到 messages 开头或采用等价机制保留语义。
- API 模式应生成稳定的 `metadata.user_id` / `X-Claude-Code-Session-Id` 会话标识，避免每轮随机导致上游画像和缓存不稳定。
- API 模式应为 billing block 生成 `cc_version=版本.指纹; cc_entrypoint=cli; cch=00000;` 占位，并保证所有 body 改写完成后再计算 cch。
- API 模式如果存在发送前临时字段清理或 body sanitize，CCH 签名必须发生在这些最终清理之后。
- API 模式应接入 message cache 断点修复策略，至少覆盖 auto/rolling/stateful 的当前系统设置语义，且不能删除客户端已有 tools。
- API 模式应尽量对齐 Claude Code headers/beta 顺序和集合；不应依赖客户端传入的非 Claude Code header 画像。
- TTL 改写只覆盖已有 ephemeral `cache_control.ttl` 或代理新建断点，不应因为 TTL 设置额外新增缓存断点。
- Haiku、小探测请求、无 system/tools 的请求需要保持兼容，不能因为 mimicry 破坏轻量请求。

## Acceptance Criteria

- [x] API 模式 `/v1/messages` 能生成 billing + banner + expansion 的 system block，并保留原始 system 指令语义。
- [x] API 模式 billing cch 使用 `00000` 占位，最终 body 改写完成后再计算 xxHash64 并替换。
- [x] API 模式最终发往上游的 body 不包含内部临时字段，且 CCH 基于这个最终 body 计算。
- [x] API 模式不删除客户端传入的 `tools`，`tools=[]` 只在缺失时补齐。
- [x] API 模式可按当前系统设置应用 message cache 断点修复。
- [x] Claude Code 客户端模式现有 CCH 顺序保持不退化。
- [x] 单元测试覆盖 API mimicry system、CCH 顺序、tools 保留、message cache 接入和 Claude Code 模式回归。
- [x] `cargo test` 通过目标相关测试。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
