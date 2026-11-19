# 账号、运行环境与请求日志展示执行节点

## 目标

在账号、运行环境和请求记录的主要视图中直接辨认执行节点，并可追溯请求真实执行位置。

## 背景与证据

- `apps/web/src/components/runtime/nodeApi.ts:20` 定义 `AccountNodeAssignment`，包含节点 ID、稳定标识、名称、类型、启用状态和归属版本。
- `apps/web/src/components/runtime/runtimeApi.ts:41` 的 `RuntimeEnvironment` 已有公开节点投影及 `node_observed`、`node_message`。
- `apps/web/src/components/RuntimeEnvironments.vue:105` 的环境详情已展示节点名称，列表卡片需要前置展示。
- `services/orchestrator/main.py:9682` 的任务账号列表目前组装账号、运行窗口、额度与养号摘要，需补齐节点公开投影。
- `apps/web/src/api.ts:436` 定义尝试的 `execution_location`，含 `node_key`、环境 ID、环境代次及分配版本。
- `apps/web/src/components/RequestDiagnostics.vue:322` 的列表缺少执行节点，`:347` 的链路详情已有逐次 `node_key` 展示。

## 需求

- R1：账号、运行环境的列表及详情展示节点名称和稳定标识，并区分所属节点与最新在线观察。沿现有设计统一层级、间距、字体和状态色，桌面与手机均保持清晰美观。
- R2：请求列表展示末次实际尝试的节点；请求详情逐次展示实际节点、环境 ID 和环境代次。
- R3：节点迁移后的历史日志继续根据实际尝试的执行位置展示。
- R4：缺少观察的历史记录显示未观测；没有实际尝试的请求保持明确的无执行信息状态。
- R5：使用管理接口的安全公开投影，保护节点私钥、凭据及传输认证材料。

## 验收

- AC1（R1）：本机和 SSH 节点账号在账号卡片、详情、环境卡片、环境详情均可辨认节点。
- AC2（R1）：远程节点不可达时继续展示已保存归属，并明确显示当前观察状态。
- AC3（R2、R3）：请求多次尝试可展示各自执行位置，账号迁移后旧请求仍归属实际执行节点。
- AC4（R4）：老日志、无上游尝试和缺少节点观察均显示与已确认本机执行不同的状态。
- AC5（R5）：新增投影只包含安全管理字段。

## 范围外

- 节点注册、探测、迁移及自动分配机制变更。
- 节点过滤、性能排行和监控面板扩展。

## 任务衔接

该子任务可独立实现和验证。执行顺序放在 11-19-account-admission-decoupling 之后，以复用该任务最终的账号公开投影。联调时确认控制变化后节点归属及历史执行信息保持一致。设计和执行计划分别记录于 design.md、implement.md。
