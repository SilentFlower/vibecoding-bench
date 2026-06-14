# cc2api Spec Package

`cc2api/` 是本仓的 Git submodule，远程仓库为 `https://github.com/SilentFlower/cc2api.git`。本 package 下的 spec 按层拆分：

| Layer | Scope |
|-------|-------|
| [backend](./backend/index.md) | Rust Axum 后端、Gateway 热路径、settings、DB、测试 |
| [frontend](./frontend/index.md) | Vue 3 + TypeScript 管理后台、API client、设置页 |
| [deploy](./deploy/index.md) | 构建、Docker、远程部署、环境变量和部署验收 |
| [protocol](./protocol/index.md) | Claude Code / Anthropic wire protocol 画像、CCH、`cc_version`、bootstrap、telemetry |

跨层任务通常至少读取 `backend` 和具体目标层；涉及 Claude Code 版本或 wire 字段时必须读取 `protocol`。
