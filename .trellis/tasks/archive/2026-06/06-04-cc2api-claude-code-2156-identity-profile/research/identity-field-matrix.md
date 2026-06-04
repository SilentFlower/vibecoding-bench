# cc2api 身份画像字段矩阵

## 目标

把 cc2api 的身份字段按来源分层，避免 `canonical_env`、system prompt、telemetry、GrowthBook 和 `/v1/messages` metadata 各自随机生成，导致整体不像同一台机器。

## 分层原则

| 层级 | 生命周期 | 典型字段 | 存储/派生策略 |
|------|----------|----------|----------------|
| 设备画像 | 账号级长期稳定 | `device_id`、platform、arch、node version、terminal、package managers、Claude Code version/build time、account/org UUID | 存储在账号字段和 `canonical_env` / `canonical_prompt_env` / `canonical_process` |
| 运行画像 | 一次 Claude Code run 内稳定 | run id、cwd、shell、started_at、process seed、telemetry session id、GrowthBook session id | 由账号稳定字段 + 当前会话开始时间派生，不新增 DB |
| 请求画像 | 单次请求 | `X-Claude-Code-Session-Id`、`x-client-request-id`、`metadata.user_id.session_id`、event id | 每次请求派生，但要与当前 run/session 对齐 |

## 字段矩阵

| 字段 | 层级 | 主要出现位置 | 当前来源 | 目标来源 |
|------|------|--------------|----------|----------|
| `device_id` | 设备 | `/v1/messages metadata.user_id`、telemetry `device_id`、GrowthBook `id/deviceID` | `Account.device_id` | 保持账号级稳定 |
| `account_uuid` | 设备 | telemetry `auth/account_uuid`、GrowthBook `accountUUID`、metadata user id | `Account.account_uuid` 或 email hash | 统一 helper 派生 fallback，避免 rewriter/telemetry 重复实现 |
| `organization_uuid` | 设备 | headers `x-organization-uuid`、telemetry、GrowthBook | `Account.organization_uuid` | 保持账号级稳定，缺失时删除相关字段 |
| `subscription_type` | 设备 | GrowthBook `subscriptionType`、rate tier、metrics resource | `Account.subscription_type` | 保持账号级稳定 |
| `platform` | 设备 | `canonical_env`、system prompt、GrowthBook、telemetry env、Stainless OS | 随机 preset | profile 内一致：linux/darwin/win32 对应 prompt、cwd、OS、Stainless OS |
| `arch` | 设备 | `canonical_env`、Stainless arch、metrics host arch | 随机 preset | 与平台 profile 一致 |
| `node_version` | 设备 | telemetry env、runtime version 相关字段 | 随机 preset | 与 Claude Code profile 和 runtime 指纹一致 |
| `terminal` | 设备 | telemetry env | 随机 preset | 与 shell/cwd 风格一致 |
| `package_managers` | 设备 | telemetry env | 随机 preset | 与平台 profile 一致 |
| `version` / `version_base` / `build_time` | 设备 | headers UA、telemetry env、GrowthBook appVersion | `version_profile` | 继续集中从 `version_profile` 读取 |
| `shell` | 运行 | system prompt | platform map | 与 terminal/platform profile 一致 |
| `os_version` | 运行 | system prompt | platform map | 与 platform、linux distro/kernel 一致 |
| `working_dir` | 运行 | system prompt、home path rewrite | platform map | 与 platform/profile home path 一致 |
| `process.uptime` | 运行 | telemetry process | telemetry 当前 session uptime | 保持单调递增 |
| `rss` / `heap*` / `external` / `arrayBuffers` | 运行 | telemetry process、rewriter telemetry 改写 | 每次随机范围 | 由 process seed + uptime 生成平滑曲线 |
| `cpuUsage` / `cpuPercent` | 运行 | telemetry process | 每次随机 | 由 uptime 和账号 seed 派生，随时间变化 |
| `metadata.user_id.session_id` | 请求/运行 | `/v1/messages metadata.user_id` | 每次请求 UUID | API 注入时生成一次，并用于 `X-Claude-Code-Session-Id` |
| `X-Claude-Code-Session-Id` | 请求/运行 | `/v1/messages` header | 从 `_session_id` 或随机 UUID | 与 metadata session id 对齐 |
| `x-client-request-id` | 请求 | `/v1/messages` header | 每次随机 UUID | 保持每次请求唯一 |
| GrowthBook `sessionId` | 运行 | `/api/eval/*` body | 每次 eval 随机 UUID | 后续 telemetry 任务可与 run profile 对齐；本任务先集中 helper |

## 当前重复点

- `derive_account_uuid` 在 `rewriter.rs` 和 `telemetry.rs` 各有一份。
- `parse_env` / `parse_process` 在 `rewriter.rs` 和 `telemetry.rs` 各自解析。
- process 内存字段在 `rewriter.rs` 和 `telemetry.rs` 都是范围随机。
- session UUID 在 `rewriter.rs` 单独实现，telemetry/GrowthBook 使用 `uuid::Uuid::new_v4()`。

## 本任务落地边界

- 不改 DB schema。
- 不静默覆盖旧账号手工配置。
- 新增统一 helper，先收敛解析、fallback、account UUID、session UUID 和 process 曲线。
- 新账号 preset 做平台内一致性增强。
- telemetry 事件类型完整度留给 `telemetry-profile` 任务。
