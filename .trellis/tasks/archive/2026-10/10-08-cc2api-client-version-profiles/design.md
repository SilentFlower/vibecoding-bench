# 技术设计

## 架构与边界

复用 `version_profile.rs` 的 `ClaudeCodeProfile` 注册表及现有 260/280 协议事实。新增请求级选择结果，原账号继续负责凭证、调度与持久设备身份。

为实际进入改写的账号创建请求级副本，使用已有 `apply_identity_to_env_json` 仅覆盖副本 canonical env 中的 version、version_base、build_time、node_version。已有 `device_profile`、body/header/billing/bootstrap helper 因而读取同一画像，不需要到处增加版本条件，不写回账号 store，也不改变设备 ID、硬件或系统环境。对空或不完整的旧账号 env，副本先使用既有 `device_profile` 归一化结果补齐已知字段，保留未知字段，再覆盖软件版本，避免反序列化失败把所选画像丢回默认版本。

新增设置 `claude_code_profile_selection_mode`，允许 `client_version` 与 `account`，默认 `client_version`。新旧数据库幂等补齐缺失 key，已有显式值保持原样。新模式把已有 `claude_code_version_profile` 作为未匹配请求的默认画像；旧模式保留原账号画像选择及全局切换事务。Settings 页面解释这一区别并提供回退选项。

## 版本选择与数据流

1. Gateway 保留原始 headers/UA，先执行当前 AccessPolicy，不扩张允许范围。
2. 新模式严格提取 `claude-cli/<semver>`、`claude-code/<semver>` 的完整版本，只自动匹配 260/280，不做 substring 或版本区间推测。
3. 原始 UA 是唯一客户端版本来源。缺少、非法或未支持的 Claude UA 版本直接回退配置的默认画像，出厂为 280。GrowthBook 的 `attributes.appVersion`、event_logging 的 env 版本及其他请求体字段均不参与选择，也不从 Bun/axios/Stainless UA 反推版本。
4. 未匹配请求使用 Gateway 热缓存的全局默认画像；旧模式使用原账号 env。单请求选择冻结，设置热更新、换号、401 和签名重试不改变其画像。
5. Admission、RPM、sticky 与上游 session pool 使用原账号和真实 session。请求级副本仅用于改写、内部 hello、bootstrap、签名重试及遥测。
6. 保留原生客户端与 API 分支、未知字段、原始 SSE 字节和各画像的模型/辅助请求/CCH/续轮后缀规则，不把两版行为强行统一。

没有版本信息的初始 hello 等辅助请求使用默认画像；已识别主请求触发的内部 hello 使用该请求画像，不承诺从无版本信息识别客户端版本。

## 遥测隔离

- 自动遥测 key 从 account_id 改为 `(account_id, profile_key)`，message request/result 用创建时的请求级副本定位所属容器。
- 同账号两版同秒启动时，运行 ID 也须区分 profile 命名空间；真实 message session 的关联规则保留。
- 后台 event logging UA、GrowthBook UA、payload env、默认模型使用容器固定画像。移除 `session_ua` 从持久账号版本构造 UA 的行为；凭证续期只更新 token。
- 容器的续期、退出、重建、异步结果和清理全部使用复合 key。管理端到期时间按账号取所有容器的最晚值，发送计数继续汇总到原账号。
- 生命周期沿用当前 10 分钟 TTL，容器数随活跃画像数增长，不为每个版本增加账号容量。

## 缓存、探测与会话

- Stateful key 增加有效 profile key，保持 account_id 和真实 session；延迟提交句柄固定原 key。
- Hello singleflight/结果 key 增加有效 profile key，保留代理与上游 session 的原去重维度；Memory/Redis 使用现有通用状态接口，不新增表。
- 非流式探针缓存增加有效 profile key，避免没有版本 UA 的请求在默认画像切换后复用旧响应。
- Sticky、RPM、并发和上游 session 池不增加版本维度；仍共享账号总容量，上游 session 映射仍用真实 session。

## 兼容与回退

- 出厂画像与默认允许范围仍为 280，管理员的显式默认与准入规则保留；画像匹配不突破 AccessPolicy。
- 在新模式下修改默认画像不保证自动开放该版本以外的客户端，页面区分默认画像与准入策略。
- 设置切回 `account` 恢复旧选择方式；缓存自然过期，无需清库或重写账号身份。
- 仅补齐设置 key，SQLite/Postgres 均幂等；既有全局画像切换事务保留，已冻结请求继续使用原上下文。

## 权衡与风险

- 请求级账号副本可复用现有 helper，必须防止误写入 store；实时 token 仍通过原账号 ID 获取。
- 遥测容器数增长，需要验证 TTL 清理、运行 ID 和账号级聚合。
- 两版 CCH、模型、safeguards、Bun 与 bootstrap 不同，测试必须使用可区分两版的样本，不只断言 UA。
- 现有已验证 classifier 分支保留；无版本证据的辅助请求使用默认规则，不推断新画像。
