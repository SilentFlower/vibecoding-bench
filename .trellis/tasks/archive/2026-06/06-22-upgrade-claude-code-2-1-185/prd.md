# 升级 vibecoding-bench 到 Claude Code 2.1.185

## Goal

将 vibecoding-bench 主项目运行 Claude Code 的默认版本从 `2.1.173` 升级到 `2.1.185`，构建并推送远程可用镜像，用于后续启动 worker 抓包观察新版本行为。

## Background / Known Context

- 主项目当前在 worker 镜像、compose 默认环境变量、entrypoint 和 orchestrator 中默认使用 `2.1.173`。
- 本次目标是先让 vibecoding-bench worker 安装并运行 Claude Code `2.1.185`，然后通过现有抓包链路观察新版本行为。
- cc2api 的默认版本画像、访问策略、CCH 逻辑和管理端默认值暂不升级，避免在抓包前引入额外变量。
- 远程部署当前通过 `.deploy/vibercoding-bench.env` 管理 SSH 信息，远程 `.env` 会锁定 `VIBEBENCH_TAG` 和 `CLAUDE_CODE_VERSION`。

## Requirements

- 将主项目默认使用的 Claude Code 版本升级到 `2.1.185`。
- 保持 worker 镜像安装版本、compose 默认环境变量、entrypoint fallback、orchestrator 默认版本和 usage 请求 User-Agent 的版本来源一致。
- 保持 Claude Code 启动、登录、抓包、任务调度和现有 worker 行为不变。
- 不修改 cc2api 目录下的默认版本画像、访问策略、请求改写逻辑、管理端默认值或 README。
- 更新必要的主项目检查，确保 vibecoding-bench 默认运行版本不再停留在 `2.1.173`。
- 本地构建并推送 vibebench orchestrator / worker / sidecar 三镜像到 DockerHub，远程部署使用同一组部署 tag。
- 远程重新部署前暂停 active 批次和正在运行的 queued/running run，避免部署过程中继续调度或硬切正在跑的任务。
- 远程 `.env` 需要同步 `VIBEBENCH_TAG` 和 `CLAUDE_CODE_VERSION`，避免新镜像被旧环境变量覆盖。

## Acceptance Criteria

- [ ] 主项目配置中 Claude Code 默认版本不再引用 `2.1.173` 作为当前默认值。
- [ ] `images/worker/Dockerfile` 默认安装 `@anthropic-ai/claude-code@2.1.185`。
- [ ] `.env.example`、`docker-compose.yml`、`docker-compose.remote.yml`、`images/worker/entrypoint.sh` 和 `orchestrator/main.py` 默认版本均为 `2.1.185`。
- [ ] `cc2api/` 目录下的默认版本画像、访问策略和文档不因本任务改变。
- [ ] 相关 Python 检查通过，关键配置搜索结果符合预期。
- [ ] DockerHub 上存在远程部署使用的 orchestrator / worker / sidecar 镜像 tag。
- [ ] 远程 `vibecoding-bench` 使用新镜像 tag 和 `CLAUDE_CODE_VERSION=2.1.185` 重建启动。
- [ ] 远程 worker 镜像内 `claude --version` 输出 `2.1.185 (Claude Code)`。
- [ ] 远程部署前 active 批次已暂停，部署后没有 queued/running run。

## Out of Scope

- 不升级 Node、Python、Rust、mitmproxy、Docker base image 或其他基础依赖。
- 不升级 cc2api 默认 Claude Code 指纹、允许版本范围、CCH 算法、请求改写逻辑、管理端默认值或 README。
- 不重新逆向 Claude Code `2.1.185` 的新抓包字段、build time、beta token 或 CCH 算法。
- 不修改 Claude Code 运行时策略、认证流程、抓包逻辑、UI 交互或任务调度行为。
- 不自动恢复已暂停批次；恢复由后续抓包计划决定。

## Notes

- 这是轻量任务，PRD-only 足够。
