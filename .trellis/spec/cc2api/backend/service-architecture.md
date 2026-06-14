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
