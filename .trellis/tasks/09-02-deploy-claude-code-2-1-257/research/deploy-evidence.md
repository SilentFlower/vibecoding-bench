# Claude Code 2.1.257 部署证据

## 发布门禁

- cc2api 提交：`84b0016`，GitHub Actions run `33590271857` 成功。
- cc2api 镜像：`ghcr.io/silentflower/claude-code-gateway:sha-84b0016`。
- cc2api digest：`sha256:8e179390f7c7fafe8cc2be629016fe80ef09eba9db53ba51f69345a0d9c4dc97`。
- vibecoding-bench 发布提交：`e03b8e1`，GitHub Actions run `33604936337` 成功。
- orchestrator digest：`sha256:dc2d6ada11193d5ccfbae70021d864a5443801b45e83bbeda2d6622ea123e245`。
- worker digest：`sha256:a80133c0c9c7dc96d98b7545d0cef7a77931bcea92d9d82e5930aff97532e0ec`。
- sidecar digest：`sha256:bea25bc648ecc0a921b3321e1669067528b91eebaf888f9d4a633c6d9059381f`。

## 部署前基线

- 目标：`us.flower-cli.com`，DNS 解析到 `23.80.83.23`。
- cc2api 旧 image ID：`sha256:87415cde63cd085a243d74a54b9303f995b83b3b18e4b0db69ab7b51b73f52da`。
- vibecoding-bench 旧 tag：`f728876`。
- vibecoding-bench 旧 orchestrator image ID：`sha256:5af75f0f419ea74c1178dba27583de500ef5470b7afeb3fa3a1856ee1a7f68d0`。
- 部署前两个 HTTP 根路径均为 200，两个端口 established 连接数均为 0。
- cc2api 部署前 profile/range：`2.1.220` / `2.1.89-2.1.220`。
- cc2api 部署前 4 个账号 canonical env 均为 `2.1.220`。
- `allow_1m_models` 分布：`opus,claude-sonnet-5`，共 4 个账号。
- `allow_1m_models` 行级摘要：`aaa04f2950a190a7e8559dbdc251aa2d181a193f7f439bbca29e599b5a24df4d`。
- vibecoding-bench `.env` 部署前版本为 `2.1.197`，WebUI 保存覆盖值为 `2.1.257`。

## 备份

- 时间戳：`20260902T081201Z`。
- cc2api：`/root/claude-code-gateway/backups/deploy-20260902T081201Z/`。
- cc2api DB SHA256：`d151a499700fcfe7d76f4ed96cc6c76c45aa537df4253b1c0aa8a417127a9928`。
- vibecoding-bench：`/root/vibecoding-bench/.deploy-backups/20260902T081201Z-claude-code-2.1.257/`。
- vibecoding-bench DB SHA256：`70fc3ab6fcd02faebb2b4bd5bcd7717f9866ab6b6106c8bd4ba62918018b1026`。
- 两份 SQLite 备份的 `PRAGMA integrity_check` 均为 `ok`。

## cc2api 部署结果

- 目标镜像 `latest` 与 `sha-84b0016` 的 image ID/digest 完全一致。
- 新容器 image ID：`sha256:8e179390f7c7fafe8cc2be629016fe80ef09eba9db53ba51f69345a0d9c4dc97`。
- 根路径返回 200，数据库 `integrity_check=ok`。
- profile/range 已迁移为 `2.1.257` / `2.1.89-2.1.257`。
- 4 个账号 canonical env 已迁移为 `2.1.257`，build time 为 `2026-09-01T05:28:54Z`。
- system-role 列表新增 `claude-fable-5-1`，并保留自定义 `claude-sonnet-5`。
- bootstrap Fable 选项更新为 `claude-fable-5-1[1m]`。
- `allow_1m_models` 分布与行级摘要均与部署前一致。
- 最近日志脱敏计数：panic 0、migration failure 0、system-role local 400 为 0。

## vibecoding-bench 部署结果

- 等待线上真实 warmup run 自然结束后，最终门禁为：活动 run 0、worker/sidecar 容器 0、
  8080 established 连接 0。
- 生产值已更新为 `VIBEBENCH_TAG=e03b8e1`、`CLAUDE_CODE_VERSION=2.1.257`，候选
  Compose 通过 `docker compose config --quiet` 后才执行 recreate。
- orchestrator image ID 为
  `sha256:dc2d6ada11193d5ccfbae70021d864a5443801b45e83bbeda2d6622ea123e245`，
  与目标 digest 一致。
- orchestrator 运行环境引用 `e03b8e1` worker/sidecar，数据、WebUI、topics 和 Docker
  socket 挂载均保持原路径。
- 首页返回 200，SQLite `integrity_check=ok`，WebUI 保存的 `claude_code_version` 仍为
  `2.1.257`。
- 安全验证容器执行 `claude --version` 返回 `2.1.257 (Claude Code)`。
- warmup 调度已恢复：4 个账号启用，部署后最近一次检查距下一次到期约 45 分钟；活动
  run 和临时 worker/sidecar 容器均为 0。
- orchestrator 最近日志脱敏计数：traceback/panic 0、`No response from API` 0、
  error/exception 0。

## 集成观察

- cc2api 与 vibecoding-bench 根路径均返回 200，两个容器均运行目标 image ID。
- cc2api 最近一小时日志脱敏计数：panic 0、migration failure 0、版本拒绝 0、
  system-role 本地 400 为 0、signature-related 400 为 0、signature retry failure 0。
- 首字节超时和流式 idle timeout 均为 0；因此本次上线观察没有复现 Fable 5.1
  `No response from API`。代码日志契约已区分 `upstream_first_byte_timeout` 的
  `chunk_count=0` 与 `upstream_stream_idle_timeout` 的非零 chunk。
- 自然生产流量中已有 11 次 `claude-fable-5-1` 响应流完整结束，响应流读取失败为 0。
  本次没有伪造 `[1m]` beta，也没有修改账号 `allow_1m_models`。

## 回滚证据

- cc2api 旧 image ID 仍在本机：
  `sha256:87415cde63cd085a243d74a54b9303f995b83b3b18e4b0db69ab7b51b73f52da`。
- vibecoding-bench 的 `f728876` orchestrator、worker、sidecar 三个旧镜像均仍在本机；
  旧 orchestrator image ID 为
  `sha256:5af75f0f419ea74c1178dba27583de500ef5470b7afeb3fa3a1856ee1a7f68d0`。
- 两份数据库备份重新执行 `integrity_check` 均为 `ok`，SHA256 与部署前记录一致；
  vibecoding-bench 数据库备份权限已收紧为 `600`。
- vibecoding-bench 备份 Compose 与 `.env` 可解析出旧 tag `f728876` 和旧默认版本
  `2.1.197`。
- 旧 worker 镜像 `f728876` 实测内置 Claude Code `2.1.220`，与旧 cc2api profile
  上限一致。联合回滚时显式把 WebUI 版本覆盖固定为 `2.1.220`，避免恢复旧 DB 后残留
  的 `2.1.257` 覆盖值继续生效。

### 联合回滚操作单

仅故障时执行，整段按顺序运行，不删除 volume。必须先停止并准备好 2.1.220 的
vibecoding-bench，保持停止状态完成 cc2api 回滚，最后再启动 orchestrator；不得反向执行。

```bash
set -euo pipefail

wait_for_http() {
  local url=$1
  local code
  for _ in $(seq 1 60); do
    code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 "$url" || true)
    if [ "$code" = "200" ]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

rollback_ts=$(date -u +%Y%m%dT%H%M%SZ)
vb_root=/root/vibecoding-bench
vb_release_backup=$vb_root/.deploy-backups/20260902T081201Z-claude-code-2.1.257
vb_snapshot=$vb_root/.deploy-backups/pre-rollback-$rollback_ts
vb_db=$vb_root/data/db.sqlite

# 有活动 run 或临时容器时不进入回滚，避免留下跨版本运行状态。
test "$(sqlite3 $vb_db "SELECT COUNT(*) FROM runs WHERE status IN ('queued','running','stopping');")" = \
  "0"
test "$(docker ps --format '{{.Names}}' | awk '/bench-worker|bench-sidecar/ {count++} END {print count+0}')" = \
  "0"

# 停止 orchestrator，避免快照后仍有 API 或调度写入。
docker compose -f $vb_root/docker-compose.remote.yml --env-file $vb_root/.env \
  stop orchestrator
install -d -m 700 $vb_snapshot
sqlite3 $vb_db ".backup '$vb_snapshot/db.sqlite'"
install -m 600 $vb_root/.env $vb_snapshot/.env
install -m 600 $vb_root/docker-compose.remote.yml $vb_snapshot/docker-compose.remote.yml
install -m 600 $vb_root/webui/index.html $vb_snapshot/index.html
chmod 600 $vb_snapshot/db.sqlite
test "$(sqlite3 $vb_snapshot/db.sqlite 'PRAGMA integrity_check;')" = "ok"

# 恢复旧版本文件和 DB，并覆盖旧 DB 中残留的 2.1.257 页面配置。
test "$(sqlite3 $vb_release_backup/db.sqlite 'PRAGMA integrity_check;')" = "ok"
install -m 600 \
  $vb_release_backup/.env $vb_root/.env
install -m 644 \
  $vb_release_backup/docker-compose.remote.yml $vb_root/docker-compose.remote.yml
install -m 644 \
  $vb_release_backup/index.html $vb_root/webui/index.html
sqlite3 $vb_db ".restore '$vb_release_backup/db.sqlite'"
sqlite3 $vb_db \
  "INSERT INTO app_settings(key,value,updated_at) VALUES('claude_code_version','2.1.220',julianday('now')) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=julianday('now');"
test "$(sqlite3 $vb_db "SELECT value FROM app_settings WHERE key='claude_code_version';")" = \
  "2.1.220"

# 只验证旧配置和镜像，网关切换完成前不启动调度器。
docker compose -f $vb_root/docker-compose.remote.yml --env-file $vb_root/.env config --quiet
docker image inspect \
  ghcr.io/silentflower/vibebench-orchestrator:f728876 >/dev/null
docker run --rm --entrypoint claude \
  ghcr.io/silentflower/vibebench-worker:f728876 --version | grep -F "2.1.220"

# bench 已兼容旧网关后，再停止并回滚 cc2api。
cc_root=/root/claude-code-gateway
cc_db=/var/lib/docker/volumes/docker_claude-code-gateway-data/_data/claude-code-gateway.db
cc_release_backup=$cc_root/backups/deploy-20260902T081201Z/claude-code-gateway.db
cc_snapshot=$cc_root/backups/pre-rollback-$rollback_ts

test "$(ss -Htan state established '( sport = :5674 )' 2>/dev/null | wc -l)" = "0"
docker compose -f $cc_root/docker/docker-compose.yml --env-file $cc_root/.env \
  stop claude-code-gateway
install -d -m 700 $cc_snapshot
sqlite3 $cc_db ".backup '$cc_snapshot/claude-code-gateway.db'"
chmod 600 $cc_snapshot/claude-code-gateway.db
test "$(sqlite3 $cc_snapshot/claude-code-gateway.db 'PRAGMA integrity_check;')" = "ok"
test "$(sqlite3 $cc_release_backup 'PRAGMA integrity_check;')" = "ok"

sqlite3 $cc_db ".restore '$cc_release_backup'"
docker tag sha256:87415cde63cd085a243d74a54b9303f995b83b3b18e4b0db69ab7b51b73f52da \
  ghcr.io/silentflower/claude-code-gateway:latest
docker compose -f $cc_root/docker/docker-compose.yml --env-file $cc_root/.env \
  up -d --force-recreate --pull never claude-code-gateway
wait_for_http http://127.0.0.1:5674/
test "$(docker inspect -f '{{.Image}}' docker-claude-code-gateway-1)" = \
  "sha256:87415cde63cd085a243d74a54b9303f995b83b3b18e4b0db69ab7b51b73f52da"
test "$(sqlite3 $cc_db "SELECT value FROM settings WHERE key='claude_code_version_profile';")" = \
  "2.1.220"
test "$(sqlite3 $cc_db "SELECT value FROM settings WHERE key='allowed_claude_code_versions';")" = \
  "2.1.89-2.1.220"

# 网关验证通过后再启动旧 orchestrator，避免调度任务落在切换窗口。
docker compose -f $vb_root/docker-compose.remote.yml --env-file $vb_root/.env \
  up -d --force-recreate --pull never orchestrator
wait_for_http http://127.0.0.1:8080/
test "$(docker inspect -f '{{.Config.Image}}' vibebench-orchestrator)" = \
  "ghcr.io/silentflower/vibebench-orchestrator:f728876"
test "$(docker inspect -f '{{.Image}}' vibebench-orchestrator)" = \
  "sha256:5af75f0f419ea74c1178dba27583de500ef5470b7afeb3fa3a1856ee1a7f68d0"

echo "vibecoding-bench pre-rollback snapshot: $vb_snapshot"
echo "cc2api pre-rollback snapshot: $cc_snapshot"
```

如果联合回滚中途失败，先保持两个服务停止，使用上面输出的 `pre-rollback-*` 快照恢复
数据库和 vibecoding-bench 三个配置文件；cc2api 新镜像仍可通过 `sha-84b0016` 精确恢复，
vibecoding-bench 新镜像仍可通过 `e03b8e1` 精确恢复。

操作单已完成非破坏验证：Shell `bash -n` 通过；远程临时目录中的两套 SQLite
backup/restore、版本覆盖写入和 `integrity_check` 均通过；旧 Compose 可解析出三个
`f728876` 镜像，旧 worker 实测为 `2.1.220`。验证过程未停止或修改当前生产服务，
验证后两个根路径仍返回 200。

发布 Check-All 重检已确认：联合回滚顺序、2.1.220 版本协调、回滚前现场快照和恢复
路径均闭环，上一轮 `FBK-001`、`FBK-002` 已关闭。
