# Release Operations

## Conclusion

Release operations exist. 当前代码和本地检查已完成，但首次 GHCR 发布仍需等待 GitHub Actions 服务恢复后重新运行，并完成人工公开 Package 与远程拉取验证。

## Evidence Checked

- `task.json`
- `prd.md`
- `design.md`
- `implement.md`
- `implement.jsonl`
- `check.jsonl`
- Git 提交 `dd954ce`、`a81670f`、`71ead6f` 及其变更文件
- `.github/workflows/docker-publish.yml`
- `docker-compose.remote.yml`
- `README.md`

## Drift Check

Missing release.md. 任务材料和实际提交都明确包含 GHCR 首次发布、Package 可见性切换、匿名拉取与远程部署操作，因此补充本发布操作单。

## SQL Changes

None.

## Configuration Changes

- 首次成功发布后，在 GitHub Packages 设置中将以下三个 GHCR Package 分别设为 Public：
  - `vibebench-orchestrator`
  - `vibebench-worker`
  - `vibebench-sidecar`
- 远程 `.env` 可不设置 `VIBEBENCH_TAG` 以跟随 `latest`；需要锁定或回滚时，设置为一次成功 workflow 对应的原始 7 位短 SHA。
- 不需要新增 Docker Hub 或 GHCR PAT；workflow 使用仓库提供的 `GITHUB_TOKEN`，公开后远程主机应保持匿名拉取。

## Batch / Deployment Scripts / Data Repair

- GitHub Actions 服务恢复后，重新运行“构建并发布 Docker 镜像” workflow，确认 orchestrator、worker、sidecar 三个矩阵 job 全部成功。
- 远程仓库更新到包含 `docker-compose.remote.yml` GHCR 地址的版本后执行：

  ```bash
  docker compose -f docker-compose.remote.yml --env-file .env pull
  docker compose -f docker-compose.remote.yml --env-file .env up -d --force-recreate orchestrator
  ```

- 不涉及数据修复或一次性数据库脚本。

## External Systems / Dependent Platforms

- GitHub Actions：本次首次触发期间发生官方服务故障，运行 `#1`、`#2`、`#3` 均在创建 job 前以 `startup_failure` 结束；服务恢复后需要重新触发。
- GitHub Container Registry：首次成功构建会创建三个 Package，必须由仓库所有者手动改为 Public，公开后再从未登录 GHCR 的环境验证匿名拉取。

## Release Order

1. 确认 GitHub Actions 服务恢复并重新触发 workflow。
2. 确认三个镜像都同时生成 `latest` 和同一原始 7 位短 SHA tag，并包含 `linux/amd64`、`linux/arm64` manifest。
3. 将三个 GHCR Package 设为 Public。
4. 在未登录 GHCR 的环境验证三个镜像均可匿名拉取。
5. 更新远程仓库并执行 Compose pull 与 orchestrator 重建。

## Rollback Notes

- 已发布版本异常时，将远程 `.env` 的 `VIBEBENCH_TAG` 固定到上一次成功发布的 7 位短 SHA，再 pull 并重建 orchestrator。
- GHCR 首次迁移不可用时，可回退到迁移前提交 `93b0160`，恢复使用原 Docker Hub 镜像；不要删除现有 Docker Hub 镜像。
- GHCR Package 改为 Public 后不能恢复为 Private，执行公开操作前必须确认镜像命名和归属正确。

## Post-release Verification

- 三个矩阵 job 均成功，且没有部分镜像单独更新 `latest` 的情况。
- `ghcr.io/silentflower/vibebench-orchestrator`、`vibebench-worker`、`vibebench-sidecar` 均存在 `latest` 与同一短 SHA tag。
- 三个镜像 manifest 都包含 `linux/amd64` 和 `linux/arm64`。
- 未登录 GHCR 的环境可以 pull 三个公开镜像。
- 远程 Compose 能启动 orchestrator，且 orchestrator 能通过 `WORKER_IMAGE`、`SIDECAR_IMAGE` 创建对应 sibling 容器。
