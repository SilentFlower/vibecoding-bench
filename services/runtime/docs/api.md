# 接口合同与配置

## 请求入口

POST /v1/messages 接收 JSON Messages 正文。POST /api/requests 还支持下列信封；两者使用相同的校验和执行链路：

    {
      "schema_version": 1,
      "request_id": "request-001",
      "body": {
        "model": "claude-sonnet-4-6",
        "max_tokens": 128,
        "stream": true,
        "messages": [{"role": "user", "content": "查询状态"}]
      },
      "headers": [["accept-language", "zh-CN"]],
      "context": {
        "requestClass": "subagent",
        "sessionId": "11111111-1111-4111-8111-111111111111",
        "promptId": "22222222-2222-4222-8222-222222222222",
        "agentId": "child-001",
        "parentAgentId": "root-001",
        "agentType": "Explore"
      }
    }

request_id 可省略，使用 1–128 位字母、数字、连字符、下划线。重复标识返回 409，不覆盖旧日志。schema_version 只支持 1。HTTP 入口接收未压缩 JSON，不另设 2 MiB 或排队 16 项的业务门槛；正文大小、准入和调用预算交给前置服务。日志预览上限独立于完整转发。

信封 headers 是有序二元字符串数组，提供后替代外层 HTTP 头作为业务转发输入；日志仍会保存实际入站 HTTP 头。没有信封 headers 时使用 HTTP 头。两类输入共用精确协议白名单，名单外的代理、CDN、客户端私有及未知协议头逐项删除并记录原因。鉴权、传输字段、Connection 动态字段及原生上下文按 [头部策略](header-policy.md) 处理。

两种入口均在解析正文时删除顶层 `settings`、`claude_settings`、`env`，随后继续校验和处理。它们的值不参与运行时配置；账号、凭据、代理及工作目录由服务端启动配置管理。清理只作用于正文根字段，工具 schema、工具调用参数及其他嵌套业务数据中的同名字段保持。入站日志仍保存原始请求表示，并按日志策略脱敏。

## 原生 CC 正文

两种入口均按正文证据区分原生 CC 与普通 API。原生请求需要根 system 数组首段包含唯一独立 billing 文本块，`cc_version=2.1.293.<三位十六进制后缀>`、`cc_entrypoint=cli`、有效 CCH，以及合法的 `metadata.user_id` JSON 字符串。设备 ID 为 64 位十六进制，账号 UUID 可为空，会话 ID 必须为 UUID；可选 prompt ID、轮次及子代理标识同时校验。损坏或不支持的原生证据返回 422，不回落到普通 API 重组。

默认缓存策略下，原生分支保留业务 system、messages、tools、tool_choice、thinking、output_config、缓存标记及位置，以及 thread、diagnostics、fallbacks、safeguards 和扩展 JSON。消息可包含原生 system 角色及扩展字段。省略字段保持省略；工具为空或省略均不补工具，也不添加 CLI 提醒或默认正文。显式启用 sub2api 时按下述规则处理消息断点。

默认 preserve 下的必要改写仅包括：metadata.user_id 的 device_id/account_uuid 使用当前专用运行时身份，session_id 与其他 metadata 保留；billing CCH 先置为原生占位，再由同一原生传输生成最终值。原版本后缀、prompt、轮次及父子标识保留，显式上下文或头部冲突返回 400。入站 beta 在原生分支保留，凭据与传输头仍遵循既有头部策略。

扩展 JSON 只作为上游数据。三个顶层本机设置字段按入口规则删除；根字段 extra_headers、extra_body、headers、proxy_url、api_key、oauth_token、claude_binary、claude_home、claude_config_dir、workdir 继续返回 422。调用方不能通过正文改变账号、代理、工作目录或执行程序。原生识别不代表上游已接受扩展字段或模型参数组合。

### 本地 Base URL 联调模式

显式 `bun run start:pool` 启动的实例允许固定 293 的 `cli` 和 `sdk-cli` 入站，billing 可以省略 CCH；存在时仍须唯一且有效。该策略只来自启动配置，不能用 HTTP 正文、信封或头部打开。普通启动继续使用上述严格合同。

兼容分支保留原始入站表示及业务正文，发送入口取同次 SDK 实际生成的 CLI 上下文，缺失 CCH 先准备原生占位，再由原生传输完成。该模式使用已校验原版及当前预加载入口，现有内嵌旧桥接代码的轻量产物暂不接纳。

TLS 接收端实收并独立核验后，第二段仅将根 model 映射为 deepseek-flash，重建鉴权及必要传输字段；凭据不进入原生进程。手工 CLI 默认不限次数、不附加请求总超时，模型参数原样交池判断。入口只校验组装必需的结构，不再校验输出范围、温度范围、thinking 枚举/最小预算或工具组合。有限测试实例仍在额度耗尽时返回本地 429，不伪造成池响应；自动验收保留显式测试预算。每个入站最多一次转发，客户端重发作为新请求计数。

原生分支的 SDK 种子只取得发送上下文，其消息及提醒会被真实原生正文替换，不套用普通 API 的业务消息保留断言。两条路径继续核对实际发送结构、请求归属和单次发送。

`/api/health.localPool` 返回 runId、model、live、budget、reserved、remaining；不限次数时 budget/remaining 为 null，reserved 持续记录发送前预留数，异常时为可能实际调用次数的上界。只有配置了已自检 TLS 采集端的实例才报告 nativeFinalCapture=true。启动、自检及只读访问均不推理；操作和临时客户端配置见 [README](../README.md#用自己的-claude-code-联调)。

## 普通 API 正文能力

| 字段 | 首版行为 |
| --- | --- |
| model | 必填；由实际官方构造器处理 |
| messages | 必填；user / assistant，文本或内容块数组 |
| system | 省略使用 CLI 默认正文；显式文本或仅含 type/text 的文本块完整替换正文，对应 --system-prompt；空文本与空数组同样是替换 |
| tools | 省略或 [] 均无工具；非空数组为完整列表，不加入 CC 内置、延迟或搜索工具；schema 经原生 extraToolSchemas 输入 |
| tool_choice | 交给实际原生构造，不在入口根据工具列表或 thinking 组合提前拒绝 |
| max_tokens、temperature | 映射原生输出预算和温度参数，只检查有限数值结构，不自设模型能力范围 |
| thinking | 交给实际原生构造；完整对象恰为 {"type":"disabled"} 且被原生省略时补齐原值，再做保留检查；不在入口添加枚举或最小预算政策 |
| output_config | effort、format；模型或原生能力不能表达时返回 422 |
| stream | true 返回原始 SSE；false 或省略返回原始 JSON |

工具调用、工具结果、thinking 及签名等历史通过内部消息实体输入。发送前对显式字段做保留检查；文本字符串与等价文本块按相同语义比较，原生添加的缓存等字段允许保留。业务内容、角色或内容块顺序无法保留时明确拒绝，不宣称完整兼容任意 Messages 历史。

普通主请求使用固定 293 交互终端 CLI 的原生身份、提示词、权限、环境和技能等提醒，工具仅来自调用方显式列表；默认正文及提醒根据实际工具集生成。业务 system 替换默认正文，身份及 billing 仍由原生链路装配。原生补充消息逐项关联，不能以忽略全部 system-reminder 代替业务保留校验。自定义工具 schema 是桥接的结构化接口能力，不表示终端 --tools 接受任意 schema。

普通 API 的显式 system cache_control、top_p、metadata、stop_sequences 和未登记正文/消息字段当前不支持，返回明确错误。未知 JSON 字段采用拒绝策略；未登记请求头采用删除并记录原因的白名单策略。完整原生 billing 由上一节的独立分支处理。

省略模型可选参数时，采用 CLI 根据当前模型与配置计算的 thinking、effort 和输出预算；不再固定关闭 thinking。普通 API 的显式 {"type":"disabled"} 被原生省略时由桥接补齐，额外字段及原生已有不同值不能套用这项适配。显式 enabled thinking 若被模型原生规则转换成 adaptive，也会因无法原样表达而返回 422。完整原生 CC 正文仍保持原值；最终发送该字段不保证自定义池遵守关闭，响应原样返回。

模型参数的业务规则由前置服务与上游判断。普通 API 仍检查实际组装所需结构与显式字段保留；原生构造无法保留时明确失败，不能静默丢字段。原生正文则直接保留参数，不让上下文种子的默认模型判断覆盖原始请求。原生构造错误和模型失败事件直接收口，不隐式切换模型或重试。

## 上下文

支持 main、subagent、workflow、compaction、auxiliary、side_reply。requestClass 可由 context 或相应 x-claude-code-* 头提供，两处冲突时拒绝。

- 无分类或 agent 身份时生成普通主上下文，querySource=repl_main_thread，source 标明 bridge-default；普通用户输入采用 human 来源，纯工具结果不伪装为新的人类输入。
- 显式 agentKind=main 可提供 root agentId；单独提供 agentId 默认按子代理处理。
- 子代理需要 agentId，workflow 还需要 workflowRunId；父 agent、agent 类型、session 和 prompt 一起传给原生链路。
- agentKind 支持 main、subagent、teammate；类别与身份冲突返回错误。
- 压缩可以保留主代理或子代理身份，不能只改变 request-class 头。
- 普通 API 的 sessionId、promptId 未提供时生成；原生分支优先使用 metadata 会话及可选 billing prompt，缺少 prompt 时生成。promptId 必须为 UUID。
- 普通 API 的有效 promptId 绑定历史中最近一条不含 tool_result 的 user 轮次，工具结果仍保持续轮语义；调用方可显式复用该 ID 关联同一次工具往返。没有可归属用户轮次的历史返回 422，发送前拒绝；sessionId 不代替 promptId。

账号工作进程惰性启动、串行常驻，每轮建立独立原生会话根并以 session transition 恢复指定会话身份。正常完成后复用进程，取消或异常后隔离重建；不重放当前请求。它保留请求关联，不在本地维护可执行的用户代理循环。原版和精简版的构建与身份合同见 [运行时说明](runtime.md)。

子代理指定已加载的原生 agentType 且省略 system 时，使用其官方定义；未知类型需提供业务 system。未提供 agentType 时保留调用方上下文，使用通用 CLI 正文，不猜测自定义代理定义。workflow、compaction、auxiliary、side_reply 保留原生类别和父子关联；该分类不会自动创建终端中的工作流、压缩任务、标题或其它辅助推理。输出风格产生无法与已解析主来源一致的配置时，在发送前拒绝。

### 原生用途识别与日志关联

固定 293 原生请求通过完整构造证据识别用途，`context.classification` 可选，`source` 固定为 `native_profile`：

| purpose | profile | requestClass | querySource |
| --- | --- | --- | --- |
| auto_permission_classifier | cc293-auto-mode-xml-s1 / cc293-auto-mode-xml-s2 | auxiliary | auto_mode |
| session_title | cc293-session-title-v1 | auxiliary | generate_session_title |
| compaction | cc293-compact-full-v1 | compaction | compact |

权限分类核对完整静态摘要、两阶段结构及官方动态权限规则插槽；标题生成核对完整身份和 system 摘要、单条会话包装及默认或显式语言收尾；手动和自动压缩核对末条用户消息的完整摘要指令，支持字符串和末尾文本块，仅规范化官方附加要求插槽。识别不改变原始正文、模型预算或主/子代理身份，不因历史里曾出现压缩指令就把后续请求归为压缩。

不以业务关键词或单个输出参数猜用途；未知变体继续转发，页面标明未识别特殊用途。与显式类别冲突时返回 400。用途、profile、类别和 querySource 必须匹配，损坏日志或私有作业的混搭证据拒绝。此元数据由服务生成，不能通过 HTTP context 注入，也不作为身份认证；旧日志不回填。

新日志行可含 `agentLaunches={state,links}`。每条 link 保存从配对 Agent 调用/成功启动结果中取得的 `childAgentId`、`parentAgentId`、`agentType`、`toolUseId`，不保存工具正文。最多 32 条、原始提取元数据最多 16 KiB，扫描最多 4096 个内容块；缺口标为 incomplete。off 不新增记录，summary 可保存该关联摘要，随日志保留期和容量回收。

子代理详情可含只读 `agentAssociation={state,parentAgentId,agentType,parentSource,typeSource,evidence}`，`evidence` 是 `{requestId,toolUseId}` 数组。state 为 explicit / linked / unknown / conflict / incomplete；字段来源为 explicit / client_tool_result / unknown。显式值优先，未提供的字段可由同会话、同子代理 ID 的启动记录补充；每次查询最多 32 条去重后的证据，额外结果、损坏或提取缺口不冒充完整关联。不同会话不关联，冲突不任意选值。

后到证据在刷新详情时生效，不修改发生时 context、原始请求行的父代理值、capture 或已发送头。没有证据、证据已过期或旧记录不含新元数据时保持未知。页面区分有效关联、来源与发生时上下文，不把缺失代理类型当成已知自定义类型。

## 响应与取消

HTTP 状态、合法端到端响应头及响应逻辑字节原样返回。content-length、content-encoding、连接级字段与 set-cookie 不沿用，以适配原生 Response 可能已解压的内容。

响应附加 x-ccrb-request-id 和 x-ccrb-engine。工具调用事件直接返回，不执行调用方工具。禁用模型隐式重试，每个日志记录仅有 attempt=1。

调用方显式声明的工具也仅参与请求构造，tool_use 仍交给调用方处理；即使上游返回声明外的 Bash，桥接也不在本机执行命令、文件操作或技能，不启动后续代理轮次。本地初始化只构造参数、不发送；业务请求在同一 SDK 的 fetchOverride 中校验后由 Ree 唯一发送，响应由桥接独占，读取收口后取消原生解析。

客户端断开、请求预算耗尽和服务关闭会取消当前作业并解除背压。HTTP 头发出后直接结束逻辑流，不拼接新事件；SSE 调用方须检查 message_stop，不能以 HTTP 200 判定完整完成。日志将 HTTP 错误、流内错误、缺失终态、本地错误和取消分开记录。

## 配置

### 上游、根模型与按需验证

- `CCRB_NATIVE_BASE_URL` 为可选 HTTP(S) 绝对地址，不含凭据、查询串、片段或空白；不设置时不传 `ANTHROPIC_BASE_URL`。保留原生 SDK 对路径前缀的语义，不自动删除或增加 `/v1`。
- `CCRB_MODEL_OVERRIDE` 只覆盖根 `body.model`，在原生构造前生效，历史及工具内部同名字段保持。入站原文保留原模型，`context.modelSelection` 记录 requested、effective 和 request/startup_override 来源；历史记录缺字段时显示未注明。
- `CCRB_NATIVE_INGRESS_POLICY=strict|local_base_url` 与上游及验证开关独立；本地原版 CC 客户端的自定义 Base URL 请求需显式选择后者。内部也使用自定义目标时，CCH 是否存在服从同次内部 CC 的原生分支，不强行补回。
- `CCRB_TLS_CAPTURE=off|verify` 默认 off。off 时原版 CC 直接发送，wire_final 为 unavailable。verify 只支持 Linux x64 固定官方原版 293、HTTPS Messages/HTTP1.1、遥测 off、直连或 HTTP CONNECT 代理；旧精简文件、HTTP 目标、HTTPS/SOCKS 代理、开启遥测等未验证组合在启动时拒绝。

verify 的辅助程序将原版 CC 已生成的请求行、有序头及正文原字节写入固定画像 TLS 通道，不重组业务、不计算最终 CCH、不替换账号。日志 source=`native_tls_verifier`，representation=`http_entity_from_final_tls_write`；哈希和 observedBytes 属于实际接受的实体字节，预览截断不缩小整体计数。note 保存连接/worker 代次、HTTP 总字节哈希和刷出状态。该样本是最后 TLS 本地写出明文，不是加密网络帧，也不证明上游已收到或执行。旧池 source=`local_pool_node_tls_receiver` 仍表示其真实接收位置。

`/api/health` 增加 tlsCapture、tlsVerifier（独立画像、SHA256、target、recipe、state）及 upstream 的安全选择摘要；不返回真实上游地址或凭据。nativeFinalCapture 表示配置能力，不表示每次请求已采集成功。辅助程序失效会显示 failed，停止后续发送，不切换发送器或自动重放。配置按实例冻结，业务请求不能控制目标、凭据、代理或采集策略。

3xx 响应按原状态返回并记为 http_error，不自动跟随；4xx/5xx 及 SSE 错误仍按已有合同处理。

### 可选缓存策略

`CCRB_CACHE_POLICY=preserve` 为默认值，保持当前布局。显式设为 `sub2api` 并重启服务后，对没有调用方消息断点的请求选取尾部可缓存块；消息至少四条时，再选倒数第二条 user 消息的末尾可缓存块。已有 system/tools 标记保留，总预算最多四个，预算不足时尾部优先。普通 API 的 SDK 自动消息标记仅在调用方未声明消息标记时由此策略替换。

调用方已有消息断点、根级 cache_control、未知缓存结构、预算耗尽或没有候选时保留原文，日志说明原因。新标记默认 ephemeral/1h；已有前置标记为 5m 或省略 TTL 时，新标记用 5m，已有 TTL/scope 不改。thinking、图片及 tool_use 不作为选点，工具结果可选。此策略不保证上游实际命中，实际缓存读写量仍以上游 usage 为准。

策略仅来自启动配置，不接受请求头或正文覆盖。旧精简产物若不支持显式 sub2api，返回受控配置错误，需重新构建和接纳产物。`/api/health` 的 runtimePolicy.cachePolicy 是已配置策略，日志的中间阶段说明是当次处理结果。

### 第一方遥测

`CCRB_TELEMETRY=off` 为默认值，关闭采集及上传。显式设为 `on` 并重启后，接入固定 293 的官方第一方事件采集、鉴权及批处理；本地初始化不采集，只有活跃业务作用域的原生事件进入采集器。自动更新、错误上报、远程功能配置拉取及第三方监控保持关闭。

遥测与模型请求共用显式配置的代理和 CA，但使用各自的官方 HTTP 实现；第一方 HTTP 客户端需要原生网络初始化，不能仅删除关闭环境变量。事件入口保持 cli，不补造启动、成功或用量事件。桥接在首发后收口 SDK，事件集合可能少于完整 CLI，反映原生构造流程，不能替代最终 HTTP 出站采样。

`/api/health.runtimePolicy` 返回 telemetry（配置）和 telemetryState（实际初始化状态）：off、pending、initialized、suppressed、unavailable。initialized 表示 logger 已初始化，不表示上传成功；suppressed 表示官方策略禁止采集，unavailable 表示 demo/旧产物没有该能力。显式 on 而旧产物不支持时，在业务发送前返回配置错误。

采集在后台执行，最多跟踪 128 个正在进行的原生采集任务，超限或采集失败不会阻塞模型；原生 exporter 自己持有批处理队列。退出清理预算 1000 ms，配合进程关闭宽限收口，不重放模型请求。关闭不会自动删除专用目录中的历史遥测文件；测试只使用合成身份和本机回环。

### 变量一览

Bun 读取本机 .env；该文件已被 Git 忽略。参考仓库 .env.example。

| 变量 | 默认或用途 |
| --- | --- |
| CCRB_MODE | native；显式 demo 才生成合成响应 |
| CCRB_CLAUDE_BINARY | 官方固定 293 程序绝对路径，原生模式必需 |
| CCRB_CLAUDE_HOME、CCRB_CLAUDE_CONFIG_DIR | 专用 HOME 与配置目录，原生模式必需 |
| CCRB_NATIVE_API_KEY、CCRB_NATIVE_OAUTH_TOKEN | 显式原生凭据；也可由专用配置提供 |
| CCRB_NATIVE_BASE_URL | 可选 HTTP(S) 目标，不设置时保留原生默认 |
| CCRB_MODEL_OVERRIDE | 可选根模型选择，不设置时保留调用方模型 |
| CCRB_NATIVE_INGRESS_POLICY | strict；本地原版 CC 自定义端点接入时显式 local_base_url |
| CCRB_TLS_CAPTURE | off；verify 需要独立构建及授信的 TLS 辅助程序 |
| CCRB_PROXY_URL、CCRB_CA_FILE | 原生进程 HTTP/HTTPS 代理与额外 CA 文件 |
| CCRB_WORKDIR | 默认专用 HOME |
| CCRB_HOST、CCRB_PORT | 127.0.0.1、8787；仅允许回环监听 |
| CCRB_DATA_DIR | data |
| CCRB_LOG_MODE | debug，可选 off、summary |
| CCRB_CAPTURE_BYTES | 单阶段正文 1048576，允许 1024–8388608 |
| CCRB_LOG_BYTES | 总载荷 536870912，允许 1024–2147483648 |
| CCRB_RETAIN_DAYS | 摘要 7 天，允许 1–90 |
| CCRB_DEBUG_RETAIN_DAYS | 正文 3 天，不超过摘要保留期 |
| CCRB_TIMEOUT_MS | 默认 0，不附加总时限；显式正整数启用包含排队的预算，最大 2147483647（计时器范围） |
| CCRB_CACHE_POLICY | preserve；可选 sub2api，修改后重启 |
| CCRB_TELEMETRY | off；可选 on，修改后重启，服从官方策略 |

真实 OAuth、账号刷新及生产请求仍需独立验收。本项目不会读取现有 cc2api 配置来自动接管账号。

显式配置的 API key 按 CLI 原生规则在专用配置中记录本地使用确认，仅保存官方标识，不保存完整密钥。专用配置中已拒绝的密钥会失败，不覆盖原决定；该操作不登录或刷新账号。

## 只读查询

GET /api/logs 支持 requestId、model、state、requestClass、sessionId、since、until、limit、offset。时间使用 ISO 8601 UTC；limit 默认 50、最多 100。GET /api/logs/:id 返回发生时的请求快照、上下文、头部决策和阶段数据。GET /api/health 返回引擎、日志模式、采集故障和最终采样能力。

查询仅使用本地日志库，不创建官方进程。页面和 API 拒绝跨来源访问，不提供公开管理鉴权或多租户隔离。
