# 将 vibecoding-bench 打包改造为 GitHub Action - 技术设计

## 架构边界

本任务只改造三镜像的构建与发布链路，不改变 orchestrator、worker、sidecar 的运行职责，也不自动登录远程主机部署。`topics.md`、`webui/` 和 `data/` 继续保留现有 bind mount / 运行时数据边界。

交付物包括：

- `.github/workflows/docker-publish.yml`：构建并发布三镜像。
- `docker-compose.remote.yml`：镜像地址从 Docker Hub 迁移到 GHCR。
- `.env.example`、README 与部署规范：同步 registry、tag、首次公开 package 和升级/回滚说明。

## Workflow 触发与权限

workflow 在以下事件触发：

- push 到 `main`。
- `workflow_dispatch` 手动触发。

手动触发只允许对 `main` ref 执行发布 job，避免从功能分支覆盖 `latest`。使用并发组 `docker-publish-${{ github.ref }}`，新运行取消同 ref 尚未完成的旧运行。

最小权限固定为：

```yaml
permissions:
  contents: read
  packages: write
```

GHCR 登录使用 `${{ github.actor }}` 和 `${{ secrets.GITHUB_TOKEN }}`，不新增 PAT 或 Docker Hub Secrets。

## 镜像矩阵

单个 workflow job 使用 matrix 构建三个镜像：

| matrix key | GHCR image | context | Dockerfile |
| --- | --- | --- | --- |
| `orchestrator` | `ghcr.io/silentflower/vibebench-orchestrator` | `orchestrator` | `orchestrator/Dockerfile` |
| `worker` | `ghcr.io/silentflower/vibebench-worker` | `images/worker` | `images/worker/Dockerfile` |
| `sidecar` | `ghcr.io/silentflower/vibebench-sidecar` | `images/sidecar` | `images/sidecar/Dockerfile` |

每个矩阵项都构建 `linux/amd64,linux/arm64`。现有基础镜像支持这两个平台，sidecar Dockerfile 也已显式映射 `x86_64` 与 `aarch64` 的 hev-socks5-tunnel 二进制。

即使只有一个镜像目录发生变化，也构建并发布全部三个镜像。原因是部署侧只有一个 `VIBEBENCH_TAG`，现有锁定契约要求同一提交的三个镜像 tag 始终齐全。

## Action 版本与缓存

采用 2026-07-20 官方文档当前主版本：

- `actions/checkout@v6`
- `docker/setup-qemu-action@v4`
- `docker/setup-buildx-action@v4`
- `docker/login-action@v4`
- `docker/metadata-action@v6`
- `docker/build-push-action@v7`

每个镜像使用独立 GitHub Actions cache scope，避免三个矩阵项相互覆盖：

```text
type=gha,scope=vibebench-<image>
```

缓存写入使用 `mode=max`，保留 Dockerfile 中可复用的依赖层。

## Tag 与镜像元数据

每个镜像同时发布：

- `latest`：跟随 `main` 最新成功构建。
- `<git-sha-short>`：原始 7 位短 SHA，例如 `158b462`。

短 SHA 不加 `sha-` 前缀，继续兼容 `.env.example`、远程部署规范和已有 `VIBEBENCH_TAG=<git-sha-short>` 用法。`docker/metadata-action` 使用 raw `latest` 与 `type=sha,prefix=` 生成标签，并输出 OCI source/revision 等 labels，使 package 自动关联当前仓库。

## GHCR 可见性

workflow 首次推送后，三个新 package 默认是 private。需要在 GitHub package settings 中把它们分别改成 public：

- `vibebench-orchestrator`
- `vibebench-worker`
- `vibebench-sidecar`

这是一次性人工发布门槛。公开后，远程服务器继续匿名执行 `docker compose pull`，不需要保存 GHCR PAT。文档必须明确 package 公开后不能再改回 private。

## 远程部署与回滚

`docker-compose.remote.yml` 的三个地址迁移为：

```text
ghcr.io/silentflower/vibebench-orchestrator:${VIBEBENCH_TAG:-latest}
ghcr.io/silentflower/vibebench-worker:${VIBEBENCH_TAG:-latest}
ghcr.io/silentflower/vibebench-sidecar:${VIBEBENCH_TAG:-latest}
```

日常升级仍执行 `git pull`、`docker compose pull`、`up -d --force-recreate orchestrator`。需要回滚时，在 `.env` 中把 `VIBEBENCH_TAG` 设为某次成功 workflow 的 7 位短 SHA，再 pull/recreate。

registry 迁移失败时，可回退到改造前提交并继续使用原 Docker Hub 镜像；不删除 Docker Hub 旧镜像。

## 风险与约束

- `latest` 只有在三个矩阵项全部成功时才算一套完整发布；矩阵部分失败可能让成功项先更新 `latest`。部署时优先使用短 SHA，可避免拉到混合构建。后续如需原子更新 `latest`，应改成按平台推 digest、汇总 manifest 的两阶段 workflow，本任务不先引入该复杂度。
- worker 多架构构建体积大，QEMU 下 arm64 构建会明显慢于 amd64；独立 cache scope 用于降低后续耗时。
- GHCR package 首次发布后的 public 切换不是 workflow 自动完成项，首次上线前必须按文档操作并验证匿名 pull。
- `workflow_dispatch` 从非 `main` ref 触发时发布 job 会跳过，这是保护 `latest` 的预期行为。

