# cc2api Settings & Database

## 数据库栈

`cc2api` 同时支持 SQLite 和 PostgreSQL：

- 初始化入口：`src/store/db.rs::init_db`
- schema/migration 入口：`src/store/db.rs::migrate`
- 运行时连接：`sqlx::AnyPool`

所有 SQL 变更都必须考虑 SQLite 与 PostgreSQL 两套 schema。不要只改其中一套。

## 迁移规则

- `ALTER TABLE ... ADD COLUMN` 目前采用幂等失败吞掉的方式支持旧库升级；新增列要确认重复执行安全。
- settings 默认值通过 `settings` 表插入 key/value；新增 setting 必须有默认值、老值迁移策略和非法值兜底。
- `claude_code_profile_selection_mode` 缺失时幂等插入 `client_version`，SQLite 使用 `INSERT OR IGNORE`、PostgreSQL 使用 `ON CONFLICT (key) DO NOTHING`；不得覆盖显式模式值。仅补齐选择模式不批量修改账号 env。
- 版本画像相关迁移必须更新已有账号的 `canonical_env.version/version_base/build_time/node_version`，不能只改新账号默认值。
- 多个 setting 共同表达一个默认画像时，旧默认组合必须成对迁移。293 升级只在 `claude_code_profile_selection_mode=client_version` 且 profile/允许范围精确匹配 `PREVIOUS_DEFAULT_CLAUDE_CODE_PROFILE_SETTINGS` 中旧出厂组合时升级为默认 293 与 `2.1.89-2.1.293`；账号模式即使使用旧出厂 260/280 组合也保留，管理员自定义任一值同样保留。
- `upgrade_default_profile_setting` 在同一事务内迁移组合配置并按最终存储画像同步账号四项软件字段，SQLite 使用 `json_set`、PostgreSQL 使用 `jsonb_set`；保持幂等，保留设备身份、凭据、容量和未知环境字段。不得新增针对 260 的强制升级。
- 迁移不得改写禁止版本和其它 UA；出厂禁止列表仍为空。「仅允许 280、293」是管理员明确保存的设置页预设，不是启动时自动覆盖的安全策略。
- 删除或废弃 setting key 时，加入 `OBSOLETE_SETTINGS_KEYS`，并确认 UI 不再提交旧 key。

## Settings Key 契约

新增 setting 必须同步：

1. `src/store/settings_store.rs` 的 `DEFAULT_*` 常量。
2. `src/store/db.rs` 的默认插入或迁移。
3. `src/handler/router.rs` 的校验、解析、`update_settings` reload。
4. `src/service/gateway.rs` 或对应 service 的内存缓存字段。
5. `web/src/components/Settings.vue` 的控件。
6. README 或部署文档中需要用户配置的说明。

Setting value 应以字符串存储，进入 service 前解析成 enum/bool/number。非法值必须返回 `AppError::BadRequest` 或回退到明确默认值，不要让热路径 panic。

`claude_code_profile_selection_mode` 仅接受精确字符串 `client_version` / `account`，PUT 在任何写入前校验，GET 补齐默认 `client_version`。非法存量 mode/default 分别回退 `client_version` / `2.1.293`。仅切 mode 不写账号 env。

`SettingsStore::upsert_many_with_profile(&HashMap<String, String>, Option<&'static ClaudeCodeProfile>)` 把本次全部 settings 与主动选择画像时的账号四项软件字段放入同一事务，任一写入失败整体回滚。客户端模式保存显式提交的允许范围，profile-only payload 保留存量范围；账号模式使用目标画像范围。未提交的禁止版本、UA 和其它配置保持原值。`apply_claude_code_profile` 是显式携带画像范围的旧便捷接口，不能替代管理 API 的独立准入保存。

保存 mode/profile/允许范围/禁止版本/其它 UA 后调用 `GatewayService::reload_access_profile_config`。准入与选择必须从同一次 `get_all` 构成同一个 `AccessProfileConfig`，在一把 `RwLock` 中原子替换；写锁覆盖读取和替换，解析失败保持旧快照，请求在同一读锁内先准入、后冻结画像。完整契约见 [按客户端 UA 选择请求画像](../protocol/claude-code-profile-upgrade.md#scenario-按客户端-ua-选择请求画像) 与 [293 画像和准入预设](../protocol/claude-code-profile-upgrade.md#scenario-claude-code-21293-画像与-280293-准入预设)。

## Account 字段同步

账号字段跨越多层：

```text
src/model/account.rs
src/store/account_store.rs
src/service/account.rs
src/handler/router.rs
web/src/api.ts
web/src/components/Accounts.vue
```

新增账号字段时必须同步读写、分页列表、更新接口、前端类型和 UI。涉及 token、邮箱、OAuth、usage 的字段必须默认脱敏展示。

## 时间字段

- 后端持久化时间优先使用 RFC3339 字符串。
- 前端展示前只做格式化，不反推出业务窗口。
- usage window、RPM window、telemetry session 过期时间不能混用。

## Scenario: 创建账号的提交可见性

### 1. Scope / Trigger

- 修改账号创建、SQLite 连接模式或首次同步后的凭据解析时适用。创建成功必须表示其它连接已可读取，不能依赖下一次创建或同池查询才完成提交。

### 2. Signatures

```rust
pub async fn create(&self, a: &mut Account) -> Result<(), AppError>
```

- `INSERT INTO accounts (...) VALUES (...) RETURNING id, created_at, updated_at`，同时支持 SQLite／PostgreSQL。

### 3. Contracts

- `AccountStore::create` 通过 `fetch_all` 完整消费单行 RETURNING 及执行结束，再回填账号 ID 和时间并返回成功；空结果保持 NotFound 错误。不能使用只取首行的 `fetch_one` 提前确认写入。
- SQLite WAL 的独立读连接不等待未完成的写语句；只通过原连接重读会掩盖提交可见性缺陷。不得用固定延时或重试 404 替代写入完成保证。
- 创建返回后，正式同步流程可立即调用凭据解析并切换绑定；SQL、字段、重复邮箱处理及 schema 保持既有契约。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|---|---|
| 创建成功 | 独立连接立即读到返回 ID，后续凭据解析正常 |
| 重复邮箱或 SQL 执行失败 | 返回错误，不报告新账号创建成功 |
| RETURNING 无记录 | NotFound，不回填伪造 ID |

### 5. Scenarios and Examples

- 正常：首次同步创建账号后，紧接的凭据解析读取同一账号，无需用户再次点击同步。
- 基础：SQLite WAL 下用另一个连接池读取刚创建 ID，计数为 1；时间与 OAuth 字段继续通过现有回归。
- 错误用法：`fetch_one` 取得 ID 后立即返回 201，独立连接尚读不到记录。正确处理：完整消费执行结果，并用独立连接证明提交已完成。

### 6. Tests Required

- `test_create_is_committed_before_independent_read`：使用生产 `init_db` 的 WAL 模式、独立 reader 连接池；创建返回后立即按 ID 查询，必须为 1。不得改成同池读取或添加等待。
- `account_store_timestamp_test`：原时间／空值／OAuth／策略字段回归保持；v3 联合堆栈通过正式同步 API 创建后立即解析凭据并绑定。

## Scenario: 网关请求窗口费用

### 1. Scope / Trigger

- 修改网关业务用量记录、5h／7d 费用汇总、账号分页 `request_usage` 或卡片统计展示时适用。官方额度百分比与本地请求费用属于不同数据源，不能把订阅额度解释成固定美元余额。

### 2. Signatures

- `UsageStore::migrate(pool: &AnyPool) -> Result<(), sqlx::Error>`：通过 `db::migrate` 幂等建表，SQLite／PostgreSQL 共用 SQL。
- `UsageStore::record(&self, record: &UsageRecord) -> Result<(), AppError>`：按 `record_id` 唯一键插入一次调用。
- `UsageStore::summaries(&self, accounts: &[Account], now: DateTime<Utc>) -> Result<HashMap<i64, RequestUsage>, AppError>`：在数据库内批量聚合当前账号页。
- `GatewayService::new(account_svc, rewriter, telemetry_svc, settings_store, cache, usage_store)`：最后一个参数是全进程共享的 `Arc<UsageStore>`。
- `GET /admin/accounts`：保留原分页与账号字段，账号新增可选／可空 `request_usage`。
- 新表 `usage_records` 保存账号、UTC 毫秒时间、模型、Token 数、可空费用、partial 和价格版本；`usage_stats_meta` 的 `recorded_since` 保存首次启用时间，不是可编辑 setting。

### 3. Contracts

- 只采集实际成功转发的 `/v1/messages`，独立于自动遥测开关；普通 JSON、SSE、压缩与提前断开都通过同一一次性上下文收口。EOF、末帧、body error 与 Drop 不得重复写入。首次实际非流探针调用计入，本地缓存命中、mock、count_tokens 和手动 usage 查询不计入。
- 共用 `merge_message_usage` 的累计最大值语义；输入、输出、缓存读与缓存写总量分别累加，5m／1h 写入只是总写量明细，不能再次加入总 Token。采样和解码限长；未知模型、无用量、损坏响应和中断使用未定价／部分记录状态，不能假装免费且完整。
- Claude 价格由 `src/service/claude-pricing.json` 内置，版本来自本机 sub2api 快照及其明确兜底规则。已记录费用不随目录更新回算；不在业务热路径访问远程价格或参考仓库。该资源随现有 Docker `COPY src` 进入构建。
- `usage_records` 只保存数值摘要，不保存正文、凭据和会话明文。时间统一为 UTC RFC3339 毫秒字符串；按时间至少保留完整周窗口，当前为八天，禁止按固定条数裁剪。已成功落库的记录重启后可读，异步尚未落盘的调用不承诺崩溃恢复。
- 两个窗口分别采用有效未来 reset 减去 5h／7d 作为开始时间，且 reset 不得超过该窗口长度；按请求开始时间的左闭右开区间汇总，查询上限不超过本次 now。reset 缺失、非法或到期时返回明确标为 `rolling` 的最近窗口。
- `request_usage` 包含 `recorded_since`、`five_hour`、`seven_day`。各窗口字段为 `requests`、`tokens`、`cost_usd`、`unpriced_requests`、`partial_requests`、`starts_at`、`ends_at`、`basis: "quota" | "rolling"`、`coverage_complete`、`estimated_total_cost_usd`。
- `cost_usd` 是已知部分的标准 API 折算费用，不是 A／U 用户结算。费用未确定的请求计入 `unpriced_requests`；不完整响应计入 `partial_requests`。读取数据库失败时 API 保留账号列表并返回空统计，前端不得填成零请求／零费用。
- 总额只在有效官方周期、有限正百分比／费用、无未定价／部分记录且覆盖完整时使用 `cost_usd * 100 / utilization`。覆盖起点保守取首次记录时间、本进程开始时间和最近写失败；因此启用／重启后的首个未完整覆盖周期隐藏估算。页面标明按网关记录估算，不称为官方配额或余额。
- 列表刷新只读，不删除记录；5h 重置只切换自身周期，7d 按自己的 reset 切换。手动额度刷新成功后立即重读列表，正常页面维持既有 5 秒轮询，不新增自动 usage POST。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 同一 `record_id` 重复 finalize | 一条记录、一次请求费用 |
| 同一 SSE usage 多次出现 | 保留字段最大值，不累计重复事件 |
| 未知模型／缺少 usage | 请求仍可统计，费用未知；不生成总额估算 |
| 中断、损坏或解码超限 | 标记部分数据，只展示已知费用 |
| 缺少／非法／过期 reset | 本地统计 `basis=rolling`，官方百分比未知／待更新，无外推 |
| 真实已知 0% | 允许显示 0%，不做除零外推 |
| 普通刷新／重启 | 已落库金额保留；重启后覆盖不足时隐藏外推 |
| 5h reset 推进，7d 未推进 | 5h 只计新周期，7d 保留仍属于其周期的请求 |
| 数据库读写失败 | 记录脱敏诊断，统计不可用或覆盖不完整；不阻断业务转发，不伪造零值 |

### 5. Scenarios and Examples

- 正常：同一请求按所属周期同时进入 5h／7d；完整周期的费用为 $12.50、官方占用为 10% 时，按网关记录估算 $125.00。
- 基础／边界：上线首周仍可显示已记录请求和费用，首个周期缺少历史数据时不外推；页面刷新保留金额，新 reset 使窗口查询自然排除旧周期。
- 错误：刷新页面时执行 DELETE 清空统计，或把所有请求费用挂到 Fable 专属窗口。
- 正确：仅后台按保留时长裁剪历史记录，当前 5h／7d 由各自 reset 选区间；模型专属额度继续使用原有含义。

### 6. Tests Required

- `refresh_keeps_records_and_each_reset_selects_its_own_cycle`：重复读取与重复 finalize、两个周期独立推进、请求边界和 Token／费用汇总。
- `committed_records_survive_independent_connection_and_reopening`：幂等迁移、独立连接可见、重启保留金额、覆盖不足禁止外推。
- `unknown_or_incomplete_data_never_produces_total_estimate`：缺失／非法／到期 reset、零比例、未定价和部分响应。
- `gateway_usage_records_real_responses_once_without_telemetry`：本地真实 HTTP 上游验证 JSON、分块 SSE、gzip、取消、首次探针与缓存命中、count_tokens 的调用／记录次数。
- `service::usage`／`service::usage_pricing`：实际模型与 speed、累计 Token、不同 TTL、别名、长上下文、未知模型及有界解码；金额断言对照参考价格。
- 管理 API／浏览器：字段与 TypeScript 契约一致，自动刷新独立切换周期、未知与待更新明确、手机无横向溢出、零自动 usage POST；通过 `cargo fmt --check`、`cargo test --locked`、`npm run build`。

## Common Mistakes

| 反模式 | 风险 | 正确做法 |
|--------|------|----------|
| 只更新 SQLite schema | PostgreSQL 部署启动失败 | SQLite/PG 同步改 |
| 老 settings 没有迁移 | 远程实例仍使用旧行为 | 在 `migrate` 中处理旧 key/value |
| 只迁移组合 setting 的一半 | 服务启动后仍按另一个旧 key 刷回旧行为 | 把旧默认组合一起迁移，并用自定义值测试保护显式回滚 |
| setting 写入后不 reload | UI 显示已保存但热路径不生效 | `update_settings` 后调用对应 reload |
| 前端类型漏字段 | 构建或运行时展示异常 | 同步 `web/src/api.ts` |
| 直接暴露 `access_token` / `refresh_token` | 凭据泄露 | 管理 API 和 UI 做脱敏或必要最小展示 |
