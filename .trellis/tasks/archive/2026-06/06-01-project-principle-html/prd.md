# 生成项目原理介绍 HTML

## Goal

生成一个独立的 HTML 页面，详细介绍 `vibecoding-bench` 项目的运行原理、核心架构、数据流和关键设计决策，方便新读者快速理解这个项目如何用真实 Claude Code 在容器中执行题库任务，并通过代理、调度和 WebUI 完成观测与管理。

## Background / Known Context

- 项目 README 描述该项目把 `topics.md` 中的 300 道题作为题库，让真实 Claude Code 在容器中运行。
- 当前架构包含静态 HTML WebUI、FastAPI + SQLite + Docker SDK 的 Orchestrator、sidecar 透明代理容器、worker 执行容器。
- 每次运行会启动 sidecar 与 worker 两个容器，worker 共享 sidecar 的 network namespace，使流量经过 `hev-socks5-tunnel` 与 mitmproxy。
- 项目通过 OAuth 账号 profile、tmux 驱动交互式 `claude`、Stop hook、transcript 抓取、MITM flow 落盘、SSE 状态推送等机制完成任务执行与观测。
- 已有前端是 `webui/index.html`、`webui/style.css`、`webui/app.js`，README 中已有项目架构图、启动说明、WebUI 用途、关键决策、目录结构、P1/P2/P3 范围和已知限制。

## Requirements

- 产出一个可直接在浏览器打开的 HTML 页面，用中文详细介绍项目原理。
- 页面必须覆盖项目目标、整体架构、一次任务从创建到完成的生命周期、账号与并发调度、sidecar/worker 协作、透明代理与 TLS MITM、数据落盘、WebUI 与 SSE 实时更新、关键配置和已知限制。
- 内容必须基于仓库已有代码、README 和配置，不得编造不存在的模块、字段或能力。
- 页面应具备清晰的信息层级，适合新开发者或评审者阅读；可以包含架构图、流程图、模块说明、时序说明、关键文件索引等。
- HTML 应为静态页面，不引入复杂构建流程；如需要 CSS/JS，应优先保持简单、可维护，并遵循现有 WebUI 的静态资源风格。
- 页面文字、代码注释和文档内容必须使用中文。
- 不改变现有运行逻辑、数据库结构、容器编排或 API 行为。

## Acceptance Criteria

- [ ] 仓库中新增或更新一个静态 HTML 页面，页面可直接打开并完整展示项目原理说明。
- [ ] 页面包含项目目标、架构组成、任务执行链路、容器网络链路、数据流、关键文件与配置、已知限制等核心内容。
- [ ] 页面内容与 README 及代码实现一致，没有使用未经确认的字段、接口或功能。
- [ ] 页面在桌面和移动视口下文本不溢出、不互相遮挡，结构清晰可读。
- [ ] 如页面引用现有图片或新增视觉元素，路径有效，浏览器无明显资源加载错误。
- [ ] 变更不影响现有 WebUI 的账号、题库、任务、运行等页面功能。

## Definition of Done

- 静态页面实现完成并通过浏览器或本地静态服务验证。
- 如修改现有前端资源，完成必要的手动冒烟检查。
- 运行相关轻量检查；若仓库无前端构建或测试命令，记录已执行的替代验证方式。
- 任务进入实现前，应先补充实现计划或在轻量任务模式下确认 PRD 足够。

## Out of Scope

- 不实现新的调度、代理、账号、数据库或评测功能。
- 不重写现有 WebUI 信息架构。
- 不新增后端 API。
- 不接入外部文档站点生成器或复杂前端框架。

## Research References

- `README.md`
- `webui/index.html`
- `webui/style.css`
- `webui/app.js`
- `docker-compose.yml`
- `orchestrator/main.py`
- `images/sidecar/start.sh`
- `images/worker/entrypoint.sh`
