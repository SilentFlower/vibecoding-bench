# cc2api Backend Testing & Quality

## 基础验证

Rust 后端提交前默认执行：

```bash
cd cc2api
cargo fmt --check
cargo test
```

如果只改文档或 Trellis spec，可以说明未运行代码测试；如果改 `src/`，不要跳过。

## 定向测试策略

- 请求体改写、CCH、`cc_version`：补 `rewriter` / `version_profile` 相关单测，覆盖多 text block、Fable、Haiku/title、小请求。
- 账号调度、RPM、粘性会话：补 service/store 层测试，明确并发、队列、超时和降级条件。
- settings：测试默认值、非法值、热刷新路径。
- DB migration：至少覆盖 SQLite；涉及 SQL 兼容时人工检查 PostgreSQL 语法。
- gateway 错误体：保留 Anthropic/OpenAI 可解析 error object，不要把本地拒绝改成裸字符串。

## 敏感数据边界

测试 fixture、日志和 spec 中禁止提交：

- OAuth `access_token` / `refresh_token`
- `Authorization` / `Cookie`
- 完整 prompt、tool input、响应正文
- 完整 `http_capture.jsonl`
- 邮箱、组织 ID、账号 UUID 的真实映射

需要记录抓包结论时，只写字段差异、header 顺序、hash 结果和脱敏摘要。

## Review Checklist

- [ ] 新代码沿用现有 `AppError` / `Result<_, AppError>` 风格。
- [ ] 热路径没有不必要的 clone、全量 JSON 重序列化或阻塞 I/O。
- [ ] 新 setting 完成默认值、迁移、校验、reload、UI、测试。
- [ ] 账号调度行为说明了粘性会话和 RPM 限制。
- [ ] `/v1/messages` 改写后 CCH / `cc_version` 仍在最终 body 上计算。
- [ ] SSE keepalive、压缩解码、错误体读取都有大小上限。
- [ ] 日志不输出敏感凭据或完整请求体。

## Common Mistakes

| 反模式 | 风险 | 正确做法 |
|--------|------|----------|
| 只跑单个测试忽略全量 `cargo test` | 共享 helper 回归 | 至少全量跑一次 |
| 用真实抓包全文做 fixture | 敏感数据入库 | 用脱敏最小样本 |
| 修改 CCH 后只测当前版本 | 旧版本兼容回退 | 保留 169/172/173 等版本回归 |
| Web build 不跑 | API 类型和设置页漏改 | 改前端或嵌入资源时跑 `npm run build` |
