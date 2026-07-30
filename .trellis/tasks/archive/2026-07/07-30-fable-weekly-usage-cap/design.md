# cc2api Fable 周用量全局上限 - 技术设计

## 范围

本任务扩展既有 Fable sticky 配额 fallback，不新增数据库表或账号字段：

- settings 默认值与迁移：`cc2api/src/store/settings_store.rs`、`cc2api/src/store/db.rs`
- settings 管理 API 与热刷新：`cc2api/src/handler/router.rs`、`cc2api/src/main.rs`
- Gateway 配置缓存与请求上下文：`cc2api/src/service/gateway.rs`
- 账号选择和 Fable 窗口判断：`cc2api/src/service/account.rs`
- 管理页配置：`cc2api/web/src/components/Settings.vue`
- 调度与默认值回归：`cc2api/tests/account_scheduler_test.rs` 及相关模块单测

`web/src/api.ts` 现有 `SettingsMap = Record<string, string>` 已能承载新 key，除非实现阶段发现类型同步需要，否则不修改。

## Setting 契约

新增 key：

```text
fable_weekly_usage_limit_percent=50
```

- `settings_store.rs` 新增公开默认常量 `DEFAULT_FABLE_WEEKLY_USAGE_LIMIT_PERCENT: &str = "50"`，使用中文 doc comment。
- `db.rs` 在 settings 默认插入列表中补齐新 key，SQLite/PostgreSQL 共用同一 insert-if-missing 路径；已有库升级后自动获得默认值。
- `router.rs::get_settings` 在 key 缺失时回填默认值。
- `router.rs::update_settings` 使用整数范围校验，只接受 `1～100`；`0`、负数、小数、非数字和大于 `100` 均返回 `AppError::BadRequest`。
- 现有 `fable_sticky_quota_fallback_enabled` 保留为总开关，不迁移、不重命名。

## Gateway 热缓存

- `GatewayService` 新增 `RwLock<u32>` 字段缓存百分比，初始值由默认常量解析。
- 新增公开 reload 方法，从 settings 读取并解析 `fable_weekly_usage_limit_percent`；非法存量值回退默认 `50`，热路径不得 panic。
- `main.rs` 启动时在现有 Fable 开关 reload 附近加载百分比。
- `update_settings` 写入新 key 后调用对应 reload，使保存立即生效。
- `/v1/messages` 构造 `AccountSelectionContext` 时，同时传入总开关、请求模型和百分比；其他入口继续使用 `AccountSelectionContext::disabled()`。

## 账号选择上下文

在现有结构上增加阈值字段：

```rust
pub struct AccountSelectionContext {
    pub fable_quota_fallback_enabled: bool,
    pub fable_weekly_usage_limit_percent: u32,
    pub request_model: Option<String>,
}
```

- `disabled()` 提供关闭状态和合法默认百分比，保持旧调用入口兼容。
- `is_fable_quota_fallback_active()` 仍只判断开关与模型族；阈值由调用账号可用性判断时读取。
- 所有新增或修改的 public API、字段和方法保持中文 Rust doc comment，并补齐 `@param` / `@return`。

## Fable 上限判断

将固定 `100%` 的账号判断泛化为“达到配置上限”：

- 仅 `AccountAuthType::Oauth` 参与判断。
- 读取 `usage_data.seven_day_fable.utilization`，以 `f64` 与 `u32` 阈值转换值比较，语义为 `utilization >= limit_percent`。
- `resets_at` 必须是可解析且晚于当前时间的 RFC3339 时间。
- usage 缺失、字段类型错误、reset 缺失或过期时返回未达到上限。
- 不复用通用 `USAGE_HIT_THRESHOLD = 97.0`，也不修改普通 `five_hour` / `seven_day` 撞墙判断。
- 429 分类如需返回 Fable reset 信息，使用同一请求上下文阈值；通用窗口、`retry-after` 和 `RetryOtherAccount` 既有优先级不变。

## 调度行为

### Sticky 请求

1. 总开关关闭、模型非 Fable、账号非 OAuth或合法窗口低于阈值时，直接沿用原 sticky。
2. sticky 账号达到阈值时，仅加入本轮 `runtime_exclude_ids`，刷新并保留原 sticky TTL。
3. 继续按 API Token allow/block、账号可调度状态和现有评分选择替代账号。
4. 替代账号真实承载上游请求后，复用现有 `should_bind_session` / `bind_selected_session` 覆盖 sticky。
5. 无替代账号时返回 `AppError::TooManyRequests`，错误文案使用“达到 Fable 周用量上限”，不得描述为“额度耗尽”。

### 非 Sticky 请求

- 开关开启且请求模型为 Fable 时，先过滤达到配置上限的 OAuth 账号。
- 过滤后存在候选时，继续执行现有 RPM 可用过滤与 `select_by_score`，不按 Fable 用量重新排序。
- 所有候选均达到上限时返回 `AppError::TooManyRequests`。

### 观测延迟

- 请求入场只依据账号当前缓存的最新 usage。
- 请求开始时低于阈值则允许执行，即使响应后的新 usage 略高于阈值。
- 被动或主动采集写回后，后续请求按新值过滤；不估算当前请求成本。

## Settings 页面

在现有“Fable 配额切换”小节内增加数字输入：

- 字段绑定 `fableWeeklyUsageLimitPercent`，默认字符串 `"50"`。
- `<Input type="number" min="1" max="100" step="1">`，旁边明确显示百分比语义。
- 前端保存前校验整数 `1～100`，不合法时使用现有 toast 中止保存；后端校验仍是最终边界。
- 总开关关闭时保留已填写百分比，但说明限制不生效；重新开启后继续使用该值。
- 说明文案明确“达到最近观测的周用量上限后切换账号，单次请求可能轻微越线”，不宣称精确阻止每个 token。

## 兼容与回滚

- 新 key 缺失时默认 `50`，因此升级后现有开启总开关的部署会从 100% 提前切换为 50%；这是本任务确认的产品行为。
- 把百分比设置为 `100` 可恢复此前“明确耗尽才切换”的阈值语义。
- 关闭 `fable_sticky_quota_fallback_enabled` 可完全停用 Fable 周用量过滤并热生效。
- 不修改 usage JSON 结构、账号 DTO、token allow/block、RPM 或账号全局 `rate_limit_reset_at` 语义。

## 验证矩阵

| 条件 | 期望行为 |
|------|----------|
| 开关开启，OAuth sticky usage 为 50%，阈值 50 | 本轮跳过 sticky，尝试替代账号 |
| 开关开启，OAuth sticky usage 为 49%，阈值 50 | 保持原 sticky |
| 开关关闭，OAuth sticky usage 为 100% | 不按 Fable 周用量切换 |
| 非 sticky 候选分别为 50% 和 49% | 过滤 50% 账号，49% 账号进入既有评分 |
| 所有允许候选均达到阈值 | 返回 429 |
| 非 Fable 请求或 SetupToken 账号 | 忽略 Fable 周用量上限 |
| reset 已过期或字段不完整 | 视为未达到上限 |
| 阈值为 100，usage 为 99% / 100% | 99% 允许，100% 过滤 |
| 设置值为 0、101、50.5 或文本 | 管理 API 返回 BadRequest，旧配置不变 |

## 风险

- 默认 50% 会改变升级后行为：通过 Settings 页面展示当前值，并保留总开关和 100% 回滚路径。
- usage 观测存在延迟：文案和测试只承诺“达到已观测阈值后阻止后续请求”。
- 上下文字段变更影响所有结构体字面量：实现时全量搜索 `AccountSelectionContext {` 并同步测试。
- 错误文案仍写“耗尽”会误导管理员：统一改为“达到周用量上限”。

## 验证命令

```bash
cd cc2api
cargo fmt --check
cargo test
cd web
npm run build
git -C .. diff --check
```
