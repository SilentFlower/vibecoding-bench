> 本文源码路径及命令以 `services/runtime/` 为工作目录。

# 请求日志合同

## Scenario: Linux x64 原生 TLS 接受边界旁路采集

### 1. Scope / Trigger

- 修改`native/tls-observer/`的探针、私有协议或平台sender接入时适用。原生运行时拥有TLS握手及唯一业务提交；该机制独立于下文终止TLS的验证器。

### 2. Signatures

- `python3 native/tls-observer/build.py`生成相邻`capture.bpf.o`。运行依赖Python 3.11+、libbpf.so.1及实际BPF/perf能力。
- `observer.py --pid <直属worker PID> --image <执行体SHA> --worker <物理代次> --capture <采集UUID>`；`CCRB_TLS_OBSERVER`由受控sender启动环境指定绝对路径。
- 私有JSONL帧`schema_version=1`；ready携带`capture_id/worker_id`。收口命令为`{capture_id,client_request_id}`，后者来自同次cc_prepared的唯一实际`x-client-request-id`。
- 平台入口为`broker.py`及固定`launch`，客户端为`client.py`；独立`observer.py`保留直属PPID模式，broker模式追加可信`--owner`及`--started`。`export_bundle.py --output <镜像输入目录> --control-policy-output <控制端策略文件>`要求canonical已提交且相关路径干净，开发快照显式`--development`。清单绑定来源revision及各文件SHA，正式镜像默认拒绝开发快照。

### 3. Contracts

- 当前只准入执行体SHA`af4cea9e21aa959c5e39c389173ba30ebb19b354b67acfe99164946450e9776d`，文件偏移`0x232d5b3`，指令`4883c4185b415c415d415e415f5dc3`；RBX=SSL对象、R14=明文指针、R15d=提交长度、EAX=实际接受长度。核验直属PPID、完整执行体SHA、指令及PID命名空间dev/inode。新映像独立重新准入。
- 探针在原生返回边界同步作一次有界副本，后续解析、收口、脱敏和持久化在后台。每事件按16KiB/64KiB/256KiB/1MiB/4MiB/8MiB六档固定容量预留，非阻塞ring16MiB，最多8条SSL连接，头128KiB、每连接正文预览2MiB。Python只复制32字节事件头和实际accepted范围。满载丢副本并累计计数，业务沿原请求继续。
- 平台加载器初始仅SYS_ADMIN/SETUID/SETGID，业务sender、worker及C监督进程为UID1001、P/E/I/A能力全零、NoNewPrivs=1；观察器附着后在ready前清零能力。Unix peer、sender直属关系、固定执行体及目标pidfd/启动时刻共同隔离归属。每worker最多一个采集器，账号至多min(max_workers,64)份诊断实例，业务并发沿原配置。
- 观察器由同UID零能力的C监督进程响应stdin挂断并回收；清理不再分配帮助进程pidfd。broker关闭stdin后最多等待2秒，socket尾部最多等待250ms，超时放弃缓冲。sender停止沿固定降权入口及既有pidfd收口，不增加KILL能力。固定seccomp按Moby profiles `6049e40058759e8a1673ac1090ec6a7e36b9c9bd`的原零能力画像展开，只补bpf/perf_event_open；制品保留其许可。
- 仅正返回实际接受量计数。事件带PID/TID、SSL对象、全采集代次sequence、accepted/requested；独立计数核对writes/bytes/dropped/read_errors/oversized。序号缺口后停止本代全部解析，继续计数用于对账。
- 仅解析唯一Content-Length的HTTP/1.1 `POST /v1/messages`（可带query）。复制和哈希前限制本实体范围，越界字节直接丢弃。不能把连接复用后的下一请求拼入当前副本。
- 最终对象`source=native_tls_uprobe`、`representation=http_entity_from_tls_accepted_write`。`complete/status/reason`区分完整与缺口；实体`observed_body_bytes/body_sha256`及整体`observed_http_bytes/http_sha256`只在完整时提供。`flushed=null`，保持TLS接受、网络刷出和上游实收的独立语义。
- 外部故障导致连续性待核对时清空头和正文预览；保留固定原因及空哈希/未知范围。Rust持久化前再次清空非HTTP_PARTIAL的不完整原文，连续HTTP前缀裁剪未闭合字符串后统一脱敏。对应平台可选快照与容量合同由`.trellis/spec/gateway/backend/settings-database.md`的“CC组装后私有采集”所有。
- 物理worker后台预备一个单次采集器。平台sender通过`NativeTlsSlot::prepare(deadline)`在新Worker初始化和复用checkout交接前有界等待同代准备，最多2秒并服从更早原截止；槽take仍即时，就绪后绑定当前业务ID。超时撤销启动代次并记OBSERVER_START_TIMEOUT，迟到启动、退役、取消及重读隔离。取消时Worker先关闭已登记槽；后继补热复用原零模型prepare及巡检路径。探针失败保持缺口，业务保持原截止和零模型重放，收口预算仍2秒。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 缺配置/未知映像/权限或帮助进程异常 | 明确OBSERVER_NOT_CONFIGURED/IMAGE_NOT_ADMITTED/受控OBSERVER原因，业务独立执行 |
| 新Worker或连续请求交接时探针准备中 | 同代有界等待；成功后交接ready，原截止或2秒先到则撤销该代并记OBSERVER_START_TIMEOUT |
| 旧sender或独立即时take在准备中 | 保留CAPTURE_PREPARING真实缺口 |
| 额外HTTP字节/未知长度或协议 | HTTP_EXTRA_BYTES/HTTP_LENGTH_UNKNOWN/HTTP_UNSUPPORTED，未知全量摘要 |
| 序号缺口或最终计数不符 | EVENT_SEQUENCE/EVENT_LOSS，清空不连续预览，哈希与范围null |
| 正文仅预览限长，事件及范围完整 | 全量实际SHA保留，正文截断单独标记 |

### 5. Scenarios and Examples

- 正常：同次原生TLS接受的实体SHA和整体HTTP SHA与隔离接收器实收一致；原生握手协议投影在采集开关两组保持一致。
- 基础边界：新worker正常探针准备在交接前完成；未配置、启动故障或截止先到保留受控原因。高负载可能丢副本或保存任务，固定原因独立于模型终态。
- 错误用法：把worker_ready直接显示为TLS ready，或取消后复用旧PID的采集器。正确处理：交接等待本PID、本代次准备，超时作废；后继零模型prepare使用独立PID和采集代次。
- 错误用法：跨缺口拼接后用完整凭据字符串替换，或把下一请求当旧请求的尾部。正确处理：先限制实体边界，缺口后冻结解析并清空不安全原文。

### 6. Tests Required

- `python3 -m unittest discover -s native/tls-observer -p 'test_*.py'`：任意头边界、部分实体、整体SHA、重复长度、连接复用分段/合并、首中尾缺口及跨事件凭据。
- `scripts/testing/cc2api-native.ts`配合CCRB_TEST_TLS_ONLY=1：交接时六PID已就绪、慢流取消后同身份补热及连续两次请求（共9次合成模型请求）、真实beta.5、独立TLS实体SHA、实际Rust保存及生产Python读取器；仅合成凭据和隔离回环。
- 强制测试ring丢副本，核对业务单次完成、EVENT_LOSS及清空预览；采集开关按完整ClientHello协议字段比较，排除真实随机及密钥材料。生产权限与资源验收由独立上线授权承接。
- `test_broker.py`覆盖六档容量、有效副本读取范围、peer/映像拒绝、目标句柄耗尽、EOF与弃读回收；`verify_container.py --image <候选> --binary <固定分发体> --output <证据目录>`在关闭外网的真实容器覆盖取消后再准备、512KiB、4MiB以上、六worker及独立TLS实收摘要。平台角色验收分别核对加载器与真实业务，不能用容器默认root身份冒充业务权限。

## Scenario: 采集、持久化及只读查询

### 1. Scope / Trigger

- 日志贯穿运行时、服务、SQLite、正文文件和页面，不能由各层自行解释采集完整性。
- 权威类型位于 src/shared/contracts.ts、src/control/log-schema.ts；终态及采集投影由 RequestTrace 统一生成。

### 2. Signatures

- LogStore.record(snapshot: LogSnapshot): boolean，有界非阻塞提交。
- LogStore.list(filters: LogFilters = {}): { rows: RequestRow[]; total: number }。
- LogStore.detail(id: string): Promise<RequestDetail | null>。
- RequestTrace.event(event: RuntimeEvent): void；finish(state: RequestState, error?: string): RequestState。
- ResponseObserver(streaming: boolean)；push(bytes: Uint8Array): boolean；finish(): boolean，返回是否首次观察到有效输出。
- requests 表保存 id、created_at、model、state、request_class、session_id、payload、context_json、decisions_json。
- captures 表保存 request_id、stage、attempt、payload、body_file；正文独立文件，payload.text 留空，按 request_id 级联删除。

### 3. Contracts

- CaptureStage 固定为 ingress、header_policy、cc_prepared、wire_final、upstream_response；每段绑定 attempt、capturedAt、source、representation、status、observedBytes、storedBytes、sha256、text、headers、note。
- ingress 使用 HTTP 原始 UTF-8 正文；不能 JSON 重序列化后声称是原文。哈希使用原始观测字节，预览先脱敏、再按完整 UTF-8 字符限长。
- cc_prepared 是 JS 原生传输前参数，CCH 可能为 00000。默认 off 的 wire_final 为 unavailable；按需 TLS 验证和显式本地常驻池实例分别遵循下文来源合同，不能重算补写或把中间值改标签充当最终值。
- context.inputFormat 可选 api / claude_code，只由输入解析写入，沿既有 context_json 持久化，不增数据库列或回填旧记录。普通 API 中间段来源为 claude_code_293_cli_prepared，原生为 claude_code_293_native_ingress_prepared；默认 preserve 的原生说明只改账号身份及 CCH 占位。显式 sub2api 实际应用时说明增加消息缓存断点处理；运行时可选 cache_policy 诊断经共享协议校验后投影到已有 capture.note，记录应用/保留/跳过及原因和位置。历史缺失字段保持可读，不把这些诊断称为真实缓存命中。demo 始终保持 demo_fixture，不能因输入是原生形状就标成实际原生发送。
- 响应 representation=response_logical_bytes。原生 fetch 可能已解压，不称为线上压缩帧。
- Content-Type 仅取分号前的媒体类型主体，去首尾空白并忽略大小写后精确匹配 text/event-stream；参数中的同名文本不切换观察器。SSE 接受 LF、CRLF、CR 及混合换行，CRLF 跨片段时仍为一个换行；规范化只用于内部观察，不改写转发及采集的原始逻辑字节。
- 模式 off 不新增记录；summary 保存摘要、关联、阶段状态而不保存原文和头值；debug 保存有界脱敏原文。既有历史不会因 off 删除。
- CCRB_CAPTURE_BYTES 默认 1048576，CCRB_LOG_BYTES 默认 536870912，CCRB_RETAIN_DAYS 默认 7，CCRB_DEBUG_RETAIN_DAYS 默认 3 且不超过摘要期。
- 总量按 JSON UTF-8 载荷和正文大小计数，SQLite 页/索引/WAL 另有开销；queued/running 的摘要和正文均不参与期限或容量回收。终态后期限仍按原 created_at 计算，可立即过期；容量超限按最旧完成记录回收。启动、写入及每分钟清理。
- 独立线程写入，队列最多 64 快照或 16 MiB。热路径不等待 flush；日志故障不得阻塞当前响应或触发模型重放。
- 同一 LogSnapshot 的请求行、上下文、决策和全部变化阶段索引在一个 SQLite 写事务中发布。先准备本轮唯一正文文件，任一文件或阶段写入失败都不能部分更新已提交索引；未引用的新文件沿用孤儿清理，旧正文继续保护既有读者。
- LogStore.detail 在同一同步只读事务内取得请求、阶段索引及关联元数据，结束事务后才异步读取正文；不得跨 await 持有读事务，也不能用查询端延时替代写入原子性。
- 私有运行时头先注册已知秘密，再统一脱敏；覆盖原生端单独持有凭据的情况。私有 IPC 不能另作普通诊断日志落盘。
- 响应片段先拼接有界前缀再脱敏；截断或中断时额外省略秘密边界，不能保存部分凭据。展示哈希不得对脱敏或格式化后的内容复算。
- 请求终态与采集状态分开：HTTP 200 不代表 SSE 成功，正文截断也不意味着模型失败。
- 只读查询不初始化 CC、不登录、不刷新账号，失效进程不影响持久详情。
- requests 快照中的 binarySha256 为实际执行体身份：原版是原文件 SHA，轻量版是经 /proc 核对的 memfd 载荷 SHA。来源与外层分发 SHA 在固定接纳表及构建清单中独立保留，不改写既有历史记录，也不把外层 SHA 冒充执行体。常驻复用和本地初始化不生成额外业务请求日志。

### 4. Validation & Error Matrix

| 条件 | 请求/采集行为 |
| --- | --- |
| SSE error 或非流式 error 内容 | stream_error，HTTP 状态及字节仍保留 |
| Text/Event-Stream 或纯 CR 换行的完整 SSE | 按完整 message_stop 判定 success，响应字节及哈希不变 |
| application/json; note="text/event-stream" | 按 JSON 观察，不误判为 SSE |
| 缺少 message_stop、JSON 无完整 message、观察超限 | incomplete |
| 调用方取消 | canceled，响应采集 incomplete |
| 预览超过上限且上游完整完成 | 请求 success，阶段 truncated |
| 正文文件丢失 | 阶段 failed，不伪造空原文 |
| 正文过期 | 阶段 unavailable，保留摘要 |
| queued/running 跨过正文或摘要保留期 | 保留原行及正文，进入终态后再按原创建时间清理 |
| 写入或队列故障 | captureError/健康状态提示缺口，停止后续采集，不重放 |
| 后续阶段 SQL 写入失败 | 请求行与全部阶段索引回滚到旧快照，采集故障可见，旧正文仍可读 |
| 重启发现 queued/running | incomplete，并记录未保存终态的说明 |

### 5. Scenarios and Examples

- 正常：收到完整 SSE message_stop，记录 success；原文 SHA256 等于实际转发字节的 SHA256。
- 正常：运行中快照切换为完成快照时，查询看到其中一份完整版本；不能出现新 success 请求行搭配旧 incomplete 响应阶段。错误用法是只等待 finishedAt 后拼接独立查询结果；正确处理是写端原子发布、读端使用同一快照。
- 边界：日志截断 1 MiB 之外的输出，但实际响应继续返回，模型仍可成功。
- 错误用法：以 Content-Type.includes('text/event-stream') 选择观察器，或把跨片段的 CR 和 LF 各算一次换行。正确做法是精确比较规范化的媒体类型主体，在有界观察器内合并 CRLF，同时保持实际响应原文。
- 错误用法：从 cch=00000 的中间正文自行重算后保存 wire_final。正确做法是保留中间值，最终采样标为 unavailable。
- 错误用法：将上游错误里的原生配置密钥直接写入数据库。正确做法是从实际发送头注册秘密，对查询、正文文件和错误说明统一脱敏，调用方响应保持原始字节。
- 错误用法：为了补日志重试一次模型。正确做法是展示采集缺口，保留唯一 attempt。
- 错误用法：给轻量运行时的请求行写入官方来源文件 SHA。正确做法是写入实际执行载荷 SHA，来源与加载器作为独立构建证据；历史原版请求继续保留原来有效的实际文件 SHA。

### 6. Tests Required

- tests/integration/control.test.ts：原始入站空白、扩展头决策、off/summary、截断、取消、慢消费者、写入故障和持锁写线程不阻塞/不重放。
- tests/integration/storage.test.ts：容量、摘要/正文分期过期、重启、正文丢失；初始快照分别为 4/8 天前的 queued/running 时保留摘要及正文，转为 success 后分别回收正文或整行。
- 同一存储套件另验证并发读取五阶段的代次一致性，以及在最后响应阶段注入 SQL 失败后请求/上下文/阶段全部回滚、旧正文可读且 captureError 可见。
- tests/unit/observer.test.ts：LF/CRLF/CR/混合换行在所有 UTF-8 分片宽度下保持终态与首输出一致；跨片段 CRLF 不产生空事件，未结束及超大事件仍不可验证。
- tests/native/tls-verifier.test.ts：TLS 采集 off/verify 两种模式均用实际原版及独立 OpenSSL 实收验证普通 SSE、大小写媒体类型、纯 CR 和 JSON 同名参数；终态正确、只发送一次，客户端与日志响应哈希及字节数等于夹具原始实体。
- tests/unit/redaction.test.ts：原对象不变、已知秘密、代理密码、UTF-8 与部分凭据边界。
- tests/native/native.test.ts：控制层事先不知道原生密钥时，上游错误回显的秘密仍不能进入可查询日志。
- 同一原生套件对原版与轻量产物验证 binarySha256 真实；多轮复用、取消与流中退出后的日志归属和采集状态独立，初始化不制造虚假作业。
- 新原生样本导入前后核对既有详情投影哈希不变；独立 Node TLS rawHeaders 与实体正文可作有序原始头证据，Bun 接收的规范化头不能冒充 rawHeaders。生产最终采集能力不因离线补采而改变。

## Scenario: 原生模型选择与最后 TLS 本地写出采集

### 1. Scope / Trigger

- 前置模型选择和验证器观测贯通服务、私有管道、RequestTrace、持久化与只读页；保留既有五阶段，不增加数据库列或回填旧记录。
- 相关类型在 src/shared/{contracts,tls-verifier-protocol}.ts、src/control/trace.ts；运行目标与传输策略由 runtime-contract.md 所有。

### 2. Signatures

- RequestContext.modelSelection?: { requested: string; effective: string; source: 'request' | 'startup_override' }；isModelSelection(value: unknown): value is ModelSelection。
- FinalCaptureSample 保留 body、headers、httpVersion、capturedAt、verified、note；新来源可附 source='native_tls_verifier'、observedBytes、sha256: string | null、complete、flushed、status='failed'。
- decodeTlsVerifierFrame(line: string, instanceId: string, previewLimit: number): TlsVerifierEvent；RequestTrace.finalCapture(read: () => FinalCaptureSample | null): void。
- GET /api/health 增加 tlsCapture、tlsVerifier 和 upstream；日志详情继续返回 RequestDetail。

### 3. Contracts

- 原始入站模型保留在 ingress；前置有效模型写入 RequestRow.model，选择证据沿 context_json 保存。共享解码器核对 effective 与行/作业根模型相同；历史缺字段保持缺省，不从当前配置补写。
- 私有封套固定 schema_version=1、instance_id；command_id 单调，指令为 init/begin/expected/finish/shutdown。ready 核对辅助 PID 和画像；capture 绑定 request_id、worker_id、worker_pid、connection_id 和单调 sequence。重复、跨归属或非法完整性关系不得写到下一请求。
- capture 来自最后上游 TLS 写入器实际接受的明文；body_bytes/body_sha256 覆盖实体已接受范围，http_bytes/http_sha256 覆盖请求行、头和实体。complete 表示全范围已接受，flushed 单独表示刷出成功，verified 再核对同次准备值及原生 CCH 槽位；待发送缓冲区不能整体算作已写出。
- wire_final 的新 source='native_tls_verifier'、representation='http_entity_from_final_tls_write'；note 记录 worker/连接、整体 HTTP 字节及哈希、刷出和固定原因。它不等于加密网络帧、第一跳接收，也不证明上游接收或执行。
- body_preview_b64 有启动侧预览上限，增量整体计数/哈希不截断。先注册实际发送头中的秘密，再脱敏保存正文和有序头；不完整前缀省略秘密边界，UTF-8/格式化后的预览不用于重算原观测哈希。summary/off 不保存原文，采集截断独立于模型终态。
- 默认 off 未取得样本时为 unavailable，不用准备值补写。部分写出或刷出失败为 incomplete；完整但核验不符为 failed。私有通道缺证显示 failed、sha256=null 和范围未知说明，不能把未知零值当成已确认没有发送。采集失败不触发模型重放。
- final_capture_ready 只通知已存入本请求的独立样本，允许流结束前刷新日志；completed/错误收口再次检查时不得覆盖已保存证据。旧池省略新来源字段时，仍保持 local_pool_node_tls_receiver/http_entity_body_after_native_transport 的接收语义。
- 健康 nativeFinalCapture 表示配置能力，不表示每次采集成功。tlsVerifier 包含 profile、sha256、target、recipe、state；upstream 只公开 endpoint 选择来源、根模型覆盖和 ingressPolicy，不返回真实端点或凭据。辅助程序失效单独显示 failed，不能仅以日志数据库健康认定验证器可用。

### 4. Validation & Error Matrix

| 条件 | 日志行为 |
| --- | --- |
| 旧记录无 modelSelection | 可读，显示历史未注明或入口未解析 |
| 选择来源未知或 effective 与实际行/作业不符 | 解码失败，不猜测有效模型 |
| 完整写出且已刷出、预览小于整体 | truncated，整体计数/哈希保持 |
| 仅写出部分或刷出失败 | incomplete，保留实际范围及失败原因 |
| 完整实体核验失败 | failed/captureError，不修改已返回模型字节或重放 |
| 验证器未开启、无样本或通道失效 | 分别显示 unavailable、缺口说明或 failed，不从第一跳补写 |
| CCH 合法空白或正文含内部旧标记 | 正常采集；不能误报失败或拒绝业务 |

### 5. Scenarios and Examples

- 正常：调用方 model=A，启动覆盖为 B；入站仍保存 A，行及 modelSelection.effective 为 B，source=startup_override。
- 边界：8 MiB 原生正文完整写出，预览只保存 16 KiB；wire_final 为 truncated，observedBytes 和 SHA256 仍对应完整实际写出实体。
- 错误用法：用采集器第一跳样本或模型完成状态推断上游实收。正确处理：保留不同来源，并独立展示本地完整性、刷出和模型终态。

### 6. Tests Required

- tests/unit/{tls-verifier,log-api,upstream}.test.ts：帧归属/完整性、模型选择和历史字段兼容。
- tests/integration/control.test.ts：原始/有效模型分别持久化、缺证不重放、秘密中途截断不泄露而整体哈希保持。
- tests/native/tls-verifier.test.ts：对独立 OpenSSL 实收核对实体及整体 HTTP 哈希；长流提前可见、完整/截断/部分/失败、取消后重建、错误 PID 和实例隔离；CHK-001/CHK-002 均核对 captureError=null。
- tests/browser/logs.spec.ts：模型选择来源、最后写出位置和验证器 failed 健康状态可见，所有刷新零额外推理。

## Scenario: 测试专用 TLS 最终采集与池 Messages 验证

### 1. Scope / Trigger

- scripts/test-pool.ts 在测试链路中采集 CC 原生最终出站，再向明确的 Messages 池转发；报告字段 ccFinal 不扩展生产 CaptureStage，也不自动开启内置验证器的 nativeFinalCapture 能力。
- 复用已接纳的官方/精简二进制、Engine、RequestTrace 和 Redactor，不修改原生运行时、CC 目标、生产 EngineConfig 或数据库；池响应不能作为 Anthropic 鉴权或缓存命中证明。

### 2. Signatures

- bun run test:pool --binary <已登记文件> --output <新目录> [--serve <回环端口>]：缺省离线假池；控制端和假池处于独立无外网空间。
- bun run test:pool --live --pool-env <受保护文件> [--live-run <ID>] --binary <已登记文件> --output <新目录>：显式有界真实验收。
- bun run test:pool --report-only <报告目录> --serve <端口>：宿主只读查看；bun run test:pool:page <报告目录>：无外网浏览器验证，不运行模型场景。
- scripts/testing/pool-common.ts 统一定义 PoolConfig、BodySample、ForwarderFrame、DriverFrame 及解码器；pool-report.ts 定义 schemaVersion=1 的 PoolReport/PoolCaseReport。
- loadPoolConfig(path): Promise<PoolConfig>；validatePoolConfig(config): void；poolLedgerName(runId='first-run'): string；poolProxyEnvironment(env, live): Record<string,string>。

### 3. Contracts

- 配置文件为不超过 64 KiB 的普通文件，group/other 无权限，只解析赋值、不执行 shell。只读 CCRB_TEST_POOL_BASE_URL/API_KEY，兼容 PROJECT_REQUESTER_BASE_URL/API_KEY；来源冲突拒绝，模型/fallback 字段不读取，模型固定 deepseek-flash。
- Key 仅支持 4–4096 位 ASCII 字母数字及 ._~-。含引号、反斜杠、Unicode 等不支持格式在宿主与 Node 初始化时拒绝，避免 JSON 转义绕过字面脱敏；错误说明不回显 Key。此限制属于测试工具，不改变生产凭据合同。
- 真实目标必须 HTTPS；离线只允许回环 HTTP(S)。拒绝 URL 凭据/query/fragment 及 Anthropic/Claude 域名（含末尾点）；/v1 只拼接一次，保留原生 /v1/messages 查询串，不转换 OpenAI 协议。
- CC 驱动另处于仅 lo 的网络空间，独立 HOME/config、合成 Key、遥测 off，环境只有 HOME/LANG/PATH。CONNECT 仅接受 api.anthropic.com:443，固定接入权限 0600 的 Unix socket，不解析或直连该公网目标；启动自检实际拒绝普通 HTTP 和错误 CONNECT。
- 宿主独立 Node TLS 接收端保留实收 rawHeaders、实体正文和 HTTP 版本，启动校验有序重复头。2 MiB 请求预算只用于有限 acceptance；手工模式不套用。只收完整 UTF-8 的 Messages 正文，先由宿主独立核验非零原生 CCH 后才允许第二段；核验不能补写或生成出站 CCH。
- 第二段只改目标、根 model、鉴权及传输字段，保留其余业务、合法扩展头与父子归因。删除原 CC/代理凭据、Cookie、连接级字段及 Connection 声明字段，重建 Host、长度和 x-api-key，逐项说明原因。
- 真实池 Node 可通过 --use-env-proxy 复用经校验的 HTTP_PROXY/HTTPS_PROXY/NO_PROXY；大小写来源冲突、URL 凭据及非 HTTP(S) 代理拒绝。离线不继承宿主代理，CC 驱动也不继承；Node 缺少该选项时启动失败，不回退绕过代理。
- 每轮最多三次、串行、max_tokens=128，池预算 30 秒、CC 45 秒，首错停止，不重试、重定向、换模型或删字段。默认账本 artifacts/pool-tls-forwarder-live-first-run.json 排他创建，发送前预留场景；新预算须显式选择 --live-run，ID 限 1–64 位 ASCII 字母数字/下划线/连字符且首位为字母数字，使用独立同前缀账本。已有账本不覆盖，不自动开启下一轮；缺失回执时预留数是次数上界。
- 报告分别记录 ingress、ccPrepared、ccFinal、poolPrepared、poolResponse、bridgeResponse。ccPrepared 是中间值；ccFinal 来自 Node TLS 实收；poolPrepared 是客户端组装参数，不能称为池端原始网络头。各段保留来源、表示、原始 SHA256、观测/保存长度及完整性，预览最多 1 MiB，完整响应继续流动并参与哈希。
- forwarding 分开记录 attempted、outcome、upstreamStatus、localStatus、failureCode/error。只有观测到池响应头才设置 upstreamStatus；否则它及 poolResponse 为 null，本地 400/502 只出现在本地转发状态与调用方响应。异常只保存白名单码及受控说明，响应表示始终为逻辑字节。
- 驱动日志 off，必要数据走私有管道交宿主二次脱敏后持久化，结束并关闭驱动后扫描专用目录。Node 和驱动的脱敏上下文按请求隔离，避免上一响应的敏感名称标志值污染下一请求预览。预览含脱敏标记时以原始哈希比对，不反向填充值、不为补证据重放。
- 响应 JSON/SSE 逻辑字节直接返回，删除不匹配解压后正文的长度、编码及连接字段；取消向池请求传播，原生进程退役。场景终态复用 RequestTrace，HTTP 200/EOF 不能替代完整 Messages 终态。
- 报告写入独立新目录；只读服务器仅在回环开放 index.html/report.json，动态文本统一转义，无推理入口，查看或刷新不初始化 CC、不新增模型调用。旧回执和原版/精简身份保持。

### 4. Validation & Error Matrix

| 条件 | 必须行为 |
| --- | --- |
| 配置/Key 格式不支持、rawHeaders 自检失败 | 受控启动失败，零池模型发送，不回显秘密 |
| 非 Messages 路径、损坏 UTF-8、超限、CCH 不符 | 拒绝/关闭连接或标记采集失败，不转发池，不用中间值填补最终采集 |
| 连接失败、池超时且尚无响应头 | upstreamStatus=null、poolResponse=null；本地 502 单列，无重试 |
| 池 401/429/500 或 3xx | 保留已观测状态/逻辑字节，3xx 不跟随，真实验收首错停止 |
| SSE error、缺少 message_stop | stream_error/incomplete；不得因 HTTP 200 判成功 |
| 主动取消或慢流超时 | 取消中止池转发并报告 canceled；超时报告 timeout/未完成采样，清理有界 |
| 秘密回显、跨片段、超过预览限额 | 脱敏预览，保留实际观测字节哈希；截断不阻塞完整响应 |
| 已有轮次账本、仅查看报告 | 不覆盖或重新推理；查看不暴露配置/证书/任意文件 |

### 5. Scenarios and Examples

- 正常：Claude 模型原生请求经 TLS 完成 CCH 后，仅第二段改为 deepseek-flash；真实 JSON/SSE 响应的逻辑字节 SHA256 与调用方一致，池模型名和输出不改写。
- 边界：调用方在 SSE 首片后取消，转发器 canceled、工作进程退役；这只证明本地转发已中止，不证明池内计费或后台执行已结束。
- 错误用法：把未收到池响应时生成的本地 502 写成 real_pool_response。正确做法：poolResponse=null，并显示 forwarding.localStatus 与受控诊断。
- 错误用法：复用整个运行批次的脱敏上下文，上一响应 allow-credentials=true 导致后续 stream=true 被遮住。正确做法：按请求建立上下文；历史预览保留原样，以原始 SHA256 验证请求差异。
- 错误用法：失败后删除账本自动再试或改用 Gemini。正确做法：保留原轮次及失败；明确新预算后才显式选择独立轮次，仍执行相同三场景与首错停止。

### 6. Tests Required

- tests/unit/pool-forwarder.test.ts：受保护配置、来源冲突、ASCII Key 格式、JSON/SSE 跨片段回显、哈希/截断、路径/模型映射、预算、轮次安全、私有帧解码、报告转义与文件白名单。
- tests/integration/pool-forwarder.test.ts → tests/pool/transport.test.ts：独立无外网空间内真实 Node rawHeaders、非法 Key 零请求、拒绝/超限、单次发送、HTTP 错误、重定向、背压、取消、超时、无池响应的本地 502、代理路由和跨请求脱敏隔离。
- 原版/精简分别跑 test:pool 离线矩阵，核对 CCH、头部/metadata/父子归因、仅根 model 改动、准备预览、凭据边界、取消退役及结束后的目录扫描。
- 显式真实验收独立记录三次上限、原始 CCH/哈希及 JSON/SSE/取消结果；失败保留实际结果，普通 test/typecheck/build 不访问真实池。页面验收覆盖桌面、390 像素、文本安全、三次刷新零推理及历史文件摘要不变。

## Scenario: 本地 Claude Code 常驻池联调与最终采集

### 1. Scope / Trigger

- scripts/local-pool.ts 提供用户手工发请求的常驻 Base URL，独立于三次小预算验收；复用产品服务、原生 Engine、TLS 接收端、脱敏和日志页。
- 有限验收和用户手工链路保持独立，既有账本不覆盖；桥接缺省无预算规则由 runtime-contract.md 所有。只有本地实例配置已自检采集端时，才报告 nativeFinalCapture=true。

### 2. Signatures

- bun run start:pool --run <新ID> --binary <固定原版293> --pool-env <受保护文件> [--port <端口>]；默认 127.0.0.1:8787。
- startLocalPool(options: LocalPoolOptions): Promise<LocalPoolRunning>；startServer(config, injectedEngine?, startup: ServerStartupOptions = {}): Promise<RunningServer>。
- ServerStartupOptions 包括 nativeIngressPolicy、secrets、finalCapture(requestId)、localPoolStatus()，仅启动调用方可设置，不接受 HTTP 注入。
- FinalCaptureSample = {body, headers: HeaderPair[], httpVersion, capturedAt, verified: boolean, note}；RequestTrace.finalCapture(read: () => FinalCaptureSample | null): void。
- LocalPoolLedger.create(path, runId, live, budget)、reserve(requestId)、finish(requestId, result)；LocalPoolEngine.takeFinalCapture(requestId) 取出并清理同请求样本。
- PoolTransportObserver.run<T>(operation: () => Promise<T>): Promise<T>、snapshot(): PoolTransportDiagnostics、close(): void；decodePoolTransportDiagnostics(value: unknown): PoolTransportDiagnostics 集中规范化观测字段，ForwarderFrame.finished 可携带 transportDiagnostics。
- startIsolatedProxy(socketPath: string): Promise<IsolatedProxy> 使用隔离空间内的 Node 字节代理；私有初始化只含 socketPath，回执为 ready(port) / stats(proxyRequests,rejectedRequests)，仅接受 shutdown 或父管道 EOF 关闭。

### 3. Contracts

- PoolConfig.mode 显式区分 acceptance/manual；缺省沿用原验收。live 必须如实表示真实池或离线回环，不得用 false 放开外部调用。原有 URL、Key、模型映射及代理规则复用上文测试 TLS 合同。
- CLI 手工模式默认不限请求次数，PoolConfig.maxRequests=null；null 仅允许 manual，显式有限手工实例仍支持 1–20 次。模型参数原值交池判断，不设输出范围、温度范围、thinking 枚举/最小预算或工具组合政策；必要结构检查沿 runtime 合同。手工 PoolConfig.timeoutMs=0、桥接/驱动预算为 0，不附加请求总时限、旧 50 秒事件等待或旧 5 秒核验截止；0 不创建计时器，有限实例的显式正预算仍可用于测试。每个入站最多一次池发送，不重试、不跟随重定向、不回退；客户端重发为新调用。旧真实验收三次/128 tokens、显式超时和首错停止保持，不能用 null 或 0 绕过自动验收预算。
- artifacts/local-pool-runs/<run>/ledger.json 排他创建，发送前持久预留，同目录不覆盖重置；预留数是异常情况下实际尝试上界。保存 requestId、时间、attempted、upstreamStatus、localStatus、outcome，以及可选 failureCode、transportDiagnostics，不保存 Key 或正文；旧记录缺少新增字段时保持未知，不回填。
- PoolTransportDiagnostics.phase 为 unknown / before_send / sending / awaiting_headers / response_body；bodySentObserved 为 boolean|null，connectionBytesWritten/connectionBytesRead 为非负安全整数或 null。阶段只表示本地观测：sendHeaders 早于实际写入，bodySent 也不能证明池已执行。计数来自当前模型 POST 所关联连接的累计值，不是每个请求或池端实收字节；CONNECT、其它请求及无可靠关联的计数不得混入。
- 诊断按模型 POST 的异步作用域和 request 对象关联；当前转发结束释放订阅、请求映射及连接引用。不可用观测降为 unknown/null，不改变模型结果或触发重放。集中解码仅保留固定诊断字段与 POOL_FAILURE_CODES 白名单；未知错误码采用通用类型，不持久化任意异常 message、URL、头或正文。
- /api/health.localPool 返回 runId、model、live、budget、reserved、remaining；不限次数时 budget/remaining 为 null，reserved 持续计数，不能把 null 当成零额度。ready.json 保存 PID/Base URL 与运行元数据；启动、自检、健康检查和页面刷新均不发模型请求。
- 驱动环境只有 HOME/LANG/PATH，独立仅 lo 网络、专用 HOME/config、合成 Key、遥测 off；只接受固定 CONNECT 接入私有 socket。池真实 Key 仅由宿主/Node 持有，不进入原生进程、进程命令行或私有资源文件。
- CONNECT 密文由隔离空间内的专用 Node 进程透明转发，继续拒绝普通 HTTP 和错误目标；Bun 管道的大正文 TLS 解密失败不能靠改正文、降级 TLS 或降低测试大小绕过。代理只回传端口与计数，凭据不进入配置，关闭清理自身进程及临时 bundle。
- 原生 ready 回调在业务投递之前逐物理进程核验启动环境并保留证据；不能在大正文处理后依赖不完整 /proc 环境采样误判凭据变化。私有帧保留结构、归属及 EOF 校验，不对业务正文设置 8/24 MiB 门槛；日志预览继续独立有界。
- 驱动 run/cancel/shutdown 指令及 LocalDriverFrame 由集中解码器负责，沿用 RuntimeEvent 校验；同请求终态和真实 idle 收口，产生 TLS 采集时还须等待其 finished，之后才释放串行槽位。PrivateProcess.next(0) 允许常驻空闲，不能套用有限验收的空闲超时。
- wire_final source=local_pool_node_tls_receiver，representation=http_entity_body_after_native_transport，来自 Node 实收 rawHeaders/实体/版本，采集在第二段根模型及鉴权映射前。先核对活动请求、唯一采集、会话及独立正确非零 CCH 才允许池转发；拒绝重复或错归属帧。
- 池 Key 在 RequestTrace 创建前注册；TLS 样本在处理池响应头前保存，避免敏感名称响应标志影响此前请求预览。继续遵守 off/summary/debug、UTF-8 限长及原始哈希；脱敏预览不能用于反向校验或补造原文。
- 提供者返回 null 表示 unavailable，异常或 verified=false 表示 failed 并显示 captureError；采集故障不改变已取得响应的模型终态、不触发重放。第二段参数与真实池端实收仍严格区分。

### 4. Validation & Error Matrix

| 条件 | 必须行为 |
| --- | --- |
| 相同目录已有账本 | local_pool_run_exists，保留原内容，CLI 启动失败 |
| 回环端口冲突 | local_pool_port，清理本次启动资源，零池推理 |
| 手工原生正文 max_tokens=128000、thinking.type=adaptive | 保留参数转发；模型能力由池校验，池错误沿现有响应路径返回 |
| 入站关键字段结构不合法或数值不能表示为有限 JSON 数值 | 本地拒绝 400，不发送池；不把模型范围问题混入 |
| 手工首响应等待超过 50 秒、完整请求 66 秒 | 正常完成，不套用本地默认截止 |
| 手工正文 26 MiB | 完整转发及独立哈希/CCH；日志仅截断预览 |
| 不限次数的手工实例超过 20 次 | 继续转发并计数，不产生本地额度错误 |
| 显式有限实例耗尽其配置次数 | 本地 429/POOL_BUDGET_EXHAUSTED，不发送池，upstreamStatus=null |
| 池连接失败或显式预算超时，尚无响应头 | 本地 502，池状态为 null，单次尝试记入预算 |
| 模型 POST 正文发送后、收到池响应头前断连 | 可记录 awaiting_headers/bodySentObserved=true，upstreamStatus=null；不据此判定池未执行或自动重试 |
| 代理 CONNECT 失败，模型请求尚无发送观测 | before_send 或 unknown，模型连接累计计数保持 null，不使用代理握手的计数 |
| 诊断缺失、字段损坏或订阅回调异常 | 缺失保持兼容；非法观测归一化为 unknown/null，额外载荷丢弃，原转发结果不受影响 |
| 取消或响应异常 | 取消传到池，原生进程退役，后续新作业可重建，当前不重放 |
| 最终样本缺失、失败、日志截断 | 分别显示 unavailable/failed/truncated，不拿中间值补写 |

### 5. Scenarios and Examples

- 正常：用新轮次及受保护配置启动，再在临时终端设置 ANTHROPIC_BASE_URL=http://127.0.0.1:8787、合成 ANTHROPIC_AUTH_TOKEN，运行 claude --model claude-sonnet-4-6。池侧根 model 实际为 deepseek-flash，原生进程不取得池 Key。
- 边界：默认手工实例超过 20 次继续发送，128000 输出预算与 adaptive thinking 原样到达池；26 MiB 正文、52 秒首响应等待及 66 秒全程正常完成。显式配置 20 次的有限实例在第 21 次本地拒绝；同轮目录不能覆盖历史报告和账本。
- 错误用法：从某个 Claude 模型的默认输出预算推断池上限，再本地拒绝或裁剪。正确做法：手工链路保留原值，由实际池返回支持情况；自动验收仍用显式小预算。直接用有限验收脚本常驻、把 live=false 指向真实池、给 Base URL 再加 /v1，或把预览 CCH 当作原始校验输入仍属于错误用法。
- 错误用法：收到 UND_ERR_SOCKET 且未见池响应头，就认定请求没有发送并重试。离线可复现池读完整 POST 后关闭连接的同一错误；正确做法是记录观测阶段和受控错误，单次失败收口，允许下一独立请求执行。诊断改进不能冒充原始真实故障已解决。

### 6. Tests Required

- tests/unit/pool-forwarder.test.ts：手工 null/0 及连续 25 次账本记录、验收拒绝 null/0、真实/离线手工 32769 与 128000 原值保持、大正文私有帧、显式有限 20 次预留、旧三次/128 限制、账本排他与真实状态。
- 同一单元套件核对诊断损坏降级、零值/未知区别、额外敏感字段丢弃、错误码白名单、旧回执兼容及观测失败不改变原操作；tests/pool/transport.test.ts 的真实 Node 直连/HTTPS 代理矩阵核对收头前断连、流中断、CONNECT 拒绝、单次池实收和下一请求恢复，tests/local-pool/gateway.test.ts 核对实际 CLI 回执经宿主持久化到账本。
- tests/integration/control.test.ts：启动侧秘密、最终样本缺失/异常、off/summary/debug、原始 SHA256 与截断，采集失败不改变响应。
- tests/integration/local-pool.test.ts 包裹 tests/local-pool：无外网模拟池，真实客户端/工具续轮/交互终端、子代理、端口冲突、取消、错误/显式超时/重定向、显式有限 20 次拒绝及不限次数连续 25 次保持参数；另验证 Sonnet 5、26 MiB 完整正文和 66 秒长请求、启动环境及凭据落盘；桌面及 390 像素页面、脚本安全、三次刷新零推理。
- 当前原版 + preload 的离线池场景回归，旧轻量产物不声明已包含新源码合同；真实手工实例只检查健康/页面及隔离，不自动发送真实池推理。

## Scenario: 基于客户端启动证据的代理关联视图

### 1. Scope / Trigger

- 实际 CLI 子代理可能只提供 session、agent ID 和子代理 billing，没有 parent-agent-id 或 agent-type。日志可补充有证据的关联视图，不能冒充原始入站或当时实际发送值。

### 2. Signatures

- collectAgentLaunches(prepared: PreparedInput): AgentLaunches；resolveAgentAssociation(context: RequestContext, candidates, incomplete): AgentAssociation。
- RequestRow.agentLaunches 可选；LogStore.detail(id) 的 RequestDetail.agentAssociation 可选；isAgentLaunches / isAgentAssociation 与 decodeLogDetail 集中验证。

### 3. Contracts

- 只对已识别原生入站提取：assistant Agent tool_use 与 user 的同 tool_use_id 成功 tool_result，固定 293 成功启动或报告交付格式中的 childAgentId，匹配调用的 subagent_type，以及证据所属请求的规范 parentAgentId。自由文本、失败结果或孤立块不构成启动证据，重复/未知成功格式明确不完整。
- 异步结果沿用固定启动头及紧随的 agentId 行；前台结果接受原版 Hns 生成的完整 SubagentHandback 交付短句，包含普通及固定 SECURITY WARNING 变体，只忽略外侧缩进和空白。前台元数据限 1024 字符且必须完整匹配；报告正文、agent-message 内的任意文本不参与身份提取。同一结果出现多个前台/异步元数据块时保持 incomplete，不任取一个声明。
- AgentLaunches={state:complete|incomplete,links:[{childAgentId,parentAgentId,agentType,toolUseId}]}，两个缺失关联字段为 null。最多 32 条、JSON 容器及分隔符在内最多 16 KiB、最多扫描 4096 个内容块；父代理和类型沿既有 512 字符及 Latin-1 无控制字符边界，childAgentId/toolUseId 另限 128 位字母数字下划线连字符。
- 元数据经 Redactor 后沿既有 request payload 保存，不新增表或迁移历史。脱敏破坏身份、超限、提取异常时保存 incomplete，不把占位符当 ID。off 不保存新记录，summary 保留必要证据摘要而不保存工具正文，证据随日志容量及保留期清理。
- 详情关联只读查询同 sessionId、同 childAgentId；数据库先按声明去重再返回最多 32 条，额外取一条检测溢出。重复历史不耗尽额度，取出的内容和证据请求 ID 同源，不扫描调试正文或创建全局永久关系 Map。
- AgentAssociation={state,parentAgentId,agentType,parentSource,typeSource,evidence:[{requestId,toolUseId}]}。state=explicit|linked|unknown|conflict|incomplete；来源=explicit|client_tool_result|unknown。显式值优先，不同声明不任意取最新值；空值和 unknown 来源一致。
- 后到证据在刷新时可见，不回写 context、原始请求行的父代理值、capture/SHA 或已发送头。旧记录无元数据则未知；证据是客户端声明，不是身份认证。默认 agent:custom 不能证明实际类型为自定义代理。

### 4. Validation & Error Matrix

| 条件 | 关联视图 |
| --- | --- |
| 两字段显式给出且无矛盾 | explicit，值保持 |
| 缺失字段由同会话完整一致的启动或报告交付证据补齐 | linked，来源及证据定位可见 |
| 无证据、证据过期、旧记录无新字段 | unknown，不猜直接父代理或类型 |
| 不同父代理/类型，或证据与显式值矛盾 | conflict，显式值保留，不任取冲突值 |
| 提取/查询超限、损坏、查询失败或采集缺口 | incomplete，未确认字段不补齐，不重放模型 |
| 相同 ID 出现在不同会话 | 不关联 |

### 5. Scenarios and Examples

- 正常：子代理先到，主会话后续消息含配对启动记录或前台报告交付说明；刷新子代理详情可显示父代理和 Explore 类型，发生时字段仍为空。
- 边界：同一启动历史出现在 33 条请求中仍可关联；证据正文过期而摘要有效时仍可查，证据摘要被清理后恢复未知。
- 错误用法：把同会话主请求当所有子代理的直接父代理，或用后来证据改写过去的出站头。正确做法：按成功工具结果及所属规范上下文关联，仅更新只读视图。

### 6. Tests Required

- tests/unit/request-attribution.test.ts：角色/ID/工具/成功格式配对，前台普通及安全提示变体、外侧空白、完整收尾、混合/重复元数据、自关联、未知格式与伪造文本，以及块数/字节/条数上限、显式值和冲突。
- tests/integration/storage.test.ts：迟到、多子代理、嵌套、跨会话、重复去重、超限、损坏、summary/off、脱敏、重启及清理；原始快照不变。
- tests/local-pool/attribution.test.ts：实际 CLI 分别完成后台和前台 Explore，含权限分类与 SubagentHandback；父代理和类型按配对结果关联，TLS 实收的业务字段和独立 CCH 不变。tests/browser/logs.spec.ts 继续核对关联与来源、证据跳转、历史兼容和手机布局。

## Scenario: 本地池启动诊断与双客户端故障隔离

### 1. Scope / Trigger

- 本地池尚未就绪时，证书、TLS 自检、私有通道、隔离代理及运行时校验的失败需要保留安全证据。启动诊断与模型转发诊断分开，不能用复跑成功回填历史根因。

### 2. Signatures

- scripts/testing/local-pool-startup.ts 定义 LocalPoolStartupDiagnostics、LOCAL_POOL_STARTUP_STAGES、LOCAL_POOL_STARTUP_CODES；decodeLocalPoolStartup(value: unknown): LocalPoolStartupDiagnostics 集中重建字段。
- LocalPoolStartupError(stage: LocalPoolStartupStage, error: unknown) 继承 BridgeError，保留 code=local_pool_startup、status=503，startup 为安全诊断；本地 CLI 沿已有受控 message 显示阶段和原因。
- ForwarderFrame.fatal 与 LocalDriverFrame.fatal 可选 startup: LocalPoolStartupDiagnostics；decodeForwarderFrame / decodeLocalDriverFrame 负责重建，旧帧仍兼容。
- PrivateProcessError.code 为 CHANNEL_TIMEOUT / CHANNEL_CLOSED / CHANNEL_TRUNCATED / CHANNEL_INVALID，不携带解码器原始异常。

### 3. Contracts

- 启动诊断只含 stage、failureCode。stage 固定为 unknown、workspace、certificate、forwarder_build、node、proxy_environment、forwarder_start、tls_listen、tls_probe、forwarder_verify、driver_start、driver_isolation、proxy_start、proxy_probe、driver_setup、runtime_verify。
- failureCode 只接受 LOCAL_POOL_STARTUP_CODES：明确检查失败、固定通道代码及有限系统/TLS 代码。系统/TLS 白名单为 ENOENT、EACCES、EPERM、EADDRINUSE、ECONNREFUSED、ECONNRESET、EPIPE、CERT_NOT_YET_VALID、CERT_HAS_EXPIRED、DEPTH_ZERO_SELF_SIGNED_CERT、UNABLE_TO_VERIFY_LEAF_SIGNATURE、ERR_TLS_CERT_ALTNAME_INVALID；未知原因统一 UNKNOWN。
- 解码后只返回两个固定字段，丢弃扩展字段。未知子阶段使用宿主已观测阶段；不得复制任意 cause、message、stderr、URL、头、正文或证书材料。fatal 的说明也重建为组件固定文案。
- TLS 接收端与隔离驱动在 ready 后清除启动标记；运行期 fatal 不附 startup，不能把已发送模型失败说明成“未发起池推理”。启动及自检仍为零模型调用，不增加重试或降低 TLS、环境、固定目标及原始头校验。
- 资源创建也纳入失败捕获；各项清理分别尝试，保存最初阶段和原因。宿主清理出现异常时附固定说明，不覆盖首错，也不推断资源已成功释放；驱动运行时构造失败仍须关闭已创建代理。
- TLS 原始头启动探针预算 5000 ms、宿主两类就绪等待各 10000 ms，均与模型 PoolConfig.timeoutMs 无关。构建既可能失败返回，也可能同步抛出，须用 try/await/catch 覆盖；不能只在返回 Promise 上接 catch。
- 双客户端验证共享合成 HOME/config/cwd，但使用不同 session；取消及关闭只操作对应终端进程组。排队请求断开与日志终态分开观测：日志会在串行队列轮到该请求时收口，模型发送和账本预留仍应为零。

### 4. Validation & Error Matrix

| 条件 | 诊断及行为 |
| --- | --- |
| 证书生成失败 / 构建失败 / Node 缺失 | certificate / forwarder_build 等实际阶段及固定检查代码，503，零模型 |
| TLS 验证、原始头不匹配 | tls_probe 及白名单 TLS 代码或 RAW_HEADERS_MISMATCH，不放行转发 |
| 等待超时、提前 EOF、截断或损坏帧 | 宿主已知阶段及对应 CHANNEL_*，不输出帧原文 |
| 隔离、目标拒绝、运行时校验失败 | driver_isolation / proxy_probe / runtime_verify 及固定代码，清理已创建资源 |
| 子进程没有诊断或未知代码 | 保留宿主阶段、UNKNOWN；不通过通用 message 猜测原因 |
| 清理自身也失败 | 其他清理仍尝试，原始阶段与原因保持，附固定清理异常说明 |
| 已发送请求取消 / 排队取消或退出 | 已发送最多一次且不重放；排队零发送；另一会话可继续 |

### 5. Scenarios and Examples

- 正常：独立初始化完成 TLS、隔离与目标拒绝自检；账本 reserved=0，首次业务前不启动模型 worker。
- 边界：子进程报告 `{stage:"tls_probe",failureCode:"CERT_NOT_YET_VALID"}`，宿主保留具体子阶段并返回安全 503；只有未知子阶段时才使用宿主等待阶段。
- 错误用法：为定位 503 落盘整个异常、私有帧或 stderr，或把 500 ms 模型预算当成启动探针截止。正确做法：只展示白名单证据，按实际启动预算和故障注入验证。
- 错误用法：过早阻塞第一个子代理，再等待其余 Agent 的权限辅助请求；单账号串行池可能因此无法完成场景准备。正确做法：先观测六个独立实际子代理均已发起，再以闸门触发故障；录制层必须传播断开，工装不能额外施加默认空闲截止。

### 6. Tests Required

- tests/unit/local-pool-startup.test.ts：未知降级、直接代码与嵌套 cause 区别、旧 fatal 兼容、敏感扩展字段丢弃，真实管道 EOF/截断/格式/超时。
- tests/local-pool/startup.test.ts 与 tests/fixtures/local-pool-startup.ts：十一种故障、各自下一独立启动、四实例并发逐次回执、零模型、进程与临时目录清理；清理回执失败不能覆盖首错或阻止其他清理。
- tests/local-pool/session-isolation.test.ts 与 isolation-client.py：两个真实 PTY、各三个实际 Explore，活动取消、排队取消、子代理期间异常退出、排队异常退出；核对存活会话续轮、原始 SHA/CCH、会话头、父子证据及账本，无重复发送和跨会话污染。
- 所有上述模型验证使用仅 lo 的独立网络、合成账号和回环假池；故障注入仅属于测试工装，不增加产品环境开关或真实账号调用。

## Scenario: 手工本地池失败现场自动取证

### 1. Scope / Trigger

- 手工服务就绪后，后台汇总既有失败日志与同轮账本；一次性命令也可补采已停止服务的记录。取证不启动引擎、不调用模型、不读取真实池配置，不改变转发、重试、业务响应或日志等级。
- 数据所有者仍为 RequestTrace、日志表和 LocalPoolLedger；取证只读取脱敏元数据，不创建 LogStore 写线程、迁移数据库、读取正文或把中间值当最终实收。

### 2. Signatures

- `PoolIncidentCollector.open(options: PoolIncidentOptions): Promise<PoolIncidentCollector>`；options 含 runId、directory、可选新 output 目录及安全日志状态／固定诊断回调。
- `collect(requestId?: string): Promise<PoolIncidentStatus>` 一次性扫描；`start(): void` 后台轮询；`status(): PoolIncidentStatus` 返回副本；`close(finalScan = true): Promise<void>` 停止并收口，重复关闭复用结果。
- `projectPoolIncident(input: PoolIncidentEvidence): PoolIncidentReport` 是唯一白名单投影；传输阶段与计数继续复用 decodePoolTransportDiagnostics，错误码复用 POOL_FAILURE_CODES。
- `bun run collect:pool-incidents --run <ID> --run-dir <目录> [--request-id <ID>] [--output <新目录>]`；不接收外部地址、Key 或模型参数。

### 3. Contracts

- ready.json、ledger.json 与显式 runId 必须一致，至少一份有效运行元数据确认归属；仅按完全相同的 requestId 关联预留。重复预留为冲突，缺失／损坏字段为未知，不从时间接近、会话或异常原文猜测。
- 使用独立 readonly/strict SQLite 连接和 query_only，查询 requests/captures 元数据。正文只检查固定 bodies 目录中合法普通文件的存在性与尺寸；recordedStatus 和 bodyStorage 分开，哈希只保留原观测摘要，不声称重新验证正文。
- 自动候选为 error、http_error、stream_error、incomplete；success 与正常 canceled 不生成故障报告。日志 off 明示不能取得完整证据；summary 的头值标未保存；离线命令无法知道当前内存采集状态时保持未知。
- 每批最多 100 条，按 `(created_at,id)` 键分页，每个完整循环从头扫描，避免漏掉旧请求的晚终态；后台间隔 2 秒，收口等待阈值 5 秒，未取得回执仍保存明确缺口，不等待业务或重放请求。
- 报告写入 `<run>/incidents/reports/<requestId>.json`，状态写入 `<run>/incidents/status.json`，合法请求 ID `status` 不得碰撞。旧平铺报告只读兼容并保留原文件；旧 status.json 始终属于进度文件。补采新证据须用新的 output，不覆盖旧快照。
- schemaVersion=1 报告固定包含 collectedAt、runId、requestId、request、forwarding、transport、captures、correlations、evidenceGaps、interpretation。request 保存终态、时间、HTTP 状态、模式及采集异常是否存在；不复制 error、context 或模型正文。
- forwarding 分开保存 sourceState、reservedAt、attempted、localStatus、upstreamStatus、outcome、failureCode；未观测池响应头时 upstreamStatus=null，不以本地 502 回填。transport 的阶段与连接累计计数不能证明池端接收、执行或安全重试，rootCause 保持 unknown。
- captures 保留五阶段、attempt、时间、来源、表示、记录状态、观测／保存字节、SHA256 和正文存储检查。缺证以显式 null/unknown 及固定缺口码表示；不能用字段缺失冒充合法部分证据。
- 标识仅取 wire_final 的 x-client-request-id，以及 upstream_response 的 x-oneapi-request-id、x-ds-trace-id、x-amz-cf-id；注明 stage、attempt、header。同源同头不同值标冲突，不同头的标识独立；代理 CONNECT ID 无证据时未知。值限 256 位受限 ASCII，拒绝脱敏占位符、控制字符和非法值。
- 已有报告去重前必须完整验证固定字段、嵌套结构、枚举、可空值、阶段覆盖、标识对应关系及身份，拒绝额外载荷。完整声明未知的合法报告可复用；损坏或冲突文件保留并报 REPORT_CONFLICT，不静默跳过。
- 输出目录权限 0700，报告／状态 0600；拒绝符号链接输出。报告先写临时文件，再排他发布；状态只在自身目录原子更新。元数据／报告上限 1 MiB，账本读取上限 32 MiB，超限或落盘失败只影响取证，不限制业务发送或调用预算。
- 正常关闭在业务收口后停止定时器、等待当前批并做有界最终扫描；预算阈值 5 秒，未完成标 SHUTDOWN_PARTIAL。最终状态必须累计各页故障，末页成功不能清除前页失败；取证清理错误不覆盖业务清理错误。
- PoolIncidentStatus 保存 active/degraded/stopped、扫描时间、完整循环、计数、日志可用性和固定故障码。源码载荷、任意异常、完整头、凭据、地址和正文均不进入报告或诊断日志；输出不可写时仅输出固定故障码。

### 4. Validation & Error Matrix

| 条件 | 必须行为 |
| --- | --- |
| runId 冲突、运行身份无法确认 | RUN_MISMATCH / SOURCE_INVALID，拒绝跨源拼接 |
| 来源不存在、损坏、超限或占锁 | 固定 SOURCE_*，可用证据保留缺口，不触发模型 |
| 已有报告缺字段、非法嵌套值、额外载荷或身份冲突 | REPORT_CONFLICT，保留原文件 |
| 已有报告完整声明 null/unknown | 合法复用，不当成损坏，也不补造值 |
| 指定请求不存在或尚非失败终态 | REQUEST_NOT_FOUND / REQUEST_NOT_TERMINAL，不生成终态报告 |
| 输出不可用或最终扫描未结束 | REPORT_WRITE_FAILED / SHUTDOWN_PARTIAL，业务行为不变 |
| 首页失败、后页成功 | 最终 stopped 状态仍保留前页故障码 |

### 5. Scenarios and Examples

```bash
bun run collect:pool-incidents --run manual-001 --run-dir artifacts/local-pool-runs/manual-001 --request-id status
```

- 正常：该请求的报告保存为 `incidents/reports/status.json`，不会覆盖 `incidents/status.json`；重复扫描只读校验后跳过。
- 边界：旧账本没有传输诊断，或摘要没有响应标识，报告明确未知；原有平铺报告完整有效时只读复用。
- 错误用法：只看 schema/runId 或数组长度就认定已有报告完整，或用最后一页成功表示整个收口成功。正确做法：验证完整报告结构，并累计全部扫描页的故障。
- 错误用法：因没有池响应头断言模型未执行，或为补证据重放。正确做法：区分本地观测和池端证据，保留未知及原始单次发送约束。

### 6. Tests Required

- tests/unit/pool-incidents.test.ts：字段白名单、秘密排除、旧字段／零值、标识冲突、无代理证据、时间与阶段损坏、未知及 summary 语义。
- tests/integration/pool-incidents.test.ts：真实表只读补采、源记录不变、正文未打开、权限、分页／晚终态、并发采集、跨运行、CLI、来源和输出故障、停止后无活动。
- 同集成套件固定回归 CHK-001/FBK-001/FBK-002：保留字 ID、旧平铺报告、首中尾页故障及恢复、末页成功仍保留前页错误、损坏嵌套／额外字段与合法部分证据的区别。
- tests/local-pool/incidents.test.ts：无外网固定原版的连接拒绝、收头前断连、HTTP／流错误、缺终态、多会话精确归属、随后独立请求成功、取证不可用不影响业务、零真实推理及无重放。
