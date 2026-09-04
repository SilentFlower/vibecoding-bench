# Fable 5.1 线上兼容与限制审计

## 结论

`claude-fable-5` 与 `claude-fable-5-1` 必须作为两个模型 ID 分别建模；当前代码只有
少数 family-prefix 分支天然覆盖 5.1，大部分请求改写、system role 和配额逻辑仍只
精确识别 Fable 5。

线上 gateway 当前仍使用 2.1.220 profile，允许版本范围为 `2.1.89-2.1.220`。
所以 Claude Code 2.1.257 请求目前首先会被版本访问策略拒绝；即使放开版本，Fable
5.1 主请求随后仍会因 system role 白名单缺失而被本地 400 拒绝。

## 已覆盖 5.1 的逻辑

| 位置 | 当前规则 | 5.1 结果 | 说明 |
| --- | --- | --- | --- |
| bootstrap query | `starts_with("claude-fable-5")` | 已覆盖 | 5.1 查询会走 Fable cwk 分支，但当前 2.1.220 profile 的 key 仍是旧 `marigold` |
| bootstrap hide | `starts_with("claude-fable-")` | 已覆盖 | `hide_fable` 会同时隐藏 Fable 5 与 5.1，符合 family 级开关语义 |
| 1M allowlist 匹配 | 大小写不敏感的子串匹配 | 可覆盖 | 配置为 `fable` 时两个模型都命中；精确配置旧 ID 时 5.1 不命中 |
| OAuth usage 数据 | `seven_day_fable` / display name `Fable` | family 共用 | 上游只提供 Fable family 周窗口，不区分 5 与 5.1 |

## 未覆盖 5.1 的逻辑

### 请求画像和改写

`rewriter.rs:104,243-286` 的 `FABLE_MODEL_ID` 精确等于 `claude-fable-5`。
Fable 5.1 因此被当成普通非 Fable 模型：

- Claude Code 原生请求会先放入通用 message beta，再追加客户端 beta，导致
  `redact-thinking` 等多余 token、旧/新 `server-side-fallback` 同时存在且顺序错误；
- API mimicry 缺省 `max_tokens` 会取 32000，而真实 Fable 5.1 为 64000；
- API mimicry 不会补 `fallbacks: "default"`；
- API mimicry 不会走 Fable body order；
- 当前 `ensure_fable_fallbacks` 只支持 Fable 5 的 fallback 数组，不能直接复用于
  Fable 5.1 的字符串 `"default"`。

### system role 白名单

`gateway.rs:5064-5066` 对配置列表做精确模型 ID 匹配。线上实际值为：

```text
claude-opus-5,claude-fable-5,claude-opus-4-8,claude-sonnet-5
```

新抓包的每条 Fable 5.1 主请求都含 `messages[].role=system`，因此当前线上配置放开
2.1.257 后仍会在请求上游前返回 `system_role_model_not_allowed`。升级迁移必须追加
`claude-fable-5-1`，同时保留线上自定义的 `claude-sonnet-5`。

### Fable 周用量保护和模型级 429

`account.rs:2196-2199` 只接受：

- 精确 `claude-fable-5`；
- `claude-fable-5[...]` 后缀。

`claude-fable-5-1` 不满足这两个条件。虽然线上
`fable_sticky_quota_fallback_enabled=true`、控制线为 50%，5.1 当前仍会：

- 绕过 sticky account 的 Fable 周用量切换；
- 绕过新会话候选账号的 Fable 周用量过滤；
- 收到无法归类的 429 时不走 Fable 模型级换号分支。

两个模型 ID 应分别识别，但继续共用上游唯一的 `seven_day_fable` family 配额窗口。

### assistant prefill 拦截

线上拦截已开启，模型列表为：

```text
claude-fable-5,claude-opus-5,claude-opus-4-8,claude-opus-4-7
```

匹配方式为精确模型 ID，因此不包含 5.1。当前 Fable 5.1 抓包没有 assistant
prefill 请求，不能从样本证明 5.1 是否需要这项兼容；它不是本次
`No response from API` 的原因。

### disabled thinking 改写

线上改写已开启，模型列表为：

```text
claude-fable-5,claude-opus-5
```

5.1 不命中，但这不应被简单视为漏配。真实 Fable 5.1 主请求使用
`thinking={"type":"adaptive","display":"updates"}`，不需要旧 Fable 5 的
disabled-to-adaptive 修复。两个模型应保持不同规则。

### bootstrap configured 兜底

线上 `bootstrap_model_options_mode=passthrough`，因此当前没有改写影响；但数据库中的
configured 兜底仍是 `claude-fable-5[1m]`。2.1.257 profile 应使用抓包中的
`claude-fable-5-1[1m]`、`cwk_cfg_key=sorrel` 和新 cedar 数据，同时保留 2.1.220
回滚 profile 的 Fable 5 配置。

## 线上 1M 限制

线上 4 个账号的 `allow_1m_models` 均为：

```text
opus,claude-sonnet-5
```

因此 Fable 5 和 Fable 5.1 当前都会被剥离 `context-1m-2025-08-07`。这与线上
bootstrap 透传可能广告 `claude-fable-5-1[1m]` 存在能力展示差异。若要开放 Fable
1M，可在账号级 allowlist 中加入 `fable`，该子串会同时覆盖两个模型；是否自动迁移
属于独立产品策略，不能由抓包推断。

## 流式超时配置

线上配置为：

```text
stream_keepalive_enabled=true
stream_keepalive_interval_secs=45
stream_upstream_idle_timeout_secs=120
```

`stable_upstream_stream` 在收到第一个上游 chunk 之前不会注入 keepalive，并会在 120
秒无 chunk 后关闭流。新抓包的 Fable 5.1 失败请求收到 200 headers 后连续约 180.7
秒没有任何 SSE 字节，所以同类故障通过线上 gateway 时会更早在 120 秒被截断。

这属于上游首字节卡死的保护与可观测性问题，不应通过放宽 CCH、修改 beta 或无限增加
idle timeout 掩盖。
