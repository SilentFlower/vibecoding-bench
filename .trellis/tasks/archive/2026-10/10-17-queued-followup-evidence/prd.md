# 修复原生队列附件的补充完成漏判

## 目标

让通过 Claude Code 原生 queued_command 附件接收的业务补充得到正确的消费与完成判定，避免已经处理完毕的任务继续等待并误记为超时。

## 背景与证据

- 用户核对实际处理情况后明确要求修复。线上 8bd1831f4dce 已入队并经原生附件交给 Claude，关联实现记录和正常最终回复存在，但阶段仍 queued，终态 timeout。脱敏证据见 research/native-queue.md。
- P1 / R1：images/worker/task_followups.py:176 公共解析器只提取普通 user/assistant 与可选 enqueue，遗漏附件消费；:403 定时阶段机拿不到 input_entry，:525 的最终回复判定因而无法完成。images/worker/entrypoint.sh:1900 在收尾后把未完成补充记为 timeout。
- R2：deploy/v3/fixtures/mock_cli.py:42 的忙碌消费生成普通 user；orchestrator/test_topic_followups.py:513 同样仅覆盖这种形式，缺少真实原生格式。

## 需求

- R1：有效主会话 queued_command 附件可确认补充消费；仅关联的正常最终回复满足稳定窗口后才能完成。支持一条/两条补充及共享回复。
- R2：兼容原普通 user、时间策略 1/2 和旧阶段规则。单独 enqueue、remove、工具正文、渲染引用、异会话、旁支、元记录、错误来源/正文和无关回复不得误认完成。
- R3：保留冻结正文、次数、时间、时钟、状态版本及原字节证据。不重抽、不重发；原 queued 状态可从原日志补认有效附件及回复。
- R4：正式 driver/tmux、管理进度 API 和双镜像验证修复；沿用既有 v3 交付、自然空闲切换及不新增服务器备份约束，不用真实账号模型探测。

## 验收标准

- A1 / R1：enqueue → remove → queued_command → 关联最终回复从当前 wait/queued 转 complete；仅附件而无最终回复为 consumed。
- A2 / R1、R2：一条/两条原生补充、普通 user 与附件混合、乱序落盘、两条共享回复均有断言；无关父链及非正常回复不能成功。
- A3 / R2、R3：仅入队/移除、文本引用、错误来源/会话/正文、重复或丢失证据、截断日志保持保守状态或明确拒绝，不重发、不改冻结计划。
- A4 / R3：原阶段 schema 1/2 及时间 schema 1/2 兼容；原 queued 状态凭有效附件和回复恢复，无有效消费仍拒绝恢复。
- A5 / R4：正式 driver/tmux 忙碌原生附件场景以 0 退出，管理 API 显示消费和完成；停止、认证、额度、收尾和错误路径回归通过。

## 范围边界

不改 topic、10%/45%/45% 概率、5%～30% 时间窗口或输入方式；不自动改历史线上终态或补发需求；不操作 cc2api 子仓及 55 项无关变更。
