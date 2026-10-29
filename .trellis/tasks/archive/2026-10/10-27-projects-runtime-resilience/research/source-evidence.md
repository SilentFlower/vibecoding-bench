# 排查与规划证据

## 用户问题

- 2026-10-27 截图中的 `cerberus`／`CERBERUS-O01-DEV` 创建于北京时间 11:13:12，持续显示“已暂停、累计执行 0 秒”。
- 用户认为补丁版本限制不必如此严格，指出错误未直接展示，随后明确要求一起优化并提高流程的可塑性与灵活性。

## 线上只读事实

- 工作 ID：`16d84f7e6a57475f90241e21a79462e0`；账号 ID 8；`started_at=NULL`、`work_sec=0`、无输入 action，未真正启动 Claude。
- 内容版本：`e745d4553b847e3f872c0dad496f79afac978fa7012842a49579e19ffe24a829`；冻结环境 `cerberus-py312` 的 Python 为 `3.12.15`。
- 当前 control/account 镜像批次 `v3-ci-40437814946-1`；固定 network 和 CLI 两个角色实际 Python 均为 `3.12.16`。
- 线上实际启动代码以字符串完全相等校验 Python；Pi 原始工具回执为 `status=rejected,message=离线 Python 版本与冻结环境不符`。
- 11:15、11:46、12:17、12:48、13:19、13:50 的 Pi 汇报均指向同一错误；计划仍启用，每轮结束约 30 分钟后重新请求模型。
- 最后读取时控制者 `generation=139,status=paused,message=Pi 已结束本轮指挥`，原工作 `generation=134,status=paused,message=NULL`；这说明故障记录不能只按工作旧代次等于控制者新代次才写入。
- 本轮未修改线上数据库、冻结内容、账号环境或计划，未启动真实模型。

## 代码因果链

| 位置 | 已确认行为 | 实施意义 |
| --- | --- | --- |
| `orchestrator/projects_runtime.py:340` | `_prepare_python` 在首次安装分支精确比较版本，缓存命中不探测版本 | 统一兼容判断并核对缓存真实环境 |
| `orchestrator/account_runtime.py:1532` | `prepare_scenario_python` 有另一份精确版本检查 | 旧场景不能保留矛盾规则 |
| `orchestrator/project_native_regression.py:1671` | contract 的 Python 与当前解释器字符串完全相等 | 放宽启动后也须处理验收的版本前置条件 |
| `orchestrator/project_verifier.py:50` | 已有基于 runner SHA256 的受信临时适配，不改冻结资产 | 历史回归 runner 的兼容更新复用此模式 |
| `orchestrator/project_verifier.py:485` | 独立验收使用 profile，暂存脚本只读挂载到隔离容器 | 显式精确策略同样在实际验收环境落实 |
| `orchestrator/projects.py:1732` | 工作先持久创建，随后才调用 terminal.start | 启动失败时有权威 work 可关联 |
| `orchestrator/projects.py:1630` | 工具异常仅返回 rejected/waiting，无持久启动失败事实 | 在真正启动／恢复边界记录，不把参数错误升级成故障 |
| `orchestrator/projects.py:1505` | settled 把 work 收成 paused，agent 消息改成正常轮次结束 | 持久故障优先于模型是否正常结束 |
| `orchestrator/projects.py:1362` | recover 会重写 work/agent 的普通 message | 未解决故障独立持久，重启后恢复展示 |
| `orchestrator/projects.py:1162` | 手动重试目前仅识别结构化模型错误 | 只增加已明确安全的启动故障恢复，不放开未知输入等保护 |
| `images/pi-agent/host.mjs:195` | 可信 project_submit 完成标记可结束工具循环 | 启动故障可在保存工具回执后交回调度，不能冒充目标完成 |
| `webui/projects.js:481`、`:719` | 当前状态和历史列表不读取完整启动故障 | 页面需要同一个后端故障投影 |
| `images/v3/Dockerfile:68` | account 基于 `python:3.12-slim-bookworm` | 补丁漂移是预期运行条件，不能靠回退镜像补丁来掩盖设计问题 |

## 现有验证入口

- `test_projects_agent`、`test_projects_schedule`、`test_projects_schedule_edges`：真实 SQLite、可控 Pi／终端、模型故障恢复和迟到竞争。
- `test_account_runtime`：真实离线依赖目录及缓存安装边界；`test_project_scenario_content`：环境档案校验。
- `test_project_native_regression`、`test_project_native_verifier`：冻结回归 runner、来源保护、隔离验收真实入口。
- `test_projects_pi_round` 与 `images/pi-agent/host.test.mjs`：真实 Python／Node／SDK 工具回执落盘和循环收尾。
- `deploy/v3/verify_pi_projects_browser.py`、`verify_warmup_pi_browser.py`：回环 API、SQLite、真实 Chrome、双主题及窄屏。
