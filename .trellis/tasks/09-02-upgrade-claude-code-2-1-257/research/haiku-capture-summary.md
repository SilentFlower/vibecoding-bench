# Claude Code 2.1.257 Haiku 抓包结论

## 样本

- run：`ea6d8e9bb665`
- 模型：`claude-haiku-4-5-20251001`
- HTTP 记录：332 条
- `/v1/messages`：55 条
- 分析范围仅包含请求结构、协议头、billing、bootstrap 和 telemetry 聚合信息；
  不记录 Authorization、Cookie、账号信息、prompt 或响应正文。

## 身份与运行时

- 55 条 message 请求的 `User-Agent` 均为
  `claude-cli/2.1.257 (external, cli)`。
- `X-Stainless-Package-Version` 为 `0.112.1`，runtime 为 Node `v26.3.0`。
- eval 请求使用 `Bun/1.4.1`。
- telemetry 的 `env.version` / `env.version_base` 1417/1417 均为 `2.1.257`，
  `build_time` 为 `2026-09-01T05:28:54Z`。
- bootstrap 查询模型为 Haiku，响应使用 Brotli，并广告
  `claude-fable-5-1[1m]`；该 Haiku bootstrap 样本没有 `cwk_cfg_key`。

## `cc_version` 与 CCH

- 55 条 message 中，1 条 `max_tokens=1` probe 没有 billing；其余 54 条均可复算。
- 现有 SHA256 文本位置算法对 `cc_version` 54/54 命中：
  - `2.1.257.aa0`：2 条结构化 title；
  - `2.1.257.e73`：48 条主请求；
  - `2.1.257.9ed`：4 条非流式辅助请求。
- CCH seed 仍为 `0x4D659218E32A3268`。
- CCH 输入仍需将顶层 `model` 置空并删除顶层 `max_tokens`：54/54 命中；
  完整 body + legacy seed 为 0/54。
- Haiku 样本没有顶层 `fallbacks`，所以“保留或删除 fallbacks”在该样本上结果相同；
  不能用此样本推翻 Fable 5.1 必须保留 `fallbacks: "default"` 的独立结论。
- 当前实现仅把版本白名单写到 2.1.220：
  `rewriter.rs:1903-1913` 会让 2.1.257 退回完整 body，
  `rewriter.rs:1951-1956` 会让 2.1.257 退回 legacy seed，因此未经适配会漏命中。

## Haiku 请求子画像

| 类型 | 数量 | 关键结构 | 抓包 beta 结论 | 当前实现影响 |
| --- | ---: | --- | --- | --- |
| probe | 1 | `max_tokens=1`、非流式、无 tools | 与现有 `HAIKU_PROBE_BETA_TOKENS` 相同 | beta 无需变化 |
| 结构化 title | 2 | `max_tokens=32000`、流式、tools 为空、thinking disabled、`output_config` 的 JSON schema 要求 `title` | 与现有 `HAIKU_STREAMING_TITLE_BETA_TOKENS` 相同 | beta 常量不变，但字符串 prompt 检测失效 |
| 主请求 | 48 | `max_tokens=32000`、流式、15 tools、4 system blocks、thinking enabled/31999 | 47 条为主 beta；1 条无 diagnostics，且同时没有 `claude-code-20250219` | 不能继续复用非 Fable 通用 beta |
| 非流式辅助请求 | 4 | `max_tokens=1024`、非流式、tools 为空、2 system blocks、thinking disabled | 使用独立窄 beta | 当前 title/suggestion/classifier 检测均不命中 |

### 结构化 title 检测

2.1.257 的两条 title 请求均不包含当前 `has_title_prompt_marker` 的三个旧字符串，
因此 `rewriter.rs:289-316` 会将其误判为普通 Haiku。`gateway.rs:4301-4317`
的 title/warmup 拦截器也存在同样问题。

应优先使用稳定结构识别：Haiku、流式、tools 为空、thinking disabled，且
`output_config.format` 的 JSON schema 明确要求 `title`；旧 prompt 标记保留为兼容兜底。

### 主请求 beta

47 条常规主请求的 beta 顺序为：

```text
oauth-2025-04-20,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,claude-code-20250219,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

唯一无 diagnostics 的主请求使用同一顺序，但缺少 `claude-code-20250219`。
相较当前 2.1.220 `MESSAGE_BETA_TOKENS`，Haiku 2.1.257 主请求不包含：

- `mid-conversation-system-2026-04-07`
- `effort-2025-11-24`
- `fallback-credit-2026-06-01`

并且 `claude-code-20250219` 的位置不同。当前
`rewriter.rs:243-280` 将所有非 Fable 模型统一映射到通用 message beta，
不能准确重放 2.1.257 Haiku。

### 非流式辅助请求 beta

4 条 `max_tokens=1024` 请求使用：

```text
oauth-2025-04-20,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,context-management-2025-06-27,prompt-caching-scope-2026-01-05,extended-cache-ttl-2025-04-11
```

这 4 条请求没有现有 suggestion 前缀、title prompt 标记、transcript、block 或
severity 协议标记，因此不能安全归入现有 mock 分类。规划阶段暂称
“Haiku 非流式辅助请求”，按请求结构配置独立 beta，不猜测其业务名称。

## 其他注意事项

- 本样本的 `messages[].role` 只有 `user` 和 `assistant`，Haiku 不需要新增
  system role 白名单。
- probe/title 的 beta 常量确实可以保留，但 Haiku 主请求和 `max_tokens=1024`
  辅助请求需要 2.1.257 专属子画像。
- CCH 不能只按版本统一删除 `fallbacks`；2.1.257 必须允许 Haiku/Opus 与
  Fable 5.1 使用不同的 fallbacks 归一化规则。
- 原生 Claude Code 转发可保留抓包 body 顺序；API mimicry 若主动合成新的
  Haiku 辅助请求，才需要新增对应字段顺序画像。
