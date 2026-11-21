# cc2api Backend Service Architecture

## 适用范围

本文件约束 `services/gateway/src/` 的 Rust 后端结构：

```text
src/main.rs
src/handler/
src/middleware/
src/model/
src/service/
src/store/
src/tlsfp/
```

## 分层契约

- `main.rs` 只负责装配：加载 `Config`、初始化 tracing、注册 SQLx Any driver、初始化 DB/cache/store/service、启动后台 poller、构建 router。
- `handler/router.rs` 负责 HTTP 路由、DTO 解析、管理 API 返回形状和静态资源 fallback，不把复杂业务逻辑塞进 handler。
- `middleware/auth.rs` 只处理管理端 Bearer 密码认证；网关 API token 鉴权留在 `gateway_fallback` 进入 `TokenStore` 查询。
- `model/` 是 DB/API 共享结构。新增字段要同步 store 映射、前端类型和迁移。
- `service/` 放业务逻辑：账号调度、Gateway 转发、OAuth、usage poller、telemetry、rewriter、version profile。
- `store/` 放持久化与缓存抽象。不要让 handler 直接写 SQL。
- `tlsfp/` 和 `craftls/` 是 TLS 指纹链路，改动要按协议/抓包任务处理。

## Scenario: 按账号选择固定 293 原生后端

历史后端键native293现为280/293自动匹配。新增私有版本字段、选择冻结、版本池与部分可用合同见[双版本自动选择](../../runtime/backend/runtime-contract.md#scenario-双版本自动选择与独立来源准入)；下文既有生命周期继续适用。

### 1. Scope / Trigger

- 账号管理、Gateway Messages 分流与 V3 sender 原生池属于跨层合同。实现依据为 `model/account.rs`、`handler/router.rs`、`service/{gateway,native_contract,native_runtime,runtime_transport}.rs` 及账号前端。

### 2. Signatures

- 账号 DTO/模型字段 `request_backend: String`，仅接受 `legacy|native293`；历史和省略值默认 `legacy`。
- `PreparedTransport::native_ready(&self) -> Result<(), AppError>`；`submit_native(self, submission: NativeSubmission, ttfb_timeout: Duration) -> Result<reqwest::Response, AppError>`。
- 服务鉴权的 `GET /internal/native/status` 返回 `raw_input_protocol:1,version,environment_id,generation`；`POST /internal/native/messages` 接收 `NativeSubmission`。
- 零模型接口：`POST /internal/native/prepare` 接收 `NativePreparation`，`POST /internal/native/prepare/cancel` 接收 `NativePreparationControl`；均沿用当前 sender 私有鉴权和绑定校验。
- 管理接口 `GET|POST /admin/accounts/:id/native-preparation` 分别查询状态、合并准备提示；POST 返回 `queued:true,preparation`，不等待加载。`GET /internal/v3/transport/:id?wake=false` 只解析已运行绑定，缺失/休眠返回 null。
- `NativePreparation` 字段：`account_id:i64,environment_id:String,generation:u64,preparation_id:UUID,deadline_unix_ms:u64,bearer,device_id,account_uuid?,organization_uuid?,email,concurrency:i32`；取消合同仅含前四个归属字段。准备响应包含 `state,account_id,environment_id,generation,preparation_id,version,raw_input_protocol,pid?,idle_workers,reused`。
- `NativeSubmission` 字段为 `request: PreparedRequest,input: Value,bearer,device_id,account_uuid?,organization_uuid?,email,concurrency:i32,log_mode:RequestLogMode,ingress_capture?:Value,cache_ttl_rewrite?:String`，禁止 Debug 输出。input 为同 request_id 的 schema 1 原始信封；日志模式缺省 info，详见[CC 组装后私有采集](settings-database.md#scenario-cc-组装后私有采集)。
- `validate_request(prepared: &PreparedRequest, config: &SenderConfig) -> Result<tokio::time::Instant, AppError>`冻结接收边界的单调截止。`NativePool::submit_validated(config, submission, deadline)`只接收已校验信封；直接`submit`先校验一次。

### 3. Contracts

- 创建、编辑、列表、OAuth 默认与表单重置同步后端值。切换进入现有排空门禁；非 V3 同样检查本地活动。状态快捷操作单独保存该字段，避免用旧 Account 快照覆盖凭据。
- 普通准入、账号选择、凭据解析及加权许可仍由 Gateway 所有。原生分支在 Rust 正文/头部/CCH 重写前接管精确 Messages；保留逻辑 JSON 与 HeaderMap 多值，头值在私有信封中按 Latin-1 字节串传递。
- 账号 Fast/1M 权限先明确拒绝越权申请；允许时保持原始输入交给二进制。当前 bearer 和受控身份进入工作进程，RT 留在既有凭据所有者。原生池的 Linux x64、身份、封存、预算及回收规则由 [V3 原生 sender](../../orchestrator/backend/account-runtime-v3.md#scenario-v3-原生-sender-共享映像池与资源预算)所有。
- 每个原生作业最多一次模型提交；签名修复仅在完整收到明确的 `invalid_request_error` 签名 400 后，同账号、冻结版本追加一次 thinking 降级作业。复用 legacy 既有 thinking 转 text、移除 redacted_thinking 及根 thinking 和依赖清理策略；工具历史保持。两次准备与发送共享首次冻结的剩余预算，已耗尽则返回首次 400。普通 400、传输失败及状态不明保持原响应路径；明确 429 由 Gateway 共用分类决定透传、有限退避或换号。legacy 的两阶段 signature 等既有重试沿原路径。调度 submitted 记录每次实际内部 POST，各作业有独立 UUID，收到可信上游观察后各自记录诊断尝试。
- 原生 OAuth 恢复只接纳受信 sender 已确认版本和实际尝试、完整且不超过 4 KiB 的逻辑 JSON HTTP 401，且 `error.type == "authentication_error"`。在账号活动门禁内只读重查同账号，当前账号必须为 active OAuth，持久化 access token 必须与本次实际发送的 token 不同且有效。比较摘要仅存在本次调用内。网关不主动换票、不等待换票、不因该 401 停用或换号。使用新凭据、首发版本、会话映射和缓存策略，在原期限和原准入上下文内重发；每个根请求最多提交一次认证重试，同轮不叠加签名修复。诊断记录重试原因为 `oauth_recovery`。
- Gateway仅在上述修复获2xx后学习失效历史；仅按改写前真实会话ID和完整thinking文本/签名前缀做SHA256隔离，新增普通消息或新thinking块仍匹配旧前缀，首发前应用同样降级。同一实际会话更换账号、源版本或模型仍复用该记录，当前请求的修复重试继续限定同账号。会话取正文metadata或合法session头；缺少明确实际会话时只处理本次修复，保持跨请求独立判断。进程内至多4096项、有效期7天，满时淘汰最早到期项；不保存正文或签名原文，失败修复不学习。重启、过期、淘汰、新失效历史或并发首次学习可能重新触发首次400。
- Gateway逐请求冻结当前cache_control_ttl_rewrite（off/5m/1h），私有TTL策略在checkout前校验。worker_ready能力cache_ttl_rewrite_protocol=1才发送该字段；强制模式遇旧内核返回503且零模型提交，off兼容旧版。策略不参与池身份，修改设置继续复用暖PID；配套内核先激活，再更新平台。旧内核回滚前先关闭强制TTL。
- 响应流日志按网关根request_id、原生job/attempt UUID、worker/PID关联。本层EOF、body_error、静默超时、下游Drop及IPC/运行时错误分别记录，含持续时间、片段/字节及最后收包间隔。错误链最多八层，仅投影reqwest/hyper/io类型标志及OS代码；运行时原错误只保存SHA与受控code。代理隧道仅记录worker/tunnel UUID及密文流量数字，不能据双向复制收口断言首个关闭方。普通日志禁止异常原文、URL、代理凭据及正文。
- account-sender 启动时初始化 JSON tracing 日志，默认 info，支持 RUST_LOG，关闭 ANSI。原生 error 事件的可选 diagnostics 经 native_error::project 独立有界校验后，记录实际阶段、最多八层白名单 name/code 及截断/循环/读取失败标记；保留原错误 SHA。日志包含 job、worker/PID、account_id、generation。缺省摘要记 unavailable，畸形记 invalid，均保持原业务响应。TS/Rust 目录及实际事件结构由 tests/fixtures/native-error-diagnostics.json 交叉验证；进程退役前记录，保留期沿 Docker 日志轮转。
- sender 校验现有绑定、代次、deadline、目标及秘密，原生目标仅 POST `/v1/messages` 且无 query。response 继续经过共用用量观察及流许可，取消、EOF、Drop 各按既有一次收口。
- 私有`deadline_unix_ms`采用一次墙钟采样：过期拒绝，未来上限允许120秒预算加5秒跨进程时钟偏差，实际剩余预算钳制120秒。legacy发送和原生启动、首响应共用接收时冻结的单调截止；池内不重复按墙钟验期。暖进程在业务投递前复核单调截止，启动耗时不能换取新预算。
- 准备仅 checkout/真实 worker_ready/回池，禁止调用 execute、模型或计费。后台协调并行2、待处理账号最多128；启动及5/20/60秒补偿只解析运行绑定。bench 环境就绪在生命周期锁外按环境/代次通知一次；在途新提示合并为一次后续执行。账号更新、凭据提交及交接重新开放门禁后触发准备。
- 准备执行时重读权威账号，解析 bearer 后核对同一身份；成功前再次核对账号及只读运行绑定。失效、维护、凭据门禁关闭及取消优先收口，已处理取消的迟到完成不能发布 ready。取消按账号/环境/代次/准备 UUID 隔离，保留130秒撤销记录覆盖提前到达与迟到重放；最多16个在途和256条登记，满时明确拒绝。
- 原生能力检查和热路径复用保持打开的已验证分发体 FD；每轮检查规范路径、dev/inode、大小、mode/uid/gid、纳秒 mtime/ctime，变化后重新完整校验 SHA。新进程启动仍执行固定分发体、精确执行 FD、执行体 SHA 和四项封存核验。
- Claude Code 原生 messages 在封口前复用现有账号级上游会话池开关、容量、TTL、刷新策略与缓存原子映射；缓存故障沿现有失败开放。窄映射只替换一致的 UUID session 头及 metadata，真实下游 session 继续拥有 sticky/RPM/排队/取消/本地历史。Prompt ID、轮次、thread、显式代理/父代理保留；隐式主代理 ID 冻结为真实 session，避免池映射改变子代理父归属。冲突/重复/畸形会话继续由原生边界拒绝。诊断将预期上游 session 与实际 cc_prepared 核对，异常显示观察缺口。
- 诊断通过 `x-v3-native-observation` 取得实际 cc_prepared 的受限摘要，画像按实际source_version记录280/293，来源对应`native280_cc_prepared|native293_cc_prepared`，私有作业UUID与sender证据关联。观察版本与冻结目标不符时拒绝采纳。上游同名控制头先剔除；网关消费后移除内部头。观察缺失标记对应版本的native*_unobserved，准备拒绝保持零模型尝试；组装快照不能当作最终TLS。按账号开启的完整头与正文遵循[CC 组装后私有采集](settings-database.md#scenario-cc-组装后私有采集)，完整内容经独立管理员入口读取。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 未知 request_backend、Fast/1M 超出账号权限 | 400，原账号或模型零发送 |
| 忙时切换后端 | 现有忙门禁拒绝，归属保持 |
| 缺 V3/二进制/预算、能力或代次不符、平台不支持 | 503 准备失败 |
| 私有期限已过期或剩余超过125秒 | sender在提交前拒绝；原生网关映射为503准备失败，模型零发送 |
| 固定 293 无法接纳正文版本或参数 | 二进制受控错误，模型零发送 |
| 提交后断线或状态不明 | 502，保持单次提交语义 |
| 原生上游状态错误（下列可恢复情形除外） | 返回本次状态及响应，管理员空闲时显式切回 legacy |
| 原生明确429 | 依共用分类透传、有限退避或排除当前账号后重新选号 |
| 明确签名400且正文可修复、预算尚余 | 同账号追加最多一次修复；获2xx后记录历史摘要，续轮命中则首发前修复 |
| 原生 OAuth 认证 401，同账号已更新有效 token 且仍能提交 | 同账号重发一次，返回第二次结果。第二次提交状态未知时走既有 502 语义 |
| 裸 401、其他错误类型、缺上游证据、token 未变或失效、重试前预算耗尽 | 保留首次 401 正文及关联 ID |
| 后台环境缺失/休眠或首次控制面未就绪 | sleeping 或 failed 状态，保持零模型；由后续通知或有界启动补偿恢复 |
| 准备后账号/凭据/运行代次变化 | 回执失效并取消本次准备，下一轮重新读取当前身份 |
| 撤销早于准备到达、准备重复或登记满 | 准备受控503；取消登记满返回明确503 |

### 5. Scenarios and Examples

- 正常：账号 A 选择 native293，账号 B 保持 legacy，A 的标准并发 3 支持 3 普通或 6 Haiku；普通 API 与原生 293 由同一二进制构造。
- 边界：历史账号缺字段仍走 legacy；count_tokens 等端点继续其既有路径；两个账号空闲切换相互独立。
- 正常：旧thinking签名首次被拒后，同号降级获2xx；下轮追加普通消息仍携带该历史时首发前降级。错误用法是每轮盲目重试任意400，或在提交结果未知时换号重放；正确处理是只接纳完整明确签名拒绝并限制一次，同号修复失败保持错误。
- 正常：首发使用旧 token，上游返回认证 401 时同账号已有新 token，重发后得到 200。错误用法是对任意 401 强制换票；应核对实际首发凭据，未发现不同的有效 token 时保留原拒绝。
- 时钟边界：原120秒信封遇到1275毫秒回拨时可接纳，实际预算为120秒；偏差恰好5秒可接纳，超过5秒拒绝。错误用法是按墙钟反复重算期限或直接等待125秒。正确处理是一次转换并沿同一`Instant`传递。
- 错误用法：原生失败后自动回落 legacy，或复用旧凭据代次的 idle worker。正确处理：当前请求明确失败，后续作业按当前代次重建，回退由管理员显式选择。
- 正常：账号启动预热一个进程，首次业务复用同一 PID；预热和重复准备的模型计数增量为0。池容量1时，下游主会话和子代理可共享上游 session，子代理的 parentAgentId 仍指向真实主会话。
- 错误用法：因账号已有准备在途而跳过新代次提示，或把 sender 的旧成功回执直接当作当前 ready。正确处理：保留合并提示，并在发布成功前复核当前绑定与身份。

### 6. Tests Required

- `account_backend_defaults_validate_and_obey_busy_gate`、`historical_backend_migration_and_account_updates_are_independent`：默认/非法值/忙门禁/两账号和回退。
- `native_backend_preserves_account_feature_authorization_without_rewriting`：Fast/1M 权限拒绝且正文保持；前端 `npm run build` 及创建/编辑/reset 链路核对。
- `tests/native_signature_fixture.py`经真实Gateway及回环sender覆盖280/293首次400→2xx、续轮单发、同一实际会话跨账号/版本/模型复用、正文与头部会话关联、不同/缺失实际会话独立判断、失败不学习、独立诊断尝试、普通400/业务透传429/提交未知保持单发和预算耗尽；`native_signature_repair`单测覆盖完整思考前缀、不同会话及变更历史隔离、跨模型复用、新建实例重新学习、7天过期及4096项上限。
- 同一回环夹具用首发屏障模拟在途换票，断言 280/293 各以旧、新凭据依次向同账号发送，正文相同，200 及再次 401 均为两次尝试。覆盖凭据未变、裸 401、其他错误类型、缺上游观察及期限耗尽时单次发送并保留首次关联 ID。
- `native_real_binary`、`native_real_gateway`：实际附件、独立 TLS/CCH、HTTP/SOCKS、多值白名单、工具/thinking、主子会话、单次发送、取消/代次和诊断来源。跨平台备用实现编译验证明确 503。
- `rejects_wrong_environment_and_arbitrary_target`覆盖回拨1275毫秒、5秒偏差边界/超界、过期及临近截止的剩余预算；`native_real_binary`覆盖暖进程到期后的零业务投递。离线驱动在子阶段断言前保存可选实收摘要，失败报告由合成缺失二进制故障注入核验。
- `native_real_gateway`：首次只读绑定503后的启动补偿、零模型预热、首次同PID、在途提示后绑定故障仍继续准备、准备完成时换代拒绝、凭据轮换旧PID退出、真实主/子会话映射与观察对应。使用隔离网络及合成 TLS，不触发真实账号模型。
- `ownership_return_is_atomic_idempotent_and_old_reply_cannot_reopen`断言交接 finish 与同操作重放产生原生就绪通知；`test_account_runtime.py`覆盖只读休眠/缺失、绑定归属/代次及通知去重/失败补偿。分发体缓存覆盖同大小改写且恢复mtime、chmod及inode替换后拒绝/重验；取消覆盖提前登记、等待初始化与跨代次隔离。

## Scenario: 原生持续预热、实时就绪与请求进程诊断

### 1. Scope / Trigger

- `native_prewarm.rs`、`native_runtime.rs`、`runtime_transport.rs` 和请求诊断共用当前原生池，增加零模型存活检查和实际业务进程观测。准备成功回执与实时可接单状态分别保存。

### 2. Signatures

- 私有鉴权 `POST /internal/native/readiness` 接收既有 `NativePreparation`，返回 `NativeReadinessStatus`。`GET /internal/native/status` 继续只表示能力。
- `GET /admin/accounts/:id/native-preparation` 主动检查当前身份；`GET /admin/native-preparations` 返回最近巡检快照数组；`POST /admin/accounts/:id/native-preparation` 接受布尔查询参数 `wake=false,cancel=false`，合并准备提示；两者同时为 true 返回400。
- `NativeRequestObservation.runtime`、持久化 `AttemptDiagnostic.runtime` 为可选 `NativeRuntimeObservation`，历史记录缺字段按 None 解析；沿用诊断 JSON，数据库结构保持原合同。

- `system_update::background_admission() -> Result<Option<UpdateActivity>, AppError>` 与普通准入共用安全门禁读取及活动锁；合法维护返回 None，开放返回活动证明，损坏门禁返回错误。

### 3. Contracts

- 成功更新中明确提交 `request_backend=native293` 且最终账号 active 时，普通和 status 快捷出口均先释放配置门禁，再发出显式唤醒事件；同值保存也适用。事件为 `(account_id,invalidate,wake)`，原通知默认 wake=false。显式事件调用 `runtime_transport::prepare`，普通扫描、启动补偿、周期巡检及 GET 检查保持 `prepare_existing` / wake=false。
- 显式唤醒沿同一有界队列、去重及截止执行。账号与平台维护等待、失败退避保留该意图；`cancel=true`、停用、切回 legacy 或身份失效撤销旧工作及其失败唤醒重试。人工停止在领取维护作业前先撤销意图。
- 批量快照附加当前权威 `request_backend`；缺缓存时使用 unprepared。该目标字段不授予 ready、PID 或实际环境归属。

- `NativeReadinessStatus` 字段为 `state:String,account_id:i64,environment_id:String,generation:u64,kernel_generation:Option<String>,release:Option<NativeReleaseRef>,checked_at_ms:u64,idle_workers:usize,live_workers:usize,pid:Option<u32>,reason:Option<String>`。池状态为 `ready|busy|preparing|unprepared|failed`，协调器另投影休眠、停用、维护、失败和未知。
- 就绪必须属于与业务相同的配置、bearer、账号身份及并发池键。检查真实子进程与空闲管道，坏进程退役；固定分发体、执行映像及封存校验完成后才记录 worker 的 ready 时刻。旧身份物理进程仍忙时不得充当新身份 busy。
- 池身份统一规范化SenderConfig.quota_identity为空、native_adaptive_prewarm=false；额度观察字段首次补写与备用开关变化保持暖池。bearer、代理、设备、账号、组织、环境/内核代次及并发继续隔离。准备、readiness、切换与业务共用这一入口。
- `NativeTlsSlot::prepare(deadline: Instant)`复用后台warm并等待同采集代次结束；新Worker初始化和复用checkout交接最多等待2秒，服从更早的请求/准备截止。Worker在等待前登记采集槽，取消时Drop关闭本代启动；超时撤销代次并记录OBSERVER_START_TIMEOUT。`take`保持即时，失败保持明确缺口，业务最多一次发送。
- 取消后的补热沿原prepare及20秒巡检协调路径；进程就绪、TLS就绪与单请求完整性分别判断。连续快速请求沿同一交接收口，旧PID和迟到代次隔离。
- readiness 只检查本地状态，不启动进程或执行模型。业务 checkout 再原子校验和占用。准备仍由原 prepare 接口完成真实握手并回到同一池；冷池首轮初始化共享代次锁，后续扩容维持原物理上限。
- 启动补偿外，每20秒巡检已启用原生账号，仅解析 `wake=false` 运行绑定。待处理最多128、并行2、按账号去重，轮转扫描避免高 ID 饥饿；失败退避40/80/160/300秒，显式变更提示清除退避。`busy|preparing` 等待后续巡检，`unprepared|failed` 才重新准备。
- 合法平台维护投影 `maintenance/system_maintenance`，准备前返回且不登记活动、不增加失败次数；待恢复账号仍占原有界队列，仅在存在等待项时每秒核对门禁。开放后解除等待，执行前再次核验准入；晚到维护回执继续登记下一轮检查。未知或损坏门禁沿错误路径收口。
- 首次控制面迟到保留5/20/60秒启动补偿。真实故障遇维护后记录中断标记，后续出队和启动补偿均遵守其原 next 截止。维护开放时恢复原失败观察、准备 UUID 和时间，归还冷却账号的队列位置，沿原巡检等待。单纯维护等待继续按一秒周期恢复；显式账号变更清除原退避。
- 发布前重读权威账号与绑定；排他维护、更新门禁、凭据活动关闭和取消继续优先。批量缓存的 ready 超过45秒转 `unknown/check_expired`。`last_preparation` 仅保存历史准备回执；GET 主动检查不承担恢复启动。
- `NativeRuntimeObservation` 字段为 `worker_id:UUID,worker_pid:u32,kernel_generation:Option<UUID>,warm_hit:bool,preparation_wait_ms:u64,checkout_ms:u64,worker_start_ms:Option<u64>,prepared_ms:u64`。毫秒值来自单调时钟。`warm_hit` 表示该 worker 在本次池接收前已经 ready；`worker_start_ms` 仅记录本次 checkout 启动的 worker。
- `prepared_ms` 从已验证信封进入 `submit_validated` 计至实际收到 `cc_prepared`，包含准备锁等待、checkout 与正文组装；`worker_start_ms` 包含于 checkout。该段不包含此前网关上传及解码，也不等于最终 TLS 发出或上游首字。原完整提交耗时继续保留，页面不得将重叠字段相加。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 成功显式选择 active/native293 / 保存失败或最终停用 | 释放配置门禁后允许唤醒 / 不发显式唤醒 |
| wake=true 且 cancel=true | 400，拒绝互斥意图 |
| 身份改变、进程退出、EOF 或迟到帧 | 原 ready 失效，后台按当前身份恢复；业务保留原截止与单次提交 |
| 正在初始化或全忙 | preparing 或 busy，保持原并发与物理上限 |
| 平台门禁合法 blocked / 开放 | maintenance/system_maintenance 且零新准备 / 一秒周期解除等待，仍核对原故障冷却 |
| 维护前已有真实故障 / 门禁损坏 | 保留原次数、截止及失败观察 / 明确错误且拒绝新工作 |
| TLS探针启动失败、未配置或原截止先到 | 保留受控缺口；超时撤销该代采集，业务沿原截止至多一次发送，过期零发送 |
| 错误绑定、过期信封、证据禁用或平台不支持 | 沿私有通道拒绝，模型零发送 |
| 诊断 PID 为0、UUID非法或计时关系越界 | 丢弃损坏观察，保持观察缺口可见；计时关系允许2毫秒取整偏差 |
| `preparation_wait_ms + checkout_ms > prepared_ms + 2` 或 `worker_start_ms > checkout_ms + 2` | 原生观察校验失败 |

### 5. Scenarios and Examples

- 正常：停止的旧布局账号成功保存原生选择，门禁释放后后台唤醒并做零模型握手。边界：同值重存及显式重试进入同一去重队列。错误用法：让列表 GET 自动唤醒休眠环境。正确处理：普通检查仍为 wake=false，仅保存和 `wake=true` 重试赋予唤醒意图。

- 正常：准备得到 PID 123，业务到达前该 worker 已 ready，首次业务记录 `worker_pid=123,warm_hit=true,worker_start_ms=null`。准备与巡检的模型 POST 增量为0。
- 边界：慢流取消后先退休原PID，再以原零模型prepare补热，新PID完成探针准备后交接；连续下一请求同样等待有界准备。准备与业务竞争时，业务记录实际等待；凭据轮换后旧忙进程自然收口，新身份单独建立可接单进程。进程故障恢复包含巡检及启动时间。
- 错误用法：用上次准备成功回执显示持续就绪，或把 `prepared_ms` 当作端到端首字延迟。正确处理：核对实时身份、活性及检查时间，并分别显示原始阶段口径。

- 正常：维护结束后无故障历史的账号及时准备，已有故障的账号继续原冷却。错误用法：把 blocked 计为准备失败，或开放时清空真实故障退避。正确处理：维护等待和真实故障分别保存，恢复原故障归属与截止。

### 6. Tests Required

- 账号更新路由测试核对两个成功出口的 active/native293 条件、门禁已释放、保存失败零唤醒。隔离协调器测试核对维护期间零唤醒、开放后准备、受控预算失败、显式重试和取消后普通检查保持只读。
- `native_real_gateway` 在 `CCRB_TEST_EXPLICIT_WAKE=1` 下，从 sleeping 开始显式唤醒真实二进制；断言准备模型计数增量0、首个业务请求复用准备 PID。

- `maintenance_waits_without_failure_and_reopens_promptly`：隔离进程核对维护期间零活动、无故障一秒恢复、坏门禁拒绝、首次启动补偿、真实故障遇维护后调用次数与原准备 ID 保持、显式变更恢复。

- `native_tls_observer`：慢探针交接、原截止超时、关闭唤醒、迟到代次、未配置及替换PID。`CCRB_TEST_TLS_ONLY=1`覆盖六worker并发、慢流取消、同身份补热和连续两次请求；实际模拟请求9次、完整TLS实体与独立接收器一致、准备模型增量0。
- `native_real_binary`：当前/错误身份、真实61秒等待与可控1800/14400秒空闲年龄、同 PID 首次复用、冷暖相同正文与资源对照、并发上限及取消退役；长空闲年龄与实际等待分别标注。
- `native_real_gateway`：终止预热进程后周期恢复为新 PID，恢复模型计数增量0；业务诊断持久化真实 PID、暖命中与启动字段，凭据轮换隔离。
- `native_real_gateway`另核候选激活/回滚后首次补写quota_identity保持预热PID；设置强制1h经真实SettingsStore和能力声明到达回环出站。`stream_error`及流日志测试覆盖截断、超时、EOF、Drop、秘密过滤与关联字段。
- 诊断与历史记录单测覆盖缺字段、非法 PID/UUID 和计时越界；前端构建及合成浏览器覆盖历史未观测、实际暖命中与阶段口径。

## Scenario: AGY 跨模型进程复用与 CRIU 启动

### 1. Scope / Trigger

- 修改 AGY 的已授权模型提交、工作进程选择、CRIU 模板补位、请求详情或运行环境账号名称时适用。账号和内部传输的现有归属校验见 [AGY账号运行环境与Gemini业务接入](../../orchestrator/backend/account-runtime-v3.md#scenario-agy账号运行环境与gemini业务接入)。

### 2. Signatures

- 网关以 `AgySubmission.model: String` 和 `native_model: AgyModelId` 传递同一次已核验的目录映射。受管监督器在私有 `gemini_request` 信封中传入这对字段。公有 Gemini 正文继续按原字段集合验证。
- `GET /admin/request-diagnostics/:request_id` 的每次尝试可带 `runtime.start_source: "exec" | "criu_restore"`。字段缺省代表未观测。沿用现有运行观察和持久化结构。
- 编排的 `GET /api/environments` 可返回 `gateway_account_name: string | null`。反重力环境从 `GET /admin/accounts?platform=antigravity` 分页查询后按 `gateway_account_id` 投影名称。

### 3. Contracts

- 每个账号和环境的监督器按凭据代次、AT 摘要、代理与实际启动采集配置选择工作进程。池内优先选择热进程。作业自身冻结原生执行 ID，并用于 `StartCascade.requestedModel`、`plannerConfig.planModel` 和历史步骤的模型字段。原工具结果沿原作业身份回填。
- 每个账号保留一个最近使用且仍有效的空闲热进程。额外热进程空闲 120 秒后回收。凭据过期、换代或进程退出时回收对应空闲资源。停放的模板保留到凭据过期、换代、环境变更或退役。模板与业务共用物理池上限。恢复交接释放模板名额，原控制连接继续负责恢复进程的退出清理。监督器清除已消费标记，并在原请求截止与池容量内补位。
- `warm_hit` 表示此次请求入池前进程已就绪。恢复及失败回退计入 `checkout_ms`，首次启动或恢复到就绪的阶段计入 `worker_start_ms`。环境 `last_start_source` 记录当前凭据代次最近的实际扩容来源。热命中保持该记录。
- `restore.state` 依据监督器的实际状态表示等待模板、准备中、模板就绪或不可用。保存与恢复失败沿可见的白名单阶段和原因，普通回退继续使用原截止。
- 运行环境卡片和详情优先展示 `gateway_account_name`。网关名称缺失、平台或绑定不匹配、查询失败时使用环境原名。账号编号和环境归属沿原字段读取。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 模型字段缺失或超出可信目录映射形状 | 受管私有请求在调用原生 RPC 前拒绝 |
| 旧独立内核的启动配置提供固定模型 | 旧信封可省略 `native_model`，采用固定执行 ID |
| 模板换代、过期或进程已退出 | 模板失去可用状态，业务凭当前已准入凭据获取进程 |
| 保存或恢复失败 | 记录受控失败，普通回退沿原截止，模型至多发送一次 |
| 诊断缺来源或来源非法 | 缺省保留其余已核验字段，非法值拒绝该进程观察 |

### 5. Scenarios and Examples

- 同一账号收到 A、B、A 三次请求。热进程的 PID 可保持一致，每次 RPC 使用对应的原生型号。
- 连续两批并发的间隔少于 120 秒时可复用额外热进程。空闲超时后保留最近使用的有效热进程，最后一个热进程可在 300 秒后继续接单。
- 容量为 1 时，恢复进程占住唯一名额，后续准备在空位可用时继续。容量允许时，原恢复进程在线期间可补下一份模板。
- 若将 `warm_hit=true` 计为普通启动，统计会把已有进程重复算作扩容。按 `warm_hit` 判断复用，按 `start_source` 展示该进程的启动来源。

### 6. Tests Required

- `test_agy_supervisor` 核对跨模型复用、额外进程的 120 秒边界、基础热进程与快照寿命、凭据换代、满槽和单次回退。固定配置与历史引用由 `test_agy_runtime` 覆盖。
- `verify_agy_native_loopback.py --shared-models` 检查真实网关的目录映射、TLS 回环出站模型、同 PID 和热命中。Linux 6.1 隔离 OCI 验证同 PID 恢复、第二份模板保存和保存或恢复失败时的单次模型发送。
- `keeps_verified_runtime_start_source` 验证实际 PID 与来源持久化、历史缺省及非法值拒绝。浏览器核对性能页的 CRIU 恢复、普通启动和热命中。
- `test_environment_summary` 核对分页平台、账号 ID、环境原名和网关失败。 `verify_agy_environment_ui.py` 验证浏览器中的反重力账号名称、详情和原账号编号。

## Gateway 热路径规则

`GatewayService::handle_request` / `handle_request_inner` 是最高风险路径。修改前必须明确：

- 请求是否应在账号选择前拦截，例如 assistant prefill、warmup、Auto Mode classifier、非流探针缓存。
- 请求是否会消耗账号并发/RPM；粘性会话下不能因为 RPM 超限随意切号破坏缓存。
- 请求体是否被读取、解压、改写或缓存；读取后转发必须使用最终 body。
- Claude Code 请求改写必须在 CCH 和 `cc_version` 重新计算前完成。
- 上游非成功响应如果要重试，必须保留原有错误体兼容性和敏感信息边界。
- SSE 流式响应只能插入明确允许的 keepalive/comment，不要重排上游 chunk。

## Scenario: Gateway 压缩请求编解码

### 1. Scope / Trigger

- Trigger：修改通用 Gateway／count_tokens 入站读体、Content-Encoding、请求正文改写与发送、signature／认证／换号重试时适用。
- 通用转发包含 Messages、event_logging 及既有其它 JSON／非 JSON 路径；不据编码新增端点、放宽 v3 路径许可或改变各端点正文校验。响应编解码与保活沿用独立链路。

### 2. Signatures

- 请求专用模块：`service/request_body_codec.rs`；`REQUEST_BODY_LIMIT: usize = 10 * 1024 * 1024`。
- `RequestBodyEncoding` 实现 Clone／Default；`from_headers(&HeaderMap) -> Result<Self, RequestBodyCodecError>`、`is_encoded(&self) -> bool`、`content_encoding(&self) -> Option<String>`。
- async `decode(&self, body: Bytes) -> Result<Bytes, RequestBodyCodecError>`；async `encode<'a>(&self, body: &'a [u8]) -> Result<Cow<'a, [u8]>, RequestBodyCodecError>`。
- `RequestBodyCodecError` 为无字段分类：`InvalidEncoding`／`UnsupportedEncoding`／`TooLarge`／`InvalidBody`／`Internal`；Gateway 的 `request_body_codec_error_response` 映射为 Anthropic error object。
- 普通 `forward_request`、`forward_count_tokens_request` 与 `maybe_retry_signature_error` 接收同一冻结的 `&RequestBodyEncoding`；`request_headers_for_encoding(&HashMap<String, String>, &RequestBodyEncoding) -> HashMap<String, String>` 清理出站传输头。没有新 setting、环境变量、依赖、数据库或 bridge 字段。

### 3. Contracts

- Router API token 鉴权、count_tokens POST 检查和 Gateway 原始 UA 准入／画像快照保持既有优先级；编码解析和解码必须先于正文策略、账号选择、slot／RPM、Session 池、Hello 及自动遥测。
- 编码源是原始 `HeaderMap::get_all(Content-Encoding)`，不使用有损的 `extract_headers` 结果。按字段顺序及逗号列表收集，仅去 SP／HTAB，完整 ASCII token 大小写无关；容忍空项／identity，累计最多 32 个列表片段、4 个实际编码层。先验证完整声明，再逆序解码；出站省略空项／identity、小写化并保留有效顺序和 x-gzip 别名。
- 支持 gzip／x-gzip、zlib／raw-deflate 兼容、标准 br、zstd。原始字节及每层解码结果各不超过 10 MiB；标准 br 不接 large-window 扩展，zstd 首次读取前设 `window_log_max(24)`，后续 frame 同样受 16 MiB 窗口限制。窗口和输出上限不是总内存或可取消 CPU 时限。
- gzip 必须完整校验所有 member 的 CRC／ISIZE；deflate 必须 StreamEnd 且耗尽输入，zlib 格式失败才尝试严格 raw，超限不回退；br 必须严格结束且耗尽输入；zstd 支持完整多 frame／skippable frame。恰好上限仍读取并验证结尾，不能只取第一 member、宽松 EOF 或前 10 MiB。请求不复用宽松响应 helper。
- 解码后的原始逻辑字节用于客户端识别、策略、真实 Session、调度和缓存。现有身份、根键清理、池映射、有限 Session 头对齐及最终 CCH 的顺序保持；count_tokens 仍严格验证 JSON object／model，通用非 JSON 继续按原规则处理，不新增全局 schema 校验。
- 实际 codec 工作进入 blocking worker；无有效编码的 decode 保留原 Bytes，encode 借用原字节，不嗅探 magic、不根据 Accept-Encoding、UA 或画像版本主动压缩。无编码读体／非法 JSON 的原状态及错误形状保留。
- CCH 完成后，每次真正发送前按有效链正序重编码。gzip 容器可以重建，deflate 统一标准 zlib；不承诺原压缩字节、member 数量或容器参数相同。编码结果容许容器膨胀超过入站 10 MiB 读取上限，所有 encoder 完整成功后才提交。
- 出站头副本移除 Content-Length／Transfer-Encoding／Content-Encoding 的全部大小写变体，再写入唯一规范 Content-Encoding；无编码不写该头。长度由现有 transport 依据最终 bytes 自动生成，保留既有 HTTP/1 头名机制和画像顺序，不用未经抓包的新版头序替换。
- 诊断、日志、usage、缓存与 signature repair 持续使用逻辑正文；冻结编码链贯穿首次、401、signature 各阶段及换号发送，每次编码当前正文，不能复用首包压缩体。缓存不按压缩容器分裂，不新增上游 400／415 后改明文的回退重试。
- 入站拒绝没有账号相关副作用或上游请求。发送阶段本地编码失败只保证本次业务请求不提交，不回滚此前已有 admission／Hello／自动遥测。PreparedRequest 与 v3 sender 继续传最终原始 bytes，既有 origin／路径许可及内部接收上限不变。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 无编码／合理空列表／identity；仅 Accept-Encoding | 保留原业务及读体路径，不推断或新增压缩 |
| 已支持编码、重复头、有序叠加 | 解码后执行业务，按同一有效链发送 |
| 非法 token／不可转字符串／超过 32 片段 | 400 `invalid_request_error` |
| 未知合法编码／超过 4 个实际层 | 415 `invalid_request_error` |
| 损坏、截断、尾随内容、超支持窗口或扩展 | 400 `invalid_request_error`，不使用部分解码结果 |
| 压缩原字节或任一层结果超过 10 MiB | 413 `invalid_request_error`，先于账号副作用 |
| worker／本地编码异常 | 500 `api_error`，本次业务请求不提交 |
| 合法编码的非 JSON | 通用转发沿用原字节语义，count_tokens 保留原严格拒绝 |
| 上游返回 415 | 沿用原上游错误，不增加明文回退发送 |

错误体不回显原始编码值、正文、凭据或库内部错误；不靠不稳定库错误字符串细分窗口失败。

### 5. Scenarios and Examples

- 正常：入站 `Content-Encoding: gzip, br`，先 br 再 gzip 解码，完成身份与 CCH 后先 gzip 再 br 编码；最终长度对应双层压缩字节。
- 边界：raw-deflate 入站在 10 MiB 内，改写后按标准 zlib 包装略超 10 MiB，仍发送并使用实际长度；空项／identity 不增加压缩层。
- 错误：在 signature 修复前压缩 `final_body`，随后 JSON 修复失效；或重建头丢掉 Content-Encoding 后继续发旧压缩体。
- 正确：业务始终处理逻辑正文，在每次网络提交边界单独生成匹配的 wire body 和头；真实上游编码支持由响应决定，不用本地合成成功冒充真实推理。

### 6. Tests Required

- `request_body_codec::tests`：完整 token／多值／32 片段与 4 层边界、无编码存储保留、各 codec 与链顺序、raw 转标准 zlib、截断／尾随、每段校验、多 member／frame、窗口、原字节及各层精确大小、实际编码膨胀。
- `gateway_compressed_request_messages_match_plaintext`、`gateway_compressed_request_other_endpoints_match_plaintext`：实际 Gateway 比较 CC／API、stream 三态、过滤开关、各入口和编码的最终逻辑字节、身份／Session／CCH；通用二进制路径为合成样例。
- `gateway_compressed_request_rejections_have_no_account_side_effects`、`gateway_compressed_request_read_errors_and_count_json_boundaries`、`gateway_compressed_request_router_authentication_precedes_decoding`：实际入口错误状态／形状、零账号副作用及上游请求、鉴权／方法优先级和原无编码行为。
- `gateway_compressed_request_tcp_headers_and_near_limit`：真实 TCP 验证唯一 CE／CL、无旧 TE、实际 wire 长度与近上限膨胀；不以内部 Map 断言代替线上字节。
- `gateway_compressed_request_auth_and_account_retries`、`gateway_compressed_request_signature_stages_reencode_current_body`、`gateway_compressed_request_does_not_retry_unsupported_upstream_encoding`：401 双入口、429 换号、两阶段修复的本次正文及 CCH、不新增编码回退。
- `gateway_compressed_request_cache_and_local_intercepts_are_equivalent`：不同编码共用逻辑缓存、cache hit 无 attempt、本地 prefill／warmup／classifier 等价且不多发包。
- Rust 格式／全量／CCH 与差异检查通过；复用既有 transport 原始字节／证书／主机名回归。新增测试只证明本地合成 Gateway／TCP 与既有 transport 合同，不宣称新原生抓包、生产 v3 或真实账号推理验证。

## Scenario: 响应观察的 SSE 与有界解码

### 1. Scope / Trigger

- Trigger：修改 `UsageCapture`、`ResponseBodyDecoder`、SSE 用量解析、压缩响应观察或诊断摘要时适用。
- 观察器不改变客户端收到的响应字节、响应头和重试；已完成诊断可按下方 v3 合同回灌健康与首输出延迟。

### 2. Signatures

```rust
UsageCapture::observe(&mut self, bytes: &[u8])
UsageCapture::configure_codings(&mut self, codings: &[String])
UsageCapture::observation(self, complete: bool) -> MessageObservation
ResponseBodyDecoder<W>::configure(&mut self, codings: &[String])
ResponseBodyDecoder<W>::finish(&mut self) -> Result<(), ResponseDecodeError>
```

### 3. Contracts

- SSE 识别前的空格、制表、CR、LF 逐行消费，不把任意长度的初始空白存入单行缓冲；JSON 观察仍按原始字节总长执行 `USAGE_BUFFER_LIMIT`。
- 初始空白后的首个非空白字节决定 SSE／JSON；JSON 前出现非 JSON 空白或控制字节时标记 `invalid_payload`，不把正文强行当作合法 JSON。
- SSE 的单行和组合事件仍各受 `USAGE_BUFFER_LIMIT` 限制；事件只有在空行派发，多 `data:` 行按 LF 拼接。压缩链先增量解码，再使用同一解析器，不因压缩率改变完整性结论。
- 编码层、CRC、尾随字节、窗口和结束帧必须完整验证；观察失败只标记 `partial`／`observation_error`，不得把缺失数据记成精确零用量，也不得阻断响应转发。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|---|---|
| 初始大量空行后为合法 SSE | 明文、gzip、br、zstd 与不同分块得到相同 usage，`partial=false` |
| 初始空白后 JSON 总字节超过上限 | `sampling_limit`，不解析部分 JSON |
| JSON 前出现非法控制字节 | `invalid_payload`，不宣称完整用量 |
| SSE 单行／事件超过上限 | 丢弃当前行／事件，后续事件仍可观察，最终标记 `partial` |
| 压缩流截断、校验失败或缺结束帧 | 保留已观察摘要并标记部分，响应原字节继续透传 |

### 5. Scenarios and Examples

- 正常：首帧前有较长合法空行，明文与压缩响应都能观察到 `input_tokens`、`output_tokens` 和 `message_stop`。
- 边界：超大事件之后仍有合法事件，超大事件不污染后续事件，但整次观察保留部分标记。
- 错误用法：把初始空白全部放进 JSON 缓冲，导致明文触发上限而 gzip 因压缩率较小正常。
- 正确处理：初始空白按 SSE 行消费，JSON 另计原始字节预算，所有编码共享同一完整性状态机。

### 6. Tests Required

- `long_initial_blank_lines_preserve_usage_across_codings_and_chunks`：LF／CRLF／CR、是否有 `event:`、明文及所有支持编码、1 字节／中等／整包分块，断言 tokens、`partial` 和错误均一致。
- `initial_whitespace_preserves_json_limit_and_validation`：恰好上限、超过上限、非法控制前缀及全空白响应，断言不使用部分 JSON。
- 响应解码器继续覆盖多 member／frame、截断、尾随和窗口边界；完整 `cargo test -- --test-threads=4`、`cargo fmt --check` 与 `git diff --check` 必须通过。


## Scenario: 账号级上游 session 池

### 1. Scope / Trigger

- Trigger：修改账号级 upstream session pool、Claude Code `/v1/messages` session 改写、event_logging 遥测 session、stateful message cache、Redis/Memory cache 状态或 Accounts 管理 UI 时适用。
- 目标：允许多个真实下游 Claude Code session 同时进入 gateway，但限制同一账号在一个活跃 TTL 窗口内发往上游的 distinct `metadata.user_id.session_id` 数量。

### 2. Signatures

- 账号字段：`Account.upstream_session_pool_enabled: bool`、`upstream_session_pool_size: i32`、`upstream_session_ttl_minutes: i32`、`upstream_session_refresh_policy: String`。
- 账号默认值：默认关闭；推荐容量 `3`；默认 TTL `60` 分钟；默认策略 `mapped_request`。
- 校验范围：容量允许 `0` 或 `1..=20`，`0` 等价关闭；TTL 允许 `5..=1440`；策略只允许 `mapped_request` / `owner_only`。
- cache 入口：`CacheStore::resolve_upstream_session_pool(account_id, real_session_id, pool_size, ttl, refresh_policy, allow_insert).await -> Result<UpstreamSessionPoolResolve, AppError>`。
- 状态入口：`CacheStore::get_upstream_session_pool_status(account_id, pool_size, ttl).await -> Result<UpstreamSessionPoolStatus, AppError>`。
- Gateway 入口：`GatewayService::build_upstream_session_rewrite(account, path, body_map, client_type).await -> UpstreamSessionRewrite`。
- Rewriter 入口：`Rewriter::rewrite_body_with_stateful_completion(..., upstream_session_rewrite, ...)`。
- 管理端字段：`upstream_session_pool_active_count`、`upstream_session_pool_capacity`、`upstream_session_pool_oldest_last_seen_ms`、`upstream_session_pool_newest_last_seen_ms`。

### 3. Contracts

- 上游 session 池只影响最终发往 Anthropic 的 Claude Code `/v1/messages` body/header；账号选择、sticky、RPM admission、队列和内部日志仍必须使用真实下游 session。
- 池成员必须来自真实进入 gateway 的 Claude Code session id，不能随机预生成，也不能按时间窗口合成。
- Gateway 必须先完成账号选择、并发槽位和 RPM admission，再解析 upstream session pool；解析结果进入 body rewrite，且必须早于 CCH、`cc_version` 和 `X-Claude-Code-Session-Id` 生成。
- Redis 实现必须用 Lua 或等价原子机制覆盖懒清理、LRU 容量收敛、成员判断、显式映射校验、入池和 TTL 刷新；MemoryStore 必须用 mutex 保持同等语义。
- 首次池满映射按活跃成员稳定排序后用 `stable_upstream_session_hash(real_session_id) % active_count` 选择，并保存 `real_session_id -> upstream_session_id` 显式映射；只要目标仍活跃，成员集合变化不能让同一真实 session 重新取模。
- 容量缩小时必须按 `(last_seen, session_id)` 从旧到新淘汰，下一次 resolve/status 后活跃成员数不得超过当前容量；指向过期或被淘汰目标的映射必须立即逻辑失效。
- `mapped_request` 会刷新被借用 upstream session 的 `last_seen`；`owner_only` 只在真实 session 自己是池成员且发起请求时刷新。
- Redis 或 cache 解析异常必须失败开放：记录脱敏 warn，保持真实 session 发上游，不阻断用户请求。
- 本地 stateful message cache key 必须优先使用真实 session；共享 upstream session 不能让多个真实 session 共用本地 cache 状态。
- 池映射专用分支只在 `real_session_id != upstream_session_id`、即 body session 确实改变时覆盖或补入 `X-Claude-Code-Session-Id`。随后普通 CC 消息可按[有限对齐规则](#scenario-普通-cc-messages-session-header-对齐)更新已有非空头；探针和异常目标仍有明确豁免，不能无条件规范化 admitted/owner-hit。
- 自动 message telemetry 必须从改写后的最终 body 构造 context，使 request/result event 与实际覆盖后的 body/header 使用同一 upstream session。
- 客户端原生 event_logging 只能只读复用已保存且目标仍活跃的 session 映射，`allow_insert=false`，不得创建成员、刷新 TTL 或按当前成员集合临时重新取模；找不到映射、池为空或 cache 出错时失败开放。
- 日志只能输出短 session hash、账号 id、容量、动作和原因，不得输出完整 `metadata.user_id`、完整 session id 或完整请求体。
- Accounts UI 必须同步 `apps/web/src/api.ts` 类型和 `Accounts.vue` 表单/列表展示；保存前可做基础校验，但以后端校验为最终真相。

### 4. Validation & Error Matrix

| 条件 | 期望行为 |
|------|----------|
| 老账号或新账号默认配置 | `upstream_session_pool_enabled=false`，上游 session 保持旧行为 |
| `upstream_session_pool_size=0` | 后端规范化为关闭，等价 `enabled=false` |
| 容量小于 0 或大于 20 | 管理 API 返回 `BadRequest` |
| TTL 小于 5 或大于 1440 | 管理 API 返回 `BadRequest` |
| 刷新策略未知 | 管理 API 返回 `BadRequest` |
| 池未满且主请求带真实 session | 真实 session 入池并作为 upstream session |
| 池已满且新真实 session 请求 | 请求继续，body/header 复用池内已有 upstream session |
| 容量从 5 调小到 2 | 下一次 resolve/status 淘汰最久未活跃成员，活跃数收敛到 2 |
| 已保存映射的其他成员加入或过期 | 目标仍活跃时继续复用原 upstream session，不重新取模 |
| 已保存映射目标过期或被淘汰 | 旧映射失效；主请求可重新映射，event_logging 只读 lookup 返回无映射 |
| Redis pool 解析失败 | 失败开放，记录脱敏 warn，使用真实 session 发上游 |
| event_logging 只有根级 session 字段且无 `events` 数组 | 递归尝试只读映射，不能因为结构不标准而直接绕过 |
| event_logging session 无映射或池为空 | 保持现有遥测改写行为，不创建池成员，不阻断请求 |

### 5. Good/Base/Bad Cases

- Good：账号容量为 3，前 3 个真实 session 进入后成为池成员，第 4 个真实 session 稳定映射到其中一个成员；sticky、RPM 和队列仍按第 4 个真实 session 计算。
- Good：第 4 个真实 session 的显式映射目标仍活跃时，即使其他池成员发生增删，它仍复用原 upstream session；容量缩小时优先淘汰 `last_seen` 最旧成员。
- Good：`mapped_request` 下借用请求会延长被借用 upstream session 的 TTL，减少上游会话边界变动；`owner_only` 下借用请求不刷新 TTL，便于池自然轮换。
- Good：stateful cache 日志只输出短 hash，cache key 内部用真实 session 隔离，不把共享 upstream session 暴露到日志。
- Base：功能关闭或容量为 0 时，rewriter 仍只改写 `device_id` / `account_uuid`，保留原始 session 语义。
- Bad：在账号选择或 RPM admission 前用 upstream session 替换真实 session，会把多个下游 session 合并到同一个 sticky/RPM 维度。
- Bad：event_logging 映射时使用 `allow_insert=true`，会让没有主请求的遥测 payload 扩大上游 session 池。
- Bad：event_logging 没有显式映射时按当前成员重新取模，会让延迟遥测和对应主请求使用不同 upstream session。
- Bad：无条件用 body session 覆盖所有 `/v1/messages` header，会抹平抓包中 warmup probe 的合法特殊行为。
- Bad：stateful cache key 直接从最终 body 取 session，会让多个真实 session 因共享 upstream session 而污染本地 cache 状态。

### 6. Tests Required

- `src/store/memory.rs` 单测覆盖：容量上限、LRU 缩容、显式映射在其他成员变化时稳定、目标失效、只读 lookup 不创建/不刷新/不重哈希、两种刷新策略和 TTL 懒清理。
- Redis Lua 变更需人工核对原子脚本，必要时补集成测试；至少确认并发入池不超容量、缩容后不返回被淘汰目标、只读遥测不写状态。
- Gateway/Rewriter 单测覆盖：JSON/legacy `metadata.user_id.session_id` 改写、池实际改变 session 时的专用补入／覆盖优先级、普通已有头有限对齐及探针／异常目标豁免、自动 telemetry 的最终 body 来源、stateful cache key 使用真实 session、event_logging 递归只读映射和无 `events` 数组路径。
- `src/store/account_store.rs` / integration 测试覆盖账号字段 create/update/list round trip。
- 管理端变更必须跑 `cd services/gateway/web && npm run build`，确认 TypeScript 类型和 `Accounts.vue` 同步。
- 完整检查至少跑 `cd services/gateway && cargo fmt --check && cargo test`；协议改写触碰 CCH 顺序时额外跑 `cargo test cch`。

### 7. Wrong vs Correct

#### Wrong

```rust
let upstream = account_svc
    .resolve_upstream_session_pool(&account, &real_session_id, true)
    .await?;
let session_hash = generate_session_hash(..., upstream.upstream_session_id.as_deref());
account_svc.acquire_account_rpm(&account, sticky, &session_hash).await?;
```

这样会用 upstream session 污染 sticky 和 RPM 维度。

```rust
account_svc
    .resolve_upstream_session_pool(&account, telemetry_session_id, true)
    .await?;
```

这样会让遥测请求创建新的上游池成员。

#### Correct

```rust
let session_hash = generate_session_hash(...); // 真实下游 session
let admission = acquire_account_admission(&account, sticky, &session_hash, timeout, slot_units).await?;
let upstream_rewrite = build_upstream_session_rewrite(&account, path, &body_map, client_type).await;
let (rewritten_body, completion) = rewriter.rewrite_body_with_stateful_completion(
    body,
    path,
    &account,
    client_type,
    env_pt,
    cache_ttl,
    message_cache,
    order_enabled,
    &disabled_thinking,
    &upstream_rewrite,
    sanitizer,
);
```

```rust
account_svc
    .resolve_upstream_session_pool(&account, telemetry_session_id, false)
    .await?;
```

## Scenario: 普通 CC Messages Session header 对齐

### 1. Scope / Trigger

- Trigger：修改普通 CC Messages 出站 Session header、探针豁免或与池映射的先后关系时适用。
- 这是普通 CC 不一致输入的有限一致性规则，不重建 body 身份、设备、账号或会话；无新增 setting、存储状态或重试。

### 2. Signatures

- `is_session_header_alignment_probe(body: &serde_json::Value) -> bool` 使用原始请求体。
- `align_claude_code_session_header(headers: &mut HashMap<String, String>, path: &str, client_type: ClientType, original_body: &serde_json::Value, rewritten_body: &serde_json::Value)` 只修改出站头。
- 最终会话沿用 `extract_session_id_from_body` 的 JSON-string／legacy 合同；既有 `align_mapped_upstream_session_header` 先执行。

### 3. Contracts

- 仅精确 `/v1/messages`、`ClientType::ClaudeCode`、原始 body 不属于豁免探针时进入普通对齐。
- 最终 body 可提取非空白 session、已有规范头 `X-Claude-Code-Session-Id` 非空白且不同、目标可安全且保真表示为 HTTP header 时，以最终 body 为准更新已有头；不补头、不 trim 写回、不新增 UUID 门槛。
- HTTP/1 会去掉头值边缘 SP／HTAB，因此目标 session 前后带这些字符时跳过普通对齐；全空白、LF／CR／NUL 或其它 HeaderValue 拒绝的目标也保留已有头。不要通过改 body 或提取器掩盖不一致。
- 探针四项同时满足才豁免：`max_tokens` 为整数 1、既有 stream 布尔解释不为 true、tools 缺失或为空数组、messages 恰好一条且 role=user。tools=null／异常类型、stream=true 不豁免；不依赖模型名、文本或拦截开关。合法同形业务请求也保守豁免。
- 既有 mapped 专用分支保持补入／覆盖能力，先处理真正的 body session 映射；新增探针或异常目标 gate 不撤销此前映射结果。API 既有规则、count_tokens 和其它路径不扩大。
- 原始 body 仍用于调度、sticky、RPM、并发、池与诊断；最终 body 只作为新增头的目标来源。不得额外 resolve、刷新 TTL、改变 Hello 去重、重序列化正文或增加 CCH 刷新；R2 根键清理开／关不影响嵌套会话来源。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 普通 CC 已有非空头与最终 body 会话不同 | 只改已有头，body 字节不因本规则改变 |
| 原本一致／缺头／空白头／无可用 body 会话 | 保持既有头状态，不补会话 |
| 非空目标前后 SP／HTAB 或不安全控制字符 | 跳过新增对齐，原 body 与原已有头保留 |
| 原始单 token 豁免探针，无实际映射 | 保留允许的差异 |
| 池已实际改变 body session，包括缺头探针 | 保留旧 mapped 补入／覆盖优先级 |
| 非精确路径／API | 新 helper 不改写，沿用各自既有规则 |

### 5. Scenarios and Examples

- 正常：原 header 为 A、最终 body 会话为 B，普通请求仅将已有 header 设为 B；不改变设备或 billing/CCH。
- 边界：173 最小 warmup 的差异继续保留；池将该探针实际映射到 C 时，旧 mapped 分支仍让 body/header 使用 C。
- 错误：将带前后空格的 body session 直接写进 HTTP 头，接收端会剥离空白，仍不一致；或先 trim 再改 body，扩大身份与 CCH 改写。
- 正确：对不能保真为头值的目标跳过新增普通分支；正常不带边缘空白的非 UUID 会话继续按原提取合同对齐。

### 6. Tests Required

- `gateway_session_header_alignment_ordinary_messages`：实际 Gateway 覆盖 JSON／legacy、三种 stream、清理开／关、头名大小写和原本一致／不一致；最终 CCH 保持有效，仅头不同时 body 字节相同。
- `gateway_session_header_alignment_input_and_path_boundaries`：缺失／空白／损坏会话、LF／CR／NUL、缺头／空头、API 补头和其它路径；断言实际上游最终头与 body。
- `gateway_session_header_alignment_probe_shape`：173／280 合成探针及 stream、tools、消息数、token 类型等反例；不能只测试 helper 或扩大 detector。
- `gateway_session_header_alignment_pool_precedence`：池关闭、admitted、owner_hit、mapped 与失败开放；resolve 次数、owner_only TTL、真实 sticky／诊断维度、Hello 去重。
- `gateway_session_header_alignment_preserves_sessions_with_edge_ows`：JSON／legacy × 清理开／关 × 前后 SP／HTAB，保留原 body 与已有头；正常及内部空白正例仍进入对齐。
- Rust 格式、全量与 CCH 回归通过；仅使用合成 loopback，不把它称为真实 Anthropic 推理或新抓包验证。

## Scenario: Gateway 账号槽位与 RPM Admission 顺序

本节固定分钟 RPM 的规则适用于非 v3 路径；v3 的精确 `/v1/messages` 使用下方「v3 API 稳定会话、智能准入与平滑发送」合同，继续保留加权槽位和 FIFO。

### 1. Scope / Trigger

- Trigger：修改 `GatewayService::handle_request_inner` 中账号选择、账号级 FIFO 队列、请求槽位权重、RPM admission、429 重试或本地拦截顺序时适用。
- 目标：RPM 计数表示“已经获得账号执行槽位、即将进入上游转发链路”的请求数，而不是“进入本地等待队列”的请求数；账号并发槽位使用标准槽位语义展示，内部用整数单位支持 Haiku 半槽。

### 2. Signatures

- 槽位入口：`AccountService::get_or_create_queue(account.id, account.concurrency).await`
- 请求权重：`request_slot_units(path, body) -> u32`；`/v1/messages` 且 `body.model` 小写包含 `haiku` 时返回 `HAIKU_REQUEST_SLOT_UNITS = 1`，其他真实上游请求返回 `DEFAULT_REQUEST_SLOT_UNITS = 2`
- 等待入口：`AccountQueue::acquire(timeout, slot_units).await -> Result<AccountSlotPermit, QueueWaitError>`
- RPM 入口：`AccountService::acquire_account_rpm(account, sticky, session_hash).await -> Result<(), AppError>`
- RPM 状态：`AccountService::get_account_rpm_status(account).await -> AccountRpmStatus`
- 管理端实时并发字段：`current_concurrency`（标准槽位，可小数）、`current_concurrency_units`、`max_concurrency_units`、`active_requests`、`queued_requests`、`queued_request_units`

### 3. Contracts

- `Account.concurrency` 的外部语义是标准并发槽位数；管理员填 `5` 表示最多 5 个普通请求，而不是内部单位数。
- 内部单位固定为 `1 标准槽 = 2 内部单位`；普通/Opus 请求占 2 单位，Haiku 请求占 1 单位。不要把 `concurrency` 存成或显示成翻倍值。
- Gateway 正常上游路径必须先计算 `slot_units` 并获得 `AccountSlotPermit`，再调用 `acquire_account_rpm`。
- 本地拦截路径（assistant prefill、warmup、Auto Mode classifier、telemetry 假响应等）必须在账号槽位获取前返回，不得新增并发槽位消耗。
- 处于 `AccountQueue::acquire(...)` 等待阶段的请求不得递增 RPM。
- 等待队列容量仍按请求数计，保持 `2 × concurrency` 个等待请求；不要按半槽权重扩大为 `4 × concurrency`。
- `AccountQueue` 必须使用 `Semaphore::acquire_many_owned(slot_units)` 保持 Tokio semaphore FIFO 公平性。若队首普通请求需要 2 单位而当前只剩 1 单位，后续 Haiku 请求不得绕过队首。
- 调度的满载判断和 `concurrency_pct` 必须按内部单位计算：`(active_units + waiting_units) / max_units × 100`。
- `QueueWaitError::QueueFull` / `QueueWaitError::Timeout` / `QueueWaitError::Closed` 发生时，该账号 RPM 不得变化。
- 非粘性请求拿到槽位后若 RPM 饱和并返回 `AppError::ServiceUnavailable`，必须释放当前账号槽位并排除该账号后重新选号。
- 粘性请求拿到槽位后若 RPM 饱和，仍按 `acquire_account_rpm` 的等待/本地 429 语义处理，不得随意切号。

### 4. Validation & Error Matrix

| 条件 | 期望行为 |
|------|----------|
| 普通请求进入真实上游路径 | 占 2 内部单位，管理端标准槽位 +1 |
| Haiku `/v1/messages` 进入真实上游路径 | 占 1 内部单位，管理端标准槽位 +0.5 |
| 排队等待槽位 | `queued_requests` 和 `queued_request_units` 可增加，RPM `current` 不增加 |
| 队首普通请求等待 2 单位且只剩 1 单位 | 后续 Haiku 不插队，直到队首请求获得 2 单位或退出 |
| 成功获得槽位且 RPM 未满 | RPM `current += 1`，permit 交给 `SlotReleaseGuard` / `SlotGuardBody` |
| 队列满 | 返回/换号前不消耗 RPM |
| 槽位等待超时 | 返回/换号前不消耗 RPM |
| 管理员缩小并发 | 已有请求不被中断；后台 shrinker 在 permit 释放后吞掉多余内部单位 |
| 非粘性 RPM 饱和 | 释放已获槽位，排除账号并重新选号 |
| 粘性 RPM 饱和 | 保持粘性账号等待；超时后返回本地 429 |

### 5. Good/Base/Bad Cases

- Good：请求 A 占满账号槽位，请求 B 在 FIFO 队列等待；B 等待期间 RPM 不变，A 释放后 B 获得槽位并通过 RPM admission 才递增。
- Good：账号并发为 5 时内部容量为 10；9 个 Haiku 占 9 单位后，新 Opus/普通请求需要 2 单位，必须等待。
- Base：`rpm_limit = 0` 时保持不限 RPM，槽位顺序仍由 `AccountQueue` 控制。
- Bad：把 `slots` 容量直接改成 `2 × concurrency` 却仍让每个请求只 acquire 1 个 permit，会让所有请求都变成半槽。
- Bad：在 `queue.acquire(...)` 前调用 `acquire_account_rpm(...)`，会让排队中或最终超时/队列满的请求提前消耗 RPM。

### 6. Tests Required

- 覆盖等待中请求不增加 `get_account_rpm_status(...).current`。
- 覆盖等待请求获得槽位并通过 RPM admission 后才递增。
- 覆盖 `QueueFull` 和 `Timeout` 不消耗 RPM。
- 覆盖普通请求占 2 单位、两个 Haiku 共享 1 个标准槽位、混合请求按内部单位满载。
- 覆盖队首普通请求需要 2 单位时，后续 Haiku 不绕过队首请求。
- 覆盖等待队列容量仍按请求数限制，不因 Haiku 半槽放大。
- 覆盖缩容不强杀已有请求，并在释放后收敛到新的内部单位容量。
- 覆盖管理 API 返回标准槽位和内部单位字段，前端类型与展示同步。
- 保留非粘性 RPM 饱和换号、粘性 RPM 饱和等待/拒绝、429 后释放槽位的回归测试。

### 7. Wrong vs Correct

#### Wrong

```rust
account_svc.acquire_account_rpm(&account, sticky, &session_hash).await?;
let permit = queue
    .acquire(SLOT_WAIT_TIMEOUT, DEFAULT_REQUEST_SLOT_UNITS)
    .await?;
```

```rust
let slots = Semaphore::new((account.concurrency * SLOT_UNIT_SCALE) as usize);
let permit = slots.acquire_owned().await?;
```

#### Correct

```rust
let slot_units = request_slot_units(&path, &body_map);
let permit = queue.acquire(SLOT_WAIT_TIMEOUT, slot_units).await?;
account_svc.acquire_account_rpm(&account, sticky, &session_hash).await?;
```

```rust
let slots = Semaphore::new((account.concurrency * SLOT_UNIT_SCALE) as usize);
let permit = slots.acquire_many_owned(slot_units).await?;
```

## Scenario: OAuth Usage Scoped 模型窗口

### 1. Scope / Trigger

- Trigger：修改 `service::oauth::fetch_usage`、`GatewayService` 被动用量采集、`AccountService::refresh_usage`、`UsagePollerService`、`apps/web/src/api.ts`、`Accounts.vue` 中 usage 解析或展示时适用。
- 背景：Claude Code 新版 usage API 可能把模型专属周用量放在 `limits[]` 的 scoped 结构里，而不是顶层 `seven_day_<model>` 字段。

### 2. Signatures

- 上游接口：`GET https://api.anthropic.com/api/oauth/usage`
- 后端入口：`service::oauth::fetch_usage(token, proxy_url).await -> Result<serde_json::Value, AppError>`
- 账号刷新：`AccountService::refresh_usage(id).await -> Result<serde_json::Value, AppError>`
- 后台服务：`UsagePollerService::new(account_svc, interval: Duration, enabled: bool)`；`run()` 在 disabled 时直接返回。v3 使用 `UsagePollerService::for_resets(account_svc)`，仅补充已结束周期的观测。
- 被动解析：`gateway::extract_passive_usage(headers) -> Option<serde_json::Value>`
- 被动写入：`AccountService::update_passive_usage(id, partial, UsageObservationKind).await -> Result<(), AppError>`
- 管理端接口：`POST /admin/accounts/:id/usage -> { status: "ok", usage }`
- 前端类型：`UsageData` 包含 `five_hour`、`seven_day`、`seven_day_sonnet`、`seven_day_fable`、`limits`

### 3. Contracts

- `five_hour` / `seven_day` / `seven_day_sonnet` 仍按顶层窗口读取，窗口最少包含 `utilization`，`resets_at` 可为空。
- Fable 周用量必须稳定暴露为 `seven_day_fable`；若上游没有顶层 `seven_day_fable`，从 `limits[]` 中匹配：
  - `kind == "weekly_scoped"` 或 `group == "weekly"`
  - `scope.model.display_name == "Fable"`，或 `scope.model.id` 包含 `fable`
  - `percent` 写入 `utilization`
  - `resets_at` 为字符串时保留，否则写 `null`
- 后端归一化只能补稳定字段，不得删除 `limits`、`spend`、`extra_usage` 等原始字段，方便排查上游变化。
- 前端展示应优先读取稳定字段；为了兼容旧缓存，也可从 `usage_data.limits` 回退提取 Fable。
- Gateway 必须从 Anthropic unified 响应头被动解析 `5h`、`7d` 与 Fable 专属 `7d_oi`；`7d_oi` 归一化为稳定字段 `seven_day_fable`。窗口必须同时具备合法 `utilization` 与未来合理范围内的 `reset`，缺失或异常时不得覆盖已有数据。
- 普通业务请求无论成功或 429 都不得调用 usage API。v3（`V3_RUNTIME_URL.trim()` 非空）后台每 15 秒扫描 active OAuth 账号，仅对普通 5h／7d 旧窗口已到期的账号调用既有 `refresh_usage`，独立于历史 `auto_poll_usage` 开关；从未获取或只有非法额度资料的账号不自动补查。非 v3 保留 active OAuth＋`auto_poll_usage=true` 的定时刷新；管理员手动接口继续可用。
- 重置刷新串行发送，账号间隔 500ms，同账号尝试至少间隔 5 分钟，成功但仍返回旧窗口时也遵守此间隔。发送前重新读取账号状态与窗口，沿用更新维护和凭据归属门禁；被动或手动观测已推进周期后跳过刷新。重试记录仅在进程内保存，删除账号后清理。
- 成功响应、PrimePoller 成功和显式 usage 查询使用 `UsageObservationKind::Allowed`；429 使用按窗口构造的 `RejectedWindows`。窗口 `status=rejected` 时视为拒绝，`status=allowed` 时明确视为允许；缺少明确状态时才用 `surpassed-threshold=true/正数` 或 `utilization >= 1.0` 兜底。旧 reset 已到期、新 reset 已推进，且窗口本身未被拒绝时，若旧值和新值仍处于 97% 以上高位，必须保存新 reset 并把首次新周期 utilization 归零；只有真实拒绝窗口保留高位值。
- 被动与主动写入都必须保留本次观察未包含的窗口和扩展字段，包括 `seven_day_sonnet`、`limits`、`spend`、`extra_usage`。

### 4. Validation & Error Matrix

| 条件 | 期望行为 |
|------|----------|
| `limits` 缺失或不是数组 | 不补 `seven_day_fable`，保留原始 usage |
| `limits` 前置项 `scope: null` | 跳过该项，继续查找后续 scoped 项 |
| Fable scoped 项 `percent` 非数字 | 不补窗口，避免 UI 展示脏值 |
| Fable scoped 项 `resets_at: null` | 窗口保留 `resets_at: null`，前端显示 `—` |
| 顶层已有 `seven_day_fable` 对象 | 保留顶层对象，不用 `limits` 覆盖 |
| 成功响应携带完整 `7d_oi` | 被动写入 `seven_day_fable`，不调用 usage API |
| 429 携带完整 `7d_oi` 且该窗口 `status=rejected` | 按拒绝样本持久化；Fable 耗尽只影响 Fable 模型族 |
| 5h 触发 429，7d/Fable 窗口为 `status=allowed` 且携带跨周期高位值 | 仅 5h 参与限流；7d/Fable 保存新 reset 并将首次 utilization 归零 |
| 旧 99%/100% reset 已到期，成功样本给出新 reset 但仍是高位 | 新 reset 保留，首次 utilization 写 0 |
| 同一新 reset 的后续完整样本 | 按响应头真实值正常更新 |
| 非 v3 且 `auto_poll_usage=false` | 后台 poller 不查询该账号 usage |
| v3 普通窗口有效／从未获取／非法数据，历史开关任意 | 重置扫描不查询 usage |
| v3 active OAuth 普通旧窗口已到期，历史开关任意 | 后台刷新；同账号 5 分钟内跳过重复尝试 |
| 账号已停用／非 OAuth／凭据由本地管理或正在交接 | 跳过目标或由既有归属门禁拒绝上游访问 |
| 管理员手动刷新 / 非 v3 且 `auto_poll_usage=true` | 允许主动查询 usage，结果仍经过 rollover 合并 |
| 上游返回 401/403/429 | 维持现有 `AppError` 分类，不吞错误体 |

### 5. Good/Base/Bad Cases

- Good：usage 先返回 session/weekly all 两个 `scope: null` limit，后返回 Fable scoped limit；解析器跳过前两项并补出 `seven_day_fable`。
- Good：Fable 成功响应带 `7d_oi utilization/reset`，Gateway 收到响应头后异步写入 `seven_day_fable`，整个请求生命周期不访问 usage API。
- Good：旧 7d 为 99% 且 reset 已过期，下一次成功响应把 reset 推到下周但仍回 99%；合并层保存新 reset 并返回 0%，后续同 reset 的真实样本可继续更新。
- Base：非 v3 沿用账号开关轮询；v3 只在普通旧窗口结束后补查，手动查询可用。
- Good：5h 旧窗口到期，后台刷新取得 `utilization: 0, resets_at: null` 后停止补查；调度按真实零用量计算。错误做法是让未知资料触发每轮查询；正确处理是仅刷新 `reset_pending`，失败后等待重试间隔。
- Base：只返回传统 `five_hour` / `seven_day`；保留已有 Fable 数据，不主动补查。
- Bad：直接假设 `limits[0]` 就是 Fable，或遇到第一个 `scope: null` 用 `?` 提前返回，导致真实 Fable 项被漏掉。
- Bad：在 Fable body EOF 或 429 后自动调用 usage API，绕过 `auto_poll_usage` 显式开关。
- Bad：只看新 reset 在未来就相信仍为 99%/100% 的成功样本，会把上一周期用量重新带入新周期。

### 6. Tests Required

- `service::oauth` 单测覆盖：前置 `scope: null` 项、Fable scoped 项、已有顶层 `seven_day_fable` 不覆盖、非 Fable scoped 项忽略。
- `service::gateway` 单测覆盖：5h/7d/7d_oi 完整解析、秒/毫秒 reset、缺失字段、非法数值和异常时间。
- `service::account` 单测覆盖：Allowed rollover 高位清零、已下降值采用、同周期后续更新、RejectedWindows 仅保留明确拒绝窗口高位及未观察字段不丢失。
- `service::gateway` 单测覆盖：429 按窗口 `status` 判定拒绝，显式 `allowed` 优先于高位 utilization，缺少 status 时兼容数值型 `surpassed-threshold`。
- `UsagePollerService` 使用真实 SQLite 账号与本地 TCP 代理，验证 disabled 零连接、enabled 保留轮询；账号 auto_poll_usage 不被改写。
- `reset_refresh_targets_expired_windows_and_throttles_retries`：仅到期的活动 OAuth 账号产生连接，覆盖开关关闭、未知资料、有效窗口、零用量无 reset、停用与非 OAuth、失败冷却和新观测后停止。
- 静态搜索必须确认 `refresh_usage` 只由 usage poller 和管理端手动接口等显式入口调用，不存在 Gateway 请求后刷新链路。
- `services/gateway/web` 构建必须通过 `npm run build`，确保 `UsageData` 类型与 `Accounts.vue` 展示同步。
- 改动 `fetch_usage` 后至少跑 `cargo test`，确认账号调度和 usage 相关共享测试不回归。

### 7. Wrong vs Correct

#### Wrong

```rust
let model = item.get("scope")?.get("model")?;
```

#### Correct

```rust
let Some(model) = item.get("scope").and_then(|scope| scope.get("model")) else {
    continue;
};
```

## Scenario: 每账号 5h/7d 用量控制线

### 1. Scope / Trigger

- 修改账号用量限制、消息选号、sticky、账号新建/编辑页或 bench 创建账号兼容性时适用。
- 控制线约束网关消息分配，依据最近观测的真实额度百分比；与本地请求费用统计、RPM、Fable 专属额度分别处理。

### 2. Signatures

- `Account.five_hour_usage_limit_percent: i32`、`seven_day_usage_limit_percent: i32`，serde 缺失默认 0；SQLite/PostgreSQL 对应列为 `NOT NULL DEFAULT 0` 整数。
- `POST /admin/accounts` 可提交两个 JSON 整数字段，缺失默认为 0；`PUT /admin/accounts/{id}` 未提交的字段保留既有值。
- `AccountSelectionContext.usage_limits_enabled: bool` 仅在网关精确 `/v1/messages` 路径为 true，`disabled()` 为 false；普通窗口控制不依赖请求模型名。
- `AccountService::update_account_usage_limits(&self, account: &Account) -> Result<(), AppError>` 校验后调用 `AccountStore::update_usage_limits`，只写两个控制线和 `updated_at`。
- `account_usage_limit_reached(account)` 对普通 `five_hour`、`seven_day` 窗口进行判断；`select_account_with_selection_context` 在 sticky 与普通候选路径执行同一规则。

### 3. Contracts

- 两个控制线分别接受 0～100 的整数，0 关闭，1～100 为百分比；新账号、旧库升级及 bench 省略字段的创建请求均默认关闭，不新增全局设置或继承关系。
- 只有窗口用量为有限非负数字、`resets_at` 是未来 RFC3339 时间且 `utilization >= limit` 时命中；不使用调度评分的衰减百分比。未知、非法或过期窗口不据此拦截。
- OAuth 与 SetupToken 的普通窗口同样适用；不要照搬 Fable helper 的 OAuth-only 条件。
- sticky 达线时加入本轮排除并保留原绑定，只有替代账号实际承载后才重绑；无替代账号返回本地 `TooManyRequests`。普通候选先遵守 Token 范围和运行时排除，再过滤额度，最后执行既有 RPM/优先级/评分。
- 通用与 Fable 规则同时适用；混合达线不能回退到任何受限账号。普通账号阈值可以不同，错误信息不能把它们描述为同一全局阈值。
- 达线不改变 active/disabled 或写入 `rate_limit_reset_at`；窗口到期、调高或关闭上限后下次选号恢复，同时继续遵守其他窗口、Fable 与真实上游冷却。
- 判断点是选号读取到的账号快照；已分配、排队或执行中的请求不取消，不预扣/预测，不保证单次或并发请求严格不越线，不新增主动 usage 查询。
- count_tokens、管理接口、后台 poller/PrimePoller 和独立 CLI 不套用新控制线；不能宣称它限制全部账号用量来源。本地拦截保持原消息链路顺序。
- 服务创建、CLI 身份创建、更新均校验值域；动态更新必须在状态或配置写入前拒绝错误类型与越界值。同次提交 active/disabled 与控制线时仍须保存控制线，只写必要字段，不能把旧快照的凭据或状态整行回写。
- 账号表单所有初始化、新建、编辑、授权导入、保存入口必须同步；列表额度区显示已配置上限。控件为 0～100、步长 1，空值不能被转换成关闭限制的 0。
- bench 的现有创建载荷继续省略新字段，保留并发 4、RPM 50、session 池 4/owner_only 和 rewrite 等既有默认；后续关联、OAuth 刷新和进程指标导入不能清掉管理员设置的控制线。
- 双库 schema、幂等补列、INSERT/UPDATE bind 顺序、`ACCOUNT_COLS` 和 row mapping 必须同步；PostgreSQL JSONB 与时间列通过文本投影适配 SQLx Any，具体类型约束见 [Settings & Database](settings-database.md#account-字段同步)。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 账号 A 的 5h=80/7d=60，任一窗口恰好达线 | 跳过 A；可用替代账号仍按既有范围和评分选择 |
| 两个窗口分别为 79.9%/59.9% | 允许 A，不提前预留缓冲 |
| 0 / 100 控制线 | 0 不检查该窗口；100 在 99.9% 允许、100% 命中 |
| 已达线账号无可用替代 | 本地 429，保留原 sticky，不调用上游 |
| 窗口未知、无效或过期 | 不按该窗口拦截；其他有效窗口仍可拦截 |
| 创建/更新字段为负数或大于 100 | BadRequest，旧数据不变 |
| 字段为字符串、布尔、小数或 null | 创建反序列化拒绝，动态更新 BadRequest，不静默忽略 |
| 仅更新一个控制线或不提交两个字段 | 另一个值或两个既有值保留 |
| 状态快捷操作同时提交控制线 | 状态与控制线都生效，保留新凭据和其他策略 |
| 两次迁移或刷新凭据/指标 | 非零控制线保留 |

### 5. Scenarios and Examples

- 正常：A 的上限为 80/60，B 为 90/70；A 的 5h 观测为 85% 后不能继续承载消息，同样用量的 B 仍可使用。
- 基础/边界：bench 新建账号省略字段，两个值均为 0；管理员在 cc2api 编辑页设置 80/60，后续凭据同步不会恢复为 0。
- 错误：直接设置 `rate_limit_reset_at` 表示管理员控制线，或状态切换后把旧 Account 整行更新，会延迟配置恢复或覆盖新凭据。
- 正确：每次消息选号只读窗口与账号阈值；状态与控制线组合更新走独立控制线 SQL，保持其余字段和真实上游冷却。

### 6. Tests Required

- `tests/account_scheduler_test.rs::usage_limits_*`：两窗口/两类账号、临界值、独立阈值、Token 范围、sticky 保留与重绑、全部达线、关闭/调高/重置恢复、脏窗口、Fable 叠加和服务校验。
- `handler::router::tests::usage_limits_*`：bench 旧载荷默认、局部更新、错误类型/范围无部分写入、状态与控制线组合保存。
- `gateway::tests::usage_limits_gateway_filters_messages_and_preserves_count_tokens`：真实本地上游账号选择、达线无上游发送、count_tokens 兼容与调高热生效。
- `tests/account_store_timestamp_test.rs::usage_limits_*`：SQLite/PostgreSQL 旧库缺列升级、重复迁移、创建/更新/详情/分页/调度字段往返，以及凭据/指标/状态变化后独立控制线写入不覆盖其它字段。
- 管理页构建及真实输入保存/回显/0 关闭/非法输入不提交/新建重置；必需 `cargo fmt --check`、完整 `cargo test --locked`、`npm run build`。

## Scenario: Fable 周用量上限 fallback

### 1. Scope / Trigger

- Trigger：修改 `/v1/messages` 账号选择、sticky session、Fable 周用量识别、上游 429 分类、settings 热刷新或 Settings 页 Fable 控件时适用。
- 目标：当 OAuth 账号最近观测的 Fable 周用量达到管理员设置的全局上限时，不再向该账号分配新的 Fable 请求；低于上限的账号仍使用原 sticky、RPM 和综合评分，不做主动均衡。

### 2. Signatures

- Setting keys：`fable_sticky_quota_fallback_enabled=true`、`fable_weekly_usage_limit_percent=50`；百分比只允许 `1..=100` 的整数字符串。
- 默认常量：`DEFAULT_FABLE_STICKY_QUOTA_FALLBACK_ENABLED`、`DEFAULT_FABLE_WEEKLY_USAGE_LIMIT_PERCENT`。
- Gateway 热缓存：`reload_fable_sticky_quota_fallback_enabled()` 与 `reload_fable_weekly_usage_limit_percent()`；启动时必须各调用一次，管理端更新对应 setting 后必须 reload。
- 请求上下文：`AccountSelectionContext { fable_quota_fallback_enabled: bool, fable_weekly_usage_limit_percent: u32, request_model: Option<String> }`。
- 账号选择：`AccountService::select_account_with_selection_context(session_hash, exclude_ids, allowed_ids, context).await -> Result<SelectedAccount, AppError>`。
- 429 分类：`AccountService::handle_rate_limit_with_context(account, retry_after_secs, body, usage, context).await -> Result<RateLimitDecision, AppError>`。
- 账号可用性判断：`account_fable_weekly_usage_limit_reached(account, limit_percent) -> bool`。
- 新决策分支：`RateLimitDecision::RetryOtherAccount` 表示当前账号仅对本请求模型不可用，调用方可排除该账号后重试其他账号。

### 3. Contracts

- Gateway 只有在 `path == "/v1/messages"` 时才允许启用 Fable fallback；`count_tokens`、bootstrap、usage poller、PrimePoller 和其它入口必须保持 disabled 语义。
- Fable 模型按小写化后的 `claude-fable-5`、`claude-fable-5-1` 及各自的 `[...]` 后缀匹配。不要用包含匹配覆盖其他模型名。
- Fable 周用量达到上限必须同时满足：账号为 `AccountAuthType::Oauth`、`usage_data.seven_day_fable.utilization >= context.fable_weekly_usage_limit_percent`、`resets_at` 是未来 RFC3339 时间。不要复用普通 usage 的 `USAGE_HIT_THRESHOLD = 97.0`。
- `utilization` 缺失或不是数字、`resets_at` 缺失/非法/已过期时视为未达到上限，避免脏缓存误伤账号。
- SetupToken 即使缓存里有脏的 `seven_day_fable`，也必须保持旧 sticky 行为。
- sticky 账号达到上限时，只把该账号加入本轮 `runtime_exclude_ids`，并刷新原 sticky TTL；不要删除旧 sticky。只有替代账号真实承载请求后，才通过已有 `should_bind_session` / `bind_selected_session` 覆盖 sticky。
- 非 sticky Fable 请求应先过滤达到上限的账号；若所有允许候选都达到上限，返回包含配置百分比的 `AppError::TooManyRequests`，不要落到普通 `ServiceUnavailable("no available accounts")` 或回退到已达上限账号。
- 低于上限的候选继续使用现有 API Token allow/block、优先级、通用 7d/5h、并发和 RPM 逻辑；不得按 `seven_day_fable` 排序、加权或主动均衡。
- 请求开始前低于上限即可执行；单次请求使实际用量轻微越线是允许的，只有 usage 被动/主动写回后的后续请求才按新观测值过滤，不预测单次请求成本。
- sticky 账号 RPM 饱和不属于 Fable 周用量 fallback，仍走 `acquire_account_rpm` 的等待或本地 429，不能换号破坏 prompt cache。
- Fable OAuth 429 且开关启用时，先识别通用 `seven_day` / `five_hour` 窗口并写账号级冷却；若通用窗口未命中，则返回 `RateLimitDecision::RetryOtherAccount`，不要写账号全局 `rate_limit_reset_at`。
- Fable 429 如需返回 Fable reset 信息，必须使用同一请求上下文阈值；本地 usage 未达到上限时，Gateway 只能使用本次 429 的 `7d_oi` 响应头做被动采集和模型级换号，不得触发 usage API。
- 新增 `RateLimitDecision` 分支后，所有 `match RateLimitDecision` 的调用方必须显式处理 `RetryOtherAccount`，不能把它误当成 `Quarantined`。
- 新 setting 必须同步默认常量、SQLite/PostgreSQL 共用的缺失键插入、管理 API GET/PUT 校验、Gateway 启动加载/保存后热刷新和 Settings 数字控件；非法存量值在 service reload 时回退默认 `50`，热路径不得 panic。
- 设置为 `100` 可恢复此前明确 100% 才过滤的阈值语义；关闭 `fable_sticky_quota_fallback_enabled` 可完全停用本规则，且二者都应热生效。

### 4. Validation & Error Matrix

| 条件 | 期望行为 |
|------|----------|
| 开关开启、阈值 50，sticky OAuth usage 为 50% 且 reset 在未来 | 本轮排除 sticky 账号，尝试选择替代账号 |
| 开关开启、阈值 50，sticky OAuth usage 为 49% | 保持原 sticky 账号 |
| 开关关闭，同样的 sticky 账号 usage 为 100% | 保持原 sticky 账号 |
| Fable sticky 达到上限且没有替代账号 | 返回 `TooManyRequests`，旧 sticky 绑定保留 |
| 非 sticky 候选分别为 50% 和 49% | 过滤 50% 账号，49% 账号进入既有评分 |
| 所有允许候选都达到上限 | 返回包含阈值的 `TooManyRequests` |
| 阈值 100，usage 为 99% / 100% | 99% 允许，100% 过滤 |
| 非 Fable 模型请求 | 忽略 `seven_day_fable`，保持普通 sticky / 调度行为 |
| SetupToken 账号带 `seven_day_fable` 脏缓存 | 忽略该窗口，保持 sticky |
| Fable 窗口缺失、非法或 reset 已过期 | 视为未达到上限 |
| sticky 账号 RPM 饱和 | 不触发 Fable fallback，保持等待/本地 429 |
| Fable OAuth 429 命中 `seven_day` 或 `five_hour` | 写账号级冷却并返回 `Quarantined` |
| Fable OAuth 429 未命中通用窗口 | 返回 `RetryOtherAccount`，不写全局冷却 |
| setting 为 `0`、`101`、小数或文本 | 管理 API 返回 `BadRequest`，旧配置不变 |

### 5. Good/Base/Bad Cases

- Good：阈值为 50，用户会话 sticky 到账号 A，A 的 `seven_day_fable` 为 50% 且 3 天后 reset；同 token 允许 49% 的账号 B，Gateway 对本次请求选择 B，真实上游成功后把 session 绑定到 B。
- Good：A 的普通周限额 `seven_day` 也为 100%；Fable 429 必须隔离 A 到通用 reset 时间，而不是继续换号重试导致所有模型都反复撞墙。
- Base：没有 `request_model`、模型不是 Fable、开关关闭或 Fable 窗口无效时，`AccountSelectionContext::disabled()` / 窗口校验保持旧行为。
- Bad：继续把固定 `100` 写死在账号 helper 中，会让管理员保存的百分比只在 UI 显示而不影响调度。
- Bad：把通用 `USAGE_HIT_THRESHOLD = 97.0` 当成 Fable 上限，或根据预估消耗提前留缓冲，都会绕过管理员设置的明确控制线。
- Bad：发现 sticky Fable 达到上限后直接 `delete_session`，没有替代账号时用户后续非 Fable 请求也会丢失原 sticky。

### 6. Tests Required

- `tests/account_scheduler_test.rs` 覆盖：49% 保持 sticky、50% 选择替代账号、替代账号可重绑、无替代账号返回 429 且旧 sticky 保留、非 sticky 过滤、所有候选达到上限、开关关闭、阈值 100、非 Fable 和 SetupToken。
- `src/service/account.rs` 单测覆盖：配置阈值比较、未来/过期/缺失/非法窗口、SetupToken 忽略，以及 Fable OAuth 429 的 `RetryOtherAccount`、通用 `seven_day` / `five_hour` `Quarantined` 和 credit 行为。
- `src/store/db.rs` / `src/handler/router.rs` / `src/service/gateway.rs` 覆盖：默认 key 为 `50`、非法值拒绝、合法保存后热刷新、非法存量值 reload 回退默认。
- Settings 改动后必须运行 `services/gateway/web` 的 `npm run build`，确保数字控件、校验和 `SettingsMap` 可构建。
- 后端改动后至少运行 `cargo fmt --check`、`cargo test`；settings / handler / gateway 同时改动时再跑 `git diff --check`。
- 静态搜索确认普通 Gateway 请求没有新增 `refresh_usage` 调用，且未在账号评分中引入 `seven_day_fable`。

### 7. Wrong vs Correct

#### Wrong

```rust
if check_usage_window(&account.usage_data, "seven_day_fable", 100.0).is_some() {
    self.cache.delete_session(session_hash).await?;
    exclude_ids.push(account.id);
}
```

```rust
match rate_limit_decision {
    RateLimitDecision::Quarantined | RateLimitDecision::RetryOtherAccount => return last_resp,
    _ => {}
}
```

#### Correct

```rust
if context.is_fable_quota_fallback_active()
    && account_fable_weekly_usage_limit_reached(
        &account,
        context.fable_weekly_usage_limit_percent,
    )
{
    runtime_exclude_ids.push(account.id);
    let _ = self
        .cache
        .set_session_account_id(session_hash, account.id, STICKY_SESSION_TTL)
        .await;
}
```

```rust
match rate_limit_decision {
    RateLimitDecision::RetryOtherAccount => exclude_ids.push(account.id),
    RateLimitDecision::Quarantined => return last_resp,
    _ => {}
}
```

## Scenario: 受信任管理端解析 OAuth 凭据

### 1. Scope / Trigger

- 修改 `POST /admin/accounts/:id/oauth-credentials/resolve`、`AccountService` OAuth refresh 锁、usage 获取 token，或新增需要消费最终 AT/RT 的受信任服务时适用。
- 该接口用于让外部 orchestrator 复用 cc2api 的单一 RT 刷新所有权，不是浏览器或普通网关 token 的公开接口。

### 2. Signatures

管理 API：

```http
POST /admin/accounts/:id/oauth-credentials/resolve
Authorization: Bearer <admin password>
Content-Type: application/json

{
  "min_validity_seconds": 2400,
  "force_refresh": false
}
```

响应：

```json
{
  "account_id": 1,
  "access_token": "<secret>",
  "refresh_token": "<secret>",
  "expires_at": 0
}
```

service 入口：

```rust
AccountService::resolve_oauth_credentials(
    id: i64,
    min_validity_seconds: i64,
    force_refresh: bool,
) -> Result<OAuthCredentialSnapshot, AppError>
```

### 3. Contracts

- handler 默认 `min_validity_seconds=2400`，只允许 `60..=7200`；`force_refresh` 默认 false。
- 只接受 `status=active` 且 `auth_type=oauth` 的账号，AT、RT、`expires_at` 任一缺失都拒绝返回。
- 每次 resolve 都必须获取 `oauth:refresh:account:<id>` cache lock，即使当前 AT 仍有效也不能走无锁快路径；这样返回快照不会与 Gateway、usage poller 或另一个 resolve 的 RT 轮换并发。
- 获锁后重新读取账号；需要刷新时复用同一 refresh 实现并落库；返回前再次读取账号，确保 AT/RT/过期时间来自同一次最终存储状态。
- `force_refresh=true` 只用于消费者已经观察到 401 的单次恢复。调用方不得用它做周期轮询，也不得自行拿响应 RT 调 OAuth endpoint。
- `resolve_upstream_token` 只允许临时刷新失败时使用仍有效 AT 的兼容 fallback；永久凭据错误不得回退。管理端 resolve 不允许返回不满足最小有效期的旧快照。
- `refresh_usage` 通过同一 token resolve 链路获取 AT，避免 usage poller 与管理端消费者形成第二条无锁刷新路径。
- tracing、错误和测试输出不得记录 AT、RT、Authorization、邮箱/UUID 的真实映射。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|------|------|
| `min_validity_seconds < 60` 或 `> 7200` | `BadRequest` |
| 账号不存在 | 现有 store 的 not found 错误 |
| 账号 disabled | `BadRequest`，提示不是 active |
| SetupToken 账号 | `BadRequest`，提示不是 OAuth |
| AT 剩余时间满足要求 | 仍获取账号锁，最终重读后原样返回 |
| AT 临期或 `force_refresh=true` | 锁内刷新、落库、最终重读后返回 |
| refresh token 缺失 | 更新 auth error，返回 `PermanentCredential` |
| refresh 返回 `invalid_grant` | 返回 `PermanentCredential`，不使用旧 RT/AT 伪装成功 |
| 等待锁超时 | `ServiceUnavailable`，不返回锁前快照 |

### 5. Good/Base/Bad Cases

- Good：Gateway 正在轮换 RT，bench resolve 等待同一 lock；锁释放后重新读库并拿到新 AT/RT，而不是返回进入函数时的旧副本。
- Base：AT 仍有 1 小时有效期，resolve 获取锁后不发 refresh 请求，只最终重读并返回当前快照。
- Bad：先检查 `has_valid_oauth_access_token`，有效就直接返回；检查后到返回前另一个刷新者可能已经轮换 RT。
- Bad：管理端 resolve 刷新失败后返回仍有效旧 AT；bench 会把不满足本次运行窗口的凭据当作已准备完成。

### 6. Tests Required

- handler 单测覆盖默认值、60/7200 边界和越界拒绝。
- service 单测覆盖有效 AT 不刷新但仍返回完整快照、非 OAuth/disabled 拒绝。
- 人工占用账号 refresh lock，启动 resolve 后断言其等待；更新 store 的 AT/RT 并释放锁，断言返回更新后的最终快照。
- refresh 成功/失败路径断言 lock 总会释放，响应和日志不包含额外账号字段。
- 完整改动至少运行 `cargo fmt --check` 和 `cargo test`。

### 7. Wrong vs Correct

#### Wrong

```rust
let account = self.store.get_by_id(id).await?;
if account.has_valid_oauth_access_token(min_validity_seconds) {
    return Ok(snapshot_from(account));
}
```

#### Correct

```rust
let lock_key = format!("oauth:refresh:account:{}", id);
let lock_owner = Uuid::new_v4().to_string();
let acquired = self
    .cache
    .acquire_lock(&lock_key, &lock_owner, OAUTH_LOCK_TTL)
    .await?;
if acquired {
    let result = self.resolve_oauth_credentials_locked(id, policy).await;
    self.cache.release_lock(&lock_key, &lock_owner).await;
    return result;
}
```

有效 AT 也必须在同一账号锁内最终重读后返回。

## Scenario: OAuth Token 预解析永久凭据错误停用与切号

### 1. Scope / Trigger

- 修改 OAuth token endpoint 错误分类、`AccountService::resolve_upstream_token`、Gateway 请求转发前 Token 预解析，或账号认证失败停用逻辑时适用。
- 目标是在账号级凭据已确定永久失效时停用当前账号并在同一请求内切号，同时避免 OAuth endpoint 临时故障触发批量误停或逐账号放大。

### 2. Signatures

```rust
AppError::PermanentCredential(String)

oauth::refresh_oauth_token_at(
    refresh_token: &str,
    proxy_url: &str,
    token_url: &str,
) -> Result<RefreshedOAuthTokens, AppError>

AccountService::resolve_upstream_token(id: i64) -> Result<String, AppError>
AccountStore::disable_for_auth_failure(id: i64, reason: &str) -> Result<(), AppError>
AccountService::disable_for_auth_failure_if_current(expected: &Account, reason: &str) -> Result<(), AppError>
```

- Gateway 适用入口为 `/v1/messages` 与 `/v1/messages/count_tokens`。
- `PermanentCredential` 的外部 HTTP 映射保持 503；所有候选耗尽时返回 Anthropic `api_error` 形状的通用 503。

### 3. Contracts

- OAuth 非 2xx 响应只读取最多 4 KiB 错误体，并只接受最长 64 字符、由 ASCII 字母数字、`_`、`-` 组成的短 `error` 码。不得记录 `error_description`、完整响应正文、AT、RT、Authorization、Cookie 或代理密码。
- 仅客户端错误且状态不是 429、短错误码为 `invalid_grant` 时返回 `PermanentCredential`。429、5xx、网络/超时、响应解析失败和其他错误码保持临时错误；临时 HTTP 状态优先于响应体中的 `invalid_grant` 文本。
- OAuth 账号缺少 refresh token 时必须在有效 AT 快路径之前返回 `PermanentCredential`；有效 AT 不能掩盖已无法续期的账号状态。
- 永久凭据错误必须保留到 Gateway，不得包装回普通 `ServiceUnavailable`，也不得使用仍有效旧 AT fallback。临时错误可继续复用尚未过期的 AT，并且不得切换到其他账号放大 token endpoint 故障。
- 只有 Gateway 请求调度路径负责停用账号；管理端 resolve、usage、telemetry 和后台任务可观察该错误，但不得仅因一次解析调用自行修改账号状态。
- Gateway 收到 OAuth `PermanentCredential` 后调用 `disable_for_auth_failure_if_current`，按原 AT/RT 且仍为 active OAuth 的条件写入。实际命中时原子写入 `status=disabled`、相同的 `auth_error` / `disable_reason` 并清空两项限流时间；已换凭据或人工停用时忽略旧回包，SQL 失败仍向上返回。无条件 `disable_for_auth_failure` 保留给既有 SetupToken 路径。
- 停用成功后把账号加入本轮 `exclude_ids`；`/v1/messages` 还必须显式释放当前 slot，再继续账号选择。sticky 选择必须服从同一排除集合，同一请求内每个永久失效账号最多探测一次。
- 永久凭据排除必须使用独立状态判断，并在候选耗尽时优先于历史 429 返回通用 503；不得改变普通 401 恢复失败与历史 429 的既有优先级。

### 4. Validation & Error Matrix

| 条件 | 分类 | Gateway 行为 |
|------|------|--------------|
| HTTP 400，`error=invalid_grant` | `PermanentCredential` | 原子停用、排除并切号 |
| refresh token 缺失，即使 AT 仍有效 | `PermanentCredential` | 不调用 token endpoint，原子停用并切号 |
| HTTP 429，即使正文含 `invalid_grant` | 临时错误 | 不停用、不跨账号重试；有效 AT 可 fallback |
| HTTP 5xx，即使正文含 `invalid_grant` | 临时错误 | 不停用；有效 AT 可 fallback |
| 网络、超时或响应解析失败 | 临时错误 | 不停用；无有效 AT 时保持当前失败语义 |
| 首账号永久失效、后续账号可用 | 永久错误已隔离 | 当前请求由后续账号完成，不向客户端泄漏前一账号错误 |
| 所有候选永久失效 | 永久错误已隔离 | 返回通用 Anthropic 503，每个账号最多探测一次 |
| 先收到 429、后遇永久凭据错误 | 永久错误已隔离 | 返回通用 503，不返回旧 429 |
| 账号停用 SQL 失败 | 存储失败 | 立即返回错误，不继续切号 |

### 5. Good/Base/Bad Cases

- Good：高优先级 OAuth 账号刷新返回 `invalid_grant`，Gateway 原子停用并排除该账号，释放 slot 后由第二账号完成原请求；后续请求不再调度失效账号。
- Base：token endpoint 返回 503，旧 AT 仍有效；请求继续使用旧 AT，账号保持 active，备用账号不参与本次请求。
- Bad：根据完整错误字符串包含 `invalid_grant` 决定停号；429/5xx 代理错误可能夹带该文本，造成批量误停。
- Bad：先检查 AT 有效期再检查 RT 是否存在；缺失 RT 的历史账号会继续被调度，直到 AT 过期后才暴露故障。
- Bad：永久错误切号后仍优先返回之前缓存的 429，客户端会看到错误的失败原因，且无法确认永久失效账号已被隔离。

### 6. Tests Required

- OAuth 分类单测覆盖：标准 400 `invalid_grant`、错误描述脱敏、429/5xx 携带 `invalid_grant` 仍为临时错误、未知错误码保持临时错误。
- AccountService 单测覆盖：有效 AT 不能绕过缺失 RT、永久错误不 fallback、临时错误仍可 fallback、管理端凭据快照保留永久错误类别。
- Gateway 回归覆盖：普通 `/v1/messages`、sticky、`count_tokens` 的停用切号；缺失 RT；所有账号永久失效；先 429 后永久失效；5xx 和网络失败不误停、不切号。
- Store 测试断言 `disable_for_auth_failure` 同时写入 disabled、两类原因并清空两个限流时间。
- 完整验证至少运行 `cargo fmt --check`、OAuth/账号/Gateway 定向测试、`cargo test` 和双仓 `git diff --check`。

### 7. Wrong vs Correct

#### Wrong

```rust
let token = account_svc.resolve_upstream_token(account.id).await?;
```

该写法把永久凭据错误直接返回给客户端，账号仍保持 active 并在后续请求中反复入选。

#### Correct

```rust
match account_svc.resolve_upstream_token(account.id).await {
    Ok(token) => token,
    Err(AppError::PermanentCredential(reason)) => {
        account_svc
            .disable_for_auth_failure_if_current(&account, &reason)
            .await?;
        exclude_ids.push(account.id);
        drop(slot_guard);
        continue;
    }
    Err(error) => return Err(error),
}
```

实际永久错误停用后切号；旧凭据快照已过期时只排除本请求中的旧候选，不能停用新登录凭据。临时错误沿用原失败或有效 AT fallback 语义。

## Scenario: 有效上游 Session 首次 Hello 代理探测

### 1. Scope / Trigger

- Trigger：修改 Claude Code `/v1/messages` 首次连通性检查、账号代理网络路径、上游 Session 池解析、Session 去重、CacheStore/Redis singleflight、严格模式或对应 Settings 时适用。
- 目标：新的有效上游 Session 第一次准备承载上游请求时，通过最终选中账号的 `proxy_url` 匿名探测 Anthropic Hello；同一活跃上游 Session、账号、有效画像和代理路径只探测一次。
- 公开 `GET/HEAD /api/hello` 仍是无状态本地健康端点，不进入账号选择或代理探测；完整 wire 画像见 `../protocol/claude-code-profile-upgrade.md`。

### 2. Signatures

- 服务入口：`SessionHelloProbeService::ensure_ready(account, real_session_id, upstream_session_id, config).await -> SessionHelloProbeDecision`。
- 决策：`Proceed`、`BlockFailure`、`BlockTimeout`、`BlockUnavailable`。
- CacheStore：`get_session_hello_probe_state(key, success_ttl)`、`set_session_hello_probe_state(key, state, ttl)`，并复用 owner 语义的 `acquire_lock/release_lock`。
- 状态 key：`session_hello_probe:v2:<account_id>:<profile_key>:<sha256(upstream_session_id)>:<sha256(proxy_url)>`，singleflight 使用相同画像维度。
- 全局 settings：
  - `session_hello_probe_enabled=false`
  - `session_hello_probe_strict=false`
  - `session_hello_probe_timeout_secs=5`，范围 `1..=30`
  - `session_hello_probe_success_ttl_secs=3600`，范围 `60..=86400`
  - `session_hello_probe_failure_cooldown_secs=300`，范围 `10..=3600`

### 3. Contracts

- 仅当 path 精确为 `/v1/messages`、客户端为 Claude Code、原始 body 能提取非空真实 Session，且请求已经选定账号并完成本轮 slot/RPM admission 时调用探测。
- Gateway 必须先解析账号级上游 Session 池，再调用探测；探测使用最终改写后的有效上游 Session 去重。池关闭或解析失败时回退到真实下游 Session，不得因池故障阻断原有业务转发。
- assistant prefill、warmup、classifier、event logging、count tokens、普通 API 客户端和其它本地响应不得创建探测状态。
- 探测请求固定为匿名 `HEAD https://api.anthropic.com/api/hello`，`User-Agent` 来自请求账号副本的有效画像：280 为 `Bun/1.4.3`、260/257 为 `Bun/1.4.1`、220 为 `Bun/1.4.0`；其余 header 为 `Accept: */*`、`Accept-Encoding: gzip, deflate, br, zstd`、`Connection: keep-alive`。不得添加 query、body、Authorization、Cookie、billing header 或用户数据。
- 非空 `Account.proxy_url` 必须由 `tlsfp::get_request_client` 内部通过 `reqwest::Proxy::all` 校验并应用；客户端创建失败时返回错误，无效代理不得静默直连。空代理允许直连。
- 只有 HTTP 200 为成功。成功状态命中时原子续期，形成滑动空闲 TTL；`failure` / `timeout` 使用固定冷却，不因读取续期。
- 状态不存在时，leader 获取 `:lock` 后执行网络请求并写状态；follower 轮询同一状态并复用结果。RedisStore 必须保证跨进程去重，MemoryStore 只保证单进程。
- leader 写状态失败时不得立即释放锁，应让锁按 TTL 自然过期以吸收当前并发波次；已经等待过该 leader 的 follower 即使随后拿到锁也不得再次发包，非严格模式开放、严格模式返回 503。新的后续请求可在锁释放或过期后恢复探测。
- MemoryStore 必须按固定间隔惰性清理所有过期探测状态，不能只清理当前访问键，也不能在每次读写时全表扫描。
- 探测不得再次执行账号 RPM admission，也不得写业务 usage 或自动 telemetry。账号 retry 从 A 切到 B 时，B 的账号 id 生成新 key，必须在 B 承载业务请求前重新判断。
- 日志只允许账号 id、真实下游 Session 短 hash、有效上游 Session 短 hash、`proxy_configured`、`source=network|cache|follower`、耗时、HTTP status 和结果类别；网络结果允许使用 `info`，缓存不可用或 follower 等待超时使用 `warn`。不得输出完整 Session、代理 URL、请求/响应 body 或凭据。
- Settings 必须同步默认常量、数据库缺失键插入、管理 API GET/PUT 校验、Gateway 热加载和前端控件；功能关闭时从属控件禁用但保留已保存值。

### 4. Validation & Error Matrix

| 条件 | 非严格模式 | 严格模式 |
|------|------------|----------|
| 功能关闭 | 不读 cache、不发探测，继续业务请求 | 同左 |
| HTTP 200 | 写 `success`，继续业务请求 | 同左 |
| HTTP 非 200、代理或网络错误 | 写 `failure` 冷却并继续 | 复用冷却并返回 Anthropic 形状 502 |
| 探测超过总超时 | 写 `timeout` 冷却并继续 | 复用冷却并返回 Anthropic 形状 504 |
| cache 读写或锁失败 | 记录脱敏 `warn`，不发无去重探测并继续 | 返回 Anthropic 形状 503 |
| follower 等待后仍无结果 | 本请求不重复发包并开放；新请求可在锁过期后恢复 | 返回 503，不永久等待或重复发包 |
| 同 Session 切换账号或账号修改代理 | 使用新 key 重新探测 | 同左 |

### 5. Good/Base/Bad Cases

- Good：两个实例同时收到映射到同一有效上游 Session 的首请求，Redis 只允许一个 leader 发 Hello，follower 复用 `success`；两个业务请求各自只执行原有一次 RPM admission。
- Good：账号 A 的业务请求返回可重试错误后切换到 B，A/B 各有一个独立探测结果，B 完成自己的探测后才转发业务请求。
- Base：功能默认关闭；升级旧数据库时只插入缺失 setting，不覆盖管理员已有值，热路径保持升级前行为。
- Bad：直接按 Session 记一个永久布尔值；这会忽略账号/代理变化并无限增长。
- Bad：代理字符串无效时继续调用会忽略代理错误的 client builder，导致探测从宿主机直连成功并错误放行业务请求。
- Bad：把探测放在 admission 前或在探测内部再计一次 RPM，会让等待、失败和重试请求的 RPM 语义漂移。

### 6. Tests Required

- 请求构造测试断言精确 method、URL、headers、空 body，以及无 Authorization、Cookie、billing header；配置有效代理时必须由本地 mock proxy 实际收到请求。
- Probe service 覆盖 200、非 200、超时、无效代理不直连、缓存故障的严格/非严格决策、失败冷却复用和状态 key 不泄漏原值。
- MemoryStore 覆盖成功滑动续期、失败固定冷却、未再次访问的过期键会被低频惰性清理，以及并发首请求只发一次。
- Probe service 覆盖 leader 写缓存失败时 follower 不重复探测，并验证锁到期后的新请求可以恢复探测。
- Redis 集成测试必须连接真实 Redis，使用两个独立 RedisStore/服务实例并发断言只产生一次网络探测，同时验证成功续期与失败不续期。
- Gateway 集成测试覆盖账号 A retry 到 B 时 Hello 调用为 2 次、两个账号 RPM 各只增加 1；共享有效上游 Session 只探测一次；池关闭或解析失败时回退真实 Session；非严格失败继续业务、严格失败不发送业务请求；本地拦截、count tokens、API 客户端和缺失 Session 不进入探测。
- Settings 覆盖默认值、布尔/数值范围、保存后热加载；前端运行 `npm run build`。
- 完整验证运行 `cargo fmt --check`、`cargo test`、`cargo test cch`、`git diff --check`，并静态扫描日志不得包含完整代理地址、Session 或凭据。

### 7. Wrong vs Correct

#### Wrong

```rust
let client = make_request_client(&account.proxy_url)
    .unwrap_or_else(|_| reqwest::Client::new());
let response = client.head(HELLO_URL).send().await?;
account_svc.acquire_account_rpm(&account, sticky, session_hash).await?;
```

代理或 TLS 客户端构建失败时退回默认客户端会绕过账号代理，而且探测后再次 admission 会把一轮业务请求计成两次 RPM。

#### Correct

```rust
let state = match get_request_client(&account.proxy_url) {
    Ok(client) => run_anonymous_head(client, config.timeout).await,
    Err(_) => SessionHelloProbeState::Failure,
};
```

Gateway 在既有 admission 后调用 `ensure_ready`；共享 client factory 负责代理失败关闭，服务再执行匿名 HEAD、状态缓存和 singleflight，不执行第二次 RPM admission。

## Scenario: Claude Code 状态分类旁路与归因补齐

### 1. Scope / Trigger

- Trigger：修改 Claude Code 后台 Agent 状态分类请求的识别、请求体改写、模拟响应、请求日志、账号代理或对应 Settings 时适用。
- 目标：保留 Fable 5.1 `cli-bg` 请求的窄范围模拟能力，并为 Claude Code 非 Haiku 状态分类请求提供默认关闭的 billing/CCH 与官方身份块补齐；普通 `/v1/messages`、Haiku、旧 Auto Mode classifier 和账号调度行为必须保持不变。

### 2. Signatures

- setting：`intercept_cli_bg_status_classifier_mode=passthrough|mock`，默认 `passthrough`。
- setting：`intercept_cli_bg_status_classifier_identity_injection_enabled=true|false`，默认 `false`。
- runtime config：`CliBgStatusClassifierConfig { mode, identity_injection_enabled }`。
- 窄 detector：`is_cli_bg_status_classifier_request(path, headers, body, client_type) -> bool`。
- 通用 detector：`detect_claude_code_status_classifier_request(path, headers, body, client_type) -> Option<CliStatusClassifierMatch>`。
- identity-only 改写：`Rewriter::rewrite_claude_code_identity_only(body, account, upstream_session_rewrite) -> Vec<u8>`。
- 归因补齐：`Rewriter::rewrite_claude_code_status_classifier_attribution(body, account, upstream_session_rewrite) -> Vec<u8>`。
- TLS 客户端：`tlsfp::get_request_client(proxy_url) -> Result<reqwest::Client, reqwest::Error>`。
- mock 外层返回 Anthropic Message envelope，`content[0].text` 是可二次解析的 `state/detail/tempo/needs/output` JSON。

### 3. Contracts

- 窄 detector 必须同时匹配精确 `/v1/messages`、`ClientType::ClaudeCode`、原始 `x-app=cli-bg`、精确 `claude-fable-5-1`、`stream=false`、`max_tokens=3072`、唯一 ephemeral classifier system text block 和唯一 user 状态文本。只有该 detector 可以选择 `mock`；Fable 5、`[1m]`、普通主请求和旧 XML classifier 不得进入模拟链路。
- 通用 detector 必须匹配精确 `/v1/messages`、`ClientType::ClaudeCode`、原始 `x-app=cli|cli-bg`、`stream` 缺失或为 `false`、非空模型、唯一 classifier block 和唯一 user 状态文本。system 只允许至多一个严格 billing block、至多一个精确官方身份块和唯一 ephemeral classifier block；未知、重复或形状异常的 block 必须拒绝。通用 detector 不得硬编码模型名或 `max_tokens`。
- 归因补齐仅在 `mode=passthrough`、`identity_injection_enabled=true`、通用 detector 命中且模型不是 Haiku 时执行。开关关闭时必须完整保留既有链路；Haiku 在开关切换前后的上游请求体必须一致，也不得新增身份块。
- billing 缺失时使用共享 Claude Code API billing builder 插入 billing 并计算有效 CCH；已有 billing 且包含 CCH 时按最终请求体刷新 CCH；已有 billing 但没有 CCH 时保留原 block，不擅自增加 CCH。最终 system 顺序固定为 billing、identity、classifier，CCH 只能基于最终序列化正文计算。
- 归因补齐只允许账号 metadata、upstream session identity、billing、identity 和 CCH 变化，不运行 expansion、缓存断点、TTL、thinking、字段顺序或其它通用正文改写；结构异常时失败开放并返回原正文。
- 独立的 `message_top_field_filter_enabled` 默认开启，三条 Messages 转发分支在本函数前统一清理固定根键，实际删除后在最终输出刷新已有唯一 CCH；这是旁路合同的有限例外，不扩展 detector 或其它通用改写。此处失败开放的“原正文”指传入函数的正文；无删除时仍保持原字节。具体范围、设置与测试见 [Messages 固定顶层字段清理开关](../protocol/claude-code-profile-upgrade.md#scenario-messages-固定顶层字段清理开关)。
- 账号 `allow_fast_mode=false` 的 Fast 策略在三条真实转发分支汇合后统一执行：只删除根级精确 `speed: "fast"`，并继续过滤完整 Fast beta；实际删除后刷新已有唯一合法 CCH，包含 Strip 旁路。该策略独立于根键清理和身份注入开关，不运行其它通用正文改写；允许或无删除时保留原字节行为。换号从公共原文重新按当前账号判断，不能沿用前次删除结果。详见 [Fast 账号控制](../protocol/claude-code-profile-upgrade.md#scenario-claude-fast-mode-账号级透传控制)。
- 窄 detector 命中 `passthrough` 且未执行归因补齐时，继续使用 identity-only 改写。所有 passthrough 请求仍走账号选择、sticky、RPM/concurrency、OAuth、2.1.257 header、账号代理/TLS、Session Hello、401、signature/429 retry 和响应透传；不得因为识别成 classifier 而跳过 Session Hello。
- classifier 命中后全文请求、429 请求和非流式响应捕获全部禁用，只保留尺寸、短 hash、重试次数与 `proxy_configured` 等脱敏摘要。`mock` 必须在 session hash、账号选择、RPM 和并发槽之前返回，不访问上游或消耗账号额度。
- mock 分类优先级固定为：API/auth/infra 错误 -> blocked；Agent 明确自动复查/继续执行 -> working；无自动复查的用户门槛 -> blocked；明确 failed/done；最后回退 `Current state`，未知值保守返回 working。
- 非空代理由共享 TLS client factory 强制解析和应用；代理或客户端构建失败必须向调用方返回错误，所有 gateway、OAuth、Hello、Prime 和 telemetry 调用点都不得自行退回直连客户端。错误日志不得包含代理 URL 或其中的凭据。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|------|------|
| 窄 detector 命中 + `mock` | 本地 HTTP 200 Message envelope，不进入账号和上游链路 |
| 窄 detector 命中 + `passthrough` + 注入关闭 | identity-only 改写后经账号代理转发，保留 Session Hello，禁用全文捕获 |
| 通用 detector 命中 + 注入开启 + 非 Haiku | 补齐 billing/identity，按 billing 原状态计算或刷新 CCH，经账号代理转发 |
| 通用 detector 命中 + 注入开启 + Haiku | 使用开关开启前的既有请求链路，上游正文不得因本开关变化 |
| 任一 detector 条件不满足 | 使用普通请求链路和管理员现有改写设置 |
| 已有 billing+CCH | 保留 billing 内容并按最终正文刷新 CCH |
| 已有 billing 但无 CCH | 保留原 billing，不自动增加 CCH |
| `Awaiting your go` 且声明 `Next check` | working，Agent 仍持有下一步 |
| 需要用户选择修复、环境或提交位置且无自动复查 | blocked |
| API/auth/infra 错误同时声明重试或复查 | blocked，硬错误优先 |
| 非空代理无法解析或客户端构建失败 | 返回受控错误，不连接目标上游，不退回直连 |

### 5. Good/Base/Bad Cases

- Good：非 Haiku 通用 classifier 在注入开启时，代理收到 billing、精确官方身份块、classifier 三段有序 system，且 CCH 对最终请求体有效。
- Good：Haiku classifier 在开关开启和关闭时，代理收到的请求体逐字节一致；已有身份块不会重复插入。
- Good：上游地址设为不可达域名，账号配置本地 mock HTTP proxy；passthrough 请求只有经过该代理才能获得 200。
- Good：全文非流/429 日志全局开启时，classifier 仍只写安全摘要；其它普通请求继续遵守管理员日志设置。
- Base：mode 缺失时默认 `passthrough`，注入开关缺失时默认 `false`；旧数据库只补缺失 key，管理员已有合法值不被覆盖。
- Bad：用通用 detector 扩大 `mock` 命中范围，会把未经验证的模型或 `x-app=cli` 请求本地短路。
- Bad：classifier 命中后跳过 Session Hello，会让默认关闭的注入开关也改变既有请求行为。
- Bad：在 billing/identity/classifier 完成排序前计算 CCH，会生成与最终上游正文不一致的 attestation。
- Bad：代理解析失败后创建默认 `reqwest::Client`，会从宿主机直连并暴露与账号不一致的网络/TLS 特征。

### 6. Tests Required

- 窄 detector 覆盖完整 Fable 5.1 正例，以及 path、UA、x-app、model、stream、max_tokens、system/user marker、Fable 5、`[1m]` 和旧 classifier 负例。
- 通用 detector 覆盖 Fable、Opus、Sonnet 与真实 Haiku 形状正例，以及 stream、x-app、未知 system block、重复 billing/identity/classifier 和缺失 marker 负例。
- 归因改写测试覆盖 billing 缺失、已有 billing+CCH、已有 billing 无 CCH、system 顺序、CCH 有效性、已有身份不重复和重复执行幂等。
- Gateway 代理测试覆盖注入开关关闭/开启、Haiku 与基线正文一致、已有身份不重复、Session Hello 仍执行、窄 mock 本地返回和非法代理失败关闭。
- mock 测试覆盖四状态 schema、API/auth 硬阻塞、自动复查优先级、用户门槛、可选追加任务和未知状态回退。
- TLS client factory 覆盖相同代理复用、不同代理隔离、关闭连接池和非法代理不缓存直连客户端。
- Settings 测试覆盖默认值、旧库迁移、GET/PUT 校验、mode 与注入开关独立热刷新；前端构建必须验证两个控件均可持久化。
- 完整验证运行 `cargo fmt --check`、classifier/settings/CCH 定向测试、`cargo test`、前端 `npm run build`、`git diff --check` 和敏感内容扫描。

### 7. Wrong vs Correct

#### Wrong

```rust
if !is_cli_status_classifier {
    if let Some(real_session_id) =
        session_hello_probe_session_id(&path, client_type, &body_map)
    {
        // 执行既有 Session Hello 链路。
    }
}
```

分类识别只应选择日志、模拟或正文改写策略；用它改变既有 Session Hello 条件，会使默认关闭的注入开关也产生行为回归。

#### Correct

```rust
if let Some(real_session_id) = session_hello_probe_session_id(&path, client_type, &body_map) {
    // 执行既有 Session Hello 链路。
}
```

Session Hello 继续由原有 probe 条件决定；classifier 配置只在同一既有代理链路内选择 mock、identity-only 或归因补齐。

#### Wrong

```rust
let client = reqwest::Proxy::all(proxy_url)
    .ok()
    .and_then(|proxy| builder.proxy(proxy).build().ok())
    .unwrap_or_else(reqwest::Client::new);
```

代理配置或指纹客户端构建失败会被吞掉，随后从宿主机直连；同一辅助请求还可能进入通用正文和全文日志链路。

#### Correct

```rust
let client = get_request_client(&account.proxy_url)
    .map_err(|_| AppError::BadGateway("upstream request client unavailable".into()))?;
```

共享 client factory 只缓存成功构建的客户端，非空代理失败立即向上传播；Gateway 对 classifier 单独选择正文改写和 summary-only 日志策略。

## Scenario: v3 重授权凭据导入与迟到回包保护

长期刷新权、上游活动排空、交接回执与双栈存储统一遵循 [凭据单一所有者与交接协议 1](../../orchestrator/backend/account-runtime-v3.md#scenario-v3-凭据单一所有者与交接协议-1)。这里的短期登录租约、导入幂等与认证状态恢复不能绕过该门禁；已提交导入操作通过所有权回执的 `import_operation_id` 关联。

### 1. Scope / Trigger

- 修改 CLI 重授权导入、OAuth 回执/锁、登录维护租约，或刷新/401 的认证状态写入时适用。bench 的暂存与恢复流程见 [固定账号环境](../../orchestrator/backend/account-runtime-v3.md#scenario-v3-关联重授权提交与恢复)。

### 2. Signatures

```text
POST /admin/accounts/:id/oauth-credentials/import
GET  /admin/accounts/:id/oauth-credentials/import/:operation_id
OAuthCredentialImport {
  operation_id: String, owner: String, generation: String, email: String,
  account_uuid: Option<String>, organization_uuid: Option<String>,
  access_token: String, refresh_token: String, expires_at: i64
}
oauth_credential_imports(
  operation_id TEXT PRIMARY KEY,
  account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  request_hash TEXT NOT NULL, created_at TEXT NOT NULL)
AccountService::import_oauth_credentials(id: i64, input: &OAuthCredentialImport)
  -> Result<OAuthCredentialSnapshot, AppError>
AccountService::oauth_import_status(id: i64, operation_id: &str)
  -> Result<Option<OAuthCredentialSnapshot>, AppError>
AccountService::disable_oauth_for_failed_token(id: i64, failed_access_token: &str, reason: &str)
  -> Result<bool, AppError>
RuntimeGate::begin_oauth_import(owner: &str, generation: &str)
  -> Result<OAuthImportPermit, AppError>
```

### 3. Contracts

- 两路导入/对账要求管理 Bearer 和 `x-v3-service-token`；`V3_RUNTIME_URL` 非空，`V3_INTERNAL_TOKEN` 至少 32 字节且恒时比较。浏览器不持内部秘密，不公开凭据快照。
- DTO 拒绝未知字段。操作 ID 为 32 位十六进制；bench 生成小写 UUID hex。邮箱非空且最多 320 字节；AT/RT 非空、各不超过 16384 字节且只含非空白可见 ASCII。新提交有效期为 UTC 毫秒，至少剩余 60 秒。
- 原账号须为 OAuth；邮箱、已有非空 UUID/组织按 trim/ASCII 忽略大小写匹配。原 UUID/组织已存在时，新值不可缺失。接口不修改设备、画像、代理或身份字段。
- 复用 `oauth:refresh:account:{id}` 的 Memory/Redis 锁：TTL 30 秒、500ms 间隔最多 20 次等待。锁内重读回执/账号，首次导入要求未过期、claimed、exclusive 的同代 `login:` 租约，active/importing 均为 0。
- 凭据、回执与认证恢复同事务写入；按原 AT/RT、状态、停用原因、邮箱及 UUID/组织做条件更新。冲突回滚回执。SQLite/PostgreSQL 共同幂等建表，回执只存请求 SHA256 与元数据，不额外保存令牌。
- 同操作、同账号、同载荷返回当前权威快照，不重写首次 RT；载荷/账号冲突拒绝。提交响应包含 `imported:true`、账号/操作 ID、AT/RT/毫秒有效期。对账无回执返回 `imported:false` 与账号/操作 ID；导入仍在途时返回不可确认错误，不能伪报未提交。
- 导入清旧 auth_error。仅 disabled 且 auth_error 等于 disable_reason、原因属于已有 OAuth 401、缺 RT 或已分类的非 429 客户端 `invalid_grant` 时恢复 active。支持已有 `permanent credential failure: ` 前缀；人工/其他停用、限流及未知配置保持，不调用会清限流的通用 enable。
- import permit 固定在途占用，release 在 importing 非 0 时拒绝。`fence` 仅同代排他 `login:` 租约使用，将 phase 写为 reconcile、expires_at=0，撤销后续导入；已在途事务仍须对账收口。
- 所有 OAuth 刷新成功/失败/缺 RT 写入按调用时 AT/RT 条件更新；失配丢弃旧结果并重读。gateway/count_tokens/prime 的 401 按实际失败 AT 重读，再以当前 AT/RT 和 active OAuth 条件停用，不能用刷新前的账号副本停用刷新后的结果。prime 的失败 AT 仅内存传递，不进日志/回执；转发与重试协议保持。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|---|---|
| 缺管理或内部服务证明、非 v3 | 401 |
| DTO/令牌/操作 ID/身份/有效期不合法 | 拒绝；service 的 BadRequest 为 400，JSON 结构错误由 Axum 拒绝 |
| 登录租约不存在 | 400，不导入 |
| 非 claimed 同代登录租约、未排空、锁等待超时、条件写入失配 | 503，不释放维护门禁 |
| 同 ID 不同载荷、对账账号冲突 | 400，原凭据/回执保持 |
| 回执已提交且租约已失效 | 只读返回当前快照，不再次导入 |
| 导入未知或仍在途 | 503，不能返回 imported:false |
| 迟到刷新/401，或已人工停用 | 条件写入不命中，保持新凭据/状态 |

### 5. Scenarios and Examples

- 正常：原登录租约导入一次，再查询同操作回执；只更新原账号，设备与限流不变。
- 基础：人工停用账号仍可修复凭据，但保持 disabled；认证恢复与养号开关、额度门禁分开。
- 错误用法：响应丢失后生成新操作或再次覆盖第一次 RT。正确处理：保留原操作/载荷，查询回执后使用当前权威快照。
- 错误用法：锁 TTL 足以防旧回包，或按旧账号 ID 无条件停用。正确处理：OAuth 锁加 AT/RT 条件写入；401 使用实际失败令牌。
- 错误用法：取消时先 release 再查询。正确处理：先 fence，等待在途提交确定，清理暂存后才 release。

### 6. Tests Required

- `login_import_*`：只恢复认证停用、保留限流/身份；UUID/组织缺失冲突；条件更新回滚回执；同操作返回进一步轮换后的 RT。
- gateway/prime 的迟到 OAuth 401 回归：新凭据保持 active；人工停用不被旧请求覆盖；普通刷新后再次 401 仍按既有规则停用。
- `login_import_fences_late_calls_and_prevents_early_release`：在途 pin、fence 后拒新导入、释放前 API 关闭、确认后放行。
- `cargo fmt --check && cargo test --locked`；SQLite 实测及 PostgreSQL SQL 兼容检查。隔离临时 DSN 未配置时明确记录已有 PostgreSQL 测试 skipped/ignored。

## 设置热刷新模式

新增全局 setting 通常要经过这些位置：

```text
src/store/settings_store.rs     默认值常量
src/store/db.rs                 首次插入默认值 / 旧值迁移
src/handler/router.rs           GET/PUT 校验与 reload 调用
src/service/gateway.rs          RwLock 缓存、reload_* 方法、热路径读取
apps/web/src/api.ts                  前端类型或字段
apps/web/src/components/Settings.vue 控件和文案
```

不要只在 `settings_store.rs` 加常量。漏掉 reload 会导致 UI 写入后服务仍用旧值；漏掉 migration 会导致老实例没有默认值。

画像选择配置通过 `reload_profile_selection_config` 将 mode/default 一次性读入同一把 `RwLock`。请求通过原始 UA 准入后、读取 body 前冻结选择；客户端模式的重试和异步回调复用该画像，不能随 reload 串版。完整配置、账号副本及遥测/缓存契约见 [按客户端 UA 选择请求画像](../protocol/claude-code-profile-upgrade.md#scenario-按客户端-ua-选择请求画像)。

## 后台任务边界

- `UsagePollerService` 负责 OAuth usage 主动刷新，不应写网关热路径状态。
- `PrimePollerService` 负责峰值预热调度，发出的请求也可能命中网关治理规则；新增拦截规则时必须说明是否影响预热。
- Telemetry 自动代发必须遵守隐私边界，不发送 prompt、tool input、响应正文、token 或 cookie。

## Scenario: 按账号后端执行峰值模型预热

### 1. Scope / Trigger

修改 `PrimePollerService` 的调度、原生发送、故障处理或预热记录时适用。峰值模型调用与原生进程准备分别核验。

### 2. Signatures

- `peak_prime_enabled/hours/model` 沿原字符串设置；`check_once` 使用服务器本地时钟，`check_at(DateTime<Local>, &mut Option<(NaiveDate,u32)>)` 承担同一调度判断。
- `send_prime_upstream(&Account, &HashMap<String,String>, &[u8]) -> Result<reqwest::Response,String>` 为 async，按目标账号 `request_backend` 分流。
- native 复用 `runtime_transport::prepare`、`native_ready_for_version` 和 `submit_native(NativeSubmission, Duration)`。
- `GET /admin/prime-logs` 返回原 `PrimeLogEntry` 数组，沿 `prime_logs` 最近200条倒序与原字段合同。

### 3. Contracts

- 服务器本地 `HH:10` 触发，30秒扫描，进程内同日同小时只领取一次。沿原启用开关、小时、模型、活跃账号范围、冷却跳过及500ms账号间隔。
- 每次预热绑定本次目标账号，使用 hi、max_tokens=512、stream=true。`native293` 账号直接向 native 发送普通API形状输入，由CLI完成装配；账号有效画像为280时选280，其余沿既有原生分流进入293。已有旧后端继续原发送合同。
- native私有信封的目标必须为无查询参数的 `/v1/messages`；旧固定地址末尾的 `?beta=true` 由原生SDK处理。不得将旧完整URL直接复用到拒绝query的私有原生入口。
- 保持维护、凭据活动和账号占用许可至响应耗尽。native准备与首响应由外层30秒期限约束，sender取得剩余总预算（首响应加读流最多90秒），收到响应后仍按原60秒读流期限处理。
- OAuth首次401恢复凭据后原账号重试一次，最终401、429、403沿原后台状态联动及失败AT条件写入。后台预热沿原重试、槽位和RPM口径，真实提交不经过 `handle_request` 的重新选号或客户端预热拦截。
- 结果沿原HTTP状态口径：HTTP成功后耗尽响应；读流错误或超时继续记录原成功语义并写警告，HTTP状态与流终态分别核验。进程准备保持零模型调用，状态归环境页；模型调用结果进入设置页预热记录。
- 日志错误片段保持原200字符预算；UI完整呈现已有error_message，真实0耗时保留。发送错误使用受控原因，原生能力缺失保持原生失败归属。

### 4. Validation & Error Matrix

| 场景 | 结果 |
| --- | --- |
| 关闭、未选小时、非:10、同日同小时重复tick | 本轮零新增模型调用 |
| 活跃但处于冷却 | 记录skipped及0ms |
| native能力缺失 | 记录本账号失败，模型发送为零 |
| OAuth401、最终401/403、429 | 原账号恢复一次或原后台状态联动 |
| 首响应超时 | 按30秒预算终止等待，记录本次失败 |
| HTTP200后断流 | 按原成功口径记录，流故障保持可观测 |

### 5. Scenarios and Examples

- 正常：账号画像280，通过280实际CLI发出配置模型的hi请求，日志保留该账号与触发小时。
- 边界：先准备进程，模型计数保持0；到点后才出现真实模型调用。冷却账号只增加跳过记录。
- 错误用法：向native信封传旧 `?beta=true` 地址，或只改内存画像便断言测试使用280。正确处理：使用无查询参数的固定私有目标，通过专用画像写入接口准备账号，并从实际TLS请求核对版本。

### 6. Tests Required

- `service::prime_poller::tests`：开关、时点、小时、日期去重、活跃与冷却范围、原401恢复与迟到凭据保护、429/403联动，native能力不足时旧路径发送为0。
- `scripts/testing/cc2api-native.ts` 的 `CCRB_TEST_PRIME_ONLY=1`：280/293各验证零模型准备、200实际SSE、429/403/401及冷却跳过；额外验证30秒首响应超时与HTTP200后断流，共10次模型请求和12条正式日志。独立核对TLS实收CCH、来源版本、身份、模型、512及stream。
- `verify_prime_history_ui.py`、Web构建、`cargo fmt --check` 与 `cargo test --locked`；界面呈现见[系统设置记录合同](../../web/frontend/ui-guidelines.md#系统设置表单与草稿)。

## Common Mistakes

| 反模式 | 风险 | 正确做法 |
|--------|------|----------|
| 在 handler 里直接拼 SQL 或写调度逻辑 | 路由层膨胀，测试困难 | 放进 service/store |
| 新 setting 只改默认常量 | 老 DB、UI、热缓存不同步 | 按 settings 热刷新模式全链路更新 |
| 网关读 body 后继续转发原 request | 上游收到空 body 或旧 body | 明确重建 request body |
| 粘性会话遇到限流直接换号 | Claude Code prompt cache 被破坏 | 粘性请求等待或本地返回 |
| CCH 之前/之后插入 body 改写顺序不清 | 请求签名不匹配真实客户端 | 所有 body 改写先完成，再统一算 CCH |

## Scenario: v3 CLI 本地身份来源导入

### 1. Scope / Trigger

- 修改 `POST /admin/accounts` 的 `cli_identity`、来源白名单或首次 CLI 账号同步时适用。固定 HOME 读取及两端同步见 [v3 身份契约](../../orchestrator/backend/account-runtime-v3.md#scenario-v3-原生-tls-账号身份与同步)。

### 2. Signatures

```text
CliIdentityImport {device_id, environment_id, source, canonical_env, canonical_prompt}
CliIdentityImport::has_confirmed_source() -> bool
AccountService::create_cli_account(&mut Account) -> Result<(), AppError>
```

### 3. Contracts

- 仅在既有管理 Bearer 与有效 `x-v3-service-token` 校验后导入；普通管理密码不能代替内部服务证明。
- 原 `cli:/v1/messages:metadata.user_id.device_id` 来源继续支持。新增 `cli:2.1.293:config.userID` 仅接受 canonical_env.version / version_base 同为 `2.1.293`，依据独立官方 CLI 禁网请求实证，不开放任意版本或配置字段。
- 服务层继续校验设备 ID、Linux 运行环境和 prompt 环境并直接保存已确认身份，不随机生成替代设备；已有账号通过绑定流程检查，不能借首次导入覆盖旧设备。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|---|---|
| 合法内部证明、环境与已验证来源 | 按原设备创建账号 |
| 缺内部证明／未知 source／配置来源版本不匹配 | 401，不创建账号 |
| 设备或运行环境不完整 | 400，不创建账号 |

### 5. Scenarios and Examples

- 正常：bench 读取 2.1.293 固定 HOME 的有效 userID，并以准确来源创建账号；保持同一设备。
- 基础：旧正式请求观察仍走原来源，未验证版本不得假称已验证本地映射。
- 错误用法：只放开 source 字符串而不绑定版本。正确处理：白名单来源与 version / version_base 同时匹配，并保留内部鉴权及服务层校验。

### 6. Tests Required

- `cli_identity_sources_require_verified_version`：精确版本通过，版本／version_base 不匹配、未来版本和 machineID 来源拒绝；旧观察兼容。
- `cli_identity_import_requires_internal_service_proof`：只有管理 Bearer 的 HTTP 请求返回 401。
- v3 隔离同步／重授权堆栈：正式同步请求创建后核对实际 SQLite 的 device_id 与持久 userID 相等，再验证重授权凭据和原账号保持；不访问真实 OAuth／模型。

## Scenario: v3 API 稳定会话、智能准入与平滑发送

### 1. Scope / Trigger

- 修改 `v3_scheduling`、`SchedulingStore`、Gateway 最终发送准入或管理端调度可视化时适用。`main` 在 `V3_RUNTIME_URL` 或 `V3_DEPLOYMENT_ID` 非空时装配；部分配置缺失仍由传输层失败关闭。
- 平滑发送预算只接管 API Gateway 的精确 `/v1/messages` 到账号 sender。反重力的 `generateContent`、`streamGenerateContent` 共用持久绑定，发送准入沿反重力原 RPM。原生 CLI、项目、养号、Hello、count_tokens 和后台独立请求不共享 Claude 发送预算；非 v3 Claude 保留原调度行为。

### 2. Signatures

```rust
V3Scheduler::begin(self: &Arc<Self>, token_id: i64, session_id: Option<&str>) -> SchedulingRequest
V3Scheduler::begin_with_parameters(self: &Arc<Self>, token_id: i64, session_id: Option<&str>, parameters: &DiagnosticParameters) -> SchedulingRequest
V3Scheduler::begin_with_key(self: &Arc<Self>, key: Option<&str>, parameters: &DiagnosticParameters) -> SchedulingRequest
AccountService::select_v3_account(&self, request: &SchedulingRequest, exclude_ids: &[i64], allowed_ids: &[i64], context: &AccountSelectionContext, slot_units: u32) -> Result<SelectedAccount, AppError> // 异步
SchedulingRequest::admit(&self, account: &Account) -> Result<SendPermit, AppError> // 异步
SendPermit::submitted(self)
SchedulingStore::claim_current(&self, account_id: i64, key: Option<&str>, expected: Option<&SessionBinding>, last_released_at: Option<Instant>) -> Result<SendClaim, AppError> // 异步
SchedulingStore::claim_binding(&self, account_id: i64, key: &str, expected: Option<&SessionBinding>) -> Result<Option<SessionBinding>, AppError> // 异步
```

- `SchedulingStore::claim(account_id, interval_ms, now_ms, key, expected)` 是受控时钟验证入口；生产使用 `claim_current`，不能从选号快照传入旧 RPM／旧时间。
- 持久表：`gateway_session_bindings(session_key PK, account_id FK, revision, created_at_ms, last_seen_at_ms, expires_at_ms)`；`gateway_account_send_state(account_id PK/FK, last_admitted_at_ms)`。时间为非空 BIGINT UTC 毫秒，账号删除与两表清理同事务。
- 管理接口：`GET /admin/accounts/:id/scheduling` 返回 `{summary,snapshot}`；`GET /admin/accounts/:id/scheduling/sessions?page=1&page_size=20&state=all&prefix=` 返回 `{items,total,page,page_size,observed_at_ms}`。复用管理员认证。
- `AccountService::get_account_capacity_info(&Account) -> AccountCapacityInfo`（异步）只读取并发、队列与退避；`apply_scheduling_config(SchedulingConfig)` 替换统一选择器配置，`reload_scheduling_config()` 在启动时加载。独立部署只复用选择器的内存评分，v3 装配后与完整准入共享同一实例。

### 3. Contracts

- 网关在入站正文改写前解析会话。Claude V3 依次读取 `metadata.user_id` 的既有 session ID、`X-Claude-Code-Session-Id`、`X-Session-Id`，保留既有显式键域。反重力 Gemini 读取 `X-Session-Id`，使用独立显式键域。头只接受单值、非空白、无控制字符且最多 256 字节；通用头由网关消费。
- 无显式会话时，使用按平台和版本分域的 SHA256，输入包含 Token ID、入站模型、工具、系统指令和首个有效用户内容。对象键按序编码，数组维持输入顺序，Claude 已知协议块的 `cache_control` 不参与计算。后续轮次、客户端 UA、流式开关和上游身份不参与计算。没有可用的模型或首轮输入时沿无绑定路径。绑定表保存摘要，原协议 `session_hash`、上游池会话及策略封禁键各沿自身合同。
- 硬资格保留 Token 范围、账号状态、真实 5h／7d 控制线、Fable 门禁及既有故障排除。有效老绑定遇到本地并发繁忙、队满、发送等待或超时不迁移；新 v3 路径不再读写旧缓存绑定。
- 新会话先剔除完全无有界容量的账号，再保留人工优先级，组内优先即时容量。没有即时候选时仅进入可容纳且预计等待不超预算的队列；最终真实许可裁决竞争，排队不扣发送名额。
- 普通请求 2 单位、Haiku 1 单位及 `2 × concurrency` 个等待请求的 FIFO 保持。请求租约随并发许可和响应流存活，取消／结束 Drop 回收；不把长流与准入超时混为一类。
- 配置和绝对准入期限在请求开始时冻结。默认 120 秒，可配置 1–120；并发、退避、凭据、池／Hello、环境准备、发送及既有重试共用期限，不重置。实际提交后使用原 TTFB／流生命周期。
- 环境与身份验证完成后才进发送 FIFO；绑定 CAS 与当前发送许可同事务。CAS 冲突回滚预算、释放当前资源并跟随最新绑定；响应结束不把旧账号写回。
- 反重力普通生成先按 Token、模型档位和附件资格筛选，在可接单档位内优先使用原绑定。原账号临时繁忙时等待其并发和 RPM，暂停接单时返回 503 并保留绑定。准备凭据及传输后调用 `claim_binding`，获胜后进入原 RPM；CAS 冲突释放候选资源，在同一请求截止前重新选号。已核验的工具接续或重读沿原工具轮账号和许可处理，不用会话键重新选号。
- 取得发送行写锁后读取账号表当前 RPM 并采样时间。间隔 `ceil(60000/RPM)` 毫秒，非正值不限；绑定 CAS 后、提交事务前记录认领时间。等待不持数据库锁，不积攒空闲名额或分钟补发。
- `SendPermit` 持有公平队首至真实提交记点，释放时保存单调时钟；下一裁决同时检查持久时间和真实已过间隔。不能把数据库／提交准备耗时抵扣后一个请求的间隔。已认领但取消／发送失败保守消耗名额，不生成假提交点；空闲队列至少保留最大间隔 60 秒后才可回收。
- `AccountService::update_account`／`update_account_options` 成功保存后通知对应发送队首；等待者重新读取 RPM，支持调低和调高，但原截止时间、协议身份快照不变。仅重新传入旧 `Account` 不能覆盖当前 RPM。
- SQLx Any 读取这些整数时使用 `CAST(... AS TEXT)` 再严格解析 i64，表中仍保存 BIGINT；SQLite 的运行时 INTEGER 可能经 Any 按 i32 映射，不能仅用 Rust `get::<i64>` 假定完整毫秒。分页排序使用底层数值列，不能按文本投影排序。
- 绑定闲置 TTL 为 60 分钟。独立维护循环每分钟按当前 revision 批量续租活动绑定，不推进最近活动；读取不续租。过期清理批次上限 200、每轮最多 50 批；旧版本不能续租或覆盖新版本，重建 revision 不复用。
- 智能因素为可用负载、有效剩余额度、真实健康、首输出延迟，均高分优先。`Account::usage_quota(now: i64) -> UsageQuota` 为评分和后台重置扫描共用投影；`remaining` 取有效普通 5h／7d 剩余额度的最小值，缺少有效观测时为 0.5。合法未来 reset 或明确 `utilization=0` 且 reset 缺失／null 的窗口参与评分；非法资料保持未知，过期窗口等待新观测，不直接推算满额。
- `factors.quota_state` 为 `unknown/reset_pending/observed`：存在合法已到期窗口即为 `reset_pending`，其余有效窗口仍可参与评分；没有到期窗口且存在有效观测为 `observed`，否则为 `unknown`。管理页区分待自动刷新与尚无有效观测，前端以可选字段兼容旧响应。未知健康与首输出延迟均从 1.0 满分起步，让冷启动账号获得真实反馈机会；未知额度仍为 0.5。初始失败率为 0，首次成功健康为 1.0，首次普通失败健康为 0.8，首次容量拒绝健康为 0.6；后续沿既有 EWMA 与时间衰减更新。真实终态反馈复用现有观察器，HTTP 200 SSE 错误不算成功，用户输入错误、取消、本地拒绝和采样缺失不污染健康，不主动探测模型。
- 首输出从准入后真正提交的 `AttemptTrace::commit` 开始计时，取已有有界解码观察器第一次看到的非空文字／思考 delta、工具参数 delta、有效文本／思考块或带有效 id/name 的 tool_use／server_tool_use；忽略头部、心跳、元数据、空白和签名。非流式 message JSON 在完整解析后记点。仅成功且完整并观察到有效输出时更新延迟；失败、取消、不完整、无输出或无诊断不能用响应头补值。
- 请求开始时冻结 `model/thinking_type/thinking_budget/effort/stream` 白名单事实，缺失保持未知；每账号最多 64 组成功延迟 EWMA，淘汰最近采样最旧组恢复未知满分基线。实际选号只读取同组，管理页 `factors.latency` 为全部成功首输出的账号汇总，文案必须说明区别。健康继续按账号共享，5 分近优轮换不变。
- `AttemptDiagnostic.first_output_ms: Option<u64>` 为新增可选 JSON 摘要；历史缺失为 None，不迁移、不回填。原 `ttft_ms` 保留响应头耗时语义，不改变历史与上游遥测载荷。
- 默认四项权重 `1/0.8/1/0.5`；健康普通 EWMA 0.2、容量拒绝 0.4、失败半衰期 15 分钟、延迟尺度 10 秒。智能近优差值 0.05 内按稳定账号 ID 轮转；所有选号统一智能评分，响应 `config.mode` 固定为 `smart`。旧排序、阶梯评分、旧权重缓存及 `scheduling_score/scheduling_detail` 已退役，容量统计独立保留。
- 重置偏好仅采用合法未来普通窗口，单窗口 `h/(h+remaining_seconds)`，`h=周期秒数/7`；按 5h／7d 窗口权重平均，缺失周期贡献 0。重置主权重或窗口权重全零时关闭，基础分按原四因素加有效重置权重归一化。
- 排队主权重仅在候选都需要等待时参与选择，即时候选只用基础分。启用时运行负载使用 `1/(1+active_units/max_units)`，排队与发送等待独立计分；关闭时复用原负载公式。并发等待按 `max(active_units+queued_units+request_units-max_units,0)/max_units*service_ms` 估算，和容量快照中的发送等待取最大值，等待偏好为 `1/(1+wait_ms/10000)`。
- `service_ms` 来自同组完整成功终态的总耗时 EWMA，与首输出独立；总耗时小于首输出或样本不完整时不更新。无同组服务耗时且确有并发等待时，按运行／排队压力与已知发送等待回退，估计毫秒为 null。服务耗时复用每账号最多 64 组的现有表；查分读取内存，缺样本不等待。
- 新摘要包含 `reset/queue/wait_score/estimated_wait_ms/wait_basis`；`score` 为基础分，`wait_score` 为等待排序分，`wait_basis` 为 `pacing/sampled/pressure`。管理端等待估算为账号汇总，实际选号限定请求参数分组；未知时长与压力回退明确展示。

| 字符串 setting | 默认 | 校验 |
| --- | --- | --- |
| `v3_admission_wait_seconds` | `120` | 整数 1–120 |
| `v3_smart_weight_load` | `1` | 有限数 0–10，至多一位小数 |
| `v3_smart_weight_quota` | `0.8` | 同上 |
| `v3_smart_weight_health` | `1` | 同上 |
| `v3_smart_weight_latency` | `0.5` | 同上 |
| `v3_smart_weight_reset` | `0` | 同上；重置偏好主权重 |
| `v3_smart_weight_queue` | `0` | 同上；仅等待选择生效 |
| `v3_smart_reset_weight_5h` | `1` | 同上；5h 重置窗口贡献 |
| `v3_smart_reset_weight_7d` | `1` | 同上；周重置窗口贡献 |

- 默认值由 `V3_SCHEDULING_DEFAULTS` 共用；更新在设置锁内合并、整体校验、事务保存，再原子替换已校验快照，不能二次读库使并发更新回退。有效主权重总和必须大于 0；仅排队权重启用时即时候选等偏好轮转。
- `SettingsStore::ensure_scheduling_defaults()` 在启动时事务补齐缺失键，保留管理员新配置，并清理 `OBSOLETE_SCHEDULING_KEYS` 中的旧模式与三个旧权重。管理 GET 隐藏、PUT 忽略废弃键；冻结迁移基线保持原定义。
- 账号列表新增可选 `v3_scheduling`／`v3_scheduling_error`，详情 `summary` 包含 config、factors、capacity、绑定／活跃会话、无当前绑定请求、各阶段及下一许可。`capacity.reason` 为 `ready/concurrency/pacing/queue_full/wait_budget/pending_submissions/account_unavailable`；无准入容量或前方有准备请求时不得显示 ready。
- `snapshot` 含 observed/history_available_from、截断／丢失标记、独立 60 秒提交统计、当前请求与真实提交事件。事件最多 5 分钟、每账号 500、全局 10000；重启有历史缺口，不补造过去或未来点。实心点是 Gateway 发起 sender 提交，空心点是预计最早许可，不能宣称供应商已接收或未来已预订。
- 会话分页 page≥1、page_size 默认 20／最大 100，state 为 all／active／idle，prefix 为最多 64 位十六进制。只返回匿名摘要及时间、阶段，不返回正文／原 SID／revision／凭据。绑定会话、不同活跃会话、请求及上游 Session 池槽位分别统计；同一会话可同时有多个阶段请求。
- 管理读取无调度副作用，不续租、消费许可或唤醒环境。详情沿用 5 秒刷新，仅打开且页面可见时读取；关闭／隐藏取消，防重叠和旧响应覆盖。失败保留原快照并标记陈旧，倒计时在浏览器递减且标为预计。会话总数缩小致页码越界时，同轮最多回读一次第一页，成功后一起更新页码与数据；归零保持第一页。
- 不改官方缓存参数、正文前缀、上游池、TLS／身份冻结或原始压缩／流字节；既有实际重试均过发送闸门，不新增重试次数／迁移条件。两个新增主权重归零可回到基础智能排序；完整回退使用旧构建并保留增量表。此合同不等于官方账号安全阈值或缓存命中保证，也不包含多实例全局并发调度。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 有效老绑定但并发繁忙／队满／等待到期 | 原账号等待或本地 429，保留绑定，`Retry-After: 1` |
| 新会话没有有界容量 | 本地 429，不提前绑定或消费发送名额 |
| 同 key 并发认领不同账号 | CAS 唯一赢家，失败事务预算回滚 |
| 反重力首次绑定竞争／原绑定暂停接单 | 冲突候选释放资源并跟随现绑定／返回 503，保留绑定 |
| 写锁／环境同批就绪／分钟切换／重启 | 不积攒许可；持久与单调时钟共同控制提交间隔 |
| 等待中调整 RPM | 当前值参与下一裁决，唤醒等待但不重置期限 |
| 调度状态不可读写／数值非法 | 固定 503，停止新增提交，不泄露底层错误 |
| 本地 mock／缓存命中或提交前取消 | 不造实际提交事件／attempt，不污染上游健康 |
| HTTP 200 内 SSE 错误 | 原字节透传，现有完整终态进入失败反馈 |
| 只有头部／心跳、无有效输出或仅有其它分组样本 | 首输出保持未知，延迟分沿用 1.0 基线；不得伪造首输出样本 |
| 普通旧窗口已到期／没有有效观测／零用量且 reset 为 null | `reset_pending`／`unknown`／`observed`；零用量剩余额度为 1 |
| 即时容量／全部需等待／无同组耗时 | 基础分／等待排序分／压力回退并标记时长未知 |
| 到期或缺失重置时间／历史旧模式 | 重置奖励 0／统一智能评分，废弃设置隐藏 |
| 管理未认证／参数越界 | 401／400，读取不改变绑定或发送状态 |
| 页面隐藏／关闭、读取失败、会话骤减 | 停止刷新／保留陈旧快照／有界回读第一页 |

### 5. Scenarios and Examples

- 正常：A 已绑定且繁忙、B 空闲时，老会话留 A，新会话可进 B；50 RPM 的发送间隔至少 1200ms。
- 基础：无显式 SID 且无有效首轮输入时按无绑定请求准入；网关重启恢复有效绑定与许可时间，时间轴从新进程采集起点开始。
- 正常：同一 Token 的两个 API 请求保留相同模型、工具、系统指令和首轮用户内容，第二次追加历史并切换流式，仍查到同一绑定。单轮客户端可用 `X-Session-Id: chat-42` 关联后续不同输入。直接以全文或 UA 派生会使追加历史或更换客户端时的关联丢失，应使用冻结的入站会话键。
- 正常：同等条件下 1 小时后重置的窗口获得高于 3 小时窗口的偏好；等待模式中，较快账号即使排队单位更多，也可因较短的成功总耗时估计获选。错误用法是用首输出替代并发槽释放耗时；正确处理是分别保存成功总耗时与首输出。
- 边界：旧 5h 到期且 7d 已用 4% 时，状态为 `reset_pending`，额度分沿用有效 7d 的 0.96。刷新取得 5h 零用量且无 reset 后，状态为 `observed`，额度分仍为 0.96；错误做法是把明确零用量也当未知，正确处理是接受该官方观测。
- 边界：头部 100ms、首个有效思考 3000ms 时，调度使用 3000ms；错误做法是沿用 `ttft_ms=100`，正确处理是读取成功终态的 `first_output_ms` 并写入请求冻结分组。
- 边界：同优先级、容量和额度相同的冷启动账号与成功首输出 1 秒的账号均可进入近优轮换。错误做法是为未知健康预置 50% 失败率；正确处理是从零失败率开始，用真实反馈更新。
- 错误用法：在数据库等待前采样时间、用选号快照 RPM，或取得许可后立即丢弃再准备提交，会在写锁释放／限额调整时误放行。正确处理：生产调用 `claim_current`，并将许可持有到提交边界：

```rust
let permit = request.admit(account).await?;
// 此处只做已准备请求的轻量提交收口，不再等待环境或解析大正文。
permit.submitted();
transport.submit(prepared, body, ttfb_timeout).await
```

- 错误用法：把同会话的两个请求算成两个会话、把池槽位当官方会话，或在绑定减少后只更新 total 而保留越界页码。正确处理：按 key 去重、阶段单独计数，页面越界回读第一页。

### 6. Tests Required

- `unknown_feedback_baseline_allows_near_best_rotation`、`health_feedback_starts_from_healthy_baseline_and_decays`：未知健康／延迟为 1.0、额度为 0.5；实际近优轮换、首次成功／失败／容量拒绝、十五分钟半衰期及成功恢复。分组隔离与 SSE 错误反馈回归沿用满分未知基线。
- `tests/v3_scheduling_test.rs`：SQLite／隔离 PG 共用 CAS、回滚、完整 UTC 毫秒、续租、清理、账号删除及跨分钟／重启合同；不得只用小于 i32 上限的模拟时间证明持久精度。
- `service::request_session` 和 `v3_messages_routes_and_records_derived_sessions` 覆盖首轮内容稳定性、非法头、Token／平台隔离、显式旧绑定及双账号优先级变化。`verify_agy_gemini.py::verify_session_affinity` 以真实 HTTP 验证两次首轮先选不同账号、实际提交同账号，以及暂停和过期后的行为。
- `sqlite_write_lock_and_held_permit_cannot_bank_send_time`：写锁延迟后才采样；持有许可时后续不抢跑，提交后仍符合间隔。
- `waiting_requests_reload_current_rpm_without_resetting_deadline` 及 PG `current_rpm_contract`：300→60、1→300，旧快照不能绕过新 RPM，唤醒及时，期限不变。
- `capacity_reason_matches_pending_work_and_wait_budget`：无容量时非 ready，前方请求和超期各有原因；原有绑定、Token 隔离、近优轮转、取消、状态故障与只读查询回归保持。
- Gateway 的 `v3_real_http_disconnect_releases_waiting_request`／`v3_real_http_stream_disconnect_releases_execution`、`v3_pacing_timeout_preserves_binding_and_has_no_attempt`、`v3_sse_error_feedback_uses_existing_body_observation`；真实本地 HTTP 验证资源与原始字节。
- `first_output_*` 覆盖有效内容／空白、完整 JSON、先头部后内容、旧诊断、成功 EWMA、失败和取消不更新、跨模型／思考／stream 隔离、实际选号和 64 组上限；`long_initial_blank_lines_preserve_usage_across_codings_and_chunks` 同时断言全部受支持编码与分块的首输出。
- `quota_observation_distinguishes_reset_unknown_and_zero_usage`／`refreshed_quota_changes_actual_selection`：覆盖到期、未知、非法值、零用量无 reset、多窗口约束与刷新后的实际选号；前端以合成接口验证两种状态文案及旧响应兼容。
- `scheduling_preferences_*`：新权重校验、有效窗口奖励、等待实际选号与即时优先、失败样本排除、历史默认补齐与旧键退役、原子热更新；`scheduling_group_lookup_benchmark` 显式执行 1／8／32／64 组与 1／10／100 候选微基准，观测环境单独记录。
- `deploy/flower2api/verify_scheduling_preferences.py`：真实构建与合成 API 验证字符串保存／撤销、精度错误定位、失败草稿、旧评分移除、估算／回退、旧响应和 1440／390px。
- `cold_environment_ready_cohort_still_submits_smoothly` 保留正式归属校验，以本地 sender 验证同批就绪后的真实提交间隔与压缩字节。
- 管理路由覆盖鉴权、有界分页、读取不续租、设置合并校验与热刷新；前端构建之外验证单会话多请求、原因文案、三页缩为一页／归零、失败陈旧和隐藏／关闭暂停。完整 Rust 回归通过；本地合成数据不得描述为真实账号或生产验收。

## Scenario: 运行中账号普通配置热更新

### 1. Scope / Trigger

- 修改账号表单、`PUT /admin/accounts/:id`、普通配置 SQL 或队列缩扩容时适用。

### 2. Signatures

- `accountUpdateDelta(current: Record<string, unknown>, baseline: Record<string, unknown>): Record<string, unknown>`：相对打开编辑弹窗时的标量快照生成更新。
- `AccountService::update_account_options(&self, account: &Account, fields: &[&str]) -> Result<(), AppError>`（异步）。
- `AccountStore::update_options(&self, account: &Account, fields: &[&str]) -> Result<(), AppError>`（异步）。

### 3. Contracts

- 普通配置允许在 API／CLI 活动时更新：name、billing_mode、subscription_type、rate_limit_tier、concurrency、priority、rpm_limit、auto_telemetry、auto_poll_usage、allow_1m_models、allow_fast_mode、上游池 enabled/size/ttl/refresh_policy 与 5h/7d 控制线。SQL 只写提交白名单列和 updated_at，不能回写快照里的凭据、状态、身份、用量或进程指标。
- 前端只发送实际变化；空凭据表示不改，可空身份／套餐字段以 null 清除，expires_at 比较数值等价，明确清空以 null 提交。认证、代理、凭据、邮箱／账号／组织身份、有效期和状态修改继续走维护门禁；不能因为普通配置可热更新而放开环境维护。
- 管理更新 concurrency/priority 为正 i32 整数，rpm_limit 为非负 i32，0 不限；错类型／越界 400 且不部分保存。套餐改变且未提交真实 tier 时清旧 tier，不推断商业分级。
- 配置成功写库与队列调整共用队列写锁；原地调整并发，旧 Account 快照与目标不一致时只按持久当前值调整，读失败保留当前容量。缩容不取消已有流；先扣空闲单位，余下差额在许可归还前销毁，防止已排队请求先于后台回收抢跑。门禁等待时取消／超时也归还同一容量许可；再次扩容按最新目标，不遗留槽位吞噬任务。
- RPM 保存通知发送等待者重新读取当前限额；准入期限不重置，优先级影响后续新会话。套餐可空字段固定绑定文本并用 NULLIF 表达清除，避免 SQLx Any 的 NULL/文本在 PostgreSQL 预编译缓存中改变参数类型。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 活动 API／CLI，只改 RPM／并发／优先级 | 200，流与租约保持 |
| 真正修改代理／凭据且运行繁忙 | 保留维护拒绝，不中断现有活动 |
| 旧快照保存普通配置、期间 OAuth／状态已变化 | 只写提交列，保留新凭据与当前状态 |
| 两个普通请求运行，并发从 2 降至 1，旧等待者已排队 | 第一条结束不放新请求，第二条结束才可进入 |
| 数值非整数、负 RPM、非正并发／优先级或超 i32 | 400，原配置保持 |
| 套餐文本／清除反复切换 | SQLite／PG 同一连接正常保存，不出现缓存参数类型错误 |

### 5. Scenarios and Examples

- 正常：只改 RPM 40→20，表单发送 `{"rpm_limit":20}`，不附带未改的 auth_type／proxy_url。
- 边界：并发缩容期间已有请求自然结束；旧请求仍带旧 concurrency 时不能恢复旧上限。
- 错误做法：移除维护锁后整行 UPDATE，旧 RT 可能覆盖新 RT。正确处理：普通配置按白名单提交列更新，身份变更继续维护保护。

### 6. Tests Required

- `account_options_hot_update_preserves_active_api_cli_and_credentials`：活动 API 和共享 CLI 下保存成功、缩容目标生效、旧快照不回退、代理／凭据仍拒绝、状态与令牌保持、非法数值不写入。
- `account_queue_hot_shrink_*`：缩容前已排队请求不能抢跑、再次扩容无残留、门禁等待取消也正确归还；原加权 FIFO 与活动计数回归保持。
- `account_store_timestamp_test` 的 SQLite／独立 PostgreSQL 共享合同：选列保存保留并行状态、凭据和指标，未知字段整次拒绝，可空套餐文本／清除反复切换。
- `node --experimental-strip-types --test web/tests/accountUpdate.test.mjs` 验证增量载荷、凭据空值和清除；前端 build 与完整 Rust 回归通过。

## Scenario: 反重力账号并发上限在线调整

### 1. Scope / Trigger

- 适用于反重力账号编辑、网关队列容量、原生工作池及 Docker 角色额度变更。三角色初始分配见[账号运行环境合同](../../orchestrator/backend/account-runtime-v3.md#scenario-agy账号运行环境与gemini业务接入)。

### 2. Signatures

- 原管理入口 `PUT /admin/accounts/{id}` 接收整数 `concurrency`，反重力范围为 1 至 64。
- 受信 `POST /internal/v3/agy-capacity/{account_id}` 接收 `{operation_id,before,target,phase}`。操作 ID 为 32 位小写十六进制，`phase` 为 `prepare|settle|reconcile`。成功回执为 `{ok:true,operation_id}`。
- `GET /admin/runtime/accounts/{id}/config?capacity_operation=<id>` 可返回 `capacity_edit_active` 布尔值。省略查询参数保持既有配置响应。
- 发送器 `POST /internal/agy/capacity` 接收 `{account_id,environment_id,generation,max_workers}`，通过账号私有 Bearer 鉴权后核对当前配置并回传相同四字段。监督器命令 `capacity` 携带 `max_workers`、`restore_allowed`，对应 `capacity_applied` 回执。状态提供 `capacity_protocol=1`、`allocated_workers` 和生效的 `max_workers`。

### 3. Contracts

- 网关在原账号更新路径登记操作。扩容核对并实际应用角色及工作池额度后按列保存，在原 `AccountQueue` 增加容量。缩容先保存网关上限，原队列通过归还许可收紧准入。真实代理或组合凭据变更沿原维护边界。
- 监督器身份继续绑定账号、环境、代次、内核和代理。容量字段由原监督器在池锁内应用。已接单和待回填的实例继续运行，超出的空闲实例先回收，基础热进程保留到可用名额耗尽或原失效条件成立。CRIU 继续按当前额度准入。
- 编排器按同一资源计算更新角色 `Memory`、`MemorySwap` 和发送器 `PidsLimit`，核对实际容量和角色主进程。有限 RAM 在账号总额内分配，发送器额度为 `512 + 256 × max_workers` MiB，进程数额度为 `128 + 64 × max_workers`。缩容时在途数量或实际占用高于新额度则暂留原角色额度。
- 私有 `runtime/agy-capacity.json` 记录 schema 版本、账号、环境、代次、操作 ID 和原目标容量。准备中的合法差异继续使用原传输绑定。原操作结束后按持久 `concurrency` 收口；未知回包先查询实际资源及原回执，确认后清记录。新准备读取权威上限，停止环境保存容量时保持停止。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 容量非法、环境代次不符、原操作未持有 | 拒绝写入或应用该容量 |
| 旧运行发送器缺少容量协议 | 显示升级提示，保留原运行容量 |
| 内存不足或资源暂不可安全划拨 | 返回对应的资源原因，保留原网关上限 |
| 4 路在途时缩到 3 | 保留原许可和在途实例。继续按新目标归还许可和回收资源 |
| Docker 或发送器的应用结果未知 | 读取同代实例和已保存的网关上限后继续原操作 |

### 5. Scenarios and Examples

- 执行 3 路时提交 `{"concurrency":4}`。先确认发送器容纳第 4 个进程，再由原队列放行等待者。
- 缩容后仍有工具结果待回填时，回填沿原账号和进程执行。对应角色额度在实际占用允许时调低。
- 仅修改 `sender.json` 会漏过监督器回执与网关队列更新。通过原管理入口执行，按同一个操作 ID 比较角色和工作池实际状态。

### 6. Tests Required

- `test_agy_capacity` 覆盖有限额度、停止环境、连续缩扩、旧发送器以及 Docker 回包丢失恢复。`test_agy_supervisor` 核对动态进程数和原工具续接。
- `agy_sender_test` 核对鉴权、过时代次与配置不符的容量拒绝。`verify_agy_native_loopback.py --live-capacity` 验证同一监督器下 3→4→3、五笔请求各提交一次。

## Scenario: Claude 会话策略封禁

### 1. Scope / Trigger

- 修改消息或计数入口、上游策略拒答识别、提交边界、会话封禁存储、管理接口及设置时适用。Rust 与 native293 使用同一封禁合同。

### 2. Signatures

- `SessionPolicyBlockService::begin(self: &Arc<Self>, token_id: i64, body: &Value) -> Result<Option<Response>, AppError>`：异步，绑定原始会话身份并执行首次检查。
- `session_policy_block::check_current() -> Result<Option<Response>, AppError>`：异步，复查有效封禁并累计实际拦截。
- `session_policy_block::remember_current(account_id: i64, reason: &str) -> Result<(), AppError>`：异步，持久登记实际拒答。
- `SessionPolicyBlockStore::hit(&self,key:&str,now:i64) -> Result<Option<SessionPolicyBlock>,AppError>`：异步，原子增加有效轮次计数并等待写入完成。
- `GET /admin/session-policy-blocks?state=active&session_prefix=&page=1&page_size=20`；`POST /admin/session-policy-blocks/:id/release`，均使用管理员鉴权。
- SQLite 版本 4：`gateway.session-policy-blocks.4`；新增 `session_policy_block_keys(session_key,revision)` 与历史表 `session_policy_blocks`，定义位于 `store/session_policy_block_schema.rs`。迁移登记、校验摘要及发行来源同步；PostgreSQL 初始化应用同等增量结构。

### 3. Contracts

- 匿名键采用独立域 `flower2api:session-policy-block:v1`、Token ID 大端字节与改写前显式 SID 的 SHA256。上游池映射、诊断开关及换账号不能改变封禁身份；无可靠 SID 沿用原入口行为。新封禁表只保存摘要、模型字段、原因分类和可选诊断关联。
- 开关 `session_policy_block_enabled` 默认字符串 `true`；时长 `session_policy_block_duration_minutes` 默认字符串 `1440`，必须是可安全换算并加到当前时间的正整数分钟。设置保存后热刷新，时长在实际拒答识别时读取；修改不延长已有轮次。
- 关闭功能停止新封禁与本地拦截，历史保留；重新开启后未到期记录继续有效。到期或解除后再次拒答新增一轮。有效期内并发拒答通过数据库事务锁合并，重复拦截仅增加计数和最近命中时间。
- 命中计数的 `UPDATE ... RETURNING id` 使用 `fetch_all` 完整消费唯一ID结果及语句完成，再读取和返回记录，独立连接随即可见计数。SQLite首行可能早于隐式提交，写入完成边界沿[账号创建可见性](settings-database.md#scenario-创建账号的提交可见性)的同类规则；保持原SQL原子更新和失败停止放行语义。
- 入口检查在账号选择、Hello、排队及遥测激活之前；排队后与真正提交前复查。最终复查必须先于 `AttemptTrace::commit` 和 `SendPermit::submitted`，本地拦截保持零上游调用、零真实 attempt。许可在复查期间保持持有；已有在途调用沿原生命周期结束。
- 仅识别结构化错误、SSE error、refusal 内容块及 `stop_reason=refusal`；`reasoning_extraction`、safeguards flagged、Usage Policy 等匹配限定错误字段，普通回答引用保持正常处理。HTTP 401/429 保留原分类，明确策略拒答不进入账号停用或签名修复重试。
- 响应观察独立于诊断，复用有界解码与增量解析。SSE 拒答在当前帧交付前等待持久写入，原协议字节及 trailers 保留；完整 JSON 在结束观察时登记。观察上下文由响应流持有，不能依赖请求 task-local 在流读取时仍存在。
- 有效封禁返回 HTTP 400 Anthropic error，`error.type=invalid_request_error`、`error.code=session_policy_blocked`，`error.details` 含 `retryable=false`、RFC3339 `expires_at` 与向上取整的 `remaining_seconds`；封禁查询失败返回本地 503。`count_tokens` 只查已有封禁。
- 列表返回 `items,total,page,page_size,observed_at_ms`；条目包含匿名会话、令牌/账号摘要、模型、原因、诊断关联、起止及解除时间、本地拦截次数/最近命中与 `active|expired|released`。时间字段为 UTC 毫秒。`state` 接受 `all|active|expired|released`，默认 active；前缀最多 64 位十六进制，page≥1，page_size 为 1–100，默认20。列表仅读取，解除幂等并保留首次解除时间。
- 页面 `/session-blocks` 位于“网关 → 请求记录”下方，设置位于“系统设置 → 会话与调度 → 会话策略封禁”。复用共享控件、确认与反馈；错误保留上次记录，离页取消并丢弃旧回包。可见且未读取、未打开解除确认时每5秒刷新；倒计时以 `observed_at_ms` 加本地单调耗时计算，避免浏览器时钟偏差。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 同会话同 Token 有效封禁 | 本地400，计数增加一次，上游调用零增量 |
| 不同 SID/Token，共用上游池槽位 | 各自隔离判断 |
| 发送等待期间新增封禁 | 释放等待资源，零真实 attempt 与提交事件 |
| 普通正文引用政策词、认证或限流错误 | 原分类保持 |
| 查询故障 / 拒答写入故障 | 本地503 / 明确错误或响应体错误，不能宣称封禁成功 |
| 管理未鉴权 / 非法筛选、页码、时长 | 401 / 400，非法设置整次拒绝 |
| 关闭后重开 / 重复解除 / 到期后再次拒答 | 恢复未过期封禁 / 首次解除时间保持 / 新一轮历史 |

### 5. Scenarios and Examples

- 正常：首次拒答创建默认24小时封禁，再次“继续”本地400；管理员从列表解除后可再次请求。
- 边界：请求等待发送期间管理员将时长改为30分钟，随后上游拒答按30分钟新建；已有24小时轮次保持原截止。
- 错误做法：使用映射后的上游 SID 建键，或先调用 `trace.commit()` 再检查封禁。正确处理：入口冻结真实会话身份，所有本地复查通过后才记录真实发送。

### 6. Tests Required

- `session_policy_block_lifecycle_and_history`、`session_policy_block_concurrency_and_restart`：固定到期、计数、解除幂等、自然到期、新轮次、跨连接合并及重开持久。
- `session_policy_block_hit_is_visible_to_independent_reader`：连续命中后由独立连接池立即读取相同计数；排队复查用例同时断言 `session_policy_blocked` 与计数，避免其它400响应混入成功证据。
- `session_policy_block_duration_reload_preserves_existing_expiry` 与配置/识别测试：默认值、非法值、进行中请求取最新时长、隔离、关闭、正文与认证排除。
- `session_policy_block_gateway_stops_upstream_requests`、`session_policy_block_queued_request_rechecks_before_send`、`session_policy_block_v3_send_wait_has_no_attempt`、`session_policy_block_query_failure_is_local_503`：真实本地HTTP/SSE拒答、两后端前置拦截、计数入口、队列/发送复查、零上游调用和零attempt、许可回收及查询故障。
- 响应观察测试覆盖压缩/分块SSE及完整JSON拒答，断言原字节保留、诊断关闭仍登记。`session_policy_block_admin_contract` 验证鉴权、参数、设置热刷新、历史及SPA入口；版本3迁移用例保留自定义值。
- `verify_session_policy_blocks_ui.py` 使用真实前端构建的离线fixture，覆盖1440px/390px、服务器时钟、筛选分页、搜索空态、解除取消/失败重试、读取失败保留、设置直达及字符串保存；完整Rust回归、前端build及数据库定义/发行测试通过。


## Scenario: Gateway 明确429的共用决策

### 1. Scope / Trigger

- 修改Messages的native分流、429分类、账号切换、临时退避、并发许可或准入截止时适用。所有模型实际收到的上游HTTP429使用相同执行路径，模型范围及分类优先级继续由AccountSelectionContext和AccountService所有。

### 2. Signatures

- AccountService::handle_rate_limit_with_context返回RateLimitDecision::{Quarantined,RetryOtherAccount,RequestBackoff(Duration),PassThrough}。
- Gateway私有响应扩展RateLimitResponseDecision(Arc<RateLimitDecision>)保留完整决定；该扩展只在进程内使用。
- GatewayService::prepare_rate_limit_retry(response,account,scheduling,slot_guard,exclude_ids,backoff_retry_ids,last_response) -> Result<Option<Response>,AppError>：Some为立即交付的业务拒绝，None为继续原选号循环，原准入到期返回AdmissionLimited。

### 3. Contracts

- finish_forward_response完成被动额度观察、响应缓冲和分类后，保存完整决定。原有转发与native分支共同执行，不能只传递退避时长而丢失PassThrough。
- PassThrough返回当前429正文及必要响应头，本次请求结束。该分支不新增容量拒绝反馈，账号全局冷却保持原分类合同。
- Quarantined与RetryOtherAccount排除本次账号，释放槽位/凭据活动，保留末次429后重新选号。前者已写入账号冷却，后者保持模型级范围；实际绑定、Token allow/block、Fable门禁及容量规则继续由原选择器与claim/admit裁决。
- RequestBackoff复用原账号软退避，默认10秒，同账号每请求最多一次该类退避重试；再次命中按原规则进入排除分支。等待前释放槽位和凭据活动，V3等待受原SchedulingRequest绝对截止限制，重试不延长预算。
- 选号失败时，已有末次429按原有优先级返回；准入超时和已存在认证排除等分支保持原优先级。分类调用失败仍使用原有排除/末次响应兜底，不伪造业务分类。
- 每次实际提交建立独立job/attempt，身份按当次目标账号重建。签名修复返回的429同样进入共用执行；绑定CAS竞争按原循环重新选号。未知提交、断线、普通400及已交付输出各自保持原错误边界。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 明确429且分类为PassThrough | 返回该次429及正文，本次拒绝之后追加提交为0 |
| 账号容量拒绝 | 原分类写入冷却，排除后尝试合格候选 |
| Fable模型级拒绝 | 换本次账号，保持模型级状态边界 |
| 临时拒绝 | 同号有限退避重试，等待期间槽位为0 |
| 原1秒准入预算遇10秒退避 | 原期限到达后返回本地429，模型仅提交首次 |
| 退避期间下游取消 | 等待计数及槽位归还，停止后续提交 |
| 候选耗尽或Token仅允许原账号 | 保留并返回末次429，范围外账号发送为0 |
| 提交状态未知 | 原502路径，保持本次提交边界 |

### 5. Scenarios and Examples

- 正常：native A明确容量429后选择B成功，两次attempt的账号身份、源版本和请求UUID分别对应。后续相同会话继续由B承载。
- 边界：Fable周用量已达到设置阈值，首次选号直接使用合格备选；原账号未被本轮发送。
- 错误用法：只把RequestBackoff写入扩展，其余429一律换号。正确处理是传递完整分类，并让PassThrough立即返回。
- 错误用法：先持有并发槽位等待10秒，或为重试创建新准入期限。正确处理是先归还许可，再用原SchedulingRequest等待。

### 6. Tests Required

- business_rate_limit_passthrough_preserves_response_without_switching：原有直连和V3调度入口均只发送一次，保留429正文/request-id，账号冷却和槽位符合原规则。
- tests/native_rate_limit_fixture.py驱动native_rate_limit_gateway_roundtrip：280/293两版、21组场景覆盖容量/Fable/业务429、额度预过滤、Token范围、候选耗尽、签名修复后429、未知提交、1秒期限、退避取消与10秒同号重试；核对实际提交顺序、目标身份、诊断、绑定与槽位。
- CCRB_TEST_RATE_LIMIT_ONLY=1运行scripts/testing/cc2api-native.ts：使用登记的280/293实际执行体，普通API与完整原生输入各一次业务429，共四次TLS实收；独立核验CCH，保留request-id及正文，单次attempt且无账号冷却。

## Scenario: 原生发送前拒绝原因与入站正文采集

### 1. Scope / Trigger

- 修改固定280/293输入拒绝、sender错误投影、请求级诊断及管理员证据读取时适用。输入400/422可在attempt_count=0发生，不能只依赖尝试记录保存原因或正文。

### 2. Signatures

- `BridgeError(code,message,status,diagnosticCode?:NativeRejectionReason)`保留既有业务code/status；`nativeErrorDiagnostics`将固定细分原因投影到既有causes首项code，JSON六字段结构保持兼容。
- `RequestDiagnostic.native_rejection?:{reason:Option<String>,capture_id:String,capture_status:String}`沿summary_json保存，历史缺字段为空；不新增数据库列。
- sender私有头`x-v3-native-rejection`和`x-v3-native-rejection-capture`仅携带固定原因与queued/disabled/dropped。网关消费后移除；真实上游返回的同名头在sender过滤，不能伪造本地拒绝。
- 复用`GET /admin/request-diagnostics/:request_id/captures/:attempt_id`，路径末段可匹配该请求native_rejection.capture_id；读取前仍核对请求、账号及采集UUID归属。

### 3. Contracts

- 固定原因目录包括native_entrypoint_unsupported、native_version_mismatch、native_billing_invalid、native_metadata_invalid、unsupported_body_field、unsupported_message_field、unsupported_system_block、invalid_message_role。TS、Rust与共享fixture同步；未知原因保持缺失，不复制任意异常文本。
- sender在cc_prepared之前收到error事件时，经既有有界后台队列保存`stage=ingress_rejected`快照。复用会话映射前已冻结的脱敏HTTP逻辑正文及原始长度/SHA256，入口上限1MiB，超限标记截断。debug及账号内容采集目录共同门控；info在复制前返回disabled。取消份数限制；拒绝证据使用`.rejected.json`标识，正常快照容量轮转不得删除它，沿共同1GiB预算和七天读取期限，容量政策由settings-database.md所有。
- 拒绝快照的body为空字符串、headers为空数组、original_body_bytes/original_body_sha256为null；实际入口只位于ingress。cc_prepared与wire_final阶段为unavailable，不创建上游attempt，不保存运行时错误全文。Python读取器和runtime_bridge同时识别该阶段并保持账号归属验证。
- 请求级摘要保留当前选择对应的拒绝归属；重新选择账号和最终成功时清除过期拒绝摘要。管理员页面显示固定原因、采集状态和“查看入站请求”；默认展示入口，未发生的组装阶段保持缺口。旧记录缺字段继续可读。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| debug、采集开启、原生输入400/422且尚未组装 | 请求级原因及入口证据可读，attempt_count=0 |
| info或账号采集关闭 | 原因可读，正文disabled/summary |
| 后台队列繁忙、文件缺失或过期 | 独立显示dropped/missing/expired，业务响应保持 |
| 错请求、错账号、任意采集UUID或未鉴权读取 | 拒绝访问 |
| ingress_rejected携带非空出站正文或完整组装/TLS声明 | 读取校验拒绝 |

### 5. Scenarios and Examples

- 正常：消息角色在输入层返回400，详情显示“消息角色不符合当前接入格式”，零尝试记录通过capture_id读取脱敏入站；凭据替换为[REDACTED]。
- 基础：旧内核省略细分原因时保持原错误码和状态；旧记录缺native_rejection仍按原详情渲染。
- 错误用法：为了读取失败正文补造一次上游attempt，或把入站正文标记为cc_prepared。正确处理是请求级关联ingress_rejected，并明确标记组装和TLS未发生。

### 6. Tests Required

- runtime的native-error-diagnostics及共享fixture：固定原因沿事件传递，原code/status保持，任意文本及未知扩展被过滤。
- native_error、native_runtime、diagnostics单测：原因私有头、输入错误状态、零attempt持久化、成功清除及历史兼容。
- native_capture与orchestrator/test_native_capture.py：脱敏入口/原始hash、info门控、账号隔离、伪造出站阶段拒绝和有界读取。
- `verify_rejected_request_ui.py`：400/422×1280/390视口，无attempt时可读取入口、具体原因可见、空组装阶段明确缺口，真实模型请求为0。

## Scenario: Native 顶层 disabled thinking 兼容

### 1. Scope / Trigger

修改 `rewrite_disabled_thinking_enabled/models`、native Messages 正文副本或相关重试时适用。该兼容沿原有显式设置执行。

### 2. Signatures

- `DisabledThinkingRewrite { enabled: bool, models: Vec<String> }`；`should_rewrite(&self, &Value) -> bool` 共用开启条件与精确匹配规则。
- `rewrite_disabled_thinking_to_adaptive(&mut Value, &DisabledThinkingRewrite)` 为 crate 内共用的最小改写入口。
- `forward_native_messages` 与 `forward_native_messages_once` 接收原请求冻结的 `&DisabledThinkingRewrite`。
- `GET/PUT /admin/settings` 沿既有字符串键 `rewrite_disabled_thinking_enabled`、`rewrite_disabled_thinking_models`，保存后调用 `reload_disabled_thinking_rewrite`。

### 3. Contracts

- 出厂开关为false，默认名单为 `claude-fable-5`，管理员已有选择保持。模型按完整字符串相等匹配；后缀、大小写及别名不做隐式扩展。
- 根请求在账号选择循环前冻结开关与模型名单，首次发送、429退避/换号及签名修复共享该配置；后续根请求使用热加载后的配置。
- 仅开启、名单命中且顶层 `thinking.type=disabled` 时改为 `adaptive`，允许模型自适应思考。其他子字段与历史 signed thinking 块沿原合同保持。
- native沿既有会话映射取得业务副本，仅命中时取得可变所有权；原始body/header、真实会话与ingress诊断保持调用方来源。改写后的副本进入原生构造、cc_prepared和最终CCH，原始入站与实际出站分别核对。
- 既有签名修复可以删除顶层thinking及相关依赖，兼容规则只处理仍存在的disabled；不得因启用兼容而恢复被签名修复删除的字段。
- 普通API的原生disabled保留适配继续按运行时合同执行。该兼容在网关修改业务正文，复用既有私有协议与固定280/293执行体。
- 实际上游拒绝原因与兼容效果后续观测；本轮按原生构造和隔离TLS发送验收。模拟拒绝不得标成真实上游复现。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 开关关闭、名单为空或完整模型名未命中 | 保持既有输入语义 |
| 命中且顶层type为disabled | 仅改为adaptive |
| thinking省略、其他类型或形状 | 沿既有构造与校验规则处理 |
| 发送期间管理员切换开关或名单 | 当前根请求各次发送继续使用冻结配置 |
| 签名修复已删除顶层thinking | 保持修复结果 |
| 原生无法表达显式参数组合 | 沿既有明确错误返回合同处理，不静默删字段 |

### 5. Scenarios and Examples

- 正常：管理员开启并配置完整模型名，调用方提交disabled，ingress记录disabled，cc_prepared及TLS实收为adaptive。
- 边界：名单为 `claude-fable-5`、请求为 `claude-fable-5[1m]`，完整字符串未命中，保持原输入；一次请求收到429后关闭开关，该请求重试仍沿原配置，下一请求采用关闭状态。
- 错误用法：修改原始入站对象、模糊匹配模型，或在签名修复后补回thinking。正确处理：仅修改业务副本、精确匹配，并保持签名修复的字段删除结果。

### 6. Tests Required

- `service::rewriter::tests` 的disabled_thinking用例覆盖开关、精确模型含后缀、字段形状、附加子字段、历史签名、缓存与CCH。
- `CCRB_TEST_THINKING_ONLY=1` 的 `native_real_gateway` 使用280/293实际执行体，共33次模型发送：普通API与完整原生输入、开启/关闭/未命中/再次关闭、ingress与cc_prepared、缓存和TTL、签名修复及学习后首发、429期间配置冻结；逐次核对TLS实收CCH及源版本。
- `cargo test --locked`、`cargo fmt --check`、运行时类型及单元/隔离联调验证；制品必须匹配当前固定清单，实际验证副本与交付补丁分别核对。


## Scenario: 多平台账号与AGY原生凭据管理

### 1. Scope / Trigger

- 修改账号平台、AGY授权/刷新、能力保存或授权制品交付时适用。权威实现为AccountService、OAuthFlowService、AccountStore及services/orchestrator/agy_auth.py。
- CC既有管理接口和凭据返回保持兼容。AGY业务worker、Gemini路由及同形体转换由后续任务承接。AGY与工程/养号的交互属于范围外。

### 2. Signatures

- Account.platform：claude_code / antigravity，省略为claude_code。agy_system_prompt_homoglyph_enabled：bool，默认false，按账号独立保存。
- GET /admin/accounts：platform缺省claude_code；all显式查询全部平台，指定平台参与SQL过滤、计数及分页；返回当前平台范围account_counts。
- POST /admin/oauth/generate-auth-url：扩展platform、account_id，沿用proxy_url或proxy_id/proxy_revision；exchange-code沿session_id/code分派。AGY重授权目标及代理在会话内冻结。
- POST /admin/oauth/:session_id/cancel?platform=antigravity；GET /admin/accounts/:id/agy-credentials；POST /admin/accounts/:id/agy-credentials/recover。
- 内部POST /internal/v3/agy-auth/{action}：start/exchange/cancel/verify/refresh/prepare/recover/retire。refresh、prepare输入operation_id/account_id/generation/document/proxy_url；recover、retire输入前三项，拒绝额外字段。
- gateway.account-platforms.5追加accounts.platform、INTEGER开关、UNIQUE(platform,email)及account_credential_states(account_id,generation,phase,operation_id,updated_at_ms)。阶段为ready/refresh_pending/reauth/reconcile；元数据表不存令牌。

### 3. Contracts

- 迁移追加独立定义和登记摘要，冻结旧步骤。历史行按CC读取，同邮箱跨平台可并存，同平台重复迁移失败；保留账号ID、绑定、凭据及配置。未知输入拒绝，未知存量仅可见并隔离平台操作。
- AGY使用完整OAuth凭据及带时区expiry，通过AT-only原生已认证状态核对邮箱，不能信任文件id_token_email作为认证证明。CC专用调度、绑定、额度、遥测和预热均按平台守卫。
- 复用账号刷新锁，锁内重读权威账号，先以原AT/RT/邮箱条件持久关闭门禁再调用唯一RT所有者。驱动按账号文件锁串行，原操作请求摘要冻结账号、代次、凭据及代理；结果未知保留同操作材料进入reconcile，不重放RT。
- complete_agy_observation按原身份、原AT/RT、操作和代次CAS，在同一事务保存新AT、RT、expiry、代理、能力和新代次。失败整体回滚。同操作已提交仅确认当前同结果，禁止回写覆盖后续编辑。
- 创建能力同事务保存；重授权和刷新传递同次capabilities并持久到usage_data.capabilities，保留source/observed_at_ms；usage_fetched_at为UTC观测时间。SQLite和历史PG的usage_data及usage_fetched_at均为TEXT，OAuth专用PG时间列沿TIMESTAMPTZ转换。
- prepare先持久保存手工候选。有效AT采用AT-only核验；到期AT在同操作内用候选代理执行一次原生models刷新，再核验身份。恢复停止原RT进程，优先采用当前私有文件的新RT，原生省略RT时沿用同操作input，代理和能力取同操作回执。
- 缺失操作的recover在账号锁→操作锁内先保存not_started终止记录。显式retire核对同账号、代次和操作，停止原进程并持久retired记录，网关取得完整终止证明后才以CAS解除旧门禁。终止记录跨重启保留，迟到refresh/prepare/exchange拒绝。重新授权替代reconcile之前先走retire。
- AGY固定1.5.9、私有HOME、OOB与PKCE白名单；制品身份沿[AGY凭据研究合同](../../platform/deploy/agy-credential-contract.md)。内部操作沿Bearer及UPDATE_GATE认证准入，公开错误脱敏，完整材料不进入日志或浏览器持久缓存。
- 可选构建输入V3_AGY_AUTH_ASSET通过固定大小及完整SHA校验后冻结，省略时声明未就绪。经auth_asset_identity校验的可用制品身份进入account.content_sha256；旧清单缺省及显式未提供等价，制品双向启停均触发account_rebuild_required。control的vibebench.account-platforms=1与宿主旧版兼容门禁共同阻止旧程序误读新平台记录。
- UI在既有账号页显式选择平台，保持草稿及焦点；平台/账号切换、关闭和旧回执按generation隔离。平台筛选保留读屏标签，桌面与状态组同高，390px平台/搜索首行、状态组次行。能力目录、套餐及额度按真实来源展示，未知、过期和零分别表达。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 未知平台、修改平台、AGY Setup Token、错账号身份 | 400且保持权威账号归属 |
| 重复同平台邮箱或历史迁移冲突 | 拒绝创建/迁移，保留原行 |
| 非ready发起刷新、未知回执、驱动未就绪 | 阻止新RT消费，保持可恢复阶段 |
| 驱动尚未落盘即失败 | 保存同归属终止记录后允许恢复或新重授权 |
| 代理刷新已轮换RT后核验/回执失败 | 保留同操作新RT，恢复核验后原子提交 |
| 旧操作、错误代次、跨账号终止证明 | 拒绝解除门禁或提交 |
| 制品字段、版本、大小或摘要不匹配 | 签发前拒绝；缺省未提供兼容读取 |

### 5. Scenarios and Examples

- 正常：CC旧客户端不传platform沿旧路径；新账号页显式请求all。AGY完成OOB后按已认证身份保存，再按账号保存同形体开关。
- 边界：旧AT到期且旧代理不可用，候选新代理在唯一操作内刷新。回执丢失后recover读取已轮换材料，代理、凭据和能力同代保存。
- 错误使用：只清数据库pending后重发旧RT，或把新代理单独先保存再提交凭据。正确处理：先取得持久终止证明，或按同操作恢复，并以原子CAS发布一致结果。
- 错误使用：源码相同就复用未携带AGY的旧账号镜像。正确处理：签发时纳入已校验制品身份，由既有内容身份比较选择镜像。

### 6. Tests Required

- cargo fmt --check与cargo test --locked；SQLite/PG历史迁移、跨平台同邮箱、重复冲突、原代次CAS、能力创建与事务回滚、终止归属和迟到回执。
- test_agy_auth*.py：真实私有文件/跨进程锁，原码单次投递、RT轮换及省略、终止记录跨重启、到期新代理刷新与已落盘RT恢复；ASGI鉴权与错误脱敏。
- test_system_release.py：固定源码下制品启停双向账号重建、历史缺省、错误声明拒绝、实际签名校验；数据库定义与宿主兼容门禁回归。
- verify_agy_accounts_api.py：真实HTTP/SQLite配合合成原生服务，断连、重启、错账号、未落盘恢复及重授权、能力回读、新代理到期刷新和丢回执。
- 前端构建与verify_accounts_design.py、verify_agy_accounts_ui.py、verify_account_filters_ui.py：旧CC载荷、两账号开关、草稿/焦点、取消与迟到结果、组合筛选及390/720/1440/1920px。
- 原生OOB启动/取消与合成身份回执分别记证据。真实Google登录、身份及刷新由具备授权测试账号的外部验收独立记录，不能用合成通过冒充真实验收，模型提交预算为0。

## Scenario: 反重力 Messages 与 WebSearch

### 1. Scope / Trigger

- 修改 Flower2API 的 Anthropic Messages 到反重力 Gemini 转换、会话或工具续轮、独立搜索执行及来源过滤时适用。账号、凭据和环境许可沿[账号环境共同合同](../../orchestrator/backend/account-runtime-v3.md#scenario-agy账号运行环境与gemini业务接入)。

### 2. Signatures

- 已鉴权的 `POST /v1/messages` 按正文中的 `gemini-*` 模型进入反重力。`stream: true` 返回 Anthropic SSE，缺省返回 Anthropic JSON。目录模型与账号权限沿现有 Gemini 准入校验。
- 普通 Messages 请求可带 `thinking: {"type":"enabled","budget_tokens":<正整数>}` 或顶层 `output_config.effort`。思考选项作为网关内部的档位偏好，生成正文沿原有 Gemini 形状。
- 唯一工具声明 `{"type":"web_search_20250305","name":"web_search"}` 时，解析最后一条用户消息的文本查询及可选的 `allowed_domains` 或 `blocked_domains`。兼容 Claude Code 的 `Perform a web search for the query: ` 前缀。
- 发送器私有 `POST /internal/agy/search` 使用已有 `AgySubmission`、Bearer 和环境归属。操作正文为 `{"query":<非空字符串>,"previous_request_id":<原作业 UUID 或 null>}`。监督器命令为 `search`，成功时先发 `search_result`，再发同请求的 `job_finalized`。

### 3. Contracts

- 顶层 `system` 和归属全局的历史系统文本按顺序构成 Gemini 的 `systemInstruction`。同一用户轮中，遇到已通过 `tool_use_id` 找到原调用的工具结果后，后续的 `messages[].role = "system"` 文本归入该轮，适用于 Read 截断提示、后台任务通知和其他补充文本。已有用户内容时，以 `UserPromptSubmit hook additional context: ` 开头的钩子文本同样归入该轮。
- 下一条 `assistant` 消息或历史末尾结束当前用户轮。将该轮已收集的补充按原顺序作为 `text` Part 追加到最后一条用户内容，分批工具结果排在补充文本之前。字符串和文本块数组采用同一投影。重发历史时按同一规则复用旧轮位置。其余历史系统文本归入 `systemInstruction`。
- 图片沿原生媒体校验。普通函数调用和工具回填按 `tool_use_id` 对应，续轮补回已匹配原调用的真实模型签名。
- 正整数手动预算优先，沿 Gemini 的预算区间选择低、中、高档。否则 `effort` 的 `low`、`medium`、`high`、`xhigh` 对应同名档，`none` 和 `minimal` 对应低档，`max` 对应 `xhigh`。基础模型优先尝试目标档位，再用原来可接单的同系目录候选。显式型号按精确名称匹配。工具续轮复用原账号和实际档位。思考 token 数由所选原生型号决定。
- AGY 返回的栅格图片 `inlineData` 按源 MIME 与 Base64 数据生成 Markdown 图片文本。Messages JSON 使用 `text` 内容块，SSE 使用 `text_delta`，都保留原 Part 顺序。原生 Gemini JSON 和 SSE 保留 `inlineData` 结构，原生 `thinkingConfig` 沿账号环境共同合同。
- 会话依次使用正文中合法的显式值、`X-Claude-Code-Session-Id`、`X-Session-Id`。网关在反重力域内结合 API 令牌派生选号键，管理诊断显示原始 Session ID。待回填轮的搜索复用同令牌、显式会话、模型和查询所对应的原账号许可。该轮的相同查询复用原搜索回执，每次回包按请求的域名规则过滤。
- 发送器以固定原版 `agy 1.5.9` 的 `-p` 和 `stream-json` 输入、输出执行 `search_web`。只读取本次成功工具步骤的 SQLite 轨迹结构，使用原生标题和 URL。外部回包在收口后生成同 ID 的 `server_tool_use` 和 `web_search_tool_result`。一次成功搜索计为 `usage.server_tool_use.web_search_requests = 1`。
- 来源规则按域名和子域匹配。固定原版对 `vertexaisearch.cloud.google.com` 的 Google 跳转只保存跳转地址和标题。存在非空允许域或禁止域列表时省略这类链接。无域名规则时保留原链接。来源标题仅用于显示。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| Messages 思考选项缺省或无法映射 | 使用该模型原有的目录选号规则 |
| Messages 图片 MIME 不受支持或 Base64 无效 | 省略该图片 Part，记录脱敏告警，保留其余内容 |
| 空查询、无效域名或同时声明允许域与禁止域 | HTTP 400 |
| 域规则过滤掉全部来源 | 成功的 `web_search_tool_result`，`content` 为 `[]` |
| 原作业失败或无法核验来源回执终态 | `web_search_tool_result_error`，`error_code` 为 `unavailable` |

### 5. Scenarios and Examples

- 两轮工具回填后分别追加运行状态和 `<task-notification>`。提前合入全局系统指令会改写缓存前缀。每段补充应随对应工具轮发送，后续回放中旧轮的位置固定。
- 手动预算 1024 优先匹配同一基础型号的 `-low`。目录缺少目标档位时，按原候选选择实际可用型号，实际命中以请求诊断为准。直接指定 `-low` 时按该精确型号选号。
- 原生发送器的生成请求接受默认或 `TEXT` 模式。要求 `responseModalities: ["IMAGE"]` 会收到字段级 400。Messages 只投影模型实际回传的图片。真实出图需在有授权的环境按固定 AGY 和目录型号验证。
- 正常查询 `IANA Example Domains`。声明 `allowed_domains: ["iana.org"]` 时保留 `www.iana.org` 直链。声明 `blocked_domains: ["iana.org"]` 时过滤该直链。
- 把 Google 跳转域填入允许列表无法确认来源站点。需要域名约束时应声明来源站点域名，回包仅包含同规则匹配且来源域可核对的结果。

### 6. Tests Required

- `messages_prompt_hook_*` 核对两种钩子文本形状的 `systemInstruction` 和历史前缀，以及普通系统提示和分批工具结果的顺序。
- `messages_tool_result_system_supplements_keep_the_cached_prefix` 核对四轮累积历史中的两批任意补充、工具回填 ID、`systemInstruction` 和已发送的消息前缀。`messages_read_truncation_notice_keeps_its_position_across_tool_turns` 核对 Read 截断提示及普通用户轮的系统归属。`verify_agy_native_loopback.py --messages-search` 核对截断提示和后台任务通知在实际出站中唯一出现、排在原工具结果之后且维持原顺序。
- `verify_agy_native_loopback.py --image <离线测试镜像> --messages-search` 核对来源直链与跳转、允许域与禁止域、无域规则、重复查询、账号和工具回填 ID、取消清理。
- 同一回环核对思考选号、目录缺档、显式档位和改 effort 后的同账号工具续轮。用同一图片源核对 Messages JSON 和 SSE 的 Markdown 数据及顺序，以及原生 Gemini 两种响应的原始 `inlineData` 和终态。
- 加 `--claude-code <可执行文件>` 核对真实客户端 `searchCount=1`、来源链接和后续生成。真实 Google 联网由有授权的测试账号单独验收。

## Scenario: AGY Messages 账号级系统提示词位置

### 1. Scope / Trigger

- 修改 AGY 账号的 Messages 系统提示词位置、同形体组合、私有策略或相应采集来源时适用。未选择用户提醒时，沿[独立系统段的同形体合同](../../orchestrator/backend/account-runtime-v3.md#scenario-agy账号系统文本同形体策略)。

### 2. Signatures

- `POST /admin/accounts`、`PUT /admin/accounts/{id}` 和账号读回使用 `agy_system_prompt_as_user_reminder: boolean`。账号表存为 `INTEGER NOT NULL DEFAULT 0`。SQLite 由 `gateway.agy-system-reminder.10` 追加，PostgreSQL 初始化沿同名列。
- `AgySubmission.system_prompt_policy` 的 `schema_version=1` 增加可选 `user_reminder_index`，为 `contents` 的非负下标。启用同形体仍由 `enabled` 表示。原生回执沿现有字段，用户提醒落点使用 `source="cortex_user_reminder"`。

### 3. Contracts

- 账号管理页独立保存两个布尔值，新旧账号的位置开关默认关闭。网关按实际选中的 AGY 账号冻结设置。普通 Messages 生成有独立系统文本时选择第一条不含函数结果的用户内容，公开请求正文不提供策略索引。
- 原生入口以换行合并系统文本，先执行现有 `transform_system`，再按可选索引追加一个 `<system-reminder>` 文本块。此时独立系统段使用 `REMINDER_SYSTEM_INSTRUCTION`。字符映射只处理原系统文本。标签、固定英文指令和已有消息逐字保留。Gemini 原生直连沿独立系统段。
- `REMINDER_SYSTEM_INSTRUCTION` 为 `Use the provided context to answer the user's request. When working on multi-step tasks or calling tools, briefly share your progress and explain what you are doing and why. For strict-format requests such as JSON-only output, or auxiliary tasks such as compaction, summaries, titles, and classification, return only the requested output.`
- 领取和历史续轮依据投影前正文及原有工具签名、调用 ID 和结果定位。新生成采用当前账号值。同一 HTTP 的认证恢复复用首次策略。开启位置或同形体时，网关先核对实际落点和转换回执再交付源帧。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 省略位置字段或保存关闭 | 私有信封省略索引。两个策略均关闭时省略策略扩展 |
| 系统文本为空或缺少普通用户内容 | 沿独立系统段，保留同形体开关语义 |
| 非 AGY 账号启用或更新字段类型无效 | 管理请求受控拒绝 |
| 私有索引畸形、越界或指向工具结果 | 原生组装前拒绝 |
| 运行组件缺少位置策略支持或回执不符 | 受控失败，公开响应不交付未经验证的源帧 |

### 5. Scenarios and Examples

- 两项开启时，`system = "ABC system"` 在用户消息追加 `<system-reminder>\nΑΒС ѕуѕtеm\n</system-reminder>`，独立系统段留下中性指令。仅启用位置时，同一标签承载 `ABC system` 原文。
- 工具等待期间关闭位置开关。原工具结果按既有归属收口，回填后的新模型请求使用独立系统段，同一回填重读复用原终态。
- 直接对整个用户消息执行同形体替换会改变原输入。配套实现先转换独立系统文本，再将结果作为新文本块追加。

### 6. Tests Required

- 真实管理 HTTP、SQLite 和浏览器覆盖两个账号独立保存、旧账号默认关闭、非 AGY 约束、重新编辑与 390px 布局。迁移核对旧版本台账、重跑幂等与原数据。
- `verify_agy_native_loopback.py --system-reminder` 在断网容器核对四种组合的实际原生 TLS 体和回执来源。覆盖领取、历史续轮、历史兜底、待回填切换、签名及单次回填。
- `verify_agy_gemini.py` 覆盖两个账号的私有快照、首次冻结及认证恢复。Python 单测覆盖已存在提醒、工具历史、非法索引及快照读回。

## Scenario: 反重力工具续轮与开流失败边界

### 1. Scope / Trigger

- 修改反重力运行环境续轮设置、工具批次接续、Claude Code 后台摘要或 AGY 的公开响应首帧时适用。账号准入、工具等待和原生模型约束沿[账号环境共同合同](../../orchestrator/backend/account-runtime-v3.md#scenario-agy账号运行环境与gemini业务接入)。

### 2. Signatures

- 管理 GET 和 POST `/runtime/api/environments/{environment_id}/agy-tool-continuation`。POST 接受 `{"expected_generation":0,"expected_revision":0,"mode":"claim_with_history"}`。返回 `mode`、`revision`、`generation` 和 `supported`。环境代次由实际管理目录提供。版本 `0` 表示缺省记录。
- 内部传输绑定可携带 `agy_tool_continuation_mode` 与 `agy_tool_continuation_protocol`。包含历史的策略要求协议 `1`。`job_finalized.history_closed` 可包含 `{request_id,generation,request_seq}`，其中 `generation` 是原工作进程代次。
- 回填重读诊断的 `replay_of_request_id` 关联原 HTTP 根。`replay_of_attempt_id` 关联已进入发送边界的尝试。`replay_submission_state` 取 `preparing`、`sending` 或 `model_observed`。历史记录可省略新增字段。

### 3. Contracts

- 中央管理面按逻辑环境原子保存策略。本机与远端共用同一配置源。缺省为 `claim`，另外支持 `history` 与 `claim_with_history`。能力取当前发送镜像和选中内核的声明。派发时冻结选择，已交付工具批次按自己的选择接续。
- 历史续轮在完整工具批次交付后触发原生取消。用同账号、环境与工作进程归属核验原作业的实际退出证明，再导入原前缀、真实调用 ID、签名与完整结果。已有显式会话标识时按原值校验。领取优先仅在旧轮退出已确认且真实结果尚未向旧轮派发时允许历史兜底。两条路径共用一次提交权与正文重读记录。有原生 WebSearch 回调绑定的批次使用领取。
- 已鉴权的 AGY Messages 请求匹配 Claude Code 固定后台摘要模板、可选 `Previous:` 行和完整工具配对时，本地生成 3–5 词状态。匹配在合入当轮系统补充文本之前进行。原工具归属与发送许可由真实回填持有。普通追加文字继续走生成路径。
- 首块有效内容、完整工具批次或确认成功的明确终态才提交公开首帧。用量和元数据先累计。原生接收先结束且源终态缺失时，在原预算内等待同一次控制结果。诊断分别记录 `native_receive_ended`、`native_source_terminal`、`observed_control_http_status` 与可选 `control_error_detail`。`tool_continuation_mode`、`tool_continuation_path` 和 `tool_continuation_reason` 分别记录配置、实际路径及原因。
- 固定 AGY 1.5.9 的观察器按调用 goroutine 的 `g.goid` 关联 Receive，按 Scanner 的 `g.parentGoid` 和同一活动作业关联原始帧。已验证映像中的槽为 `0x98` 和 `0x118`。主调用 STOP 并收到 EOF 后，与主根独立的原生调用沿各自 `call_id` 隔离。空会话的侧调用沿主工具等待阶段和独立调用身份核验。同根再次启动或无法定位归属的主帧仍进入原生失败路径。
- SQLite 的 gateway.agy-tool-receipts.11 和 PostgreSQL 初始化持久登记工具批次。记录正文、调用、签名和会话摘要，以及账号、尝试归属、阶段和恢复额度。正文和成功响应帧只走有界内存。重读权限仍按令牌、账号及会话核对。严格身份优先，省略 ID 时仅用唯一的前缀与参数别名。
- 准备中的续轮使用进程内位置，同正文重读附着到该位置。选号冲突和准备取消同步释放该位置，并归还仍可用的旧快照。数据库在原生外发前比较原阶段及尝试所有者。首次历史在这一步才绑定选中的账号。选定 sender 的实际预算约束会话认领、RPM 等待和发送边界。
- 已受理续轮保留实际 sender 生成截止，客户端断开后仍可读取原生成。成功帧在该截止回收，轻量回执有独立的工具等待窗口。只有实际 model_start 才标记 model_observed。失败后的请求不从头重放部分正文及用量。
- 同一账号、环境代次及实际尝试的可信 job_finalized 确认关闭后，暂时性失败、超时或取消可以原样历史恢复一次。维护取消适用同一证明。原工具结果只导入历史。明确未发送时恢复原阶段和额度。已登记的重复请求、送达未知以及不匹配的环境回执保留实际发送保护。原样重试及追加固定 Claude Code 断流提示的请求共用额度。实际派发时保留新请求中的提示。恢复会产生实际模型用量。
- 活跃 Gemini Claim 接受合法回填的旧式占位签名，并用原生签名组装已核对的历史。Messages 和历史路径核对签名。恢复使用仍可用的受信快照或经过校验的客户端记录。可选恢复快照使用独立的 64 MiB 预算，最长保留到生成截止加 25 秒收口和 240 秒恢复窗口。待回填工具轮保持自己的预算。
- 成功响应先发布完整终态，再写持久成功记录。写入异常进入诊断，进程内完整响应继续可重读。
- 缺少可信关闭、恢复用尽或原失败不适合继续时返回 HTTP 400，分类 AGY_TOOL_CONTINUATION_TERMINAL，带原 HTTP 根。成功但响应字节已过期的状态仍为 410。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 设置代次或版本过期，或内核缺少所选模式的能力 | 管理 POST 返回 409 |
| 工具回填归属冲突 | 400，零新增模型提交 |
| 同一回填的响应字节已回收且提交回执仍有效 | 原成功的响应返回 410。失败按物理收口及恢复额度决定是否进行一次合法历史恢复 |
| 历史续轮等待真实退出证明时到期 | 返回失败，零新增模型提交 |
| 已选择旧 sender 且发送前到期 | 429，释放未发送权和恢复额度 |
| 已知在作业登记前拒绝 | 原失败原因，恢复此前回执阶段 |
| 首块前缺少源终态，控制结果为 200 | 503，诊断保留实际控制 200 |
| 首块前确认控制 HTTP 500 或源配额 429 | 保留实际错误状态 |
| Messages 已交付正文后失败 | 保留原 HTTP 响应头，发送 SSE `error` |

### 5. Scenarios and Examples

- 正常领取优先收到匹配结果后直接收口。原轮先确认退出且未领取结果时，同一回填从历史生成一次。客户端在实际生成预算内可重读该成功响应。回执持久保留原状态及恢复额度。
- 连接断开只表示传输状态未知。收到匹配的 `history_closed` 后才具备历史接续的退出依据。网关重启会丢失进程内的待续轮归属。

### 6. Tests Required

- `verify_agy_native_loopback.py --continuation-modes` 核对原版 1.5.9 四条接续路径、配置冻结、错误会话与签名拒绝、正文重读、缓存前缀及首帧前后错误。`--messages-search` 核对历史偏好下的 WebSearch 回调与 Read 截断前缀。
- `usage_prefix_retains_http_error_until_the_first_deliverable_frame` 核对首帧之前的错误、开流后 SSE 终态和缓存用量保留。`history_closure_requires_the_original_worker_and_request` 核对回执归属和缺失证明。
- `verify_agy_native_loopback.py --tool-receipts` 以两笔重叠的原版调用验证 Scanner 帧归属，并重放一笔侧调用的空会话。核对真实 EOF 失败的 16 次重试、一次历史恢复、恢复用尽的 400、跨重启回执、维护收口恢复与成功记录存储异常。`--continuation-modes` 同时核对 Gemini Claim 占位签名。`--tool-deadlines` 核对长工具等待和已回收响应的 410。

## Scenario: AGY 本地进度标签回执

### 1. Scope / Trigger

- 修改 `/v1/messages` 的本地工具进度回包或供外层计费网关使用的回执时适用。

### 2. Signatures

- `agent_summary_response(summary: String, model: &str, streaming: bool) -> Response`
- HTTP 200，响应头 `X-Flower2API-Local-Response: agy_agent_summary`。

### 3. Contracts

- 鉴权、固定摘要模板与工具结果配对、可用候选校验通过后，本地标签分支生成回执。此时上游模型尝试为 0。
- JSON 返回文本、`stop_reason=end_turn` 和明确的零输入、零输出、零缓存读取用量。SSE 在 `message_start` 和 `message_delta` 都提供相同的零用量，并以 `message_stop` 收尾。
- 外层计费网关从受信任渠道的实际响应中取得回执，用它区分明确零用量与缺失用量。只有本地进度标签成功响应携带此值。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 本地进度标签匹配且账号候选可用 | HTTP 200、局部生成的标签和回执 |
| 本地进度标签匹配但候选为空 | 503 |
| 普通模型响应 | 模型内容和供应方用量 |

### 5. Scenarios and Examples

- 正常示例。匹配后台摘要的工具历史在本地生成 `Reading sample file`，两种响应形式都携带回执。
- 误用示例。给普通生成的空用量帧添加回执会把缺失用量解释为零消费。应由成功生成标签的本地分支签发回执。

### 6. Tests Required

- `agent_summary_response_provides_local_receipt_and_zero_usage` 核对流式及非流式的回执、内容、零用量与完整终态，并验证普通生成响应头。
