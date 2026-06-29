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
- git commits / changed files：`a74ae52`、`548d6fb`、`06aada6`

## Drift Check
Missing release.md. 当前任务已实现 `cc2api` telemetry 代码变更，并在 PRD / implement snapshot 中明确要求部署后执行远程灰度抓包验收。

## SQL Changes
None

## Configuration Changes
None

## Batch / Deployment Scripts / Data Repair
None. 本任务未新增部署脚本、一次性命令、数据修复或定时任务操作。

## External Systems / Dependent Platforms
- 需要按现有发布流程部署包含 `cc2api` commit `a74ae52` 的服务版本。
- 部署后需要对真实出站 `/api/event_logging/v2/batch` 流量做灰度抓包，并用脱敏 diff 脚本对比 2.1.195 catalog。

## Release Order
1. 发布 `cc2api` 代码版本。
2. 使用开启 `auto_telemetry` 的灰度账号触发 `/v1/messages` 请求。
3. 抓取真实出站 telemetry batch，并脱敏保存到本地 evidence 目录或远程安全位置。
4. 运行 `.trellis/tasks/06-29-cc2api-auto-telemetry-real-profile-alignment/scripts/telemetry_catalog.py` 生成对比结果。

## Rollback Notes
- 如发现字段泄露、异常事件形态或封禁风险升高，优先关闭账号级 `auto_telemetry`。
- 代码层面可回滚 `cc2api` commit `a74ae52`，恢复此前自动遥测行为。

## Post-release Verification
- 确认出站 telemetry body 不包含 prompt、tool input、响应正文、token、Cookie、邮箱、完整账号 UUID。
- 对比事件名分布、metadata key 分布、字段密度和 env shape，确认比任务前更接近 2.1.195 真实抓包。
- 保留脱敏结果，不提交原始抓包或完整 telemetry body。
