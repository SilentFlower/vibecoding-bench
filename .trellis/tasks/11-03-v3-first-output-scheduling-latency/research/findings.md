# 已核对的实现事实

- 当前父仓HEAD为91908eee（自动closed-task GC），cc2api为935cb1b，产品代码尚未改动；既有用户334个dirty文件保留。旧部署已永久退役，本轮只更新v3。
- `usage.rs`唯一`UsageCapture`已有有界SSE/JSON与gzip/br/zstd解码。`UsageParser.observe_value`在完整SSE事件空行派发时处理JSON，JSON在`complete_observation`解析；`MessageObservation`目前无首输出时间。
- `diagnostics.rs`的`AttemptTrace.commit`在准入后重设`std::time::Instant`；`headers`写`AttemptDiagnostic.ttft_ms`，当前语义为响应头耗时。`finish`以capture.observation决定success/partial/upstream_error，再调用`SchedulingRequest.finish_observed_attempt`。
- `request_diagnostics.rs`：`DiagnosticParameters`为model/max_tokens/thinking_type/thinking_budget/effort/stream/tools_count；`AttemptDiagnostic`存`summary_json`，新增可选字段无需物理列迁移。
- `diagnostics.rs:646 parameters`只接受安全claude-*模型（128字节、ASCII字母数字和-_.、排除sk-ant-）；thinking.type为enabled/disabled/adaptive；effort为low/medium/high/xhigh/max/default/none；预算为u64。将此构造函数移到参数类型owner复用，保持白名单不扩权。
- `gateway.rs:2019`在已解析body_map上创建`scheduler.begin(token,sid)`，此处可附带冻结请求参数。最终上游body才创建诊断记录，但本轮延迟分组按同一请求准入参数冻结，重试不变。
- `v3_scheduling.rs`：`Feedback`健康和latency都按账号存进程内；健康alpha0.2/容量0.4、半衰期15min；成功延迟EWMA0.2、尺度10sec。`RequestLease`当前只有scheduler/id/key/config/deadline/binding/attempt_started。
- `AccountService.v3_summary`没有请求模型上下文；管理卡片应保留账号汇总并明示范围，实际choose使用对应请求分组。
- `response_headers`仅在没有diagnostic时回灌；改造后保持健康反馈、禁止用头部耗时补首输出。正式messages通常已有CURRENT_TRACE。
- 管理端只有Settings.vue与SchedulingDetails.vue直接写“响应头延迟”；目前未找到独立诊断展示组件，新增首输出字段由既有诊断API输出，原ttft_ms保留旧语义。
- 正式发送链先prepare/admit、commit诊断、permit.submitted，再transport.submit；计时不能提前到排队。无真实模型压力探针。

## 官方事件合同

- https://platform.claude.com/docs/en/build-with-claude/streaming ：非空text_delta.text、thinking_delta.thinking、input_json_delta.partial_json；message_start/空内容块/ping/签名不是有效输出。工具调用的content_block_start包含实际tool_use身份和名称，可作为有效调用开始。
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/server-tools ：server_tool_use也按工具调用流式事件发送。

## 尚待落地的最小设计

首输出只扩展上述观察器；未知保持None。每账号健康反馈继续共享，延迟按模型、thinking.type/budget_tokens、effort、stream分组；每账号最多64组，LRU淘汰只恢复中性不拒绝业务。管理端汇总延迟继续独立维护。保持5分近优轮换与全部既有准入/平滑/绑定逻辑。
