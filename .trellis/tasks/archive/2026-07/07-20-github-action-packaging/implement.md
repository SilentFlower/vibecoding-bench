# 将 vibecoding-bench 打包改造为 GitHub Action - 实施计划

## 实施步骤

1. 新增三镜像发布 workflow。
   - 创建 `.github/workflows/docker-publish.yml`。
   - 配置 `main` push、`workflow_dispatch`、最小权限和并发取消。
   - 使用 orchestrator / worker / sidecar matrix，统一发布 `latest` 与原始 7 位短 SHA tag。
   - 使用 QEMU + Buildx 构建 `linux/amd64,linux/arm64`，按镜像隔离 GHA cache scope。

2. 迁移远程 Compose 到 GHCR。
   - 修改 `docker-compose.remote.yml` 中 orchestrator、worker、sidecar 三个镜像地址。
   - 保持单一 `VIBEBENCH_TAG` 和默认 `latest` 语义不变。

3. 更新使用文档与部署规范。
   - 更新 `.env.example` 的 registry、tag 和回滚说明。
   - 在 README 增加自动构建、镜像地址、手动触发和短 SHA 回滚入口。
   - 将 `.trellis/spec/vibecoding-bench/deploy/index.md`、`image-build-push.md`、`remote-deploy.md` 从人工 Docker Hub 发布流程更新为 GitHub Actions + GHCR。
   - 明确首次 workflow 成功后需要把三个 package 手动设为 public，并验证匿名 pull。

4. 静态验证 workflow 与部署配置。
   - 使用 YAML / GitHub Actions linter 检查 workflow 语法和 expression。
   - 检查 workflow action 主版本、permissions、事件、matrix、platforms、cache scope 和 tags。
   - 运行 `docker compose -f docker-compose.remote.yml --env-file .env.example config --quiet`。
   - 检查 `docker compose ... config --images` 输出 GHCR orchestrator service image，并检查完整 `config` 中 `WORKER_IMAGE`、`SIDECAR_IMAGE` 同样指向 GHCR；worker/sidecar 由 orchestrator 通过 Docker SDK 启动，不是 Compose service。
   - 搜索部署路径中的旧 `huajiwuyan/vibebench-*` 引用，确认除迁移说明外不再作为现行地址。

5. 构建与发布验收。
   - 在本地环境允许时对三个 Dockerfile 至少执行 `linux/amd64` 构建冒烟；若没有 Docker daemon，明确记录未执行原因。
   - 合并/推送后观察 GitHub Actions 三个矩阵项均成功。
   - 验证三个 GHCR package 同时存在 `latest` 与本次 7 位短 SHA tag，并包含 amd64/arm64 manifest。
   - 把三个 package 设为 public 后，在未登录 GHCR 的环境执行 pull 验证。

## 高风险文件

- `.github/workflows/docker-publish.yml`
- `docker-compose.remote.yml`
- `.env.example`
- `.trellis/spec/vibecoding-bench/deploy/image-build-push.md`
- `.trellis/spec/vibecoding-bench/deploy/remote-deploy.md`

## 回滚点

- workflow 有误时撤回 `.github/workflows/docker-publish.yml`，不会影响已有 Docker Hub 镜像。
- GHCR 镜像不可用时回退到改造前提交，使远程 Compose 恢复旧 Docker Hub 地址。
- 已发布但行为异常时，将 `VIBEBENCH_TAG` 固定到上一次成功的短 SHA tag，再 pull/recreate。

## 实现后检查

- 三个镜像名称、tag 与 `docker-compose.remote.yml` 完全一致。
- `workflow_dispatch` 非 `main` ref 不覆盖 `latest`。
- workflow 不引用 Docker Hub 用户名、token 或 PAT。
- 文档不声称 workflow 能自动把 GHCR package 改成 public。
- `topics.md`、`webui/`、`data/` 仍未进入镜像构建上下文或自动上传产物。
