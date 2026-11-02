# Claude Code 大请求 gzip：官方公开证据

核对日期：2026-10-29。这里是公开文档证据，不是 300／303 原生抓包。

## 官方发布记录

- 来源：[Claude Code v2.1.300](https://github.com/anthropics/claude-code/releases/tag/v2.1.300)，页面显示 10 月 14 日发布，标签提交 `94506ff`。
- 发布说明明确：发往 `api.anthropic.com` 的大请求，即使关闭遥测也使用 gzip；`CLAUDE_CODE_GZIP_REQUEST_BODIES=0` 可以关闭。
- 该说明证明 300 的默认行为覆盖遥测关闭场景，不能据此断言 gzip 最初在 300 引入，也不能断言所有请求都压缩。

## 官方环境变量文档

- 来源：[Environment variables](https://code.claude.com/docs/en/env-vars)，定位 `CLAUDE_CODE_GZIP_REQUEST_BODIES`。
- 默认压缩直连 `api.anthropic.com` 的大请求体，范围包括 Claude API、telemetry、artifact publish。
- 经过检测到的代理、配置客户端证书或设置 `NODE_EXTRA_CA_CERTS` 时跳过；变量设为 0 可关闭。
- 文档没有给出大小阈值，也没有承诺自定义 API base、代理和所有版本／配置组合采用同一策略。不采用 issue 评论中的阈值推测。

## 对本项的约束

- 用户已明确选择：请求声明什么编码，就在完成既有改写后按该编码发出；不能统一改为明文。
- 以实际 `Content-Encoding` 为依据，不根据 UA、画像版本、`Accept-Encoding` 或假定阈值启用压缩。
- 不能只修 Messages。通用 Gateway 的遥测及其它转发路径也必须使用同一正文编解码边界；不改变各端点已有的 JSON／非 JSON 语义。
- 已有 592 条原生 Messages 的最高可核对版本为 2.1.280，均没有 Content-Encoding。用户明确尚未抓取 300 之后的样本；本轮不声称已验证其 gzip 容器参数、压缩级别、头顺序或 CCH 新版本规则。

## 本项之外的响应边界

- `gateway.rs:3033` 起的普通响应复制上游头，并转发原始字节；没有与请求端相同的统一丢失编码头行为。
- `gateway.rs:3897` 的缓冲响应在解码成功后返回明文并移除旧编码／长度／传输头，失败则保留原字节与头。count_tokens 和错误响应使用此路径；bootstrap 只有实际改写时返回明文，跳过改写时保留原字节与头。
- `gateway.rs:4248` 的保活未按实际 Content-Type／Content-Encoding 设门槛。开启时可能在 gzip 或 JSON 中插入明文 SSE 注释；默认关闭，用户已经决定本轮不改 R3-01。
- 现有响应 helper 仍有无解码输出上限、单 gzip member 和严格完成校验边界；不得把本项请求专用 helper 偷换到响应链路。这里记录检查事实，不扩展本项交付范围。
