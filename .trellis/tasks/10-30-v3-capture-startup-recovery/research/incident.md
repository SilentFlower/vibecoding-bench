# 线上启动故障证据

## 核对范围

- 本节记录 2026-10-30 初始只读排障事实：通过 `.deploy/vibecoding-bench.env` 指定的既有 SSH 入口检查，配置和凭据未输出，初始检查未修改线上资源；后续已授权处置见文末。
- 部署：`us`，配置 `/opt/vibebench-v3-us/v3.env`，数据根 `/srv/vibebench-v3-us`。
- 故障及初始排障时批次：`ci-41000159989-1`；父仓源码 `af2300f2d6d91aa5d861646fe957996c5c78804b`；子仓 `046c0a28a518337ed2c9745c4193fea47904cb1f`。
- 相关管理端和网络脚本 SHA256 已与本地文件逐一比较，全部一致：`pi_terminal.py`、`account_runtime.py`、`projects_runtime.py`、`network-context.py`、`recorder.py`。

## 原工作与现场

| 项目 | 实际值 |
| --- | --- |
| 账号 | `10`，账号名 `10-30`，未绑定 cc2api |
| 工作 | `9772ee0ad1c14f998f6787eae8fa87b4` |
| 工程／目标 | `arrow / AR-WEEKDAY-DEV` |
| 目标文案 | 让数字星期解析与格式化和命名星期一致 |
| 原 Claude 会话 | `7254b6c1-5576-469a-b169-7fea6a4cbdbd` |
| 控制代次 | `29` |
| 环境／环境代次 | `4201ce3f913841d4b2a5a96bc996bb40 / 7` |
| 作业尝试 | `d7e9e29e8c5940f3ba9c` |
| 累计工作区 | `projects/arrow-e0df329e` |
| 创建／失败时间 | 北京时间 `14:28:39.997 / 14:28:43.422` |
| 故障 | `startup_unknown`、`preparing`、`ValueError`、真实失败次数 `1` |
| 控制状态 | 工作与 agent 均为 `blocked`，计划开启但状态为 `blocked` |
| 启动与输入 | `started_at = NULL`、`runtime_json = NULL`，动作记录与原生会话文件均为 `0` |
| 冻结设置 | CLI `2.1.293`、来源 `global`、思考预算 `high`、模型 `opus[1m]` |
| 工程版本 | `96d27cdbd7a24969ba5acd5c7e17e8e98d98c8edcc2aebf1f5c3bb25d7dfb72b` |
| 抓包开关 | `projects_capture_enabled = 1`、`warmup_capture_enabled = 0` |

## 准备边界证据

1. 工作区目标输入证明在 UTC `06:28:41.486`、Python 证明在 `06:28:41.598` 更新，版本与依赖准备已越过。
2. 尝试目录只含 `settings.json`；控制目录为空，没有 driver／配置／进程证明，也没有对应原生会话。
3. 抓包证据目录为 `flows/group-d7b4432bf4b54cf4fe84/executions/106087d25d34a6838064`，额度配置已于 `06:28:41.642` 写入；没有 `capture.flow`、HTTP／TLS／统计记录。
4. `capture-status.json` 为 `closed`、`recorder_graceful = true`，UTC `06:28:43.396` 更新。当前网络确认是透传模式；执行登记文件已删除。
5. CA 文件变更时间、Recorder 日志均停留在上一轮 `05:50`～`05:56`，本次没有进入新的 CA 恢复与 Recorder 记录阶段。这使故障范围落在抓包网络切换前段，但不能替代原始异常。
6. 网络容器 `memory.events` 中 `max/oom/oom_kill` 均为 `0`，峰值内存约 164 MiB、限制 256 MiB；`pids.events.max = 0`。宿主该时间窗口没有 OOM 内核记录，磁盘和相关临时盘均有可用空间。
7. 相关 Docker 日志和内核日志没有原始异常；该时间段 Docker events 已无保留记录。故障事件 `27231` 仅保存 `exception_type = ValueError`。

## 代码约束与待验证假设

- `PiTerminal.start` 在网络切换之后才创建 driver、执行配置和 Docker exec，启动本身不自动发送工程目标输入。
- 该方法的异常路径先执行 cleanup；cleanup 如果再次失败，原异常可能被覆盖。诊断必须在收口之前保存。
- `_configure_network_context` 将非零返回包装为 `ValueError`；最外层只保留异常类型，底层原因因此丢失。
- `_terminate_listener` 的进程读取和退出竞争值得用隔离夹具验证；当前没有证据认定它就是历史根因，不能据此先改进程安全检查。
- `_manual_retry_event` 明确没有白名单接纳 `startup_unknown`。恢复应补充严格的人工准入，不能伪造其它错误类别、改为自动重试或手工清空故障事实。
- 执行任何线上动作前必须重新查询当前状态；本表是本轮只读检查事实，不能作为之后线上仍空闲的许可。

## 最终处置

- 隔离真实进程测试证实 `/proc` 已打开句柄在目标退出回收后读取会报 `ESRCH / errno=3`，对应修复及回归通过；同时修复 CA 发布异常被 socket 重试吞掉的问题，并增加私有启动诊断。历史原始异常仍缺失，不能宣称该竞争就是最初的精确根因。
- 经确认的业务提交 `a32b2854` 对应联合发布 `ci-41034190954-1`，已交付 us，保留原身份与资源参数；固定环境从第 7 代变为第 8 代。
- 原工作在既有管理入口正常 POST start 后恢复到第 31 代，事件 `27232 / 27237` 分别证明人工恢复和真实启动后的故障解除。本轮接续验收既有入口的这次启动，没有重复调用 start 或重放输入。
- 原会话已出现可信助手响应，实际完整抓包含完成的模型 HTTP 200，原生 API 错误为 0；原工作、session、工作区和冻结设置保持。服务／身份／镜像回收核对已通过，详情见 `../validation.md` 和 `../release.md`。
