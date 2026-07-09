# cc2api Fable 配额耗尽时粘性会话智能切换 - 设计

## 范围

本任务修改 `cc2api` 的账号调度、Gateway 429 处理、全局 settings 和 Settings 管理页面：

- 后端调度：`cc2api/src/service/account.rs`
- Gateway 热路径与配置缓存：`cc2api/src/service/gateway.rs`
- Settings 默认值、DB 默认插入、管理 API 校验与热刷新：`cc2api/src/store/settings_store.rs`、`cc2api/src/store/db.rs`、`cc2api/src/handler/router.rs`、`cc2api/src/main.rs`
- 前端 Settings：`cc2api/web/src/components/Settings.vue`，必要时同步 `cc2api/web/src/api.ts`

不修改 Fable 请求画像、CCH、beta、fallbacks、token allow/block 语义或账号全局 `rate_limit_reset_at` 字段语义。

## 核心语义

- sticky 是软绑定：用于保护同一会话的 prompt cache，但不能让已明确耗尽 Fable 周配额的账号继续承载 Fable 请求。
- Fable 模型级耗尽只影响 Fable `/v1/messages` 请求；同账号的非 Fable 请求仍可调度。
- 明确耗尽定义：`usage_data.seven_day_fable.utilization >= 100` 且 `resets_at` 可解析并在未来。
- 不使用 `97%` 或其他“接近满”硬过滤线。
- RPM 饱和仍保持既有 sticky 语义：粘性账号 RPM 饱和时等待或本地 429，不因为本任务切号。

## 全局开关

新增 setting key：

```text
fable_sticky_quota_fallback_enabled
```

默认值：`true`。

关闭后必须保留旧行为：

- 粘性会话命中账号时，不检查 `seven_day_fable`。
- 非粘性候选账号不按 `seven_day_fable` 预过滤。
- Fable 429 不走模型级 sticky fallback 附加逻辑。
- Settings 页面仍显示开关状态。

同步位置：

- `settings_store.rs`：新增 `DEFAULT_FABLE_STICKY_QUOTA_FALLBACK_ENABLED`。
- `db.rs`：默认插入 key/value，老库通过 insert-if-missing 获得默认值。
- `router.rs`：
  - `get_settings` 回填默认值。
  - `update_settings` 校验只允许 `"true"` / `"false"`。
  - 写入该 key 后调用 Gateway reload。
- `gateway.rs`：
  - 新增 `RwLock<bool>` 缓存和 `reload_fable_sticky_quota_fallback_enabled()`。
  - `GatewayService::new` 使用默认值初始化。
- `main.rs`：启动时调用 reload。
- `Settings.vue`：
  - ref 默认 `true`。
  - `loadSettings()` 读取 key。
  - `saveSettings()` 提交 key。
  - 在“评分权重”卡片内新增“Fable 配额切换”小节。

## 账号选择

### 请求上下文

在账号选择链路加入请求模型上下文，避免非 Fable 请求受影响。推荐新增轻量结构：

```rust
pub struct AccountSelectionContext {
    pub fable_quota_fallback_enabled: bool,
    pub request_model: Option<String>,
}
```

可保留现有 `select_account` / `select_account_with_context` 作为旧调用入口，内部用默认上下文代理；Gateway 主 `/v1/messages` 路径使用带上下文的新入口。

Fable 判断应覆盖：

- `claude-fable-5`
- `claude-fable-5[1m]`

只在 `/v1/messages` 真实上游路径使用该判断；`count_tokens`、bootstrap、telemetry、本地拦截路径不启用该 fallback。

### sticky 命中

当 session 已绑定账号 A：

1. 如果功能关闭：沿用旧逻辑，账号 A 可调度则直接返回 sticky。
2. 如果不是 Fable 请求：沿用旧逻辑。
3. 如果账号 A 的 `seven_day_fable` 未明确耗尽：沿用旧逻辑。
4. 如果账号 A 的 `seven_day_fable` 已明确耗尽：
   - 本轮临时忽略 A，把 A 加入本次选择的运行时排除集合。
   - 不立即删除 session 绑定。
   - 继续按 allowed/block 规则和候选账号选择其他账号。
   - 如果选中账号 B 并真正进入上游路径，Gateway 既有 `bind_selected_session` 会覆盖 session 绑定到 B。
   - 如果没有替代账号，返回 429 或最后一个 429，但保留旧 session 绑定。

### 非粘性候选

Fable 请求且功能开启时：

- 对候选账号先排除 `seven_day_fable` 明确耗尽的账号。
- 如果排除后仍有候选，进入现有 RPM 可用过滤和评分选择。
- 如果全部候选都已满，返回本地 429 或保留最后一个 429；不能无限重试。

评分权重暂不加入 `seven_day_fable`，因为用户明确要求不使用接近满过滤线；未满账号按现有 `seven_day` / `five_hour` / 并发负载评分。

## 429 处理

`GatewayService::forward_request` 已经在 429 后缓冲错误体并调用 `AccountService::handle_rate_limit`。本任务不在 429 热路径同步调用 OAuth usage API。

推荐调整：

- `handle_rate_limit` 或其内部判断接受请求模型上下文，先识别 Fable 模型级耗尽，再处理 `credit` 文案的单请求级透传。
- 当 Fable 请求且账号缓存中 `seven_day_fable >= 100` 时，返回模型级耗尽决策；不得把该状态写成账号全局 `rate_limit_reset_at`。
- 当本地 usage 尚未满但上游返回 Fable 429 时：
  - 本轮仍按 429 排除当前账号并重试其他账号。
  - 触发已有节流保护下的后台 usage refresh。
  - 不阻塞等待 usage API 结果。
- 通用 `five_hour` / `seven_day` 撞墙仍按现有账号级冷却处理。
- `retry-after` 的全局速率限制语义保持现状。

## Settings 页面

位置：现有“评分权重”卡片内，权重输入和总和提示之后新增分隔小节。

文案：

- 小节标题：`Fable 配额切换`
- 开关显示：
  - 开启：`已启用`
  - 关闭：`保持粘性`
- 说明：`Fable 周用量明确耗尽时，允许打破粘性会话并切换到其他可用账号；RPM 饱和仍保持粘性等待。`

前端不新增临时别名，直接读写 `fable_sticky_quota_fallback_enabled`。

## 数据兼容

- 不新增 DB 表或账号字段。
- settings 表通过默认插入补齐老库 key。
- `usage_data` 缺失、非对象、`seven_day_fable` 缺字段、`utilization` 非数字、`resets_at` 缺失或过期时，都视为“未明确耗尽”，不得打破 sticky。
- reset 时间到达后自动恢复：`resets_at <= now` 时不再视为耗尽。

## 风险与回滚

- 风险：错误识别 Fable 模型会让非 Fable 请求误切号。防护：只匹配 `claude-fable-5` 和 `claude-fable-5[...]`，并只在 `/v1/messages` 上启用。
- 风险：没有替代账号时删除 sticky 会丢失 reset 后恢复路径。防护：仅当替代账号实际承载请求后覆盖绑定。
- 风险：同步 usage 查询拖慢热路径。防护：429 后只后台刷新，不等待外部 API。
- 回滚：将 `fable_sticky_quota_fallback_enabled` 设置为 `false`，热刷新后恢复旧行为。

## 验证

- 后端单测覆盖：
  - Fable sticky 账号 `seven_day_fable >= 100` 时选择替代账号。
  - 无替代账号时保留旧 sticky 绑定并返回 429/错误。
  - 非 Fable 请求不受 `seven_day_fable` 影响。
  - 功能关闭时保持旧 sticky。
  - `credit` 文案 + Fable 已满不被当作单请求级直接透传。
  - sticky RPM 饱和不切号。
- 前端构建：`cd cc2api/web && npm run build`。
- 后端验证：`cd cc2api && cargo fmt --check && cargo test`。
