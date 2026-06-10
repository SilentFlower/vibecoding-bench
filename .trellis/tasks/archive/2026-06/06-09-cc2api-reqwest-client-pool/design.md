# cc2api reqwest Client 池化

## Technical Design

在 `src/tlsfp/tlsfp.rs` 内保留现有 `make_request_client(proxy_url)` 构建逻辑，并新增一个进程级客户端缓存入口，例如 `get_request_client(proxy_url) -> reqwest::Client`。

缓存 key 使用完整 `proxy_url` 字符串。空字符串代表直连客户端。这样可以保证相同代理复用连接池，不同代理不会共享连接。

建议使用 `once_cell::sync::Lazy` 加 `std::sync::RwLock<HashMap<String, reqwest::Client>>`。`reqwest::Client` clone 成本低，返回 clone 即可复用内部连接池。

并发安全策略：

- 先读锁查缓存，命中则 clone 返回。
- 未命中时构建客户端，再写锁插入。
- 若多个并发请求同时 miss，最多会重复构建少量客户端；最终缓存只保留一个。这个成本只发生在代理首次出现时，可接受。

## Proxy Client Pool Switch

新增全局 settings key：`proxy_client_pool_enabled`，默认值为 `"true"`。

运行时开关放在 `tlsfp` 模块内，由进程级 `AtomicBool` 保存。`get_request_client(proxy_url)` 在入口处读取该开关：

- 开启：按 `proxy_url` 走 `REQUEST_CLIENT_CACHE`，返回缓存客户端 clone。
- 关闭：直接调用 `make_request_client(proxy_url)`，不读写缓存。

关闭开关时清空当前 `REQUEST_CLIENT_CACHE`，避免恢复开启前继续保留排查期间不想复用的旧连接池。启动时从 settings 加载该开关；`/admin/settings` 更新后立即写入进程级开关，使主网关、OAuth、usage、OAuth flow、prime poller、telemetry 等所有 `get_request_client` 调用路径同步生效。

前端设置页增加“代理连接池”开关，读写同一个 `proxy_client_pool_enabled` key。旧数据库缺少该 key 时，后端 `get_settings` 和启动读取都按默认开启处理。

调用点替换：

- 主网关 `GatewayService::forward_request`
- `TokenTester::test_token`
- `refresh_oauth_token`
- `fetch_usage`
- `OAuthFlowService::exchange_code_inner`
- `PrimePollerService`
- telemetry loop

不修改数据库/Redis：`sqlx::AnyPool` 和 `redis::aio::ConnectionManager` 已经是连接池/连接管理对象。

## 429 Soft Backoff

纯瞬时 429（无 `retry-after`、无 5h/7d 撞墙、非 long context / credit 类请求错误）不写数据库冷却。`AccountService` 维护进程内 `account_id -> { until, waiting }` 状态：

- `until` 使用 `tokio::time::Instant`，进程重启自然清空。
- `waiting` 统计正在等待 soft backoff 的请求数，供账号列表展示。
- 网关收到纯瞬时 429 后设置该账号 10 秒 soft backoff；同请求释放并发槽位后等待并重试。
- 新请求选中该账号后，在 RPM 预占和并发槽位获取前等待剩余时间，避免等待占用本地限流资源。
- 若同请求同账号等待后仍返回瞬时 429，刷新账号级 soft backoff，但该请求走原有换号逻辑，避免无限等待同一账号。

账号列表接口追加 `transient_backoff_waiting` 与 `transient_backoff_remaining_ms`，前端账号卡展示“429 等待”。

## Compatibility

缓存客户端必须继承现有 builder 配置：

- craftls TLS 指纹配置
- `connect_timeout(30s)`
- `tcp_keepalive(30s)`
- `no_proxy()`
- `reqwest::Proxy::all(proxy_url)`

旧函数可保留用于测试或低频路径，但生产调用应迁移到缓存入口。

## Rollout / Rollback

上线前跑 `cargo test`。上线后观察 `上游响应`、`首字到达`、连接失败、TTFB timeout 指标是否改善。

优先回滚方式是在设置页关闭代理连接池；如需代码级回滚，再恢复调用点为 `make_request_client(proxy_url)`。新增 settings key 有默认值，不涉及破坏性数据迁移。
