# 升级 cc2api 到 Claude Code 2.1.185 - 实施计划

## Implementation Checklist

- [x] 更新版本画像常量和 GrowthBook UA。
- [x] 更新允许版本范围默认值、旧值迁移和访问策略测试。
- [x] 将 `2.1.185` 纳入 CCH seed / input 版本分支并补测试。
- [x] 更新 telemetry / rewriter 相关测试期望。
- [x] 更新 Settings 页面默认值、placeholder、说明和快捷按钮。
- [x] 更新 README 中版本范围、默认画像和 CCH 说明。
- [x] 运行质量检查。

## Validation

```bash
cd cc2api
cargo fmt --check
cargo test
cargo test cch
cd web
npm run build
```

## Review Gates

- 检查 `rg "2\\.1\\.173|2\\.1\\.185|Bun/1\\." cc2api`，确认旧版本只保留在历史迁移、兼容测试或对比文档中。
- 检查 `git diff -- cc2api`，确认没有完整抓包或敏感数据进入提交。
