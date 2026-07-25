# 新增有效上游 Session 首次 Hello 代理探测

## Goal

当新的有效上游 Claude Code session 首次真正进入 cc2api 上游转发链路时，先通过最终选中账号的 `proxy_url` 模拟 Claude Code 2.1.220，向 `https://api.anthropic.com/api/hello` 发送匿名 `HEAD` 探测；多个真实下游 session 复用同一上游 session 时不重复探测，从而在首个业务请求前验证该账号代理到 Anthropic 的基础连通性。

## Background

- Claude Code 2.1.220 的真实启动请求是匿名 `HEAD https://api.anthropic.com/api/hello`，无 query、无 body、无 Authorization；wire headers 为 `User-Agent: Bun/1.4.0`、`Accept: */*`、`Accept-Encoding: gzip, deflate, br, zstd`、`Connection: keep-alive`。
- Claude Code 当前把 hello 固定发往官方域名，不使用 `ANTHROPIC_BASE_URL`，所以 `Claude Code -> new-api -> cc2api` 链路不会自然携带该请求。
- cc2api 已能从 Claude Code `/v1/messages` 的 `metadata.user_id.session_id` 提取真实下游 session，并在账号选择、并发槽位和 RPM admission 后确定真正承载请求的账号。
- cc2api 的 `tlsfp::get_request_client(account.proxy_url)` 已用于 telemetry、OAuth 和 usage 等账号代理请求，可复用同一代理/TLS client 构造方式。
- 公开的 `GET/HEAD /api/hello` 是本地静态健康端点，不选择账号，也不经过账号代理；本任务不得改变该路由语义。

## Requirements

1. 仅对具有稳定真实 session id、且即将真实转发到上游的 Claude Code `/v1/messages` 请求触发；先按最终账号解析上游 session 池，“首次”定义为该有效上游 session 首次承载业务请求。上游 session 池关闭或解析失败时回退真实下游 session。本地拦截、公开 `/api/hello`、event logging、count tokens 和普通 API 客户端不应误创建探测状态。
2. 探测必须在最终账号确定后执行，并使用该账号的 `proxy_url`；账号未配置代理时仍直连发送。不得携带账号 token、OAuth Authorization、API key、billing header、Cookie、请求正文或用户数据。
3. 探测请求必须模拟 2.1.220 抓包：`HEAD https://api.anthropic.com/api/hello`，无 query/body，使用 `Bun/1.4.0` 与对应 Accept/Encoding headers。默认总超时 5 秒，设置范围 `1..=30` 秒；只有 HTTP 200 视为成功，响应 body 和 Content-Length 不参与成功判定。
4. 去重维度使用“有效上游 session + 最终账号 + 账号代理指纹”，内部 key 只保存上游 session 与 `proxy_url` 的稳定 SHA-256 摘要，不记录完整 session id 或代理地址；多个真实下游 session 映射到同一上游 session 时共享结果，同一真实 session 切换账号、上游映射或账号代理后必须对新的实际网络路径重新探测。
5. 同一去重键的并发首请求必须 singleflight：最多一个执行网络探测，其余等待相同结果；MemoryStore 与 RedisStore 语义一致，多实例 Redis 部署不得重复放大探测。
6. 成功标记使用 60 分钟滑动空闲 TTL：同一活跃上游 session/account 的后续业务请求只续期、不重复发 hello；连续无请求超过 60 分钟后才允许重新探测，避免永久增长。
7. 失败或超时不得写成功标记。失败开放模式写 5 分钟失败冷却状态，冷却期内继续业务请求但不每轮重复探测；冷却到期后再尝试。严格模式复用同一失败结果/冷却，冷却期内直接阻断而不放大请求。
8. 探测不得执行额外的账号 RPM admission，不产生 Anthropic 业务 usage 或自动 telemetry；触发它的业务请求仍只按现有流程计一次 RPM。日志只记录账号 id、下游/上游短 session hash、代理是否配置、耗时、HTTP 状态和结果，不得输出完整 session、proxy URL 或响应正文。
9. 在现有系统 Settings 页面增加独立的“Session 首次 Hello 代理探测”设置区，setting keys 固定为 `session_hello_probe_enabled`、`session_hello_probe_strict`、`session_hello_probe_timeout_secs`、`session_hello_probe_success_ttl_secs`、`session_hello_probe_failure_cooldown_secs`；管理 API、启动默认值、热加载及精确迁移策略必须同步。
10. 功能总开关默认关闭，严格模式默认关闭。功能开启且严格模式关闭时，探测失败或超时记录脱敏日志并继续当前业务请求，日志级别允许使用 `info`；开启严格模式后，普通探测失败返回 `502`、缓存或 singleflight 无法保证去重时返回 `503`、探测超时返回 `504`，且不发送当前业务请求。
11. 公开 `/api/hello` 继续本地返回固定响应，不得改成通用 relay，也不得由 new-api 选择渠道。

## Acceptance Criteria

- [ ] 新有效上游 session 的首个真实 `/v1/messages` 在业务上游请求前，通过最终账号代理发送一次符合抓包的匿名 HEAD；多个下游 session 复用同一上游 session 时不重复。
- [ ] 两个并发首请求只产生一个 hello 网络请求，并共享成功或失败结果；MemoryStore 与 RedisStore 均有覆盖。
- [ ] 同一活跃上游 session/account 的多轮对话只续期成功状态、不重复探测；空闲超过 TTL 后可重新探测，状态不会无限增长。
- [ ] 同一真实 session 从账号 A retry 到账号 B 时，B 解析自己的有效上游 session，并在承载业务请求前完成代理探测。
- [ ] 上游 session 池关闭或解析失败时回退真实下游 session，保持每个真实 session 独立探测。
- [ ] 探测请求不含 Authorization、Cookie、billing header、body 或用户数据，不执行额外 RPM admission、不让业务请求比现有流程多计一次 RPM，也不生成业务 telemetry。
- [ ] 本地拦截、event logging、count tokens、普通 API 请求和公开 `/api/hello` 不触发账号代理探测。
- [ ] 账号 `proxy_url` 为空时仍直连执行探测；配置代理时请求确实经过对应账号代理。
- [ ] 成功结果使用 60 分钟滑动空闲 TTL；失败不写成功标记并进入 5 分钟冷却，冷却后可重试。
- [ ] Settings 页面可独立切换功能和严格模式，并可调整超时/TTL；前后端校验一致且保存后热加载。
- [ ] 严格模式默认关闭：失败开放且继续业务请求；开启后失败阻断且不发送业务请求，两种模式均不写失败成功标记。
- [ ] 失败开放模式在失败冷却期内不会每轮重复探测；冷却到期后允许重试。
- [ ] 默认超时为 5 秒且只接受 HTTP 200；设置页与后端拒绝 `1..=30` 秒之外的值。
- [ ] `cargo fmt --check`、`cargo test`、Redis 相关验证和 `web npm run build` 通过。

## Out Of Scope

- 不拦截或改写 Claude Code 自己直连 `api.anthropic.com` 的启动 hello。
- 不把 hello 扩展成带账号凭据的 Anthropic 鉴权检查。
- 不用探测结果永久禁用账号；账号健康降级和自动摘除另立机制。
- 不修改 new-api 的渠道选择或增加 `/api/hello` 透传路由。
