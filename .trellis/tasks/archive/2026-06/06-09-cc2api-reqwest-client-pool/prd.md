# brainstorm: cc2api reqwest Client 池化

## Goal

在 `/root/project/cc2api` 中复用带 TLS 指纹和代理配置的 `reqwest::Client`，避免每次上游请求都重新创建客户端，从而减少代理握手、TLS 握手和连接建立开销，改善连接速度与首字节延迟。

## Background / Known Context

- 线上 `cc2api` 最近首字节延迟偏高，排查中看到部分请求存在明显连接/上游响应耗时。
- 当前代码的 `crate::tlsfp::make_request_client(proxy_url)` 每次调用都会构建新的 `reqwest::Client`。
- `make_request_client` 目前被主网关转发、OAuth token 测试/刷新、usage 拉取、OAuth code exchange、prime poller、telemetry loop 使用。
- `reqwest::Client` 本身是可 clone、内部连接池化的长期对象；重复新建会丢失连接复用收益。
- 数据库已经使用 `sqlx::AnyPool`，Redis 已使用 `redis::aio::ConnectionManager`，本次不需要再引入 DB/Redis 连接池改造。
- 用户已将代理配置从 `socks5://` 改为 `socks5h://`，本任务不处理代理 scheme 迁移。
- 追加需求：纯瞬时上游 429 不应写数据库冷却或停用账号，应做进程内账号级 soft backoff；同账号新请求在窗口内等待，且管理端展示等待数量。
- 追加需求：代理 Client 池化需要提供全局开关，默认开启；关闭时用于线上对比或快速排查连接复用问题。

## Requirements

- 按代理配置复用 HTTP 客户端：同一个 `proxy_url` 应复用同一个 `reqwest::Client`。
- 保持现有 TLS 指纹、根证书、connect timeout、tcp keepalive、`no_proxy` 和 SOCKS/HTTP 代理行为不变。
- 覆盖所有现有 `make_request_client` 调用路径，至少包括主网关请求、OAuth、usage、OAuth flow、prime poller、telemetry。
- 当代理配置变更时，新的 `proxy_url` 应自然生成新的客户端；旧客户端可留在缓存中随进程生命周期复用/淘汰，本任务不要求动态清理。
- 不引入 short/normal 队列、TTFB 路由权重、动态并发调节或 prompt cache 改动。
- 除账号列表追加 soft backoff 展示字段外，不改变 API 响应格式、错误映射、账号选择、RPM、槽位逻辑。
- 纯瞬时 429 的 soft backoff 必须发生在 RPM 预占和账号并发槽位获取之前，避免等待期间占用本地限流资源。
- 账号列表前端需要展示 soft backoff 等待中的请求数和剩余等待时间。
- 全局设置页需要提供代理连接池开关；默认开启，保存后应立即影响所有 `get_request_client(proxy_url)` 调用路径。
- 关闭代理连接池时，请求仍必须保留现有 TLS 指纹、代理、timeout、keepalive 等 builder 行为，但每次调用都新建 `reqwest::Client`，不复用缓存客户端。

## Acceptance Criteria

- [ ] 代码中高频上游请求路径不再直接每次新建 `reqwest::Client`。
- [ ] 相同 `proxy_url` 多次获取客户端时返回同一内部连接池的 clone。
- [ ] 不同 `proxy_url` 使用不同客户端，避免代理配置串用。
- [ ] 纯瞬时 429 触发账号级进程内 soft backoff，账号保持 Active 且不写 `rate_limit_reset_at`。
- [ ] 账号列表展示 soft backoff 等待请求数和剩余等待时间。
- [ ] 管理端设置页可开启/关闭代理连接池，默认开启。
- [ ] 关闭代理连接池后，`get_request_client(proxy_url)` 不读写缓存，并回退到每次新建客户端。
- [ ] `cargo test` 通过，至少新增或更新覆盖客户端缓存行为的单元测试。
- [ ] 现有 DB/Redis 连接池不被重复改造。

## Out of Scope

- short/normal fast lane。
- TTFB EWMA 路由。
- 账号动态并发调节。
- prompt cache 策略调整。
- 代理 URL 自动从 `socks5://` 改写为 `socks5h://`。
