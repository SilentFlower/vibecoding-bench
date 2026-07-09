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
- `release.md`：归档前不存在
- git commits / changed files：
  - `5b76504 fix(gateway): 支持 Fable sticky 满额切号`
  - `954afa6 chore(task): 记录 Fable sticky 满额切号任务`
  - `ea78d71 chore(task): update cc2api-fable-sticky-quota-fallback push snapshot`

## Drift Check
Missing release.md. 当前任务新增 settings 默认值、管理端开关、Gateway 热缓存和 settings 表默认插入，属于发布时需要显式关注的配置与迁移事项。

## SQL Changes
- 无 schema 变更，无需手工 SQL。
- `cc2api/src/store/db.rs::migrate` 会在 `settings` 表缺失时插入 `fable_sticky_quota_fallback_enabled` 默认值；老实例部署新代码并启动迁移后会自动补齐。

## Configuration Changes
- 新增全局 setting：`fable_sticky_quota_fallback_enabled`。
- 默认值为 `true`，升级后默认允许 Fable 周用量明确耗尽时打破 sticky 并切换到其他可用账号。
- 管理端 Settings 页“评分权重”卡片内新增“Fable 配额切换”开关；如需回退旧 sticky 行为，可将该开关保存为关闭。
- setting 写入后 Gateway 会热刷新，无需重启才能生效。

## Batch / Deployment Scripts / Data Repair
- 需要部署 `cc2api` 新提交 `5b76504` 对应的服务代码或镜像。
- 无一次性批处理、数据修复或后台任务重跑。

## External Systems / Dependent Platforms
- `cc2api` 子模块提交已推送到 `SilentFlower/cc2api` 的 `main`。
- 父仓子模块指针已推送到 `SilentFlower/vibecoding-bench` 的 `main`。
- 无第三方控制台、权限、密钥或外部平台配置变更。

## Release Order
1. 确认 `cc2api` 提交 `5b76504` 已在远端可用。
2. 部署包含该提交的 `cc2api` 服务或镜像。
3. 启动后让 `migrate` 自动补齐 `settings.fable_sticky_quota_fallback_enabled`。
4. 如管理员不希望默认开启，部署后在 Settings 页关闭“Fable 配额切换”。

## Rollback Notes
- 最小回滚：在 Settings 页关闭“Fable 配额切换”，或将 `settings.fable_sticky_quota_fallback_enabled` 设置为 `false`，恢复旧 sticky 行为。
- 代码回滚：回退 `cc2api` 服务到 `5b76504` 之前的版本，并回退父仓子模块指针。

## Post-release Verification
- Settings 页显示“Fable 配额切换”开关，默认状态为“已启用”。
- `settings` 表存在 `fable_sticky_quota_fallback_enabled=true`，或管理员显式配置的值被保留。
- 两个 OAuth 账号场景中，sticky 账号 `seven_day_fable.utilization >= 100` 且 reset 在未来时，Fable `/v1/messages` 请求会切到仍有 Fable 配额的账号。
- 非 Fable 请求和 sticky RPM 饱和场景保持原有行为。
