# 实施计划

## 开工门禁

- [x] 明确用户要求为永久代码修复，11-5 线上恢复已独立完成。
- [x] 检查现有类、账号字段、角色创建、登录绑定、维护租约及测试入口。
- [x] 完成 PRD 收敛、技术方案与验证计划。
- [x] 完整展示 `brief.md`，用户在当前会话明确回复“确认”。
- [x] 运行 `task.py start`，通过 `trellis-route(target=implement)` 选定 inline 并开始实现。

## 实施顺序

1. 在运行时现有回归中增加原故障用例；使用真实形状 Docker Mounts 和草稿绑定链，先证明旧版复用会遗漏挂载。
2. 增加最小挂载核验和空闲补齐分支；复用现有角色归属、维护认领、重建及创建流程，确保使用新代次对象。
3. 补充保护与失败用例：正确挂载幂等、其他账号／错误可写挂载拒绝、API active／waiting、CLI／评审、遗留登记、并发及部分重建失败。
   - 独立 API 固定使用 `require_quota_mount=False`，核验“已持有自身并发许可时不因 CLI 额度文件缺失被反向阻断”；其他准备沿默认 true。
4. 扩展 `deploy/v3/verify_login_drafts.py` 的实际提交后场景，验证本账号只读额度文件、其他账号隔离及 Recorder 不产生缺文件暂停。
5. 运行下列聚焦检查，保存命令和真实结果；进入 `trellis-route(target=check)` 按 Check-All 所选深度复核。
6. 按流程执行 Spec 评估，记录正式账号首次准备的挂载／空闲补齐合同；仅展示本任务提交计划，Git 写入仍依对应确认门禁。

## 验证命令

默认使用项目已有 Python 虚拟环境；执行前确认所选解释器安装了 `orchestrator/requirements.txt` 与 `requirements-test.txt`。若依赖缺失，仅在本地隔离环境安装。

```bash
PYTHONPATH=orchestrator python3 -m unittest test_account_runtime test_login_drafts
PYTHONPATH=images/sidecar python3 -m unittest discover -s images/sidecar -p test_recorder.py
git diff --check
python3 deploy/v3/verify_stack.py --manifest .deploy/v3-ownership-implementation/release-a6.json --source-overlay --browser --reauth
```

最后一条命令使用已存在的本地 dirty 清单及其同批镜像，不发布制品。若实现需要触及 account 镜像内文件，先联合构建新的唯一标签本地清单，再以该清单执行，不冒充仅覆盖 control 的源码验证。

## 证据与对应验收

| 证据 | 对应验收 |
| --- | --- |
| 原故障回归与正式准备后的只读挂载 | AC1、AC2 |
| 维护拒绝、错误挂载、并发和失败收口用例 | AC3、AC4 |
| 原身份／HOME／凭据／工作区摘要及草稿恢复回归 | AC5 |
| 随机部署内真实容器读取及 Recorder 观察结果 | AC1、AC4、AC6 |

## 实施与回退边界

- 本任务只修改上述运行时、回归和相应权威规范，不合入已有无关脏文件。
- 不操作线上账号、不重复恢复 11-5，不自动发布或部署镜像。
- 维护结果未知即停止后续创建，保留原对账状态；不能通过清除执行记录、关闭额度门禁或扩大挂载范围让测试通过。
- 本地演练按随机部署精确标签清理，只删除本次合成数据；不得 prune 或清理其他工作资源。
