# brainstorm: runs running 详情与 token 统计修复

## Goal

让 `runs` 详情弹窗在 run 仍处于 `running` 时能持续展示当前对话现场，并修复或明确解释“输入 token / 输出 token / 请求数”为空的问题。用户打开运行中的详情页时，不应只能看到打开瞬间的静态快照；运行过程中的 transcript、统计值、退出码、状态和错误信息应随后台产物更新而刷新。

## Background / Known Context

- 用户反馈：`runs` 里还在 `running` 的详情页面也希望显示当前对话的实际情况。
- 用户反馈：详情里的“输入 token”“输出 token”“请求数”当前仍为空，怀疑是 BUG。
- 代码现状：`webui/app.js` 的 `openRunDetail(rid)` 只在打开弹窗时一次性请求 `/api/runs/{rid}`、`/api/runs/{rid}/files`、`/api/runs/{rid}/stats` 和 `/api/runs/{rid}/transcript`。
- 代码现状：`/api/runs-stream` 只实时推 runs 列表，不推详情弹窗内的 transcript / files / stats。
- 代码现状：`/api/runs/{rid}/stats` 会扫描 `data/flows/<account>/<task>/<run>/stats.jsonl`，聚合返回 `tokens_in`、`tokens_out`、`requests`、`errors`；没有匹配文件时返回 0。
- 代码现状：`images/sidecar/recorder.py` 已在请求阶段写 `phase=request` 记录，用于即使响应解析失败也能统计请求数；响应阶段从 JSON 或 SSE 里提取 `usage.input_tokens` / `usage.output_tokens`。
- 代码现状：worker 在任务结束或失败收口时才执行 `tmux capture-pane ... > /workspace/.bench-transcript.log`；因此运行中 transcript 可能尚无文件或不是最新，除非补运行中快照能力。
- 代码现状：项目是原生 FastAPI + SQLite + 静态 HTML/JS/CSS，无构建系统、无前端框架、无自动化测试。
- 相关文件：`orchestrator/main.py`、`webui/app.js`、`webui/style.css`、`images/worker/entrypoint.sh`、`images/sidecar/recorder.py`。

## Assumptions (temporary)

- “当前的对话的实际情况”优先理解为：运行中的 Claude TUI transcript 文本能够在详情页持续更新，而不是只展示最终完成后的 transcript。
- token 统计“空”是 BUG 或体验 BUG：详情页不应因为 stats 尚未写入、API 失败或字段缺失而显示难以理解的空白；未采集到数据时显示 `等待采集`。
- MVP 优先复用现有详情弹窗，不新建独立详情页，不引入前端框架或构建工具。
- 运行中详情可以使用轻量轮询拉取详情数据；runs 列表继续使用现有 SSE。

## Open Questions

- 暂无阻塞问题。

## Requirements

- 详情弹窗打开 running run 时，应自动刷新 run 状态、退出码、错误信息、统计数据和 transcript。
- MVP 范围锁定为只读实时展示：用户可以观察 running run 的当前对话现场，但不能在详情弹窗里向当前 run 输入内容或介入对话。
- 当 run 从 `running` 进入终态（`success` / `failed` / `timeout` / `stopped`）后，详情弹窗应停止自动刷新并保留最终数据。
- 用户关闭详情弹窗、切换页面或打开另一个 run 详情时，必须释放该详情刷新资源，避免重复请求或泄漏定时器。
- 详情弹窗中的 token / 请求统计必须有明确显示：
  - API 正常返回数值时显示数值，包括 0。
  - stats 文件尚未产生或未捕获到 usage 时显示 `等待采集`，不显示空白，也不直接显示 0。
  - stats API 失败时显示错误兜底，不静默变成空字段。
- 后端应尽量提供运行中 transcript 的可读快照；如果现有 `.bench-transcript.log` 只在收尾写入，应补一个运行中可读取的快照来源或端点。
- 不能破坏已有 runs 列表 SSE、停止 run、继续对话、删除 run 等操作。
- 不能引入 npm、框架、构建工具或 ORM。
- 所有新增用户可见文案、注释和文档必须使用中文。

## Acceptance Criteria

- [ ] 打开一个 `running` run 的详情后，不刷新浏览器也能看到 transcript 随后台对话进展更新。
- [ ] 打开一个 `running` run 的详情后，`输入 token`、`输出 token`、`请求数` 至少每隔数秒刷新一次，且不会显示空白。
- [ ] 当 stats 文件不存在或 usage 尚未解析到时，详情显示 `等待采集`；当 stats API 失败时，详情显示明确错误提示。
- [ ] 当 run 结束后，详情弹窗展示最终状态、退出码、错误信息、最终 transcript 和最终统计，并停止轮询。
- [ ] 关闭详情弹窗后，不再继续请求该 run 的详情接口。
- [ ] 多次打开不同 run 详情，不会出现多个刷新循环同时写同一个弹窗的问题。
- [ ] 现有 `/api/runs`、`/api/runs-stream`、`/api/runs/{rid}`、停止、删除、继续对话路径仍可用。
- [ ] 至少完成一次手工验收：创建/运行任务，打开 running 详情观察刷新，等待终态后确认最终数据。

## Definition of Done (team quality bar)

- 已按后端和前端 Trellis spec 检查代码风格。
- 若修改后端 API，路由 docstring、类型注解、错误兜底符合 `orchestrator/main.py` 现有风格。
- 若修改前端 modal 刷新逻辑，关闭路径能清理 `setInterval` / `setTimeout` 等资源。
- 手工验证 WebUI 的 runs 列表和详情弹窗关键路径。
- 变更范围和残留限制在最终说明中写清楚。

## Out of Scope (explicit)

- 不做完整的 terminal replay UI 或 xterm 嵌入，除非用户明确选择交互终端方案。
- 不做 running run 的可交互终端，不支持在详情弹窗里向当前 run 输入内容。
- 不做 mitmproxy flow 原文浏览器。
- 不在本次 MVP 展开 stats 诊断细节，例如直接展示 `stats.jsonl` 路径、MITM 解析原因或 flow 原文。
- 不做账号维度 token 仪表盘。
- 不改 runs 表结构，除非实现中确认必须持久化额外指标。
- 不引入自动化测试框架。

## Decision (ADR-lite)

**Context**: running 详情可以做成只读监控，也可以嵌入可交互终端。交互终端会扩大到 PTY/WebSocket 生命周期、输入权限和当前 worker 会话复用问题，风险明显高于本次反馈的核心需求。

**Decision**: 本任务 MVP 选择只读实时展示。详情弹窗轮询刷新 transcript、stats、run 状态和终态信息，不提供输入能力。

**Consequences**: 实现范围更小，能优先解决“running 详情静态”和“统计为空/不清晰”的问题；未来如要介入当前 run，需要另开任务设计交互终端链路。

## Stats Empty State Decision (ADR-lite)

**Context**: stats 为空可能代表采集尚未开始、`stats.jsonl` 尚未产生、usage 尚未出现在响应里，也可能是采集失败。直接显示 0 会误导用户以为确实没有消耗。

**Decision**: UI 对“尚未采集到可用 stats”的状态显示 `等待采集`。只有后端明确返回可用数值时才显示数字；API 失败时显示错误兜底。

**Consequences**: 默认界面保持简洁，避免用 0 误导；详细诊断信息不在本次 MVP 展开。

## Research References

- 代码阅读：`webui/app.js` `openRunDetail` 当前为一次性拉取详情数据。
- 代码阅读：`orchestrator/main.py` `/api/runs/{rid}/stats` 当前聚合 `stats.jsonl` 并返回 token / requests。
- 代码阅读：`images/worker/entrypoint.sh` 当前在任务收口时写 `.bench-transcript.log`。
- Spec：`.trellis/spec/frontend/component-guidelines.md`
- Spec：`.trellis/spec/frontend/state-management.md`
- Spec：`.trellis/spec/frontend/quality-guidelines.md`
- Spec：`.trellis/spec/backend/database-guidelines.md`
- Spec：`.trellis/spec/backend/quality-guidelines.md`
