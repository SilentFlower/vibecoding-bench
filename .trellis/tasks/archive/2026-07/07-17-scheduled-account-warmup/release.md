# 上线操作记录

## 结论

Needs human review：代码、配置和双系统部署已完成；仍需观察一次真实养号 run 完整进入终态，并在实际出现 401 时确认单次强制刷新恢复链路。

## 已核对证据

- `task.json`、`prd.md`、`design.md`、`implement.md`
- `implement.jsonl`、`check.jsonl`
- vibecoding-bench 业务提交 `3f99fd6`
- cc2api 业务提交 `33a46f5`
- 任务进度提交 `fb8e795`
- 本地与远程 Compose、镜像 digest、容器状态、HTTP 和 SQLite 迁移验证

## 漂移核对

- 原任务缺少 `release.md`，但存在明确的环境变量、双仓镜像和远程部署操作。
- 实际部署与 `remote-deploy.md`、`image-build-push.md` 记录的顺序和验证契约一致。

## SQL 变更

- 无需人工执行 SQL。
- orchestrator 启动时通过幂等 SQLite 迁移补齐养号字段和 `idx_accounts_cc2api_account_id` 唯一索引；远端已验证迁移成功。

## 配置变更

- 远端 bench `.env` 已配置 `CC2API_BASE_URL`、`CC2API_ADMIN_PASSWORD`、`CC2API_REQUEST_TIMEOUT_SEC=15`、`WARMUP_SCHEDULER_TICK_SEC=30`、`WARMUP_SYNC_RETRY_SEC=900`。
- cc2api 管理密码仅注入 orchestrator；worker 和 sidecar 镜像未包含该环境变量。
- 远端 bench 使用 `VIBEBENCH_TAG=fb8e795`。

## 批处理、部署脚本与数据修复

- cc2api 已拉取 GHCR `latest` 并使用 `--force-recreate` 重建，运行 revision 为 `33a46f51bb11241eca5bcbe893cbe8c7197ac317`。
- vibecoding-bench 已构建并发布 orchestrator、worker、sidecar 的 `latest` 与 `fb8e795` 标签，并使用 `--force-recreate` 重建 orchestrator。
- 远端 Compose、`.env.example` 和 WebUI 已同步。
- 无一次性数据修复脚本。

## 外部系统与依赖平台

- GitHub Actions 已成功构建并发布 cc2api 多架构镜像。
- DockerHub 已发布三套 bench 镜像的统一 `fb8e795` 标签。
- 远端 cc2api 与 vibecoding-bench 位于同一主机，bench 通过容器可达的宿主网关访问 cc2api。

## 上线顺序

1. 先发布并重建 cc2api，确认 revision 与 HTTP 200。
2. 再配置 bench 到 cc2api 的管理连接，并同步 Compose 与 WebUI。
3. 发布三套 bench 镜像的统一 SHA 标签。
4. 确认无活动 worker/sidecar 后重建 orchestrator。
5. 验证登录、账号列表、cc2api 账号列表、容器环境与 SQLite 迁移。

## 回滚说明

- bench：恢复 `/root/vibecoding-bench/.deploy-backups/20260717-054253` 中的 `.env`、Compose 和 WebUI，把 `VIBEBENCH_TAG` 恢复为 `88d778a`，再 `--force-recreate` orchestrator。
- cc2api：远端仍保留部署前镜像 ID `sha256:b6013f16bd5b668353d8d3ebc63423b8a77b1b2b0a20d7e4f4e9cbaff2cf5e41`；回滚时固定该镜像并重建服务。
- 两个系统的数据卷均未删除，回滚代码时保留现有账号、profile、run 历史和新增 SQLite 列。

## 上线后验证

- cc2api 与 bench 根路径均返回 HTTP 200，容器状态为 running。
- bench 登录、`/api/auth/me`、`/api/accounts`、`/api/cc2api/accounts` 均返回 200。
- orchestrator 容器到 cc2api 返回 HTTP 200。
- 养号字段和唯一绑定索引迁移成功。
- worker/sidecar 镜像中的 cc2api 管理密码环境变量计数为 0。
- 两个服务上线后最近日志错误计数为 0。
- 待观察：首个真实养号 run 的完整终态与下一次随机时间重排。
- 待观察：实际 401 场景下只强制刷新一次并最多重试一次。
