# cc2api Backend Service Architecture

## 适用范围

本文件约束 `cc2api/src/` 的 Rust 后端结构：

```text
src/main.rs
src/handler/
src/middleware/
src/model/
src/service/
src/store/
src/tlsfp/
```

## 分层契约

- `main.rs` 只负责装配：加载 `Config`、初始化 tracing、注册 SQLx Any driver、初始化 DB/cache/store/service、启动后台 poller、构建 router。
- `handler/router.rs` 负责 HTTP 路由、DTO 解析、管理 API 返回形状和静态资源 fallback，不把复杂业务逻辑塞进 handler。
- `middleware/auth.rs` 只处理管理端 Bearer 密码认证；网关 API token 鉴权留在 `gateway_fallback` 进入 `TokenStore` 查询。
- `model/` 是 DB/API 共享结构。新增字段要同步 store 映射、前端类型和迁移。
- `service/` 放业务逻辑：账号调度、Gateway 转发、OAuth、usage poller、telemetry、rewriter、version profile。
- `store/` 放持久化与缓存抽象。不要让 handler 直接写 SQL。
- `tlsfp/` 和 `craftls/` 是 TLS 指纹链路，改动要按协议/抓包任务处理。

## Gateway 热路径规则

`GatewayService::handle_request` / `handle_request_inner` 是最高风险路径。修改前必须明确：

- 请求是否应在账号选择前拦截，例如 assistant prefill、warmup、Auto Mode classifier、非流探针缓存。
- 请求是否会消耗账号并发/RPM；粘性会话下不能因为 RPM 超限随意切号破坏缓存。
- 请求体是否被读取、解压、改写或缓存；读取后转发必须使用最终 body。
- Claude Code 请求改写必须在 CCH 和 `cc_version` 重新计算前完成。
- 上游非成功响应如果要重试，必须保留原有错误体兼容性和敏感信息边界。
- SSE 流式响应只能插入明确允许的 keepalive/comment，不要重排上游 chunk。

## Scenario: Gateway 账号槽位与 RPM Admission 顺序

### 1. Scope / Trigger

- Trigger：修改 `GatewayService::handle_request_inner` 中账号选择、账号级 FIFO 队列、RPM admission、429 重试或本地拦截顺序时适用。
- 目标：RPM 计数表示“已经获得账号执行槽位、即将进入上游转发链路”的请求数，而不是“进入本地等待队列”的请求数。

### 2. Signatures

- 槽位入口：`AccountService::get_or_create_queue(account.id, account.concurrency).await`
- 等待入口：`AccountQueue::acquire(timeout).await -> Result<OwnedSemaphorePermit, QueueWaitError>`
- RPM 入口：`AccountService::acquire_account_rpm(account, sticky, session_hash).await -> Result<(), AppError>`
- RPM 状态：`AccountService::get_account_rpm_status(account).await -> AccountRpmStatus`

### 3. Contracts

- Gateway 正常上游路径必须先获得 `OwnedSemaphorePermit`，再调用 `acquire_account_rpm`。
- 处于 `AccountQueue::acquire(...)` 等待阶段的请求不得递增 RPM。
- `QueueWaitError::QueueFull` / `QueueWaitError::Timeout` / `QueueWaitError::Closed` 发生时，该账号 RPM 不得变化。
- 非粘性请求拿到槽位后若 RPM 饱和并返回 `AppError::ServiceUnavailable`，必须释放当前账号槽位并排除该账号后重新选号。
- 粘性请求拿到槽位后若 RPM 饱和，仍按 `acquire_account_rpm` 的等待/本地 429 语义处理，不得随意切号。

### 4. Validation & Error Matrix

| 条件 | 期望行为 |
|------|----------|
| 排队等待槽位 | `queued` 可增加，RPM `current` 不增加 |
| 成功获得槽位且 RPM 未满 | RPM `current += 1`，permit 交给 `SlotReleaseGuard` / `SlotGuardBody` |
| 队列满 | 返回/换号前不消耗 RPM |
| 槽位等待超时 | 返回/换号前不消耗 RPM |
| 非粘性 RPM 饱和 | 释放已获槽位，排除账号并重新选号 |
| 粘性 RPM 饱和 | 保持粘性账号等待；超时后返回本地 429 |

### 5. Good/Base/Bad Cases

- Good：请求 A 占满账号槽位，请求 B 在 FIFO 队列等待；B 等待期间 RPM 不变，A 释放后 B 获得槽位并通过 RPM admission 才递增。
- Base：`rpm_limit = 0` 时保持不限 RPM，槽位顺序仍由 `AccountQueue` 控制。
- Bad：在 `queue.acquire(...)` 前调用 `acquire_account_rpm(...)`，会让排队中或最终超时/队列满的请求提前消耗 RPM。

### 6. Tests Required

- 覆盖等待中请求不增加 `get_account_rpm_status(...).current`。
- 覆盖等待请求获得槽位并通过 RPM admission 后才递增。
- 覆盖 `QueueFull` 和 `Timeout` 不消耗 RPM。
- 保留非粘性 RPM 饱和换号、粘性 RPM 饱和等待/拒绝、429 后释放槽位的回归测试。

### 7. Wrong vs Correct

#### Wrong

```rust
account_svc.acquire_account_rpm(&account, sticky, &session_hash).await?;
let permit = queue.acquire(SLOT_WAIT_TIMEOUT).await?;
```

#### Correct

```rust
let permit = queue.acquire(SLOT_WAIT_TIMEOUT).await?;
account_svc.acquire_account_rpm(&account, sticky, &session_hash).await?;
```

## Scenario: OAuth Usage Scoped 模型窗口

### 1. Scope / Trigger

- Trigger：修改 `service::oauth::fetch_usage`、`AccountService::refresh_usage`、`UsagePollerService`、`web/src/api.ts`、`Accounts.vue` 中 OAuth usage 解析或展示时适用。
- 背景：Claude Code 新版 usage API 可能把模型专属周用量放在 `limits[]` 的 scoped 结构里，而不是顶层 `seven_day_<model>` 字段。

### 2. Signatures

- 上游接口：`GET https://api.anthropic.com/api/oauth/usage`
- 后端入口：`service::oauth::fetch_usage(token, proxy_url).await -> Result<serde_json::Value, AppError>`
- 账号刷新：`AccountService::refresh_usage(id).await -> Result<serde_json::Value, AppError>`
- 管理端接口：`POST /admin/accounts/:id/usage -> { status: "ok", usage }`
- 前端类型：`UsageData` 包含 `five_hour`、`seven_day`、`seven_day_sonnet`、`seven_day_fable`、`limits`

### 3. Contracts

- `five_hour` / `seven_day` / `seven_day_sonnet` 仍按顶层窗口读取，窗口最少包含 `utilization`，`resets_at` 可为空。
- Fable 周用量必须稳定暴露为 `seven_day_fable`；若上游没有顶层 `seven_day_fable`，从 `limits[]` 中匹配：
  - `kind == "weekly_scoped"` 或 `group == "weekly"`
  - `scope.model.display_name == "Fable"`，或 `scope.model.id` 包含 `fable`
  - `percent` 写入 `utilization`
  - `resets_at` 为字符串时保留，否则写 `null`
- 后端归一化只能补稳定字段，不得删除 `limits`、`spend`、`extra_usage` 等原始字段，方便排查上游变化。
- 前端展示应优先读取稳定字段；为了兼容旧缓存，也可从 `usage_data.limits` 回退提取 Fable。

### 4. Validation & Error Matrix

| 条件 | 期望行为 |
|------|----------|
| `limits` 缺失或不是数组 | 不补 `seven_day_fable`，保留原始 usage |
| `limits` 前置项 `scope: null` | 跳过该项，继续查找后续 scoped 项 |
| Fable scoped 项 `percent` 非数字 | 不补窗口，避免 UI 展示脏值 |
| Fable scoped 项 `resets_at: null` | 窗口保留 `resets_at: null`，前端显示 `—` |
| 顶层已有 `seven_day_fable` 对象 | 保留顶层对象，不用 `limits` 覆盖 |
| 上游返回 401/403/429 | 维持现有 `AppError` 分类，不吞错误体 |

### 5. Good/Base/Bad Cases

- Good：usage 先返回 session/weekly all 两个 `scope: null` limit，后返回 Fable scoped limit；解析器跳过前两项并补出 `seven_day_fable`。
- Base：只返回传统 `five_hour` / `seven_day`；UI 继续显示基础用量，Fable 为 0 或空状态。
- Bad：直接假设 `limits[0]` 就是 Fable，或遇到第一个 `scope: null` 用 `?` 提前返回，导致真实 Fable 项被漏掉。

### 6. Tests Required

- `service::oauth` 单测覆盖：前置 `scope: null` 项、Fable scoped 项、已有顶层 `seven_day_fable` 不覆盖、非 Fable scoped 项忽略。
- `cc2api/web` 构建必须通过 `npm run build`，确保 `UsageData` 类型与 `Accounts.vue` 展示同步。
- 改动 `fetch_usage` 后至少跑 `cargo test`，确认账号调度和 usage 相关共享测试不回归。

### 7. Wrong vs Correct

#### Wrong

```rust
let model = item.get("scope")?.get("model")?;
```

#### Correct

```rust
let Some(model) = item.get("scope").and_then(|scope| scope.get("model")) else {
    continue;
};
```

## 设置热刷新模式

新增全局 setting 通常要经过这些位置：

```text
src/store/settings_store.rs     默认值常量
src/store/db.rs                 首次插入默认值 / 旧值迁移
src/handler/router.rs           GET/PUT 校验与 reload 调用
src/service/gateway.rs          RwLock 缓存、reload_* 方法、热路径读取
web/src/api.ts                  前端类型或字段
web/src/components/Settings.vue 控件和文案
```

不要只在 `settings_store.rs` 加常量。漏掉 reload 会导致 UI 写入后服务仍用旧值；漏掉 migration 会导致老实例没有默认值。

## 后台任务边界

- `UsagePollerService` 负责 OAuth usage 主动刷新，不应写网关热路径状态。
- `PrimePollerService` 负责峰值预热调度，发出的请求也可能命中网关治理规则；新增拦截规则时必须说明是否影响预热。
- Telemetry 自动代发必须遵守隐私边界，不发送 prompt、tool input、响应正文、token 或 cookie。

## Common Mistakes

| 反模式 | 风险 | 正确做法 |
|--------|------|----------|
| 在 handler 里直接拼 SQL 或写调度逻辑 | 路由层膨胀，测试困难 | 放进 service/store |
| 新 setting 只改默认常量 | 老 DB、UI、热缓存不同步 | 按 settings 热刷新模式全链路更新 |
| 网关读 body 后继续转发原 request | 上游收到空 body 或旧 body | 明确重建 request body |
| 粘性会话遇到限流直接换号 | Claude Code prompt cache 被破坏 | 粘性请求等待或本地返回 |
| CCH 之前/之后插入 body 改写顺序不清 | 请求签名不匹配真实客户端 | 所有 body 改写先完成，再统一算 CCH |
