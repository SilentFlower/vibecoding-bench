# 实施计划

## 开工与上下文

- [x] 展示最终 Brief 并取得首次实施确认，随后运行 `task.py start`。
- [x] 通过 `trellis-route(target=implement)` 确定执行方式；本次为内联，未派遣子代理。
- [x] 读取 `trellis-before-dev` 要求的后端规范、相关类／测试和 Phase 2.1 细节；保留本轮开始前的 9 项脏文件和其它任务。

## 实现顺序

1. [x] 先补隔离复现：真实 `/proc` 退出竞争、未知 PID、真实重复模式切换；区分已证实问题和历史假设。
2. [x] 为网络切换和 Pi 终端启动增加绑定尝试的私有诊断，保存原错误与清理错误的独立事实，验证权限、大小和敏感字段边界。
3. [x] 修复已确认的 ESRCH 漏接和 CA 错误被 socket 重试吞掉，保持 PID／代次／角色核对及定向清理。
4. [x] 为当前原工作增加严格的人工恢复准入，复用原启动事务和审计，不改变自动调度的未知执行门禁。
5. [x] 补充两空间回归并通过适用 Check-All；按 `trellis-update-spec` 记录可执行合同，然后进入 `trellis-push` 的精确范围计划与确认。

## 验证命令与重点

```bash
PYTHONPATH=orchestrator .venv/bin/python -m unittest discover -s images/account -p test_network_context.py
PYTHONPATH=orchestrator .venv/bin/python -m unittest discover -s orchestrator -p test_capture_settings_runtime.py
PYTHONPATH=orchestrator .venv/bin/python -m unittest discover -s orchestrator -p test_projects_runtime_resilience.py
PYTHONPATH=orchestrator .venv/bin/python -m unittest discover -s orchestrator -p test_runtime_diagnostics.py
PYTHONPATH=orchestrator .venv/bin/python -m unittest discover -s orchestrator -p test_startup_recovery.py
PYTHONPATH=orchestrator .venv/bin/python -m unittest discover -s orchestrator -p test_account_runtime.py
PYTHONPATH=orchestrator .venv/bin/python -m unittest discover -s orchestrator -p test_projects_agent.py
.venv/bin/python deploy/v3/verify_network_context.py --image ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1 --cycles 3
git diff --check
```

- 覆盖首次失败和 cleanup 再次失败、私有证据关联／原子性／拒绝链接、异常中含合成 token 与代理密码、诊断写入故障及原公开失败合同。
- 覆盖人工准入正例和全部拒绝条件：自动扫描、已有输入／会话／运行时、曾经启动、未知收口、角色或账号身份变化、冻结合同变化、旧代次及并发启动；拒绝保留原阻塞与故障。
- 复用真实进程测试；另以随机标签的隔离账号容器运行真实 `v3-network-context` 的重复透传／抓包切换，仅使用合成上下游和空数据，不挂生产目录、不发模型请求。按新增验证入口的实际参数记录命令和结果，不以模拟网络配置宣称完整链路通过。
- 检查范围以实现实际影响确定；通过后不无故重复整套构建或测试。

## 线上交付与恢复

1. [x] 确认所需提交／推送与部署计划已得到对应授权，使用 v3 Action 构建、发布同批 control/account，核对两件成功、提交和清单；不混入其它任务的未提交内容。业务提交为 `a32b2854`，联合发布为 `ci-41034190954-1`。
2. [x] 只读复核当前 `us` 目标、资源参数、身份、API／CLI／控制者／未知输入和原故障。按既有 SOP 交付，不备份、不重新计算内存，不修改已保存资源配额。
3. [x] 完成健康验收和旧镜像定向回收，复核保留批次、原数据和服务健康。本次候选为 0，保留当前与两个完整历史批次、全部容器引用，25 个容器及部署配置复核通过。
4. [x] 原工作已通过现有正常人工启动入口恢复一次；核对原会话、工作区、设置、实际启动证明、`resolved_at`／`runtime_recovered` 和可信原生响应，恢复控制代次为 31、环境代次为 8。该正常入口请求由既有管理入口发出，本轮接续验收，未额外调用 start 或重复输入。
5. [x] 本次原目标恢复成功，任务证据和验证结果已更新；后续启动再次失败时继续保留故障并读取私有诊断，不盲目重复调用模型。历史原始异常缺失的限制继续保留。

## 回退与停止条件

- 变更文件集中于网络切换、账号／Pi／Projects 运行边界、相应测试和必要规范；`runtime_files.py` 仅搬移既有安全文件函数，`runtime_diagnostics.py` 仅服务本次失败边界，`verify_network_context.py` 为禁网容器验证入口，不建设通用框架。
- 生产对象／代次变化、原执行未知、身份或合同不符、镜像／清单不一致、健康失败时停止对应交付或恢复，不扩大操作范围。
- 采用项目已有兼容批次回退流程，保留最新 HOME、工作区、会话、成果与凭据；不恢复旧数据库或 RT。
