# Brief — cc2api 自动遥测真实画像长期对齐

## Goal

- 建立并分阶段实现 `cc2api` auto telemetry 与真实 Claude Code 2.1.195 抓包的事件、`additional_metadata`、请求链、usage 摘要和安全字段对齐，降低自动遥测开启时暴露模拟痕迹的风险。

## Scope

- 从 `23594999fa77` 和历史 2.1.187/2.1.185 抓包生成脱敏 telemetry event catalog，记录事件名、metadata key、字段类型、出现频率、来源和敏感等级。
- 设计并实现会话内 correlation 模型，包括 `queryChainId`、`requestId`、`messageID`、`previousRequestId` 等字段的稳定生成与账号/session 隔离。
- 分阶段补齐安全 metadata，第一阶段优先覆盖 `tengu_api_before_normalize` / `after_normalize` / `query` / `success`、tool、attachment、cache breakpoints 等事件。
- 从非流和流式响应摘要中补齐 token/cache/ttft/duration/stop_reason 等数值字段。
- 增加脱敏 diff 脚本和单测，验证字段密度、事件名分布、metadata key 分布、env shape 和敏感字段缺失。

## Non-Goals

- 不提交原始 telemetry body 或完整抓包。
- 不写入 prompt、tool input、响应正文、token、Cookie、邮箱、完整账号 UUID。
- 不一次性复刻所有 Claude Code 本地 UI / 工具状态。
- 不修改 `/v1/messages` 主请求 body 顺序；该项由 `cc2api-json-body-order-fingerprint` 处理。

## Key Context

- 主要风险文件：`cc2api/src/service/telemetry.rs`、`cc2api/src/service/gateway.rs`、`cc2api/src/model/identity.rs`、`cc2api/src/store/account_store.rs`。
- `TelemetryService` 需要从固定少量事件字段演进为按事件类型生成安全 metadata 模板。
- 请求/响应摘要继续由 `GatewayService` 提供，禁止把完整 body 传进 telemetry queue。
- correlation state 必须按账号/session 隔离，不能跨账号复用 ID 链。
- 字段来源分为请求体可推导、响应可推导、网关运行时可推导、客户端本地不可得、禁止发送五类。
- 高风险环境仍可通过账号级 `auto_telemetry` 关闭；如新增阶段性设置，应允许关闭具体增强。

## Acceptance

- 有脱敏 telemetry event catalog，覆盖 2.1.195 抓包主要事件名和 metadata key。
- 每个字段标注来源和敏感等级。
- 至少实现一阶段安全字段补齐，并有单测覆盖。
- auto telemetry 开启时字段密度和事件差异比当前更接近真实抓包。
- 不新增敏感正文、token、Cookie、邮箱、完整账号 UUID 泄露。
- 有远程灰度抓包验收步骤和回滚策略。

## Next Step

- 确认 planning artifacts 和本 brief 后，运行 `task.py start` 激活该任务；实现前读取 cc2api backend/protocol spec，并从 Phase A 事件目录与字段分级开始。
