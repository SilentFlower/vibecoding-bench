# cc2api 非流单消息探针缓存设计

## Technical Design

### Scope

实现位置在 `/root/project/cc2api`：

* `src/store/settings_store.rs`：新增默认设置常量。
* `src/store/db.rs`：迁移默认设置。
* `src/handler/router.rs`：Settings API 默认值、校验、热刷新。
* `src/service/gateway.rs`：缓存配置、探针识别、缓存读写、日志、命中返回。
* `web/src/components/Settings.vue`：Settings 页面全局开关。

### Data Flow

1. `/v1/messages` 请求进入网关后解析 body 并识别客户端类型。
2. 账号选择、RPM、槽位、请求改写、header 改写和 token 解析仍按现有顺序执行。
3. 在准备转发上游前，对最终请求形态判断是否符合“非流单消息探针缓存”条件。
4. 若开关关闭或条件不匹配，继续现有上游转发。
5. 若开关开启且 key 命中未过期缓存，记录 `non_stream_probe_cache_hit` 并直接返回缓存响应。
6. 若未命中，继续请求上游；成功返回非流 JSON message 后记录 `non_stream_probe_cache_create` 并写入进程内缓存。

### Probe Matching

MVP 使用白名单式文本特征，避免误缓存用户真实 prompt：

* 精确文本 `count`
* `# Session-specific guidance`
* `# Context management`
* `# Memory`
* `# Environment`
* `This is the git status at the start of the conversation`
* `When you have enough information to act, act.`
* `trellis-` 且包含 `skill`
* `You are an interactive agent that helps users with software engineering tasks`
* `For actions that are hard to reverse or outward-facing`
* `AI-HUB-GUIDE-LANGUAGE` 或 `Always reply in Chinese`
* `Write code that reads like the surrounding code`

未命中文本特征的 `max_tokens=1` 请求继续请求上游，不进入缓存。

### Cache Key

缓存 key 使用 SHA-256，输入为规范 JSON：

* `path`
* `model`
* 最终上游请求 body 字节的 SHA-256
* 关键 header：`anthropic-version`、`anthropic-beta`、`x-app`、`User-Agent`、`X-Stainless-*`、`x-anthropic-billing-header`
* gateway 侧会影响请求语义的配置版本可以先用当前设置值拼入 key，例如 `message_cache_control_rewrite`、`cache_control_ttl_rewrite`

日志只输出 `cache_key_hash` 前 12 或 16 位，不输出 key 原文。

### Cache Value

缓存值保存：

* 响应状态码
* 响应 header 中安全且必要的字段，例如 `content-type`
* 响应 body JSON
* 创建时间与过期时间
* `probe_type`、`model`、`account_id`

命中返回前可在响应 body 中重写 `id` 为 `msg_cached_probe_<hash>_<timestamp>`，保留 content、stop_reason、usage 等字段，减少客户端把重复 id 当成同一响应的风险。

### Logs

创建日志：

```text
non_stream_probe_cache_create {"cache_key_hash":"...","probe_type":"count","model":"claude-opus-4-8","account_id":13,"ttl_secs":1800,"body_bytes":123,"status":200,"expires_at":"..."}
```

命中日志：

```text
non_stream_probe_cache_hit {"cache_key_hash":"...","probe_type":"count","model":"claude-opus-4-8","account_id":13,"age_secs":42,"expires_in_secs":1758}
```

### Concurrency

使用 `tokio::sync::RwLock<HashMap<String, CachedProbeResponse>>` 存储进程内缓存。MVP 不做 singleflight；并发首次 miss 时允许多个请求同时上游，后续命中即可。必要时后续任务再加 per-key in-flight 去重。

### Rollout / Rollback

* 默认关闭，部署后无行为变化。
* 开启后仅影响强特征 `max_tokens=1` 单消息 Claude Code 非流探针。
* 如出现异常，关闭 `non_stream_probe_cache_enabled` 即回退到现有上游转发。

## Tradeoffs

* 选择精确缓存而非本地 mock：保留上游真实响应形态，风险较低。
* 选择进程内缓存而非持久化：实现简单，足够覆盖启动阶段短时间重复请求；重启丢失可接受。
* 选择固定 30 分钟 TTL：满足当前需求，减少额外设置复杂度。
