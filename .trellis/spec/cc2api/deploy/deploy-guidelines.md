# cc2api Deploy Guidelines

## 构建形态

`cc2api` 交付物有两种：

- 单二进制：`scripts/build.sh` / `scripts/build.bat` 先构建 `web/dist`，再构建 Rust 后端。
- Docker 镜像：`docker/Dockerfile` 分三段构建 frontend、backend、runtime。

前端资源是构建时产物；改 `web/` 后必须重新 build，不能只重启旧二进制。

## 本地开发

```bash
cd cc2api
./scripts/dev.sh
```

脚本会在需要时构建前端，再 `cargo run`。如果只改后端但前端 dist 过期，仍要让脚本处理。

## Docker Compose

`cc2api/docker/docker-compose.yml` 默认服务名：

```text
claude-code-gateway
```

默认端口来自 `SERVER_PORT`，服务内监听 `5674`。容器数据在 `claude-code-gateway-data` volume 的 `/app/data`，默认 SQLite DB 位于该目录下。

## 远程部署规则

- 远程环境变量通常由本仓 `.deploy/cc2api.env` 记录 SSH 信息；不要把密码或 token 写入 spec、README 或任务日志。
- 部署前确认子模块提交已推送到 `https://github.com/SilentFlower/cc2api.git`，父仓只固定 gitlink。
- 镜像升级后必须 recreate 服务，不能只 `docker compose pull`。
- 涉及 `canonical_env`、settings、allowed versions 的改动，部署后必须查 DB 分布，不只看容器 `Up`。
- 远程时区使用 `TZ=Asia/Shanghai`，峰值预热依赖本地小时。

## 验证清单

部署后至少检查：

```bash
docker compose ps
curl http://127.0.0.1:<port>/
```

涉及网关行为时再检查：

- `/admin/settings` 中新 setting 是否存在并保存后生效。
- `accounts.canonical_env.version/version_base/build_time` 是否符合目标默认画像。
- `/v1/messages` 本地拒绝、上游 429、流式 keepalive 等行为是否符合本次变更。
- 容器日志无 token、Cookie、完整 prompt 或完整响应正文。

## Common Mistakes

| 反模式 | 风险 | 正确做法 |
|--------|------|----------|
| 改前端后只重启后端 | 旧 `web/dist` 仍被嵌入 | 重新 `npm run build` 和后端构建 |
| 子模块未推送就提交父仓 gitlink | 其他机器无法拉取提交 | 先推 `cc2api`，再提交父仓 |
| 只看容器 Up | DB/settings 可能仍旧值 | 查 DB 和 API 行为 |
| 在日志/文档写远程密码 | 凭据泄露 | 只记录路径和脱敏摘要 |
