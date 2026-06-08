# cc2api 当前状态与差异

## API 模式现状

当前主要逻辑在 `/root/project/cc2api/src/service/rewriter.rs`。

API 模式 `/v1/messages` 当前行为：

- 注入 `metadata.user_id`。
- 删除 `temperature`、`top_k`、`top_p`、`stop_sequences`、`tool_choice`。
- 缺失时补 `tools=[]`，不会删除已有 tools。
- 强制 `stream=true`。
- 调用 `strip_cache_control` 移除 system 和 messages content block 上的 cache_control。
- 调用 `normalize_api_max_tokens`。
- 只注入短 Claude Code banner：`You are Claude Code, Anthropic's official CLI for Claude.`，并带 ephemeral cache_control。

缺口：

- 不生成 billing attribution block。
- 不生成 `cc_version` 指纹和 `cch=00000` 占位。
- 不在 API 模式执行 message cache 断点修复。
- API 模式存在发送前清理 `_session_id` 后再次序列化的步骤；若未来在清理前计算 cch，会导致 cch 对不上最终 body。
- 原始 API system 仍可能作为 system block 留在 banner 后面，和 sub2api 的“迁移到 messages”策略不同。

## Claude Code 模式 CCH 顺序

当前 Claude Code 模式在 `billing_mode=rewrite` 下的顺序基本正确：

1. `rewrite_system_prompt` 替换 `cc_version=<version>.<fp>`。
2. `rewrite_system_prompt` 将已有 `cch=<hex>` 重置为 `cch=00000`。
3. `rewrite_body_inner` 继续执行 message cache 断点改写和 TTL 改写。
4. `rewrite_body_inner` 将最终 JSON 序列化为 body 字节。
5. `compute_cch_attestation` 对带 `cch=00000` 的最终 body 计算 xxHash64 并替换真实 cch。

signature retry 路径如果清理 thinking/tool 相关块，会通过 `refresh_cch_attestation` 先把旧 cch 改回 `00000`，再重新计算。

## 本任务实现风险

- API 模式如果生成 billing block，CCH 计算必须发生在 `_session_id` 清理和所有 body sanitize 之后。
- 如果保留 API 模式当前 `strip_cache_control`，会和新 system expansion / message cache 断点策略冲突，需要调整调用顺序。
- API 模式接入 stateful cache 时，session key 必须稳定，否则 stateful 主线会被随机 session 污染。
- `tool_choice` 删除需要重新评估。真实 Claude Code 画像和 API 兼容性有冲突时，优先避免破坏用户传入 tools。
