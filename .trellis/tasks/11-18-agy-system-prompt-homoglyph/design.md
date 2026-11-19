# AGY系统提示词同形体接入设计

## 1. 已核对定义与真实边界

Account已有agy_system_prompt_homoglyph_enabled，账号创建/更新和Accounts.vue均已保存、回读该布尔字段。AgySubmission目前包含request、api_token_id、credential_snapshot、model、native_model、body、capture_enabled并拒绝未知字段；AgyToolCompletion独立绑定原请求和真实工具结果。

Gemini入口在账号选择及原许可准入后读当前Account并提交AgySubmission。drive持有原始body，认证恢复重用同一body。监督器严格验证私有信封，Worker.send发送独立gemini_request。gemini_contract.decode_request从systemInstruction.parts[].text合并得到独立system，同时保留gemini_body深拷贝及native_steps。Kernel.execute将system写入plannerConfig.declarativeMixinConfig.promptSections[].custom.content。

本地固定原版基线已验证该配置进入Google协议request.systemInstruction.parts[].text。普通、SSE和工具场景共9次合成生成均保持测试系统文本。该边界允许只转换独立system，不改gemini_body、历史和工具。

## 2. 单一规则来源与纯转换

拟新增agy_runtime内的纯策略模块和固定JSON规则资源。26个ASCII键及非ASCII目标逐项取自已核对参考表，规则标识采用稳定版本（首版new-api-homoglyph-v1），来源及摘要保存在任务研究材料。

字符映射仅定义于一个受管理资源，构建时纳入admission资源哈希。正式镜像不依赖外部new-api目录、Node进程、网络或开发机私有路径。Rust只持有私有合同的规则版本标识，不复制字符表。

转换按Unicode码点逐字查表，未命中的码点原样保留。所有目标都不属于源键，保证T(T(s))=T(s)。不归一化、不反向替换、不添加分隔符。映射改变UTF-8字节数，原码点数量保持一致。替换数和系统长度仅用于处理事实诊断。

## 3. 私有快照及兼容

拟为AgySubmission增加可缺省的system_prompt_policy对象，包含schema_version=1、enabled:boolean、rule_version:string。缺省解释为关闭；关闭时可省略序列化字段以维持旧默认请求的兼容。显式畸形类型、未知字段、未知版本或规则拒绝。

公共请求体不提供策略覆盖入口，策略只来自已选账号配置。账号读取后构造不可变快照，传输、监督器和内核逐层校验并按原request/attempt身份携带。认证恢复显式复用该快照；不重新读取开关。新HTTP工具续轮在原工具真实回填后冻结其本次账号策略，原工具收口使用原工作进程及原记录。

新增字段为私有协议的受控扩展，原NDJSON schema维持1。既有AgySubmission的deny_unknown_fields和监督器严格字段集合会拒绝启用扩展；该拒绝保持失败，不回退到未转换发送。启用请求须收到匹配的策略处理回执才继续交付。部署使用现有组件内容身份触发账号组件更新，各生产者/消费者组合加入兼容断言。回退先关闭后续请求策略并收口在途，再按既有兼容镜像流程操作。

## 4. 原生处理点与进程复用

在解码并验证完Gemini输入后，策略模块只处理独立system；保留gemini_body作为转换前的已解码Gemini视图。执行仍使用现有custom prompt section和原生RPC。

策略是请求属性，排除在worker池身份之外；切换账号开关不要求重建暖worker。模型、凭据、代理及资源身份继续按现有worker key冻结。原截止、物理并发、背压、取消、有界恢复及AT-only边界保持。

系统不存在或为空时沿原行为；已由外部链路转换过的文本在开启时保持幂等。多Part先解码合并，换行本身不参与映射，因此转换与合并顺序一致。非系统结构继续使用原有已验证映射，不通过序列化全文正则改写。

## 5. 事件、视图与敏感保护

本次事件拟增加system_prompt_policy元数据：冻结enabled、schema/规则版本、规则资源身份、处理source、changed及替换码点数。关闭、空目标、已经映射和真实替换分别可由开关、目标长度和changed判断。

网关保存请求策略事实，内核给出实际处理回执；source准确标识Cortex自定义系统段，不能标作逐请求HTTPS线字节观察。沿现有账号、环境、worker、credential_generation、HTTP request、attempt和工具关联字段串联。公开Gemini响应不添加内部策略字段。

采集开启时，gemini-input.json是转换前的已解码入站视图，input-mapping.json登记处理决策，既有rpc.ndjson保存处理后的原生提交。原始HTTP线字节归后续请求记录采集合同。采集关闭时不额外落完整系统文本。网关日志仅投影必要元数据，禁止输出系统正文、凭据及工具参数。

usageMetadata、cachedContentTokenCount及思考等扩展继续来自上游源帧。稳定输入的转换文本可直接比较；真实供应商分词、缓存命中及计费不能由字符计数推导，保持外部验收。

## 6. UI、数据及交付

复用现有账号字段、保存接口和控件，更新“接入后生效”的过期提示，拟显示“按当前账号保存，开启后转换系统提示词文本。”。保持开关默认、平台显示规则、草稿、焦点及账号代次保护。

当前范围预计无需追加数据库迁移。执行代码位于gateway和orchestrator，前端仅对应设置提示及回归。Task原package=runtime是早期占位；当前主要归属改为orchestrator。services/runtime的TS实现不在当前影响面。

## 7. 验证与回退

先纯转换与私有合同测试，再真实HTTP/SQLite验证两个账号、开关动态变化、工具和认证恢复快照。原生验收扩展既有本地TLS探针，对照原始入站、Cortex提交及实际request.systemInstruction，验证其他字段及usage保真。包含普通/SSE、工具往返、缺省、幂等、大文本和关闭采集。

真实模型调用预算0；测试只使用合成身份和断网容器。大文本遵循现有内存和截止，验收记录实际边界。真实Google分词、缓存及用量影响由后续明确授权和独立预算承接。回退通过关闭开关控制新请求，原在途按冻结策略收口，权威凭据和身份保持。
