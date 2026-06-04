# cc2api Claude Code 2.1.156 设备与运行身份画像优化实施计划

## Implementation Checklist

- [x] 从抓包和现有代码整理身份字段矩阵。
- [x] 梳理 `CanonicalEnvData`、`CanonicalPromptEnvData`、`CanonicalProcessData` 的现有字段和默认值。
- [x] 设计 profile helper，集中生成设备级、运行级、请求级字段。
- [x] 优化新账号 identity preset，补齐 linux/darwin/win32 内部一致性字段。
- [x] 实现 process 曲线生成，替换完全离散的随机值。
- [x] 让 telemetry、GrowthBook、system prompt rewrite 和 header profile 使用统一身份来源。
- [x] 增加旧账号补齐或 regenerate 路径。
- [x] 更新 README 或内部文档说明身份画像层次和兼容策略。

## Validation

- `docker run --rm -v /root/project/cc2api:/work -w /work rust:latest /usr/local/cargo/bin/cargo test`
- 专项测试应覆盖：
  - 新账号 identity 生成。
  - 三个平台 profile 一致性。
  - 同一 run 内 process 指标连续性。
  - 跨 run 的 session 字段变化。
  - 旧账号缺失字段 fallback。

## Review Gates

- 实现前确认是否需要 DB schema 变更；若需要，先补迁移设计。
- 提交前确认不提交真实账号 profile、token、prompt 或抓包原文。
- 不允许静默覆盖用户已有的手工身份配置。
