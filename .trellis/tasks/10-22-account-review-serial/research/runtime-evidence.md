# 串行复用方案取证

本节现状和行号均记录开工前基线 `2d5a99051a5a95600be6d7b0f1c01777d35c91d4`；本轮实现进展另见 `implementation-progress.md`。

## 已确认的入口与约束

| 证据 | 当前行为 | 对本任务的约束 |
| --- | --- | --- |
| `orchestrator/account_runtime.py:631`、`723`、`2116`、`2201` | 登录按普通三角色创建，评审布局只在首次创建且显式请求时写入；保存登录复用容器 | 必须覆盖新登录创建到项目评审的交叉路径 |
| `orchestrator/resource_budget.py:32`、`46` | 普通预算为网络 256 MiB、发送器 128 MiB、剩余给 CLI；旧场景预算再从 CLI 划出 512 MiB | 新串行模式沿普通预算，旧函数只保留兼容校验职责 |
| `orchestrator/project_scenarios.py:1289` | 候选严格释放后才排程序验收和评审 | 同一任务本已按先后顺序处理，问题还包括其他任务重叠 |
| `orchestrator/project_review_runtime.py:314`、`374`、`396`、`451` | 私有评审查固定布局并认领共享 CLI，另启容器 | 不能仅更改并发参数或删除检查，必须真正互斥并交接资源 |
| `orchestrator/account_runtime.py:1019`、`1084` | `shared_cli=False, exclusive=False` 使用 `prepare-cli`，阻止其他 CLI，但不排空 API | 可复用现有非共享 CLI 租约，不需要修改网关协议 |
| `cc2api/src/service/runtime_lease.rs:254`、`293`、`551` | `prepare_cli` 拒绝现存 CLI holder，同时允许 API 进入；已有对应 Rust 测试 | 保持发送连接，不把串行评审升级为整个账号的 API 维护 |
| `orchestrator/account_isolation.py:147`、`201`、`220` | CLI、网络、发送器独立；CLI 是 UID1000 的 `v3-cli-control idle`，使用网络角色的 netns | 可单独停止并重新启动同一个 CLI 容器，保留网络、发送器和持久 HOME |
| `images/account/cli-control.py:261` | CLI 空闲 PID1 有正常信号收口，监督器记录进程证明 | 停止后须核 Docker 实际状态；不能把暂停视为已释放 RAM |
| `orchestrator/account_runtime.py:1133`、`1157`、`1773`、`2740`、`2880` | 执行记录按共享模式选择路径；现有私有评审清理主要位于 shared 分支，重启有单作业及共享作业两条分支 | 改为非共享评审时须同步持久字段、清理及两条恢复入口 |
| `orchestrator/account_runtime.py:2684`、`2710` | 指标校验根据普通预算或已有布局交叉核对 | 评审使用自己的真实 cgroup；不能向已停止的固定 CLI 发采样 exec |
| `orchestrator/main.py:7829` | 项目准入已检查非共享作业与容量 | 还须在通用 CLI 认领边界处理跨批次优先级和切换状态 |
| `deploy/v3/verify_project_scenarios.py:182`、`245` | 当前验收主动要求候选和评审重叠，并在评审时 exec 固定 CLI | 必须改为观测互斥及资源交接，不能删除验证来掩盖旧假设 |

## 选定的最小机制

采用“确认空闲 → 非共享 CLI 租约 → 停固定 CLI → 运行私有评审 → 停净评审 → 恢复原 CLI → 释放租约”。保持原容器 ID、环境 generation、HostConfig 和持久目录；不做动态缩内存，也不要求新的宿主 cgroup 配置。

1536 MiB 配置下，普通 CLI 上限为 1152 MiB；评审阶段在固定 CLI 已停止的前提下借用相同 RAM，上限总和仍为 256＋128＋1152 MiB。额外 swap 仍只属于原固定 CLI，私有评审禁止额外 swap。旧预留布局保持其原 CLI 配额，串行评审在核验原预算后使用相同交接机制，不在线扩容旧 CLI。

## 仍须在实现中取得的证据

- 真正的 Docker 停止、再次启动与清理时序，以及期间独立发送连接保持。
- 登录与项目链路串起来的冷环境验证；此前两条路径分别验证过不能替代交叉回归。
- 每个切换阶段中断后的重启对账，包括私有容器创建 ACK 丢失、Docker 停止结果未知及租约释放失败。
- 本地合成 CLI 只能证明机制，真实代理、OAuth、冷安装与模型回答仍需后续真实账号验收。

本次规划只读源码与既有审计文件，并写入本任务材料；没有修改产品代码、生产配置或真实账号。
