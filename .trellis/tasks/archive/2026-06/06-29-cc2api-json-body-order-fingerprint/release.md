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
- `release.md`：原先不存在
- git commits / changed files：`66d0c06`、`dd5aa20`、`3d5ef10`、`294f358`、`f3f4876`

## Drift Check
Missing release.md. 当前任务修改了 `cc2api` 请求体改写、settings、DB 默认值和前端 Settings，需要按正常代码发布流程上线。

## SQL Changes
None. 本任务使用既有 settings 存储路径新增默认 key，没有独立 SQL 迁移文件。

## Configuration Changes
- 新增全局 setting：`message_body_order_fingerprint_enabled`。
- 默认值为 `true`，用于控制 API mimicry `/v1/messages` 顶层字段顺序对齐。
- 运维可在 Settings 页面关闭该开关作为快速回滚手段。

## Batch / Deployment Scripts / Data Repair
None. 本任务未新增部署脚本、一次性命令、数据修复或定时任务操作。

## External Systems / Dependent Platforms
- 需要按现有发布流程部署包含 `cc2api` commits `66d0c06` 和 `dd5aa20` 的服务版本。
- 前端 Settings 需要随同发布，确保开关可展示和保存。

## Release Order
1. 发布 `cc2api` 后端和前端构建产物。
2. 打开 Settings 页面确认 `message_body_order_fingerprint_enabled` 可见且默认开启。
3. 使用 API mimicry `/v1/messages` 请求确认排序后的 body 参与 CCH。
4. 使用 Claude Code 客户端请求确认原始顶层字段顺序被保留。

## Rollback Notes
- 首选回滚方式：在 Settings 页面关闭 `message_body_order_fingerprint_enabled`。
- 如仍有风险，回滚 `cc2api` 相关代码 commit。

## Post-release Verification
- 确认 API mimicry `/v1/messages` 顶层字段顺序符合 2.1.195 抓包画像。
- 确认 Claude Code 客户端 `/v1/messages` 不被额外重排。
- 确认 CCH 使用排序后的最终 body。
