# cc2api API 模式 max_tokens 对齐 Claude Code 抓包

## Goal

让 cc2api 在 API 模式下生成更接近 Claude Code 2.1.156 抓包的 `/v1/messages` `max_tokens`，避免当前 `>32768 => 16384` 的规则把 Opus 4.8 官方风格请求压低，同时为缺失 `max_tokens` 的非 Claude Code 客户端提供稳定默认值。

## Background / Known Context

- 用户确认抓包位于 `data/flows/auto-2/1887/46ba25a8d791/http_capture.jsonl`。
- 抓包中 Claude Code 2.1.156 主链路 Opus 4.8 请求为 `model=claude-opus-4-8`、`max_tokens=64000`、`stream=true`、`thinking={"type":"adaptive"}`。
- 抓包中 `claude-opus-4-8[1m]` 出现在遥测/客户端内部字段，真实 `/v1/messages` 请求 body 里的模型是 `claude-opus-4-8`。
- 抓包中 Haiku 有两类请求：`max_tokens=1` 的轻量探测，以及 `max_tokens=32000` 的 `generate_session_title` 标题生成请求。
- `/api/eval/*` 返回的 `tengu_amber_wren.value.maxTokens=25000` 是远程配置字段，不是 Anthropic `/v1/messages` 请求体的 `max_tokens`。
- cc2api 当前 Claude Code 模式不改写 `max_tokens`；API 模式只在传入 `max_tokens > 32768` 时改成 `16384`。
- 本任务只处理 cc2api 代码库 `/root/project/cc2api`。

## Requirements

- Claude Code 模式必须继续保持 `max_tokens` 原样，不新增默认值，不降低上限。
- API 模式在 `/v1/messages` 请求缺失 `max_tokens` 时必须补默认值：
  - `claude-opus-4-8` 补 `64000`。
  - Haiku 模型补 `32000`。
  - 其他 Claude 模型补 `32000`。
- API 模式在 `/v1/messages` 请求已传 `max_tokens` 时必须按规则规范化：
  - `max_tokens=1` 必须保留，避免破坏 Haiku 探测。
  - `max_tokens <= 64000` 必须保留。
  - `max_tokens > 64000` 必须降到 `64000`。
- 不得使用 `/api/eval/*` feature flag 中的 `maxTokens=25000` 作为 `/v1/messages` 默认值。
- 保持现有 API 模式其他改写行为不变，包括 metadata 注入、`stream=true`、tools 默认值、cache_control 剥离、system prompt 注入。
- 添加聚焦测试覆盖上述行为，避免后续回归。

## Acceptance Criteria

- [ ] API 模式缺失 `max_tokens` 且模型为 `claude-opus-4-8` 时，改写后 body 包含 `max_tokens=64000`。
- [ ] API 模式缺失 `max_tokens` 且模型为 Haiku 时，改写后 body 包含 `max_tokens=32000`。
- [ ] API 模式缺失 `max_tokens` 且模型为其他 Claude 模型时，改写后 body 包含 `max_tokens=32000`。
- [ ] API 模式 `max_tokens=1` 时保持为 `1`。
- [ ] API 模式 `max_tokens=64000` 时保持为 `64000`。
- [ ] API 模式 `max_tokens=128000` 时降为 `64000`。
- [ ] Claude Code 模式不会改写、补充或降低 `max_tokens`。
- [ ] 相关 Rust 测试通过。

## Out of Scope

- 不改写 `thinking` 策略。
- 不修改 `anthropic-beta` / 1M context 选择逻辑。
- 不修改 sub2api。
- 不修改自动遥测或 prime 预热逻辑。
- 不把 API 模式伪装完全扩展为 Claude Code 全量行为。
