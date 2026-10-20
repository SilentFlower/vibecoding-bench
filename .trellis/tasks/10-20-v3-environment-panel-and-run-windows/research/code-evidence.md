# 环境面板和当地运行窗口：代码证据

以下保留最初规划阶段的取证基线及当时状态；最终范围、实施和交付以父任务最新三件套为准。

## 基线与范围

- 仓库分支 v3，HEAD `7d705e3a64b321073c6e31811d9e4ca6795e8749`。
- 创建规划前没有当前任务和 untracked flow；原有工作区变更由父任务 `task.json` 的 intentRouting baseline 保存。
- 本轮只研究代码并写任务规划，不修改产品代码、不操作生产环境。
- 物理面板与时间控制可分别验收，拆成同一父任务下的两个子任务；当前父任务保持 planning。

## 面板数据

- `webui/app.js:83` 的 `renderEnvironments()`：基础 hostname/mem/tz/lang、generation、角色、身份、CLI 版本与维护按钮；可直接扩展详情入口。
- `orchestrator/main.py:11196` 的 `/api/environments`：读取 SQLite 指纹，核对角色和设备身份；没有完整的物理特征快照或采集端点。
- `orchestrator/account_runtime.py:485` 的 `role_status`：按角色归属与批次核对，返回 running/stopped/缺失/不匹配/未知；不负责唤醒。
- `orchestrator/system_profile.py:16`～`:22`：DMI 两目录六字段及 schema；`:47` 起系统探针和 DMI 探针可作为只读采集模式的参考。不要把现有校验函数的副作用或异常语义直接当面板契约。
- 已有画像分别保存 CPU/内核与计算机 DMI；显示必须区分合成保存配置和实际 CLI 读取结果。真实 cgroup RAM、CPU 能力、RSS 的契约见 account-runtime-v3，不可套用截图的宿主资源值。

## 时区与入口

- `orchestrator/main.py:2696`：`_effective_account_timezone` 的 v3 路径优先查询已持久化环境，并通过 `AccountRuntime.execution_environment` 读取 TZ。未创建环境时才采用显式值或洛杉矶默认。
- `orchestrator/main.py:8150`：账号列表返回有效时区；`webui/app.js:559` 当前只显示时区名称和 auto/manual，不显示当地时钟或窗口。
- `orchestrator/main.py:6173`：`Scheduler.submit` 创建执行线程；`:6629` 的 `_execute` 在信号量和 owner 锁后重读账号。窗口必须在实际启动前复核。
- `orchestrator/main.py:6212`：批次恢复/投放有持久 next_launch_at、并发及 quota_wait；时间窗口不能把原间隔清零，也不能在长等待期间使用旧账号快照。
- `orchestrator/main.py:7047`、`:7321`：手动立即养号和后台定时最终进入 trigger_account，须在同步凭据或认领新轮之前检查时间窗口。
- `orchestrator/main.py:10766`、`:5499`、`:5713`：续聊包括创建会话和后续输入两个边界，不能仅拦截页面的“继续”按钮。
- `orchestrator/main.py:10185`：抓包使用独立创建入口；是否纳入必须写入最终范围矩阵。
- `orchestrator/main.py:5814` 的 OAuthRefreshScheduler、独立网关 API 不是 bench CLI 调度入口。建议本任务不改它们，最终 Brief 明示范围供审核。

## 已加载规范

- guides/backend/frontend 三个索引。
- account-runtime-v3：真实进程指标、持久计算机身份/DMI 读取契约。
- database-guidelines：账号阈值、运行中停止、被动采集及恢复契约。
- topic-prompt-contract：prompt 与恢复计划只生成/冻结一次，时间窗口不得重造历史任务。

## 待收敛

- 用户已回答：窗口关闭时本轮完成再休息；自设额度百分比强停也改为本轮完成后等待。
- 在父任务范围中增加 P3 子任务，先调整额度策略，再实施窗口集成；不重新打开已关闭的旧强停任务。
- `Scheduler._enforce_running_quota` 是当前 v3 主强停入口。最初检查到 Recorder 仍有逐请求阈值暂停；继续核对 `AccountRuntime.start_run` 后确认 v3 normal/warmup 实际均为 passthrough，driver QUOTA_WARMUP=0。因此旧 Recorder 逻辑只需作为边界回归，不计划修改旧运行模式。
- `process_metrics.memory_limit` 已安装到账号镜像 `/usr/local/bin/process_metrics.py`，物理采集应复用其 cgroup RAM 读取，不另造宿主总内存口径。
- 新增的窗口只影响新执行/新交互输入，已经启动 run 中的原定补充属于本轮，不被窗口或自设百分比打断。
