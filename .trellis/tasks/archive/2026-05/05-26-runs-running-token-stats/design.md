# design.md

## Technical Design

### 现有链路

- 列表实时性：`webui/app.js` 进入 runs tab 后建立 `/api/runs-stream` EventSource，后端 `stream_runs()` 每秒查询 runs 表并推全量列表。
- 详情静态性：`openRunDetail(rid)` 打开 modal 后一次性并发拉取 run、files、stats，再单独 fetch transcript；之后不再刷新。
- 统计来源：sidecar 的 `Recorder` 写 `stats.jsonl`，后端 `/api/runs/{rid}/stats` 扫描所有匹配 run id 的 stats 文件并聚合。
- transcript 来源：后端 `/api/runs/{rid}/transcript` 只读取 `data/workspaces/<run>/.bench-transcript.log`；worker 当前主要在 run 收口时 capture tmux pane 写入该文件。

### 建议方案

MVP 采用“详情弹窗轻量轮询 + 后端补运行中 transcript 快照能力”的只读方案：

1. 前端新增 `state.runDetail` 保存当前详情弹窗的 run id、刷新句柄和最近一次请求序号。
2. `openRunDetail(rid)` 打开详情后先清理旧详情刷新，再渲染 loading，随后调用一个内部刷新函数。
3. 刷新函数每次拉取 `/runs/{rid}`、`/runs/{rid}/stats`、`/runs/{rid}/transcript`，必要时拉取 `/runs/{rid}/files`；数据返回后重绘同一个 `#modal-content`。
4. 当 run 状态仍在 `queued` / `running` / `stopping` 时继续调度下一次刷新；终态后停止。
5. modal 关闭、遮罩关闭、Esc 关闭、切 tab 时统一调用详情收口函数，清理刷新句柄。
6. 后端 transcript 端点优先返回已存在的 `.bench-transcript.log`；为了 running 可见，补一种运行中快照写入或读取路径：
   - 优先选择低风险做法：worker 在等待完成期间周期性 capture pane 到 `.bench-transcript.log`。
   - 若实现时发现 worker 循环结构不适合周期性写文件，再在 orchestrator 侧通过 worker container exec `tmux capture-pane` 生成快照，但要评估 docker exec 频率和失败兜底。
7. stats 展示不新增表字段，继续读取 `stats.jsonl`。后端可在 `/api/runs/{rid}/stats` 中新增兼容字段标记 stats 是否可用，前端据此区分“真实数值 0”和“等待采集”，避免把失败 catch 成 `{}` 后展示空白。
8. 不接入当前 running worker 的输入通道，不新增交互终端 WebSocket。

### 数据契约

- `/api/runs/{rid}`：保持现有字段，详情用 `status`、`exit_code`、`error`、`started_at`、`ended_at`。
- `/api/runs/{rid}/stats`：保持返回 `tokens_in`、`tokens_out`、`requests`、`errors`。为支持 `等待采集`，可新增兼容字段，例如 `available`；当 stats 文件不存在或尚无可用记录时 `available=false`，前端显示 `等待采集`；当 `available=true` 时显示数值。
- `/api/runs/{rid}/transcript`：保持 `text/plain`。运行中无内容时仍可 404，前端显示“等待 transcript”；有快照时返回当前快照文本。
- `/api/runs/{rid}/files`：可低频刷新或只在终态刷新，避免 running 时频繁递归扫描 workspace。

### 兼容性与取舍

- 不把详情实时性并入 `/api/runs-stream`，因为列表 SSE 当前只推数据库行；把 transcript 和 stats 塞进 1Hz 全量列表会放大 payload，也会让列表和详情边界变乱。
- 不新增 WebSocket，详情只读展示用轮询更简单，和当前原生 JS 架构匹配；可交互终端留给后续单独任务。
- token 输出可能天然滞后：响应 usage 通常在 Anthropic 响应结束或 SSE 后段才可解析。运行中应至少先看到请求数增长；输入/输出 token 可在 usage 出现后更新。
- 若 MITM 未捕获到 Anthropic 流量，请求数和 token 仍可能长时间不可用；这时 UI 在 MVP 中显示 `等待采集`，详细诊断留给后续任务。

## Rollout / Rollback

- 回滚前端刷新逻辑时，只需恢复 `openRunDetail` 的一次性拉取行为，并删除 `state.runDetail` 收口路径。
- 回滚 worker transcript 快照时，保留后端 transcript 端点现状即可；详情仍能在终态展示最终 transcript。
- 不涉及数据库结构变更，回滚无需迁移数据。
