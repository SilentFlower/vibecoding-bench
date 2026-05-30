# 实施计划

## Implementation Checklist

- [x] 搜索所有思考预算、终态状态、timeout、OAuth credentials、401 标记的引用，确认没有漏点。
- [x] 增加配置常量：
  - `CLAUDE_CODE_EFFORT_LEVEL` 默认 `xhigh`
  - `TIMEOUT_WRAPUP_SEC` 默认约 600
  - 必要时增加 `OAUTH_CREDENTIAL_SYNC_INTERVAL_SEC`
- [x] 更新 `.env.example`、`docker-compose.yml`、`docker-compose.remote.yml`，把新配置传给 orchestrator/worker。
- [x] 修改 `orchestrator/main.py` 默认 Claude settings，使用配置值而不是硬编码 `max`。
- [x] 修改 `images/worker/entrypoint.sh` 的默认 settings，使用环境变量写入 `CLAUDE_CODE_EFFORT_LEVEL`。
- [x] 修改默认题目 prompt，加入自动运行约束和临近超时收尾倾向。
- [x] 在 worker 中实现 credentials 单向同步：
  - 从 `/mnt/profile/.credentials.json` 到 `$CLAUDE_DIR/.credentials.json`
  - JSON 校验
  - 原子替换
  - 后台循环和退出清理
- [x] 在 worker 等待循环中加入 401 检测、一次恢复提示、无法恢复时写明确状态。
- [x] 如采用 `auth_failed` 状态，更新 orchestrator 状态映射、批次统计和 WebUI pill/legend/action。
- [x] 更新 README 中 timeout / 思考预算 / OAuth 刷新竞态排查说明。
- [x] 运行验证命令并记录结果。

## Validation

- `python3 -m py_compile orchestrator/main.py`
- `bash -n images/worker/entrypoint.sh`
- 静态搜索确认无遗留硬编码：`rg "CLAUDE_CODE_EFFORT_LEVEL|auth_failed|timeout|401" ...`
- 若环境允许：`docker compose --profile build build orchestrator worker-image`
- 远程部署前检查 `.env.example` 与 remote compose 参数一致。

已执行：

- `python3 -m py_compile orchestrator/main.py` 通过。
- `bash -n images/worker/entrypoint.sh` 通过。
- `git diff --check` 通过。
- `rg "CLAUDE_CODE_EFFORT_LEVEL|auth_failed|timeout|401|OAUTH_401_PROFILE_WAIT_SEC" ...` 未发现阻断性遗漏。

## Review Gates

- 开始实现前：用户确认规划范围，尤其确认“不做启动前强制刷新 token”。
- 实现完成后：先本地静态验证，再考虑构建镜像和远程部署。

## Rollback Points

- 思考预算配置可通过 `.env` 改回 `max`。
- 临近超时收尾可通过 `TIMEOUT_WRAPUP_SEC=0` 关闭。
- 若运行中 credentials 同步异常，可回滚 worker 镜像；profile 原文件不会被 worker 回写覆盖。
