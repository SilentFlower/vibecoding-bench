# cc2api 升级 Claude Code 2.1.172 实施计划

## Implementation Checklist

- [x] 读取 cc2api 相关 spec、现有 `version_profile`、`rewriter`、access policy、settings migration 和测试。
- [x] 更新默认 Claude Code 版本画像到 `2.1.172`，同步 build time、默认允许范围、usage User-Agent 和文档。
- [x] 更新 `/v1/messages` 和 bootstrap 的 UA/header profile，确保 172 只升级应变字段，不误改 Stainless/runtime/timeout 等稳定字段。
- [x] 将 beta 生成改为模型/profile 驱动：Haiku/title、Opus `[1m]`、Fable fallback 三类分别覆盖。
- [x] 将 CCH seed 选择扩展为版本化 profile，新增 `2.1.172` 输入规范化。
- [x] 在最终 body 字节上实现 top-level 字段裁剪：`model` 值、`max_tokens` 字段、`fallbacks` 字段。
- [x] 补齐 Fable 请求画像中 `fallbacks` 等 172 抓包差异，确保该字段发送但不参与 CCH。
- [x] 补齐 172 bootstrap response profile：`cedar_lagoon`、`additional_model_options`、Fable `cwk_cfg_key="marigold"`。
- [x] 如现有 cc2api 涉及 telemetry 生成或改写，更新 172 env version/build_time、模型/beta metadata，并把 `flags=model` 限定为一次性 model override 场景。
- [x] 增加 169 / 172 Opus / 172 Fable CCH 回归测试和 top-level 裁剪边界测试。
- [x] 增加 header/beta/telemetry profile 测试或快照，明确 `context-1m-2025-08-07` 只属于 Opus `[1m]` 等对应 profile。
- [x] 运行 rustfmt / cargo test；如改 Web/settings，再运行对应前端构建或静态检查。

## Implementation Notes

- bootstrap response 改写已落到 `/api/claude_cli/bootstrap` 的 2xx JSON 响应路径：默认 `passthrough` 不改变上游；`configured` 按全局设置注入 `client_data.cedar_lagoon` 和 `additional_model_options`，Fable bootstrap query 时补 `cwk_cfg_key="marigold"`；`hide_fable` 隐藏 Fable 入口并清空 `marigold`。抓包 `data/flows/pingguo-1/3078` 确认 bootstrap 响应为 `Content-Encoding: gzip`，实现会按响应头解码后改写 JSON，并移除压缩/长度/transfer 头返回未压缩 JSON。
- Fable `[1m]` 的 beta 顺序等待后续抓包确认；本轮只对已确认的 `claude-fable-5` 主请求启用 fallback beta 和 `fallbacks` body 字段。

## Validation

- `cargo test`
- `cargo test cch` 或等价精准测试命令。
- `rustfmt --edition 2024 --check <changed rust files>`。
- 如果涉及 Web：`npm run build`。
- `git diff --check`。

## Review Gates

- 实现前确认新任务进入 `in_progress`。
- CCH 代码合并前必须能解释 169/172 三组样本各自命中的输入规则。
- 检查通过后按 Trellis 路由进入提交流程，不直接裸 `git commit` 代码。
