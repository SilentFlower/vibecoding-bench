# Brief — 将 vibecoding-bench 打包改造为 GitHub Action

## Goal

- 将三镜像人工构建发布迁移为 `main` 自动触发的 GitHub Actions + GHCR 多架构发布流程，并保留 `latest` 与原始 7 位短 SHA 的部署/回滚语义。

## Scope

- 新增 `.github/workflows/docker-publish.yml`，用 matrix 构建 orchestrator、worker、sidecar。
- 三个镜像统一发布到 `ghcr.io/silentflower/vibebench-*`，平台为 `linux/amd64,linux/arm64`。
- push 到 `main` 自动发布；保留仅针对 `main` ref 的 `workflow_dispatch`。
- 使用 `GITHUB_TOKEN`、最小 `contents: read` / `packages: write` 权限、并发取消和独立 GHA cache scope。
- 更新 `docker-compose.remote.yml`、`.env.example`、README 和 vibecoding-bench 部署规范。
- 首次发布后将三个 GHCR package 手动设为 public，并验证匿名 pull。

## Non-Goals

- 不自动 SSH 到远程服务器部署。
- 不把 `topics.md`、`webui/` 或 `data/` 烤入镜像。
- 不修改 `cc2api` 子模块的 workflow。
- 不创建 GitHub Marketplace 可复用 Action。

## Key Context

- 三镜像构建上下文分别为 `orchestrator/`、`images/worker/`、`images/sidecar/`。
- 远程部署只有一个 `VIBEBENCH_TAG`；即使仅一个镜像变化，也必须给三个镜像发布同一短 SHA tag，保证套件完整。
- 短 SHA 必须保持无 `sha-` 前缀的 7 位格式，兼容现有 `.env.example` 和部署规范。
- workflow 使用当前官方主版本：`actions/checkout@v6`、Docker setup/login actions `@v4`、metadata `@v6`、build-push `@v7`。
- GHCR package 首次发布默认 private，改为 public 是一次性人工门槛，不能声称 workflow 自动完成。
- matrix 部分失败可能使成功镜像先更新 `latest`；部署优先使用完整成功运行的短 SHA tag，本任务不引入两阶段原子 manifest 发布。

## Acceptance

- `main` push 和 `main` ref 手动触发均能运行三镜像发布。
- 三个 GHCR 镜像均包含 `latest`、当前原始 7 位短 SHA、amd64/arm64 manifest。
- 远程 Compose 默认 `latest` 和显式短 SHA 均解析到实际 GHCR 镜像。
- workflow 使用最小权限、GHA cache 和并发取消，不需要 Docker Hub Secrets 或额外 PAT。
- 三个 package 设为 public 后，未登录 GHCR 的环境可以直接 pull。
- README 和部署规范覆盖首次配置、日常升级和短 SHA 回滚。

## Next Step

- 用户确认 planning artifacts 和本 brief 后，运行 `task.py start`，再通过 `trellis-route(target=implement)` 进入实现。
