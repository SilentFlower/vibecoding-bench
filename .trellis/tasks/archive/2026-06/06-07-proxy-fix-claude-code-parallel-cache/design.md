# design.md

## Technical Design

### Scope

改造目标是 `/root/project/cc2api` 的 Claude Code `/v1/messages` 请求体重写链路。入口保持在 `src/service/rewriter.rs` 的 `rewrite_body` 中，设置来源保持在 `src/service/gateway.rs` 与 `src/store/settings_store.rs`，管理 UI 入口保持在 `web/src/components/Settings.vue`。

### 模式定义

`message_cache_control_rewrite` 收敛为：

* `off`：默认值，保持客户端原始 `messages[].content[].cache_control`。
* `auto`：推荐的保守自动修复策略，稳定化 prefix 后优先在 text 边界放置断点，不主动选择 `assistant tool_use`。
* `rolling`：更积极的滚动断点对照策略，稳定化 prefix 后尽量补足可用断点；同样不选择 `assistant tool_use`，窗口回退优先 text，只有当前窗口没有 text 时才兜底使用 `user tool_result`。

历史配置字符串 `stable` / `anchored` 兼容解析到 `auto`，但不再保留独立运行路径。前端只展示 `off / auto / rolling`，避免继续暴露已被复现证明不可靠的会话锚定实验模式。

本任务已确认不新增 `disable_parallel_tool_use` 串行兜底模式。

### auto / rolling 断点策略

`auto` / `rolling` 只对 `ClientType::ClaudeCode` 生效。处理顺序：

1. 稳定化 cache prefix：`tools[]` 按 `name` 排序；`system[]` 和 `messages[0].content[]` 中的 skills 列表、deferred tools 列表按条目排序。
2. 清理请求根级、`system`、`tools` 和 `messages[].content[]` 顶层 block 上已有 `cache_control`，把 4 个断点预算集中给 message history。
3. 在 Anthropic 最多 4 个 breakpoint 的限制下，计算 message 可用断点数量。
4. 从 message history 尾部向前扫描可缓存顶层 content block，跳过 `thinking` 与 `redacted_thinking`，始终优先选择最后一个可缓存 block，再每隔最多 19 个真实顶层 message content block 选择一个断点。
5. `auto` 的尾部选择最新可缓存 block，可包含 `user tool_result`，避免大块工具结果落在缓存断点之后被反复重写。窗口回退只选择 `user/assistant text`，不为了用满 4 个断点强行落到高抖动 tool 区域。
6. `rolling` 尾部同样选择最新可缓存 block；窗口先选择 `user/assistant text`，只有当前 19-block 窗口完全没有 text 时才兜底选择 `user tool_result`，保留比 `auto` 更积极的对照能力。
7. 若 message 侧还有可用断点，尝试在 `messages[0].content[]` 中 Claude Code 自动注入块的末尾补一个边界断点，用于保护 hooks / skills / CLAUDE.md / deferred tools / MCP resources 这类被 Claude Code 放进首个 user message 的稳定前缀。
8. 最多放置可用数量个断点，优先覆盖尾部最近区间；写回时按原 message 顺序自然存在。

选择“最多 19 个可缓存 block 间隔”是为了适配 Anthropic 文档中的 20-block lookback：断点自身算第一格，因此连续断点之间最多隔 19 个可缓存位置，下一轮即使追加大量并行 tool block，也更可能命中前一轮写出的中间断点。

请求根级 `cache_control` 不算作 message history 尾部断点，也不应替代 message block 上的 `cache_control`。2026-06-07 的复现 `claude --resume 48e97f59-0be8-4526-a6f6-21d4833a8ee5` 证明，把根级 `cache_control` 当作“自动负责尾部”的假设会导致 message 侧少打断点，`cache_read_input_tokens` 固定在 system/tools floor。

2026-06-07 复现 `claude --resume 46cb6503-716b-46ee-9c16-971fc2d5c2ba` 进一步证明：即使 message 侧断点距离未超过 20-block lookback，`cache_read_input_tokens` 仍可能固定在 system/tools floor，原因很可能是 `tools[]`、skills 或 deferred tools 顺序抖动导致 message prefix 之前的 hash 已经变化。因此 `rolling` 需要同时做 prefix 顺序稳定化；该处理仅改变顺序，不新增或删除工具定义。

2026-06-07 后续复现显示 prefix 稳定化 + 激进 `rolling` 仍可能因为断点落到并行 tool 区域而失败。会话锚定实验也被复现证明不可靠，因为 Anthropic 命中完整 prefix，不是单 block 指纹。因此最终改为 `auto` 保守策略：减少断点数量和高抖动选点，优先保证所选 prefix 稳定。

### 与 TTL 改写的关系

保持现有顺序：先执行 message cache 策略，再执行 `rewrite_existing_ephemeral_cache_control_ttl`。这样 `auto` / `rolling` 新建的断点会被 TTL 设置覆盖；TTL 设置本身仍不创建断点。

### 与 CCH 的关系

保持现有 `rewrite_body` 结构：所有 body 变更完成并序列化后，再在 `BillingMode::Rewrite` 下调用 `compute_cch_attestation`。新增测试必须证明 `auto` 改写后 CCH 不是基于旧 body。

### 非 message 断点限制

Anthropic 总共最多允许 4 个 cache breakpoint。为避免 Claude Code 原始 system/tools 断点占掉 message history 的 slot，`auto` / `rolling` 会清理请求根级、system、tools 和 messages 内已有断点，再把最多 4 个断点集中用于 message history。

请求根级 `cache_control` 不参与本策略的 message slot 计算；本策略只约束 Anthropic 文档中真实承载前缀缓存的 `tools` / `system` / `messages[].content[]` block 断点。TTL 改写仍可覆盖根级已有 ephemeral `cache_control.ttl`，但在 `auto` / `rolling` 下根级断点会先被清理。

### 非目标问题

工具集合本身增删会改变 prompt 前缀开头，导致 `cache_read -> 0`；这与相同集合的顺序抖动不同。本任务只处理同一工具/skills/deferred-tools 集合的确定性排序，不尝试合成缺失工具或冻结动态工具集合。

## Rollout / Rollback

默认 `off`，线上升级后不会改变现有请求。用户可在设置页手动切到 `auto` 验证保守修复，也可切到 `rolling` 做激进对照。如出现异常，切回 `off` 即恢复客户端原始 `cache_control`。历史 `stable` / `anchored` 配置会归一为 `auto`。
