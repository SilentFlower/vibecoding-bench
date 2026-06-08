# Claude Code 并行 tool 与 prompt cache 断点研究

## Anthropic 文档结论

来源：

* `https://docs.claude.com/en/docs/build-with-claude/prompt-caching`
* `https://docs.claude.com/en/agents-and-tools/tool-use/tool-use-with-prompt-caching`
* `https://docs.claude.com/en/docs/build-with-claude/cache-diagnostics`

关键点：

* prompt cache 前缀顺序是 `tools -> system -> messages`。
* 每个 cache breakpoint 只写入该断点位置的前缀缓存。
* 下一次请求在断点处未命中时，只向前回看最多 20 个 block。
* 对增长会话，如果单轮新增 20 个或更多 block，上一轮最后断点可能落在 lookback 窗口外。
* 最多可定义 4 个 cache breakpoint。
* tool definitions 修改会使整个 cache 失效；`disable_parallel_tool_use` 变化会使 messages cache 失效。
* cache diagnostics beta 可帮助定位 model/system/tools/messages 的首个差异，但本任务不直接依赖该 beta。

## GitHub issue 63930 结论

来源：`https://github.com/anthropics/claude-code/issues/63930`

issue 报告 Claude Code v2.1.154+ / Opus 4.8 在大量并行 `tool_use` 后出现 message-history cache invalidation。表现为下一轮 `cache_read` 回退到 system+tools floor，`cache_creation` 接近整段 message history。issue 作者统计：floor miss 大多紧跟 12 个以上并行 `tool_use` 的回合。

这与用户在 cc2api 中的复现一致：cc2api 透传客户端原始 `cache_control` 后，并行 tool 仍能复现，因此代理级修复应面向“增强 message breakpoint 布局”，而不是只修 TTL 或 header。

## 对 cc2api 的设计启发

* `off` 必须保留，作为客户端原始行为和回滚开关。
* 旧 `stable` 只打两个断点，不足以覆盖一次新增 20+ block 的并行 tool 回合。
* 新策略应在 messages 尾部按 20-block lookback 规则滚动放置多个断点。
* 因 Anthropic 总断点上限为 4，必须考虑 system/tools 现有断点占用。
* 中途修改 `disable_parallel_tool_use` 会改变 messages cache 维度，若要加串行兜底，也应作为独立模式且提示不要在同一长会话中频繁切换。
