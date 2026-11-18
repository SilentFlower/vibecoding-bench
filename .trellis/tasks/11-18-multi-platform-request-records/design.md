# 多平台请求记录接入设计

## 1. 复用边界

复用DiagnosticsStore、RequestDiagnostic/AttemptDiagnostic、原管理接口和RequestDiagnostics.vue。CC现有UsageCapture及转发链保持；AGY按其Gemini源帧和原生控制事件生成同一存储需要的摘要。新增代码按AGY观察与采集职责组织，避免让CC解析器承担另一种协议。

诊断旁路不承担选号、凭据恢复、模型发送、工具回填或取消决策。根记录在鉴权后创建。目录及后台任务保持原边界。故障只更新健康/完整性与采集状态，业务继续原执行及单次提交语义。

## 2. 可缺省的事实合同

以下为拟新增字段分组，实际DTO保持显式类型与历史serde default。

| 层级 | 冻结或观测事实 |
| --- | --- |
| 根请求 | platform、entry_protocol、requested_model；原request_id/时间/HTTP状态/attempt_count保持 |
| 尝试 | 实际platform、kernel/version/source身份、submitted_model、源response_model/modelVersion、环境及凭据代次、worker及原生conversation/trajectory |
| AGY用量 | source=gemini_usage_metadata、有界usage_metadata、总量/思考及现有输入/输出/缓存投影、完整性 |
| 策略 | requested开关与实际处理回执分开保存；schema/rule/version/hash/source/changed/替换数沿依赖合同 |
| 工具 | continuation_of_request_id、原attempt归属、账号域匿名工具标识、最近观测的原生工具状态与收口时刻 |

requested_model来自实际HTTP输入；submitted_model来自同次受信目录和提交；响应字段仅在源帧存在时填写。AGY调用claude-模型仍标antigravity/AGY1.5.9，不能套CC画像。各身份先核对所属请求/尝试/账号，摘要只保存明确白名单或账号域散列。原始functionCall/结果留在受控内容视图。

历史新字段缺失保持未知，使用“历史未记录”展示。当前账号名称/邮箱沿原查询投影，不能用当前platform/版本/策略回填历史事实。筛选增加history_unknown选项，以明确覆盖旧记录。

## 3. HTTP、尝试和工具生命周期

Gemini鉴权后冻结日志模式，建立TraceContext和HTTP终结保护，附加既有X-CC2API-Request-Id关联头。HTTP根ID与实际attempt UUID独立。根上下文及AGY观察对象显式传入drive后台任务，避免依赖task-local跨spawn传播。

选号、凭据、环境准备和原生准备在各自失败边界记录阶段。准备观察不增加尝试；在真实私有提交边界登记attempt。传输异常保留提交未知；不能据此生成成功、虚构模型调用数或自动重放。原生model_calls是独立事实，缺失保持未知。401恢复先终结原attempt，再建立同根下的新attempt并记录oauth_recovery，沿原系统策略快照及原截止。

源帧更新用量、首次有效输出和源终态；内核completed/job_finalized分别更新响应和控制事实。HTTP响应体消费/Drop终结根，后台实际作业继续原取消/收口流程。对工具响应，HTTP可成功且原生状态waiting；后续HTTP从已核对ToolTurn取得前驱根与attempt，不以请求体相似度构造额外诊断会话。

为原生工具状态增加限定字段更新命令，沿原串行诊断队列处理。只更新所属attempt的工具状态/时间及关联元数据，保留根finished_at、outcome、HTTP耗时及attempt_count；迟到普通快照继续受原防回退保护。工具完成只更新工具结果；原控制终态仅由实际job_finalized回执通过独立control_state/control_observed_at补写。原生error/cancelled先终结所观测的尝试，物理收口保持未知。取消和截止有明确来源才写收口。进程重启后保留最后观测和缺口，不声称恢复原内存工具作业。

## 4. 协议用量和性能

AGY观察器直接消费已校验的Gemini源JSON，采用累计计数最大值及最终源事实，不逐帧累加。promptTokenCount、candidatesTokenCount、cachedContentTokenCount、thoughtsTokenCount、totalTokenCount分别保留；缺失字段为None，CC缓存写与AGY缓存读分别表达。usage_metadata以有界脱敏对象保存原字段/来源，超限或异常标记partial及截断。任意字符串、深度、数组和扩展均受白名单及字节预算控制，不能突破原16KiB摘要上限。

ttft_ms继续表示所测响应头边界，并标明AGY私有发送器来源；first_output_ms为首次有效文本/思考/函数输出观察，keepalive与单独usage不算输出。根HTTP总耗时、attempt耗时与工具后续收口独立。平均TPS只沿同一完整成功尝试计算。真实供应商缓存/分词与费用效果属于独立外部验收；usage_records价格、遥测及账号额度语义保持。

## 5. 有界内容旁路

同HTTP冻结info/debug；账号目录开关与模式共同控制采集。入口复用native_capture::ingress的脱敏、有序头和原始逻辑字节预览；通过独立有界旁路发布到已绑定账号的快照存储。该发布独立于模型请求信封，失败、旧组件不支持或超时仅记录缺口，不重放模型、不扩展业务截止。

原始执行材料在临时worker目录生成并沿原关闭流程清理；长期采集仅保留有界脱敏快照。AGY执行侧按实际attempt生成独立脱敏预览，使用既有gemini-input和本次Cortex提交事实，不能将原始supervisor配置、HOME、NDJSON全文件作为管理下载。入站、decoded_gemini_input、native_cascade_prompt_sections分别声明representation/source；未有AGY最终TLS证据时wire_final显示unavailable。源usage及响应内容按同次权限处理。

复用现有/admin/request-diagnostics/:request_id/captures/:attempt_id管理路径；先核对已保存请求/attempt，再按持久平台选择受信内部读取。内部读取/发布都核对服务鉴权、唯一账号环境绑定、标准UUID、账号/环境归属和冻结状态。路径由受控平台映射固定，不能接受调用方传任意目录。复用目录FD/NOFOLLOW/普通文件/私有权限、原子发布和七天验期。

正文预览共享2MiB、头128KiB、序列化6MiB；每账号采集总量沿1GiB预算，AGY原有调试材料与新增快照统一纳入清理范围。活跃worker/工具材料受保护，空间不足丢弃采集并记录状态。后台清理有批次/时间预算，读取不唤醒环境。info及账号关闭分别显示摘要/已关闭，历史debug按当时事实读取。旧采集阶段保持原合同。

## 6. 查询与追加迁移

DiagnosticQuery拟增加platform、entry_protocol、kernel_version、requested_model、actual_model；account_id沿原字段。严格校验值域、长度与安全标识，全部SQL参数化。筛选在服务端执行，根与各尝试按事实关联，counts去掉结果维度后保留其余条件；不在当前页计算全量统计，不新增逐行详情查询。

新增必要投影列及索引，完整事实继续保存在有界summary_json。独立纯迁移模块拟登记gateway.request-records.6，追加执行及结构核验、module导出、registry摘要和system_release精确来源映射；gateway.baseline.1及步骤2—5冻结。SQLite凭据提交及诊断限定更新在读取前取得写入权限，避免新增并行诊断写入触发读快照升级冲突；原凭据CAS及RT所有权条件保持。PG沿原初始化调用同一增量定义，核对Any空值绑定类型。历史原行和JSON保持，新增投影为空并可显式查询历史未知。

隔离库验证5→6、空库、重复、重开连接和旧程序compatible_newer读写，核对已登记校验和及账号/凭据保持。仅演练通过后声明兼容；实际生产迁移、发行附件签发和部署走后续发布流程。

## 7. 既有UI与验收

在原筛选区追加平台/协议/内核/请求模型/实际模型，按390px折叠既有高级筛选。账号选择器展示全平台可选账号并保留明确平台标记；请求平台以持久事实为准。沿现有四页签与选择器呈现策略、源用量、身份和工具关联，沿原异步代次、AbortController、焦点返回及分页组件。

验证复用Rust存储/router/diagnostics用例和管理浏览器探针，扩展真实HTTP/SQLite合成发送器与固定原版本地TLS探针。每场景同时核对HTTP、数据库、管理API及相应DOM；原生来源独立记录，真实外部调用0。CC行为与完整Rust回归、Web构建、相关Python/部署回归均为交付门槛。
