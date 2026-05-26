# implement.md

## Implementation Checklist

- [x] 重新确认 active task 为 `.trellis/tasks/05-26-runs-running-token-stats`，并按 Trellis 路由进入实现阶段。
- [x] 阅读相关定义和上下文：`orchestrator/main.py` runs schema、runs API、stats API、transcript API；`webui/app.js` runs 渲染和 modal close helper；`images/worker/entrypoint.sh` tmux 等待与 transcript capture 逻辑。
- [x] 后端/worker：让运行中的 run 能产生可读取 transcript 快照，优先在 worker 等待循环中周期性 capture pane 到 `/workspace/.bench-transcript.log`。
- [x] 后端：检查 `/api/runs/{rid}/transcript` 和 `/api/runs/{rid}/stats` 的错误兜底；stats 端点必要时新增兼容字段标记是否已有可用采集数据。
- [x] 前端：新增 run detail 生命周期状态和收口函数，确保打开新详情、关闭 modal、Esc、遮罩关闭、切 tab 都会清理刷新句柄。
- [x] 前端：重构 `openRunDetail(rid)` 为可重复刷新渲染，running / queued / stopping 状态继续刷新，终态停止。
- [x] 前端：修正 stats 展示逻辑，区分真实数值、`等待采集`、接口失败，避免 catch 后 `{}` 导致空白。
- [x] 前端：控制 files 刷新频率，避免 running 时每次都递归扫描 workspace；终态至少刷新一次文件树。
- [ ] 手工验证 running 详情的 transcript、stats、终态停止刷新和关闭资源释放。
- [x] 更新最终说明，明确 token 统计为空的根因和仍可能出现 0 的场景。

## Validation

- `python3 -m py_compile orchestrator/main.py`
- `bash -n images/worker/entrypoint.sh`
- 手工运行 WebUI：
  - 进入 runs tab，确认列表 SSE 仍刷新。
  - 启动一个 run，在 `running` 时打开详情，观察 transcript 和统计刷新。
  - 关闭详情后用浏览器 Network 确认不再继续请求该 run 详情。
  - 等 run 到终态，确认详情停止刷新并显示最终状态。

## Review Gates

- 实现前：确认规划文件已锁定 MVP 为只读实时详情，不做可交互终端。
- 实现后：如果 token 长时间显示 `等待采集`，需要给出可操作排查路径：stats 文件是否存在、请求阶段记录是否写入、响应 usage 是否能被解析、MITM 是否捕获 Anthropic 域名。
