# 技术设计

## 边界与数据流

### 思考预算配置

配置源为 compose 环境变量 `CLAUDE_CODE_EFFORT_LEVEL`。orchestrator 读取后写入账号 profile 的 `settings.json`，worker 也从同名环境变量生成运行时默认 settings。这样本地、远程、临时 profile 修复路径使用同一个配置值。

允许值建议为 `low|medium|high|xhigh|max`，其中 `xhigh` 为默认值。`max` 保留给手动覆盖，但不再作为批量默认。

### Prompt 约束

`build_topic_prompt()` 是默认题目 prompt 的单一来源，单任务和批次都复用它。应在该函数中追加自动运行约束，避免在 `create_task` / `create_task_batch` 两处重复拼接。

用户自定义 `prompt_override` 当前会完全覆盖默认 prompt。为了不改变用户语义，本任务不强行改写 override，但可以考虑在设计里保留后续“系统尾注”能力；本次 MVP 先覆盖默认题目 prompt。

### 临近超时自动收尾

worker 已经拥有 deadline 循环和 tmux session。新增配置：

- `TIMEOUT_WRAPUP_SEC`：距离 deadline 多少秒注入收尾提示，默认建议 600。
- `TIMEOUT_WRAPUP_PROMPT`：可覆盖的中文收尾提示。

在等待循环中，当 `deadline - now <= TIMEOUT_WRAPUP_SEC` 且尚未注入时，用 bracketed paste 向 tmux 发送收尾提示并回车。注入后继续使用现有 `classify_claude_completion` 判断最终结果。

### 运行中 credentials 同步

worker 当前挂载 `/mnt/profile` 为 rw。新增一个后台同步循环：

1. 定期读取 `/mnt/profile/.credentials.json` 的 mtime / size / hash。
2. 与 `$HOME/.claude/.credentials.json` 比较。
3. 若 profile 文件更新且 JSON 可解析，则复制到临时文件，再 `mv` 原子替换本地 credentials。
4. 只从 profile 同步到 run home，不从 run home 回写 credentials。

这样后台刷新器更新 profile 后，正在运行的 worker 能在短时间内拿到新 token；不会引入启动前强刷。

### 401 检测与恢复

短期 MVP 优先在 worker 侧通过 Claude session JSONL / transcript 检测认证错误文本，因为 worker 已经能访问 TUI 和 JSONL，且不需要 orchestrator 订阅 sidecar stats。

检测策略：

- 在等待循环中增加 `detect_claude_auth_error()`。
- 若检测到 `API Error: 401`、`Invalid authentication credentials`、`OAuth token has expired`、`Please run /login` 等标记：
  - 先主动执行一次 credentials 同步。
  - 若未尝试过恢复，则注入一次“凭据已刷新，请重试刚才失败的请求并继续收尾”的提示。
  - 记录 `/tmp/claude-auth-recovered-once`，避免无限重试。
  - 若恢复后仍检测到认证错误，则写 `/tmp/claude-fatal-error` 并退出失败。

如果 orchestrator 侧后续要更精细，可基于 `stats.jsonl` 的 401 响应补充状态，但本次先不增加跨容器监听线程，避免复杂度膨胀。

### 状态与前端

如果 worker 对无法恢复的 401 退出 1，orchestrator 当前会标 `failed`。为了让 UI 区分认证失败，有两个可选方案：

- MVP：worker 在 transcript 和退出前状态文件写明确 OAuth 401 错误，orchestrator 捕捉不到细分状态，但详情可见。
- 完整：worker 写 `/workspace/.bench-status.json`，orchestrator wait 后读取其中 `status=auth_failed` 并写入 runs.status。

推荐完整方案，影响范围可控。若引入 `auth_failed`，需要同步：

- `_TERMINAL_RUN_STATUSES`
- batch done 统计
- batch item 终态统计
- WebUI pill class / legend / continue 按钮终态判断

## 兼容性

- 现有 DB 无需新增列；可复用 `runs.status` 和 `runs.error`。
- 新增环境变量都有默认值，旧 `.env` 不设置也能运行。
- worker 挂载 `/mnt/profile` 已存在，credentials 同步不需要改 Docker volume 形态。

## 风险与缓解

- 风险：注入收尾提示打断正在执行的工具调用。
  - 缓解：只在临近 deadline 且最多一次注入；提示要求收尾而不是取消。
- 风险：credentials 同步时复制到半写文件。
  - 缓解：profile 端已有原子替换；worker 端复制前 JSON parse 验证，复制后本地也原子替换。
- 风险：401 文本检测误判。
  - 缓解：仅匹配明确认证错误标记；恢复只尝试一次，避免循环。
- 风险：新增 `auth_failed` 后前端漏改。
  - 缓解：实施时搜索所有 `success|failed|timeout|stopped` 和 `_TERMINAL_RUN_STATUSES` 引用。

## Rollout / Rollback

上线时先用新 tag 部署远程，`.env` 默认 `CLAUDE_CODE_EFFORT_LEVEL=xhigh`。如果发现异常，可把 env 改回 `max` 或关闭超时收尾窗口；若 `auth_failed` 状态导致 UI 问题，可回滚镜像 tag，DB 中字符串状态不会破坏旧代码读取。
