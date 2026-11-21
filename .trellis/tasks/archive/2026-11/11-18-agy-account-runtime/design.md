# AGY运行环境与Gemini API接入设计

## 1. 归属、现有定义与兼容

本任务在现有账号、调度、运行环境和account-sender中增加AGY平台适配。源码核对及私有研究原型身份见research/current-contracts.md与prototype-source-identity.json。下文标为新增的路径、类型与方法属于设计目标，实现前继续核对相邻实际定义。

现有OAuthCredentialSnapshot只有account_id/access_token/refresh_token/expires_at。NativeSubmission与NativeSenderConfig专属CC 280/293。TransportBinding已经保存account_id/environment_id/generation/endpoint/secret/release_id，SenderConfig保存native/binding/proxy_url/allowed_origin等。ApiToken沿allowed_accounts/blocked_accounts/status执行授权。AGY不能以伪造CC UUID、版本或将同名model当平台的方式复用这些专属合同。

## 2. 公共Gemini接口与选择

拟新增GET /v1beta/models、POST /v1beta/models/:model:generateContent、POST /v1beta/models/:model:streamGenerateContent?alt=sse。Axum实现按实际path捕获规则解析末尾action。模型列表返回经当前令牌可用AGY账号观测的实际模型能力，不把全量catalog当作账号已授权能力。

入口复用现有令牌存储及账号权限；Gemini入口扩展x-goog-api-key与query key兼容，已有x-api-key/Bearer保持可用。多个来源携带不同key时拒绝歧义。查询密钥在日志、请求详情及错误中统一脱敏，权限、活动状态和管理密码边界按现有API合同执行。

新增Gemini handler/服务模块，由现有Router显式分派。新增AGY账号选择分支复用现有队列、RPM、并发许可、取消及维护生命周期；旧CC选择方法及messages行为保持。候选须为antigravity、active、凭据ready、符合令牌账号白/黑名单且确有该模型映射。空候选及未就绪返回有界错误。AGY账号的Claude/Gemini模型均进入AGY内核。

请求模型名通过已认证状态/原生目录的完整模型配置映射到原生执行ID，不能硬编码原型M36或按名称猜测。现有models名称列表不足时，扩展受信能力观测保存对应ID和来源，保持旧能力字段可读。

## 3. Gemini输入、参数与响应

- 接入contents、systemInstruction、文本、历史、函数声明、functionCall/functionResponse、原生签名、maxOutputTokens及有证据的工具模式。未知扩展能力逐项核验，不能仅接受JSON便声称真实生效。
- temperature、topP为显式兼容例外：接收后忽略，使用原生默认值，记录policy=native_default与字段名；该诊断留在已有技术记录，不增加用户弹窗或错误。maxOutputTokens使用已验证映射。
- Gemini原始响应帧为业务数据来源，保留候选、思考/签名、usageMetadata、finishReason、安全反馈及未知响应扩展。原型的派生视图与原始帧区分来源。
- streamGenerateContent输出Gemini SSE data事件，遵循原始JSON逻辑帧及标准结束语义；一次原生调用的预算、取消和背压贯穿HTTP正文生命周期。不能伪造[DONE]、STOP、成功usage或上游HTTP状态。
- generateContent在同一内部生成路径上按明确规则聚合文本/函数调用和最终usage，签名、候选顺序及错误保持。错误发生在HTTP发送前返回Gemini结构错误；开始发送后以已验证流错误/关闭规则收尾，保留失败终态，不追加成功结果。
- 内核每次实际模型尝试禁用隐式API和输出重试；安全拦截、MAX_TOKENS、容量错误按实际终态处理。只有第6节认证恢复可额外提交一次。

## 4. 现有账号发送器与原生适配

拟在services/gateway/src/service增加agy_contract、agy_runtime及Gemini服务模块，在现有runtime_transport::sender_router增加受信AGY准备/状态/执行/取消路径。复用TransportBinding的账号、环境、部署代次、release、secret、deadline校验，AGY的model与私有材料使用独立DTO。SenderConfig拟增加可选AGY配置和平台信息，省略沿CC；现有NativeSourceVersion保持280/293。

AGY执行源码拟归入services/orchestrator/agy_runtime/，导入经过身份冻结和裁剪的研究原型。account-sender监督受控Python适配进程，通过版本化NDJSON交付命令及事件。正式路径仅接收管理侧生成的AT-only OAuth HOME，移除原型GEMINI_API_KEY及测试CA的正式依赖；测试CA只在现有隔离verification镜像路径可用。

拟新增私有AGY提交实体绑定account_id、environment_id、environment_generation、credential_generation、worker_id/request_id/attempt_id、调用方token ID、模型与原单调预算。AT仅在受鉴权私有边界交付，不派生Debug。worker_ready必须核对固定执行体、原生PID套接字、CSRF能力响应、模型能力、版本、平台与当前身份。

固定原版继续1.5.9。构建将适配源码、观察器源码及资源登记为可复现输入，完整原版沿已有私有staging输入。分发摘要与完整ELF身份分别登记。新的AGY适配制品身份进入账号组件内容身份与部署标签，旧无AGY声明保持未就绪。正式镜像不依赖/root/.local/state路径，不提交原版二进制。

## 5. 环境与资源

在AccountRuntime现有API传输、环境列表、启动/停止和维护入口按平台增加AGY分派，复用既有代理、network/sender隔离、私有原子文件、环境ID和部署标签。AGY API环境以gateway账号ID为权威归属，通过平台参数或严格命名空间关联现有环境记录，避免伪造bench工程账号。新增持久字段或表使用追加迁移和台账，旧CC记录/绑定/画像及冻结步骤保持。

AGY不创建工程/养号执行流程。已有CC CLI角色和管理操作保持；AGY仅暴露与实际API能力匹配的现有环境控件。

同版本完整执行映像用封存memfd和只读FD共享，先核对SHA、大小、四封存和执行体身份。共享对象只承载不可变代码，账号HOME、AT、工作目录及会话各自私有。镜像池失效、FD身份错误或观察能力缺失时拒绝新准备。

显式资源布局先通过零模型启动/回环压测确定AGY控制、共享映像、每worker及网络分项，再映射现有持久资源策略。并发上限、硬RAM/swap/CPU限制和空闲回收均有明确值；分发体积不冒充RSS节省，不能直接照抄CC的worker常量或隐式扩大现有账号限额。

## 6. 凭据发布与进程代次

新增AT-only运行快照，包含账号、credential_generation、AT、expires_at和已核验身份元数据。通过AccountService现有刷新锁及resolve_agy_credentials的锁内实现生成，同次重读ready状态与权威凭据；保持旧OAuthCredentialSnapshot和旧响应字段兼容，不在已有锁内再次调用获取相同锁的公开resolve方法。

worker身份至少包括平台、账号、环境代次、凭据代次、原版/适配身份、代理指纹和冻结资源策略。同账号发布新代时，关闭旧代普通准入，新请求从新worker开始；旧在途worker按原请求归属收尾。pending/reconcile阻止新的普通凭据发布，旧工具收尾只使用原有许可和执行归属。

认证恢复须有已验证的原生认证错误分类、同账号ready且不同的新AT、原截止仍有效、响应尚未发送、无工具副作用且尚未重试。满足条件时最多增加一次实际模型提交，并登记oauth_recovery。分类不明、429/5xx/容量错误不得冒充认证失败，不触发第二个RT刷新所有者。

## 7. 工具跨HTTP续轮、取消与排空

HTTP工具响应完成与原生工具轮完成分开。保留原worker、conversation/trajectory、toolCall、原始历史前缀、调用方token ID和账号许可。续轮先按调用方权限、原历史前缀及真实函数身份匹配已有等待项；缺失ID时只有名称/参数/历史唯一匹配才允许，多个匹配拒绝猜测。重复、错调用方、错账号或过期结果拒绝。

续轮复用原持有许可，避免concurrency=1时再次排队导致死锁。先将真实工具结果投递原worker，并等待原工具轮及hooks完成；随后核对当前凭据代次，下一次模型生成采用当前合法worker。不会在工具结果确认前把旧调用迁移到新进程，也不因凭据换代重放工具效果。

等待有界且延续原冻结截止；取消和超时先关闭续轮准入，再精确取消原作业。优雅停止观察实际业务队列、遥测、输入关闭、原生退出及必要强制回收。异常或重启后不能恢复的工具轮记录可查询的失效终态，旧结果不能接到新代。

## 8. UI、诊断与任务交接

环境页沿用现有字段和组件，增加平台、固定内核版本、就绪/等待工具/退役状态及真实资源来源。读取不初始化或刷新账号。轮询保持草稿与焦点，动作及回执核对账号/环境代次，390px及桌面验证。

请求事件最少保存平台、账号、内核来源、环境、worker、凭据代次、HTTP请求、attempt、conversation/toolCall、模型、实际模型入口数及终态。该任务交付事件生产和基础诊断，统一请求记录页面由后续任务实现。完整头体仍遵循账号采集开关和管理员权限。

## 9. 验证、交付与回退

工程验证使用合成凭据、临时SQLite/PG、真实子进程、回环TLS上游和固定执行体；覆盖Gemini内容保真、参数兼容、权限、并发、背压、取消、工具接续、凭据换代与资源。原生Google身份、模型接受性及跨真实到期场景独立记为外部验证，维持本轮真实模型预算0，用户无需作为本轮人工验收前置。

回退先停止新准入，收口在途与工具等待，再切换已验证的兼容镜像。保留当前权威AT/RT和账号身份，禁止回填旧凭据快照。新增AGY记录对不识别平台/布局的旧control保持受控阻止。生产迁移及部署单独授权。

## 10. 实现收敛的合同细节

- 环境归属使用追加迁移bench.agy-environments.2的platform_api_environments。account_environments继续保存原角色生命周期；AGY行的account_id为空，名称采用工程账号禁止的冒号命名空间，网关账号ID由独立唯一映射保存。database_schema.py及历史迁移摘要保持冻结。宿主身份摘要包含实际非空平台映射，存在AGY环境时目标control/account都必须声明agy-runtime-protocol=1。
- 复用三角色时AGY的CLI角色保持基础隔离支撑，工程和养号入口继续只消费原账号。AGY物理worker上限直接等于账号concurrency，覆盖同账号全部模型和凭据代次。有限sender预算为512+256×worker数MiB，另外保持原network 256MiB及CLI至少512MiB。零沿既有无限策略，实际cgroup v1/v2上限须与冻结配置一致；未知读取保持拒绝。默认CPU继续采用现有独立角色策略。
- 封存完整映像按账号内worker共享，计入image_scope=account_workers。完整ELF大小265700040字节独立于RSS/PSS/USS及实际cgroup current/peak；控制、内核、观察器和原生进程分开观测。暖worker闲置300秒回收，原工具等待继续受原请求截止约束。
- 新普通发布在监督器核对单调凭据代次；同代不同AT和迟到旧代在模型发送前拒绝。私有/tools控制不携带AT，先按原调用方、历史、原函数身份回填原worker并确认真实收口。管理状态pending/reconcile时这一步仍沿原许可完成。下一次模型生成单独读取ready快照；失败期间保留同一结果的有限幂等回执和原许可，恢复后继续原截止，回填副作用只发生一次。
- Gemini源帧中code=401且status=UNAUTHENTICATED、没有候选及usage时才属于可验证认证失败。源帧未交付、无工具结果历史、同账号不同有效新代且原作业已物理收口时最多一次oauth_recovery。控制RPC失败、429及SSE首帧后错误保持独立失败。
- Rust唯一监督器读取器有64MiB帧上限及合计64MiB待交付字节许可。慢调用方单独取消。Python事件队列和匿名暂存分别有字节上限，匿名临时输出使用账号私有工作卷。采集默认值复用native_capture_policy，开启时原始记录位于flows/api/agy-prepared；退役删除AT HOME，已退役采集按七天清理。
- 监督器异常后原worker通过父进程监测退出，观察器及Go进程由PDEATHSIG链收口。未确认正常退出的监督目录阻止新准备，显式环境重建/对账在三角色实际停止后清理派生worker和AT副本。正常关闭在最终作业事件入队之后写stopped回执。
- 正式OAuth观察器绑定codeassist Scanner和channelModelResponseStream，原始Scanner块归档后解开response信封。真实EOF与控制RPC独立于源finishReason/安全拦截终态；截断流保持失败。worker的冻结PYTHONPATH同时包含适配根和/usr/local/bin，与正式共享文件助手布局一致。
- 对外仍保持Gemini协议。私有NDJSON生产完整环境、worker、凭据代次、HTTP请求、attempt、conversation/trajectory/toolCall及实际模型入口数。网关基础日志只投影这些身份及终态，不投影头体、AT、RT或函数参数。统一请求页面继续由独立任务消费。
