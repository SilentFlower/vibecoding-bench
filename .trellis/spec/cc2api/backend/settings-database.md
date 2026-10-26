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

`AccountStore` 使用 SQLx Any：PostgreSQL 的 JSONB 写入参数必须显式转为 `::JSONB`；查询和 INSERT RETURNING 的原生 JSONB/时间列须投影为 TEXT 后解码。时间解析同时接受 SQLite RFC3339 和 PostgreSQL 带时区文本，不能把无法直接解码的原生类型误当作空 JSON、无到期时间或当前时间。

`five_hour_usage_limit_percent`、`seven_day_usage_limit_percent` 的账号字段、双库升级和局部更新合同见 [每账号 5h/7d 用量控制线](./service-architecture.md#scenario-每账号-5h7d-用量控制线)。凭据刷新、进程指标更新和状态快捷操作必须保留这两个配置；状态与控制线同时提交时用独立控制线 SQL 避免旧 Account 快照覆盖新凭据或状态。

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
- 总额预估与本机 sub2api 一致：有效官方周期内，只要官方百分比和已记录费用为有限正数，就使用 `cost_usd * 100 / utilization`；启用、重启、采集间断、未定价或部分响应均不作为隐藏已有正费用预估的门槛。完整性字段保留为元数据，卡片不显示“部分记录”标签，金额标为“预计总费用”，不称为官方配额或余额。
- 列表刷新只读，不删除记录；5h 重置只切换自身周期，7d 按自己的 reset 切换。手动额度刷新成功后立即重读列表，正常页面维持既有 5 秒轮询，不新增自动 usage POST。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 同一 `record_id` 重复 finalize | 一条记录、一次请求费用 |
| 同一 SSE usage 多次出现 | 保留字段最大值，不累计重复事件 |
| 未知模型／缺少 usage | 请求仍可统计；没有已知正费用时不预估，混合窗口按已知正费用预估 |
| 中断、损坏或解码超限 | 保留部分数据事实，按已知正费用和有效正比例预估 |
| 缺少／非法／过期 reset | 本地统计 `basis=rolling`，官方百分比未知／待更新，无外推 |
| 真实已知 0% | 允许显示 0%，不做除零外推 |
| 普通刷新／重启 | 已落库金额保留；不因重启重新等待完整周期才显示预估 |
| 5h reset 推进，7d 未推进 | 5h 只计新周期，7d 保留仍属于其周期的请求 |
| 数据库读写失败 | 记录脱敏诊断，统计不可用或覆盖不完整；不阻断业务转发，不伪造零值 |

### 5. Scenarios and Examples

- 正常：同一请求按所属周期同时进入 5h／7d；完整周期的费用为 $12.50、官方占用为 10% 时，按网关记录估算 $125.00。
- 基础／边界：上线首周和重启后均按已有正费用与有效官方占用预估；页面刷新保留金额，新 reset 使窗口查询自然排除旧周期。
- 错误：刷新页面时执行 DELETE 清空统计，或把所有请求费用挂到 Fable 专属窗口。
- 正确：仅后台按保留时长裁剪历史记录，当前 5h／7d 由各自 reset 选区间；模型专属额度继续使用原有含义。

### 6. Tests Required

- `refresh_keeps_records_and_each_reset_selects_its_own_cycle`：重复读取与重复 finalize、两个周期独立推进、请求边界和 Token／费用汇总。
- `committed_records_survive_independent_connection_and_reopening`：幂等迁移、独立连接可见、重启保留金额与总额预估。
- `unpriced_data_without_positive_cost_never_produces_total_estimate`：缺失／非法／到期 reset、零比例及无已知正费用。
- `partial_window_estimates_use_known_cost_like_sub2api`：重启及混合未定价／部分响应时，两个窗口仍按已有正费用预估。
- `gateway_usage_records_real_responses_once_without_telemetry`：本地真实 HTTP 上游验证 JSON、分块 SSE、gzip、取消、首次探针与缓存命中、count_tokens 的调用／记录次数。
- `service::usage`／`service::usage_pricing`：实际模型与 speed、累计 Token、不同 TTL、别名、长上下文、未知模型及有界解码；金额断言对照参考价格。
- 管理 API／浏览器：字段与 TypeScript 契约一致，自动刷新独立切换周期、未知与待更新明确、手机无横向溢出、零自动 usage POST；通过 `cargo fmt --check`、`cargo test --locked`、`npm run build`。

## Scenario: 请求级诊断与发送尝试关联

### 1. Scope / Trigger

- 修改 messages 请求观测、响应关联头、sender 请求 ID、诊断数据库、管理查询、留存或响应解析时适用。
- 诊断用于排查实际调用行为，独立于 `usage_records` 计费和自动遥测。不得为了补齐诊断改变准入、画像、调度、重试、session 池或上游协议字节。

### 2. Signatures

- `GatewayService::with_diagnostics(self, Arc<DiagnosticsStore>) -> Self`：生产装配入口，保留原构造函数兼容性。
- `DiagnosticsStore::migrate(&AnyPool)`：由正式 `db::migrate` 调用，幂等创建 `request_diagnostics`、`request_diagnostic_attempts` 和索引；两表分别以请求 UUID、尝试 UUID 为唯一键。
- `DiagnosticsStore::list(DiagnosticQuery) -> Result<DiagnosticPage, AppError>`；`detail(&str) -> Result<DiagnosticDetail, AppError>`，均为 async。
- `GET /admin/request-diagnostics`：沿用管理鉴权；参数为 `page`、`page_size`、`account_id`、`correlation_id`、`outcome`、`since`、`until`；返回 `items/total/page/page_size/health`。
- `GET /admin/request-diagnostics/:request_id`：返回 `request` 和按序排列的 `attempts`。
- `PreparedRequest.request_id`：有合法内部 UUID 时保留，空值继续生成；v3 sender 的既有 observations 复用该尝试 UUID。

### 3. Contracts

- 仅在网关 Token 鉴权后的精确 `/v1/messages` 入口建立根请求 UUID；每次真实提交建立独立尝试 UUID。`count_tokens`、Hello、后台遥测不混入此请求尝试链。
- 下游新增 `X-CC2API-Request-Id` 根 UUID；保留已有 `X-Request-Id`，缺失时补根 UUID。根 UUID、最终响应 ID、上游 `request-id/x-request-id` 可用于列表反查；标准 UUID 和 `req_` 字母数字 ID 保留，其它头值先 SHA256。诊断 ID 不增加到发往上游的业务 headers/body。
- 尝试记录实际冻结画像 key/选择方式、最终模型/max_tokens/thinking 类型与预算/effort/stream/工具数量、匿名 session/thread、响应模型与消息、stop_reason、六类 token、partial、状态、耗时、重试原因和受控错误阶段/类型。未知字段保留 `null`；累计 usage 使用每字段最大值，5m/1h 缓存写明细不重复加入总量。
- 根记录包含起止时间、下游状态、最终选中账号、结果和尝试数。根状态与尝试实际上游状态分开；中间认证或签名错误不得覆盖后续尝试结果。首字节字段 `ttft_ms` 测量响应头到达耗时，不解释为首个模型文本 token。
- 本地拒绝、模拟和缓存命中有根记录，但无虚构的上游尝试。EOF、末帧、读取错误和 Drop 只终结一次；HTTP 200 内的错误事件与成功区分，缺用量或采样失败标记 `incomplete/partial`。发送错误不伪造上游 HTTP 状态或断言未提交。
- session/thread/响应消息仅存带账号及标识类型域的 SHA256 前 128 位；线程前驱和响应消息使用同一消息域。只观察既有池解析结果，不能额外 resolve 或刷新 TTL；上游 session 摘要以实际最终 body 为准。
- 不持久化正文、工具参数、完整 headers、凭据、Cookie、邮箱、设备 ID、账号 UUID、完整 session 或任意 error.message。响应模型、参数枚举及错误类型执行白名单；非标准关联头只保存散列。
- 有界异步队列容量 1024，热路径不等待数据库；每个摘要上限 16 KiB，响应解析/压缩采样上限 1 MiB。`health.dropped_records` 统计丢弃写入事件，`write_failures` 统计写入/清理失败，`observation_failures` 统计采样/解码/解析失败尝试；均为进程内计数，重启清零，日志只输出固定文案、计数及内部 UUID。
- 按请求开始时间保留至少八天，后台每小时清理，列表 GET 不删除。已提交记录跨重启可查，进程崩溃前未提交缓冲不承诺恢复；`in_progress` 不能被直接当作仍在运行。追加表支持回滚旧程序后保留，不影响原费用表。
- 请求与尝试分别 upsert，迟到的进行中快照不得覆盖终态。SQLx Any 0.7 将无类型 NULL 参数编码为 i32；同一缓存 SQL 的可空字段先空后有值时须保持绑定类型稳定。内部非空标识/时间用字符串绑定再 `NULLIF($n,'')`，正整数账号 ID 用 i64 绑定再 `NULLIF($n,0)`；不得把这些占位约定用于允许真实空字符串或零值的业务字段。
- 分页默认 1/50，每页 1..=200；账号 ID 为正整数。关联条件最多 128 字节，并执行与写入相同的规范化。时间为 RFC3339，统一 UTC 毫秒，筛选区间左闭右开。无新环境变量或 setting。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 401 恢复、签名修复或换号 | 同一根请求，独立尝试与实际账号/状态/重试原因 |
| 模拟、缓存、本地拒绝 | 根结果明确，未发送时尝试数为零 |
| 流内错误、读取异常、取消 | 保留部分 token，受控终态，响应原始字节继续透传 |
| 损坏压缩、采样超限、非法 JSON | `partial=true`，受控错误类型与观察失败计数，不阻断业务 |
| 队列满、写入或清理失败 | 记录脱敏失败信号，不改变转发/费用，不返回假完整覆盖 |
| 非法分页、账号、时间或结果筛选 | 400 |
| 未鉴权管理查询 / 不存在详情 / 存储不可用 | 401 / 404 / 503，不伪装为空列表 |
| SQLite/PG 首次/重复迁移，可空字段从开始到终态 | 幂等、正确保留 NULL，无参数类型漂移 |

### 5. Scenarios and Examples

- 正常：new-api 留下响应 ID，管理员以 `correlation_id` 查到根 UUID，再读取两次 401→200 尝试；sender evidence 的 request_id 对应尝试 UUID。
- 边界：两个真实 session 借用同一上游成员时，真实散列不同、上游散列相同；目标过期后可观察新目标，诊断不能延长旧目标 TTL。
- 错误用法：HTTP 200 且没有完整 usage 就填零并标成功，或把缓存/中间重试写入原费用表。正确处理：未知值为 `null`，结果与完整性分开判定，费用保持原语义。
- PostgreSQL 可空正整数示例：`.bind(request.account_id.unwrap_or(0))` 配合 `NULLIF($7,0)`；不能直接复用先绑定 `None::<i64>`、再绑定实值的 Any 缓存语句，也不能把未知账号持久化为真实 0。

### 6. Tests Required

- `sqlite_diagnostics_storage_contract` 与显式执行 `postgres_diagnostics_storage_contract`：开始→终态、重复写入、迟到快照、NULL、分页/账号/关联过滤、重开连接、八天精确边界。PG 使用 `CC2API_DIAGNOSTICS_TEST_POSTGRES_DSN` 指向独立临时库，ignored 不等于通过。
- `diagnostics_preserve_bytes_and_correlate_anonymous_sessions`：最终参数、stop_reason、null token、匿名标识、头值保留/散列反查及合成秘密不泄露。
- `diagnostics_record_stream_errors_and_cancellation_once`、`diagnostics_report_observation_failures_without_changing_bytes`、`diagnostics_cover_early_cancellation_and_unavailable_storage`：流内错误、读取失败、取消、超限/解码/解析、数据库故障与响应保真。
- `diagnostics_overload_and_write_failures_are_observable` 与 `diagnostics_routes_require_admin_and_expose_committed_requests`：队列立即返回、健康计数、管理员鉴权、分页错误和详情查询。
- Gateway 现有真实 HTTP 回归：`gateway_usage_records_real_responses_once_without_telemetry` 验证 JSON/SSE/gzip/取消、缓存/count_tokens 与费用次数；签名重试、OAuth 恢复、setup 换号及 `gateway_hello_probe_reuses_resolved_upstream_session` 核对独立尝试、实际画像和会话归属。
- `raw_body_header_order_and_upstream_error_survive_bridge`：sender 证据保留尝试 UUID，上游业务 headers 不泄漏该 UUID，原字节/头顺序不变。执行 `cargo fmt --check` 与完整 `cargo test --locked`；协议改写变化复用完整测试中的 CCH 回归或补定向验证。

## Common Mistakes

| 反模式 | 风险 | 正确做法 |
|--------|------|----------|
| 只更新 SQLite schema | PostgreSQL 部署启动失败 | SQLite/PG 同步改 |
| 老 settings 没有迁移 | 远程实例仍使用旧行为 | 在 `migrate` 中处理旧 key/value |
| 只迁移组合 setting 的一半 | 服务启动后仍按另一个旧 key 刷回旧行为 | 把旧默认组合一起迁移，并用自定义值测试保护显式回滚 |
| setting 写入后不 reload | UI 显示已保存但热路径不生效 | `update_settings` 后调用对应 reload |
| 前端类型漏字段 | 构建或运行时展示异常 | 同步 `web/src/api.ts` |
| 直接暴露 `access_token` / `refresh_token` | 凭据泄露 | 管理 API 和 UI 做脱敏或必要最小展示 |
