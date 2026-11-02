# v3 调度改造与 codex-proxy-rs 对照

## 研究范围与版本

- 目标父仓：vibecoding-bench 的 v3 分支，研究开始时 HEAD 为 68950fd0b512ce6ca5f62e46420454e9fdfacd16。
- 目标子仓：cc2api，HEAD 为 046c0a28a518337ed2c9745c4193fea47904cb1f。
- 参考仓库：/root/project/codex-proxy-rs，HEAD 为 e0b7a841ca074f17e11dad73f39a159c75cb2fb1，研究时工作区干净；仅只读研究。
- 参考仓库没有 .codegraph 目录，按其 AGENTS.md 跳过 CodeGraph，使用当前源码核对。
- 已读取参考仓库的 AGENTS.md、cpr-dev-guide、架构中的 Workspace 边界、Core owner、智能调度／亲和／等待及后端自审章节。
- 本文记录研究开始时的源码事实与候选方向；当时未执行产品代码修改、构建、压测或线上发布。后续实施及验证见同目录上级的 `progress.md`、`verification/summary.md`。

## 用户确认的目标

1. 老会话稳定绑定，新会话控制准入。
2. 平滑发送，避免集中放行。
3. 参考 codex-proxy-rs 的智能调度，超出当前单一评分选账号的能力。
4. 暂不扩展上一轮建议中的独立错误重试／迁移策略和官方缓存配置改造。

## v3 研究基线事实

| 事实 | 源码或契约依据 | 对本轮的影响 |
| --- | --- | --- |
| 会话命中后直接续期并返回原账号；资格检查包含 Token 范围、账号状态和额度规则 | cc2api/src/service/account.rs:1105 | 稳定绑定必须保留现有硬门禁，不能把繁忙和真正不可用混为一类 |
| 首次准入后的绑定通过普通 set 写入，没有期望版本参数 | cc2api/src/service/account.rs:1259；cc2api/src/store/cache.rs:152 | 需要研究首次并发认领与过期写入覆盖，不能只延长 TTL |
| 当前会话哈希由原始 UA、正文和客户端类型生成，调用处没有传入 API Token ID | cc2api/src/service/gateway.rs:1952 | 新绑定命名空间与既有账号范围之间需要明确隔离及兼容合同 |
| 当前同优先级采用 7d／5h 有效用量与并发负载加权，最低分获选 | cc2api/src/service/account.rs:2249 | 智能调度不能仅修改系数；要引入准入事实和真实反馈，并区分未知／过期额度 |
| 当前并发队列满或超时会排除账号并重新选择；该分支没有排除 sticky 请求 | cc2api/src/service/gateway.rs:2140 | 本地容量等待需要与绑定稳定性协调，这是当前用户目标的直接差异 |
| 原 RPM 是固定分钟窗口；sticky 等待预算 5 秒、检查步长 250 毫秒；计数服务错误会失败放行 | cc2api/src/service/account.rs:1322；cc2api/src/store/cache.rs:168 | 平滑发送需要独立的真实发送许可及故障语义，不能只在分钟边界重置计数 |
| Gateway 先获取并发槽，再获取 RPM；等待并发时不得消费 RPM | .trellis/spec/cc2api/backend/service-architecture.md:336 | 新方案不能简单颠倒调用顺序，必须避免提前消耗或泄漏准入资源 |
| v3 发送先取得账号环境绑定，环境准备最长单独等待 120 秒，随后才向 sender 提交 | cc2api/src/service/runtime_transport.rs:184；cc2api/src/service/runtime_transport.rs:220 | 平滑发送位置必须考虑环境唤醒；入口按间隔放行不足以证明最终提交平滑 |
| sender 使用被冻结的账号、环境、generation、TLS 和原始 body；提交不确定时不能盲目重放 | cc2api/src/service/runtime_transport.rs:53；.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md:85 | 准入改造必须保留身份、字节与不确定提交边界 |
| 原生 CLI／项目／养号使用 passthrough 和原生 TLS，API 使用独立 sender，不经过 CLI relay | .trellis/spec/vibecoding-bench/backend/account-runtime-v3.md:68；:81；:85 | 只改 Gateway 不等于覆盖整个账号的所有模型调用；入口范围需用户明确 |
| 当前同时提供 MemoryStore 与 RedisStore，会话存储接口只有读取、设置和删除 | cc2api/src/store/memory.rs:9；cc2api/src/store/redis.rs:79；cc2api/src/store/cache.rs:152 | 绑定的原子性、保留时长及重启恢复应由单一事实来源负责，不能新增两个独立可写绑定 |

## 参考项目的实际机制

### 调度不是取消评分，而是把评分放在正确的约束之后

- RotationStrategy 提供 smart、quota_reset_priority、round_robin、sticky；亲和是独立的 relaxed／preferred／strict 策略。
- AccountSelector 先过滤账号范围、可用性、排除集与并发容量，再处理亲和与权重。
- Smart 使用实时负载、额度、平滑失败率、首个有效输出延迟及重置时间。
- 排队权重仅用于选择等待队列，不混入立即选号；参数为零时保留现有最短队列行为。
- 在近似最优候选集合中按稳定账号顺序轮转，避免总是让唯一最低／最高分账号成为热点。
- 未知额度保持中性；未知或过期重置时间不获得奖励。

依据：backend/crates/gateway-core/src/account/selection.rs:200、:689、:819、:895、:916；account/smart_scheduling.rs。

### 真实反馈与本地容量拒绝分开

- AccountFeedbackStats 只接收真实上游 attempt 的结果，按 Provider 与账号隔离。
- 成功、失败与容量拒绝更新平滑失败率；错误率随时间衰减，首个有效输出延迟使用平滑观测。
- 没有实际发送的本地排队超时不作为上游健康失败，不应该把繁忙账号误判为坏账号。

依据：backend/crates/gateway-core/src/account/selection.rs:219、:273、:311；docs/architecture.md:750、:808。

### 绑定是带版本的事实

- 会话绑定按 Client Key 隔离，并携带 revision。
- compare_and_bind 在发送前原子首次认领、续期或迁移；期望快照冲突时释放租约并重新选择。
- 响应完成不把账号重新写回绑定，避免旧请求覆盖较新的绑定。
- 严格亲和与续写的 Provider 语义独立；不能把 OpenAI 根线程／后代规则原样套到 Claude 协议。

依据：backend/crates/gateway-core/src/provider_ports/affinity.rs:10、:43、:85；docs/architecture.md:767。

### 等待有统一生命周期

- 并发等待保留同级 FIFO、固定等待位置、容量上限与取消回收。
- 等待开始后，不因切换等待层、账号或 Provider 而重置预算。
- 在成功准入时才计入 RPM；等待位置不能替代真正运行容量的原子裁决。
- 请求取消或异常退出通过租约和 Drop 清理；不把请求正文持久化后在重启时重放。

依据：backend/crates/gateway-core/src/engine/admission.rs；engine/execution/admission.rs；docs/architecture.md:808。

## 可移植方向与边界

- 借鉴：资格与容量过滤、严格会话亲和、带版本绑定、共享等待预算、真实反馈、近优轮转、诊断与实际选号共用规则。
- 保留本项目的 Account、Token 范围、已有额度门禁、weighted FIFO、原始字节与 v3 sender 归属校验。
- 不为照搬参考项目引入 Provider 插件框架、Redis／PostgreSQL 作为新的强制部署依赖、OpenAI continuation 语义或额外模型探测请求。
- 不把参考项目的具体权重、阈值和半衰期直接当成本项目已有需求；具体取值应在设计中明确来源及验证方式。
- 不改变现有上游故障重试次数和永久失效处置；已有实际发送仍须纳入平滑发送约束，避免重试绕过准入。
- 不将方案描述成能保证官方不会停用账号，验收聚焦本地可观察的不变量。

## 范围与已收敛决定

- 用户已确认本轮先完成 v3 API 网关的会话、账号调度、最终发送准入这一条链路。
- 原生 CLI／项目／养号维持既有独立出口，不在本轮声明统一每请求发送预算。
- 新模式默认 smart，保留旧评分排序回退；稳定绑定与平滑发送为 v3 共同底座。等待预算、持久状态、配置与管理诊断已收敛至同目录 design.md，最终 Brief 已由用户确认，当前处于实施验收阶段。
- 初版复用目标项目已有的响应头到达耗时，不将其写成参考项目的首个有效输出延迟。发送节奏以环境就绪后 Gateway 向 sender 提交为验证边界。

## 验证入口

- cc2api/tests/account_scheduler_test.rs：Token 范围、真实额度、sticky、未提交绑定、RPM 饱和等既有合同。
- cc2api/src/service/gateway.rs 的 admission 回归：等待不提前消费 RPM、队列满／超时后的资源清理。
- cc2api/src/service/runtime_transport.rs：环境与代次校验、sender 前置拒绝、原始字节和不确定提交。
- 跨分钟、并发首次认领、热点会话、取消、冷启动和重启恢复行为已加入测试；实际执行结果见 `../verification/summary.md`。
