# Claude Code API 卡死 watchdog 与自动续跑

## Goal

提升批量 run 在 Claude Code API 连接异常后的自动恢复能力。当前已确认 `1179c962831a` 不是认证失败或模型能力不足，而是 Claude Code 在 `/v1/messages` 请求出现 `ECONNRESET` 后长时间卡在 TUI busy 状态；人工追加一句“为什么卡住了”后，同一 session 立刻继续并产出文件。本任务要把这种“人工踢一下可恢复”的场景自动化，减少纯等到 `timeout` 的失败。

## Background / Known Context

- 远程 run `1179c962831a`：任务 `间隔重复闪卡`，账号 `auto-2`，`timeout_sec=2000`，实际运行约 `2037s`，最终 `status=timeout`、`exit_code=124`。
- 该 run 的 Claude JSONL 多次记录 `system api_error`，错误为 `Unable to connect to API (ECONNRESET)`，`maxRetries=10`，且每隔约 5 分钟出现一次。
- 同一期间 `/api/event_logging/v2/batch` 仍返回 HTTP 200，说明 sidecar/网络不是完全断开。
- worker 已经注入临近超时收尾提示，但 Claude TUI 当时仍处于 busy 状态，提示只排队在输入框，没有进入模型回合。
- 用户后续在同一 session 手动发 `？为啥卡主了哇` 后，Claude 立即继续实现并写出 `index.html`、`styles.css`，验证了“中断/追加继续提示”可恢复。
- 现有 worker 已实现：最终 assistant JSONL 判定、临近超时收尾提示、OAuth 401 检测与一次恢复、`.bench-status.json` 状态提示。
- 当前实现约束：worker 不能因为没看到最终 assistant 文本而反复追加 prompt；本任务只允许对明确 API 卡死形态做有限恢复，不能变成无限催促。

## Requirements

- worker 必须能识别 Claude Code API 卡死形态：
  - 从 Claude session JSONL 中读取 `system` / `api_error` 事件。
  - 至少识别 `ECONNRESET`、`Connection error`、`Unable to connect to API` 这类明确连接错误。
  - 判断条件必须结合“无有效进展”窗口，不能只要出现一次 API error 就打断。
- “有效进展”至少应包含：
  - 最新 conversation 消息变化。
  - 最新 assistant/tool_use/tool_result 事件变化。
  - workspace 内用户产物文件有新增或修改。
  - Claude 已经给出最终 assistant 文本则不再恢复。
- worker 必须支持有限自动恢复：
  - 当 API 卡死超过可配置窗口后，向 Claude TUI 发送一次中断信号，让当前 busy 请求退出。
  - 等 TUI 回到可输入状态后，注入继续提示，要求从当前状态继续、优先最小可运行版本、不要重新调研。
  - 每个 run 默认最多恢复 1 次，可通过环境变量调整，但必须有上限。
- 临近超时收尾必须复用恢复能力：
  - 如果 wrap-up 时 TUI 正忙且普通注入只会排队，应先尝试中断 busy 状态，再注入收尾提示。
  - 如果已经用完恢复次数，仍按现有 timeout 逻辑处理，但错误信息应更明确。
- 状态与错误信息必须可见：
  - 若最终仍超时，run `error` 或 `.bench-status.json` 应能说明曾检测到 Claude API 卡死和自动恢复次数。
  - 不新增复杂 DB schema；优先复用现有 `runs.error` 和 `.bench-status.json`。
- 配置必须可通过 compose / `.env` 覆盖：
  - API 卡死 watchdog 开关。
  - 无进展窗口秒数，默认 `400` 秒。
  - 最大自动恢复次数。
  - 恢复提示文本或默认中文提示。
- 不能污染被测任务 prompt：
  - 不在原始 `TASK_PROMPT` 中追加 bench sentinel。
  - 恢复提示只能作为运行时 TUI 注入，不改变任务创建时 prompt。
- 不能把 OAuth/401、配额、普通工具调用失败误判成 API 卡死：
  - 401 仍走现有 `auth_failed` 路径。
  - 普通 smoke test 失败、Edit 字符串找不到、用户代码报错不应触发 API 卡死恢复，除非同时满足 API error + 无进展窗口。

## Acceptance Criteria

- [ ] worker 能从 Claude JSONL 检测 `ECONNRESET` / `Unable to connect to API` 等 API 连接错误。
- [ ] worker 只有在 API error 后持续无有效进展超过配置窗口时才触发自动恢复。
- [ ] 自动恢复会先中断当前 busy TUI，再注入一次中文继续提示；同一 run 默认最多触发 1 次。
- [ ] 临近超时收尾在 TUI busy 时能使用同一中断注入路径，避免提示只排队在输入框。
- [ ] `.env.example`、`docker-compose.yml`、`docker-compose.remote.yml` 暴露相关配置，并有安全默认值。
- [ ] orchestrator 能传递新配置给 worker，并在 worker 写出 `.bench-status.json` 时把可见错误写入 `runs.error`。
- [ ] 不改变任务创建时 `prompt` 字段，不向题目 prompt 注入 bench sentinel。
- [ ] `bash -n images/worker/entrypoint.sh` 和 `python3 -m py_compile orchestrator/main.py` 通过。
- [ ] 用本地 JSONL 样例覆盖：API error 后无进展触发、API error 后有 assistant 进展不触发、401 不走 API 卡死恢复。

## Definition of Done

- 代码改动符合现有 worker shell 脚本和单文件 orchestrator 风格。
- 所有新增用户可见文案、注释、文档使用中文。
- 恢复次数有硬上限，不会无限打断 Claude。
- 错误信息不泄漏 access token、refresh token、账号密码或完整敏感 prompt。
- 更新部署契约，让远程发版知道 worker/orchestrator 镜像需要重建与重推。

## Out of Scope

- 不重跑已经失败的历史 run。
- 不实现完整“自动重启 Claude Code / 新 session 接续”产品。
- 不新增 DB 表或 migration。
- 不改账号 OAuth 登录与 refresh 机制。
- 不把所有长时间无输出都判成卡死；本任务只覆盖有明确 API 连接错误证据的卡死。

## Research References

- `research/1179c962831a-api-stall.md`
