# AGY 与集群版本兼容设计

## 集成基线与 Git 边界

在当前工作区从冻结集群目标 `0764b5fa75e0df6c5c12969fdc40b53d3bbf734c` 创建 `merge/agy-into-flower2api`，将 AGY 来源 `ca198ee979ec968bcd7d1a2063c872edb05850f7` 以 `--no-commit --no-ff` 合入。冲突解决后得到同时包含两侧历史的集成分支，后续可供 Flower2API 合回。提交与推送由精确 Git 计划承接。

原 `/root/project/vibecoding-bench` 的 Flower2API 工作区有 323 项状态条目。所有集成修改限当前工作区。若冻结来源或目标在开工前发生变化，先重新检查差异并同步规划材料。

## 迁移链

采用已发布集群链为唯一 bench 正式链：

| 版本 | 步骤 | 处理 |
| --- | --- | --- |
| 1 | bench.baseline.1 | 保留 |
| 2 | bench.cluster.2 | 保留 |
| 3 | bench.node-executions.3 | 保留 |
| 4 | bench.node-login-drafts.4 | 保留 |
| 5 | bench.agy-environments.5 | 从 AGY 增量追加，更新前驱和全部运行时/校验引用 |

AGY 环境纯定义继续保持既有 SQL 语义。执行器的注册、结构验证、测试及发布 `BENCH_SCHEMA_SOURCES` 均引用新步骤身份。网关沿集群已有 1—4 加入 AGY 5—6，保持两侧原定义摘要。

迁移定义来源表合为一个完整映射，包含 baseline、cluster、node-executions、node-login-drafts、agy-environments。保留目标对符号链接、来源缺失和摘要不符的严格校验。旧步骤的 SQL 和摘要逐项与冻结目标比较。

`bench.agy-environments.2` 开发分支台账与正式链存在同版本异身份。沿原校验在写入前受控拒绝，验证拒绝后内容及台账一致。该场景不能伪装为普通 `compatible_newer`，也不能自动重写历史。正式集群旧程序针对新增版本 5 的兼容读写继续按现有演练合同验证。

## 运行时与维护

- AGY 在原平台分流入口使用独立 API 环境，保持工程账号 ID 空值和网关账号独立映射；原集群工程账号继续按 assignment 路由远程 Node。
- 合并维护调用时同时保留远程分发和 `expected_generation`。核对远程管理输入的现有代次保护；只有发现实际缺口才在既有合同内补齐。
- 退出路径分别关闭集群迁移操作和取消/等待 AGY 清理任务，复用原 lifespan 资源释放顺序。
- 凭据管理继续保留单一 RT 所有者及原维护门禁，业务环境只接收 AT-only 副本。
- AGY 工具回填与实际 Root active 继续进入维护排空；原工具结束与物理控制收口保持两个事实。

## 诊断和页面

`AttemptDiagnostic` 同时包含可选 `execution_location` 和 `context`，所有结构构造点同步补齐默认值。旧 JSON 缺失字段沿 serde default / TypeScript 可选字段兼容。CC 节点观测和 AGY 上下文分别来自实际执行事实。

环境数据类型同时保留 node/login_draft 与 platform/agy_runtime。Vue 冲突区合并对应显示内容；沿原 tabs、轮询、焦点、维护状态及登录草稿交互。诊断详情同时展示节点信息和 AGY 代次、工具、策略及收口事实。

## 构建与升级器

以目标运行时读取平台版本的实现为准，接入 AGY 认证制品 SHA 构建输入。保留当前受控构建缓存、并发及镜像身份核验。升级器源码集合取两侧必要模块并集，复用已有去重和摘要校验机制。

## 验证和恢复

验证按 PRD 的 AC01—AC07 记录证据。使用本地合成材料和隔离数据库，真实外部模型预算为 0。后续验证遇到环境缺失时记录实际阻断并沿既有测试启动方式补齐。

Git 恢复点为两个冻结 SHA、保存的全树检查点和实际 merge 状态。集群目标作为第一父提交，AGY来源作为第二父提交。实施过程中保存已完成的冲突处理。若恢复会覆盖新增文件或其它会话改动，先核对精确范围；禁止用整体重置代替恢复。测试数据库与合成环境按原工具 finally 清理。生产数据库和原 Flower2API 工作区由原所有者流程管理。

## 合并方向调整证据

Git预检发现原方向会重复检查集群已发布的原始日志行尾。最终方向改为集群第一父提交，已解决的最终索引树与保存的候选树完全相同。AGY两个Python桥和历史父任务PRD仅规范文件末尾空行，Python AST逐项一致。目标、范围和业务验收保持原方案；详见 research/integration-tree-proof.json。
