# 被动额度入口与移除自动查询的证据

## 已有数据和入口

- `orchestrator/main.py:2767` 的 `QuotaGuard.refresh_usage()`：阈值启用时查询 usage，300 秒缓存，失败默认至少 60 秒重试；401／403 修改提示但仍重试，未解析永久错误正文。
- 自动调用分布在 `main.py:3608`（待运行工作的后台 tick）、`6269`（批次）、`6555`（执行前）、`6748`（收尾强制刷新）、`6974`（养号）。`invalidate_usage()` 与 `_policy_decision()` 又把消费后／过期数据变成主动查询门禁。
- `main.py:4350` 的 v3 `Runner.query_quota()` 复用固定容器，`_exec_quota_probe()` 用 Node fetch 请求 `https://api.anthropic.com/api/oauth/usage`。手动入口为 `POST /api/accounts/{aid}/quota`，不能把手动接口删除。
- `account_quota_states` 与 `quota_observation_cursors` 已保存账号身份、窗口状态、来源、文件游标与恢复认领；`QuotaGuard.consume()` 只消费完整 JSONL 行，复用既有归属与乱序合并。
- `cc2api/src/service/gateway.rs:2677`：成功响应只做被动采集；429 也单独处理拒绝窗口。`extract_passive_usage()` 解析 5h／7d／7d_oi 真实响应头，`AccountService.update_passive_usage()` 合并入已有账号数据。
- `cc2api/src/service/runtime_transport.rs:77`：v3 发送器仅记录 `anthropic-ratelimit-unified-*` 和 `retry-after`。`main.py:3272` 已将绑定账号的 API observations 注册到共同额度消费链。
- `cc2api/src/service/usage_poller.rs` 与 `src/main.rs:191`：独立轮询 active OAuth 且 `auto_poll_usage=true` 的账号。v3 使用 `V3_RUNTIME_URL` 启用管理桥，该边界已有多处运行模式判断，适合将轮询禁用限制在 v3，不改非 v3 行为。

## CLI 本地入口

- 官方文档：https://code.claude.com/docs/en/statusline#rate-limit-usage 。statusLine 通过 stdin 接收 `rate_limits.five_hour/seven_day.used_percentage`、`resets_at`；Pro／Max 的这些字段在会话首次 API 响应后出现，各窗口独立可缺失，reset 到期后会移除窗口。
- 文档说明 statusLine 是本地命令，默认跟随会话事件更新；本任务不设置 `refreshInterval`，不在采集命令中调用 HTTP 或 `/usage`。
- 只读核对服务器当前 2.1.293 包：`package.json` 版本为 2.1.293，实际二进制包含 statusLine、rate_limits、five_hour、seven_day、used_percentage、resets_at 字段。这是静态证据，不能冒称完整采集已通过真实运行验证。
- `orchestrator/account_runtime.py:714` 的 `_cli_setup()`、`start_run()` 和 `begin_continue()` 负责固定 HOME 与作业准备；`cleanup()` 已恢复作业 hook 设置。新增采集须接入同一生命周期，保留原设置、登录路径与原生 TLS。
- 旧 worker／profile 默认设置明确移除长期 hooks/statusLine（`main.py:335`、`images/worker/entrypoint.sh:130`）。不能把 v3 运行采集配置写回旧 profile；只给正式 CLI 执行设置临时采集，退出时按快照恢复。

## 状态与兼容约束

- 既有被动规范已定义：首次无观察正常任务可以启动；窗口到期只认领一个已有正式执行；耗尽且无可信 reset 时等待，不伪造未来 reset；账号暂停／invalid_grant 不自动恢复。
- 当前 v3 自动查询门禁与这些行为不兼容，必须一并移除其 300 秒／dirty／retry 条件，不能只删 HTTP 调用后留下永久等待。
- `_observe()`、`quota_observation()`、`merge_quota_observation()`、`admit()/release()` 应优先复用。状态不能因窗口缺失、CLI 重放旧数据或 reset 到期而伪造 0%。
- 本任务规划只涉及 v3 功能变更与本地隔离验收；生产交付遵循现有 v3 发布／备份 SOP，不把本次功能确认解释成直接切换镜像。

## 相关规范

- `.trellis/spec/vibecoding-bench/backend/database-guidelines.md`：被动额度等待及原任务恢复、账号级阈值与旧自动采样契约。
- `.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md`：作业租约、固定 HOME、控制目录、原生 TLS、API 观察。
- `.trellis/spec/cc2api/backend/service-architecture.md`：OAuth usage 与被动写入、v3 模式、后台任务边界。

## 验证限制

- 不对封禁账号发额度或模型验证请求，不输出凭据或原始 statusLine 会话内容。
- 当前已确认网络出口在账号代理内；本次实现仍应通过隔离代理与请求计数测试证明被动采集不新增请求，不能用“同一代理”替代行为验证。
