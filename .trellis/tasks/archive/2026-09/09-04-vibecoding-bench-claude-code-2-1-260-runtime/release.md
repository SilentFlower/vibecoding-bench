# Release Operations

## Conclusion

Release operations exist.

## Evidence Checked

- `task.json`、`prd.md`、`design.md`、`implement.md`
- `implement.jsonl`、`check.jsonl`、`research.md`
- 业务提交 `e6f1f0b` 与任务记录提交 `b856d41`
- `orchestrator/main.py`、两份 Compose、worker 镜像入口和部署规范

## Drift Check

Missing release.md. 本文件根据已推送实现和任务验收要求补齐上线动作。

## SQL Changes

- `[vibecoding-bench-claude-code-2-1-260-runtime]` `runs` 新增 nullable `claude_code_version TEXT`。
- 不需要手工执行 DDL；新 orchestrator 启动时由 `init_db()` 通过 `_ensure_column` 幂等补列。
- 部署前必须使用 SQLite `.backup` 备份生产数据库；部署后执行 `PRAGMA integrity_check` 并确认新列存在。

## Configuration Changes

- `[vibecoding-bench-claude-code-2-1-260-runtime]` `CLAUDE_CODE_VERSION` 默认值升级为 `2.1.260`。
- WebUI `app_settings.claude_code_version` 优先于 `.env`。部署前记录旧覆盖值，部署后把页面覆盖和 `.env` 兜底都确认到 `2.1.260`。
- worker 启动会安装精确 CLI 版本；安装失败必须显式失败，不能静默回退。

## Batch / Deployment Scripts / Data Repair

- 确认 orchestrator、worker、sidecar 三个镜像已经发布同一个 commit SHA tag，并且 `latest` 指向该批次。
- 记录生产当前容器、镜像 ID、Compose 配置和运行时设置；确认没有活跃 run、continue、login 或残留 worker/sidecar。
- 在生产主机执行镜像 pull，并使用 `docker compose up -d --force-recreate orchestrator` 重建服务；不能使用只保留旧镜像的 `restart`。
- 不需要批量回填历史 run。历史 `claude_code_version IS NULL` 的记录只在首次继续前按当前有效版本补写一次。

## External Systems / Dependent Platforms

- GitHub Actions / GHCR：三个 bench 镜像必须完成同 SHA 发布。
- 生产 Docker 主机：负责数据库备份、镜像切换、容器重建和健康检查。
- 本任务不修改 cc2api；2.1.260 协议画像与允许范围由后续 cc2api 任务承接。

## Release Order

1. 确认远端 `main` 提交和三镜像同 SHA tag/`latest` 发布成功。
2. 确认生产没有活跃会话，记录旧镜像、`.env` 和 WebUI 版本覆盖值。
3. 使用 SQLite `.backup` 创建数据库快照并完成完整性检查。
4. pull 新镜像，固定 `CLAUDE_CODE_VERSION=2.1.260`，force recreate orchestrator。
5. 验证 orchestrator 健康、数据库补列和运行时版本设置。
6. 创建新普通 run 与抓包 run，并验证抓包 run 关闭后继续仍使用原 `2.1.260` 快照。

## Rollback Notes

- 保留部署前数据库快照、旧镜像 ID/tag、旧 `.env` 和 WebUI 覆盖值。
- 回滚时恢复旧镜像与兼容的 `CLAUDE_CODE_VERSION`，再 force recreate orchestrator。
- 新增 nullable 列可以保留，旧代码会忽略；只有数据库完整性或数据异常时才使用部署前快照恢复。
- 不删除 bench `data/`、账号 profile、workspace 或 Docker volume。

## Post-release Verification

- orchestrator 容器健康，HTTP/API 可访问，最近日志无启动或迁移错误。
- `runs` 表包含 `claude_code_version`，数据库 `PRAGMA integrity_check` 返回 `ok`。
- 设置接口显示环境兜底值和当前有效值均为 `2.1.260`。
- 新普通、批量、养号和抓包 run 保存非空版本快照；实际 worker `claude --version` 为 `2.1.260`。
- 以 `2.1.260` 创建抓包 run 后修改全局设置并关闭 worker，继续该 run 仍启动 `2.1.260`；之后新建 run 使用新的全局版本。
