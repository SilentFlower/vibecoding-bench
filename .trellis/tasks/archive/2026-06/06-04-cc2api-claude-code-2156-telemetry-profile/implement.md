# cc2api Claude Code 2.1.156 遥测事件画像优化实施计划

## Implementation Checklist

- [x] 编写安全抓包摘要脚本或研究记录，输出 event logging 的事件目录和 batch 摘要。
- [x] 梳理当前 `telemetry.rs` 自动代发逻辑和 `rewriter.rs` telemetry 改写逻辑。
- [x] 设计 telemetry event context 和 event queue 数据结构。
- [x] 在 gateway 的 `/v1/messages` 生命周期接入事件记录点。
- [x] 实现首批 2.1.156 事件模板，覆盖 API 生命周期、system prompt、启动、工具/技能/附件和 GrowthBook。
- [x] 调整 batch 聚合节奏，避免固定机械心跳。
- [x] 增加隐私保护测试，确认日志和任务文档不包含请求体/响应体/token/prompt 原文。
- [x] 更新 README 或任务研究文档。

## Validation

- `docker run --rm -v /root/project/cc2api:/work -w /work rust:latest /usr/local/cargo/bin/cargo test`
- 专项测试应覆盖：
  - event queue 入队、聚合、过期和发送。
  - v2 batch body schema。
  - 真实 telemetry body 身份字段改写。
  - GrowthBook attributes。
  - 隐私字段不进入日志或模板。

## Review Gates

- 开始实现前确认事件目录只包含安全摘要。
- 提交前确认未添加 `data/flows/**` 原始抓包、`.flow`、token、prompt、响应体全文。
- 真实 telemetry 透传策略变更必须明确说明隐私影响。
