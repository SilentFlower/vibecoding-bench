# 技术设计

## 边界与数据流

本任务只修改 task worker 运行期控制逻辑，并少量修改 orchestrator / compose 配置，把新环境变量传入 worker。核心数据源是 worker 本地可读的 Claude session JSONL、workspace 文件 mtime、TUI transcript 和已有 `.bench-status.json`。

### API 卡死检测

新增 worker 函数 `detect_claude_api_stall()`，输入为：

- Claude session JSONL 目录：`$CLAUDE_DIR/projects/-workspace`
- workspace 路径：`/workspace`
- 最近一次恢复时间或 run 启动时间
- 无进展窗口秒数

检测分两步：

1. 扫描最近 session JSONL，找 `type=system`、`subtype=api_error`、`error.formatted` 或 `error.connection.code` 中包含明确连接错误标记：
   - `ECONNRESET`
   - `Connection error`
   - `Unable to connect to API`
   - `FailedToOpenSocket`
2. 计算最近有效进展时间：
   - 最新 assistant/user conversation 消息时间。
   - 最新非 api_error 的 tool_use/tool_result 或 assistant 文本事件时间。
   - `/workspace` 下排除 `.claude-home`、`.claude`、`.bench-transcript.log` 的文件 mtime。

只有满足“最近 API error 存在、API error 之后无有效进展、无进展时长超过阈值、当前没有最终 assistant 完成”时才返回需要恢复。

### 自动恢复策略

新增可配置项：

- `CLAUDE_API_STALL_WATCHDOG_SEC`：无进展超过多少秒后触发，默认 `400`；`0` 关闭。
- `CLAUDE_API_STALL_MAX_RECOVERIES`：每个 run 最多自动恢复次数，默认 `1`。
- `CLAUDE_API_STALL_RECOVERY_PROMPT`：恢复提示，默认中文。
- `CLAUDE_BUSY_INTERRUPT_GRACE_SEC`：发送中断后等待 TUI 回到可输入状态的秒数，默认 `8`。

新增函数 `interrupt_and_inject_tmux_prompt(kind, text)`：

1. `tmux send-keys C-c` 中断当前 busy 请求。
2. 等待短窗口，期间持续 `capture_transcript_snapshot`。
3. 使用现有 bracketed paste 注入恢复提示并回车。
4. 记录 `/tmp/claude-api-stall-recoveries` 计数与时间。

恢复提示不要求 Claude 解释卡死原因，只要求：

- 从当前文件状态继续。
- 不重新做环境调研。
- 优先补齐最小可运行版本。
- 时间不足时输出最终总结。

### 临近超时收尾抢占

现有 `inject_tmux_prompt wrapup` 在 TUI busy 时会排队，无法进入模型回合。改为：

- 如果 transcript 显示 busy 状态，且恢复次数未超上限，则用 `interrupt_and_inject_tmux_prompt wrapup "$TIMEOUT_WRAPUP_PROMPT"`。
- 如果无法判断 busy 或已无恢复次数，保留现有普通注入。

busy 判断不需要复杂 UI 解析，优先使用保守信号：

- transcript 包含 `Beboppin'`、`Herding`、`Frosting` 等 Claude Code spinner 文本。
- 或最近 JSONL 最新有效消息是 `user tool_result` / `assistant tool_use`，之后长期只有 api_error / event_logging。

### 状态输出

worker 在触发恢复时写 `/workspace/.bench-status.json`，例如：

```json
{
  "status": "running",
  "error": "检测到 Claude API 连接卡死，已自动中断并继续 1 次",
  "api_stall_recoveries": 1
}
```

最终仍 timeout 时更新为：

```json
{
  "status": "timeout",
  "error": "Claude API 连接卡死后仍未在超时前完成，已自动恢复 1 次"
}
```

orchestrator 当前只把 `auth_failed` hint 细分为状态，但会读取 `error` 并写入 `runs.error`。本任务不新增 `api_stalled` 终态，避免扩大前端状态改动。

如果恢复后最终成功或被用户主动停止，orchestrator 不应把中途的恢复提示写入 `runs.error`；只有非成功、非停止终态才保留该错误说明。

### 配置传递

orchestrator 新增环境读取常量，并在 `Runner.start_run()` 的 worker environment 中传入：

- `CLAUDE_API_STALL_WATCHDOG_SEC`
- `CLAUDE_API_STALL_MAX_RECOVERIES`
- `CLAUDE_BUSY_INTERRUPT_GRACE_SEC`
- `CLAUDE_API_STALL_RECOVERY_PROMPT`

compose 和 `.env.example` 暴露默认值。`CLAUDE_API_STALL_RECOVERY_PROMPT` 留空时使用 worker 内置中文提示，远程需要微调文案时可在 `.env` 覆盖。

## 兼容性

- 默认开启一次恢复，但只在明确 API error + 无进展窗口后触发，对正常 run 不影响。
- `CLAUDE_API_STALL_WATCHDOG_SEC=0` 可关闭新逻辑。
- 不新增 DB schema；旧前端照常展示 `timeout`，但详情中能看到更明确的 `error`。
- 只改 task 模式，不影响 login 模式。

## 风险与缓解

- 风险：误中断正在正常长思考的请求。
  - 缓解：必须同时满足明确 API error 和无有效进展窗口；普通长思考没有 api_error 不触发。
- 风险：中断后丢失正在生成的回答。
  - 缓解：恢复次数默认 1，且窗口默认 400 秒；比等到硬 timeout 更可接受。
- 风险：wrap-up 中断过早导致未完成工具调用。
  - 缓解：只在临近 deadline，目标是最大化最终总结产出。
- 风险：`.bench-status.json` 的 `status=running` 干扰 orchestrator。
  - 缓解：orchestrator 只基于 worker exit_code 决定终态，非 `auth_failed` status_hint 不改变 status。

## Rollout / Rollback

上线需要重建并推送 orchestrator 与 worker 镜像。若远程发现误打断，可在 `.env` 设置 `CLAUDE_API_STALL_WATCHDOG_SEC=0` 并 recreate orchestrator，后续 worker 即关闭 watchdog。若需要彻底回滚，使用上一版三镜像 tag。
