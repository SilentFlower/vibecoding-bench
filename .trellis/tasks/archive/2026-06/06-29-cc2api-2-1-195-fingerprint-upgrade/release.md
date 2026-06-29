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
- git commits / changed files：`b24cf56`、`01a4a4d`、`832ce2c`

## Drift Check
Missing release.md. 当前任务升级 `cc2api` 默认 Claude Code 画像到 `2.1.195`，涉及请求指纹、settings 默认值、DB 启动迁移、已有账号 canonical env 更新和前端 Settings 展示。

## SQL Changes
None. 本任务没有新增独立 SQL migration 文件。

## Configuration Changes
- 默认 Claude Code profile 更新为 `2.1.195`。
- 默认 `allowed_claude_code_versions` 更新为 `2.1.89-2.1.195`。
- 默认 canonical env 更新为 `version=2.1.195`、`version_base=2.1.195`、`build_time=2026-06-26T01:00:56Z`。
- Stainless runtime version 更新为 `v26.3.0`。

## Batch / Deployment Scripts / Data Repair
- 需要在发布后确认服务启动迁移已执行：旧默认 `allowed_claude_code_versions` 升级到 `2.1.89-2.1.195`。
- 需要在发布后确认已有账号 canonical env 已更新到 `2.1.195` 对应字段。
- 无单独一次性脚本；迁移逻辑随服务启动执行。

## External Systems / Dependent Platforms
- 需要按现有发布流程部署包含 `cc2api` commit `b24cf56` 的服务版本。
- 需要发布前端 Settings 变更，确保可展示并选择 `2.1.195`。
- 远程服务器上原始抓包 evidence 不应提交到仓库；只保留脱敏摘要。

## Release Order
1. 发布 `cc2api` 后端和前端构建产物。
2. 重启服务，触发 settings / canonical env 启动迁移。
3. 在 Settings 页面确认默认 profile、allowed range 和 profile 列表。
4. 使用测试账号发起 `/v1/messages`，确认 UA、Stainless runtime、beta、CCH、`cc_version`、telemetry env 与 2.1.195 画像一致。
5. 对远程 DB/settings 做只读验收，确认旧默认值已迁移。

## Rollback Notes
- 首选回滚方式：切回 `claude_code_version_profile=2.1.187`。
- settings 事务会回写 `allowed_claude_code_versions` 和账号 canonical env；必要时重新部署旧镜像。
- 如发现 CCH / `cc_version` / runtime 指纹异常，应暂停 `2.1.195` 画像并回退到旧 profile。

## Post-release Verification
- `/v1/messages` 请求画像输出对齐 `2.1.195`：User-Agent、Stainless package/runtime、beta、billing 与 CCH 规则。
- `cc_version` 对 Haiku / Opus 样本后缀可复算。
- CCH 使用 `2.1.172+` 规范化规则和 seed `0x4D659218E32A3268`。
- Settings 保存 `2.1.195` 后重新加载显示后端强制覆盖的版本范围。
- 原始抓包、token、Cookie、邮箱、账号 UUID、完整 prompt 或响应正文未进入提交内容。
