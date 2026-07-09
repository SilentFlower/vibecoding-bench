# Brief — cc2api Fable 配额耗尽时粘性会话智能切换

## Goal

- 当粘性会话绑定账号的 Fable 周用量明确耗尽时，cc2api 能自动避开该账号并切换到仍有 Fable 配额的账号，同时保留 RPM 饱和时的既有 sticky 保护语义。

## Scope

- 在账号选择阶段加入 Fable 请求上下文，识别 `claude-fable-5` / `claude-fable-5[...]`。
- 使用 `usage_data.seven_day_fable.utilization >= 100` 且 `resets_at` 在未来作为“明确耗尽”条件；不使用 `97%` 或其他接近满过滤线。
- Fable sticky 账号明确耗尽时，本轮临时忽略该账号并尝试选择替代账号；只有替代账号实际承载请求后才覆盖 session 绑定。
- 非粘性 Fable 请求优先过滤明确耗尽账号；所有候选都满时返回 429 或最后一个 429，不能无限重试。
- Fable 429 后不在 Gateway 热路径同步查询 OAuth usage；只触发已有节流保护下的后台 usage refresh。
- 新增全局 setting `fable_sticky_quota_fallback_enabled`，默认开启，支持管理端保存和 Gateway 热刷新。
- Settings 页面在“评分权重”卡片内新增“Fable 配额切换”开关。

## Non-Goals

- 不改变 Fable 请求画像、CCH、beta、fallbacks 或 `claude-fable-5[1m]` 归一规则。
- 不把 Fable 模型级耗尽写入账号全局 `rate_limit_reset_at`。
- 不新增账号字段或新 DB 表。
- 不改变 token allowed/blocked account 规则。
- 不把 RPM 饱和作为打破 sticky 的理由。

## Key Context

- 现有 sticky 入口：`cc2api/src/service/account.rs::select_account_with_context`，当前 sticky 命中只检查账号可调度、token block/allow 和 allowed 列表。
- Gateway 主循环：`cc2api/src/service/gateway.rs::handle_request_inner` 会在 429 后排除当前账号并重试。
- 429 分类：`cc2api/src/service/account.rs::handle_rate_limit` / `determine_rate_limit_window` 当前只处理通用 `seven_day` / `five_hour`，且 `credit` 文案会走单请求级逻辑。
- Fable 周用量稳定字段来自 OAuth usage scoped 窗口：`usage_data.seven_day_fable`；普通 `anthropic-ratelimit-unified-*` 头不能可靠推导 Fable 周用量。
- settings 新 key 必须同步 `settings_store.rs`、`db.rs`、`router.rs`、`gateway.rs`、`main.rs` 和 `Settings.vue`。
- 回滚方式：把 `fable_sticky_quota_fallback_enabled` 设置为 `false`，热刷新后恢复旧行为。

## Acceptance

- 两个 OAuth 账号中，账号 A 的 `seven_day_fable >= 100` 且 reset 在未来，session 已粘到 A；新的 Fable `/v1/messages` 请求应避开 A 并选择账号 B。
- 替代账号实际承载请求后，session 绑定更新为账号 B；下一次同 session Fable 请求不再命中账号 A。
- 如果账号 A 已满但没有可用替代账号，本轮返回 429，但旧 session 绑定仍保留。
- 非 Fable 请求不受 `seven_day_fable` 满影响。
- 全局开关关闭时，即使 sticky 账号 `seven_day_fable >= 100`，仍保持旧逻辑命中该账号。
- Fable 429 且本地 usage 尚未满时，不阻塞等待 OAuth usage；继续按 429 排除当前账号重试，并触发后台 usage refresh。
- sticky RPM 饱和仍保持现有等待/本地 429 行为，不切号。
- Settings 页面开关位于“评分权重”卡片内“Fable 配额切换”小节；开启显示“已启用”，关闭显示“保持粘性”。
- `cd cc2api && cargo fmt --check && cargo test` 通过；`cd cc2api/web && npm run build` 通过。

## Next Step

- 用户确认 planning artifacts 和本 brief 后，运行 `task.py start` 进入 `in_progress`，下一步必须先走 `trellis-route(implement)`，不能直接编辑代码。
