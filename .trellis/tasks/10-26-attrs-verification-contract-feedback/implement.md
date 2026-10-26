# attrs 验收实施计划

## 前置与顺序

先完成观察效率子任务并保存其验证证据，再在相同联合批准范围内激活本子任务。代码变更依赖现有共享 ProjectsService/ProjectVerifier，而不依赖新的数据库结构。按 trellis-route 和 trellis-before-dev inline 执行。

## 实施步骤

- [x] 核对公开 prompt、材料、私有观察器及冻结候选；将精确旧观察器保存为测试夹具并记录摘要。
- [x] 为未来内容修正 attrs 业务矩阵，去除未公布的 raise_errors=1/TypeError 假设；增强原公开功能的独立检查和枚举诊断。
- [x] 在 ProjectVerifier 复用精确版本适配与可信暂存入口，支持旧冻结目标；结果比较保持严格，仅识别白名单诊断。
- [x] 在 ProjectsVerification 增加公开行为反馈映射及泄漏/体积限制回归。
- [x] 跑本地精确候选、公开六项与真实错误反例；验证业务通过后仍进入原生、历史及语义检查。
- [x] 跑原 schema/weighted/Arrow 适配器和双空间 deferred/历史回归，记录旧资产字节未改写的证据。
- [x] 更新项目迭代验收契约及必要文档，定向验证证据保存后返回父任务，统一进入联合 Check-All。

## 适用验证

```bash
PYTHONPATH=orchestrator python3 -m unittest test_project_native_verifier test_project_schema_adapter test_project_weighted_adapter test_project_arrow_adapter test_projects_verification_history test_projects_verification_recovery
```

新增精确适配/反馈矩阵拟放入 `orchestrator/test_project_attrs_adapter.py`，需增加真实隔离候选或适当替身的正反例，而非只验证字符串替换。业务候选复现使用已封存源码，在本地无供应商凭据的环境执行，不在生产宿主加载候选代码。

## 回退点

改动限于 attrs 当前内容、适配及安全反馈和必要测试/规范；冻结旧资产不动。保留原失败报告，回退代码恢复原验证行为，不迁移数据库，不自动把目标转 passed 或解除冷却。与前一子任务的观察视图组合后再做父任务集成审查。

## 联合交付证据

本子任务在父任务完成统一 full Check-All，定向与集成证据见 `../10-26-pi-efficiency-feedback/research/validation.md`。规范已同步；Git 交付与 completed/Close 尚待联合提交计划确认。
