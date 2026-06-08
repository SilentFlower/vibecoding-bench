# cc2api API 模式 max_tokens 对齐 Claude Code 抓包

## Technical Design

改动边界在 cc2api 的 `/v1/messages` body 改写逻辑，预计位于 `/root/project/cc2api/src/service/rewriter.rs` 的 API 模式分支。

新增一个局部 helper，例如 `normalize_api_max_tokens(body: &mut serde_json::Value)`，只在 `ClientType::API` 分支调用。Claude Code 分支不调用该 helper，保证官方客户端请求原样通过。

`normalize_api_max_tokens` 的规则：

- 读取 `model` 字符串，使用小写判断模型族。
- 缺失 `max_tokens` 时：
  - `claude-opus-4-8` 使用 `64000`。
  - 包含 `haiku` 的 Claude 模型使用 `32000`。
  - 其他模型使用 `32000`。
- 已存在 `max_tokens` 时：
  - 可解析为数字且 `> 64000` 时写回 `64000`。
  - 其他值保持原样，包括 `1`。

该 helper 不处理 `/api/eval/*` 的 `maxTokens`，也不读取 GrowthBook feature flag。`maxTokens=25000` 是远程配置值，不应和 Anthropic body 字段混用。

## Compatibility

这会改变非 Claude Code 客户端在 API 模式下的行为：以前大于 `32768` 会被压到 `16384`，改后 `32769..64000` 保留，超过 `64000` 才压到 `64000`。这更接近 Claude Code 2.1.156 的 Opus 4.8 抓包。

缺失 `max_tokens` 的 API 模式请求以前会原样缺失并可能被上游拒绝，改后会在本地补默认值，提升兼容性。

## Rollout / Rollback

该改动是纯请求体改写逻辑，无数据库迁移。回滚方式是恢复 `rewriter.rs` 中 API 模式 `max_tokens` 规范化逻辑。
