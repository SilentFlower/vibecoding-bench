# 升级 cc2api 到 Claude Code 2.1.185 - 技术设计

## Boundaries

本任务只修改 `cc2api` 子模块及本任务 Trellis 文档。父仓后续仅用于记录子模块 gitlink 和任务文档，不改 `vibecoding-bench` 主项目运行逻辑。

## Data Flow

`version_profile.rs` 是协议画像源头：

```text
DEFAULT_CLAUDE_CODE_* / UA helper
  -> model/identity.rs 默认 canonical env
  -> store/db.rs 启动迁移
  -> rewriter.rs 上游 header/body/CCH/cc_version
  -> telemetry.rs 自动遥测 header/body
  -> settings_store.rs / access_policy.rs / web Settings / README
```

## Protocol Decisions

- `2.1.185` 沿用 `2.1.172` / `2.1.173` 的 CCH 规则，不新增 seed 搜索逻辑。
- `2.1.185` 沿用现有 `cc_version` 后缀公式，不改 text block 选择规则。
- `MESSAGE_BETA_TOKENS` 暂不改成 Haiku 探针专用集合；当前 cc2api 的常量对应主请求画像，抓包中 Haiku 辅助请求的 beta 差异暂不作为本次默认画像范围。
- Fable `[1m]` 行为沿用现有白名单透传：账号允许且客户端传入 `context-1m-2025-08-07` 时保留并排序到 `oauth` 后。
- 自动遥测字段继续只发送脱敏/画像类元数据，不写完整 prompt、tool input、响应正文或 token。

## Implementation Shape

- 更新 `src/service/version_profile.rs` 中版本、build time 和 GrowthBook UA。
- 更新 `src/service/rewriter.rs` 中 `2.1.185` 的 CCH seed / input 分支和测试。
- 更新 `src/service/access_policy.rs`、`src/store/settings_store.rs`、`src/store/db.rs` 的默认版本范围和迁移旧值。
- 更新 `web/src/components/Settings.vue` 的默认值、placeholder、说明和快捷按钮。
- 更新 README 中默认版本、允许范围、CCH 说明。

## Rollback

如测试或后续远程验证发现 `2.1.185` 画像有未覆盖字段，可回滚子模块 commit，账号启动迁移会在旧版本二进制启动时按旧默认画像再次写回。
