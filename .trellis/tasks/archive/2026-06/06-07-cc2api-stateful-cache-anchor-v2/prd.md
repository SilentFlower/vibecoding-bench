# 代理级会话锚点防污染缓存策略

## Goal

在 `/root/project/cc2api` 中实现新的代理级 stateful message cache 策略，用会话级锚点保留和异常请求防污染机制，缓解 Claude Code 并行 tool、中断、停止、恢复等场景下请求体形态抖动导致 Anthropic prompt cache 反复重建的问题。

## Background / Known Context

* 用户多次通过 `claude --resume` 复现：`cache_read_input_tokens` 固定、回退或归零，`cache_creation_input_tokens` 每轮继续累加。
* 已做过透传 A/B，仍能复现，说明问题不只是 cc2api 改写 `cache_control` 造成。
* 旧 `anchored` 提交 `3f5cce8 fix(gateway): 增加会话锚定缓存断点模式` 已实现过“记录上一轮 selected block fingerprint、下一轮复用”的基础锚点，但用户实测无效，后续 `8ce812a` 将其移除并把 `anchored` 兼容解析为 `auto`。
* 最新复现 `claude --resume d15f7438-b85b-4bf5-8d2f-93b6e993e398` 显示，同一时间附近远程日志出现不同请求形态：
  * `10:19:41 message_content_blocks=76`
  * `10:19:59 message_content_blocks=567`
  * `10:19:59 message_content_blocks=78`
* 本地 JSONL 在 `read=0` 前可见主线顶层 content block 约 77 个，说明 `567 blocks` 是 Claude Code 构造的特殊请求，不是普通主线 history 自然增长。
* 特殊请求如果写入会话锚点，会污染后续正常 78-block 请求；旧 anchored 只有单一 `session_id -> anchors`，无法区分正常主线和异常请求，也无法处理同一秒多个请求互相覆盖。
* 当前 `auto` / `rolling` 是无状态选点，只看当前请求，遇到 `76 -> 567 -> 78` 这种形态切换会忘掉上一轮真正写过的缓存断点。

## Requirements

* 新增一个明确的 stateful 缓存策略，避免复用旧 `anchored` 名称直接恢复旧实现；建议配置值为 `stateful` 或 `sticky`。
* 新策略只对 Claude Code `/v1/messages` 生效，非 Claude Code 和非 messages 请求不改写。
* 新策略必须继续稳定化 cache prefix：`tools[]`、skills / deferred tools 文本列表、连续并行 `tool_use/tool_result` 顺序。
* 新策略必须清理旧 cache_control 后重新接管最多 4 个断点，且不得在 `thinking`、`redacted_thinking`、`assistant tool_use` 上放置断点。
* 新策略必须按 `account_id + Claude Code session_id` 管理会话状态，记录上一轮实际发送给上游的断点 fingerprint。
* fingerprint 必须剥离 `cache_control`，并能抵抗重复 block 误匹配；必要时纳入 role、block type、block 内容 hash、邻近上下文 hash。
* 新策略必须识别异常请求形态，至少包括：
  * 当前 `message_content_blocks` 相对主线锚点暴涨，例如超过 3 倍且绝对增量超过阈值。
  * 同一会话短时间内出现 block 数量差异巨大的并发请求。
  * 请求缺少正常线性用户 turn 特征，或看起来是中断/停止/总结/内部恢复请求。
* 异常请求可以临时放置断点以降低单次成本，但不得覆盖正常主线锚点。
* 正常请求应优先复用已命中的旧锚点，再用剩余 slot 放置 bridge / tail 断点。
* 同一会话并发请求写状态时必须有覆盖保护，不能让较早的异常请求或失配请求覆盖更新后的正常主线锚点。
* 新策略必须暴露诊断日志：模式、session key、block_count、request_class、reused_count、promoted/ignored reason、selected positions。
* 新策略必须保持 TTL 改写和 CCH 重算顺序正确：先 body/cache 策略，再 TTL，再 CCH。
* 前端设置页和 settings 接口必须能选择新策略，并保留 `off / auto / rolling` 回滚。

## Acceptance Criteria

* [ ] `message_cache_control_rewrite` 新增 stateful 策略值，并能从设置接口保存、回显、前端选择。
* [ ] 单元测试覆盖正常线性增长：上一轮断点 fingerprint 在下一轮找到并优先复用。
* [ ] 单元测试覆盖异常暴涨请求：`76 -> 567 -> 78` 中 567 请求不污染 78 主线锚点。
* [ ] 单元测试覆盖同一 session 并发覆盖保护：异常请求后写入不得覆盖正常请求锚点。
* [ ] 单元测试覆盖重复 block 场景：fingerprint 匹配不应误复用错误位置。
* [ ] 单元测试覆盖 TTL 组合：stateful 新建断点可被 `cache_control_ttl_rewrite=5m|1h` 覆盖。
* [ ] 单元测试覆盖 CCH：stateful body 改写后 `cch=` 基于最终 body 重算。
* [ ] 日志中可分辨 request_class、reused_count、selected、promotion/ignore reason。
* [ ] `cargo test message_cache_control --lib` 和完整后端测试通过；前端构建通过。

## Out of Scope

* 不修改 Claude Code 客户端。
* 不强制禁用并行 tool。
* 不保证前缀内容真实变化时仍能命中 Anthropic cache。
* 不持久化原始 prompt 文本；状态只保存结构化指纹和必要元数据。
* 不把旧 `anchored` 原样恢复为可选模式。

## Research References

* 旧实现：`/root/project/cc2api` commit `3f5cce8`
* 移除旧 anchored：`/root/project/cc2api` commit `8ce812a`
* 最新无状态选点修复：`/root/project/cc2api` commit `391da3a`
* 复现会话：`/root/.claude/projects/-root-project-cc2api/d15f7438-b85b-4bf5-8d2f-93b6e993e398.jsonl`
