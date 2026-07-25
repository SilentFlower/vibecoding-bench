# 下游 Session 首次 Hello 代理探测 - 技术设计

## 1. 边界与数据流

该功能只挂接到 Claude Code `/v1/messages` 的真实上游路径。公开 `/api/hello`、管理 API、count tokens、event logging、普通 API 客户端和本地拦截响应保持原样。

执行顺序：

```text
读取请求并识别真实 session
  -> 账号选择
  -> 并发槽位与业务 RPM admission
  -> SessionHelloProbeService.ensure_ready(account, real_session_id)
  -> 请求体/header 改写与 token 解析
  -> sticky 绑定
  -> 业务请求转发
```

探测放在 admission 后，保证使用本轮准备承载请求的账号并受现有账号并发保护；探测本身不再执行额外 RPM admission。严格模式失败时，槽位 guard 正常释放，业务请求不发上游。

## 2. 设置契约

新增全局 settings：

| Key | 默认值 | 校验 |
| --- | --- | --- |
| `session_hello_probe_enabled` | `false` | `true` / `false` |
| `session_hello_probe_strict` | `false` | `true` / `false` |
| `session_hello_probe_timeout_secs` | `5` | `1..=30` |
| `session_hello_probe_success_ttl_secs` | `3600` | `60..=86400` |
| `session_hello_probe_failure_cooldown_secs` | `300` | `10..=3600` |

`GatewayService` 持有热缓存 `RwLock<SessionHelloProbeConfig>`，启动时从 `SettingsStore` 加载；`PUT /admin/settings` 校验成功并持久化后调用 `reload_session_hello_probe_config()`。旧数据库只插入缺失默认值，不覆盖管理员已有 setting。

Settings 页面在现有系统设置中增加独立区块：功能与严格模式使用 toggle，三个数值使用 number input。功能关闭时其余控件保留值但禁用编辑；严格模式默认关闭。

## 3. 探测服务

新增 `service/session_hello_probe.rs`，避免继续膨胀 Gateway 热路径。核心入口：

```rust
pub async fn ensure_ready(
    &self,
    account: &Account,
    real_session_id: &str,
    config: SessionHelloProbeConfig,
) -> SessionHelloProbeDecision
```

`SessionHelloProbeDecision` 区分：

- `Proceed`：功能关闭、成功缓存命中、探测成功，或非严格模式失败开放。
- `BlockTimeout`：严格模式下本次或缓存结果为超时，Gateway 返回 504。
- `BlockFailure`：严格模式下代理、网络或非 200 失败，Gateway 返回 502。

请求构造固定为：

```http
HEAD https://api.anthropic.com/api/hello
User-Agent: Bun/1.4.0
Accept: */*
Accept-Encoding: gzip, deflate, br, zstd
Connection: keep-alive
```

使用 `tlsfp::get_request_client(&account.proxy_url)`；空 `proxy_url` 直连。禁止添加 Authorization、Cookie、billing header、query 或 body。HTTP 200 为成功；超时单独分类，其余 reqwest 错误与非 200 均为普通失败。

## 4. 状态键与 singleflight

状态 key：

```text
session_hello_probe:v1:<account_id>:<sha256(real_session_id)>:<sha256(proxy_url)>
```

完整 session 与代理地址不得进入 Redis key、内存 key 或日志。代理配置变化会自然生成新 key并重新探测。

`CacheStore` 增加专用状态读写接口，状态只包含 `success`、`failure`、`timeout`：

- 读取 `success` 时原子续期 3600 秒，形成滑动空闲 TTL。
- `failure` / `timeout` 使用 300 秒固定冷却，不因后续请求续期。
- 状态不存在时复用现有 `acquire_lock/release_lock` 获取 `:lock` singleflight 锁；锁 TTL 为请求超时加安全余量。
- leader 执行网络请求并写结果；follower 短轮询同一状态，复用 leader 结果，不自行发送第二次请求。
- leader 异常退出时锁到期可恢复，不允许永久卡住。
- CacheStore 异常时：非严格模式记录告警并跳过探测；严格模式返回 503，避免无法保证去重时继续业务请求。

MemoryStore 用 mutex 保持状态与续期原子性；RedisStore 用 Lua 或等价原子命令实现读取成功并续期。Redis 部署跨进程去重；MemoryStore 仅保证单进程，服务重启后允许安全地重新探测一次。

## 5. Gateway 集成

Gateway 仅在以下条件全部满足时调用探测：

- path 为 `/v1/messages`；
- `ClientType::ClaudeCode`；
- 原始 body 能从 `metadata.user_id.session_id` 或受支持旧格式提取非空真实 session；
- 请求未被 assistant prefill、warmup、classifier、telemetry 或其他本地路径提前返回；
- 已选定账号并通过本轮 admission。

429/auth retry 切换账号时，新账号 id 形成新 key，业务请求在该账号上转发前必须重新走状态判断。探测成功不提前提交 sticky 绑定；sticky 仍在现有“真正准备发上游”位置写入。

## 6. 错误与日志

| 场景 | 非严格模式 | 严格模式 |
| --- | --- | --- |
| HTTP 200 | 写成功状态并继续 | 写成功状态并继续 |
| HTTP 非 200 / 代理错误 / 网络错误 | 写 5 分钟失败冷却、记录脱敏日志并继续 | 写失败冷却并返回 502 |
| 5 秒超时 | 写 5 分钟 timeout 冷却、记录脱敏日志并继续 | 写 timeout 冷却并返回 504 |
| cache 读写/锁失败 | 告警并继续，不发无去重探测 | 返回 503 |
| follower 等待 leader 无结果且锁到期 | 重新竞争一次或按失败处理 | 返回 503，不永久等待 |

日志字段限于 `account_id`、session 短 hash、`proxy_configured`、`source=network|cache|follower`、耗时、HTTP status、结果类别；成功、失败和超时结果允许统一使用 `info`，缓存不可用和 follower 等待超时继续使用 `warn`。不得输出完整 session、代理 URL、请求/响应 body 或任何凭据。

## 7. 兼容、上线与回滚

- 功能和严格模式默认关闭，升级后热路径无行为变化。
- 线上启用顺序：先开启功能并保持非严格，观察延迟/失败率；确认稳定后才考虑严格模式。
- 紧急回滚优先在 Settings 关闭功能，无需重启；代码回滚不需要 DB migration。
- 已写 cache 状态会自然 TTL 过期，关闭功能时不需要扫描或删除 Redis key。

## 8. 测试设计

- 请求构造测试断言 method、URL、headers、空 body、无 Authorization/Cookie/billing。
- MemoryStore 覆盖成功滑动 TTL、失败固定冷却、锁 owner、leader/follower、锁过期恢复。
- Redis 脚本覆盖并发 claim、成功续期、失败不续期和多实例只发一次。
- Probe service 使用本地 mock endpoint/proxy 覆盖直连、账号代理、200、非 200、超时和 cache 故障。
- Gateway 覆盖功能关闭、本地拦截不触发、同 session 多轮不重复、并发首轮、账号 retry 新 key、严格/非严格状态码、无额外 RPM admission。
- Router settings 覆盖默认值、范围校验和热加载；Vue 构建覆盖控件 load/save。
