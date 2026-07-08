# Release Operations

## Conclusion
Release operations exist.

## Evidence Checked
- task.json
- prd.md
- design.md
- implement.md
- implement.jsonl
- check.jsonl
- git commits `b2233c4`、`d46ded4`
- 远程部署验证输出

## Drift Check
Missing release.md. 已按本次实际发布动作补齐。

## SQL Changes
无人工 SQL 需要执行。

本次代码在 orchestrator 启动时通过幂等迁移为 `accounts` 补 `deleted_at REAL`，远程 recreate 后由应用启动路径自动处理。

## Configuration Changes
远程 `/root/vibecoding-bench/.env` 已将 `VIBEBENCH_TAG` 从旧 tag 切到 `d46ded4`，备份为 `.env.bak-deploy-20260708-020018`。

## Batch / Deployment Scripts / Data Repair
已执行本次部署操作：

- 本地构建 `vibebench-orchestrator:latest`。
- 为 `orchestrator`、`worker`、`sidecar` 三镜像打 `latest` 和 `d46ded4` 双 tag。
- 推送 DockerHub `huajiwuyan/vibebench-{orchestrator,worker,sidecar}:latest` 与 `:d46ded4`。
- 远程部署目录不是 git 仓库，已备份并同步 bind mount 文件 `webui/` 与 `docker-compose.remote.yml`。
- 远程显式拉取三镜像 `d46ded4`，并执行 `docker compose -f docker-compose.remote.yml --env-file .env up -d --force-recreate orchestrator`。

## External Systems / Dependent Platforms
涉及 DockerHub 镜像仓库和远程 VPS `23.80.83.23` 上的 vibebench 实例。

## Release Order
1. 推送代码提交 `b2233c4` 和任务快照提交 `d46ded4`。
2. 构建并推送三镜像 `latest` / `d46ded4`。
3. 同步远程 bind mount 前端文件。
4. 更新远程 `VIBEBENCH_TAG=d46ded4`。
5. 拉取三镜像并 force recreate orchestrator。
6. 执行 HTTP 与日志验证。

## Rollback Notes
可将远程 `.env` 的 `VIBEBENCH_TAG` 改回上一版本 `b0e01bb`，然后重新拉取并执行：

```bash
docker compose -f docker-compose.remote.yml --env-file .env pull
docker compose -f docker-compose.remote.yml --env-file .env up -d --force-recreate orchestrator
```

如需回滚前端 bind mount 文件，可使用远程备份 `webui.bak-deploy-20260708-015921` 恢复。

## Post-release Verification
已验证：

- 远程 orchestrator 容器镜像为 `huajiwuyan/vibebench-orchestrator:d46ded4`。
- 容器 image digest 为 `sha256:d821e3e577c905195005649a9a1fc5e508697f097b216b62bfa3d618245d6972`。
- 远程 `GET /` 返回 `200`。
- 远程 `GET /api/topics` 返回 `401`，符合启用鉴权时的预期。
- 日志包含 `Application startup complete`，未见启动错误。
- 公网 `http://23.80.83.23:8080/` 返回 `200`。
- 远程 `webui/app.js` 与本地 checksum 一致，旧删除提示文案不存在。
