# 2.1.257 联合回滚操作与恢复边界

## 当前状态

本文件是故障时的操作边界记录，不是已执行脚本。当前 2.1.260 保持运行；用户停止测试后未执行回滚。
已验证的材料及完整性结果见 [部署证据](deploy-evidence.md)。
2026-09-05 用户确认本次不做完整回滚演练，取消原 CHK-001 收尾阻塞；以下内容保留给未来故障处置参考，不是本次待执行清单。

## 已知恢复目标

- 旧 cc2api image ID：`sha256:06701eb10f03bd665527f059b25085dfc0640c1467794ac5c51db9027a17b96d`。
- cc2api 旧 DB 目录：`/root/claude-code-gateway/backups/deploy-20260904T230043Z-claude-code-2.1.260`。
- 旧 DB profile/range：`2.1.257 / 2.1.89-2.1.257`。
- bench 当前状态备份目录：`/root/vibecoding-bench/.deploy-backups/20260904T230043Z-cc2api-claude-code-2.1.260`。
- 上述 bench 备份属于 `abc2c98 / 2.1.260`，只用于恢复本次操作前现场。2.1.257 的旧 bench 三镜像及匹配配置必须另行定位，不能假设该目录就是旧版本备份。
- 若恢复本次 2.1.260 发布产物，cc2api 使用精确 tag `sha-7aecda3`，其 digest 见部署证据；bench 使用操作前核验并保留的 `abc2c98` 镜像、配置和 DB。

## 执行顺序

1. 故障处置获得明确回滚授权后，先核对旧镜像、完整配置和数据库文件名、hash、目录权限。任一缺失时停止。不得依赖漂移的 `latest`。
2. 定位旧 bench 三镜像及匹配 Compose、WebUI、环境文件，实际读取旧 worker 的 CLI 版本。将 `rollback_cli_version` 选为旧网关允许范围内的已验证版本，目标为 `2.1.257`。
3. 确认 bench 无活跃 run、continue、登录流程或残留 worker/sidecar；保持现场 run 数据，不为演练强行终止。
4. 停止 orchestrator，创建新的操作前数据库 API 快照和配置快照。快照目录 `700`、DB 文件 `600`，完整性必须为 `ok`。
5. 恢复已核验的旧 bench 镜像配置和必要数据库快照，将 `.env` 与 `app_settings.claude_code_version` 固定为同一 `rollback_cli_version`。数据库恢复前明确历史记录回退的影响，避免误覆盖发布后新增数据。
6. 解析旧 Compose，验证三镜像和旧 worker CLI，保持 orchestrator 停止。只读检查 `runs.claude_code_version`；已有 2.1.260 run 不改写，延后 continue 或恢复兼容网关后再继续。
7. 等待 cc2api 低连接窗口，停止网关；创建当前网关 DB 和配置的操作前快照并检查完整性，然后才恢复已核验的旧 DB、配置和精确镜像。
8. recreate 网关，核验 HTTP、image ID、DB integrity、profile、allowed range 与账号身份。旧网关必须包含 `rollback_cli_version`，失败时不得启动 orchestrator。
9. 最后恢复并验证旧 orchestrator；新 worker 使用已固定的兼容 CLI，原 run 的版本快照仍保持原值。

数据库快照使用 SQLite `.backup/.restore` API。路径须先在目标主机确认，在线数据库不得直接复制。
Compose 的相对路径按原项目目录解析；把文件放入备份目录后直接 `config` 可能寻找错误的 `../.env`，应还原目录结构或显式使用经核验的项目目录。
不得删除 volume、bench `data/`、profile 或 workspace。

## 中途失败恢复

- 保持 orchestrator 停止，先修复或恢复网关到操作前 2.1.260 镜像、DB、配置并确认 HTTP 和版本范围，再恢复 bench 操作前快照。
- 恢复的是本次回滚开始前新建的快照，不是盲目恢复发布前旧 DB；这样才能保留发布后形成的配置和记录。
- 每次 `.restore` 前保留目标现状并校验源备份完整性。任一步前提不满足时停止，保留快照和现场。

## 本次未执行项目

- 精确旧 bench 三镜像、旧 Compose 和 WebUI 文件清单及 worker CLI 验证。
- 本版本完整可执行操作单的 `bash -n`、适用的 shellcheck 和先后顺序断言。
- 两份生产备份临时副本中的 `.backup/.restore`、`integrity_check` 和 CLI 页面覆盖写入演练。
- 用户已取消以上项目作为本次升级的演练要求，不再安排补测或阻塞归档；未执行事实保留，将来实际故障回滚前仍须核验相应前提。
