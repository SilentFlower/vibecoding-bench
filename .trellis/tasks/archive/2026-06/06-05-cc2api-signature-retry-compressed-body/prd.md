# 修复 cc2api 压缩上游错误体导致 signature 降级未触发

## 目标

修复 `/root/project/cc2api` 中 Anthropic 上游错误响应体被压缩时，signature 相关 400 识别失败、未触发 thinking signature 降级重试的问题。

## 背景

远程容器日志显示 `/v1/messages` 上游返回：

`messages.1.content.0: Invalid signature in thinking block`

当前日志解压后可以打印明文错误体，但 `maybe_retry_signature_error` 内部仍对压缩后的原始 body 调用 `is_signature_related_error_body`，因此识别不到 `signature` 关键字，没有进入 `signature retry` 流程。

## 需求

- 保持上游请求的 `Accept-Encoding: gzip, deflate, br, zstd` 不变，不通过改请求头影响 Claude Code wire profile。
- 对上游错误响应体的业务判断使用按 `content-encoding` 解压后的 body。
- `maybe_retry_signature_error` 必须在压缩错误体场景下正确识别 signature 相关 400，并触发现有两阶段降级重试。
- 响应返回给客户端时仍保留原始上游响应体和响应头，不因内部判断破坏透传行为。
- 审核 cc2api 内其他依赖上游 response body 的逻辑，明确是否同样需要解压或保持现状。
- 保持日志不输出请求体、Authorization、access token、refresh token 等敏感数据。

## 已知响应体依赖点

- `GatewayService::maybe_retry_signature_error`：读取上游 400 body 判断是否 signature 相关，必须改为解压后判断。
- `GatewayService::forward_request` 的 429 分支：读取 429 body 供 `handle_rate_limit` 判断单请求级拒绝/账号级限流，也可能受压缩影响，需要使用解压后文本做业务判断，同时原样返回原始 body。
- `GatewayService::forward_request` 的非 2xx 诊断日志：已按 `content-encoding` 解压，仅用于日志。
- `extract_passive_usage`：只依赖响应头，不依赖 body。
- `PrimePollerService`：主要依赖状态码和响应头，429 调用 `handle_rate_limit(account, None, "", None)`，非 2xx drain body 只为释放连接，不解析 body。
- 流式转发 `bytes_stream`：透传响应体，不应解压。

## 验收标准

- [ ] 压缩的 signature 相关上游 400 能被 `maybe_retry_signature_error` 识别。
- [ ] 识别后日志出现 `returned signature-related 400, retrying with sanitized thinking history` 和对应 retry stage。
- [ ] 429 body 业务判断使用解压后的文本，不影响响应透传。
- [ ] 请求侧 `Accept-Encoding` 保持不变。
- [ ] 添加或更新单元测试覆盖 gzip/br/zstd 至少一种压缩错误体识别场景。
- [ ] 本地或容器内执行可用的 Rust 校验；如本机无 `cargo`，记录未执行原因。
