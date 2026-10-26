# 联合优化验证记录

## 观察与模型视图

- Python：`PYTHONPATH=orchestrator .venv/bin/python -m unittest test_projects_observation test_pi_interaction test_projects_agent test_projects_terminal test_projects_feed test_projects_store test_projects_single_objective test_projects_schedule_edges test_projects_pi_round test_projects_cycles test_projects_engine_cycles test_projects_quota test_projects_catalog`。最终 133 项通过，日志 `/tmp/pi-efficiency-python-final.log`；新增编号菜单及通知命名空间用例包含在最终重验。
- Pi SDK：原宿主与新增视图回归首次完整运行 50 项通过，日志 `/tmp/pi-efficiency-node-tests.log`。新增真实 SDK 模型视图/本地等待计量用例独立执行，最终独立 1 项通过，日志 `/tmp/pi-efficiency-sdk-view-final.log`；与此前 50 项合计 51 个独立用例，未重跑未变化的完整宿主套件。
- 固定 CLI 2.1.293 对接回环合成上游，真实 Stop 钩子写出来源/会话匹配的通知，外部模型请求 0。见 `native-cli-hook-probe.json`；提问与授权通知另有真实通知子进程、原生 JSONL 和命名空间回归。
- 最终实际策略对原始时间和画面的离线回放见 `implementation-replay.json`：341 次观察合并为 52 次；其他十四次调用保持不变时估计总请求 66 次；按 UTF-8 紧凑 JSON 比较，模型载荷由 1,307,245 降至 192,155 字节，减少 85.30%。该证据只证明记录时点的本地策略及观察载荷变化，不模拟未来模型决策或真实扣费。原始正文留在 `.deploy/pi-request-usage-audit-20261026/`，任务研究只保存摘要。

## 验收与冻结兼容

- `PYTHONPATH=orchestrator .venv/bin/python -m unittest test_project_attrs_adapter test_project_native_verifier test_project_schema_adapter test_project_weighted_adapter test_project_arrow_adapter test_projects_verification_history test_projects_verification_recovery`：109 项通过，日志 `/tmp/pi-efficiency-verification-tests.log`。
- 精确线上候选实现用实际 ProjectVerifier、现有本地 v3 账号镜像和离线 Python 3.12 环境执行；旧冻结脚本经适配业务通过，原生回归 1401 passed、10 skipped、1 xfailed，冻结集合/预期一致；原公开六条回归夹具通过。见 `native-program-verification.json`。这些测试没有调用语义审查供应商，也没有给生产目标写入通过记录。
- 首次 Docker 验证因本地夹具路径不在模拟数据根下返回环境错误，未进入业务验证；修正夹具目录后完整重验通过，旧失败证据保存在 `.deploy/pi-request-usage-audit-20261026/native-program-verification-attempt-1.json`。
- `.venv/bin/python -m unittest discover -s deploy/v3 -p test_manage.py` 31 项通过，日志 `/tmp/pi-efficiency-manage-tests.log`；其中备份与恢复均为测试临时目录，与生产无关。

## 最终检查

- 联合 full Check-All 已通过，三个维度均通过，CHK/FBK/DOC 均为零；324 个独立自动化回归用例通过，另有实际 Docker 原生/公开回归、固定 CLI 钩子和最终策略回放证据。Python/Node 语法、分发路径及 git diff --check 通过。规范同步结果为 written，仅更新 .trellis/spec/vibecoding-bench/backend/project-iterations.md，并复读差异、反查实现和通过规范差异检查。
- 本次没有生产发布、任务恢复、额度探测、账号身份或资源配置变更。

Git 交付与 completed/Close 尚待精确计划确认；不将本地实现完成等同于已提交、上线或生产目标通过。发布后由发布流程核对两空间真实交互延迟及用量，本轮不执行该操作。
