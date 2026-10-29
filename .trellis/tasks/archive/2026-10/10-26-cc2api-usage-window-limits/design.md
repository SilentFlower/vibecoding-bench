# cc2api 每账号 5h/7d 用量控制线设计

## 已核对的现有接口

- `Account` 定义在 `cc2api/src/model/account.rs:164`，已有 `rpm_limit: i32` 与 `usage_data: Value`。
- `CreateAccountRequest` 是 `cc2api/src/handler/router.rs:410` 的私有反序列化类型；更新接口在同文件 `update_account` 中接收 `Json<serde_json::Value>`，没有单独的 UpdateAccount DTO。
- `AccountStore` 的 `row_to_account/create/update/get_by_id/list/list_schedulable` 负责字段落库与读取；`ACCOUNT_COLS` 显式列出查询字段。
- 调度入口是 `AccountService::select_account_with_selection_context`，上下文目前只含 Fable 开关、Fable 阈值与模型。
- `web/src/api.ts` 的管理端创建/更新参数为 `Partial<Account>`；`Accounts.vue` 有初始化、新建重置、编辑回显、导入表单和保存多个入口。

## 新增账号字段

| 字段 | Rust/数据库类型 | 默认与值域 | 含义 |
| --- | --- | --- | --- |
| `five_hour_usage_limit_percent` | `i32` / INTEGER（PG INT） | 0；整数 0～100 | 0 关闭，1～100 为 5h 用量百分比上限 |
| `seven_day_usage_limit_percent` | `i32` / INTEGER（PG INT） | 0；整数 0～100 | 0 关闭，1～100 为 7d 用量百分比上限 |

- `Account` 使用 serde 缺失默认 0，新增公开字段附中文用途注释。
- 新账号省略字段时使用 0；创建请求显式提供的非法 JSON 类型或越界数值拒绝。
- 更新未提交的字段保留现有值；显式提交必须是 0～100 的 JSON 整数，不把非法值静默忽略或夹取到范围内。
- `AccountService::create_account/update_account` 校验同一值域，覆盖不经 HTTP handler 的内部调用。
- 新校验在任何字段落库或状态快捷更新之前完成，失败不写入其他更新。
- 同时提交 active/disabled 状态与控制线时，沿用原状态操作，再通过 `AccountService::update_account_usage_limits` / `AccountStore::update_usage_limits` 仅写两个控制线；不能因状态快捷返回丢弃已提交字段，也不能把状态操作前的旧账号快照整行写回。
- 不新增全局设置键，不改变 Fable 的全局配置契约。

## 持久化与兼容

1. SQLite/PG 新建 schema 均添加两个 `NOT NULL DEFAULT 0` 整数列。
2. 旧库沿用当前幂等 `ALTER TABLE` 迁移方式补列；重复执行不覆盖已设置值。
3. `AccountStore::row_to_account`、`ACCOUNT_COLS`、INSERT/UPDATE 列表与 bind 顺序成对更新，保留创建后消费完整 RETURNING 结果的提交可见性契约。
4. 账号新建、更新、get、分页与调度查询均返回真实持久值。
5. 同步仓库全部 `Account { ... }` 字面量及测试 fixture，旧行为用 0 明确表达。
6. 凭据刷新、指标条件更新、停用/启用等专用 SQL 保留这两个字段；不借本任务重构凭据所有权或配置门禁。
7. 实际 PostgreSQL 回归发现现有账号创建/指标写入缺少 JSONB 参数转换，且 Any 读取原生 JSONB/时间列会失败。为完成本任务双库创建、调度读取及 bench 兼容验收，局部修正 AccountStore 的 JSONB 写入、JSON/时间文本投影和时间解析；增加凭据刷新与指标更新后控制线保留的双库回归。此为原接口的类型兼容修复，不改变字段或所有权语义。

## 窗口判断

- 读取 `usage_data.five_hour` 与 `usage_data.seven_day`，分别对照账号自己的两个字段。
- 只处理有效阈值 1～100；阈值为 0 时该窗口直接跳过。
- `utilization` 必须为可解析、有限且非负的数字；`resets_at` 必须为可解析且晚于当前时间的 RFC3339 字符串。
- 命中语义为 `utilization >= limit_percent`；不使用评分的时间衰减值，也不预留隐含缓冲。
- 任一有效窗口命中即本轮不可选；每次选号重新按当前时间判断，不缓存“达线”状态。
- 两类账号都可提供普通窗口被动数据，因此 OAuth 与 SetupToken 都适用；不能复用 Fable helper 的 OAuth-only 资格限制。
- 可复用现有 `check_usage_window` 的解析流程；若增强其异常值处理，须回归既有 Fable 与 429 分类测试，避免改变合法输入行为。

## 入口与调度

### 请求上下文

- 在 `AccountSelectionContext` 增加消息额度控制启用标记，具体命名在实现时与现有风格一致。
- 主网关仅对 `path == "/v1/messages"` 启用；阈值来自所选账号，不放入 Gateway 全局热缓存。
- `AccountSelectionContext::disabled()` 保持新规则关闭；count_tokens、管理和后台独立调用继续走兼容路径。
- 消息请求不依赖是否解析到了模型即可执行通用限制，Fable 专属判断仍依赖原模型条件。

### Sticky 与普通候选

1. sticky 账号通过原 active/冷却/Token 范围判断后，再判断本账号通用窗口与现有 Fable 专用限制。
2. 达线时只加入本轮排除列表并保留/续期原 sticky，继续寻找可用替代账号。
3. 普通候选先按 Token 范围与本轮排除过滤，再剔除通用或 Fable 达线账号，最后沿用现有 RPM 与优先级/评分。
4. 仅因本地额度限制耗尽允许候选时返回 `AppError::TooManyRequests`；报错可说明是账号用量上限，但不能把不同账号阈值描述为同一个全局百分比。
5. 无符合范围的账号、凭据失败、已有上游响应等原有错误优先级保持既有合同；新增测试确认不把实际达线误报为无账号或静默放回达线账号。
6. 替代账号实际承载后使用已有 `should_bind_session` / `bind_selected_session` 重绑，不提前覆盖原 sticky。
7. 达线不写账号状态或 `rate_limit_reset_at`；关闭/调高阈值与窗口过期后可自动恢复，已有真实上游冷却继续有效。

### 观测与排队边界

- 判断点是每次选号读取到的当前账号快照；请求分配后不因新配置或新 usage 被取消。
- 已分配但尚在排队中的请求与正在执行的请求保持现有生命周期。
- 网关响应继续通过现有被动采集更新用量，后续选号使用新值。
- 不新增主动 usage 查询、额度预扣、成本预测、协议正文/头部改写或后台任务调度修改。
- 部分本地 warmup/classifier 响应发生在选号后，本任务保持既有顺序，不为了额度控制改变拦截识别。

## 前端

- `api.ts::Account` 增加两个数值字段，兼容旧响应时表单以 `?? 0` 回显。
- `Accounts.vue` 在并发/RPM/优先级附近增加「5 小时用量上限 (%)」「7 天用量上限 (%)」两个 number input，整数步长 1，最小 0、最大 100；说明「0 表示不限制，达到任一上限后暂停分配新请求」。
- 初始化、新建、编辑、导入后的表单、create payload 与 update payload 一并同步，不能遗漏任一重置入口。
- 保存前验证有限整数及 0～100；空值或错误类型不能因 `Number('')`、`Number(null)` 等转换被意外保存成 0。
- 列表既有 5h/7d 额度区域显示配置上限；关闭时明确显示未限制，不把本地限制误称为上游停用。
- 说明依据已观测用量控制，单次或并发请求可能越线；不展示 Rust/数据库等实现细节。
- 沿用现有 `api`、toast 和管理页样式，不新增路由。

## 验证

- 模型/服务：0、1、100 边界，非法值，两个窗口恰好达线、低于达线、未来/过期/缺失/非法 reset、无效用量与两类账号。
- 迁移/存储：新库与旧库，两次迁移，非零值保留，创建/更新/get/分页/调度查询读写往返。SQLite/PG 均执行可复核契约测试；数据库证据不足时明确记录，不以 SQLite 代替 PG 声称通过。
- 管理 API：创建默认、显式值、局部修改保留另一字段、非法类型/范围拒绝且旧配置未变、旧 payload 兼容。
- 调度：sticky 换号与保留、全部达线、Token 范围、混合 Fable/通用限制、非消息禁用、RPM 保持与窗口恢复。
- 页面：新建/编辑/导入重置、修改 number input 保存与回显、列表上限展示、后端保存错误提示。
- 检查：`cargo fmt --check`、完整 `cargo test`、`cd web && npm run build`、`git diff --check`。

## 回滚与限制

- 将账号两个字段设为 0 即关闭本任务规则；迁移只增列，保留既有账号与用量数据。
- 部署旧代码时新列可保留，旧代码不读取它们；不执行删列回滚。
- 用量未知时允许调度、并发可能越线、独立 CLI/后台请求不由本次网关选号控制，须在最终 Brief 明示。
