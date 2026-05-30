# 实施计划

## Implementation Checklist

- [x] 补充研究记录 `research/1179c962831a-api-stall.md`，固化远程 run 证据。
- [x] 在 `images/worker/entrypoint.sh` 增加 API error / 无进展检测函数。
- [x] 增加恢复计数、TUI 中断注入函数和默认中文恢复提示。
- [x] 把等待循环接入 API 卡死 watchdog，确保 401/auth_failed 路径优先级不变。
- [x] 改造临近超时 wrap-up：busy 时先中断再注入，非 busy 时保留普通注入。
- [x] 在 `.bench-status.json` 中写入 API 卡死恢复次数和最终可见错误。
- [x] 在 `orchestrator/main.py` 增加配置读取并传给 worker。
- [x] 更新 `.env.example`、`docker-compose.yml`、`docker-compose.remote.yml`。
- [x] 更新 `implement.jsonl` / `check.jsonl`，保留相关代码、spec、研究上下文。
- [x] 如改动 worker 完成判定契约，更新 `.trellis/spec/deploy/image-build-push.md`。

## Validation

- `bash -n images/worker/entrypoint.sh`
- `python3 -m py_compile orchestrator/main.py`
- `git diff --check`
- 用本地临时 JSONL 样例验证：
  - API error 后无进展超过窗口 -> 触发恢复。
  - API error 后出现 assistant/tool_use 进展 -> 不触发恢复。
  - 401/OAuth 文本 -> 仍走 auth_failed 检测，不走 API 卡死恢复。
- 静态搜索确认配置传递完整：
  - `rg "CLAUDE_API_STALL|BUSY_INTERRUPT|bench-status" images/worker/entrypoint.sh orchestrator/main.py docker-compose*.yml .env.example`

## Review Gates

- 实现前：确认任务状态为 `in_progress`，并按 Trellis Phase 2 路由进入实现。
- 实现后：先跑本地静态验证，再决定是否构建镜像和远程部署。

## Rollback Points

- 运行时关闭：`CLAUDE_API_STALL_WATCHDOG_SEC=0`。
- 行为降级：`CLAUDE_API_STALL_MAX_RECOVERIES=0`。
- 镜像回滚：远程改回上一版 `VIBEBENCH_TAG` 并 force recreate。
