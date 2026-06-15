# 强化 cc2api count_tokens 兼容 - 实施计划

## Implementation Checklist

- [x] 在 `cc2api/src/handler/router.rs` 增加 `POST /v1/messages/count_tokens` 显式路由，复用现有 API token 鉴权。
- [x] 在 `GatewayService` 增加 count_tokens 专用入口，读取 body、解析 JSON、校验 `model`。
- [x] 抽取或新增 count_tokens 专用账号选择逻辑，复用 allowed/blocked account ids 和 session hash，但不消耗普通 RPM/并发槽。
- [x] 实现 count_tokens 专用 header 计算，确保最终 `anthropic-beta` 包含 `token-counting-2024-11-01`。
- [x] 实现上游 URL 构造，确保目标为 `/v1/messages/count_tokens?beta=true`。
- [x] 实现 body 轻量兼容处理和模型映射，避免注入 `max_tokens=1` 或进入普通 messages rewrite 副作用。
- [x] 实现成功响应透传和错误响应映射，尤其是 404/429/529。
- [x] 确认 count_tokens 不触发非流探针日志/缓存、telemetry message request、stateful cache 锚点推进和普通 429 跨账号重试。
- [x] 补充单元测试/集成式 service 测试：
  - [x] 路由或入口分流到 count_tokens 专用路径。
  - [x] 上游 URL 使用 `/v1/messages/count_tokens?beta=true`。
  - [x] beta 自动补齐 `token-counting-2024-11-01`。
  - [x] 429 不跨账号风暴重试。
  - [x] 成功响应保留 `input_tokens`。
  - [x] 错误响应为 Anthropic 风格。
- [x] 运行格式和测试。

## Validation

```bash
cd /root/project/cc2api
cargo fmt --check
cargo test
```

可选远程验证：

```bash
cd /root/project/vibecoding-bench
# 使用 .deploy/cc2api.env 部署后，触发 Claude Code /context
# 检查远程日志中 /v1/messages/count_tokens 与 max_tokens=1 非流 429 数量
```

## Review Gates

- 开始实现前确认 PRD/design/implement 范围。
- 改动 `src/` 后必须至少跑定向 Rust 测试；最终跑 `cargo test`。
- 不新增 DB migration 或前端设置，除非实现中发现不可避免并回到 PRD 更新。
