# cc2api reqwest Client 池化实现计划

## Implementation Checklist

- [ ] 在 `src/tlsfp/tlsfp.rs` 新增进程级客户端缓存 API。
- [ ] 添加单元测试验证相同 `proxy_url` 复用、不同 `proxy_url` 隔离。
- [ ] 将主网关、OAuth、usage、OAuth flow、prime poller、telemetry 的调用点切到缓存 API。
- [ ] 增加 `proxy_client_pool_enabled` 全局设置，默认开启，并在启动和设置保存后同步到 `tlsfp` 运行时开关。
- [ ] 在设置页增加代理连接池开关，关闭时 `get_request_client(proxy_url)` 回退到每次新建客户端。
- [ ] 将纯瞬时 429 改为账号级进程内 soft backoff，不写数据库冷却。
- [ ] 在账号列表 API 和前端账号卡展示 soft backoff 等待数量与剩余时间。
- [ ] 运行格式化与测试。

## Validation

- `cargo fmt --check`
- `cargo test`
- `npm --prefix web run build`

## Review Gates

- 开始实现前确认 PRD/design/implement 范围。
- 检查不引入 short/normal 队列、动态并发、路由权重等额外行为。
