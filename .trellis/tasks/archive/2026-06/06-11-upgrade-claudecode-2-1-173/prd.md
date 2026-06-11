# 升级 Claude Code 到 2.1.173

## Goal

将 vibebench 当前使用的 Claude Code 版本升级到 2.1.173，并完成必要验证。

## Requirements

- 将项目默认使用的 Claude Code 版本从 `2.1.172` 升级到 `2.1.173`。
- 保持 worker 镜像安装版本、远程 compose 默认环境变量、orchestrator 默认版本和 usage 请求 User-Agent 的版本来源一致。
- 不改变 Claude Code 启动、登录、抓包、任务调度等既有行为。

## Acceptance Criteria

- [ ] 代码库中 Claude Code 默认版本不再引用 `2.1.172`。
- [ ] `images/worker/Dockerfile` 默认安装 `@anthropic-ai/claude-code@2.1.173`。
- [ ] `docker-compose.remote.yml` 和 `orchestrator/main.py` 默认版本均为 `2.1.173`。
- [ ] Python 语法检查通过，关键配置搜索结果符合预期。

## Out of Scope

- 不升级 Node、Python、mitmproxy 或其他基础依赖。
- 不重建或推送 Docker 镜像。
- 不修改 Claude Code 运行时策略、认证流程、抓包逻辑或 UI 文案。

## Notes

- 这是轻量任务，PRD-only 足够。
