# 定时养号技术设计

## 1. 架构边界

本功能由四个现有边界协作完成：

1. `cc2api` 负责 OAuth 凭据解析、刷新锁和账号主数据。
2. `orchestrator` 负责 cc2api 管理 API 客户端、本地 profile 镜像、账号绑定和调度状态。
3. `Scheduler` 继续负责真实 run 的每账号并发和 worker 生命周期。
4. `webui` 在现有 Accounts 和 Runs 页面提供配置、操作与状态展示。

凭据流只允许：

```text
cc2api AccountService
  -> 受管理员鉴权的凭据解析接口
  -> orchestrator 原子更新 data/profiles/<name>/.credentials.json
  -> worker 运行副本只使用 AT，不持有可刷新的 RT
```

bench 不新增 OAuth refresh 实现，也不经 cc2api 网关账号池执行题库任务。真实 worker 仍按 bench 账号 profile 直连现有上游链路。

## 2. 配置

orchestrator 新增环境变量：

| 变量 | 用途 |
|---|---|
| `CC2API_BASE_URL` | cc2api 服务根地址，空值时禁用集成功能 |
| `CC2API_ADMIN_PASSWORD` | cc2api 管理 API Bearer 密码，只保存在 orchestrator 环境 |
| `CC2API_REQUEST_TIMEOUT_SEC` | 管理 API 请求超时，默认 15 秒 |
| `WARMUP_SCHEDULER_TICK_SEC` | 养号调度扫描间隔，默认 30 秒 |
| `WARMUP_SYNC_RETRY_SEC` | 临时同步失败重试间隔，默认 900 秒 |

同步更新 `.env.example`、本地/远程 compose 和远程部署文档。任何 API 响应或错误都不得回显管理密码。

## 3. bench 数据模型

在现有 `accounts` 表新增 nullable/default 列，并由 `init_db()` 的 `_ensure_column` 幂等补齐：

| 字段 | 类型 | 语义 |
|---|---|---|
| `cc2api_account_id` | INTEGER NULL | 绑定的 cc2api 账号 ID |
| `warmup_enabled` | INTEGER DEFAULT 0 | 是否参与自动调度 |
| `warmup_interval_min_hours` | INTEGER DEFAULT 3 | 最小随机间隔 |
| `warmup_interval_max_hours` | INTEGER DEFAULT 5 | 最大随机间隔 |
| `warmup_next_run_at` | REAL NULL | 下次触发 epoch seconds；NULL 表示未安排或 run 活跃中 |
| `warmup_last_attempt_at` | REAL NULL | 最近调度/手动尝试时间 |
| `warmup_last_run_id` | TEXT NULL | 最近养号 run ID |
| `warmup_last_status` | TEXT NULL | preparing/queued/终态/sync_failed/paused |
| `warmup_last_error` | TEXT NULL | 脱敏错误摘要 |
| `warmup_auth_failures` | INTEGER DEFAULT 0 | 连续 auth_failed 次数 |

增加 `cc2api_account_id IS NOT NULL` 的唯一索引。SQLite 对多个 NULL 允许重复，能够表达未绑定账号。

不新增养号历史表。最近题目直接查询 `runs`：按 `account_id`、`run_kind='warmup'` 和创建时间倒序取最近 20 个 `topic_id`。凭据同步失败没有 run，其最近状态保存在 account 列中。

`runs.run_kind` 复用现有列，新增值 `warmup`。对应 task 标题使用 `[warmup] <topic title>`，prompt 保持标准题目内容。

## 4. cc2api 凭据接口

新增管理员接口：

```text
POST /admin/accounts/:id/oauth-credentials/resolve
```

请求体：

```json
{
  "min_validity_seconds": 2400,
  "force_refresh": false
}
```

响应只包含本次同步需要的字段：

```json
{
  "account_id": 1,
  "access_token": "<secret>",
  "refresh_token": "<secret>",
  "expires_at": 0
}
```

接口约束：

- 只接受 active OAuth 账号。
- `min_validity_seconds` 有明确上下界；普通 run 前传 `timeout + 600`。
- 复用账号级 cache lock，确保 gateway、usage poller 和 bench 不会并发刷新同一 RT。
- `force_refresh=true` 只用于 worker 已检测到 401 的一次恢复。
- 返回前重新读取账号，确保 AT、RT 和过期时间来自同一次最终存储状态。
- 日志只记录账号 ID、是否刷新和错误分类，不记录 token。

`AccountService` 增加可复用的公开方法，现有 `resolve_upstream_token` 继续以 5 分钟缓冲调用同一内部逻辑，保持网关行为兼容。

## 5. orchestrator cc2api 客户端

新增小型 `Cc2ApiClient`，使用 Python 标准库结构化发送 JSON 请求，集中处理：

- base URL 与管理员 Bearer header；
- 请求超时、HTTP 状态和有限大小错误体；
- 分页读取全部 cc2api accounts；
- 创建 OAuth account；
- 解析指定账号凭据；
- 对前端返回脱敏账号摘要。

外部 HTTP 请求必须在 `_db_lock` 外执行。错误转换为可展示但不含敏感响应体的 `ValueError`/`HTTPException`。

## 6. 单账号同步与绑定

### 6.1 profile 解析

集中 helper 读取并校验：

- `.credentials.json.claudeAiOauth.accessToken`
- `.credentials.json.claudeAiOauth.refreshToken`
- `.credentials.json.claudeAiOauth.expiresAt`
- `.credentials.json.claudeAiOauth.subscriptionType`
- `.claude.json.oauthAccount.emailAddress`
- `.claude.json.oauthAccount.accountUuid`
- `.claude.json.oauthAccount.organizationUuid`

代理从 bench account 的协议、host、port、user、pass 组装。代理密码仅用于 backend-to-backend 创建请求，不出现在页面或日志。

### 6.2 创建或关联

`POST /api/accounts/{id}/cc2api/sync`：

1. 读取可用 bench account 与完整 profile。
2. 拉取 cc2api accounts。
3. 优先按非空 `account_uuid` 匹配。
4. bench UUID 缺失时才按规范化邮箱匹配。
5. 邮箱匹配但双方非空 UUID 不同则返回 409。
6. 无匹配时调用 cc2api 创建 OAuth account。
7. 有匹配或创建成功后调用凭据解析接口，以 cc2api 当前凭据原子更新 bench profile。
8. 最后在短事务中写入 `cc2api_account_id`；唯一索引冲突返回 409。

`PUT /api/accounts/{id}/warmup` 用于显式选择已有 cc2api 账号并保存养号配置。后端必须再次校验身份一致性和一对一约束，不能信任前端下拉。

`DELETE /api/accounts/{id}/cc2api-binding` 只清除绑定和养号状态，不调用 cc2api 删除接口。

## 7. managed OAuth worker 模式

只要 account 已绑定 `cc2api_account_id`，所有 task/capture/continue worker 都设置 `CC2API_MANAGED_OAUTH=1`，不以 `warmup_enabled` 为条件。

worker 行为：

- profile 持久副本仍保存与 cc2api 一致的完整 AT/RT。
- 复制到 run home 后移除运行副本中的 `refreshToken`，Claude Code 无法自行轮换 RT。
- profile -> run home 同步只更新 AT、过期时间和非敏感 OAuth 元数据，继续移除 RT。
- run home -> profile credentials 回写在 managed 模式下完全禁用；`.claude.json` 和 `settings.json` 仍按现有规则回写。
- 检测 401 时写入 workspace 的凭据刷新请求标记，并等待 profile 出现新 AT；不调用本地 refresh endpoint。
- orchestrator 为 managed run 启动轻量 watcher。收到标记后调用 cc2api `force_refresh=true`，原子更新 profile，并写入完成/失败标记。
- worker 同步到新 AT 后只注入一次现有认证重试提示；再次 401 则 `auth_failed`。

`OAuthRefreshScheduler` 对绑定账号改为从 cc2api 定期镜像凭据，不调用 `Runner.refresh_account_oauth_token`。额度查询对绑定账号改走 cc2api usage/凭据链路，重授权按钮在绑定期间拒绝执行，要求先解绑，避免绕过单一所有权。

## 8. 养号调度器

新增 `WarmupScheduler` 后台 daemon thread，在 FastAPI lifespan 中随服务启动/停止。

### 8.1 扫描与认领

- 每个 tick 查询 `warmup_enabled=1`、已绑定、账号可用且 `warmup_next_run_at <= now` 的账号。
- 用短事务重新校验状态，并把 `warmup_next_run_at` 置 NULL、`warmup_last_status='preparing'`，防止手动触发和 tick 重复认领。
- 若已有同账号 active warmup run，则保持不创建；由该 run 终态回调重新安排时间。

### 8.2 启动流程

1. 在 DB 锁外调用 cc2api 凭据解析，要求有效期至少 `2400` 秒。
2. 同步失败：临时错误安排 `now + 900`；永久错误关闭养号并写暂停原因。
3. 原子更新 profile 凭据。
4. 查询最近 20 个 warmup topic，选择有效候选。
5. 在单个事务中创建 task、`run_kind=warmup` 的 queued run，并更新账号最近状态。
6. 调用现有 `Scheduler.submit`。

若题库为空，按永久配置错误暂停并显示原因，避免每 30 秒重复扫描。

### 8.3 run 终态

`Scheduler._execute` 在 warmup run 收口后调用统一 helper：

- success：清零连续认证失败并安排下一次随机时间。
- failed/timeout/stopped：保留错误摘要并安排下一次随机时间。
- auth_failed：计数加一；达到 3 次时关闭养号，否则安排下一次随机时间。
- 所有更新必须只影响仍绑定同一 cc2api account 的账号，避免 run 期间解绑后旧回调重新启用调度。

“立即运行”复用同一认领、同步和创建流程；成功启动后等待 run 终态再安排下一次时间。

## 9. WebUI

Accounts 页面保持现有表格和 modal 模式：

- 表格增加紧凑的 `cc2api / warmup` 状态列，显示绑定 ID、active/paused/off、间隔、next 和最近状态。
- 操作区增加“同步”“养号”“立即运行”“恢复/解绑”，按当前状态显示必要按钮。
- 新增养号配置 modal：选择脱敏 cc2api 账号、设置最小/最大小时、开关养号。
- cc2api 列表由 bench 后端代理，只返回 id、name、email 脱敏摘要、status、auth_type；绝不把 token 发到浏览器。
- Runs 页面为 `run_kind=warmup` 显示养号 badge，其他详情链路不变。

所有动态文本继续使用 `escapeHTML`，危险/解绑操作保留确认，暗色和亮色主题均需检查。

## 10. 兼容与回滚

- 新列都有兼容默认值，旧数据库启动后所有账号保持未绑定、养号关闭。
- `run_kind` 已是兼容文本列，新增 `warmup` 不影响 normal/capture。
- 未配置 cc2api 环境变量时，现有账号、任务、抓包和运行继续可用；集成按钮显示不可用错误。
- 回滚代码后新增列和 warmup run 历史可保留，旧版本会忽略未知账号列，并把 warmup run 当普通非 capture run 展示。
- 不修改或删除 cc2api 既有账号，解绑和删除 bench 账号均不向 cc2api 传播删除。

## 11. 验证重点

- SQLite 旧库幂等补列与唯一绑定约束。
- profile 字段解析、脱敏错误和原子凭据写入。
- cc2api 创建/匹配/UUID 冲突与凭据解析锁。
- managed worker 不携带 RT、不本地刷新、不反向覆盖 profile。
- 调度随机边界、最近 20 题去重、停机逾期单次补跑和并发认领。
- 401 强制解析只发生一次，连续认证失败自动暂停。
- WebUI 单账号同步、配置、立即运行、恢复、解绑和 warmup badge。
- 普通任务、批次、抓包、继续对话、额度和账号删除回归。
