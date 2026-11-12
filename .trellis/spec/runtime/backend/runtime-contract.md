> 本文源码路径及命令以 `services/runtime/` 为工作目录。

# 固定 293 原生运行时合同

## Scenario: 结构化 API 到单次原生发送

### 1. Scope / Trigger

- 新增 HTTP API、私有 JSONL 和原生 SDK 适配，属于跨层执行合同。
- 实现依据：src/shared/input.ts、src/control/header-policy.ts、src/control/engine.ts、src/runtime/293/{preload,worker,job,cli}.ts。
- 来源版本及内部模块只由 src/runtime/293/source-profile.ts 定义，profile.ts 重导出；精简产物身份由 compact-profile.ts 单独登记，避免载荷包含自身最终哈希。内部绑定依据固定二进制实测，不得猜测混淆符号。

### 2. Signatures

- parseInput(raw: unknown, incomingHeaders: HeaderPair[] = []): BridgeInput。
- prepareInput(input: BridgeInput): PreparedInput。
- NativeEngine.run(prepared: PreparedInput, signal: AbortSignal, emit: (event: RuntimeEvent) => Promise<void>): Promise<void>。
- Engine.close(): Promise<void>；workerPid: number | null 是只读状态，读取不启动进程。
- verifyRuntime(path: string): Promise<VerifiedRuntime> 保留核验 FD；runtimeFileStamp(path: string): Promise<string> 用于暖复用；verifyExecutionImage(pid: number, identity: RuntimeIdentity): Promise<void> 独立核对内存执行体。
- bun scripts/build-runtime.ts --source <固定原版> --out <新产物> [--sevenzip <固定7zz>] [--sdk <固定源归档>]。
- POST /v1/messages 接收正文；POST /api/requests 还接收 schema_version、request_id、body、headers、context。
- decodeRuntimeEvent(line: string, requestId: string): RuntimeEvent 校验请求事件；decodeWorkerCommand(value: unknown, workerId: string): WorkerCommand 和 decodeWorkerFrame(line: string, workerId: string): WorkerFrame 是常驻管道的统一边界。
- initializeCli(bindings: NativeBindings): Promise<void> 完成本地 CLI 初始化；prepareCli(prepared: PreparedInput, bindings: NativeBindings, system: string[] | undefined, thinking: JsonObject | undefined, abort: AbortController): Promise<CliPreparation> 生成本轮独立装配参数。

### 3. Contracts

- 固定官方 2.1.293 来源，SHA256 为 8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978。创建引擎与每次加载新进程校验完整分发文件；暖复用检查真实路径、dev/inode、大小及纳秒 mtime/ctime。通过已核验 FD 启动，避免路径替换后执行另一文件。官方程序与提取源码不提交。
- 轻量入口仅接纳固定登记的外层及执行体身份，外部 manifest 不授信。当前基底为原版 Bun 1.4.3；原生代码保留，ICU 仅按固定 C.UTF-8 环境保留 root/en、完整字符/规范化数据和全部分词规则/字典。它是桥接专用程序，不能宣称具备通用 CLI 的全部 Intl locale 定制。
- BCJ2/LZMA2 与静态 C SDK 加载器单文件分发；载荷 SHA256 自校验后写入封存 memfd 并 fexecve，同 PID 执行，控制层再核对 /proc/<pid>/exe。运行不依赖原版、提取目录或构建工具；磁盘、内存文件与 RSS 分列，不把内存展开当作内存节省。
- 原生模式显式提供 CCRB_CLAUDE_BINARY、CCRB_CLAUDE_HOME、CCRB_CLAUDE_CONFIG_DIR；可提供 CCRB_NATIVE_API_KEY、CCRB_NATIVE_OAUTH_TOKEN、CCRB_PROXY_URL、CCRB_CA_FILE、CCRB_NATIVE_BASE_URL。子进程使用环境白名单；显式代理同时写入 HTTP_PROXY/HTTPS_PROXY，不继承宿主代理或账号。
- 启动工作进程与配对性能脚本统一设置 CLAUDE_CODE_ENTRYPOINT=cli，由原生代码生成 User-Agent 的 cli 入口段及 billing 的 cc_entrypoint=cli；requestClass、agentKind 和父子身份仍独立按真实上下文生成。切换入口须重建进程，历史 sdk-cli 日志保留原采样值，不能仅替换日志或正文中的标签。
- 普通 API 以固定 293 交互 CLI 主请求为参考，主来源为 repl_main_thread、业务用户消息采用 human；-p 的 SDK 行为仅作差异证据。原生 pie、VA/Kz/LT/Uz 及 OM 生成工具、system、提醒和默认模型参数，不手写身份句或用录制请求模板替代；工具结果及六类上下文保持实际来源。完整原生正文走后文的保真分支。
- 两条路径的 tools 省略与 [] 均无工具，非空列表完整采用调用方定义，不加入 CC 内置、延迟、搜索或占位工具。普通 API 的原生 system 和提醒按实际列表生成，CLI 参考须使用对应工具选择；system 省略时使用 CLI 默认正文，显式值按 --system-prompt 替换，空文本/数组同样属于显式替换。普通 API 的显式消息、工具/thinking 和模型参数在发送前核对；工具数组即使省略也核对空列表，不能无损表达时拒绝，不静默删字段。原生业务正文不借用种子的字段政策。
- 每个引擎绑定一个账号环境，首个模型作业惰性启动，正常串行作业复用一个物理进程，不另设 16 项准入门槛。HOME、配置、凭据来源、代理及 cwd 不按请求切换；更换配置须关闭并重建引擎。服务关闭后不再接收作业，并等待队列和常驻进程退出。
- 请求预算、大小与排队政策交前置服务。CCRB_TIMEOUT_MS、EngineConfig.timeoutMs 和 ServiceOptions.timeoutMs 默认 0，不创建请求总计时器；.env.example 同步为 0。显式正整数仅在计时器可表示范围内启用预算。HTTP 不施加 2 MiB 门槛或空闲截止，私有模型正文不施加 8/24 MiB 字节门槛；JSON、归属、状态与完整性校验保留，日志预览上限不限制转发。取消、关闭和取消后的清理宽限独立处理。
- 控制配置中的显式 API key 使用官方本地规则只记录使用确认标识，不保存完整密钥；已有 rejected 决定返回 native_configuration/503，不改写拒绝状态。初始化、预热及测试不能因此触发真实账号登录或付费推理。
- worker_ready 晚于原生绑定、Nst 与本地构造依赖初始化；本地初始化使用独立根，发送前中止，不发模型请求或业务事件，成本计入总启动时间。每轮经 nEr 创建全新原生根，AsyncLocalStorage/yLs 绑定作用域，再调用 t_；同 sessionId 也不能复用上一轮账本、请求日志及取消状态。
- 普通 API 只支持 docs/api.md 登记的正文键。内部 Re/Kc 负责消息实体；原生规范化后的显式消息、工具、thinking 等必须保留，不可表达时拒绝。原生入站的扩展正文及必要改写另见后文合同。
- 普通 API 的 business 构造仅对完整对象恰为 thinking={type:'disabled'} 且原生结果缺失 thinking 的情况补齐原值，同步 result 与 init.body 后再做完整保留校验。省略保持原生默认；额外字段和原生已有不同值不适用补齐，不能静默删改。transport_context 种子与完整原生业务不应用此适配。cc_prepared、同次 Ree 实际发送及 TLS 哈希必须反映相同正文；上游仍返回 thinking 时原样保留，不过滤或重发。
- OM 的 deps.callModel 仅进入一次 K_t；其 fetchOverride 取得同一官方 SDK 的正文、头及发送上下文，在显式字段核验后由 Ree 唯一发送。stream 仅按调用方明确值映射；SDK 不取得 Response，桥接独占原始逻辑响应，读取收口后立即取消原生解析。调用次数守卫禁止模型重试，不创建第二个 SDK，不替换全局 fetch；本地工具、代理循环及自动辅助压缩禁用，显式 compaction 保留。
- 只在精简构建复用固定摘要的六个纯正文格式化函数 KLo、XLo、QLo、nNo、sNo、pNo。每次仍求值原生条件与外层钩子，每个工厂仅保留最近一次原始条件及字符串；UTF-8 键和值每项 ≤64 KiB、六项 ≤384 KiB，不代表堆或 RSS 上限。失败和超限不入缓存；整份提示词、权限/工具选择、会话段落表、memory 读取及请求正文不跨作业缓存。
- HTTP 与 RuntimeEvent 保持 schema_version=1、request_id；事件包含 ready、cc_prepared、response_headers、response_chunk、completed、error；final_capture_ready(attempt=1) 仅由控制侧独立采集器产生，工作进程不得伪造。ready 表示本轮已绑定就绪进程，不代表每轮新建 PID。attempt=1，片段使用可逆 base64。
- error 可选 diagnostics 为 schema_version=1、stage、causes、chain_truncated、cycle_detected、inspection_failed。阶段在 worker/job 实际边界记录，causes 最多八层，只投影 src/shared/native-error-diagnostics.ts 的固定 name/code 白名单；未知值为 unknown，任意 message/stack/URL 不进入摘要。getter 和 cause 环安全降级；共享协议验证结构及字段，旧事件省略保持兼容。完整摘要需重新构建并按原发行合同接纳内核，固定 SHA 与探针准入保持原规则。
- 诊断校验独立于基础 error/归属校验。TypeScript 移除非法摘要及任意扩展字段，标记 diagnostics_state=invalid，保留 code/status；decodeWorkerFrame 交付该规范化结果。缺省旧事件保持原形状，错误归属或非法基础状态仍按 runtime_protocol 拒绝。
- 私有 stdin/stdout 使用 schema_version=2、worker_id；request_start 携带 request_id/prepared，可协商的 request_input 原始信封见下文；request_cancel 携带匹配 request_id，worker_shutdown 关闭进程。输出为 worker_ready(version,pid)、request_event(request_id,payload)、worker_idle(request_id)。payload 禁止覆盖 schema_version、worker_id、request_id。
- 握手前还可返回 worker_error(code=native_configuration,status=503,error)，不带 request_id 或额外字段。error 只公开受控 BridgeError 配置说明，先脱敏且 ≤2048 UTF-8 B，未知异常用通用中文消息；入口等待帧写入完成后退出。错进程归属、握手后错误帧或畸形字段按 runtime_protocol/502 隔离，失败作业不重放。
- 每个物理进程只有一个持续读取器。唯一终态与匹配 worker_idle 缺一不可；释放响应并等待 SDK 收口后才发 idle。重复握手、错代次/错请求、双终态、终态后事件、缺 idle 或畸形帧均隔离进程；读取回调和输出闭包绑定旧代次，不得归入下一作业。取消、异常或状态不明时退役，下一轮重建，不重放当前请求；取消采用 1500 ms 强制终止宽限，空闲关闭优先 shutdown，1500 ms 后仍未退出则强制终止。
- cc_prepared 的正文、body_bytes、body_sha256 在 Ree 前固定，快照输出与唯一发送可并行，但两者成功后才交付响应事件；任一失败取消原生调用并释放未交付响应。原文和 headers 只在私有管道传递，控制层先注册秘密再脱敏持久化；stdout 不兼任普通日志。默认 off 的 wire_final 不可用；启动侧可按下文开启独立验证，来源必须对应实际采集位置，不以 cc_prepared 冒充最终值。
- Connection 声明字段和连接级字段删除；调用方凭据不作为上游凭据；版本、传输、X-Stainless-*、X-Client-Request-Id 等由运行时生成。调用方字段按下文精确协议白名单准入，名单外附加头逐项记录删除原因。
- 透传头与 SDK 默认头重名时，先聚合调用方完整的同名有序值，再覆盖该默认值；不能在默认值后再次 append。Accept 和 anthropic-dangerous-direct-browser-access 不因 SDK 已有相同默认值而重复，调用方显式不同值和合法多值仍保持；beta/version 及运行时所属字段沿各自专用规则处理。
- 上下文为类别、agentKind、agentId、parentAgentId、agentType、sessionId、promptId、workflowRunId 的同一来源。promptId 必须为 UUID。
- 普通 API 的有效 promptId 归到最近一条不含任何 tool_result 的 user 实体，由官方轮次选择器生成 billing 与请求头；工具结果及混合结果不冒充新的 human。显式 ID 可由调用方跨工具往返复用，省略仍按请求生成，不用 sessionId 代替，也不共享上一原生根。没有可归属用户轮次时在构造前返回 unsupported_parameter/422，零发送。
- 类别支持 main、subagent、workflow、compaction、auxiliary、side_reply。子代理必须有 agentId；workflow 还需要 workflowRunId；主代理独立 agentId 须显式 agentKind=main。
- 响应逻辑字节原样返回，删除不匹配逻辑正文的长度、编码及连接字段。工具交给调用方，不注册本地执行器。取消解除待消费片段并收口原生进程，不重放模型请求。
- 新增公共类、接口和公开方法写中文 JSDoc；导入或调用现有内部接口前读取定义与实测证据。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 普通 API 不支持的正文键、system 缓存参数、beta 或原生无法保留的显式值 | 422，发送前拒绝 |
| 上下文冲突、非法头、无效 promptId | 400 |
| 普通 API 历史无可归属用户轮次 | unsupported_parameter/422，零业务发送 |
| 明确且仅含 type=disabled 的 thinking 被原生省略 | 补齐明确值并同步实际发送正文，再校验；带额外字段或原生已有不同值且无法保留时 unsupported_parameter/422、零发送 |
| 合法透传头与 SDK 默认值重名 | 保持调用方完整头值，合法多值按序保留；不拼入 SDK 默认值 |
| 重复 request_id | 409，不覆盖已有记录 |
| 超过 16 个执行或等待作业 | 按原顺序继续串行执行，不产生本地 queue_full |
| 缺省请求预算或显式 0 | 等待完成、上游失败、调用方取消或服务关闭，不套用旧默认截止 |
| 原生初始化时配置或二进制 hash 不匹配 | 失败类型 status=503，不能暗中回退 demo |
| 作业期间二进制 hash 改变 | 当前请求失败，不执行变更后的程序 |
| HTTP 上游错误 | 保留原始状态和正文，不重试 |
| 本地异常发生在响应头之后 | 结束逻辑流，日志记录错误；不拼接伪造 SSE |
| 原生接口不匹配或协议格式错误 | 明确失败，不猜字段或符号 |
| 未登记精简文件、源/载荷 hash 不匹配 | 拒绝，不信任外部清单或回退演示 |
| 终态后缺 idle、错归属或迟到帧 | 本轮失败或隔离空闲进程；下一轮新建，不重放 |
| 构建来源/布局/资源异常、构建期间源码改变或最终文件超预算 | 不输出可接纳产物，清理临时提取内容，已有文件不覆盖 |

### 5. Scenarios and Examples

- 正常：普通正文无来源上下文，生成 main，source=bridge-default；原生 metadata.user_id 内的 session_id、请求头和 billing 的 cc_prompt_id 关联一致。
- 边界：子代理发生压缩，requestClass=compaction，仍保持子代理 agentContext 和父子关系。
- 边界：26 MiB 请求和超过 50 秒的首响应等待保持可转发，日志可截断预览但保留原始字节数及哈希。不能把有限验收的预算或日志容量当作业务准入政策。
- 错误用法：子代理只强行声明 requestClass=main；这样会使身份与 billing 矛盾。正确做法是保留 subagent 和真实关联，冲突明确拒绝。
- 错误用法：将整个 API JSON 转成 prompt，或收到 tool_use 后本地执行。正确做法是结构化映射，单轮返回原始工具事件。
- 错误用法：只给数组末尾的 tool_result 写 promptId，官方轮次选择会跳过该记录。正确做法是把有效 ID 绑定到最近的实际用户轮次，验证日志、billing 与最终头一致；没有该轮次则明确拒绝。
- 错误用法：把原生省略 disabled 当作保留成功，或为关闭效果删除响应 thinking 块。正确做法是在明确的普通 API 适配边界补齐发送值，并分别验证实际写出和上游响应语义；省略参数及完整原生正文不套用补齐。
- 错误用法：将入站 Accept 或浏览器访问开关追加到 SDK 已有默认值，产生 application/json, application/json 或 true, true。正确做法是先保留调用方同名完整表示，再覆盖该透传字段的默认值。
- 演示必须显式选择 demo；它只产生合成内容，不能作为原生发送证明。
- 正常复用：连续两个主/子代理作业保持同 PID，但每轮使用独立 session 根和 prompt；只有下面的匹配空闲帧到达后，才能接收下一作业：

```json
{"type":"worker_idle","schema_version":2,"worker_id":"11111111-1111-4111-8111-111111111111","request_id":"request-001"}
```

- 错误用法：只收到 completed 就重用进程，或把分发文件 SHA 写作内存执行体 SHA。正确做法是等待 idle，并分别登记外层与执行体、核对实际执行体身份。
- 正常入口：主会话与子代理均使用 cc_entrypoint=cli，但保持各自 requestClass 和 agentContext；入口标识一致不代表把子代理改为主会话。

### 6. Tests Required

- tests/unit/header-policy.test.ts：未知头保留、动态 Connection 删除、凭据/原生请求 ID 归属、冲突与默认来源。
- tests/unit/profile.test.ts：错误二进制不执行、不回退。
- tests/unit/engine.test.ts、worker-protocol.test.ts：同 PID 与哈希次数、文件替换、错归属/载荷覆盖、双终态/缺 idle、迟到帧、取消、背压和关闭；错误作业不得重放。
- tests/native/native.test.ts：无外网 TLS 上游独立核对 CCH、metadata/session/prompt、六类请求、thinking/工具历史、非流式、HTTP/SSE 错误及取消后下一请求；实际模型发送次数必须符合 attempt=1。
- 同一套件另核对完整工具续轮、混合文本/结果、最近用户轮次、显式/自动 promptId、同会话独立根，以及无用户轮次 422/零发送；tests/native/tls-verifier.test.ts 在 off/verify 下逐项核对六类续轮的独立实收头、实体与整体 HTTP 哈希及原生 CCH。
- tests/native/tls-verifier.test.ts 在 off/verify 和默认/自定义 Base URL 下核对显式 disabled 的 JSON、SSE、工具历史，准备值与独立 TLS 实收只允许原生 CCH 差异；另核对省略时的原生 adaptive、原生业务省略/扩展保真，以及普通额外字段、未知类型和 enabled 改 adaptive 的 422 零发送。
- 同一原生套件对普通 API 和原生入站核对 Accept、浏览器访问开关的精确值、显式不同值及大小写混合的 Accept-Language 有序多值；tests/local-pool/gateway.test.ts 另核对实际 293 --print 客户端的 Node TLS 实收头值不重复。
- 同一原生套件分别核对原版与精简版的 User-Agent 为 claude-cli/2.1.293 (external, cli)，billing 包含 cc_entrypoint=cli；不再主动设置 SDK client-app。最终 CCH 由实际 TLS 接收正文独立验证，不用标签替换或日志投影代替原生生成；兼容与 CCH 不能解释为账号免封保证。
- 原版与登记轻量文件运行同一原生套件，核对同 session 多轮、Unicode、空闲及流中崩溃后的重建。独立部署须隐藏原版/源码/构建目录后仍能运行；重复生成核对分发及执行体 SHA256。
- 完整必需部署文件总量 ≤27933052 B。保留总启动到首轮、就绪后首轮及暖复用实测，初始化与解包计入启动；控制面、额外空间、RSS、页缓存和本地合成上游边界分别记录。2026-11-05 用户已接受当前延迟，vm2api 相对速度不再是当前准入；scripts/benchmark-runtime.ts 仍保留固定标杆、五轮六作业和旧 1.10 诊断规则，原 passed/退出状态不修改。
- tests/unit/{redaction,startup-failure,header-policy,profile,engine,worker-protocol}.test.ts：秘密及截断边界不泄露，调用方凭据不转发，拒绝未知身份；初始化错误保留受控原因且等待写完，取消、错帧和迟到输出隔离，不重放或遗留进程。tests/unit/{static-prompts,static-text}.test.ts 核对缓存条件变化、失败不入缓存及 UTF-8 预算；原生套件另核对模型/工具交替恢复后无串值。
- 原生验证仅使用专用 HOME、合成凭据和 unshare 网络命名空间；不能因测试失败切换真实账号。

## Scenario: 前置上游选择与按需 TLS 验证

### 1. Scope / Trigger

- 启动配置、原生发送和控制侧观测跨层联动；权威实现为 src/shared/upstream.ts、src/control/tls-verifier.ts 与 native/tls-verifier。
- 官方来源身份继续由 source-profile.ts 所有，辅助程序独立登记于 tls-verifier-profile.ts；不能用辅助程序哈希冒充官方 CC，也不以旧精简产物自动取得新能力。

### 2. Signatures

- EngineConfig.baseUrl?: string；ServerConfig.modelOverride?: string、nativeIngressPolicy?: NativeIngressPolicy、tlsCapture?: 'off' | 'verify'。
- readNativeBaseUrl(value: string | undefined): string | undefined；selectUpstreamModel(prepared: PreparedInput, override?: string): PreparedInput。
- TlsVerifierEngine.create(config: EngineConfig, previewLimit: number): Promise<TlsVerifierEngine>；Engine.takeFinalCapture?(requestId: string): FinalCaptureSample | null。
- expectedTlsWrite(event: Extract<RuntimeEvent, { type: 'cc_prepared' }>): TlsExpected，字段为 request_id、body_bytes、body_sha256、cch_offset: number | null、headers。
- bun run build:tls-verifier 独立构建 dist/tls-verifier 及来源清单；bun run test:tls 在仅回环网络验证实际原版和独立上游。

### 3. Contracts

- CCRB_NATIVE_BASE_URL 可选，不设置时不传 ANTHROPIC_BASE_URL；只接受无凭据、query、fragment 或空白的 HTTP(S) 绝对地址，保留 SDK 路径前缀语义。旧精简运行时尚未验证该配置时明确拒绝。
- CCRB_MODEL_OVERRIDE 只在前置覆盖根 model，原始入站保留；历史消息、工具内部同名字段及分类证据保持。CCRB_NATIVE_INGRESS_POLICY 默认 strict，local_base_url 仅由启动侧开启，与上游和验证开关独立。
- CCRB_TLS_CAPTURE 默认 off：官方 CC 直接对外，不创建辅助进程、监听或私有 CA。verify 仅覆盖 Linux x64、固定官方原版 293、HTTPS Messages/HTTP1.1、遥测 off、直连或 HTTP CONNECT 上游代理；不支持组合明确拒绝，不改用 Node 或隐式直连。
- verify 的 TLS 实现为独立固定画像，CC 仍唯一生成业务、账号上下文及最终 CCH。内部自定义目标是否产生 CCH，取决于同次内部 CC；prepareNativeBody 只按实际生成上下文准备或省略占位，不强行补回。
- 本地认证 CONNECT 同时核对冻结目标及实际 worker PID 的 TCP/socket FD 所有权；一条原生连接对应一条上游连接。上游 CONNECT 沿用原生字节、头顺序和连接特征，只删除本地代理凭据或替换为冻结的上游代理凭据。Messages 请求行、头和正文不经二次 HTTP/JSON 组装。
- 作业在实际 ready 后绑定代次，取得 cc_prepared 校验依据后才写上游；不新增 HTTP 池、请求重试、模型回退或默认总时限。取消/退休先收口本代连接，保留原生复用、重连与半关闭语义；3xx 原状态返回并记 http_error，不自动跟随。
- CCH 槽位定位接受现有 billing 合同的前导空白、尾部空格/制表符、首/末字段；只在观测副本中改变一个已知 ASCII 字符，比较序列化首个差异后换算 UTF-8 偏移。业务可包含任意同名标记或 CCH 示例文本，不能以固定哨兵冲突拒绝；无 CCH 时 offset=null。该过程不改发送正文，也不生成最终 CCH。
- 辅助程序按固定依赖锁、第三方快照及许可独立构建，生产不引用外部 cc2api 工作目录或缓存 rlib。构建记录不自动授信；核验独立 SHA256 后经打开的 FD 执行。产物采用原子更换路径，不能原地截断已运行进程映像。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 非法端点、模型或枚举 | 启动 native_configuration/503，无业务发送 |
| verify + HTTP、旧精简、遥测 on 或未支持代理 | tls_verifier_configuration/503，不兜底发送 |
| 辅助程序缺失、哈希不符或失效 | 明确 unavailable/identity/failed；不切换发送器或重放 |
| 实例、代次、请求、序号或帧结构不符 | 私有协议失败并隔离，不归到下一作业 |
| 正文含内部旧标记、billing 带合法空白 | 正常发送及核验，不能误报 502 或 integrity_mismatch |
| CCH 缺省 | 校验实际实体哈希，不猜槽位或补 CCH |

### 5. Scenarios and Examples

- 正常：仅配置根模型，CC 使用原生端点生成对应请求；端点、模型都未设置时保持原生选择。verify 开启后由最后 TLS 写入处取得证据。
- 边界：正文讨论 `__ccrb_cch_observation_slot__`，或合法 billing 写为 `cch=12345 \t;`，业务及采集均应完成；日志预览可截断而整体哈希继续完整。
- 错误用法：把第一跳 TLS 实收、JS 组装值或模拟 TLS 实现称作官方最终网络实收。正确处理：分别登记来源、实现身份及最后本地写出范围。

### 6. Tests Required

- tests/unit/{upstream,tls-verifier,native-input}.test.ts：默认与非法配置、根模型选择、任意业务标记、合法 billing 空白、UTF-8/转义前缀及唯一槽位；原对象不变。
- tests/native/tls-verifier.test.ts：普通/原生输入覆盖组合、最后 HTTP/实体哈希、完整公开 ClientHello、TLS1.2/1.3/HRR、证书、认证代理 CONNECT、复用/重连、2/8 MiB、长流/取消/错误、PID 及双实际客户端各三个子代理。CHK-001/CHK-002 场景逐项核对 off/verify、单次发送与 captureError=null。
- Cargo fmt、clippy、locked build/test：真实 ML-KEM+X25519 交换和无效输入、CCH 跨写入边界、写入中断仅计成功前缀及 CONNECT 凭据选择。

## Scenario: 固定 293 原生正文接入与构造失败收口

### 1. Scope / Trigger

- 同一 HTTP 入口区分普通 API 和完整原生 CC 正文；输入证据、必要改写、原生发送、日志路径须保持一致。
- 依据 src/shared/{input,native-input,parameters}.ts 和 src/runtime/293/job.ts；模型规则仅依据固定官方源，不从其他版本或模型名称猜测。

### 2. Signatures

- readNativeInput(body: JsonObject, policy: NativeIngressPolicy = 'strict'): NativeInput | null；没有 billing 前缀返回 null，疑似原生但损坏时明确失败。
- mergeNativeContext(context: ContextInput, native: NativeInput): ContextInput；显式归因冲突返回 400。
- prepareNativeBody(body: MessageBody, generatedMetadata: unknown, policy: NativeIngressPolicy = 'strict', generatedSystem?: unknown): JsonObject；严格分支更新账号归属及 CCH 占位，兼容分支另采用同次 SDK 实际 CLI 入口。
- generateNativeRequest(prepared, bindings, signal, send?, purpose: 'business' | 'transport_context' = 'business'): Promise<NativeRequest>；用途只由内部调用方指定，不属于 HTTP 或私有作业字段。
- ensureMessages(expected: ApiMessage[], nativeMetadata: NativeMessage[], actual: unknown): void；普通 API 的规范化历史保留守卫。
- BridgeInput.inputFormat 与 RequestContext.inputFormat 为可选 'api' | 'claude_code'；HTTP 由 parseInput 计算，不能由信封直接指定。私有作业校验 input.inputFormat，日志解码校验 context.inputFormat 的已知枚举，历史缺失保持可读。

### 3. Contracts

- 默认严格策略下，原生根 system 必须为数组，首段是唯一独立 text billing 且不带 cache_control。cc_version 匹配 2.1.293.<三位十六进制>，cc_entrypoint=cli，CCH 为五位十六进制；重复字段、歧义 CCH、非法 cc_is_subagent、prompt UUID 或轮次均拒绝。这里只核对入站形状，不凭 billing 授权账号或执行。本地 Base URL 兼容例外见下文独立场景。
- metadata.user_id 必须是 JSON 字符串，device_id 为 64 位十六进制，account_uuid 为空或 UUID，session_id 为 UUID。session、可选 billing prompt 和主/子身份合并显式信封及原生头，冲突拒绝；子代理及 workflow 仍须提供既有合同所需关联，不能猜父子身份。
- 默认 preserve 策略下，原生保留业务 system、messages、tools、thinking、输出配置、缓存位置及 thread/diagnostics/fallbacks/safeguards 等扩展 JSON；省略字段保持省略，原生 system 角色和消息扩展允许。不加入默认 CLI system、提醒、工具、strict 或种子默认参数。显式启用的消息缓存策略按下文独立合同处理。
- `parseInput` 在普通 API/原生识别前，以正文的浅副本删除三个精确根字段 settings、claude_settings、env；无论字段值的 JSON 类型均删除后继续既有校验，不读取、合并或执行调用方设置。两种 HTTP 入口及显式信封 body 共用该行为，strict/local_base_url 相同；信封根字段仍按既有白名单校验。原始对象及入站日志表示保持，日志继续先脱敏再保存。
- 根 extra_headers、extra_body、headers、proxy_url、api_key、oauth_token、claude_binary、claude_home、claude_config_dir、workdir 继续作为本机控制字段拒绝；内部 readNativeInput 仍拒绝带任一本机控制字段的未清理正文。工具 schema、tool_use.input 和其他嵌套业务数据中的 settings/claude_settings/env 保留。其他扩展只作为上游数据，不改变账号、目标地址、代理或工作目录。
- 同一 SDK 的安全种子仅取得当前账号发送上下文，内部用途为 transport_context；不对即将丢弃的种子执行业务消息、提醒或参数保留断言，不能因 Sonnet 5 的种子布局误拦原生分类请求。普通 API/bootstrap 仍为 business 用途，真实业务保留检查不删除。两种用途都只进入一次真实构造和发送回调，验证发送结构及上下文；唯一 fetchOverride 中才替换为原生正文。metadata.user_id 只用原生 SDK 生成的 device_id/account_uuid 覆盖归属，保留原 session 及其余字段；billing 只定位独立 CCH 字段写 00000，保留其余文本与合法间隔，最终值仍由 Ree 的原生传输生成。入站 beta 沿用其列表，普通 API 继续按生成列表校验；凭据与传输头遵循共同策略。
- 入口仅检查实际组装所需结构，max_tokens/temperature 须为有限 JSON 数值，不判定数值范围、thinking 枚举/最小预算或工具名称与选择组合的模型政策。原生参数原值交上游；普通 API 仍须满足原生装配的结构和显式字段保留要求，原生工厂不能表达时明确失败，不能静默改值或推断实际上游能力。
- 构造边界异常先保存原因并取消；model_fallback_triggered 和助手 isApiErrorMessage 事件在未采集正文时明确 422，只公开受控分类，不启动模型回退，不等待整体超时。
- 普通 API 的 tool_result 仅允许原业务完整前缀及同次已知完整提醒合并；Environment 提升为 system 只允许对应已知完整正文。业务丢失、改写、未知注入及未消费附件均拒绝，不能靠忽略所有提醒通过。终态、idle、取消退役、响应所有权和单次发送合同不变。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 无 billing 前缀 | 普通 API 白名单及角色校验 |
| 正文根 settings、claude_settings、env | 删除后继续普通/原生识别及原有校验，不应用调用方设置 |
| 版本、billing、metadata 不合法，或其余根本机控制字段 | 422，0 发送，不回落 API 重组 |
| metadata/billing 与显式上下文或头部冲突 | 400，0 发送 |
| 原生 thinking 未来类型、低预算或强制工具组合 | 保留原值，不根据种子或固定模型政策提前拒绝，由上游判断 |
| max_tokens/temperature 非有限数值，或关键字段结构无法组装 | 400，0 发送 |
| 原生身份无法取得 | native_identity/503，不沿用调用方账号归属 |
| 原生构造失败事件或业务投影不能保留 | 确定失败并收口，不以模型重试、隐式 fallback 或超时掩盖 |

### 5. Scenarios and Examples

- 正常：默认 preserve 下，原生主请求自带业务 system、缓存、线程和工具历史，仅改设备/账号归属及最终 CCH，保留版本后缀、轮次、签名和会话。
- 边界：原生省略 stream/max_tokens/tools 时不从种子补入；缺可选 billing prompt 时可生成头部 prompt，metadata 会话仍保留。子代理压缩保留子身份及 compaction 类别。
- 正常：Sonnet 5 分类请求只借用同次 SDK 的发送上下文，system/messages/stop_sequences 仍来自原生输入，种子提醒不会成为发送或拦截依据。
- 边界：正文根 env=null、settings=false 或 claude_settings 为数组时均移除后继续；工具参数中的 env、settings、claude_settings 保留。清理后仍带 proxy_url 或损坏 billing 的请求继续明确拒绝。
- 错误用法：递归删除业务参数内的同名字段，或修改原对象后将日志称为原始入站。正确做法是在 parseInput 的正文浅副本上只删三个根字段，原始哈希与日志脱敏独立处理。
- 错误用法：把已有原生正文再次交给 OM 添加默认提醒，或仅替换版本字符串接纳 303。正确做法是固定 293 原生分支保真，版本不匹配明确拒绝。
- 错误用法：工具续轮守卫失败后忽略全部 system-reminder。正确做法是逐项关联同次已知提醒，同时保留完整业务前缀并拒绝未知注入。

### 6. Tests Required

- tests/unit/native-input.test.ts：普通白名单、原生保真/缓存/省略、版本/身份/重复/冲突、本机控制、模型参数与工具组合原值保持、错误结构拒绝及 billing 间隔占位；两类输入、两种信封表示和两种入站策略删除三个根字段的各类 JSON 值，原输入与嵌套 schema/tool_use.input 保持。
- tests/unit/message-projection.test.ts：字符串/数组工具结果的已知提醒合并、Environment 提升、业务丢失/改写和未知注入反例。
- tests/native/native.test.ts：当前原版 + preload 验证保真正文、六类归因、原工具历史、参数透传、26 MiB 完整正文、错误/取消及后续隔离，独立核验已发送 TLS 实体的 CCH；两类输入清理根设置后恰好一次 TLS 实收，业务工具字段保留。旧轻量文件内嵌代码不随源码变化；只有重新构建并验证的最终哈希才能声明具备本次合同。
- tests/integration/control.test.ts：0 预算、20 个提交保持串行、取消及慢消费者；两种 HTTP 入口接受三个根设置字段，组装后移除，原始入站 SHA256 和设置字段保留且秘密脱敏。tests/integration/local-pool.test.ts：合成 Sonnet 5、26 MiB 完整哈希及超过旧 50 秒等待预算。
- 原 23 组 API 与新增原生矩阵保留稳定 ID、预期状态、发送次数和最终采集缺失原因；支持输入成功，不支持输入明确拒绝，不能删用例换取全通过。只用合成凭据与无外网回环。

## Scenario: 官方运行时压缩与新版本适配

### 1. Scope / Trigger

- 升级官方源版本、Bun 基底、模块绑定、资源裁剪策略或打包工具时，重新执行本节准入。当前脚本只接受已核验的 Linux x64、官方 2.1.293 与 Bun 1.4.3；本节提供适配顺序，不表示脚本已支持任意新版本。
- 可复用路线为：核对来源和容器 → 从源码模块重建桥接专用依赖闭包 → 按固定环境裁剪资源 → 压缩完整执行体并加入内存加载器 → 验证独立部署、原生行为和常驻速度。先减少不需要携带的内容，再选择压缩方式；仅给完整官方程序加壳不能替代这套验证。
- 实现入口为 scripts/build-runtime.ts、scripts/runtime/{image.py,compile.ts,loader.c}；最终操作说明见 [docs/runtime.md](../../../../services/runtime/docs/runtime.md)，293 的历史方案及最终证据见 [验收记录](../../../../docs/migrations/runtime-footprint-acceptance.md)。

### 2. Signatures

- buildRuntime(args: string[]): Promise<void>：`bun scripts/build-runtime.ts --source <固定官方文件> --out <尚不存在的产物> [--sevenzip <固定7zz>] [--sdk <固定SDK归档>]`。
- 容器内部步骤：`python3 scripts/runtime/image.py extract <来源> <临时模块目录> <源SHA256>`；`python3 scripts/runtime/image.py prune <专用ELF> <执行体> <裁剪报告>`。它们由构建驱动调用，不是任意版本的通用提取器。
- benchmarkRuntime(args: string[]): Promise<void>：`bun scripts/benchmark-runtime.ts --binary <候选文件> --reference <固定标杆> --output <证据目录>`；候选及标杆均须通过脚本的身份核对。

### 3. Contracts

1. **固定每版输入**：先记录官方版本、完整 SHA256、实际 Bun 版本/revision、模块路径及原生接口定义。293 的来源在 src/runtime/293/source-profile.ts，产物在 src/runtime/compact-profile.ts。新版本必须重新定位并读取实际定义，不能只替换这两处哈希、混淆符号或版本字符串，也不能拿另一个项目的定制程序充当官方来源。
2. **核验容器后提取**：校验 ELF 架构/节表、Bun 尾标/长度/模块表、各指针和路径、编码及 loader；拒绝越界、重复和未知记录。提取到临时目录，保留可读模块/资源及逐项摘要；专用构建不复制原版整套应用字节码与共享缓存。293 的模块数、标志、ICU 偏移和摘要是版本专属断言，新版本须重新测得，不能删除断言让未知布局继续执行。
3. **闭合依赖后重建入口**：只引用桥接需要的原生构造、发送、配置和会话接口。通过 AST 转换已核验的静态 import.meta.require/辅助调用，使 JS、文本及通过路径读取的压缩资源可打包；逐项记录模块摘要、转换位置、内建模块和残余动态调用。空 metafile imports、接口 typeof 正确或一次导入成功均不代表闭包成立；残余动态路径须逐项说明可达性，并用脱离提取目录的真实请求验证。不能全局替换字符串、强改所有引用为静态 import 或为未知工厂添加纯调用标记。
4. **保留已验证的原生能力**：当前通过原版 BUN_OPTIONS 加载构建驱动，Bun.build 的 compile.executablePath 指向已核验原版；env='disable'，关闭 dotenv/bunfig/tsconfig/package.json 自动加载，保留函数名。构建前及裁剪前核对固定原生节；裁剪后 .text、.bun_builtins、.data 必须不变，.rodata 的预期变化单列。其它可追溯 Bun 基底须重新通过真实 TLS 发送、FetchSession/CCH 回归；通用 Bun 的版本相近或 trim 选项不报错都不构成兼容证据，不用 JS 补写缺失 CCH。
5. **按实际使用范围裁剪资源**：当前 LANG=C.UTF-8，保留 ICU root/en/en_*、共享池/索引、完整字符及规范化数据、全部 brkitr 规则/字典。仅清零不需要的 locale 定制资源并压紧目录，保留项地址不动；293 为 3990 项保留 801 项、移除 3189 项、清零 5839120 B。此步骤降低待压缩数据的熵，不缩短 ELF 或保证 RSS 同比例减少；不能把桥接专用产物宣传为完整多语言 Intl CLI。新增 locale 能力或升级 ICU 时重做保留集合及回归。
6. **对完整可执行产物计量**：当前固定 7-Zip 26.05 的 BCJ2 + 三路 LZMA2，主流字典 128 MiB/fb=273、其余两路 16 MiB，单线程并关闭归档时间字段；完整参数以 recipe.archive 为准。C SDK 的解码/SHA256 部分静态编入自有加载器，工具及 SDK 归档均核验 SHA256。比较的是包含加载器及全部新增专属依赖的最终 stat 字节数，不是归档大小或 Bun.build 的 BuildArtifact.size。当前上限为固定 vm2api 标杆的 27933052 B，换标杆须另行固定身份及验收目标。
7. **分开核验三种身份和空间**：官方源、外层分发文件、解码执行体各有独立 SHA256。加载器限制单个非目录载荷、检查解码长度/SHA256，写入封存 memfd，释放解码缓冲后 fexecve，同 PID 执行；控制层经核验 FD 启动，并在握手后检查 /proc/<pid>/exe。外部 manifest 只作证据，不能自行授信；接纳表内的最终身份必须绑定完整验收，失败候选不得交付。部署文件、磁盘展开、内存文件及 RSS 分列。
8. **把启动成本放在进程边界**：正常串行作业复用单账号进程，每轮仍建立新原生根和取消/日志作用域，遵守上一场景的终态加 idle 合同。当前本地构造初始化在 worker_ready 前完成且在模型发送前中止，成本计入启动至首轮完整完成；不能靠提前 ready、漏算解包或每轮重新启动来宣称达标。

构建报告为 `<out>.manifest.json`，schema_version=1；下列实际字段是每版复核入口，不应另外维护一份可自行授信的部署清单：

| 字段 | 类型与含义 |
| --- | --- |
| source.version、source.sha256 | string；固定官方来源身份 |
| kernel.version、kernel.revision、kernel.sections_before_prune | string、string、Record<string,string>；实际基底和裁剪前原生节摘要 |
| launcher.sha256/bytes、image.sha256/bytes | string/number；外层及实际执行体各自身份和字节数 |
| deployment.files、total_bytes、limit_bytes | `{name,bytes,sha256}[]`、number、number；完整必需部署集合及预算 |
| deployment.required_external_files、existing_system_libraries | string[]；新增外部依赖与既有系统库分别登记 |
| deployment.disk_expansion_bytes、memory_file_bytes | number；磁盘展开与内存文件分别登记，不能相互抵扣 |
| recipe.bridge_sources、archive、gcc、tool_sha256、sdk_archive_sha256、sdk_files、icu | 源码摘要、参数、编译器、工具/SDK 身份及资源策略；变更后重做产物验收 |
| closure.mapped_modules、rewrites、native_imports、remaining_dynamic_calls | 依赖映射、转换位置、内建模块及残余动态调用审计 |

### 4. Validation & Error Matrix

| 条件 | 行为或准入结论 |
| --- | --- |
| 来源/工具哈希错误、未知 ELF/Bun/ICU 布局、路径或资源异常 | 构建失败，不以放松断言或读取旧提取目录补齐 |
| 输出或同名 manifest 已存在 | 拒绝覆盖；来源、其它项目及旧产物保持原状 |
| 来源或桥接源码在构建期间变化、最终文件超预算 | 不输出可接纳产物，清理临时目录 |
| 归档、解码长度/SHA256、memfd 或封存/执行失败 | 加载器非零退出，不自动回退或从磁盘展开 |
| 未登记分发文件、实际执行体不符或运行时文件被替换 | 发送前拒绝或隔离进程，不能依赖 manifest 授信 |
| 缺 CCH、支持输入/Unicode 行为退化或多轮状态污染 | 兼容性不通过；不能删减原有覆盖换取体积 |
| 部署体积超预算或安全/兼容验证不通过 | 保留失败证据，候选不得作为达标版本交付 |
| 历史三项相对速度诊断未通过 | 保留原样本、passed=false 及退出状态；当前延迟已获用户接受，不据此声称旧性能目标达标，也不放宽安全/兼容约束 |

### 5. Scenarios and Examples

- 正常：固定官方输入，在两个独立临时目录以同一工具/源码/配方构建，比较分发及执行体 SHA256；审计数组可按条目集合比较，不能忽略二进制差异。当前 CLI 缓存/遥测产物为 27383864 B（26.12 MiB），它是本版结果，不是对新版本的体积保证；完整身份与证据见 docs/runtime.md。
- 边界：先隐藏原版、项目 src/scripts、提取目录与旧临时文件，再在独立 HOME/网络命名空间用合成凭据完成真实回环请求和 shutdown；部署只留下清单中的必需文件。普通 API 和原生入站分别验收。当前内存执行体约 107.60 MiB，与磁盘 26.12 MiB 分列。
- 错误用法：拿到新版本后只改 PROFILE_293.sha256，沿用旧模块名和 ICU 偏移。正确做法是先重新测定容器、原生符号及资源合同，适配构建，再对最终哈希运行全部准入；当前 293 入口继续只接受原有固定来源。
- 错误用法：用压缩包或 --version 耗时证明体积/速度达标，或把用户接受延迟改写为 benchmark 通过。正确做法是比较完整可执行部署集合，保留协议边界的总启动、就绪后首轮及暖复用实测和原诊断结论；各阶段中位数不能相加代替总耗时，不为追赶旧目标引入未验证的研究裁剪。

当前版本的可执行验证入口如下；未来适配须先更新各入口内的来源/版本绑定，不能把命令成功假定为支持新版本：

```bash
bun scripts/build-runtime.ts --source /绝对路径/固定官方文件 --out /绝对路径/新产物
CCRB_TEST_CLAUDE_BINARY=/绝对路径/新产物 bun run test:native
bun scripts/benchmark-runtime.ts --binary /绝对路径/新产物 --reference /root/project/vm2api/share/wrap-cli/cli-node --output artifacts/runtime-benchmark
```

最后一条命令为历史相对速度诊断，原 1.10 倍判断不等于当前版本的准入条件。

### 6. Tests Required

- 构建负例：损坏来源/原生节、未知标志/编码/布局、越界和重复路径、缺资源、超过预算 1 B；断言失败、不生成最终产物且来源未变。当前故障夹具及原始结果保存在上述验收目录，不把临时研究脚本当作通用产品命令。
- 闭包与独立部署：核对模块/资源摘要、原生扩展及每个残余动态调用；隐藏构建输入后完成所有支持路径，记录运行生成文件；只跑导入探针不算通过。
- 原版及最终候选分别执行 tests/native/native.test.ts，独立核对真实 TLS CCH、头部、metadata/billing、父子与压缩标识、工具/thinking、流/非流、Unicode、原始响应和单次发送。默认 Intl、en/zh/ja/th/ar 分词、组合字符及 emoji 另作原版对照。
- tests/unit/{profile,engine,worker-protocol}.test.ts 及 tests/integration/control.test.ts：未知身份/文件替换拒绝，同 PID 多轮的状态隔离，取消/错帧/迟到帧后重建且不重放，关闭不留孤儿进程。
- scripts/benchmark-runtime.ts：交错且反转顺序，两方各五个新进程、每进程六轮；同输入、回环上游和响应负载，每轮一次实际发送。直接保留 startup_to_first_complete_ms、ready_to_first_complete_ms、后五轮 elapsed_ms 及三项中位数；旧 ≤1.10 判断只作历史诊断，不改原失败样本。RSS、额外文件、页缓存及协议/控制面边界单列，计时期间不并行压缩。
- 重复构建：固定所有输入和工具，在独立构建目录至少两次生成，断言分发及执行体哈希一致、部署文件总量达标，重新核对 manifest 与实际 /proc 执行体；来源或配方变化后不能沿用旧产物的通过结论。全部验证继续只使用合成凭据、专用 HOME 和无外网回环。

## Scenario: 可选 sub2api 消息缓存策略

### 1. Scope / Trigger

- 本机缓存配置贯穿控制层、私有握手、原生单次发送和日志；共享类型及校验位于 src/shared/runtime-policy.ts，纯处理器位于 src/shared/cache-policy.ts。

### 2. Signatures

- readCachePolicy(value: unknown): CachePolicy，CachePolicy 为 preserve/sub2api。
- applyCachePolicy(original: JsonObject, outgoing: JsonObject, mode: CachePolicy): CachePolicyResult，返回 body 和 CachePolicyDecision。
- runNativeJob(..., cachePolicy: CachePolicy = 'preserve') 仅在真实发送回调应用策略；generateNativeRequest 的本地 bootstrap 不应用策略。
- worker_ready.cache_policy?: CachePolicy；cc_prepared.cache_policy?: CachePolicyDecision。HTTP/事件 schema 1 和 worker schema 2 保持原版号，可选字段由统一协议解码器校验。

### 3. Contracts

- CCRB_CACHE_POLICY 默认 preserve，显式值仅接受 preserve/sub2api。readConfig、直接 NativeEngine/createEngine 和 worker 边界均校验，配置固定到引擎/物理进程，修改后重建，不从请求头或正文取得策略。
- preserve 不规范化消息或新增标记。sub2api 遇到调用方已有顶层或嵌套协议消息标记、任一根 cache_control、未知缓存结构或没有候选时整体保留。工具 input/schema 等业务对象中的同名字段不解释为控制指令。
- 可优化时只移除本轮 SDK 自动消息标记，保留 system/tools 的原标记；先完整评估候选及预算，再克隆应用，跳过分支不改变原文。
- 候选先为末条消息的最后一个可缓存块，消息至少四条时再选倒数第二个 user；总显式预算四减去 tools/system 的既有数量，尾部优先。仅 assistant text、user text/tool_result 可选，thinking、redacted_thinking、图片和 tool_use 不选。仅实际选中的字符串 content 转成 text 数组。
- 新标记为 ephemeral，不添加 scope；默认 1h，若前置 tools/system 标记存在 5m 或省略 TTL，则新标记用 5m。未知类型/TTL/结构及既有反向 TTL 顺序触发保留，不修补调用方原值。
- 所有改动在 cc_prepared 快照及 Ree 之前完成；原生 transport 继续生成最终 CCH。只读诊断包含 mode/action/reason/selected/breakpoints/ttl，不保存业务文本或宣称上游命中。
- 旧握手缺少 cache_policy 时仅兼容 preserve；显式 sub2api 缺能力或回显不符返回配置错误，业务作业不发送。握手后故障与发送竞争时保留首个故障，不能把原配置/协议错误覆盖成通用 runtime_exit。
- /api/health.runtimePolicy.cachePolicy 只表示已配置策略。精简新能力须对确定哈希完成独立重复构建及原生回归后登记，外部 manifest 不授信。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 非法配置值 | native_configuration/503，启动/配置阶段失败 |
| 旧 worker 或策略回显不符 | native_configuration/503，隔离进程且业务发送为零 |
| 畸形私有握手或诊断 | runtime_protocol/502，隔离进程 |
| 调用方消息已有标记或根缓存 | 保留，分别记录 caller_message_breakpoints/root_cache_control_present |
| 预算耗尽、无候选或不支持结构 | 保留，记录确定跳过原因，不猜测修复 |

### 5. Scenarios and Examples

- 正常：显式 sub2api，五条交替消息且无调用方消息标记，选择第三条 user 和第五条 user 的末尾可缓存块。
- 边界：三个 tools/system 标记仅剩一格，尾部优先；四格已满时不转换候选字符串。已有 system/5m 时新标记用 5m。
- 错误用法：把调用方 5m/scope 标记清除后强制全部 1h。正确做法是保留调用方锚点，整体跳过并说明；实际缓存命中以上游 usage 为准。
- 错误用法：给旧产物传新环境变量便宣称策略已应用。正确做法是核验 worker 能力及回显，显式能力不足明确失败。

### 6. Tests Required

- tests/unit/cache-policy.test.ts：默认值与非法配置、不可变输入、短长历史、助手尾部、string/tool_result、thinking/图片、预算、TTL、原有标记及未知格式。
- tests/unit/{engine,worker-protocol}.test.ts：旧握手与不匹配配置在作业发送前失败，畸形诊断拒绝，握手后故障保持原始状态。
- tests/native/native.test.ts：API/原生两路径的策略应用及 caller/root/budget 跳过，最终接收正文与 CCH、日志说明及单次模型请求；原版和精简都执行。
- tests/browser/logs.spec.ts：历史详情、原生来源和中间值标签继续正确；生产 wire_final 不因离线接收样本变成已采集。

## Scenario: 默认关闭的官方第一方遥测

### 1. Scope / Trigger

- 本机开关贯穿控制配置、worker 能力握手、原生事件采集及进程退出。类型和校验由 src/shared/runtime-policy.ts 持有，原生生命周期由 src/runtime/293/telemetry.ts 持有。
- 当前导出仅适用于已核验的官方 293；增加或升级遥测接口必须先读取实际定义，同步 source-profile/native 类型及构建输入，并重新验证原版与精简产物。

### 2. Signatures

- readTelemetryPolicy(value: unknown): TelemetryPolicy；TelemetryPolicy 为 off/on。
- createNativeTelemetry(bindings: TelemetryBindings, policy: TelemetryPolicy, isBusiness: () => boolean): NativeTelemetry；start(): TelemetryHandshake；close(): Promise<void>。
- TelemetryHandshake 为 `{policy:'off',state:'off'}` 或 `{policy:'on',state:'initialized'|'suppressed'}`；worker_ready.telemetry 可选，由 isTelemetryHandshake 和 decodeWorkerFrame 校验。
- Engine.telemetryState?: TelemetryState；GET /api/health.runtimePolicy 为 `{cachePolicy,telemetry,telemetryState}`。TelemetryState 为 off/pending/initialized/suppressed/unavailable。

### 3. Contracts

- CCRB_TELEMETRY 默认 off，显式只接受 off/on；readConfig、直接 NativeEngine/createEngine 及 worker 入口均校验。配置固定到引擎/物理进程，修改后关闭并重建，不能从请求头或正文启用。
- off 从模块初始化、bootstrap、业务复用到退出均保持遥测关闭，不调用官方 logger 初始化、业务采集或退出上传；不主动删除专用目录中的历史遥测文件。
- G_o 事件接收器在 initializeCli 前注册，初始化及 bootstrap 保持关闭，并使用业务 ALS 许可筛选。每轮结束撤销许可，迟到回调不能借下一作业的状态采集；on 只在 bootstrap 收口后启用。
- on 移除 DISABLE_TELEMETRY、CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC、DO_NOT_TRACK 的本轮关闭键，再调用官方 a4 检查资格。原生策略抑制时恢复关闭键，报告 suppressed；允许时先 Jb 配置第一方 HTTP 客户端的代理/CA，再 SLe 初始化 logger，成功才报告 initialized。不能只写字符串 0 或假设模型 FetchSession 已替第一方客户端配置网络。
- 自动更新、错误上报及 GrowthBook 远程功能配置分别保持禁用；不初始化含第三方通道的完整 CLI analytics sink。本轮只使用官方第一方鉴权、metadata、指标和 exporter，不补造事件或模拟进程指标。
- 官方 gyr 负责采样，模型目录 Nco/w9t 就绪后登记 gDn(tt()) 并由 Yus 脱敏，再交给 Jk。同步重入守卫防止元数据依赖递归记事件。可等待事件的接收回调也立即返回，实际采集在后台；目录等待和错误不得进入模型响应背压链。
- 最多跟踪 128 个进行中的原生采集承诺；这是退出收口集合，不是桥接自有事件队列。超限或采集失败丢弃遥测，批处理及重试仍归原生 exporter。
- close 停止接收新事件，等待已开始的采集并并行启动 MDs/bLe，整个清理预算 1000 ms，配合控制层 1500 ms 强制退出宽限。取消/强制退役可丢弃遥测，不能为补传重放模型、改变响应字节或下一轮归属。
- off 是本机关闭状态；pending 表示 on 尚无初始化完成的 worker；initialized 只证明 logger 初始化，不证明上传成功；suppressed 来自官方资格检查；unavailable 表示 demo/旧握手没有该能力。读取 health 不启动 worker，也不报告伪造的上传成功率。
- 旧握手没有 telemetry 时仅兼容 off；显式 on 缺能力或回显不同按配置错误隔离，业务发送为零。新精简身份须经双次构建、实际执行体、独立部署、完整原生回归及两项配置四组合证明后登记，外部 manifest 不授信。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 非法配置值 | native_configuration/503，在启动或直接引擎入口失败 |
| 显式 on 而旧 worker 缺能力或回显不符 | native_configuration/503，隔离且业务请求不发送 |
| 畸形握手，如 off/initialized 或 on/pending | runtime_protocol/502，不能以配置猜测实际状态 |
| 官方 a4 返回 false | suppressed，模型服务按原策略运行，不初始化或上传 |
| 原生网络/logger 初始化同步异常 | 受控 native_configuration/503，不回显原生秘密 |
| 元数据采集失败、超限或退出上传失败/超时 | 丢弃或有界退出，模型单次发送及原始响应保持 |

### 5. Scenarios and Examples

- 正常：本机 on，bootstrap 不采集；业务主请求和子代理产生原生事件，经同一显式代理/CA 上传，事件入口 cli、身份和会话来自各自原生业务作用域。
- 边界：on 但原生策略不允许时显示 suppressed；demo 为 unavailable。接收器返回 500 或持续等待时，health 可保持 initialized，但不能说明已上传成功，模型不重试。
- 错误用法：删除关闭变量便声称遥测已开启，或补造 tengu_init/api_success 作为证明。正确做法是接入固定版本官方初始化和真实事件链，以无外网回环实收验证。
- 错误用法：在模型响应路径 await flush，或为了退出遥测等待超过进程宽限。正确做法是后台采集、总计 1000 ms 的有界关闭，允许退出时丢弃遥测。

### 6. Tests Required

- tests/unit/telemetry.test.ts：默认值与非法值、off 零调用、原生抑制、初始化异常、采样/脱敏、目录等待、同步重入、128 承诺上限及永久等待的一秒退出。
- tests/unit/{engine,worker-protocol}.test.ts：状态来自实际握手、旧能力拒绝时零作业发送、畸形配置/状态组合拒绝，默认旧握手继续兼容。
- tests/native/native.test.ts：原版和最终精简均执行 preserve/sub2api × off/on，真实 TLS 模型正文/CCH、响应、业务会话及 cli 入口一致；off 零上传、on 实收原生事件，无 bootstrap/其他 API/明文 HTTP forward。
- 同一原生套件覆盖遥测 500、慢响应、有界关闭、开启后取消/退役/重建及下一业务归属；每作业只有一次模型发送，真实上游为零。使用独立合成 HOME/config，不触发真实账号或付费推理。

## Scenario: 本地 Base URL 的固定 293 原生入站兼容

### 1. Scope / Trigger

- 固定 293 的客户端使用自定义 Base URL 时会省略 billing CCH，--print 使用 sdk-cli；常驻本地池入口需要接纳这些实际形状，默认严格入口保持原合同。
- 仅适用于显式本地联调，不授权真实 Anthropic、不同版本、账号接管或工具执行。

### 2. Signatures

- NativeIngressPolicy = 'strict' | 'local_base_url'；parseInput(raw, incomingHeaders = [], nativeIngressPolicy = 'strict'): BridgeInput。
- BridgeInput.nativeIngressPolicy 可选，只有控制层对已识别原生输入写入；decodeRuntimeJob/decodeWorkerCommand 验证已知枚举且 inputFormat 必须为 claude_code。
- prepareNativeBody 的 policy/generatedSystem 参数来自内部作业与同次 SDK 生成值，不从外部 JSON 授权。

### 3. Contracts

- local_base_url 接纳固定 2.1.293.<三位十六进制>、cc_entrypoint=cli|sdk-cli；CCH 可以缺失，存在时必须恰好一个独立五位十六进制字段。扩展值内伪装 cch= 同样按歧义拒绝。
- 其他 billing、metadata、tools、thinking、上下文与本机控制字段规则不变。原始 HTTP 入站仍按原表示保存，不在日志前改写后声称是原文。
- 兼容分支读取同次 SDK 实际生成、经验证的 CLI billing，形成发送入口；仅在同次上下文实际生成 CCH 时准备原生占位，自定义目标省略时不补回。账号归属仍取同次 metadata。业务正文、缓存位置、会话、轮次及父子扩展保留，最终 CCH 由原生传输生成。
- 本地模式只接纳已登记原版与当前 dist/preload.mjs。已发布轻量文件内嵌旧代码，源码更新不能使其取得新合同；重新构建并独立验证前不得混用。旧轻量严格路径继续使用原产物。
- 常驻入口及 TLS 映射的启动与预算规则由 logging-guidelines.md 的本地常驻池场景所有，不增加可由请求控制的运行时目标配置。

### 4. Validation & Error Matrix

| 条件 | 必须行为 |
| --- | --- |
| 默认严格入口收到无 CCH 或 sdk-cli | invalid_native_request/422，不回落普通 API |
| 显式本地模式收到合法固定 293、缺少 CCH | 保留业务进入原生发送，最终必须在 TLS 实收独立核验 |
| 重复、损坏或位于扩展值的歧义 CCH | 入站 422，不发送模型 |
| HTTP 信封企图指定内部兼容策略 | 不支持字段；不能自行启用策略 |
| 私有作业未知策略或普通 API 携带原生策略 | runtime_protocol/502 |
| 同次 SDK CLI 上下文缺失或不合法 | native_identity/503，不伪造入口 |
| 本地模式选择现有轻量产物 | local_pool_runtime/503，不静默回退 |

### 5. Scenarios and Examples

- 正常：启动侧调用 parseInput(body, headers, 'local_base_url')；原生输入内部标记策略，--print 的 sdk-cli/无 CCH 正文保留后交给真实 CLI 发送上下文处理。
- 边界：原生 tools 省略保持无工具；有效已有 CCH 同样准备占位，子代理上下文仍须提供 agentId，冲突继续拒绝。
- 错误用法：给 HTTP body 添加 nativeIngressPolicy 以绕过严格校验，或从预览重算 CCH 冒充最终值。正确做法：由独立启动入口启用兼容，保存实际原文，从 TLS 接收端验证最终值。

### 6. Tests Required

- tests/unit/native-input.test.ts：默认严格行为、cli/sdk-cli、CCH 缺失/有效/重复/损坏/扩展值歧义、实际生成上下文缺失、业务与缓存保持。
- tests/unit/worker-protocol.test.ts：内部枚举、原生格式限定，不能靠包装改变策略。
- tests/local-pool/gateway.test.ts：实际 --print、真实伪终端交互 CLI、Read 工具续轮、有效/缺失 CCH、子代理与 TLS 非零 CCH；测试在无外网空间运行。

## Scenario: 实际 CLI 原生用途归因

### 1. Scope / Trigger

- 对已经通过固定 293 billing/metadata 校验的原生正文识别用途；普通 API 不根据业务关键词推断类别。
- 实际 CLI 的自动权限分类、会话标题、手动和自动压缩可能没有显式 request-class；由完整已验证构造补充用途，不能全部回落为主会话。
- 识别只声明客户端提供的原生构造证据，不授予身份认证、配置修改或本地工具执行权限。

### 2. Signatures

- readNativeClassification(body: MessageBody): NativeClassification | undefined；prepareInput(input: BridgeInput): PreparedInput。
- RequestContext.classification 可选，NativeClassification 是 purpose/profile 配对的联合，source 固定 native_profile；HTTP ContextInput 不接收 classification。
- classificationContext(classification: NativeClassification): Pick<RequestContext, 'requestClass' | 'querySource'>；isNativeClassification(value: unknown): value is NativeClassification；isNativeClassificationContext(value: unknown): boolean。入口、私有作业和日志 API 复用统一映射与校验。

| purpose | profile | requestClass | querySource |
| --- | --- | --- | --- |
| auto_permission_classifier | cc293-auto-mode-xml-s1 / cc293-auto-mode-xml-s2 | auxiliary | auto_mode |
| session_title | cc293-session-title-v1 | auxiliary | generate_session_title |
| compaction | cc293-compact-full-v1 | compaction | compact |

### 3. Contracts

- 固定版本已验证 XML 两阶段共同使用完整 system 静态摘要，按官方结构只规范化 deny rules 列表插槽，其余静态内容及对应阶段收尾摘要必须一致。system 最多 160000 字符，规则行最多 16384 字符；未知或超限保持未识别，不成为新的业务准入限制。
- 校验原生文本块、一个 transcript 或前置上下文加 transcript 两种消息布局、temperature=1、非流式且不声明工具。第一阶段包含唯一 </block> stop，第二阶段没有 stop；不能只凭 max_tokens、模型、billing 三位后缀或关键词识别。输出和思考预算不改变用途，参数原值保持。
- 标题核对完整 CLI 身份及标题 system 摘要、唯一用户文本块中的 session 包装和完整收尾；不声明工具。身份最多 512、system 最多 160000 个 string.length 单位。默认语言收尾完整核验；显式 language 只规范化官方语言插槽，插槽 1–512 单位，其余收尾保持完整摘要匹配。
- 压缩只核对末条 user 的字符串或末尾 text 块，指令最多 160000 个 string.length 单位；固定收尾和完整提示词摘要同时匹配。仅在官方 Additional Instructions 插槽有非空附加要求时规范化该段，手动和自动压缩共用同一 profile；此前历史及整个大正文不套用此指令长度上限，不扫描旧指令给后续请求贴标签。
- 已识别用途依上表生成类别及官方来源，证据随当前上下文持久化。显式类别冲突返回 context_conflict/400，不静默覆盖。普通 auxiliary 继续使用原有 side_query；压缩保留主/子身份、session、agent、parent、类型和 workflow 关联。
- 原始正文、缓存、工具、输出和思考预算保持原值；profile 不以预算、模型名或短关键词认定。私有作业要求 input 与 context 接入类型一致为 claude_code；日志中的用途、profile、requestClass 和 querySource 组合必须一致。
- 未验证变体保持原分类并明确未识别特殊用途；不为取得识别标记改正文、增加调用或切换模型。旧日志不回填。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 固定 XML 第一/第二阶段完整证据符合 | auxiliary / auto_mode，保存对应 profile |
| deny rules 合法变化 | 规范化列表后核对完整静态摘要 |
| 默认或显式语言的完整标题构造 | auxiliary / generate_session_title，保存标题 profile |
| 字符串或末尾文本块承载完整压缩指令 | compaction / compact，保留代理身份及关联 |
| 合法附加压缩要求 | 只在核验时规范化对应插槽，出站原文保持 |
| 历史中有压缩指令，当前末条为普通业务 | 不继承压缩用途 |
| 普通关键词、局部特征、损坏静态正文或未验证布局 | 未识别，仍按既有入口规则转发 |
| 已识别用途与显式类别冲突 | context_conflict/400，模型零发送 |
| HTTP 注入内部 classification | 不支持字段/422 |
| 私有分类标签与接入类型、类别或 querySource 不符 | runtime_protocol/502 |

### 5. Scenarios and Examples

- 正常：实际 CLI 发起 Agent 和 SubagentHandback，各自的分类请求被标为辅助；进入复核的第二阶段仍保持辅助用途。
- 正常：交互 CLI 自动生成标题时归入辅助；同一会话 /compact 和长上下文自动压缩均归入压缩，恢复后的普通请求不继续标压缩。
- 边界：没有用户附件时仅一个 transcript 消息；附带用户上下文时为两条消息。思考预算可以改变输出上限，不因此认作主对话。
- 边界：无工具模式把压缩指令直接放在 content 字符串，带工具模式放在末尾文本块；子代理发生压缩仍保持子代理身份和父代理声明。
- 错误用法：看见 max_tokens=64 或 </block> 就标分类，或固定一次完整提示词哈希忽略动态规则。正确做法：校验固定构造的完整证据，未知变体保留未识别。
- 错误用法：业务仅提到标题、总结或复制一段局部指令就被归类。正确做法：标题校验完整 system 和包装；压缩校验当前末尾完整静态指令与固定收尾。

### 6. Tests Required

- tests/local-pool/attribution.test.ts：实际 CLI 默认、deny rules、两阶段复核三组回环，auxiliary/auto_mode/profile、原文内存与 TLS SHA/CCH、工具报告真实送达及每入站单次发送。
- tests/local-pool/session-purpose.test.ts：实际默认/显式中文交互标题、会话恢复、手动和长上下文自动压缩；字符串布局、完整前后缀、预算独立性、显式类别冲突、压缩子身份保留、原始内存与 TLS SHA/CCH、日志解码及每入站单次发送。
- tests/unit/request-attribution.test.ts、tests/unit/log-api.test.ts：关键词/单字段反例、普通 auxiliary、HTTP 禁注入、日志和私有协议一致性；实际 CLI 验收只在合成凭据、独立 HOME 和无外网空间执行。
- tests/browser/logs.spec.ts：三个用途及固定来源标签正确，历史缺字段仍可读。双实际交互客户端各 3 个子代理的隔离验收另核对文本块布局、两个 session 的父子证据、恢复和两种压缩以及最终 SHA/CCH，不能用单次 HTTP 200 代替完整流程。

## Scenario: 调用方请求头精确白名单

### 1. Scope / Trigger

- 普通 API 与原生 Claude Code 共用 `prepareInput` 边界，清理代理、CDN、new-api 及客户端附加头。依据为 vm2api 的字段归属、固定 293 定义与本项目历史分阶段采样。
- 白名单约束调用方带入原生构造的字段。运行时自行生成的请求头、上游响应和测试池第二段转发分别遵守原合同。

### 2. Signatures

- `parseInput(raw: unknown, incomingHeaders: HeaderPair[] = [], nativeIngressPolicy: NativeIngressPolicy = 'strict'): BridgeInput`。
- `prepareInput(input: BridgeInput): PreparedInput`；`HeaderPair = [string, string]`，有序数组保留同名输入。
- `HeaderDecision` 为 `{ name: string; action: 'keep' | 'drop' | 'runtime' | 'context'; reason: string }`。
- `POST /v1/messages` 与 `POST /api/requests` 均经上述边界；显式信封 `headers` 替代 HTTP 头作为策略输入，原始 HTTP 入站独立采集。

### 3. Contracts

- 九个精确协议字段为 `accept`、`accept-language`、`cache-control`、`anthropic-version`、`anthropic-beta`、`anthropic-dangerous-direct-browser-access`、`x-claude-code-prev-tool-durations`、`x-claude-code-compaction`、`x-claude-code-context-compacted`。
- 六个上下文字段为 `x-claude-code-request-class`、`x-claude-code-session-id`、`x-claude-code-prompt-id`、`x-claude-code-agent-id`、`x-claude-code-parent-agent-id`、`x-claude-code-agent-type`，继续提取为同一来源上下文。查表只接受对象自身登记键，`constructor`、`__proto__` 等名字按未登记字段处理。
- 名称匹配忽略大小写。先验证全部格式并解析 Connection，再处理连接、凭据及运行时归属；其余未登记字段在重复检查前逐项 `drop`，固定原因为“调用方请求头未登记到协议白名单”。原始输入保持原表示。
- 仅 `accept`、`accept-language`、`cache-control`、`anthropic-beta` 沿已有规则接受有序多值。其他已登记单值重复明确失败。协议字段聚合完整调用方值后覆盖 SDK 同名默认值；版本及 beta 沿专用分支。
- `anthropic-version` 必须等于同次原生版本；普通 API beta 只能请求同次已生成能力，完整原生入站保留其原分支的 beta。三个可选工具耗时/压缩字段按完整单值透传。
- `anthropic-*`、`x-claude-code-*` 前缀不整体放行。新增调用方扩展须显式登记并提供版本依据与验证；请求不能指定白名单或旁路开关。
- 入站、`header_policy`、`cc_prepared`、`wire_final` 继续分阶段记录并脱敏，日志模式及历史 schema 保持原合同。
- TLS 测试夹具模式经私有 stdin/JSONL 的 `{type:'response_mode',port,mode}` 设置到唯一已启动上游并确认同字段，默认 `json`。每个请求开始时固定模式。测试头 `x-fixture-mode` 按未登记字段删除。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 合法未知头、代理/CDN 头及大小写重复项 | 全部逐项删除，记录固定原因 |
| 未登记头包含非法格式 | `invalid_header/400`，先校验再过滤 |
| 已登记单值字段重复 | `duplicate_header/400` |
| 已登记上下文与显式 context 冲突 | `context_conflict/400` |
| 已登记上下文为空或超长 | `invalid_context/400` |
| 普通 API 额外 beta 或版本不符 | `unsupported_parameter/422`，发送前拒绝 |
| Connection 声明某个已登记字段 | 按连接级原因删除 |

### 5. Scenarios and Examples

- 正常：`headers: [['Accept-Language','zh-CN'],['accept-language','en-US;q=0.8']]`，实收为 `zh-CN, en-US;q=0.8`，完整覆盖同名默认值。
- 边界：`X-Forwarded-For` 与 `x-forwarded-for` 同时输入，各有删除决定，业务继续发送一次。`constructor` 保持普通未知头语义。
- 错误用法：把历史响应中的 `x-new-api-version` 或任意 `x-claude-code-*` 当作调用方协议准入依据。正确做法：按来源阶段和固定版本定义登记精确字段。
- 错误用法：为测试响应模式在生产白名单登记 `x-fixture-mode`。正确做法：发送前通过夹具私有控制通道设置并确认模式。

### 6. Tests Required

- `tests/unit/header-policy.test.ts`：全部协议字段、大小写、多值顺序、未知及原型属性名、名单外重复、格式错误与名单内冲突。
- `tests/integration/control.test.ts`：HTTP/信封共享过滤，原始入站与删除原因可见，`cc_prepared` 排除未知字段，日志秘密继续脱敏。
- `tests/native/native.test.ts`：普通/原生输入的独立 TLS 实收排除代理/CDN/new-api/客户端字段，三个可选协议字段及多值保持，CCH、正文和单次发送正确。
- `tests/native/tls-verifier.test.ts`：夹具私有模式实际驱动错误、长流、取消、部分读取及重建；最终采集排除测试头，双实际 CLI 各三个子代理保持隔离。
- `bun run typecheck`、单元及控制集成须通过。`test:native`、`test:tls` 使用固定原版 293、合成凭据和无外网环境。

## Scenario: 独立二进制的原始输入消费者

### 1. Scope / Trigger

- cc2api 等外部消费者通过私有 JSONL 调用固定 293，请求构造及头部策略继续由本二进制所有。
- 实现依据：`src/shared/{contracts,protocol}.ts`、`src/runtime/293/worker.ts`；实际消费者入口为 `scripts/testing/cc2api-native.ts`。

### 2. Signatures

- `worker_ready` 可包含 `raw_input_protocol: 1`；旧握手省略该字段表示缺少原始输入能力。
- `request_input = {type:'request_input',schema_version:2,worker_id,request_id,input}`；`input` 为既有 schema 1 信封，包含 `schema_version,request_id,body,headers?,context?`。
- 准备成功后输出 `request_event(payload={type:'header_policy',attempt:1,decisions})`；decision 仅包含 `name,action,reason`，action 为 `keep|drop|runtime|context`。

### 3. Contracts

- 外层与信封的 request_id 必须一致；消费者先验证 PID、固定版本及能力，再提交一次原始作业。调用方不能指定可执行文件、HOME、授权来源或代理。
- worker 在本次作业内部执行 `parseInput`、`prepareInput` 和同一原生 job；保留普通 API/原生输入、白名单和每轮独立根的既有规则。header_policy 不携带头值，且属于准备阶段观察。
- 业务输入错误返回受控 error 和匹配 idle，模型零发送，后续合法作业可复用该进程。私有帧损坏、错归属、执行异常及取消沿退役规则处理；终态和 idle 收齐后才复用。
- 登记的 Linux x64 分发为 27387960 B，SHA256 `a6998db0128cb3d0a9862f3b72e9e359e434840c9be4d57b69d56092847fd800`；实际执行体为 112839864 B，SHA256 `ea2cc610928260ca76054fc1818c7c83bb95efe183b06ce98e3d6be7dc31b9b1`。来源仍为本文件固定官方摘要，新增身份须双次构建和实际兼容验证。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 缺少 raw_input_protocol 或能力值不符 | 消费者准备失败，不提交作业 |
| 外层与信封版本、request_id 或 worker_id 错误 | 私有协议拒绝，隔离对应进程 |
| 业务正文、头部或上下文校验失败 | 受控错误和 idle，模型零发送 |
| 合法原始输入 | header_policy 后进入原生准备、唯一发送与响应状态机 |

### 5. Scenarios and Examples

- 正常：schema 2 指令携带同 ID 的 schema 1 信封，二进制内部生成 SDK 请求；消费者只转交原始 JSON 与有序头。
- 边界：非法头输入失败后，在同一 worker 发送合法输入，后续 TLS 实收与 CCH 仍独立正确。
- 错误用法：把 worker_ready 缺省能力当作支持，或在 Rust 先做正文/CCH 改写。正确处理：校验能力并交给二进制唯一构造。

### 6. Tests Required

- `tests/unit/worker-protocol.test.ts`：原始信封归属、能力枚举与 header_policy 字段限制。
- `tests/native/native.test.ts`：固定原版和新精简二进制的错误后复用、实际头部策略、独立 TLS/CCH 与单次发送。
- `scripts/testing/{standalone-native.py,cc2api-native.ts}`：脱离源码和构建工具执行，实际 Rust 消费者覆盖 HTTP/SOCKS、3 普通/6 Haiku、凭据代次、取消及独立账号。

## Scenario: 固定 293 内核修订的签名分发

### 1. Scope / Trigger

- 为 V3 单账号在线升级生成受信附件，固定官方版本和来源。账号排空及 sender 轮换由 bench 的 account-runtime-v3 合同所有。

### 2. Signatures

- sealRuntimeRelease(release,binary,keyPath,output): Promise<RuntimeRelease>；CLI 为 bun scripts/seal-runtime-release.ts <发布标签> <分发文件> <Ed25519私钥文件> <新目录>。
- 输出 runtime-release.json、runtime-release.sig（64字节原始签名）、ccrb-runtime-linux-x64。

### 3. Contracts

- 只接受 v0.1.0-beta.N（正整数且至多9位）、Linux x64、官方2.1.293及当前来源SHA256，worker_schema=2、raw_input_protocol=1、resource_contract=1。
- 清单 schema_version=1，包含 release、platform、asset、source_version/source_sha256、launcher_sha256/launcher_bytes、image_sha256/image_bytes。分发不超过27933052字节，执行体不超过128MiB。
- 签名覆盖 UTF-8 JSON 与末尾换行的精确字节。私钥仅在发布端，部署信任根提前固定；未验证的外部构建清单不能直接获得受信身份。签署前必须完成最终产物的行为准入。
- 工具从分发文件旁读取构建清单，签名前与复制后均核对实际分发SHA；输出目录必须全新。异常清理本轮新目录。
- 配方10给外层加载器加ELF Build ID用于制品定位，实际内存执行体仍独立核验。每个新配方重复构建并比较分发/执行体摘要。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 来源、大小、摘要、标签或私钥类型不符 | 拒绝签署 |
| 输出目录已存在 | 拒绝覆盖 |
| 复制后摘要不符 | 清理新输出并失败 |
| 仅构建或签署成功 | 仍需最终产物行为准入 |

### 5. Scenarios and Examples

- 正常：两次独立构建摘要相同，对最终哈希完成原生及消费者离线验证后签署，部署预登记公钥。
- 边界：外层加载器不同、执行体相同，仍须实际运行每份候选加载器并核验真实进程。
- 错误用法：签署任意下载清单后直接上线。正确处理：先核来源、重建配方和行为证据，再由发布者批准对应实际SHA。

### 6. Tests Required

- tests/unit/runtime-release.test.ts：签名覆盖原始字节、字节改动使签名失效、分发文件被替换时拒绝。
- scripts/testing/cc2api-native.ts：签名候选的切换/回滚真实PID，零模型预热，HTTP/SOCKS TLS实收及私有协议保真。
- scripts/testing/standalone-native.py：新候选显式传入 expected-launcher/expected-executable，在无外网固定容器核验真实映像和有限资源。

## Scenario: 首响应预算归属与逐请求缓存TTL

### 1. Scope / Trigger
- 修改固定293的fetchOverride、Ree发送信号、缓存TTL及常驻私有指令时适用。官方来源版本与摘要保持固定。

### 2. Signatures
- `runNativeJob(..., cachePolicy:CachePolicy='preserve', cacheTtlRewrite:CacheTtlRewrite='off')`。
- `CacheTtlRewrite='off'|'5m'|'1h'`；`readCacheTtlRewrite(value:unknown)`校验私有值；`rewriteCacheTtl(body:JsonObject,mode:CacheTtlRewrite):JsonObject`。
- `request_input.cache_ttl_rewrite?`为受信指令同级字段；`worker_ready.cache_ttl_rewrite_protocol?:1`声明能力。业务信封与body/context不能设置该私有字段。

### 3. Contracts
- 官方SDK的首响应计时器等待fetchOverride返回。桥接send回调独占响应并等待整条流释放，SDK内部signal不能直接作为实际Ree的取消信号，否则持续有数据的流也会在180秒加上传余量后误断。
- 实际发送使用`AbortSignal.any([signal,dispatch.signal])`，分别承接调用方取消和本地发送/快照失败清理。前置服务继续拥有首响应及流静默预算；不以扩大固定总时限掩盖阶段归属错误。
- TTL在原生构造与既有缓存选点之后、cc_prepared/Ree之前应用。只覆盖根、system数组项、tools数组项和messages顶层content数组块内已有`type=ephemeral`的cache_control。工具schema、tool_use.input及嵌套tool_result业务内容保持。
- off返回原对象；5m/1h复制正文并覆盖已有标记的ttl，断点位置保持。非法私有值按runtime_protocol/502拒绝；旧握手省略能力仍可解码。消费者对强制模式要求能力1，省略能力时不能静默忽略。
- cc_prepared仍是中间值。最终CCH由原生传输根据TTL改写后的正文封口；模型只发送一次。新候选须固定真实SHA并完成重建与行为验证。

### 4. Validation & Error Matrix
| 条件 | 结果 |
| --- | --- |
| 持续有数据跨181秒 | 正常读取到真实终态 |
| 调用方取消、快照写出或实际发送失败 | 取消本次实际网络活动并收口 |
| off/5m/1h同PID切换 | 仅按本次受信模式处理 |
| null、布尔、未知TTL或能力值 | 私有协议拒绝 |

### 5. Scenarios and Examples
- 正常：cc2api强制1h，worker收到同级策略，组装快照与回环实收已有断点均为1h。
- 基础：off保留调用方TTL及官方默认，旧消费者继续使用既有指令。
- 错误用法：把SDK的首响应signal绑定到独占读取的整流，或递归改写工具业务JSON。正确处理：按阶段管理取消，按协议精确路径覆盖TTL。

### 6. Tests Required
- `scripts/testing/native-stream-budget.ts`：校验实际二进制SHA，在隔离回环对照旧版181秒误断与新候选185秒完整流；主动取消和每条唯一提交。
- `tests/unit/{cache-policy,worker-protocol}.test.ts`：off对象保持、5m/1h切换、嵌套业务保持及非法私有值拒绝。
- `tests/native/native.test.ts`：同PID三个模式，cc_prepared与TLS实收仅规范已知CCH占位后相等；另独立核验最终CCH。

## Scenario: 原生进程池 CRIU 热模板恢复协议 1

### 1. Scope / Trigger

- gateway NativePool 扩容、runtime 恢复绑定、受信任恢复控制器、TLS 归属与部署配置共同遵守本合同。一个物理 worker 继续串行执行作业，业务构造与发送沿原生栈。

### 2. Signatures

- `worker_restore_bind` 使用 schema_version=2，字段固定为 `type/worker_id/template_id/new_worker_id/nonce`；模板与新 worker 为规范 UUID，新旧 worker 必须不同，nonce 为64位小写十六进制。拒绝额外字段。
- `worker_ready` 可选 `restore_protocol:1`；模板态带 `restore_template:UUID`，绑定态带 `restore_binding:{template_id,nonce,entropy_profile:'bun143-wipeonfork-v1'}`，两者互斥。旧 ready 继续兼容。
- Linux x64 的 `native_criu::Template::register(key,id,worker,pid,image)` 登记模板；`Process::start(template,key,worker,nonce)` 接管私有管道和 pidfd，`Process::retire()` 等待实际命名空间退出。
- 控制器固定 socket `/run/ccrb-criu/control.sock`。`template` 命令仅含 `type/key/template/worker/pid`，`restore` 仅含 `type/key/template/worker/nonce`；key 为64位小写十六进制。控制帧最多4096字节。

### 3. Contracts

- `V3_NATIVE_CRIU` 默认0，部署只接受空值、0或1。显式1与账号镜像标签 `vibebench.native-criu=1` 共同选择 `/opt/ccrb-criu/entry.py`。入口将实际恢复可用性通过 `CCRB_CRIU=1|0` 交给 sender。协议1内核沿原签名发行及激活合同使用。
- 模板 key 复用完整池身份，覆盖 bearer、账号/设备/组织、环境与内核代次、代理及有效启动配置。后台种子服从同一物理容量；先完成零模型 bootstrap，再 dump/leave-running。种子绑定为普通暖进程后继续归池。模板只接纳尚未执行业务的受控种子。
- 普通 exec 的共享 memfd dev/inode 与四项封存校验保持原合同。CRIU 会重建 memfd，恢复分支独立校验实际外部 PID 的执行体 SHA、大小、四项 seals、新 ready、模板及随机挑战。每个恢复副本的独立代码映像额外按向上取整 MiB 预算；当前画像为108MiB。有限 sender 最低 RAM 为 `256 + max_workers × (192 + 108)` MiB。
- 固定配方为 CRIU4.2 加 memfd 执行体修补，记录来源归档/补丁/二进制 SHA、编译器、功能配置与许可；按目标 ABI 构建。源码束与生成镜像输入逐文件核对。TLS束继续使用既有正式来源导出检查。
- 控制器必须持有权威 sender PID；对端必须是该 sender 自身、UID1001。种子为其直属受限子进程，模板标记、worker ID、HOME/config/cwd及执行体须匹配。IPC禁止指定任意程序、路径与其他进程。控制目录0750、socket0660；模板磁盘根目录0700，快照0600。
- 控制器权限集合为 `CHOWN DAC_OVERRIDE FOWNER KILL SETUID SETGID SETPCAP NET_ADMIN SYS_CHROOT SYS_PTRACE SYS_ADMIN SYS_RESOURCE SYS_TIME`，有效掩码032c11eb、NNP1、seccomp0。固定C入口安装冻结业务BPF并降权；sender和worker为UID1001、capability0、NNP1、seccomp2。入口先核验降权入口/BPF，失败终止启动；恢复环境预检失败使用受限正常exec。
- 每个实例独立PID/挂载命名空间、HOME/config/cwd副本及管道。冻结文件拒绝链接、设备、外来归属和超预算；恢复前核对完整条目集合及包含ctime的文件身份。文件原权限/时间在独立映射中重建，原快照保持私有。
- 固定 Bun1.4.3/revision `eecfd55debb281c3fe3518098b1a49f76429637c`。恢复进程全线程暂停时，控制器核验执行体、线程组及唯一WIPEONFORK页，只清零原生fork标志4字节；绑定时耗尽2048字节UUID缓存，并使用系统熵重新播种主执行域。执行域或熵画像不匹配拒绝恢复。
- SCM_RIGHTS先交接命名空间pidfd，sender保存后ACK；之后才恢复业务worker并交接stdin/stdout及实际worker pidfd。取消或连接关闭触发实例退出。WorkerLease、代理引用及目录清理所有权保留至实际退出；清理中的finally避免二次取消。
- 模板持有同账号稳定代理引用。身份/内核切换、维护排空和关闭撤销模板，已受理实例沿原生命周期收口。恢复失败在业务投递前清理并回退正常exec，复用原单调截止。已提交业务继续遵守唯一发送合同。
- TLS broker为恢复实例登记外部PID、父进程、启动时刻、worker及映像；探针使用目标活动PID命名空间和内部PID，最终证据保存外部物理PID。实际TLS正文/头与独立接收端比对；cc_prepared保持其组装阶段含义。
- `criu_template/criu_restore`安全日志记录来源、实例及dump/交接/映像核验/绑定/TLS准备时间，CRIU命令与熵核验时间在私有日志单列。IPC EOF的`worker_pid`来自实际承载进程；普通Child与恢复pidfd分别判断`process_exited`，恢复退出码缺省为空。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 旧内核缺恢复能力、无可用模板或权限预检失败 | 正常共享映像exec，保留原业务截止与唯一发送 |
| 对端/PID/模板身份错误、额外控制字段、快照污染或租约过期 | 业务前拒绝，日志只输出受控原因 |
| 熵画像、映像、封存或新绑定不匹配 | 清理恢复实例后按原截止回退；失败模板停止准入并退避 |
| ACK前后取消、控制器退出、管道断开 | 通过真实pidfd等待收口，实际退出后释放许可；新入口清理私有遗留 |
| IPC已EOF且worker仍存活 / pidfd已退出 | 分别记录process_exited=false / true，保持实际外部PID |

### 5. Scenarios and Examples

- 正常：同账号模板已就绪，需要第三个worker时恢复独立实例，经新UUID/nonce绑定、执行体核验与TLS准备后接单。
- 边界：关闭部署开关或使用旧协议内核时继续现有正常启动。普通Child与恢复worker共同服从账号物理上限。
- 错误用法：直接复用快照中的worker_id、旧ready或探针PID，或把CRIU命令时间当作完整准备时间。正确处理：独立绑定与真实执行体/TLS准入，性能从checkout计到可接单，首次建模板单列。

### 6. Tests Required

- `tests/unit/worker-protocol.test.ts`：版本、新旧UUID、随机挑战、额外字段、互斥模板/绑定及旧ready兼容。
- `native/criu/test_{entropy,protocol,entry}.py`：全线程暂停与熵画像、冻结目录权限/链接/预算、入口降权准入及umask下socket权限。
- gateway `native_criu` 定向测试：SCM_RIGHTS数量/截断/CLOEXEC、真实pidfd归属、取消时许可保留、EOF前后真实退出日志。普通Child错误/EOF/截止日志继续回归。
- 隔离验收：同源存活时串行3/并发4副本，独立会话和两模型、每笔一次模拟POST，最终TLS与独立接收端匹配；控制器强退/重启、污染/过期模板与完整submit回退；至少20轮完整准备配对，p50降低至少50%。
- 目标ABI实际构建并核验包文件SHA；运行环境失败的受限exec回退；编排预算、部署开关/角色权限与受影响回归通过。生产启用沿独立上线授权验收。
