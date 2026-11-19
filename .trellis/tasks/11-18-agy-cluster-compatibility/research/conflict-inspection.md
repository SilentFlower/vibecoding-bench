# AGY 与 Flower2API 集群版本合并检查

- 目标：`origin/flower2api`，`0764b5fa75e0df6c5c12969fdc40b53d3bbf734c`。
- 来源：`feat/agy-account-runtime`，`ca198ee979ec968bcd7d1a2063c872edb05850f7`。
- 共同基线：`6d4253a29f7a0ee6bbadc0809d5acb570b14781f`。
- 已完成远端刷新。`feat/manual-node-cluster` 已包含于目标。
- 两侧分别变更 859 / 207 个路径，共同修改 37 个路径。
- `git merge-tree --write-tree --name-only` 返回 1，冲突涉及 20 个文件。
- 模拟树：`7d8f6bf539d198be1c8bc384de2b256ec43ab541`。

## 关键发现

1. **编排数据库版本碰撞**：AGY 登记 `bench.agy-environments.2`；集群版登记 `bench.cluster.2`、`bench.node-executions.3`、`bench.node-login-drafts.4`。两种版本 2 的身份和摘要不同。使用两侧实际执行器分别构造内存库，再读对侧迁移登记，两次均报“数据库迁移台账版本或摘要与当前程序不符”。证据见 `ledger-probe.json`。
2. **迁移来源表覆盖**：模拟树 `deploy/flower2api/system_release.py` 第 24、38 行分别赋值 `BENCH_SCHEMA_SOURCES`，后一次只保留 AGY 步骤。这两处赋值本身没有冲突标记。只处理文本冲突仍会丢失集群来源登记。
3. **环境维护合同**：`main.py` 同一维护调用位置，一侧增加远程 Node 分发，另一侧增加 `expected_generation`。需要同时保留节点归属和环境代次检查。启动退出收口也需要同时保留集群迁移操作关闭与 AGY 清理任务取消。
4. **诊断及界面字段**：集群版加入 `execution_location` 和节点信息；AGY 加入 `context`、平台、凭据代次和工具轮等信息。应合并这些独立字段并更新所有 Rust 结构构造处及 Vue 展示。
5. **发行及构建合同**：集群版平台版本改为运行时读取，AGY 分支仍带前端构建版本参数；合并时保留运行时版本方式并接入 AGY 认证制品摘要。升级器源码清单需同时包含集群备份与 AGY 认证模块。

## 集成边界

- 以最新 Flower2API 集群实现为基线，保留已发布迁移 1—4 的身份和摘要。AGY 增量步骤需要安排在其后。
- 若已有 AGY 分支版本 2 的持久数据库，需要制定并验证台账分叉的兼容处理；仅重新编号不足以支持这类数据库。
- 合并结果仍按现有 AGY 独立 API 环境走中央本机 Docker。AGY 入口在集群任务账号路由之前按平台分流；节点分配按工程账号 ID 工作。现有集群转发白名单只覆盖已有 CC 协议。将 AGY 分配至远程节点属于额外功能范围。
- 原 `/root/project/vibecoding-bench` 的 `flower2api` 工作区有 323 项本地状态条目，其分支落后远端。后续集成应选择干净工作区。

## 文本冲突文件

- `.trellis/spec/orchestrator/backend/account-runtime-v3.md`
- `.trellis/spec/platform/deploy/platform-online-update.md`
- `apps/web/src/api.ts`
- `apps/web/src/components/RequestDiagnostics.vue`
- `apps/web/src/components/RuntimeEnvironments.vue`
- `apps/web/src/components/runtime/runtimeApi.ts`
- `deploy/flower2api/install_system_updater.py`
- `deploy/flower2api/manage.py`
- `deploy/flower2api/system_release.py`
- `deploy/flower2api/test_database_definitions.py`
- `deploy/flower2api/test_manage.py`
- `deploy/flower2api/verify_database_definitions.py`
- `services/gateway/src/model/request_diagnostics.rs`
- `services/gateway/src/service/diagnostics.rs`
- `services/gateway/src/service/runtime_transport.rs`
- `services/gateway/src/store/diagnostics_store.rs`
- `services/orchestrator/database-migration-registry.json`
- `services/orchestrator/database_migrations.py`
- `services/orchestrator/main.py`
- `services/orchestrator/test_database_migrations.py`

## 验证范围

本轮执行 Git 提交树模拟合并、交集路径统计、关键接口源码核对以及两方向内存 SQLite 台账兼容验证。完整合并后的构建、迁移升级演练、集群与 AGY 共存行为属于后续集成验收。
