# 下游 Session 首次 Hello 代理探测 - 实施计划

## 1. CacheStore 状态契约

1. 在 `src/store/cache.rs` 定义探测状态枚举和专用读写接口，所有新增 public 类型/方法补齐中文文档。
2. 在 `src/store/memory.rs` 实现状态 TTL、成功滑动续期与失败固定冷却。
3. 在 `src/store/redis.rs` 使用原子命令/Lua 实现等价语义，复用现有 owner lock 保证跨实例 singleflight。
4. 补 Memory/Redis 定向测试：并发 leader/follower、TTL、失败冷却、锁过期恢复。

## 2. Probe Service

1. 新增 `src/service/session_hello_probe.rs` 与 module 导出。
2. 实现配置结构、稳定状态 key、精确 HEAD request builder、超时和结果分类。
3. 使用 `tlsfp::get_request_client(account.proxy_url)`，确保空代理直连且请求不含凭据。
4. 实现 cache 命中、singleflight leader/follower、严格/非严格 decision 和脱敏日志。
5. 使用测试 endpoint/client fixture 覆盖 HTTP 200、非 200、超时、代理与 cache 异常。

## 3. Gateway 热路径

1. 在 `GatewayService` 注入 probe service 与热配置，更新 main/router/test assembly。
2. 启动时加载 probe settings，增加 `reload_session_hello_probe_config()`。
3. 在真实 Claude Code `/v1/messages` admission 后、改写/token/转发前调用 `ensure_ready`。
4. 严格失败构造 Anthropic-compatible 502/503/504；非严格失败继续现有链路。
5. 保持公开 `/api/hello`、count tokens、本地拦截、RPM 次数、sticky 绑定与 telemetry 语义不变。

## 4. Settings 后端

1. 在 `settings_store.rs` 增加五个默认常量，功能/严格模式默认 `false`。
2. 在 `db.rs` 默认 settings 插入缺失键，不覆盖现有值。
3. 在 `/admin/settings` GET 补默认值；PUT 校验布尔与数值范围，持久化后热加载 probe config。
4. 补默认值、非法范围、保存后热加载的 router/store 测试。

## 5. Settings 前端

1. 在 `web/src/components/Settings.vue` 增加独立设置区。
2. 使用两个 toggle 和三个 number input，功能关闭时禁用从属控件但保留值。
3. load/save 使用五个真实 setting key；前端范围校验与后端一致。
4. 保持现有紧凑运维后台布局，不新增页面或嵌套卡片。

## 6. 集成验证

1. `cargo fmt --check`。
2. `cargo test`，重点检查 gateway、cache、settings、proxy/tlsfp 和现有 sticky/RPM 回归。
3. Redis 可用时运行跨实例/原子状态定向测试。
4. `cd web && npm run build`。
5. `git diff --check`，静态扫描不得出现完整 proxy URL、session id 或凭据日志。

## 7. 上线与回滚

1. 发布镜像并 recreate cc2api。
2. 默认功能关闭完成健康检查。
3. 在目标环境只开启 `session_hello_probe_enabled`，严格模式保持关闭；验证首个 session/account 产生一次探测、后续多轮只命中 cache。
4. 观察首请求延迟与失败日志；异常时直接关闭功能热回滚。

## 风险与回滚点

- CacheStore/Redis 原子语义错误可能重复探测或永久等待，必须先完成 store 定向测试再接 Gateway。
- 探测位于账号 slot 生命周期内，最大增加 5 秒首请求占槽；默认关闭并允许热回滚。
- 严格模式会把代理或 Anthropic hello 故障转化为用户请求失败，只允许管理员显式开启。
- 公开 `/api/hello` 与 new-api 边界不得随实现改变。
