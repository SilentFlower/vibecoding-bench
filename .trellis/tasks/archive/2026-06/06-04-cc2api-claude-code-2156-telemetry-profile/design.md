# cc2api Claude Code 2.1.156 遥测事件画像优化设计

## Technical Design

### 安全输入边界

抓包分析只输出结构化摘要：

- endpoint、method、status、时间间隔。
- event type、event name、字段名、字段类型、出现次数。
- batch size、事件顺序、事件类别。
- 请求体和响应体只允许输出 hash、长度和字段路径，不输出原文。

### 模块边界

- `telemetry.rs`：负责事件队列、事件模板、v2 batch 构造、后台发送。
- `gateway.rs`：在 `/v1/messages` 请求开始、上游响应成功/失败、429 重试等节点记录事件摘要。
- `rewriter.rs`：继续负责真实客户端 telemetry body 的身份字段改写。
- `version_profile.rs`：继续集中维护 event logging endpoint、UA 和 beta token。

### 数据流

1. `/v1/messages` 进入 gateway 时创建请求上下文摘要：账号、model、session id、request id、body 长度、是否 stream、开始时间。
2. header/body rewrite 后记录 normalize 前后事件，但只保存字段级摘要。
3. 上游响应完成后记录 success、slow first byte、error 或 retry 事件。
4. telemetry 队列按真实抓包的 batch 形态聚合事件，再发送到 `/api/event_logging/v2/batch`。
5. 后台周期事件仍保留，但只用于 startup、feature flag、GrowthBook 等低频事件，不再伪装成所有行为来源。

### 事件模板策略

首轮实现优先覆盖：

- 启动/初始化：`tengu_started`、`tengu_init`、`tengu_startup_telemetry`。
- API 生命周期：`tengu_api_before_normalize`、`tengu_api_after_normalize`、`tengu_api_query`、`tengu_api_success`、`tengu_api_slow_first_byte`。
- system prompt：`tengu_sysprompt_boundary_found`、`tengu_sysprompt_block`、`tengu_sysprompt_missing_boundary_marker`。
- 工具/权限：`tengu_tool_search_mode_decision`、`tengu_tool_use_can_use_tool_allowed`、`tengu_tool_use_granted_in_config`、`tengu_tool_use_success`。
- 技能/文件/附件：`tengu_skill_loaded`、`tengu_file_operation`、`tengu_attachment_compute_duration`。
- GrowthBook：保留 `GrowthbookExperimentEvent` 兼容字段。

### 隐私策略

- 事件模板不写入 prompt 原文、tool input 原文、响应正文、token。
- system prompt block 只允许写入 hash、长度、类型和边界信息。
- additional metadata 中的 gateway/baseUrl 字段继续剥离。
- 日志只打印事件数量、事件名和发送状态。

## Rollout / Rollback

- 新事件队列放在 `auto_telemetry` 后面，默认沿用账号开关。
- 保留旧单事件模板作为 fallback，便于队列异常时降级。
- 先用单元测试和本地 dummy upstream 验证字段，不依赖真实 token。
- 如新模板导致上游拒绝或噪声过大，可通过配置回退到当前最小遥测。
