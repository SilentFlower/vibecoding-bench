# Release Operations

## Conclusion

Release operations exist. 本任务包含 cc2api 数据库自动迁移、cc2api 服务部署，以及 vibecoding-bench 编排服务部署，均已执行并完成验证。

## Evidence Checked

- cc2api 提交：`917a6e1 feat(account): 增加 Claude Fast Mode 透传控制`
- vibecoding-bench 业务提交：`e0b3a39 feat: 同步 cc2api Fast Mode 账号策略`
- vibecoding-bench 任务进度提交：`de461ca chore(task): update cc2api-claude-fast-mode-policy progress`
- cc2api 远程镜像版本：`917a6e153358a4bc65a842574df67770623c7acc`
- vibecoding-bench 远程镜像版本：`de461ca35fb196512335bebc38534ce13cd482f3`

## Drift Check

- 归档前任务目录缺少 `release.md`，本文件补齐实际发布记录。
- 代码、任务记录和远程部署版本一致，未发现待处理的发布漂移。

## SQL Changes

- 无需手工执行 SQL。
- cc2api 启动时自动为 SQLite/PostgreSQL 的 `accounts` 表增加 `allow_fast_mode INTEGER NOT NULL DEFAULT 0`。
- 默认值为 `0`，历史账号和新建账号默认禁止客户端启用 Claude Fast Mode。

## Configuration Changes

- cc2api 账号级配置新增 `allow_fast_mode`，默认关闭。
- vibecoding-bench 创建和同步 cc2api 账号时显式传递 `allow_fast_mode: false`，且同步既有账号时不覆盖服务端已有配置。
- 远程 vibecoding-bench 的 `VIBEBENCH_TAG` 已从 `d73237e` 更新为 `de461ca`，原 `.env` 已备份。

## External Systems

- GitHub Actions / GHCR：使用已推送提交构建和拉取镜像。
- cc2api 远程主机：拉取新镜像并强制重建服务。
- vibecoding-bench 远程主机：更新镜像标签并强制重建 orchestrator 服务。

## Data Operations

- 无手工数据修复或批处理。
- 迁移后远程账号分布为 `allow_fast_mode=0` 共 3 个账号。

## Post-release Validation

- cc2api 服务 HTTP 状态码为 `200`。
- cc2api 数据库字段为 `allow_fast_mode INTEGER NOT NULL DEFAULT 0`。
- cc2api 最近错误日志数量为 `0`。
- vibecoding-bench WebUI 在宿主机 `8080` 端口返回 `200`。
- orchestrator 容器代码包含 `"allow_fast_mode": False`。
- vibecoding-bench 活跃运行数为 `0`，cc2api API 连通状态为 `200`，账号数为 3，最近错误日志数量为 `0`。

## Rollback

- vibecoding-bench：将远程 `VIBEBENCH_TAG` 恢复为 `d73237e`，重新拉取镜像并强制重建 orchestrator；也可使用部署前备份的 `.env`。
- cc2api：切换到上一版本提交 `2e54c85` 对应的可用镜像并强制重建服务。
- 数据库新增字段可保留，旧版本不会读取该字段，无需破坏性回滚。
