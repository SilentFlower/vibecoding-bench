# Release Operations

## Conclusion
Release operations exist.

## SQL Changes
SQLite 新增 `app_settings` 表，用于保存 WebUI 运行页的默认模型覆盖值。由 orchestrator 启动时的 `init_db()` 幂等创建，无需手工 SQL。

## Configuration Changes
新增 / 更新 `CLAUDE_DEFAULT_MODEL` 作为普通 run 和批量 run 的兜底默认模型。WebUI 运行页保存的页面覆盖值优先于 `.env`，清空页面覆盖后回退到 `.env`。

## Batch / Deployment Scripts / Data Repair
已构建并推送 DockerHub 三镜像的 `latest` 和 `30f52db` tag：
- `huajiwuyan/vibebench-orchestrator:30f52db`
- `huajiwuyan/vibebench-worker:30f52db`
- `huajiwuyan/vibebench-sidecar:30f52db`

已远端部署到 `23.80.83.23:/root/vibecoding-bench`，并将远端 `.env` 的 `VIBEBENCH_TAG` 更新为 `30f52db`。

## External Systems / Dependent Platforms
DockerHub 镜像仓库需要发布三镜像同一 git sha tag。远端 Docker 主机需要 pull `30f52db` 并 recreate orchestrator。

## Release Order
1. 推送代码到 `origin/main`。
2. 构建并推送 DockerHub 三镜像的 `latest` 和 git sha tag。
3. 同步远端 `docker-compose.remote.yml`、`topics.md`、`webui/`。
4. 更新远端 `.env` 的 `VIBEBENCH_TAG`。
5. 远端 `docker compose pull` 后 `up -d --force-recreate orchestrator`。

## Rollback Notes
把远端 `.env` 的 `VIBEBENCH_TAG` 改回上一版 tag（例如 `9d263a6`），然后执行 `docker compose -f docker-compose.remote.yml --env-file .env up -d --force-recreate orchestrator`。SQLite 中的 `app_settings` 表可保留，旧版本不会使用该表。

## Post-release Verification
已验证：
- 远端 `/` 返回 200。
- 未登录访问 `/api/topics` 返回 401。
- 登录后 `/api/settings/runtime-model` 返回当前默认模型设置。
- 远端 orchestrator、worker、sidecar 镜像 tag 均为 `30f52db`。
