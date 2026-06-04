# cc2api thinking signature retry 设计

## Technical Design

### 边界

- 修改目标仓库：`/root/project/cc2api`。
- 主要落点：
  - `src/service/gateway.rs`：在上游返回 400 后插入签名整流重试流程。
  - `src/service/rewriter.rs` 或 `src/service/gateway.rs` 私有 helper：实现 signature-sensitive body 转换函数。
  - `src/service/telemetry.rs`：如现有字段不足，补充安全摘要字段或错误类型，不能记录原文。
- 不修改 Anthropic 签名，不生成 dummy `signature`。
- 不把 Gemini `thoughtSignature` 的 dummy 逻辑迁入 Anthropic 官方链路。

### 参考实现

- `/root/project/sub2api/backend/internal/service/antigravity_gateway_service.go`
  - `isSignatureRelatedError`
  - `stripThinkingFromClaudeRequest`
  - `stripSignatureSensitiveBlocksFromClaudeRequest`
  - 400 后按 `thinking-only` / `thinking+tools` 两阶段重试
- `/root/project/sub2api/backend/internal/service/gemini_native_signature_cleaner.go`
  - 只作为反例参考：Gemini native `thoughtSignature` 可以 dummy，Anthropic `thinking.signature` 不这样做。

### 数据流

1. `GatewayService::handle_request_inner` 读取原请求体，选择账号并完成现有 body/header 改写。
2. 使用 `final_body` 和 `final_headers` 发起第一次官方 Anthropic 请求。
3. 如果响应不是 `/v1/messages` 的 HTTP 400，保持现有逻辑。
4. 如果响应是 signature 相关 400：
   - 读取并缓存错误体，提取安全错误摘要。
   - 对 `final_body` 做第一阶段转换：移除顶层 `thinking`，`thinking` block 转 `text`，删除 `redacted_thinking`。
   - 若账号为 `billing_mode=rewrite`，重试体变更后必须刷新 `cch` attestation，避免 body hash 和 billing header 不一致。
   - 使用同账号、同 token、同 headers 重试。
5. 如果第一阶段仍是 signature 相关 400：
   - 对 `final_body` 做第二阶段转换：在第一阶段基础上额外 `tool_use` / `tool_result` 转 `text`。
   - 同样刷新 `cch` attestation。
   - 使用同账号、同 token、同 headers 重试。
6. 任一阶段成功则返回该响应；两阶段失败则返回最后一次上游响应。

### 转换契约

- `thinking` block:
  - 输入：`{"type":"thinking","thinking":"...","signature":"..."}`
  - 输出：`{"type":"text","text":"..."}`
- `redacted_thinking` block:
  - 输出：删除。
- 无 `type` 但包含 `thinking` 字段：
  - 输出：`{"type":"text","text":"..."}`
- 第一阶段不改 `tool_use` / `tool_result`。
- 第二阶段：
  - `tool_use` 输出文本包含 `name`、`id`、`input` 的安全 JSON 摘要。
  - `tool_result` 输出文本包含 `tool_use_id`、`is_error`、`content` 的安全 JSON 摘要。
- 某条 message 的 content 清理后为空时，补普通 text：`(content removed)`。

### 错误识别

- 从上游 400 响应体中提取字符串后小写匹配。
- 需要兼容 Anthropic 常见结构：
  - `{"type":"error","error":{"type":"invalid_request_error","message":"..."}}`
  - `{"error":{"message":"..."}}`
  - fallback 扫描原始响应体字符串。
- 命中条件：
  - 包含 `signature`
  - 包含 `thought_signature`
  - 同时包含 `expected` 和 `thinking` 或 `redacted_thinking`

### 遥测与日志

- 不记录完整 body。
- 可记录：
  - `signature_retry_stage=thinking-only|thinking+tools`
  - `signature_retry_triggered=true`
  - `status_code`
  - `duration_ms`
  - `upstream_request_id` 如响应 header 可得
- 如果 telemetry 结构不适合扩展，先用 `error_kind` / `debug!` / `warn!` 安全摘要实现。

### 回滚

- 所有重试逻辑集中在 helper 或小范围 gateway 分支。
- 若上线后异常，只需关闭调用分支或移除 signature retry helper，恢复原始 400 透传。

## Tradeoffs

- thinking 转 text 会牺牲 extended thinking 的连续性，但能避免官方上游校验非法签名导致整个会话不可用。
- 第二阶段降级 tool blocks 会破坏工具调用语义，只在第一阶段仍失败时使用，符合 `sub2api` 的保守降级策略。
- `billing_mode=rewrite` 下重试体会改变 body 字节，因此需要额外刷新 `cch`；这不是新指纹策略，只是保持既有 CCH 契约一致。
- 不新增配置开关，保持行为和用户要求一致；如后续发现误触发，再增加 settings 开关。
