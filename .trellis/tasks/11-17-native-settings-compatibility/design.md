# Native 系统设置兼容总体设计

## 任务边界

本父任务维护五项来源需求、独立子任务映射和最终集成验收。实际实现由子任务承接，父任务承担集成审阅。产品方向为后续全面使用native，原有路径用于行为对照和已授权的PassThrough修复。账号批量迁移、后端退役、正式发布和部署由独立任务或SOP负责。

## 子任务与数据流

| 顺序 | 子任务 | 主要边界 | 交付 |
| --- | --- | --- | --- |
| 1 | native-fable-429-fallback | Gateway响应分类→完整决策→原循环重试 | 全模型明确429、Fable、PassThrough、槽位及截止 |
| 2 | native-message-cache-policy | Settings→请求快照→NativeSubmission→worker→原生封口 | 默认off、存量一次性重置、手动开启、热生效及能力 |
| 3 | native-peak-prime-routing | PrimePoller→指定账号native→prime_logs→Settings UI | 原生模型预热及统一记录界面 |
| 4 | native-disabled-thinking-compat | 显式开关/模型名单→业务副本→原生封口 | 最小disabled→adaptive兼容及双版本原生回环证据 |
| 5 | proxy-pool-setting-scope | Settings元数据与帮助 | Rust代理HTTP连接池适用范围 |

各子任务的prd/design/implement是本项权威材料。R5为轻量文案任务，使用PRD即可。R2基于R1后的热路径工作；R3基于R2后的原生策略通道；R4基于R2/R3后的发送接口。此顺序作为文档依赖，父子关系本身不执行调度。

## 共同合同

原始HTTP入站、实际业务副本、原生组装和TLS观察分别保留来源。429换号保持同一请求截止、每次账号身份、真实attempt和槽位生命周期。缓存及thinking改写在CCH封口前完成，历史签名和无关业务字段保持。系统设置复用原保存、草稿、热刷新及双库约束。

进程准备为零模型初始化，峰值预热是真实模型调用，两类状态分别留在环境页和设置页。预热记录复用现有字段及统一视觉token；连接池控件说明Rust与native SDK的实际作用范围。

## 验证与证据

先离线特征测试，再合成凭据的sender/回环TLS验证，再浏览器呈现验收。280/293、实际执行体身份、CCH和各次模型发送数来自真实观察。R4按用户最新决定以双版本原生构造和实际TLS发送验收，真实上游失败及实际兼容效果列为后续验证项；模拟拒绝与真实事件分开登记。

## 回滚与交付

R1/R3依精确代码补丁回退；R2可切off回到保留缓存布局，旧模式归一化需要保留转换记录；R4可关闭原开关；R5为可逆文案。共享runtime协议/能力和本地候选产物需保持配套。Check-All、Spec更新和Git交付各遵循其独立门禁。
