# cc2api 2.1.173 抓包差异评估

## 样本矩阵

| 样本 | 本地路径 | 启动模型 | `/v1/messages` 主模型 | 说明 |
| --- | --- | --- | --- | --- |
| 3075 | `data/flows/pingguo-1/3075/a773a0d683a6` | 默认 | `claude-opus-4-8` | 2.1.172 Opus `[1m]` baseline |
| 3078 | `data/flows/pingguo-1/3078/715232eae9e8` | `claude-fable-5` | `claude-fable-5` | 2.1.172 Fable |
| 3085 | `data/flows/pingguo-1/3085/03373b8d8c65` | `claude-fable-5` | `claude-fable-5` | 2.1.172 Fable，另一个 topic |
| 3088 | `data/flows/pingguo-1/3088/09383cec8ea7` | `claude-fable-5[1m]` | `claude-fable-5` | 2.1.172 Fable `[1m]` |
| 3125 | `data/flows/pingguo-1/3125/bca74ce4196b` | 默认 | `claude-opus-4-8` | 2.1.173 Opus `[1m]` |
| 3126 | `data/flows/pingguo-1/3126/6e65bb7cb888` | `claude-fable-5` | `claude-fable-5` | 2.1.173 Fable |
| 3127 | `data/flows/pingguo-1/3127/7445da8ab9af` | `claude-fable-5[1m]` | `claude-fable-5` | 2.1.173 Fable `[1m]` |

三条新抓包均已拉到本地，并且都包含 `capture_index.json`、`http_capture.jsonl`、`stats.jsonl`、`.flow`。

## 结论

`2.1.173` 相对 `2.1.172` 没看到新的 header 顺序、beta、body profile、bootstrap 或 CCH 规则变化。需要升级的确定项是：

- 默认版本号：`2.1.173`
- `env.version` / `env.version_base`：`2.1.173`
- `env.build_time`：`2026-06-11T01:23:13Z`
- `User-Agent`：`claude-cli/2.1.173 (external, cli)` / `claude-code/2.1.173`
- access policy / Web 设置默认允许范围：从 `2.1.89-2.1.172` 扩到 `2.1.89-2.1.173`
- CCH profile 需要把 `2.1.173` 纳入 `2.1.172` 同款 seed 和输入规范化规则。

不建议改动的项：

- `X-Stainless-Package-Version=0.94.0`
- `X-Stainless-Runtime=node`
- `X-Stainless-Runtime-Version=v24.3.0`
- `X-Stainless-Timeout=600`
- `/v1/messages`、telemetry、bootstrap、GrowthBook、triggers、MCP 等端点的 header 顺序
- Fable fallback beta 与 `fallbacks:[{"model":"claude-opus-4-8"}]`
- bootstrap `additional_model_options` 中的 `claude-fable-5[1m]` 和 Fable `cwk_cfg_key="marigold"`

## cc_version

离线复算规则仍命中：`sha256("59cf53e54c78" + text[4] + text[7] + text[20] + version).hex()[0:3]`，按 JS UTF-16 code unit 索引，文本源取首条 user message 的最后一个 text block。

| 样本 | checked | matched | 观察到的 `cc_version` |
| --- | ---: | ---: | --- |
| 3075 | 38 | 38 | `2.1.172.6b6`、`2.1.172.be6` |
| 3078 | 23 | 23 | `2.1.172.6b6`、`2.1.172.be6` |
| 3085 | 8 | 8 | `2.1.172.ee0`、`2.1.172.51f` |
| 3088 | 7 | 7 | `2.1.172.ee0`、`2.1.172.51f` |
| 3125 | 31 | 31 | `2.1.173.090`、`2.1.173.445` |
| 3126 | 18 | 18 | `2.1.173.090`、`2.1.173.445` |
| 3127 | 18 | 18 | `2.1.173.090`、`2.1.173.445` |

判断：`2.1.173` 只把 version 字符串纳入同一后缀公式，没有换 salt 或取文本逻辑。

## CCH

使用 seed `0x4D659218E32A3268` 复算。`2.1.173` 按 `2.1.172` 的输入规范化规则全命中：

- Opus / Haiku：把真实 `cch` 替回 `00000` 后，排除 top-level `model` 值和 top-level `max_tokens` 字段。
- Fable：在上面基础上额外排除 top-level `fallbacks` 字段。

| 样本 | checked | 完整 body | 去 `model/max_tokens` | 再去 `fallbacks` |
| --- | ---: | ---: | ---: | ---: |
| 3075 | 38 | 0 | 38 | 38 |
| 3078 | 23 | 0 | 1 | 23 |
| 3085 | 8 | 0 | 1 | 8 |
| 3088 | 7 | 0 | 1 | 7 |
| 3125 | 31 | 0 | 31 | 31 |
| 3126 | 18 | 0 | 1 | 18 |
| 3127 | 18 | 0 | 1 | 18 |

Fable 中 `model_max=1` 是 Haiku/title 探测请求，本身没有 `fallbacks`；主 `claude-fable-5` 请求必须排除 `fallbacks` 才命中。

## 请求头顺序

所有新旧样本的 `/v1/messages` header 顺序一致：

```text
Accept, Authorization, Content-Type, User-Agent,
X-Claude-Code-Session-Id, X-Stainless-Arch, X-Stainless-Lang, X-Stainless-OS,
X-Stainless-Package-Version, X-Stainless-Retry-Count, X-Stainless-Runtime,
X-Stainless-Runtime-Version, X-Stainless-Timeout,
anthropic-beta, anthropic-dangerous-direct-browser-access, anthropic-version,
x-app, x-client-request-id, Connection, Host, Accept-Encoding, Content-Length
```

主要值：

- `User-Agent` 从 `2.1.172` 改为 `2.1.173`。
- `X-Stainless-Package-Version` 保持 `0.94.0`。
- `X-Stainless-Runtime-Version` 保持 `v24.3.0`。
- `Accept-Encoding` 保持 `gzip, deflate, br, zstd`。
- `anthropic-version` 保持 `2023-06-01`。
- `x-app` 保持 `cli`。

其他端点也没有顺序变化：

- `/api/event_logging/v2/batch`：`Accept, Accept-Encoding, Authorization, Content-Type, User-Agent, anthropic-beta, x-service-name, Connection, Host, Content-Length`
- `/api/claude_cli/bootstrap`：`Accept, Accept-Encoding, Authorization, Content-Type, User-Agent, anthropic-beta, Connection, Host`
- `/api/eval/sdk-zAZezfDKGoZuXXKe`：继续 `Bun/1.3.14`
- `/v1/code/triggers`：继续 `ccr-triggers-2026-01-30`
- `/v1/mcp_servers`：继续 `axios/1.15.2` 和 `mcp-servers-2025-12-04`

## Fable `[1m]` 与无 `[1m]`

### 2.1.172

`3088` 的 Fable `[1m]` 主请求包含 `context-1m-2025-08-07`，而 `3078/3085` 的无 `[1m]` Fable 主请求不包含。

### 2.1.173

`3126` 和 `3127` 主 `/v1/messages` 都使用同一个 Fable beta profile，不包含 `context-1m-2025-08-07`：

```text
claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,server-side-fallback-2026-06-01,fallback-credit-2026-06-01,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

两者主请求 body 也一致：

- top-level `model=claude-fable-5`
- `max_tokens=64000`
- `thinking.type=adaptive`
- `fallbacks=["claude-opus-4-8"]`

差异只出现在 telemetry 的启动配置信号：

- `3126`：`tengu_startup_manual_model_config` 的 `cli_flag=claude-fable-5`
- `3127`：`tengu_startup_manual_model_config` 的 `cli_flag=claude-fable-5[1m]`
- 两者 `tengu_cli_flags` 都是 `flags=model`

判断：`2.1.173` 下用户指定 `claude-fable-5[1m]` 并不会让主请求带 `context-1m-2025-08-07`，至少本次样本如此。cc2api 不应因为输入是 Fable `[1m]` 就给主请求注入 1M beta；若要保留旧 2.1.172 的 Fable `[1m]` 行为，需要作为显式兼容分支，而不是默认 2.1.173 画像。

## 遥测

endpoint 仍是 `/api/event_logging/v2/batch`，headers 不变：

- `User-Agent=claude-code/<version>`
- `anthropic-beta=oauth-2025-04-20`
- `x-service-name=claude-code`
- `Accept-Encoding=gzip, compress, deflate, br`

版本字段变化：

| 版本 | `env.version` | `env.version_base` | `env.build_time` |
| --- | --- | --- | --- |
| 2.1.172 | `2.1.172` | `2.1.172` | `2026-06-10T16:30:37Z` |
| 2.1.173 | `2.1.173` | `2.1.173` | `2026-06-11T01:23:13Z` |

模型字段：

- Opus 默认样本：大量 telemetry model 为 `claude-opus-4-8[1m]`，API 成功相关可出现 `claude-opus-4-8`。
- Fable 无 `[1m]`：主请求相关 telemetry model 为 `claude-fable-5`。
- `3088` 的 2.1.172 Fable `[1m]`：telemetry model 以 `claude-fable-5[1m]` 为主，主 `/v1/messages` 仍是 `claude-fable-5`。
- `3127` 的 2.1.173 Fable `[1m]`：启动配置记录 `cli_flag=claude-fable-5[1m]`，但主请求相关 telemetry model 聚合仍以 `claude-fable-5` 为主。

`flags=model` 仍表示 CLI 使用 `--model` 一次性覆盖 settings，不是 Fable 协议字段。cc2api 不应无条件给所有 Fable 生成该标记，只应在确实模拟一次性 model override 时生成。

## Bootstrap

bootstrap 请求保持：

- `User-Agent=claude-code/<version>`
- `anthropic-beta=oauth-2025-04-20`
- `Accept-Encoding=gzip, compress, deflate, br`

bootstrap response 保持 172 行为：

- Opus：`cwk_cfg_key=null`
- Fable / Fable `[1m]`：`cwk_cfg_key="marigold"`
- `client_data.cedar_lagoon` 含 `claude-fable=true`、`claude-mythos=true`
- `additional_model_options` 含 `claude-fable-5[1m]`
- response 仍是 gzip

## cc2api 修改建议

必须改：

1. `src/service/version_profile.rs`
   - `DEFAULT_CLAUDE_CODE_VERSION="2.1.173"`
   - `DEFAULT_CLAUDE_CODE_VERSION_BASE="2.1.173"`
   - `DEFAULT_CLAUDE_CODE_BUILD_TIME="2026-06-11T01:23:13Z"`
   - 注释从 2.1.172 更新为 2.1.173。
2. `src/service/access_policy.rs`
   - 默认允许范围扩到 `2.1.89-2.1.173`。
   - 更新 2.1.173 allow 测试。
3. `src/service/rewriter.rs`
   - `cch_attestation_seed` 把 `2.1.173` 纳入 `0x4D659218E32A3268`。
   - `cch_attestation_input` 把 `2.1.173` 纳入 `2.1.172` 同款规范化。
   - 更新固定期望 UA / billing prefix 的测试。
4. `src/service/telemetry.rs`
   - 更新测试里的 `claude-code/2.1.172` 期望为默认版本或 `2.1.173`。
   - 确认 env version/build_time 测试随默认常量走。
5. Web / README
   - `web/src/components/Settings.vue` 默认允许版本和文案改为 `2.1.89-2.1.173`。
   - README 中默认版本、允许范围、CCH 说明补 `2.1.173`。

无需改：

- `MESSAGE_BETA_TOKENS`
- `FABLE_FALLBACK_BETA_TOKENS`
- `FABLE_MESSAGE_BETA_TOKENS`
- `STAINLESS_PACKAGE_VERSION`
- `STAINLESS_RUNTIME_VERSION`
- `MCP_CLIENT_CAPABILITIES`
- `MCP_PROTOCOL_VERSION`
- `DEFAULT_BOOTSTRAP_ADDITIONAL_MODEL_OPTIONS`

需要加测试：

- `cch_attestation_seed("2.1.173") == 0x4D659218E32A3268`
- `cch_attestation_input(..., "2.1.173")` 与 2.1.172 同样裁剪 top-level `model/max_tokens/fallbacks`
- `compute_cc_version_suffix(..., "2.1.173")` 覆盖至少一个本轮样本对应的后缀形态
- Fable `[1m]` 在 2.1.173 profile 下不自动注入 `context-1m-2025-08-07`

## 安全说明

本报告只记录 endpoint、header 顺序、安全 header 值、版本字段、模型名、计数和 CCH/`cc_version` 命中统计。完整 `http_capture.jsonl`、`.flow`、token、Authorization、Cookie、账号邮箱、完整 prompt 和响应正文没有写入报告。
