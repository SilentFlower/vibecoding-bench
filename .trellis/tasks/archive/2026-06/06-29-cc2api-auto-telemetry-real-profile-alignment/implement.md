# 实施计划草案

## Step 1：研究目录

- [x] 从 2.1.195 抓包生成脱敏 telemetry event catalog。
- [x] 标注 metadata key 的出现频率、字段类型、来源和敏感等级。
- [x] 与 2.1.187/2.1.185 对比 shape 差异。

## Step 2：相关性 ID 模型

- [x] 设计 `queryChainId` / `requestId` / `messageID` / `previousRequestId` 生成规则。
- [x] 按账号和 telemetry session 隔离状态。
- [x] 增加 ID 稳定性和不跨账号复用测试。

## Step 3：事件模板第一阶段

- [x] 补齐 `tengu_api_before_normalize` / `after_normalize` / `query` / `success` 的安全 metadata。
- [x] 补齐 tool / attachment / cache breakpoints 的安全 metadata。
- [x] 确保不传 prompt、tool input、响应正文。

## Step 4：usage 与响应摘要

- [x] 从非流和流式响应提取 usage 数值摘要。
- [x] 写入 token/cache/ttft/duration/stop_reason 等字段。

## Step 5：diff 和远程验收

- [x] 增加脱敏 diff 脚本。
- [x] 跑单测和集成检查。
- [x] 远程灰度抓包验收步骤已记录，实际远程抓包需部署后执行。

## 风险文件

- `cc2api/src/service/telemetry.rs`
- `cc2api/src/service/gateway.rs`
- `cc2api/src/model/identity.rs`
- `cc2api/src/store/account_store.rs`
