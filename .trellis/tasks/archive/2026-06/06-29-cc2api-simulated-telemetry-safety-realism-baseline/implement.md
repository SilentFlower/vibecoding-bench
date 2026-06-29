# 实施计划

## Step 1：上下文与规格读取

- [x] 读取 `cc2api` backend/protocol spec。
- [x] 复核 `TelemetryService` batch 构造、`GatewayService` telemetry context 和现有 telemetry 单测。
- [x] 明确当前固定假值字段清单。

## Step 2：清理明显假值字段

- [x] 移除或条件化 `costUSD=0.0`、`buildAgeMins=0`、内存 delta/hook duration 固定 0。
- [x] image/document/tool/attachment 只保留可安全推导字段。
- [x] 增加单测确认明显假字段不再出现在相关事件 metadata 中。

## Step 3：最终 payload 安全扫描

- [x] 增加 batch 发送前 scanner，覆盖顶层 event_data 和 base64 `additional_metadata`。
- [x] 实现 key denylist、value pattern、长文本限制和允许路径。
- [x] 命中后清理字段或丢弃事件，并返回扫描摘要。
- [x] 增加敏感字段不泄露单测，确保日志不包含原值。

## Step 4：结构化诊断日志与 shape summary

- [x] 发送前记录 event count、event name counts、扫描摘要。
- [x] 发送后记录 status code 或 error kind。
- [x] 增加脱敏 shape summary helper 或测试输出结构，供后续 catalog diff 使用。

## Step 5：correlation fallback

- [x] 将 correlation session key fallback 从随机 request key 改为 telemetry session 的 `run_profile.session_id`。
- [x] 增加单测确认缺少 body session id 时同一 auto telemetry session 内 query chain 连续。

## Step 6：验证

- [x] `cd cc2api && cargo fmt --check`
- [x] `cd cc2api && cargo test telemetry --lib`
- [x] `cd cc2api && cargo test message_telemetry --lib` 或相关 gateway telemetry 测试
- [x] 如影响更广，再运行 `cd cc2api && cargo test`

## 风险文件

- `cc2api/src/service/telemetry.rs`
- `cc2api/src/service/gateway.rs`
- `cc2api/src/model/identity.rs`
