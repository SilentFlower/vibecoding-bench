# 实施计划

## 步骤

- [ ] 读取 `cc2api/src/service/gateway.rs` 中 response body 缓冲、解压、signature retry、429 处理逻辑。
- [ ] 提取可复用的“按 response headers 解压 body 并用于内部判断”的 helper，避免日志和业务判断各写一套。
- [ ] 修改 `maybe_retry_signature_error`：保留原始 buffered body 用于重建响应，使用解压后的 body 做 `is_signature_related_error_body` 判断。
- [ ] 修改 retry 阶段的二次 400 判断，同样使用解压后的 body。
- [ ] 修改 429 分支：`handle_rate_limit` 使用解压后的 body 文本，返回仍使用原始 body。
- [ ] 添加压缩 body 单元测试，覆盖 signature detector 或 helper。
- [ ] 运行可用校验：优先 `cargo test` / `cargo check`；若本机无 cargo，使用 Docker 构建或记录限制。
- [ ] 推送 cc2api `v2` 分支并协助查看远程容器日志。

## 关键约束

- 不改 `Accept-Encoding`。
- 不解压透传给客户端的响应体。
- 不打印敏感请求体和凭证。
