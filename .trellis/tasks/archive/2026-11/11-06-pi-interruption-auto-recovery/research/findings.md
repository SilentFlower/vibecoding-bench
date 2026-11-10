# 已核实事实与代码位置

## 用户目标

用户已确认：程序自行中断应先自动对账与恢复；临时失败持续时冷却；仅明确需要人做的事项才提示人工。用户最后指令为“修复他”。本任务仍处于首次实施前规划评审，尚未修改产品代码或生产运行状态。

## 本会话线上只读证据

- 数据库中的账号 `10-23` 为 ID 8，空间为 projects。
- 当前工作：`79ce7f8e88e941bea99e418c26dcaca8`；`python-frontmatter / FM-FX-01-DEV`。
- 当前控制状态与计划均为 blocked，计划开启但下一次执行时间为空。检查时没有活跃 runtime，两个动作均为 sent。
- 原错误事件：51015，北京时间 `2026-11-06 02:22:42.632155+08:00`，公开消息为“Pi 模型请求失败，请检查模型的流式响应及工具调用兼容性”，未保存 reason。
- 原 Pi 会话最后助手：`2026-11-05T18:22:42.609Z`，模型 `gemini-3-flash-agent`，`stopReason=error`，`errorMessage=Stream ended without finish_reason`。
- 会话大小为 87,328,750 字节。最终成功读取的是原文件尾部 16 KiB 的完整 JSONL 记录；全文件或大范围事件回扫成本较高，未来诊断应有界。
- 连接参数与凭据不记录到任务材料。排查未发送模型请求，未改写生产库，未启动／暂停目标。

## 关键代码

- `images/pi-agent/host.mjs`：`unavailable`、`recoverFailure`、摘要 `summaryStream`、最终错误事件、输入管道 `receive`。
- `images/pi-agent/recovery-policy.test.mjs`：直接执行实际分类器的 HTTP 全状态及传输错误回归。
- `images/pi-agent/host.test.mjs`：实际 SDK、回环 SSE、已确认工具历史、服务端等待、过滤与模型降级场景。
- `orchestrator/projects_pi.py`：`ProjectsPi.run` 的 JSONL 读取、EOF、工具回调、停止与超时。
- `orchestrator/projects.py`：`_model_recovery`、`_finish_model_recovery`、`_manual_retry_event`、`start`、`recover`、`_run`、`_pi_event`。
- `webui/projects.js`：计划倒计时、运行概览、恢复事件说明及页面代次；已有 SSE 与时钟可复用。
- `orchestrator/projects_warmup.py`：本文件负责旧养号配置迁移；工程养号的执行策略由共享项目服务负责，不能误改旧配置迁移逻辑来解决模型断流。

## 规范与约束

- 项目迭代契约：同一目标连续会话、工具结果持久化、安全收口、双空间隔离、当前模型顺序与上下文摘要、绑定原错误的旧诊断。
- 数据库契约：参数化 SQL、事务写入、身份及投递对账、暂停／停止优先、恢复不清空原事实。
- 前端契约：直接渲染服务端状态、既有 SSE 生命周期、转义输出、账号／空间旧响应失效、资源版本同步。
- 先使用现有恢复机制，新增内容保持在已确认故障和安全执行边界，不引入通用调度框架。
