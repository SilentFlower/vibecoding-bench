# 养号额度阈值的现有机制

## 实际配置与页面

- `accounts` 已有 `warmup_enabled`、`warmup_interval_min_hours`、`warmup_interval_max_hours` 等字段，尚无养号额度阈值字段（`orchestrator/main.py:1256`）。
- `WarmupConfigIn` 定义 cc2api 绑定、启用开关和随机小时区间（`orchestrator/main.py:7024`）。
- `PUT /api/accounts/{aid}/warmup` 在绑定/凭据所有权锁内校验绑定，再持有数据库锁写入配置；改变绑定时另走排他维护门禁（`orchestrator/main.py:7353`）。
- 前端已有账号级养号弹窗，`openWarmupModal` 读取账号字段，`saveWarmupConfig` 提交对应请求（`webui/app.js:317`、`webui/app.js:350`）。用户已选择账号级阈值，两个窗口可独立设置或关闭，复用此入口。

## 必须覆盖的调度入口

- `WarmupScheduler.trigger_account` 先检查正式 CLI 工作/租约，再消费真实额度并检查共同门禁；通过认领后同步凭据、选择题目并创建 task/run（`orchestrator/main.py:6131`）。
- `_claim_account` 在事务内重读启用/绑定/到期条件，已有 queued/running/stopping/quota_wait 养号时不会重复建 run（`orchestrator/main.py:6418`）。
- `Scheduler` 在排队后的实际启动阶段重读账号、run 与父任务，再执行 `QuotaGuard.admit`；额度可能在排队期间发生变化（`orchestrator/main.py:5812`、`orchestrator/main.py:5857`）。
- `QuotaGuard._resume_account` 从 quota_wait 重建原 run 的执行代次，保留执行快照；目前仅检查养号开关，尚无提前停止阈值（`orchestrator/main.py:3160`、`orchestrator/main.py:3182`）。
- `_tick` 只扫描 `warmup_next_run_at` 非空且已到期的账号，阈值等待的恢复设计必须考虑 next_run_at 为空后如何重新进入调度（`orchestrator/main.py:6397`）。

## 额度事实与共同门禁

- `QuotaGuard.snapshot` 从账号身份匹配的 `account_quota_states` 读窗口、观察来源、恢复认领和永久异常；公共额度摘要不包含内部身份及凭据（`orchestrator/main.py:2685`）。
- 窗口键是 `five_hour`、`seven_day`，用量 `utilization` 为已用百分比；`reset_at`、`observed_at` 以 UTC 秒表达（`orchestrator/quota_protocol.py:75`、`orchestrator/quota_protocol.py:80`）。
- `quota_decision` 只为耗尽窗口计算等待与到期恢复机会，reset 到期不修改真实窗口用量（`orchestrator/quota_protocol.py:145`）。
- `QuotaGuard.admit` 是所有正式执行共用的保护入口；养号阈值不能无条件加进它并阻断普通任务（`orchestrator/main.py:2730`）。
- 现有测试 `orchestrator/test_quota.py` 已覆盖真实头部合并、过期窗口、原 run 恢复和禁止主动查询，可作为新规则的基线；新增测试必须验证实际行为及不同入口，而非只镜像配置函数。

## 待定范围对实现的影响

- 用户已选择同时暂停运行中养号，并要求已发出的请求正常收尾。需要按 run/source/代次发布养号专用暂停信号、保存原会话，确保不继承到普通 CLI 或共享 API；不能用停止整个账号容器实现。
- Recorder 的 `responseheaders` 会立即观察真实用量，`requestheaders` 负责下一条请求的门禁（`images/sidecar/recorder.py:482`、`images/sidecar/recorder.py:508`）。新阈值应及时阻止后续请求，但不能在成功流仍未完成时通知 worker 强制退出。
- 现有 `check_quota_pause` 在读取有效控制文件后直接发布退出状态，主循环随即退出，缺少等待已接受请求完成的阈值专用证明（`images/worker/entrypoint.sh:1111`、`images/worker/entrypoint.sh:1764`）。不可只在响应头阶段复用这个信号就宣称当前请求会正常收尾。
- 最终方案应区分命中后的请求阻断与执行暂停发布，并验证流式响应、并行请求、断流及取消；既有真实额度耗尽和认证错误行为保持原契约。
- 未观测额度或窗口到期后的恢复属于产品行为；不以实现便利替用户决定放行、等待或主动查询。
- 现有 `_resume_account` 还会在共同耗尽门禁消失时将账号的 `quota_wait` 状态重新排入养号，且 `warmup/resume` 目前只重新启用调度；阈值等待需要同步覆盖这两个入口，避免被通用恢复绕过（`orchestrator/main.py:3220`、`orchestrator/main.py:7493`）。
- 通用 `recovery_source` 同时协调正常任务的真实耗尽恢复。养号阈值的未知/过期机会不能关闭共享 API 入场或把普通任务误标为耗尽；独立认领与代次持久化设计需在最终方案中说明。
- 若选择未知/到期后放行一次正式养号请求，必须记录已用机会并消费真实结果；无法获得有效窗口时保持等待，不能每轮 timer 都重试，也不能在 reset 到期直接清零用量。这是待用户选择策略的必要技术约束。

## 证据边界

本轮只读取现有代码和规范、创建规划记录，未修改产品代码、运行 task.py start 或操作生产服务。旧任务与原用户脏文件保持不变。
