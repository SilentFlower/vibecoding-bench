# cc2api 自动遥测真实画像长期对齐

## Goal

建立并分阶段实现 `cc2api` auto telemetry 与真实 Claude Code 2.1.195 抓包的事件、`additional_metadata`、请求链、usage 摘要和安全字段对齐，降低自动遥测开启时暴露模拟痕迹的风险。

## 背景

- 2.1.195 抓包中 `/api/event_logging/v2/batch` 有 43 批、829 个事件。
- 当前 `cc2api` 已对齐 telemetry env 主字段，但 `additional_metadata` 明显更稀疏。
- 真实 `additional_metadata` 来自 Claude Code 本地运行状态机，包含请求链、消息、工具、附件、cache、token、耗时、权限模式等字段。
- 完全复刻需要多阶段，不适合塞进 2.1.195 升级收尾。

## 需求

- 建立脱敏 telemetry 事件目录，按事件名记录真实字段集合、字段类型、出现频率和可安全合成程度。
- 区分字段来源：请求体可推导、响应 usage 可推导、网关运行时可推导、客户端本地状态不可得、敏感不可发送。
- 设计 telemetry correlation 模型：`queryChainId`、`requestId`、`messageID`、`previousRequestId` 等字段如何在一次会话内稳定生成。
- 分阶段补齐安全字段，不记录 prompt、tool input、响应正文、token、Cookie、邮箱、完整账号 UUID。
- 为 auto telemetry 增加对齐测试和脱敏抓包回归对比脚本。
- 明确默认策略：高风险环境可以关闭 auto telemetry；开启时尽量接近真实字段密度和事件差异。

## 非目标

- 不提交原始 telemetry body 或完整抓包。
- 不为追求真实而写入敏感正文或凭据。
- 不在一个任务里一次性复刻所有 Claude Code 本地 UI / 工具状态。
- 不修改 `/v1/messages` 主请求 body 顺序；该项由子任务 `cc2api-json-body-order-fingerprint` 处理。

## 阶段建议

### Phase A：事件目录与字段分级

- 从 `23594999fa77` 和历史 2.1.187/2.1.185 抓包生成脱敏事件目录。
- 每个事件记录字段集合、字段类型、是否可推导、敏感等级。

### Phase B：请求链与基础 metadata

- 生成稳定 `requestId`、`messageID`、`queryChainId`、`previousRequestId`。
- 按 `tengu_api_*`、tool、attachment、cache 事件拆分 metadata 模板。

### Phase C：响应 usage / cache / token 摘要

- 从上游响应 usage 和流式 side tap 补齐 token/cache/ttft/duration 字段。
- 不记录正文，只记录数值摘要。

### Phase D：真实抓包差异验证

- 增加脱敏 diff 工具，对比字段密度、事件名分布、metadata key 分布和 env shape。
- 远程灰度抓包验证。

## 验收标准

- [ ] 有脱敏 telemetry event catalog，覆盖 2.1.195 抓包主要事件名和 metadata key。
- [ ] 每个字段标注来源和敏感等级。
- [ ] 实现至少一阶段安全字段补齐，并有单测覆盖。
- [ ] auto telemetry 开启时字段密度和事件差异比当前更接近真实抓包。
- [ ] 不新增敏感正文、token、Cookie、邮箱、完整账号 UUID 泄露。
- [ ] 有远程灰度抓包验收步骤和回滚策略。
