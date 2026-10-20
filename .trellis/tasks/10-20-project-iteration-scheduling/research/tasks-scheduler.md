# Tasks 调度复用证据

- `orchestrator/main.py:10280` 的 `BatchIn` 已有 `concurrency`、`interval_min_sec`、`interval_max_sec`、`timeout_sec`。
- `orchestrator/main.py:10418` 的 `create_task_batch` 在锁外准备题目、执行一次随机洗牌，再在事务内按该顺序写入 `task_batch_items`。持久 item ID 固化顺序。
- `Scheduler._execute_batch` 读取 `next_launch_at` 并恢复等待，按 item ID 取未完成记录；先填充并发窗口，后续等收口后抽取间隔。
- `_random_batch_delay` 使用闭区间 `random.randint(low, high)`；`_set_batch_next_launch` 持久化截止时间。暂停等待循环检查父状态。
- v3 的 `PER_ACCOUNT_CONCURRENCY` 固定为 1；`AccountRuntime` 和网关 CLI 租约同样维持每账号一个 CLI。Tasks 页面允许填写 2 并不证明 v3 实际可以同时执行两个 CLI。
- 项目模式 `DEFAULT_POLICY` 为活动池 3、修复 2、超时 1800 秒；`create_batch` 当前按提交的键顺序保存 `visit_order`，没有洗牌；`next_launch_at` 只有 schema 定义而无读写。
- `ProjectIterationManager._drive_batch` 只允许每账号一个未收口的项目尝试。阶段边界后清空当前实例，按 `visit_order` 回到可继续的已开始实例；未开始实例只在池有空位时引入。

## 并发变更历史与用户决定

- `git log -S 'PER_ACCOUNT_CONCURRENCY = 1 if V3_ENABLED' -- orchestrator/main.py` 与 `git blame -L 72,84` 定位到 2026-10-12 的 `34f56c02242f43d996fb63e5a42a176f66e65492`，提交标题为 `feat(v3): 实现固定账号环境与统一部署`。
- 该提交明确将 `PER_ACCOUNT_CONCURRENCY = int(os.environ.get("PER_ACCOUNT_CONCURRENCY", "2"))` 改为 `PER_ACCOUNT_CONCURRENCY = 1 if V3_ENABLED else int(os.environ.get("PER_ACCOUNT_CONCURRENCY", "2"))`。
- 当前 `orchestrator/main.py:6386` 的 `Scheduler._sem()` 使用该常量，`Scheduler._execute()` 在 6751 行取得对应账号信号量。`BatchIn.concurrency` 默认 2，`create_task_batch()` 仍将并发限制在 1～2，因此存在批次配置和实际运行上限不一致。
- `orchestrator/account_runtime.py:957` 的 `claim()` 在 `self.jobs` 中以 environment ID 仅登记一个作业，第二个认领被拒绝；`release()` 也按单作业清理 `runtime/execution.json`。不能只放大调度器信号量。
- `cc2api/src/service/runtime_lease.rs` 的 `RuntimeGate.state` 为 `Mutex<Option<RuntimeLease>>`；`prepare_cli()` 虽允许 API 同时入场，但 `prepare_mode()` 对不同来源的第二个 CLI 仍返回 occupied。
- 用户已明确选择同账号多项目真正并行；本任务必须规划运行时及租约的配套变更，并回归 Tasks 原有可配置并发，而不是保留单 CLI 再推荐用户多建账号。

规划方向：复用 Tasks 的参数命名、一次洗牌与持久等待模式，增加项目模式必需的活动池和轮换语义。账号 CLI 容量由 Tasks 与项目迭代共同遵守；每个执行独立登记、续期、对账及清理，维护保持排他。同一项目的依赖步骤不并行写目录，活动池不能替代实际并发。

## 用量控制与间隔的边界

- 用户已在“账号既有 5h／7d 已用比例”与“另加每日 token 预算”之间选择前者。额度阈值由账号统一配置；token 继续用于统计，本任务不新增按每日时长、次数或 token 计量的预算。
- `orchestrator/main.py:2901` 的 `QuotaGuard.policy_snapshot()` 读取账号已有的两个已用比例阈值；`_policy_decision()` 根据有效的 5h／7d 观察和恢复认领决定是否允许下一轮。该窗口不是自然日预算，不能把窗口用量差直接称为当天消耗。
- `orchestrator/main.py:7731` 的 `_project_admission()` 已将项目执行接入账号窗口、共用真实额度和普通任务阈值。规范要求自设百分比只阻止下一轮，在途按原计划完成；并行在途执行可能使观测值越过自设阈值。
- `orchestrator/project_iteration.py:423` 的 `native_usage()` 仅汇总本 run 字节区间内去重主响应，明确排除 sidechain／meta。证据缺失、截断或扫描越界时返回 `usage_available=False`。现有统计不能直接声称是完整账号或所有子会话的 token 总量。
- `orchestrator/main.py:10180` 的步骤用量接口聚合首轮与修复尝试，以 `known_attempts` 和 `complete` 展示已有记录。只要部分尝试有统计也可能返回部分总数，消费方必须检查完整性，不能拿显示值作为无遗漏的日预算台账。
- Tasks 的 `_execute_batch()` 先填充并发窗口，后续等待至少一个 run 收口，然后在配置的闭区间抽取随机补位间隔；`_set_batch_next_launch()` 保存截止时间，恢复沿用原截止，不重抽。此规则可作为项目调度的交互参考。
- 规划建议：用量门禁决定是否允许投放，随机间隔决定何时补位，账号并发决定最多同时运行多少个执行；三个条件和运行窗口共同满足才可启动。不能以 token 估算精确等待时长，也不能把等待补位实现为暂停其它在途作业。
