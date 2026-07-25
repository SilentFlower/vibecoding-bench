# 下游 Session 首次 Hello 代理探测 - 任务简报

## 目标

为 cc2api 增加可选的 Session 首次 Hello 代理探测：新的 Claude Code session 首次真正进入 `/v1/messages` 上游转发链路时，先通过最终选中账号的 `proxy_url` 匿名请求 `HEAD https://api.anthropic.com/api/hello`，验证该账号实际网络路径；同一活跃 session 后续对话不重复探测。

## 范围

- 仅处理能从 `metadata.user_id.session_id` 或受支持旧格式取得稳定真实 session id 的 Claude Code `/v1/messages`。
- 探测在账号选择以及本轮并发槽位、RPM admission 完成后，在请求改写、token 解析、sticky 绑定和业务上游转发前执行。
- 请求固定模拟 Claude Code 2.1.220：匿名 `HEAD`、`User-Agent: Bun/1.4.0`、`Accept: */*`、`Accept-Encoding: gzip, deflate, br, zstd`、`Connection: keep-alive`，无 query、body、凭据和用户数据；仅 HTTP 200 成功。
- 使用账号 `proxy_url`，代理为空时直连。状态键包含账号 id、session SHA-256 和 proxy URL SHA-256，账号或代理变化后重新探测。
- MemoryStore 与 RedisStore 都实现状态 TTL 和 singleflight；Redis 需要支持跨实例去重。
- 成功状态使用 60 分钟滑动空闲 TTL；失败或超时使用 5 分钟固定冷却；默认探测超时 5 秒，可配置范围 `1..=30` 秒。
- Settings 增加功能开关、严格模式、超时、成功 TTL、失败冷却五项全局设置，并支持保存后热加载。功能和严格模式默认关闭。

## 失败语义

- 非严格模式：探测失败或超时记录脱敏日志并继续当前业务请求，日志级别允许使用 `info`；缓存或 singleflight 不可用继续记录 `warn`。
- 严格模式：普通探测失败返回 `502`，缓存或 singleflight 无法保证去重时返回 `503`，探测超时返回 `504`；当前业务请求不发送上游。
- 探测不执行额外 RPM admission，不产生业务 usage 或自动 telemetry；触发探测的业务请求仍沿用现有 RPM 计数流程。

## 不处理

- 不拦截或改写 Claude Code 自己直连官方域名的启动 hello。
- 不修改公开 `GET/HEAD /api/hello` 的本地健康端点语义。
- 不修改 new-api 渠道选择，也不增加 new-api 的 `/api/hello` 透传。
- 不携带账号凭据做鉴权检查，不根据结果永久禁用账号。
- count tokens、event logging、本地拦截和普通 API 客户端不触发探测。

## 实现重点

- 新增独立 `SessionHelloProbeService`，避免继续扩大 Gateway 热路径职责。
- Gateway 只在真实业务路径满足触发条件后调用服务；账号 retry 切换后，新账号在承载业务请求前也需要自己的探测结果。
- 读取成功状态时原子续期；失败状态不续期。leader 执行网络请求，follower 等待并复用结果，锁过期后允许恢复竞争。
- 日志只允许账号 id、短 session hash、是否配置代理、来源、耗时、HTTP 状态和结果类别，不记录完整 session、代理地址、请求体、响应体或凭据。
- 旧数据库只补缺失默认 setting，不覆盖管理员已有值；关闭功能即可热回滚，缓存状态自然过期。

## 验收重点

- 首个真实请求通过最终账号代理发出一次精确匿名 HEAD；活跃 session 多轮不重复，并发首请求只发一次。
- 账号切换或代理变更后重新探测；空代理时直连。
- 成功滑动 TTL、失败固定冷却、超时和严格/非严格状态码符合设计。
- Settings 五项配置前后端校验一致、保存后热加载，默认升级行为不变。
- 本地拦截、公开 hello、RPM、sticky、telemetry 和现有业务转发语义无回归。
- `cargo fmt --check`、`cargo test`、Redis 定向验证、`web npm run build` 和 `git diff --check` 通过。

## 下一步

用户确认本简报后，将任务状态切换为 `in_progress`，按 `implement.md` 依次完成 CacheStore、探测服务、Gateway、Settings 后端与前端，并进入统一质量检查。
