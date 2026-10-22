# 账号执行与评审串行复用资源实施计划

## 开工门禁

- 用户已确认完整 Brief，已运行 `task.py start` 进入 in_progress；`trellis-route(target=implement)` 解析为 inline，`trellis-before-dev` 的规范加载已完成。
- 采用单任务、inline 执行，不创建子任务或分派子代理。当前分支 v3，基线 HEAD 为 `2d5a99051a5a95600be6d7b0f1c01777d35c91d4`。
- task.json 已记录两个仓库和 262 个既有脏文件；修改前后核验其 SHA、模式和状态，不把既有配置、研究或工作流改动纳入本修复。

## 实施顺序

1. [x] 读取相关 backend 索引和类定义；在 `resource_budget.py`、`account_runtime.py:ensure` 补充串行预算和启动前核验。现有 `account_isolation.py` 已有普通创建及旧布局 reader，保持该实现。
2. [x] 调整 `project_review_runtime.py`：非共享 CLI 租约、私有输入、持久交接、原容器停止/恢复和实际预算核验。
3. [x] 同步 `account_runtime.py` 的执行记录、ensure、claim、cleanup、wait_worker、release、reconcile 与维护恢复入口；评审采样复用原按角色分流，不改原监督器。
4. [x] 用 `ProjectReviewRuntime.pending` 查询全部活动批次，并在通用 `AccountRuntime.claim` 阻止非评审插队；复用原项目 admission 和 Scheduler 的 RuntimeBusy 重排队，不修改 `main.py` 或 `project_scenarios.py`。
5. [x] 在 `test_project_review_runtime.py`、`test_project_scenarios.py` 增加有状态恢复、预算、普通 CLI 竞争和跨批次门禁回归；原 `test_account_runtime.py` 纳入组合验证。
6. [x] 更新 `verify_project_scenarios.py`、`verify_local.py` 和测试替身：从未绑定登录创建角色，经提交后核同环境；在真实创建/恢复边界观察互斥，跨切换保留同一 API 流。替身消息改用 UUID，避免容器重启复用 PID 后出现假父链冲突。
7. [x] 按用户“修复全部”处置 FBK-001：让普通 CLI 的状态/画像检查至认领使用共同环境锁，增加检查期间评审竞争的确定性回归；保留版本安装在锁外及坏画像门禁。
8. [x] 完成定向验证并复检，复用仍有效的完整场景证据；同步受影响 spec，经用户确认精确范围后提交并推送业务代码与规范，任务记录随完成链同步。

当前有效证据见 `research/implementation-progress.md`。181项完整组合回归、30项部署回归及两组完整场景通过；FBK-001 已按用户授权修复，新增回归修复前稳定失败，修复后完整组合及F镜像真实Docker竞争/恢复验证通过。Check-All复检通过；两个既有backend规范已同步，规范diff／签名及写入边界核验通过。用户已确认精确推送计划，业务代码与规范已推送；任务完成态及Close以task.json记录为准。生产部署与真实号验收另行执行。

## 验证矩阵

| 场景 | 期望 | PRD |
| --- | --- | --- |
| 新号登录建立普通环境并保存，然后启动同环境项目 | 无旧评审布局也能完成执行、评审、落盘；无需重建 | AC3 |
| 同账号两个批次与普通 Tasks/续聊竞争 | 评审只在其他 CLI 释放后启动；新 CLI 等待；结束后继续，无饥饿 | AC1、AC5 |
| 容量1和容量2，两个不同账号 | 同账号评审互斥，候选间既有并发及不同账号运行不被全局锁阻塞 | AC1 |
| RAM1536m＋额外swap2048m及旧预留布局 | 实测三个阶段运行容器限额合计在预算内，旧 HostConfig 不变 | AC2、AC6 |
| 原普通最小预算边界与无效预算 | 常规功能维持原行为，不借 swap 冒充 RAM，不接受无限限额 | AC2、AC6 |
| 私有评审及程序验收失败 | 私有材料不可由候选读取，同实际模型，程序失败不能被 pass 覆盖 | AC4 |
| 停固定 CLI 前后、私有创建 ACK 丢失、评审停止前后、固定 CLI 恢复失败、退租失败 | 保留准确意图并按实际状态恢复；不同时运行、不伪报释放 | AC5 |
| 超时、停止、额度中断、控制服务重启及迟到旧代结果 | 不重复模型任务或验收、不多扣业务尝试，原现场及冻结结果可追溯 | AC5 |
| 切换期间已有 API/SSE | 网络和发送器身份及连接连续，固定 CLI 恢复同 ID/代次/HOME | AC6 |

## 验证命令与证据

先确认现有 `.deploy/project-iteration-repairs/venv/bin/python` 的测试依赖；缺依赖时只安装项目已固定的测试要求，不修改业务依赖版本。

```bash
PYTHONPATH=orchestrator .deploy/project-iteration-repairs/venv/bin/python -m unittest test_account_runtime test_project_review_runtime test_project_scenarios test_project_evaluation
PYTHONPATH=orchestrator .deploy/project-iteration-repairs/venv/bin/python -m unittest test_project_iterations test_project_plans
python3 -m unittest discover -s deploy/v3 -p test_manage.py
```

本地 Docker 使用本次候选同批镜像及隔离清单，按现有验证 SOP 准备后执行：

```bash
python3 deploy/v3/run_local_verification.py --manifest <本地验证清单> --project-scenarios-only --scenario-capacity 1 --scenario-failures --evidence-dir <证据目录-1>
python3 deploy/v3/run_local_verification.py --manifest <同一清单> --project-scenarios-only --scenario-capacity 2 --scenario-browser --evidence-dir <证据目录-2>
```

新登录交叉路径及独立发送连接如需补充开关，先按最终实现同步此处命令。证据须包含实际 Docker 状态和 HostConfig、顺序事件、SQLite 与私有挂载检查；`real_model_calls=0` 必须明确。既有模拟用例完成只能证明机制，真实代理/OAuth/模型闭环在后续真实账号验收中另行留证。

## 风险与回退点

- 切换与重启处理最易误唤醒固定 CLI：所有入口用同一持久记录和归属核验，不以无内存 job 推断空闲。
- 认领方式改变会触达清理及恢复两条路径：先通过失败边界回归，再跑真实 Docker 时序验证。
- 仅在评审已停净、固定 CLI 已恢复且租约已收口时回退；未知状态保持受阻，不删除记录制造成功。
- 本任务开发不触碰生产账号；提交、推送、部署及真实号验收分别遵守授权和项目 SOP。
