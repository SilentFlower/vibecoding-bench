# Bench 功能扩展实现计划草案

## Implementation Checklist

- [ ] 补 schema：topics 表、batch 调度相关表/字段、runs 状态/关联字段迁移。
- [ ] 实现 topics CRUD API，并把 `topics.md` seed 到 DB。
- [ ] 改 topics UI：新增/删除/详情编辑；移除点击 topic 创建 task 的行为。
- [ ] 实现账号 profile 白名单同步：task/继续对话成功、失败、异常、timeout、停止收口时回写 `.credentials.json`、`.claude.json`、`settings.json`，不回写 sessions/telemetry/backups。
- [ ] 实现 accounts 额度查询后端：按账号 SOCKS5 启临时 worker/sidecar，通过 OAuth usage API 查询 5h / 7d usage。
- [ ] 改 accounts UI：额度查询按钮、loading、结果/缺字段/失败态展示。
- [ ] 设计并实现 batch scheduler：账号维度、多 topic、多并发、随机区间间隔投放。
- [ ] 改 tasks UI：账号选择、多 topic 选择、全选、并发和随机区间间隔配置、批次启动、删除按钮。
- [ ] 实现 runs 停止、删除、继续对话 API；继续对话走 WebSocket PTY，启动前把账号 profile 的最新凭据覆盖到 run `.claude-home`。
- [ ] 改 runs UI：操作按钮、状态刷新、继续对话 xterm modal。
- [ ] 修复 stats：确认 `.flow` 中真实请求结构，修正 `recorder.py` 或 sidecar 启动参数，确保 `stats.jsonl` 生成。
- [ ] 远端部署并用真实账号跑验收。

## Validation

- `python3 -m py_compile orchestrator/main.py`
- `bash -n images/worker/entrypoint.sh`
- `bash -n images/sidecar/start.sh`
- `node --check webui/app.js`
- `git diff --check`
- 远端手动验收：
  - accounts 额度查询经过 SOCKS5。
  - topics 新增/删除后重启仍存在。
  - tasks 批量启动后同账号最多 2 个 running。
  - tasks 可软删，默认列表隐藏，磁盘产物保留。
  - running run 可停止并清容器。
  - completed run 可继续对话。
  - 旧 run 继续对话前会使用账号最新 `.credentials.json`，不会因为 workspace 内旧 token 直接失败。
  - task/继续对话后账号 profile 的 `.credentials.json` 能随 Claude Code 自动刷新而更新。
  - task 失败、异常退出、timeout 或用户停止时，已刷新的 `.credentials.json` 仍会尽量回写。
  - runs 可软删，默认列表隐藏，workspace/flow/transcript 保留。
  - 成功 run 的请求数/token 统计非固定 0。

## Review Gates

- [x] 开始实现前确认额度字段 MVP 范围：先做 5h / 7d，7d Sonnet 单独额度显示未返回/暂不支持。
- [x] 开始实现前确认 topics 持久化策略：SQLite 为主，`topics.md` 首次 seed。
- [x] 开始实现前确认动态间隔策略：随机区间间隔。
- [x] 开始实现前确认继续对话的交互形式：交互 TUI。
- [x] 开始实现前确认删除是否清理磁盘产物：软删 DB，保留磁盘产物。
- [x] 开始实现前确认账号凭据同步策略：运行结束白名单回写 `.credentials.json`，继续对话启动前用账号最新凭据覆盖旧 run workspace。
- [x] 开始实现前确认异常路径凭据策略：失败、异常、timeout、停止都要尽量回写刷新后的 `.credentials.json`。
