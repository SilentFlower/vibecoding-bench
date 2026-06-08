# 代理级修复 Claude Code 并行工具缓存失效

## Goal

在 cc2api 中增加代理级 Claude Code prompt cache 保护能力，缓解 Claude Code 并行 tool 场景下 Anthropic message-history 缓存断点超过 20-block lookback 后失效的问题，降低长会话中 `cache_creation_input_tokens` 反复重写整段历史的成本。

## Background / Known Context

* 用户在 `/root/project/cc2api` 通过 Claude Code 使用 Anthropic `/v1/messages`，多次复现 `cache_read_input_tokens` 固定、回退或归零，同时 `cache_creation_input_tokens` 大幅累加。
* 用户已做 A/B：cc2api 改成透传客户端原始 `cache_control` 后，并行 tool 场景仍可复现，说明 `message_cache_control_rewrite=stable` 不是唯一根因。
* Anthropic 文档说明：prompt cache 前缀顺序为 `tools -> system -> messages`；每个 cache breakpoint 最多回看 20 个 block；最多 4 个 cache breakpoint；当增长会话单轮新增 20 个或更多 block 时，需要额外 breakpoint 覆盖旧写入位置。
* GitHub issue `anthropics/claude-code#63930` 报告同类问题：Claude Code v2.1.154+ / Opus 4.8 在大量并行 `tool_use` 后，下一轮 `cache_read` 回退到 system+tools floor，message history 被整段重写；issue 仍为 open。
* cc2api 当前已有 `cache_control_ttl_rewrite=off|5m|1h` 和 `message_cache_control_rewrite=off|stable`；`stable` 会清理 `messages[].content[].cache_control` 后只在最后 message 与倒数第二个 user turn 重打断点，无法保证覆盖并行 tool 带来的大 block 跨距。
* cc2api 当前 `/v1/messages` body 改写发生在 CCH attestation 重新计算之前；本任务新增的 body 改写必须继续保持最终 CCH 正确。
* sub2api 旧处理思路主要是保留客户端断点、TTL 改写 opt-in；本任务不等同于 sub2api 的 TTL 改写，而是新增代理级 message breakpoint 策略。
* MVP 已确认按 `rolling` 断点修复走，不在本任务内加入“强制禁用并行 tool”的兜底模式。
* 2026-06-07 复现 `claude --resume 46cb6503-716b-46ee-9c16-971fc2d5c2ba` 显示：`cache_read_input_tokens` 卡在约 71k，`cache_creation_input_tokens` 从 21k 继续涨到 112k/137k，说明单纯移动 message 断点仍无法覆盖 prefix 抖动。
* `cnighswonger/claude-code-cache-fix` 将 non-deterministic tool ordering 列为 cache busting 根因，并通过 `sort-stabilization` 对 `tools[]`、skills 列表和 deferred tools 列表做确定性排序。

## Requirements

* 新增一个可配置的代理级 message cache 策略，用于 Claude Code `/v1/messages` 请求。
* 默认行为必须保持 `off`，即透传客户端原始 message `cache_control`，避免升级后默认改变用户流量。
* 保留旧 `stable` / `anchored` 配置值的兼容入口，但不再保留独立运行路径；旧值应归一到推荐的 `auto` 策略。
* 新策略必须能在并行 tool 一轮新增大量 `tool_use/tool_result` block 时，为 message history 放置最多 4 个滚动断点，尽量覆盖 Anthropic 20-block lookback。
* 新策略必须在放置 message 断点之前稳定化 Claude Code cache prefix：`tools[]` 按 `name` 排序，skills / deferred tools 文本列表按条目排序，避免并行 tool 场景下前缀顺序抖动导致 message 断点完全失效。
* 新策略不得在 `thinking` 或 `redacted_thinking` block 上直接放置 `cache_control`。
* 新策略不得改写非 Claude Code 客户端，不得改写非 `/v1/messages` 请求。
* 新策略必须与 `cache_control_ttl_rewrite` 独立：TTL 设置只改写已有或策略新建的 ephemeral breakpoint 的 `ttl`，不得额外新建断点。
* 新策略修改请求体后，必须确保 CCH attestation 基于最终请求体重新计算。
* 设置接口和前端设置页必须能选择新策略，并能回滚到 `off`。
* 测试必须覆盖 parse、body 改写、TTL 组合、非 Claude Code 忽略、CCH 重新计算。

## Acceptance Criteria

* [ ] `message_cache_control_rewrite` 支持 `off`、推荐 `auto` 和激进对照 `rolling`，并将旧 `stable` / `anchored` 兼容解析为 `auto`。
* [ ] 在包含 40 个以上尾部可缓存 message blocks 的请求体中，新模式最多设置 4 个 message `cache_control`，且相邻断点距离不超过 20 个可缓存顶层 message block。
* [ ] 新模式会先清理请求根级、system、tools 和 messages 内客户端旧断点，再按确定性规则重放，且不会超过 Anthropic 4-breakpoint 限制。
* [ ] 新模式会稳定化 `tools[]`、skills 列表和 deferred tools 列表；相同集合的不同输入顺序在 rewrite 后应得到一致顺序。
* [ ] `cache_control_ttl_rewrite=5m|1h` 能覆盖新模式创建的断点 TTL；`off` 保持默认 TTL。
* [ ] CCH 测试证明新增断点后 billing rewrite 模式下的 `cch=` 值已按最终 body 更新。
* [ ] 前端设置页能保存和回显 `off`、`auto`、`rolling`，说明 `off` 是回滚开关；历史 `stable` / `anchored` 回显为 `auto`。
* [ ] 后端单元测试通过；能运行的前端构建或类型检查通过。

## Out of Scope

* 不修改 Claude Code 客户端本身。
* 不强制禁用所有并行 tool；串行兜底模式如后续需要，单独开任务。
* 不修复工具集合本身增删导致的全前缀变化；本任务只修复相同工具集合的顺序抖动。
* 不持久化会话级 cache 状态，不在代理内记录原始 prompt 内容。

## Research References

* `research/prompt-cache-parallel-tool.md`
* Anthropic Prompt caching: `https://docs.claude.com/en/docs/build-with-claude/prompt-caching`
* Anthropic Tool use with prompt caching: `https://docs.claude.com/en/agents-and-tools/tool-use/tool-use-with-prompt-caching`
* GitHub issue: `https://github.com/anthropics/claude-code/issues/63930`
