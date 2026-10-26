# 研究依据与范围

用户已确认同时优化三项：宿主等待合并、模型增量视图、验收合同与具体反馈。完整线上核查证据在本地 `.deploy/pi-request-usage-audit-20261026/`；该目录不作为必须提交的私有数据。

已核查主要定义：ProjectsService.tool/_observe/_input、PiTerminal.observe、ProjectsPi.run、Pi host 的 callTool/runSession/摘要边界、ProjectsVerification.__call__/_public_facts、ProjectVerifier.verify_native 及 schema/weighted 精确适配。API 的 ProjectsAgentIn/ProjectsScheduleIn 与 snapshot/events 为现有管理协议，本轮不改其形状。

关键源码锚点：`orchestrator/projects.py:115` 工具定义；`:1588` 工具入口；`:1831` 观察等待；`orchestrator/pi_terminal.py:283` 原始采样；`images/pi-agent/host.mjs:194` 模型工具回执；`orchestrator/project_verifier.py:405` 验收入口；`orchestrator/projects_verification.py:104` 交付检查；`project_library/projects/attrs/verification/AT-VALIDATION-REPORT-DEV-observe.py:28` 未公开类型要求。

样本统计：Pi 355 次已知用量调用，Claude 46 次；341 次观察/316 次无原生文本，315 次运行期间仅屏幕改变，间隔中位数 2.009 秒。6 条原公开回归通过，原冻结观察器仍 business=false；直接诊断为 raise_errors=1 抛 MultiValidationError 而非未公布的 TypeError。

原始终端和会话正文不放入研究夹具。observation-trace.json 只保留记录时点、屏幕摘要/字节数、原生事件数及运行标志，可验证记录时点上的等待合并；它不能证明记录间所有连续变化或模拟未来模型决策。实际文本增量大小另用可审查的合成画面验证。

规划回放见 planning-replay.json：341 条记录保留 39 次返回，观察返回下降 88.56%，保留回执在尚未做文本增量时由 1,289,513 字节变为 179,813 字节。若其他十四次模型调用保持不变，总调用估计为 53 次。此计算未执行待实现产品代码，也不包含连续采样或模型决策改变，不能作为已经达到验收标准的证据。

参考已有任务 `.trellis/tasks/10-26-verification-feedback-contamination/` 的设计与需求：旧冻结合同通过精确运行时适配修正，不能原地改写；失败事实白名单化；三次失败/deferred 的收口与冷却保护复用。旧任务曾有单次部署授权，不扩展到本轮。

当前四项 Trellis/Flower 工作区修改已由 task_intent 保存基线，本轮保持隔离。
