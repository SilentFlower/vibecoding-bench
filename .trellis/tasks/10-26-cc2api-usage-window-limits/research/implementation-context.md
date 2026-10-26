# cc2api 每账号额度控制线：实现前证据

## 最终配置粒度

- 用户最终要求每个账号独立设置；正式范围以最新 `prd.md`、`design.md`、`implement.md` 为准。
- 以下保留全局路线的初始技术对照，标记为未采用，不作为实现要求。

## 已核对的类型与入口

- `cc2api/src/model/account.rs:177`：`Account` 已有 `usage_data`、`rate_limit_reset_at` 等字段，没有本地 5h/7d 百分比控制线。
- `cc2api/src/model/account.rs:270`：`Account::is_schedulable` 只判断 active 和上游冷却截止时间。
- `cc2api/src/store/account_store.rs:777`：`list_schedulable` 的 SQL 与 `is_schedulable` 语义一致，没有用量过滤。
- `cc2api/src/service/account.rs:120`：现有 `AccountSelectionContext` 只有 Fable 开关、Fable 周阈值与请求模型；添加新字段时必须搜索全部结构体字面量。
- `cc2api/src/service/account.rs:1086`：`select_account_with_selection_context` 同时覆盖 sticky 和普通候选，是通用控制线的统一入口。
- `cc2api/src/service/account.rs:2517`：`check_usage_window` 读取 `utilization` 和未来 RFC3339 `resets_at`，可复用窗口校验思路；新规则不得把阈值写入 `USAGE_HIT_THRESHOLD`。
- `cc2api/src/service/gateway.rs:1805`：主消息路径构造选号上下文；重试循环复用该快照。应仅为 `/v1/messages` 打开通用控制线，非消息路径保持兼容上下文。
- `cc2api/src/service/gateway.rs:1830`：选号错误在已有上游错误响应、凭据失败等分支下有既定优先级；新增本地 429 需测试首次请求与重试耗尽分支，不能泄漏凭据或原始响应正文。
- `cc2api/src/service/gateway.rs:1960`：先选号，后获取并发槽位与 RPM admission。承诺边界应为选号时最近观测的用量，不应宣称对已分配、排队中或执行中的请求有 token 级硬保证。

## 已有 Fable 行为可复用的部分

- `cc2api/src/service/account.rs:1109`：sticky 达线时加入本轮排除列表、保留并刷新旧绑定；替代账号实际承载请求后再重绑。
- `cc2api/src/service/account.rs:1166`：普通候选先过滤，再进入 RPM 过滤与原有评分。
- 所有允许候选因上限被排除时返回 `AppError::TooManyRequests`，不能回退到达线账号。
- 已有 Fable 限制只影响 OAuth 和 Fable 窗口；通用 5h/7d 有被动响应头数据，应独立支持 OAuth 和 SetupToken，不能照搬 Fable 的 OAuth-only 条件。
- 用量窗口缺失、字段非法或 reset 已过期时不拦截；只有有效的已观测用量满足 `utilization >= limit` 才命中。
- 新的本地百分比过滤不写账号 `status` 或 `rate_limit_reset_at`，以便配置调高、关闭或窗口过期后立即恢复选号。上游实际 429 的冷却仍按原有 97% 分类处理。

## 配置落点选项

### 未采用：全局设置

- `SettingsStore::get_all` 位于 `cc2api/src/store/settings_store.rs:130`，可一次读取两个窗口配置，再通过一把 `RwLock` 发布配置快照。
- 设置键需同步默认常量、`db.rs` 共用缺失键补齐、GET 默认回填、PUT 校验、保存后 reload、`main.rs` 启动 reload、Settings.vue 和 README。
- 现有 `SettingsMap = Record<string, string>` 足以传递新设置，不必新增账号 DTO。
- 可以用两个独立整数字符串设置表达限制，0 为关闭，1～100 为开启后的百分比；默认均为 0，避免升级立即改变调度行为。
- `Settings.vue` 的数字输入运行时可能为数字；须沿用 `formString` 规整后校验与保存，不能直接对 ref 调用 `.trim()`。

### 采用：账号独立设置

- 需扩展 `Account`、create/update DTO、`ACCOUNT_COLS`/row mapping、账号 create/update SQL、SQLite/PostgreSQL 列迁移、`web/src/api.ts` 与 `Accounts.vue`。
- 已重新核对完整 Account、CreateAccountRequest、动态 `Json<Value>` 更新 handler、账号 SQL、两套 schema 与前端表单；更新接口没有独立 UpdateAccount DTO。
- 新字段为 `five_hour_usage_limit_percent`、`seven_day_usage_limit_percent`，默认 0；正式设计记录了创建、局部更新与值域规则。

## 入口范围与限制

- 初次范围优先沿用 Fable 的 `/v1/messages` 入口；`count_tokens`、usage 手动查询、后台 poller、PrimePoller 和其他管理路径不套用新的百分比过滤。
- 后台 PrimePoller 可能独立发出少量真实请求；需要在正式设计中明确此任务控制的是网关消息分配，不能声称拦截所有可能的账号用量来源。
- 当前本地 warmup/classifier 拦截有部分发生在选号之后；保持既有拦截顺序，不能为了限额任务改写协议识别或本地假响应契约。
- 并发和采集延迟可能造成越线；不新增主动 usage 查询、不预扣额度、不估算单请求消耗。

## 验证安排

- `cc2api/tests/account_scheduler_test.rs` 已有临时 SQLite、Memory cache、账号与 Fable 窗口 fixture；新增通用窗口行为用例可沿用同一测试框架。
- 调度覆盖两个窗口各自达线、恰好相等、低于阈值、sticky 换号/保留绑定、全部达线、本地关闭、过期/非法/未知窗口、Token allow/block、OAuth 与 SetupToken、Fable 规则叠加和 RPM 兼容。
- `cc2api/src/handler/router.rs` 已有 settings 默认值、非法值和热刷新测试；新增控制线须覆盖整批保存前校验，失败不写入旧配置。
- `cc2api/src/store/db.rs:1443` 是现有默认插入幂等测试参考。
- `cc2api/src/service/gateway.rs:7647` 是非法存量值 reload 兜底测试参考。
- 必需验证：`cargo fmt --check`、完整 `cargo test`、`cd web && npm run build`，以及修改数字输入后保存的页面交互验证。

## 已读取规范

- `.trellis/spec/cc2api/backend/settings-database.md`：Settings Key 契约、账号字段同步。
- `.trellis/spec/cc2api/backend/service-architecture.md`：热路径规则、Fable 周用量上限 fallback、被动用量采集。
- `.trellis/spec/cc2api/frontend/frontend-guidelines.md`：设置字符串、数字输入规整、API client 与构建。
- `.trellis/tasks/archive/2026-07/07-30-fable-weekly-usage-cap/{prd,design}.md`：旧 Fable 全局阈值的范围与兼容决策。
