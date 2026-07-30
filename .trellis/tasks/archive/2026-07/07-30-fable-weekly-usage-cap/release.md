# Release Operations

## Conclusion

Release operations exist.

## Evidence Checked

- `task.json`
- `prd.md`
- `design.md`
- `implement.md`
- `implement.jsonl`
- `check.jsonl`
- 父仓提交 `69a97db28ab6430b5b6a251be0419b10c0e46d05`
- cc2api 提交 `f7cecbc6edab79ffe7352cfe11e946b7e08dab4b`

## Drift Check

Missing `release.md`; this file records the verified release operations.

## SQL Changes

None. cc2api 启动迁移会通过现有 insert-if-missing 路径自动补齐 setting，不需要人工执行 SQL。

## Configuration Changes

- `[07-30-fable-weekly-usage-cap]` 新增全局 setting `fable_weekly_usage_limit_percent`，合法范围为 `1..=100`，缺失时自动写入默认值 `50`。
- `[07-30-fable-weekly-usage-cap]` 已有 `fable_sticky_quota_fallback_enabled` 继续作为总开关；开启时，升级后会从固定 100% 改为按新 setting 提前停止分配 Fable 请求。
- `[07-30-fable-weekly-usage-cap]` 管理端保存百分比后热生效，不要求额外重启。

## Batch / Deployment Scripts / Data Repair

None.

## External Systems / Dependent Platforms

None.

## Release Order

1. 部署包含 cc2api 提交 `f7cecbc` 的版本。
2. 在管理端 Settings 确认 Fable 周用量上限符合预期；默认值为 `50%`。

## Rollback Notes

- 优先把 `fable_weekly_usage_limit_percent` 设置为 `100`，恢复此前明确达到 100% 才过滤账号的阈值语义。
- 或关闭 `fable_sticky_quota_fallback_enabled`，立即停用 Fable 周用量过滤。
- 两种配置回滚都热生效；代码回滚后遗留的新 setting 会被旧版本忽略。

## Post-release Verification

- `GET /admin/settings` 返回 `fable_weekly_usage_limit_percent`，新部署缺失 key 时为字符串 `"50"`。
- 保存 `1..=100` 的整数后，新 `/v1/messages` Fable 请求立即使用新阈值；`0`、`101`、小数和文本应被拒绝。
- OAuth 账号最近观测的 `seven_day_fable.utilization` 达到阈值后不再承载后续 Fable 请求；低于阈值时继续使用原 sticky、RPM 和综合评分。
- 非 Fable 请求、SetupToken 账号、过期或不完整的 Fable usage 窗口保持原行为。
