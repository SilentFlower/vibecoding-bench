# 实施与验证计划

## 开始条件

- [x] 读取当前代码、公开合同、旧纠错任务和线上只读证据，复现三项失败并保留分类。
- [x] 收敛为单条验收与反馈链路修复；沿用已有适配器，无新数据库、前端或调度需求。
- [x] 用户在完整 Brief 后回复“确认”，已运行 `task.py start` 并按 `trellis-route` 进入实现。

## 实施顺序

1. 按 `trellis-before-dev` 加载实施规范，复核已有定义和本任务研究；保存两个精确旧观察器样本。
2. 实现两个公开合同观察器及来源适配，和未来内容的观察器副本保持字节一致。
3. 扩展受信诊断协议与中文反馈映射，保留其它观察器原有协议行为与私有信息边界。
4. 同步两项目的公开说明、任务提示和公开示例；避免调整真实功能、范围、回归或覆盖率门槛。
5. 添加真实参考实现、合理变体、错误反例、未知摘要、非法协议、历史嵌套报告及真实入口挂载检查。
6. 在候选副本中复验三项业务与 13 条冻结公开测试，再执行相应原生历史回归；对真实失败如实分类。
7. 经 `trellis-route(target=check)` 执行适当深度的 Check-All，通过后同步规范并按完成链进入可审阅交付步骤。

## 验证命令

基础回归沿本仓库现有 unittest 入口执行：

```bash
PYTHONPATH=orchestrator .venv/bin/python -m unittest test_project_contract_observers test_project_attrs_adapter test_project_schema_adapter test_project_weighted_adapter test_project_arrow_adapter test_projects_verification_recovery test_project_native_verifier test_projects_verification_history
```

- 两个新增观察器的来源、协议、参考实现、合理变体和反例在 `test_project_contract_observers.py` 合并验证，避免复制相同适配器测试脚手架。
- 测试按依赖合并执行可减少启动开销；无需为此次无前端改动重复浏览器验证。
- 三个线上候选的只读副本位于 `/tmp/vibebench-deferred-audit-vgew_i65`；研究记录包含 immutable submission ID、环境摘要和已有离线命令形状。使用 Python 3.12.15、核对过的离线轮子、无网络及只读候选挂载，单独保存各阶段结果。
- 业务通过、公开测试通过、原生回归通过和未执行的线上语义验收分别报告，禁止互相替代。

## 已有验证证据

- 上述定向回归 115 项全部通过；新模块单独执行 6 个测试方法，包含多个合理实现、错误实现及协议子场景。
- 通过真实 `ProjectVerifier.verify_native` 入口，在禁网隔离容器执行三个原候选的业务检查与冻结原生回归，三个业务结果均为通过且诊断为空。
- 原生回归：attrs 1,401 通过，bibtexparser 2,819 通过，babel 7,989 通过；合计 12,209 通过、0 失败、0 错误，既有跳过与预期失败按原合同保留。
- 有界证据副本：`research/validation.json`。完整容器报告：`/tmp/vibebench-deferred-audit-vgew_i65/native-results.json`。
- 线上语义验收及线上通过状态没有在本地改写；生产切换和恢复仍按发布流程接续。

## 风险与恢复点

- 观察器来源或修正摘要不符：停止该适配，不改写旧脚本、合同或报告。
- 新观察器拒绝原参考实现：回到具体公开合同定位误差，不能只让线上候选通过。
- 负向实现被放行或反馈含私有内容：阻断交付，修正对应矩阵/协议后定向复验。
- 本地回归暴露当前任务范围外的真实业务缺陷：保留证据，按 Brief 增量规则处理，不为凑通过率静默改候选或扩大范围。
- 生产发布及原目标重新提交需按项目发布流程核对当前在途工作和授权，本计划不提前写入线上状态。
