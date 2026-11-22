# 实施计划

## 启动门槛

- [x] 三件套收敛并派生完整 Brief，取得有效人工授权或后台领取与 started 回执。
- [x] `task.py start` 成功，进入 `trellis-route`，按 `trellis-before-dev` 载入实施上下文。
- [x] 核对冻结提交、分支重名、工作区归属及最新远端；保存恢复点。

## 顺序

1. [x] 从 `92ea67e805c4b25b1feba0fd435aadbb9d3c39fe` 创建 `merge/agy-flower2api-refresh`，合并 `48f6029e19bebfa89a541d3703801f6c861678c0` 并保留待评审状态。
2. [x] 读取冲突周边类型与实际接口，整合启动/退出及发行测试导入，按完整场景同步两份合同。
3. [x] 逐项审查共同改动及发布定义来源，必要时补充针对行为缺口的回归。
4. [x] 核对冻结定义与注册项，执行聚焦回归，再完成受影响层的验证。记录源码摘要、命令、退出码、通过/跳过数及证据路径。
5. [ ] 完成差异说明和 pre-check 状态，进入 Check-All。依流程处理检查结果，随后进行 Spec 评估和精确 Git 计划。

## 验证计划

- Python 入口：`/root/project/vibecoding-bench/.venv/bin/python`，按模块设置 `PYTHONPATH=services/orchestrator:deploy/flower2api`。
- 定义：`python3 deploy/flower2api/verify_database_definitions.py`，另比对冻结步骤 1–4 的注册与源摘要。
- 部署：上述 Python 执行 `-m unittest discover -s deploy/flower2api`。
- 编排：先通过 `rg --files services/orchestrator` 确定当前同步、迁移、更新、AGY 维护/认证/诊断测试的真实文件与入口。执行受影响模块集；共用生命周期变更影响全局时使用既有 4 批 helper 执行完整编排集合。
- 网关：`cargo fmt --check --manifest-path services/gateway/Cargo.toml`；`cargo test --locked --manifest-path services/gateway/Cargo.toml`。
- 前端：`npm --prefix apps/web run build`。
- 浏览器：按实际改动执行 `verify_cluster_ui.py`、`verify_environment_ui.py`、`verify_cluster_request_ui.py`。AGY 请求记录与模型夹具按实际源码变化及本地镜像条件选择既有探针，完整保留执行证据。
- 数据演练：bench4→5、gateway4→6、重复 apply 与旧版兼容读写。与旧任务源摘要一致的证据可以引用，发生变化的部分重新验证。
- 新证据写入本任务 `research/` 或独立 `.trellis/.runtime/agy-cluster-refresh/`。

## 恢复与评审

- 分支与合并失败先检查实际状态，再按设计恢复点处理，保护任务材料和其他工作。
- 新范围或风险决定先同步三件套，按 Brief 增量规则处理。
- 真实凭据、付费模型、生产部署、正式发行属于独立边界。
- 最终记录验证限制和风险，由 Check-All 与 Push owner 执行后续门槛。
