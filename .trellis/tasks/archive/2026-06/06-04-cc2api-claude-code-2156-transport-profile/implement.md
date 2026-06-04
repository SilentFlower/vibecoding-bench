# cc2api Claude Code 2.1.156 传输层与 Header Wire 指纹优化实施计划

## Implementation Checklist

- [x] 编写真实抓包 wire 摘要脚本，输出 endpoint/header/HTTP 行为摘要。
- [x] 搭建 cc2api 本地 dummy upstream 捕获流程，生成相同格式摘要。
- [x] 生成真实 Claude Code vs cc2api 差异表。
- [x] 按差异表修复低风险 header casing/order/encoding/profile 问题。
- [x] 如确认为必要，再评估 `tlsfp.rs` 的 client profile 调整。
- [x] 增加 endpoint header profile 测试，避免后续版本回退。
- [x] 更新 README 或任务研究文档。

## Validation

- `docker run --rm -v /root/project/cc2api:/work -w /work rust:latest /usr/local/cargo/bin/cargo test`
- 专项验证：
  - wire 摘要脚本不输出敏感 header 值和 body 原文。
  - endpoint header profile 测试覆盖主要路径。
  - 本地 dummy upstream 能捕获 cc2api 出站请求并生成 diff。

## Review Gates

- 传输层修改前必须有真实抓包和 cc2api 本地抓包的差异证据。
- 不允许仅凭猜测修改 TLS/HTTP client profile。
- 提交前确认不包含 `.flow`、`http_capture.jsonl`、token、prompt、响应体全文。
