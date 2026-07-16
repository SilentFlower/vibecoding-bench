# 上线操作

## 结论

存在上线操作。账号时区业务代码已经推送，但 DockerHub 镜像发布和远程实例升级尚未执行；任务归档不代表这些上线动作已经完成。

## 已核对证据

- `task.json`、`prd.md`、`design.md`、`implement.md`、`implement.jsonl`、`check.jsonl`
- 业务提交 `4b02980 feat(account): 支持账号时区选择`
- `.trellis/spec/vibecoding-bench/deploy/image-build-push.md`
- `.trellis/spec/vibecoding-bench/deploy/remote-deploy.md`

## 漂移检查

原任务缺少 `release.md`。`task.json.progress` 明确记录下一步为构建并推送 DockerHub 三镜像，并在远程暂停任务后重新部署，因此需要补充本操作单。

## SQL 变更

- 不需要人工执行 SQL。
- 新版 orchestrator 启动时由 `init_db()` 幂等补充 nullable 的 `accounts.timezone` 列；现有数据不需要回填，空值继续使用账号名派生时区。

## 配置变更

- 不新增或修改 `.env` 配置项。
- 账号时区保存在 SQLite 的账号记录中，不需要配置中心、密钥或权限调整。

## 批处理、部署脚本与数据修复

1. 由于 `orchestrator/main.py` 已修改，重新构建 orchestrator 镜像。
2. worker 和 sidecar 镜像内容未变化，但发布时仍需与 orchestrator 同时打 `latest` 和同一个 Git 短 SHA tag，保证三镜像版本集合完整。
3. 将三镜像的 `latest` 与短 SHA tag 推送到 DockerHub。
4. 远程仓库拉取最新代码；`webui/` 是 bind mount，前端更新依赖这次代码同步，不需要烤入镜像。
5. 拉取新镜像并使用 `--force-recreate orchestrator` 重建服务，不能只执行 `restart`。

## 外部系统与依赖平台

- DockerHub：需要具备 `huajiwuyan/vibebench-{orchestrator,worker,sidecar}` 的推送权限。
- 远程 vibecoding-bench 实例：升级前暂停或等待当前运行任务结束，避免重建 orchestrator 时中断任务。

## 上线顺序

1. 确认远程实例没有需要继续运行的任务，必要时先暂停任务。
2. 本地构建 orchestrator，并为三镜像生成一致的 `latest` 与短 SHA tag。
3. 推送三镜像到 DockerHub。
4. 远程执行 `git pull --rebase`，再拉取镜像。
5. 使用 `docker compose -f docker-compose.remote.yml --env-file .env up -d --force-recreate orchestrator` 完成升级。
6. 执行服务、账号时区和 worker 环境验证。

## 回滚说明

- 远程仓库回退到上一业务版本，并将 `VIBEBENCH_TAG` 指向上一组不可变短 SHA 镜像后重新创建 orchestrator。
- 数据库新增的 nullable `accounts.timezone` 列可以保留；旧代码不会依赖该字段，已有账号空值仍保持兼容。

## 上线后验证

- WebUI 账号表单展示自动模式和 10 个允许时区，不包含 `Asia/Shanghai`。
- 新建账号选择 `Europe/Berlin` 后，OAuth 登录容器与后续任务 worker 的 `TZ` 都为 `Europe/Berlin`。
- 自动模式和旧账号继续使用按账号名派生的时区。
- 非允许列表时区返回 400，且不启动登录容器、不写入数据库。
- `docker compose` 显示 orchestrator 正常运行，WebUI 登录和 `/api/topics` 鉴权行为正常。
