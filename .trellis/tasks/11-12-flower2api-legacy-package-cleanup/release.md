# 旧三镜像包清理操作

## 前提

- 精确Git计划执行后，确认默认main与flower2api的docker-publish.yml均为退役入口。
- 仅使用ghcr-legacy-cleanup.yml的flower2api手动入口。仓库临时令牌需要实际具备目标包权限。
- deploy/flower2api/legacy-package-reference-evidence.json须为24小时内真实宿主只读核验，三个旧镜像引用为零。

## 上线后验证与应用

1. 先以apply=false运行，下载legacy-package-preview；核对成功运行、完整源码SHA、三个包ID、全部版本、关联仓库及规范JSON摘要。
2. 按已授权范围，以同一源码运行apply=true，提供plan_run与plan_sha256。精确目标为vibebench-orchestrator、vibebench-worker、vibebench-sidecar。
3. 下载legacy-package-receipt；每项须同时具备正向204删除记录和404复查。只有三项全部完成才关闭本任务。

## 失败恢复

- 权限、归属、版本、引用、来源或摘要失败时停止，保存实际结果。
- 部分成功按收据逐项记录；后续操作重新规划剩余精确对象，禁止将不可见404补记为删除成功。
- 恢复需要重新核对GitHub允许的时间、命名空间及权限，再取得恢复指令。
- 当前及后继正式control/account包、历史签名发行、线上容器与数据进入保护范围。

## 实际结果

预览43247664483、应用43248120634均成功。三个固定旧包共1360个版本完成删除，每项均有204收据及404复查。
