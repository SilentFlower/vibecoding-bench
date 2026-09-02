# Brief — 升级 vibecoding-bench 到 Claude Code 2.1.257

## Goal

- 将所有无页面覆盖的新 worker 默认 CLI 版本统一为 2.1.257。

## Scope

- 同步 worker Dockerfile/entrypoint、orchestrator fallback、普通/capture/login/quota
  worker 版本传递、Compose、env、WebUI、README、部署规范和测试中的默认版本。

## Non-Goals

- 不改模型、effort、代理、凭据或 cc2api 协议。
- 不构建或部署镜像。

## Key Decisions

- 保持 WebUI SQLite 覆盖 > 环境默认 > 代码默认的现有优先级。
- worker 启动继续校验实际版本，不一致时安装目标版本，失败即失败。

## Key Context

- 升级前 2.1.220 默认值分布在 `images/worker/Dockerfile`、
  `images/worker/entrypoint.sh`、`orchestrator/main.py`、两份 Compose、
  `.env.example`、`webui/index.html` 和文档。

## Risks / Deferred

- 内嵌 Node fallback 漏改会让少见恢复路径继续写旧版本。
- 生产页面覆盖值由发布子任务处理。

## Acceptance

- 所有 worker 类型默认和显式传递值为 2.1.257；WebUI 覆盖/清空语义、版本格式校验、
  安装失败行为和抓包隔离规则不回归；单元测试与两份 Compose 校验通过。

## Next Step

- Check-All 已通过；下一步进入 `trellis-update-spec`，再由 `trellis-push` 生成提交计划。
