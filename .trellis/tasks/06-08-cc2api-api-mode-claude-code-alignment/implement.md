# cc2api API 模式对齐 Claude Code 请求画像实施计划

## Implementation Checklist

- [x] 补齐 API mimicry system 常量和 billing block 构造函数。
- [x] 复用或调整现有 `compute_cc_version_suffix` / `compute_cch_attestation`，让 API 模式也生成 `cch=00000` 占位并在最终 body 后签名。
- [x] 修改 API 模式 `/v1/messages` 改写链路：system 重写、原始 system 迁移到 messages、metadata/session 稳定化、保留 tools。
- [x] 处理 API 模式 `_session_id` 清理与 CCH 顺序，确保签名发生在最终上游 body 之后。
- [x] 让 API 模式按设置进入 message cache 断点修复，确保 TTL 改写和 CCH 签名顺序正确。
- [x] 检查 header 生成：`X-Claude-Code-Session-Id` 与 `metadata.user_id` 对齐，Claude Code-like beta/header 集合不退化。
- [x] 增加单元测试覆盖 API mimicry、CCH 顺序、tools 保留、message cache 改写和 Claude Code 模式回归。

## Validation

- `cargo test -p cc2api rewriter`
- 如仓库无 workspace package 名，退化为在 `/root/project/cc2api` 执行 `cargo test rewriter`。
- 已执行 `rustfmt --edition 2024 --check src/service/rewriter.rs src/service/gateway.rs src/service/prime_poller.rs`。
- 已执行 `cargo test rewriter -- --nocapture`、`cargo test gateway -- --nocapture`、`cargo test prime -- --nocapture`、`cargo test`。
- 目标测试至少包含：
  - API mimicry system 3-block 形态。
  - API 原始 system 迁移到 messages。
  - API 已有 tools 不被删除。
  - API message cache 设置生效。
  - API CCH 基于最终 body 计算。
  - Claude Code 模式 CCH 顺序回归。

## Review Gates

- 开始实现前确认任务从 planning 进入 in_progress。
- 实现完成后检查 PRD 验收项逐条满足，再走 Trellis check。
