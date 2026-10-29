# 当前实现与参考实现证据

## cc2api

- `web/src/components/Accounts.vue:988`：四组额度进度条；`effectiveUtil():454` 当前会把缺失和到期窗口显示为 0，新增展示需要区分未知、待更新与实际零占用，不能改变调度器的窗口逻辑。
- `web/src/api.ts:118`：`UsageWindow { utilization, resets_at? }`；额度是账号 `usage_data`，没有费用字段。
- `src/handler/router.rs:299`：分页账号列表已经给 `Account` 的序列化结果附加运行指标，适合附加独立、可选的本地统计，不把费用写回上游额度缓存。
- `src/handler/router.rs:1042`：手动刷新仅调用 `AccountService::refresh_usage`，保持此行为；费用跟随下一次现有列表轮询更新。
- `src/service/gateway.rs:2083`：自动遥测上下文依赖 `auto_telemetry`；本地用量采集必须独立于该开关。
- `src/service/gateway.rs:2312`：非流探针缓存的首次上游请求单独缓冲返回；真实调用需要记录，后续本地缓存命中不重复计算上游消费。
- `src/service/gateway.rs:6498`、`:6636`、`:6660`：`SlotGuardBody` 已解析完整 Token 摘要并在结束／错误时发遥测；需补独立的一次性落库上下文，并审查 Drop 提前断开路径。
- `src/service/gateway.rs:6860`：已有压缩响应限长旁路副本和解码工具，保持原始响应帧直接转发；费用解析应复用该能力，并对截断标记不完整。
- `src/service/gateway.rs:7007`：`merge_message_telemetry_from_value` 支持普通、`message/usage`、`delta/usage`；累计 usage 合并采用 max，不能把多个事件直接相加。
- `src/service/telemetry.rs:178`：`MessageTelemetryUsage` 的六个 Token 字段可复用，不虚构新的上游 usage 名称。
- `src/store/db.rs:29`、`:50`：SQLx AnyPool，SQLite／PostgreSQL 双栈；新增统计表和索引需要幂等，不能仅更新一种数据库。
- `src/store/prime_log_store.rs:23`：已有独立 store 的注入与日志裁剪模式，可参考；费用记录不采用仅保留 200 条的裁剪方式，否则高流量会破坏周窗口。

## sub2api

- `frontend/src/components/account/UsageProgressBar.vue:4`：请求数、Token、A 费用、U 费用位于进度条上方。
- `frontend/src/components/account/AccountUsageCell.vue:129`：截图对应 OpenAI 分支，5h／7d 都有 `window_stats`；`:829` 的周总额计算为 `cost * 100 / utilization`，仅接受有限正数。
- `backend/internal/service/account_usage_service.go:134`：A 是 `total_cost * account_rate_multiplier`，U 是用户实际费用；cc2api 没有对应两套倍率／结算契约，因此只展示标准 API 折算费用。
- `backend/internal/service/account_usage_service.go:768`、`:1558`：OpenAI 两个窗口分开汇总；有效 reset 减窗口长度作为起点，否则使用最近窗口。
- `backend/internal/service/account_usage_service.go:1359`：Claude 原分支只为 FiveHour 附加窗口统计，不能原样搬过来后声称已支持 Claude 7d。
- `backend/resources/model-pricing/model_prices_and_context_window.json`：本地 Claude 价格目录，包含输入、输出、缓存写／读、1h 缓存写，以及部分 priority 价格和长上下文阶梯字段；实现时只提取所需 Claude 项并保留来源版本。
- `backend/internal/service/billing_service.go:365`：无目录时的 Claude 回退价格，包含 Fable 5／5.1、Opus／Sonnet／Haiku 5.5 及长上下文规则。`:1036` 的宽泛未知 Claude→Sonnet 回退不能照搬为可靠统计，应显示未定价。

## 本轮约束

参考仓库只读。实现仅修改 cc2api 子仓及父仓中的当前任务／必要规范；不新增 CLI 消费采集，不增加上游查询，不改 v3 被动额度既有任务内容。价格以该本机源码快照为准，不声称来自已查询的线上实时价格。

参考版本：`9e070a1ff`。价格目录 SHA256：`e15664964561bf34513c9a357e301fa3f03819565e1efbd3ea3c2b7d55671dc9`；`billing_service.go` SHA256：`580e218ff8c4da0eb10d243d9f12d75165d4845e7d01dc7b682a59ad24401f96`。
