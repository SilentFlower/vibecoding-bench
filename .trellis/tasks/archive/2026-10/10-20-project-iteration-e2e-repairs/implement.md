# 实施与验证计划

## 开工条件

- [x] 已创建planning任务并记录原dirty基线。
- [x] 已核对五项缺陷、原始证据及项目接口／字段／方法定义。
- [x] 无待决产品问题，PRD与设计已收敛。
- [x] 已完整展示Brief，用户回复“修复”确认开工。
- [x] 已start为in_progress，trellis-route恢复inline个人默认，由主会话实施。

## 顺序

1. 为决定发布权限、相同决定重复发布、open/fstat替换、非法链接／过大文件、终态停止竞争、局部blocked保留及兄弟继续建立有意义的失败回归。优先扩展 `orchestrator/test_project_plans.py`、`test_project_iterations.py`、`test_main.py` 现有夹具。
2. 修改 `orchestrator/project_library.py`、`project_plans.py` 和 `images/account/project_plan.py`，实现原子权限发布、幂等决定和有界重读。
3. 修改 `orchestrator/main.py` 的共享停止与内部项目适配、`project_iteration.py` 的停止调用、`project_plans.py` 的局部故障收口，保留释放证明和终态语义。
4. 修改 `webui/app.js`、`index.html`、`style.css`，完成终态调度文案及运行时段表单修复；不为纯样式编写镜像实现的单元测试，以浏览器实测验证。
5. 扩展 `deploy/v3/verify_project_scheduling.py`、`verify_project_browser.py`及现有时段浏览器路径，覆盖受影响的真实链路；在 `run_local_verification.py`／`verify_local.py` 增加opt-in规模分支和单独有界截止，规模主体可置于新的 `verify_project_catalog.py`。
6. 本地构建本轮control/account验证镜像并记录源码及镜像摘要；运行下方分层验证。短链路通过后按用户最新要求观察规模运行并及时停止，不再等待完整100×20。
7. 经trellis-route进入check，完成Check-All；按其收尾规则再同步规范与任务进度。提交／推送由trellis-push另行处理，生产发布不在本任务中。

## 验证命令与场景

测试依赖使用隔离Python环境，沿 `orchestrator/requirements.txt`、`requirements-test.txt`；不改依赖版本。

```bash
PYTHONPATH=orchestrator python3 -m unittest test_project_plans test_project_iterations test_main test_run_windows test_run_window_scheduling test_warmup_quota
node --check webui/app.js
git diff --check
python3 deploy/v3/run_local_verification.py --manifest <本轮验证镜像清单> --project-scheduling-only
python3 deploy/v3/run_local_verification.py --manifest <本轮验证镜像清单> --project-iterations-only
```

新增规模参数及浏览器入口以实施时实际 `--help` 和源码为准；新增接口属于测试工具，不改变产品API。

| 场景 | 路径 | 可观察期望 |
| --- | --- | --- |
| F1 原子发布 | 同步屏障＋真实UID1000读取 | replace后的文件立即可读、完整，重复相同决定不换inode |
| F2 读取替换 | 实际driver模块＋open/fstat间replace | 合法替换有限恢复，链接／超限／持续竞争失败，fd不泄漏 |
| F3 终态停止 | 实际SQLite、停止入口、故障与清理竞争 | 旧终态不覆写，幂等不伪造释放，错误原因保留 |
| F4 局部失败 | 两CLI真实Docker、定向故障 | 一项目blocked后兄弟与后续健康项目继续，严格清理失败仍阻断 |
| F5 状态展示 | 真实浏览器＋API／DB状态对照 | 七种批次状态准确，终态隐藏下一投放，SSE保持展开与滚动 |
| F6 时段表单 | 1280／390px、明暗、键盘与保存回读 | 启用／星期同行，关闭禁用且保留配置，启用后恢复且服务端校验有效 |
| F7 单批规模观察 | 本地随机部署、真实Scheduler／driver／验证器 | 按用户最新要求记录当次已观察项目与接受步数、重复接受及实际并发，保留未完成全库和逐项目原生审计边界；完整100×20为后续opt-in，不阻塞本轮 |
| F8 清理 | 精确部署标签、PID／挂载归属核对 | 只删本轮临时资源；证据与原生产展示保留，真实模型请求0 |

## 证据与回退

- 每层保存实际命令、返回码、镜像／源码摘要和结果；报告入口写入 `research/verification.md`，较大运行证据保存在gitignored专用目录。
- 规模观察保持生产默认10秒稳定等待，按用户要求保留部分覆盖；不能把原1秒环境或未完成全库当作本轮全量通过。
- 若发现新故障，先保留失败现场并定位；不得重置状态或拼接批次凑通过。范围内修复同步规划材料后继续，新增产品决策才暂停受影响部分。
- 回退只针对本任务新增diff；任务基线中的其他文件及生产资源不回滚。
