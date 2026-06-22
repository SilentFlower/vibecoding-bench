# fix: cc2api telemetry 2.1.185 alignment

## Goal

在 `auto_telemetry` 默认开启的使用场景下，将 `cc2api` 主动代发的 Claude Code 遥测请求对齐 2.1.185 抓包结构，降低“像官方但字段形态不一致”的账号画像特征。范围聚焦 `/api/event_logging/v2/batch` 与 `/api/eval/sdk-zAZezfDKGoZuXXKe` 的 payload 和必要 header/profile，不改变普通 `/v1/messages` 主请求逻辑。

## Background / Known Context

- 用户说明当前部署默认开启 `auto_telemetry`，因此主动遥测不再是低优先级可忽略项。
- 参考抓包目录：`data/flows/6-5/3930/dac88465b061/`，Claude Code 版本为 `2.1.185`。
- 抓包统计：
  - `/api/event_logging/v2/batch` 共 52 次，内部事件的 `event_data.betas` 非空，`additional_metadata` 为 base64 JSON，`event_data` 未出现 `email`。
  - `/api/eval/sdk-zAZezfDKGoZuXXKe` body 顶层包含 `attributes`、`forcedVariations`、`forcedFeatures`、`url`；`forcedFeatures` 是数组；`attributes` 未出现 `email`。
  - event env 字段包含 `shell`、`is_running_with_bun`、`version`、`version_base`、`build_time`、Linux distro/kernel 等 2.1.185 画像字段。
- 当前 `cc2api/src/service/telemetry.rs` 主动构造 event logging 和 GrowthBook eval；其中 event logging 会写 `email`、`betas=""`、`additional_metadata=""`，GrowthBook eval 会写 `email`，且 payload 顶层结构与抓包不完全一致。

## Requirements

- `/api/event_logging/v2/batch`：
  - 不主动发送抓包中没有的 `email` 字段。
  - `ClaudeCodeInternalEvent.event_data.betas` 必须按最终 `/v1/messages` beta profile 或 2.1.185 默认 profile 填充，不允许长期空字符串。
  - `ClaudeCodeInternalEvent.event_data.additional_metadata` 必须是 base64 编码 JSON，至少包含 2.1.185 抓包中稳定、可安全派生的字段，例如 `renderer_mode`、`subscription_type`，并允许事件字段补充 `model`、`provider`、`attempt` 等安全摘要。
  - `env` 字段集必须覆盖 2.1.185 抓包中的核心字段，至少包括 `shell` 与正确来源的 `is_running_with_bun`。
  - 不发送 prompt 原文、tool input、响应正文、token、cookie 或完整抓包数据。
- `/api/eval/sdk-zAZezfDKGoZuXXKe`：
  - 顶层结构必须对齐抓包：`attributes`、`forcedVariations: {}`、`forcedFeatures: []`、`url: ""`。
  - `attributes` 不主动发送 `email`。
  - `attributes` 保留 2.1.185 抓包中存在且可从账号画像安全生成的字段：`id`、`sessionId`、`deviceID`、`platform`、`organizationUUID`、`accountUUID`、`userType`、`subscriptionType`、`rateLimitTier`、`appVersion`、`entrypoint`。
  - 若 `firstTokenTime` 无真实来源，需明确采用保守策略：不写入或按现有账号画像可解释地生成，不得伪造无法维护的一次性真实值。
- Header/profile：
  - 保持 event logging 使用 `User-Agent: claude-code/2.1.185`、`anthropic-beta: oauth-2025-04-20`、`x-service-name: claude-code`。
  - 保持 GrowthBook eval 使用抓包对应 `Bun/1.4.0` UA 和 eval header 顺序。
- 测试需使用最小脱敏样本或构造数据，不提交完整 `http_capture.jsonl`。

## Acceptance Criteria

- [ ] event logging 单测断言内部事件不包含 `email`。
- [ ] event logging 单测断言内部事件 `betas` 非空，`additional_metadata` 可 base64 解码为 JSON。
- [ ] event logging 单测断言 `env` 包含 `shell`、`is_running_with_bun`、`version`、`version_base`、`build_time`。
- [ ] GrowthBook eval 单测断言顶层 keys 包含 `attributes`、`forcedVariations`、`forcedFeatures`、`url`，且 `forcedFeatures` 为数组。
- [ ] GrowthBook eval 单测断言 `attributes` 不包含 `email`，并包含 2.1.185 抓包中的核心账号画像字段。
- [ ] `cd cc2api && cargo fmt --check && cargo test` 通过。

## Out of Scope

- 不改变 `/v1/messages` 主请求的 `metadata.user_id` 修复；该工作由任务 `06-22-cc2api-metadata-user-id-account-alignment` 覆盖。
- 不新增前端设置项，不改变 DB schema。
- 不逆向或修改 CCH / `cc_version` 算法。
- 不处理带 `cache_control` 的 system block 清洗策略。

## Research References

- `data/flows/6-5/3930/dac88465b061/http_capture.jsonl`（仅本地参考，不提交完整内容）
- `.trellis/spec/cc2api/backend/service-architecture.md`
- `.trellis/spec/cc2api/backend/testing-quality.md`
- `.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md`
