# cc2api thinking signature retry 实施计划

## Implementation Checklist

- [x] 读取 `cc2api` 相关上下文：`gateway.rs` 上游响应处理、`rewriter.rs` body helper、`telemetry.rs` 安全摘要字段。
- [x] 新增 signature 错误识别 helper，覆盖 Anthropic error JSON、Google-style error JSON 和原始字符串 fallback。
- [x] 新增 `strip_thinking_from_messages_request`：
  - [x] 移除顶层 `thinking`。
  - [x] `thinking` block 转 text。
  - [x] 删除 `redacted_thinking`。
  - [x] 无 type 但有 `thinking` 字段时转 text。
  - [x] 清空 content 时补 `(content removed)`。
- [x] 新增 `strip_signature_sensitive_blocks_from_messages_request`：
  - [x] 复用 thinking-only 行为。
  - [x] 额外将 `tool_use` 转 text。
  - [x] 额外将 `tool_result` 转 text。
- [x] 在 `GatewayService::handle_request_inner` 第一次 `forward_request` 后加入 `/v1/messages` + HTTP 400 + signature 相关判断。
- [x] 第一阶段用同账号、同 token、同 headers、同 path/query 重试。
- [x] 第一阶段仍为 signature 相关 400 时执行第二阶段重试。
- [x] `billing_mode=rewrite` 下重试体变更后刷新 `cch` attestation。
- [x] 确保两阶段失败时返回最后一次上游响应，非 signature 400 不变。
- [x] 补充安全日志/遥测标记，不记录完整请求体/响应体/thinking/signature/token。
- [x] 增加单元测试：错误识别、thinking-only 转换、thinking+tools 转换。
- [x] 增加 gateway 级测试或可测 helper 测试：两阶段重试触发顺序和停止条件。
- [x] README 或运维说明补充：签名错误整流行为和限制。

## Validation

- `cargo fmt --check`：未运行，本机缺少 `cargo`。
- `rustfmt --version`：未运行，本机缺少 `rustfmt`。
- `docker build -f docker/Dockerfile --target backend --progress=plain -t cc2api-thinking-signature-check .`：通过，容器内 release 构建成功。
- `docker run --rm cc2api-thinking-signature-check cargo fmt --check`：未通过，容器工具链缺少 `cargo-fmt` / `rustfmt` 组件。
- `docker run --rm cc2api-thinking-signature-check cargo test --offline`：通过，86 个单元测试全部通过。
- `npm --prefix web run build`：通过。
- `git diff --check`：通过。

## Implementation Notes

- 代码改动集中在 `/root/project/cc2api/src/service/gateway.rs`、`src/service/rewriter.rs` 和 `README.md`。
- signature retry 使用同一账号、同一 upstream token、同一套 header 语义；重试时移除 `content-length`，避免 body 大小变化后沿用旧长度。
- `billing_mode=rewrite` 的重试 body 会先把既有 `cch=xxxxx` 归零，再按变更后的 body 重新计算 CCH。
- 日志只记录阶段名、账号 ID 和 `safe_body_summary`，不记录 thinking、signature、请求体或响应体全文。
- `forward_request` 的 header debug 日志已对 `authorization` 脱敏，避免 signature retry 再次转发时泄漏 upstream token。

## Review Gates

- 实现前确认不引入 Anthropic signature 伪造或 dummy 逻辑。
- 提交前确认没有抓包原文、token、prompt、请求体/响应体全文进入代码或任务文档。
- 提交前确认父仓和 `cc2api` 分别只提交相关文件，仍禁止 `git add -A` / `git add .`。
