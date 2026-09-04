# Brief — 发布并验证 Claude Code 2.1.257 升级

## Goal

- 发布正式镜像并在生产环境完成可回滚的 2.1.257 升级与验收。

## Scope

- GHCR workflow、digest、连接预检、DB/配置备份、cc2api 先升级、vibecoding-bench
  后升级、HTTP/DB/容器/worker/log 验证和回滚证据。

## Non-Goals

- 不删除 volume，不改 1M allowlist，不用真实敏感 prompt 做破坏性验证。

## Key Decisions

- 必须等待两个实现子任务通过 Check-All 且提交已推送。
- 三个 vibecoding-bench 镜像锁定同一 SHA tag。
- cc2api 先部署，避免新 worker 被旧 allowed range 拒绝。

## Key Context

- 目标主机为 `us.flower-cli.com`；凭据不写入任务文件或日志。
- 线上已有自定义 system-role 模型和不含 fable 的账号 1M allowlist。

## Risks / Deferred

- 高连接、备份失败、镜像不一致或迁移覆盖自定义值时立即停止。
- 上游 no-response 只验证诊断，不现场放大 timeout。

## Acceptance

- 镜像、HTTP、DB、settings、worker 版本和日志均通过，1M allowlist 不变；回滚命令
  已补齐版本协调、现场快照和恢复路径。

## Next Step

- Check-All 通过后进入 `trellis-update-spec`，再由 `trellis-push` 生成精确提交计划。
