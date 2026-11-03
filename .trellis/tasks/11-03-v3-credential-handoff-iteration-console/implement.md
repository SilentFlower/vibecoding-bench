# 父任务整合计划

## 顺序

1. [x] 完成两个子任务的规划与 Brief 评审，从子任务 A 进入实施，父任务保持统筹角色。
2. [x] A 独立完成代码、故障验证、Check-All、Spec 同步及精确范围提交/推送。
3. [x] B 保留 A 的页面改动，独立完成导航、浏览器验证、Check-All、Spec 同步及提交/推送。
4. [x] 复用各自验证证据，仅补跑父任务 PA3 的交叉场景以及最终改动引入的必要回归。
5. [x] 核对父仓库/子模块提交、同批镜像、所有权能力兼容与部署操作单，再按现有 v3 SOP 更新 US。
6. [x] 记录发布健康、页面直达、凭据状态、原数据保留及已知真实 OAuth 验证边界，完成 PA1–PA4 与任务 Close。

## 交付检查

- 两个子任务完成标准及证据均可追溯，不用父任务的“完成”代替子任务验收。
- 只提交本任务树与实际业务改动；工作区原有协议研究/旧任务文件保留，不纳入本轮。
- 当前用户已授权常规提交、推送及部署；发布时沿用该范围，并遵守真实工作空闲和协议兼容要求。
- 两个子任务已按确认范围实施并提交；父任务执行联合验证和部署，继续保留不做生产账号操作、备份、资源重算或清理的边界。

## 联合验证命令

`PYTHONUNBUFFERED=1 PATH="$PWD/.deploy/v3-ownership-implementation/bin:$PATH" .venv/bin/python .trellis/tasks/11-03-v3-credential-handoff-iteration-console/research/joint_verify.py --manifest .deploy/v3-ownership-implementation/release-a6.json --source-overlay --browser --ownership` 已退出0。原合成账号启用仅供页面选择，验证后恢复原夹具停用状态；真实关联重授权维护与取消先运行，再复用完整交接流程。
