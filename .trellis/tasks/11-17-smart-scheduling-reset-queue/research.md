# 源码依据

- 当前分支 `flower2api`，规划时 HEAD `abf5f51d124236acabd4560ff3d2576d5bcca63e`。
- `services/gateway/src/service/v3_scheduling.rs`：`LatencyClass`／`LatencySample`、`MAX_LATENCY_CLASSES=64`；`factors_for_class` 查内存分组；`choose` 先资格容量与人工优先级，再即时容量与近优轮转。
- `services/gateway/src/service/diagnostics.rs::AttemptTrace::finish`：首输出、完整性和成功终态已具备；总耗时目前在反馈之后写入，需要在扩展反馈时统一采样时间。
- `services/gateway/src/store/settings_store.rs`：调度默认表、字符串设置与 `ensure_native_idle_timeout` 的兼容补齐先例。
- `services/gateway/src/store/database_schema.rs`：冻结的历史默认表；`database_migrations.rs::schema_checksum` 校验纯迁移源码，新增设置应使用独立幂等补齐入口。
- `apps/web/src/components/Settings.vue`：四项权重草稿、整体合法性、字段桥接与保存；`apps/web/src/lib/settingsSchema.ts` 为页面元数据源。
- `apps/web/src/components/SchedulingDetails.vue`、`apps/web/src/api.ts`：既有四项摘要和可选字段兼容。
- `/root/project/codex-proxy-rs` HEAD `9d2aad95ece02c34634cf19e84cec1244d2bb21c`：`account/scheduling.rs` 的两级重置系数与未来窗口奖励；`account/selection.rs::wait_for_capacity` 将队列系数限定于等待选择。
- 本任务属于一个统一评分合同和设置热更新交付，采用单任务组织；具体模型额度与全套选号追踪为后续范围。
