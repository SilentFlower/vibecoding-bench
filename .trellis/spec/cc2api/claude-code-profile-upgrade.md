# Claude Code Profile Upgrade

> 记录 `cc2api` 升级 Claude Code 版本画像时必须执行的协议契约。目标是让未来从 `2.1.172` 升到新版本时，不再只改版本号而漏掉 CCH、`cc_version`、beta 顺序、bootstrap 和账号迁移。

---

## Scenario: Claude Code 版本画像升级

### 1. Scope / Trigger

- Trigger: 升级 `/root/project/cc2api` 的 Claude Code 默认版本、User-Agent、请求头、CCH、`cc_version`、bootstrap response、telemetry metadata 或账号默认画像。
- 必须使用真实抓包对比，不允许只根据代码常量推断协议。
- 本场景属于跨层契约：请求重写、header profile、body profile、telemetry、DB migration、Web settings 和远程部署都可能一起受影响。

### 2. Signatures

关键代码入口：

```text
src/service/version_profile.rs
src/service/rewriter.rs
src/service/telemetry.rs
src/service/gateway.rs
src/store/db.rs
src/store/settings_store.rs
web/src/components/Settings.vue
```

关键 wire 字段：

```text
User-Agent: claude-cli/<version> (external, cli)
User-Agent: claude-code/<version>
X-Stainless-Package-Version
X-Stainless-Runtime
X-Stainless-Runtime-Version
X-Stainless-Timeout
anthropic-version
anthropic-beta
x-app
x-anthropic-billing-header: cc_version=<version>.<suffix>; cc_entrypoint=cli; cch=<5hex>;
```

关键 DB 字段：

```sql
accounts.canonical_env.version
accounts.canonical_env.version_base
accounts.canonical_env.build_time
settings.allowed_claude_code_versions
```

抓包目录约定：

```text
data/flows/<account>/<topic_id>/<run_id>/
├── capture_index.json
├── http_capture.jsonl
├── stats.jsonl
└── *.flow
```

### 3. Contracts

版本画像必须集中维护：

- `DEFAULT_CLAUDE_CODE_VERSION`
- `DEFAULT_CLAUDE_CODE_VERSION_BASE`
- `DEFAULT_CLAUDE_CODE_BUILD_TIME`
- `claude_cli_user_agent(version)`
- `claude_code_user_agent(version)`
- `DEFAULT_ALLOWED_CLAUDE_CODE_VERSIONS_SETTING`

`cc_version` 后缀契约：

- 算法：`sha256("59cf53e54c78" + text[4] + text[7] + text[20] + version).hex()[0:3]`。
- 字符索引必须按 JavaScript UTF-16 code unit 语义。
- `messages[0].content` 是数组时，Claude Code 主请求可能先放环境上下文 text block，再放真实用户 prompt text block；后缀文本源应取首条 user message 的最后一个 text block，而不是第一个 text block。
- Haiku/title 这类只有一个 text block 的请求仍取唯一 text block。

CCH 契约：

- seed 不是默认可变项；升级时先用旧 seed 复算，不命中再尝试找 seed。
- `2.1.156` / `2.1.169` / `2.1.172` seed 均为 `0x4D659218E32A3268`。
- `2.1.169`：在最终 body 字节上把真实 `cch=<5hex>` 替回 `cch=00000` 后计算，保留完整 body。
- `2.1.172`：在最终 body 字节上替回 `cch=00000` 后，再做 top-level 规范化：
  - `model` 字段保留 key 和空字符串值，排除原模型值。
  - 删除 top-level `max_tokens` 字段。
  - 删除 top-level `fallbacks` 字段。
- CCH 输入裁剪必须只作用 top-level JSON 字段，不能误删 tool schema、message content 或嵌套对象里的同名字段。
- 不要先 `serde_json` 反序列化再重新序列化后计算 CCH；字段顺序、转义和空格变化会改变结果。

Beta 顺序契约：

- `context-1m-2025-08-07` 不放进通用必需 beta；它由账号 `allow_1m_models` 和客户端传入 beta 共同决定。
- 当允许 1M 并保留 `context-1m-2025-08-07` 时，顺序必须整理为 `oauth-2025-04-20` 后、`interleaved-thinking-2025-05-14` 前。
- Fable 无 1M 主请求顺序：

```text
claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,server-side-fallback-2026-06-01,fallback-credit-2026-06-01,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

- Fable `[1m]` 主请求顺序：

```text
claude-code-20250219,oauth-2025-04-20,context-1m-2025-08-07,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,server-side-fallback-2026-06-01,fallback-credit-2026-06-01,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

Fable body 契约：

- `model=claude-fable-5`。
- `max_tokens=64000` 默认只在缺失时补齐，不覆盖用户已有值。
- `fallbacks:[{"model":"claude-opus-4-8"}]` 只在缺失时补齐，不重复追加，不覆盖用户已有字段。
- `fallbacks` 必须发送给上游，但不参与 `2.1.172` CCH 输入。

Bootstrap 契约：

- `/api/claude_cli/bootstrap` response 可能是 gzip；改写前必须按 `Content-Encoding` 解码 JSON。
- 改写后的响应返回未压缩 JSON 时必须移除或重算 `Content-Encoding`、`Content-Length`、`Transfer-Encoding`，避免客户端按旧压缩头解释。
- Fable 能力由全局设置控制：
  - `bootstrap_model_options_mode=passthrough`：不改上游。
  - `configured`：可注入 `client_data.cedar_lagoon`、`additional_model_options`，Fable query 时 `cwk_cfg_key="marigold"`。
  - `hide_fable`：隐藏 Fable 入口并清空 `marigold`。

Telemetry 契约：

- `env.version`、`env.version_base`、`env.build_time` 必须跟默认版本画像一致。
- `model`、`preNormalizedModel`、`betas` 应来自最终请求 profile。
- `flags=model` 只表示 CLI 使用了一次性 `--model` 覆盖，不是 Fable 协议字段；不要因为模型是 Fable 就无条件写入。

账号迁移契约：

- 启动迁移必须把已有账号 `canonical_env.version/version_base/build_time` 更新到当前默认画像。
- 远程部署后必须查 DB 版本分布，不能只依赖日志判断。

### 4. Validation & Error Matrix

| 条件 | 期望 |
|------|------|
| 新版本抓包 CCH 不命中旧 seed | 先尝试输入规范化差异；只有多组样本都不命中时再逆向 seed |
| `cc_version` 主请求按第一个 text block 计算不命中 | 检查首条 user message 是否有多个 text block；按最后一个 text block 复算 |
| Fable 带 `[1m]` 时 beta 顺序与抓包不同 | 把 `context-1m-2025-08-07` 整理到 `oauth` 后面 |
| bootstrap response 有 gzip | 先解码再改 JSON，返回时修正压缩/长度相关 header |
| 远程部署后账号仍是旧版本 | 检查迁移是否执行；直接查 volume 内 SQLite/Postgres 的 `canonical_env` |
| 抓包分析需要保存到仓库 | 禁止提交完整 `http_capture.jsonl`、token、Cookie、Authorization、邮箱、完整 prompt/响应正文 |

### 5. Good/Base/Bad Cases

**Good**：升级版本前先收集 baseline 和目标版本的 Opus/Fable/Haiku 抓包，离线复算 `cc_version` 与 CCH，确认 beta 顺序，再改 profile 和测试。

**Base**：只升级一个 patch 版本，也必须至少验证 `/v1/messages` header、body keys、billing header、bootstrap 和 telemetry metadata 是否变化。

**Bad**：只把 `DEFAULT_CLAUDE_CODE_VERSION` 改成新版本，未同步 `User-Agent`、账号迁移、CCH 输入 profile 和 beta 顺序。

**Bad**：看到 Fable 抓包里有 `flags=model`，就把它硬编码成所有 Fable telemetry 字段。

**Bad**：把 `context-1m-2025-08-07` 放进 Fable 必需 beta，导致无 1M 设置时也开启 1M beta。

### 6. Tests Required

- `cargo fmt --check`
- `cargo test`
- `cargo test cch`
- 定向测试：
  - `cc_version_suffix_uses_string_indices`
  - `cc_version_suffix_source_uses_last_user_text_block`
  - `fable_messages_headers_use_fallback_beta_without_context_1m`
  - `fable_context_1m_beta_keeps_claude_code_order_when_allowed`
  - bootstrap gzip 解码和 configured/hide_fable 行为
  - telemetry 中 Fable `betas`、`model`，以及不无条件写 `flags=model`
- 抓包回归：
  - 169 baseline CCH 命中旧完整 body 规则。
  - 172 Opus CCH 命中 `model + max_tokens` 排除规则。
  - 172 Fable CCH 命中 `model + max_tokens + fallbacks` 排除规则。
  - Fable `[1m]` 抓包 beta 顺序与代码输出完全一致。
- 远程部署验收：
  - `docker compose pull` 后必须 `up -d --force-recreate`。
  - `curl http://127.0.0.1:<port>/` 返回 200。
  - DB 中 `accounts.canonical_env.version/version_base/build_time` 分布全部为目标默认值。

### 7. Wrong vs Correct

#### Wrong: `cc_version` 固定取第一个 text block

```rust
for item in arr {
    if let Some(text) = item.get("text").and_then(|t| t.as_str()) {
        return text.to_string();
    }
}
```

这样会取到 Claude Code 注入的环境上下文 block，主请求后缀会和抓包不一致。

#### Correct: 对多 text block 取最后一个 prompt block

```rust
if let Some(text) = arr
    .iter()
    .rev()
    .find_map(|item| item.get("text").and_then(|t| t.as_str()))
{
    return text.to_string();
}
```

#### Wrong: 把客户端 1M beta 追加到末尾

```text
claude-code-20250219,oauth-2025-04-20,...,cache-diagnosis-2026-04-07,context-1m-2025-08-07
```

#### Correct: 按抓包把 1M beta 放到 oauth 后

```text
claude-code-20250219,oauth-2025-04-20,context-1m-2025-08-07,interleaved-thinking-2025-05-14,...
```

---

## Common Mistakes

| 反模式 | 现象 | 怎么改 |
|--------|------|--------|
| 只改版本常量 | 请求 UA、账号 env、telemetry 或 access policy 仍停旧版本 | 搜索旧版本号并逐处确认 |
| 只看 CCH 不看 `cc_version` | CCH 命中但 billing header 后缀不真实 | 对每条主请求复算 suffix |
| 重新序列化 body 再算 CCH | 字段顺序或转义变化导致 hash 偏移 | 在最终 body 字节上做 top-level 裁剪 |
| Fable beta 无条件注入 1M | 不允许 1M 的账号也带 `context-1m` | 让客户端/白名单决定 1M |
| 部署后只看容器 Up | 账号仍可能停旧 `canonical_env` | 查 DB 版本分布 |
