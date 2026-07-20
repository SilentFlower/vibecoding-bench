# 将 vibecoding-bench 打包改造为 GitHub Action

## Goal

将 vibecoding-bench 当前依赖人工执行的三镜像构建与发布流程迁移到仓库内的 GitHub Actions workflow，使 `main` 变更能够稳定地产出 GHCR 多架构镜像，并继续支持远程 Compose 通过 `VIBEBENCH_TAG` 跟随最新版本或锁定提交版本。

## Background

- 主仓当前没有 `.github/workflows/`，也没有历史 GitHub Actions 配置。
- 本地通过 `docker compose --profile build build` 构建三个镜像：
  - `vibebench-orchestrator`，构建上下文为 `orchestrator/`。
  - `vibebench-worker`，构建上下文为 `images/worker/`。
  - `vibebench-sidecar`，构建上下文为 `images/sidecar/`。
- 远程部署由 `docker-compose.remote.yml` 拉取三个预构建镜像，当前地址为 `huajiwuyan/vibebench-*:${VIBEBENCH_TAG:-latest}`。
- `.env.example` 已约定 `latest` 跟随主分支构建，短 Git SHA tag 用于锁定版本和回滚。
- `cc2api` 子模块已有 GitHub Actions 先例，使用 Buildx、GitHub Actions cache，并构建 `linux/amd64,linux/arm64` 镜像。
- `topics.md` 与 `webui/` 刻意不烤入 orchestrator 镜像，远程部署仍需随仓库提供这些 bind mount 文件。
- GitHub 仓库 `SilentFlower/vibecoding-bench` 当前为 public，镜像 registry 确定迁移到 `ghcr.io/silentflower/`。
- GHCR 新 package 首次发布默认 private；三个 package 确定在首次发布后手动设为 public，以保持远程主机匿名拉取。

## Requirements

- 在主仓新增 GitHub Actions workflow，自动构建并推送 orchestrator、worker、sidecar 三个 Docker 镜像。
- 每次 push 到 `main` 自动发布，同时保留仅针对 `main` ref 的 `workflow_dispatch` 手动触发。
- 三个镜像必须来自当前仓库中各自既有 Dockerfile 和构建上下文，不改变应用运行边界。
- 主分支和手动构建必须产出 `latest` 和可回滚的原始短提交 SHA tag（例如 `9787fc1`），三个镜像使用同一组 tag。
- 三个镜像必须同时发布 `linux/amd64`、`linux/arm64` manifest。
- 使用 Docker Buildx 与 GitHub Actions cache，避免每次从零构建三个镜像。
- 远程 `docker-compose.remote.yml` 必须能消费 workflow 生成的镜像和 tag。
- workflow 权限和凭据按最小权限配置，不得把 registry token 写入仓库文件或日志。
- 使用 GitHub Actions 提供的 `GITHUB_TOKEN` 登录 GHCR，workflow 仅申请 `contents: read` 与 `packages: write` 权限。
- 将远程 Compose 中三个镜像地址迁移到 `ghcr.io/silentflower/vibebench-*`。
- 文档需说明触发条件、所需 Secrets、镜像命名、tag 规则和远程升级方式。

## Acceptance Criteria

- [ ] GitHub Actions 能在每次 push 到 `main` 和手动触发时运行三镜像构建发布流程。
- [ ] orchestrator、worker、sidecar 均成功发布 `latest` 与当前提交对应的原始 7 位短 SHA tag。
- [ ] 三个镜像均发布 `linux/amd64`、`linux/arm64` 多架构 manifest。
- [ ] `docker-compose.remote.yml` 使用默认 `latest` 和显式短 SHA tag 时都能解析为 workflow 实际发布的镜像。
- [ ] workflow 使用缓存并设置并发控制，新的同分支构建可以取消旧的未完成构建。
- [ ] Secrets 只通过 GitHub Actions secret/context 注入，日志和版本库中不出现明文 token。
- [ ] 远程部署不再依赖 Docker Hub 凭据或 `DOCKERHUB_*` Secrets。
- [ ] 三个 GHCR package 均设为 public，未登录 GHCR 的远程主机可以直接 pull。
- [ ] README 或部署规范包含首次配置和日常发布/回滚说明。

## Out of Scope

- 自动 SSH 到远程服务器并执行部署。
- 将 `topics.md`、`webui/` 或运行时 `data/` 烤入镜像。
- 改造 `cc2api` 子模块自己的构建发布 workflow。
- 创建 GitHub Marketplace 可复用 JavaScript/Docker Action；本任务目标是仓库内 CI/CD workflow。
