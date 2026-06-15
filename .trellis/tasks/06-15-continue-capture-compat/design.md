# design.md

## Technical Design

### 判定边界

continue 是否继承完整抓包，应以原 run 的持久化字段为准：

- 优先使用 `run["capture_summary_path"]` 是否存在且非空判断原 run 是否为 capture run。
- `run["flows_dir"]` 是 continue sidecar 的目标挂载目录来源。
- 如果 `capture_summary_path` 存在但 `flows_dir` 缺失，应回退到现有 run 详情页的查找逻辑，按 `FLOWS_DIR` 下的 `<rid>/stats.jsonl` 匹配目录；如果仍找不到，则不启用完整抓包并返回明确错误或保持现有启动失败语义。

### 容器启动变更

`Runner.start_continue()` 当前只挂载 `/ca` 到 sidecar。需要在原 run 是 capture run 时增加：

- `run.flows_dir -> /flows`
- `SAVE_FULL_FLOWS=1`
- `CAPTURE_FULL_HTTP=1`
- `CAPTURE_MODE=continue_full_http`
- `CAPTURE_SCOPE=all`
- `CAPTURE_TARGETS=anthropic.com,claude.com`
- `CAPTURE_MAX_BODY_BYTES=0`

非 capture run 保持当前行为：不挂载 `/flows`，不设置 `CAPTURE_FULL_HTTP`。

### 数据流

capture continue 的 HTTP 流量路径为：

1. 浏览器 WebSocket 连接 continue API。
2. orchestrator 启动 continue sidecar 和 worker。
3. worker 通过 `network_mode=container:<sidecar>` 走 sidecar MITM。
4. sidecar recorder 将完整 HTTP 记录追加到 `/flows/http_capture.jsonl`。
5. recorder 更新 `/flows/capture_index.json`。
6. run 详情页沿用原 `flows_dir` 和 `capture_summary_path` 读取追加后的索引。

### 兼容性

- 已存在的 capture run 可直接受益，只要数据库中保留 `flows_dir` 和 `capture_summary_path`。
- 非 capture run 不新增正文落盘，避免改变默认隐私和磁盘行为。
- sidecar recorder 的现有追加写入语义可以复用，不需要迁移已有 capture 文件。

### 风险与约束

- continue 追加到原 capture 文件会让同一个 run 的 capture timeline 包含初始 run 和手动继续两段流量，这是本任务的目标行为。
- `capture_index.json` 由 recorder 读写整个 JSON 文件，继续多次操作时要确认不会覆盖旧 entries。
- 完整抓包包含高敏正文，任务验证时不能输出 Authorization、Cookie、完整 prompt、完整 request body 或 tool schema。

## Rollout / Rollback

- Rollout：先本地实现并用一个测试 capture run 验证行数和索引追加，再部署远程镜像。
- Rollback：恢复 `Runner.start_continue()` 的 sidecar volumes/env 变更即可，已追加的本地 capture 文件无需迁移。
